#!/usr/bin/env python3
"""สร้าง data/tour.js และภาพสำหรับเว็บ จากภาพ 360° ใน Asset/

ขั้นตอน
  1. ประมาณทิศเดิน + มุมหมุนระหว่างภาพคู่ที่เชื่อมกัน (tools/estimate_links.py)
     ผลเก็บไว้ที่ tools/links-cache.json (ลบไฟล์นี้ถ้าต้องการคำนวณใหม่)
  2. ไล่ตำแหน่งบนแผนผังแบบ dead-reckoning และหา northOffset ของทุกภาพ
     ระยะก้าวประมาณจากสามเหลี่ยมของภาพสามภาพติดกัน
  3. ย่อภาพเป็น 4096×2048 ลง images/panoramas/ และเขียน data/tour.js

ใช้งาน (จากรากโปรเจกต์):
  pip install numpy opencv-python-headless pillow
  python3 tools/build_tour.py
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estimate_links as est  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(ROOT, "Asset")
OUT_IMG = os.path.join(ROOT, "images", "panoramas")
CACHE = os.path.join(ROOT, "tools", "links-cache.json")
OUT_W = 4096


def src(n, kind="-scaled"):
    return os.path.join(ASSET, "20210903_044411_%s%s.jpg" % (n, kind))


# เส้นทางหลักตามลำดับการถ่าย (224 ซ้ำกับ 215 จึงตัดออก, 181 และ 197 เป็นทางแยก)
MAIN = ["039", "048", "050", "053", "057", "060", "063", "065", "069", "072",
        "075", "080", "086", "089", "093", "096", "098", "105", "113", "116",
        "119", "122", "125", "128", "130", "136", "143", "145", "148", "151",
        "153", "155", "158", "172", "175", "177", "179", "183", "189", "194",
        "195", "199", "201", "203", "205", "206", "209", "210", "212", "215",
        "220"]
EXTRA = [("096", "105"), ("183", "181"), ("195", "197")]

# คู่ที่จับจุดเด่นไม่ได้ (ภาพต่างกันมาก) — กำหนดจากการดูภาพ
#   yaw: ทิศไปภาพปลายทาง (yaw ในภาพต้นทาง), rot: yaw ในภาพต้นทางที่ตรงกับ yaw 0 ของปลายทาง
MANUAL = {
    ("183", "181"): {"yaw": 175.0, "rot": -5.0, "len": 0.6},    # หลังองค์พระพุทธรูป
    ("195", "199"): {"yaw": -72.0, "rot": -176.0, "len": 1.0},  # ประตู → ระเบียงซ้าย
    ("195", "197"): {"yaw": 100.0, "rot": -176.0, "len": 1.2},  # ประตู → ระเบียงขวา (บันได)
}

ZONES = [
    (["039", "048", "050", "053", "057", "060", "063", "065"],
     "โซนวิถีชีวิตและเครื่องใช้พื้นบ้าน",
     "เครื่องมือเครื่องใช้พื้นบ้าน หูก กี่ทอผ้า และบอร์ดนิทรรศการพุทธศิลป์"),
    (["069", "072", "075", "080", "086", "089"],
     "โซนจิตรกรรมร่วมสมัย",
     "ภาพจิตรกรรมพุทธศิลป์ร่วมสมัยและมุมสักการะรูปเหมือนพระเถระ"),
    (["093", "096", "098", "105", "113", "116", "119", "122", "125", "128"],
     "โซนคัมภีร์และเครื่องสักการะ",
     "คัมภีร์โบราณ เครื่องสักการะ และงานจิตรกรรมบนแผ่นไม้"),
    (["130", "136", "143", "145", "148", "151"],
     "โซนพระพุทธรูป",
     "พระพุทธรูปหลากหลายพุทธลักษณะที่จัดแสดงบนแท่นไม้"),
    (["153", "155", "158", "172", "175", "177", "179"],
     "โซนธรรมาสน์และบุษบก",
     "ธรรมาสน์ บุษบก สัปทน และเครื่องประกอบพิธีกรรมทางพุทธศาสนา"),
    (["181", "183"],
     "พระพุทธรูปประธาน",
     "พระพุทธรูปประทับนั่งพร้อมเครื่องสักการะ และจิตรกรรมพื้นหลัง"),
    (["189", "194"],
     "มุมแผงพระพิมพ์",
     "แผงพระพิมพ์ที่ประดิษฐานพระพุทธรูปองค์เล็กจำนวนมาก ใกล้ประตูทางออก"),
    (["195"], "ประตูหอพุทธศิลป์", "ประตูเชื่อมระหว่างห้องจัดแสดงกับระเบียงด้านนอก"),
    (["197"], "ระเบียงฝั่งบันได", "ระเบียงด้านนอกอาคาร ฝั่งบันไดขึ้นชั้นบน"),
    (["199", "201", "203", "205", "206", "209", "210", "212"],
     "ระเบียงทางเดิน",
     "ระเบียงทางเดินด้านนอกเลียบหอพุทธศิลป์"),
    (["215"], "ลานหน้าอาคาร", "ลานโล่งหน้าทางเข้าหอพุทธศิลป์"),
    (["220"], "ทางเข้าหอพุทธศิลป์", "ประตูทางเข้าหอพุทธศิลป์ มจร วิทยาเขตแพร่"),
]
FIRST = "220"


def zone_of(n):
    for ids, title, desc in ZONES:
        if n in ids:
            return title, desc
    raise KeyError(n)


def estimate_pairs(pairs):
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    feats = {}

    def F(n):
        if n not in feats:
            im = est.load(src(n))
            feats[n] = (est.features(im), (im.shape[1], im.shape[0]))
        return feats[n]

    for a, b in pairs:
        key = a + ">" + b
        if key in cache:
            continue
        fa, wh = F(a)
        fb, _ = F(b)
        r = est.estimate(fa, fb, wh) or {"inliers": 0}
        cache[key] = {k: float(v) for k, v in r.items()}
        print("  ", key, cache[key], file=sys.stderr)
        json.dump(cache, open(CACHE, "w"), indent=1, sort_keys=True)
    return cache


def unit(b):
    r = math.radians(b)
    return np.array([math.sin(r), -math.cos(r)])


def main():
    est.WIDTH = 2560
    edges = list(zip(MAIN, MAIN[1:])) + EXTRA
    triples = [(MAIN[i], MAIN[i + 2]) for i in range(len(MAIN) - 2)]
    cache = estimate_pairs([e for e in edges if e not in MANUAL] + triples)

    def rel(a, b):
        if (a, b) in MANUAL:
            return MANUAL[(a, b)]
        return cache[a + ">" + b]

    # northOffset (n) ไล่ตามเส้นทาง: ทิศเดียวกันในโลก  yaw_b = yaw_a − rot
    north = {MAIN[0]: 0.0}
    for a, b in edges:
        if b not in north:
            north[b] = north[a] - rel(a, b)["rot"]

    def bearing(a, b):
        return rel(a, b)["yaw"] - north[a]

    # ระยะก้าวจากสามเหลี่ยม A-B-C  (s1·AB + s2·BC = s3·AC)
    step = {}
    for i in range(len(MAIN) - 2):
        a, b, c = MAIN[i:i + 3]
        t = cache.get(a + ">" + c, {})
        if (a, b) in MANUAL or (b, c) in MANUAL or t.get("inliers", 0) < 40 or t.get("cheirality", 0) < 0.85:
            continue
        M = np.stack([unit(bearing(b, c)), -unit(t["yaw"] - north[a])], 1)
        try:
            s2, s3 = np.linalg.solve(M, -unit(bearing(a, b)))
        except np.linalg.LinAlgError:
            continue
        if 0.25 < s2 < 4 and s3 > 0:
            step.setdefault((b, c), []).append(s2)   # สัมพัทธ์กับ |AB|
    length = {(MAIN[0], MAIN[1]): 1.0}
    for i in range(1, len(MAIN) - 1):
        a, b, c = MAIN[i - 1], MAIN[i], MAIN[i + 1]
        prev = length[(a, b)]
        if (b, c) in MANUAL:
            length[(b, c)] = MANUAL[(b, c)]["len"]
        elif (b, c) in step:
            length[(b, c)] = float(np.clip(prev * step[(b, c)][0], 0.4, 2.5))
        else:
            length[(b, c)] = 1.0
    for e in EXTRA:
        length.setdefault(e, MANUAL.get(e, {}).get("len", 1.0))

    # จัดให้ระเบียงทางเดินชี้ไปทางขวาของแผนผัง
    turn = 90 - bearing("199", "201")
    for k in north:
        north[k] = ((north[k] - turn + 180) % 360) - 180

    pos = {MAIN[0]: np.zeros(2)}
    for a, b in list(zip(MAIN, MAIN[1:])) + EXTRA:
        if b not in pos:
            pos[b] = pos[a] + length[(a, b)] * unit(bearing(a, b))
    pts = np.array(list(pos.values()))
    lo, hi = pts.min(0), pts.max(0)
    scale = 88 / max(hi - lo)
    off = (100 - (hi - lo) * scale) / 2
    mp = {k: (v - lo) * scale + off for k, v in pos.items()}

    # ภาพ
    os.makedirs(OUT_IMG, exist_ok=True)
    order = MAIN[:]
    order.insert(order.index("183"), "181")
    order.insert(order.index("199"), "197")
    for n in order:
        out = os.path.join(OUT_IMG, "p%s.jpg" % n)
        if not os.path.exists(out):
            im = cv2.imread(src(n, ""))
            im = cv2.resize(im, (OUT_W, OUT_W // 2), interpolation=cv2.INTER_AREA)
            cv2.imwrite(out, im, [cv2.IMWRITE_JPEG_QUALITY, 82, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
            print("   ภาพ", out, file=sys.stderr)

    links = {n: [] for n in order}
    for a, b in edges:
        if (a, b) in EXTRA and (a, b) not in MANUAL:
            # ทางลัดนอกเส้นทางหลัก: ใช้ทิศที่วัดได้ตรง ๆ แทนการคำนวณจากแผนผัง
            r = rel(a, b)
            back = ((r["yaw"] + 180 - r["rot"] + 180) % 360) - 180
            links[a].append({"to": "p" + b, "yaw": round(r["yaw"], 1)})
            links[b].append({"to": "p" + a, "yaw": round(back, 1)})
        else:
            links[a].append({"to": "p" + b})

    count = {}
    scenes = []
    for n in order:
        title, desc = zone_of(n)
        count[title] = count.get(title, 0) + 1
        scenes.append({
            "id": "p" + n,
            "title": title,
            "description": desc,
            "image": "images/panoramas/p%s.jpg" % n,
            "map": {"x": round(float(mp[n][0]), 1), "y": round(float(mp[n][1]), 1)},
            "northOffset": round(north[n], 1),
            "links": links[n],
        })
    # ใส่ลำดับเมื่อชื่อซ้ำกันในโซน
    seen = {}
    for s in scenes:
        if count[s["title"]] > 1:
            seen[s["title"]] = seen.get(s["title"], 0) + 1
            s["title"] = "%s (%d)" % (s["title"], seen[s["title"]])

    tour = {
        "title": "หอพุทธศิลป์",
        "subtitle": "พิพิธภัณฑ์เสมือนจริง 360° · มหาวิทยาลัยมหาจุฬาลงกรณราชวิทยาลัย วิทยาเขตแพร่",
        "firstScene": "p" + FIRST,
        "floorPlan": {"image": None, "rooms": []},
        "scenes": scenes,
    }
    with open(os.path.join(ROOT, "data", "tour.js"), "w") as f:
        f.write("/*\n * ข้อมูลทัวร์ 360° หอพุทธศิลป์ — สร้างโดย tools/build_tour.py\n"
                " * แก้ชื่อ/คำบรรยาย/จุดข้อมูล (infos) ได้โดยตรง หรือแก้ใน build_tour.py แล้วรันใหม่\n"
                " * ความหมายของแต่ละช่อง ดู README.md\n */\n")
        f.write("window.TOUR = ")
        json.dump(tour, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print("scenes:", len(scenes), file=sys.stderr)


if __name__ == "__main__":
    main()
