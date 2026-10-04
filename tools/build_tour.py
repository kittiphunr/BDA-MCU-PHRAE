#!/usr/bin/env python3
"""สร้าง data/tour.js และภาพสำหรับเว็บ จากภาพ 360° ใน Asset/

ขั้นตอน (จากรากโปรเจกต์)
  1. python3 tools/pairs.py window 5
       เปรียบเทียบภาพทุกคู่ที่ถ่ายห่างกันไม่เกิน 5 ภาพ (SIFT + Essential matrix บนทรงกลม)
       ผลเก็บใน tools/links-cache.json
  2. python3 tools/build_tour.py
       - คำนวณมุมหันและตำแหน่งของทุกจุดพร้อมกันจากทุกคู่ (tools/solve_map.py)
       - หมุนแผนผังให้ผนังห้อง (ห้องเป็นกล่อง) ขนานแกน และวาดกรอบห้อง
       - เลือกลูกศรไปยังจุดใกล้เคียงหลายทิศ (คู่สั้นก่อน ไม่ให้ลูกศรชี้ซ้อนกัน)
       - ใส่จุดข้อมูลงานศิลปะจาก tools/artworks.json
       - ย่อภาพเป็น 4096×2048 ลง images/panoramas/ และเขียน data/tour.js
  (ไม่บังคับ) ถ้าแผนผังเปลี่ยนมาก ให้หาคู่ที่อยู่ใกล้กันบนแผนผังเพิ่มด้วย
       python3 tools/pairs.py list 130>153 ...   แล้วรันข้อ 2 ใหม่

ต้องติดตั้ง: pip install numpy scipy opencv-python-headless
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solve_map  # noqa: E402
import geometry  # noqa: E402

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
# ภาพทั้งหมดตามลำดับการถ่าย (รวมทางแยก)
ALL = MAIN[:MAIN.index("183")] + ["181"] + MAIN[MAIN.index("183"):MAIN.index("199")] + ["197"] + MAIN[MAIN.index("199"):]
EXTRA = [("096", "105"), ("183", "181"), ("195", "197")]

# คู่ที่จับจุดเด่นไม่ได้ (ภาพต่างกันมาก) — กำหนดจากการดูภาพ
#   yaw: ทิศไปภาพปลายทาง (yaw ในภาพต้นทาง), rot: yaw ในภาพต้นทางที่ตรงกับ yaw 0 ของปลายทาง
MANUAL = {
    ("183", "181"): {"yaw": 175.0, "rot": -5.0, "len": 0.6},    # หลังองค์พระพุทธรูป
    # ยืนที่ประตูหันออกนอก (yaw 0): ห้องโถงอยู่ด้านหลัง ระเบียงไปทาง 199→212 อยู่ทางขวา
    # (เดินไปทาง 212 แล้วห้องโถงอยู่ขวามือ ตรงกับภาพ 199/201) ส่วนบันได (197) อยู่ทางซ้าย
    ("195", "199"): {"yaw": 72.0, "rot": 4.0, "len": 1.0},
    ("195", "197"): {"yaw": -100.0, "rot": 4.0, "len": 1.2},
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
FIRST = "215"
# มุมเปิดของหน้าแรก: ลานหน้าอาคาร หันหน้าเข้าประตูที่มีป้าย "ห้องพุทธศิลป์" (SW 220°)
FIRST_VIEW = {"yaw": -175.8, "pitch": 0}

DOOR = ("194", "195")   # ประตูระหว่างห้องโถงกับระเบียง
# ลิงก์ที่กำหนดเอง (เพิ่มหลังเลือกลูกศรอัตโนมัติ): เดินจากระเบียง/ทางเข้า เข้าห้องโถงที่มุมแผงพระพิมพ์
EXTRA_LINKS = [("212", "194"), ("220", "194")]

# คู่ที่ผลคำนวณขัดกับคู่อื่น (มุมหมุนผิด) — ไม่ใช้
SKIP = {"098>105"}

# กรอบห้องบนแผนผัง: (ชื่อ, จุดถ่ายในห้อง, ระยะเผื่อขอบ)
ROOMS = [
    ("ห้องจัดแสดง หอพุทธศิลป์", [n for n in ALL[:ALL.index("194") + 1] if n != "113"], 1.5),
    ("ระเบียงทางเดิน", ALL[ALL.index("195"):], 1.0),
]
ARTWORKS = os.path.join(ROOT, "tools", "artworks.json")


def artworks():
    return json.load(open(ARTWORKS)) if os.path.exists(ARTWORKS) else []


def load_artworks(keep=None):
    """จุดข้อมูลงานศิลปะ (tools/artworks.json) → {ภาพ: [infos]} เฉพาะภาพที่ใช้"""
    out = {}
    for a in artworks():
        for p in a.get("placements", []):
            if keep is not None and p["pano"] not in keep:
                continue
            out.setdefault(p["pano"], []).append({
                "yaw": p["yaw"], "pitch": p["pitch"], "artwork": a["id"],
                "title": a["title"], "subtitle": a.get("title_en", ""),
                "card": "images/artworks/%s.jpg" % a["id"],
            } | ({"approx": True} if p.get("approx") else {}))
    return out


def zone_of(n):
    for ids, title, desc in ZONES:
        if n in ids:
            return title, desc
    raise KeyError(n)


def load_edges():
    """คู่ภาพที่ใช้ได้จาก tools/links-cache.json (สร้างด้วย tools/pairs.py) + คู่ที่กำหนดเอง"""
    cache = json.load(open(CACHE))
    verified = set(zip(MAIN, MAIN[1:])) | set(EXTRA)
    edges = []
    for key, r in cache.items():
        a, b = key.split(">")
        if a not in ALL or b not in ALL or (a, b) in MANUAL or key in SKIP:
            continue
        # คู่ตามเส้นทางเดิมผ่านการตรวจด้วยตาแล้ว จึงผ่อนเกณฑ์ลงได้
        if solve_map.reliable(r) or ((a, b) in verified and r.get("inliers", 0) >= 25):
            edges.append((a, b, r["yaw"], r["rot"], min(r["inliers"], 300)))
    for (a, b), m in MANUAL.items():
        edges.append((a, b, m["yaw"], m["rot"], 40))
    missing = [e for e in verified if e not in MANUAL and a_b(e) not in cache]
    if missing:
        sys.exit("ยังไม่ได้เปรียบเทียบคู่: %s — รัน python3 tools/pairs.py window 5 ก่อน" % missing)
    return edges


def a_b(e):
    return e[0] + ">" + e[1]


def pick_links(pos, edges, min_sep=35, max_links=6):
    """เลือกลูกศร: คู่สั้นก่อน ไม่ให้ลูกศรสองอันในจุดเดียวกันชี้ใกล้กันเกิน min_sep องศา"""
    def bearing(a, b):
        v = pos[b] - pos[a]
        return math.degrees(math.atan2(v[0], -v[1]))

    chosen = {n: [] for n in pos}        # n -> [(bearing, other)]
    order = sorted(edges, key=lambda e: np.linalg.norm(pos[e[1]] - pos[e[0]]))

    def free(a, b):
        t = bearing(a, b)
        return len(chosen[a]) < max_links and all(
            abs(solve_map.wrap(t - u)) >= min_sep for u, _ in chosen[a])

    keep = []
    for e in order:
        a, b = e[0], e[1]
        if free(a, b) and free(b, a):
            chosen[a].append((bearing(a, b), b))
            chosen[b].append((bearing(b, a), a))
            keep.append((a, b))
    # ให้ทุกจุดเดินถึงกันได้: เติมคู่สั้นที่สุดที่เชื่อมกลุ่มที่แยกกัน
    parent = {n: n for n in pos}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in keep:
        parent[root(a)] = root(b)
    for e in order:
        a, b = e[0], e[1]
        if root(a) != root(b):
            parent[root(a)] = root(b)
            keep.append((a, b))
    return keep


ATLAS = os.path.join(ROOT, "images", "model", "atlas.jpg")
ATLAS_CELL = (1024, 512)
ATLAS_COLS = 4


def build_atlas(order):
    """รวมภาพ 360° ขนาดเล็กเป็นภาพเดียว ใช้ฉายลงพื้น/ผนังของโมเดล 3 มิติ"""
    w, h = ATLAS_CELL
    rows = -(-len(order) // ATLAS_COLS)
    atlas = np.zeros((rows * h, ATLAS_COLS * w, 3), np.uint8)
    cells = {}
    for i, n in enumerate(order):
        r, c = divmod(i, ATLAS_COLS)
        im = cv2.imread(src(n, "-2048x1024"))
        atlas[r * h:(r + 1) * h, c * w:(c + 1) * w] = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
        cells["p" + n] = [c, r]
    os.makedirs(os.path.dirname(ATLAS), exist_ok=True)
    cv2.imwrite(ATLAS, atlas, [cv2.IMWRITE_JPEG_QUALITY, 80, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
    return {"image": "images/model/atlas.jpg", "cols": ATLAS_COLS, "rows": rows, "cells": cells}


# เข็มทิศ: มองออกทางประตูห้องโถง (จาก 194 ไป 195) หันไปทิศตะวันออกเฉียงเหนือ 35° (ข้อมูลจากผู้ดูแล)
DOOR_AZIMUTH = 35.0


def compass(north):
    """มุมทิศจริง (องศาจากทิศเหนือ ตามเข็มนาฬิกา) ของ "ด้านบนแผนผัง"
    ทิศประตูบนแผนผัง = yaw ที่วัดได้ใน 194 ไปยัง 195 − northOffset ของ 194"""
    door_yaw = json.load(open(CACHE))[a_b(DOOR)]["yaw"]
    door_bearing = solve_map.wrap(door_yaw - north[DOOR[0]])
    return {"door": "p" + DOOR[0], "doorYaw": round(door_yaw, 1), "doorAzimuth": DOOR_AZIMUTH,
            "mapUpAzimuth": round((DOOR_AZIMUTH - door_bearing) % 360, 1)}


def same_room(a, b):
    corridor = ALL.index("195")
    return (ALL.index(a) >= corridor) == (ALL.index(b) >= corridor) or {a, b} == set(DOOR)


def walk_edges(pos, used, keep, spacing):
    """ทางเดินระหว่างจุดที่เก็บไว้: คู่ที่วัดได้โดยตรง + ทางที่เคยผ่านจุดที่ถูกตัด (A–x–B เกือบเป็นเส้นตรง)
    ไม่เชื่อมข้ามผนังระหว่างห้องโถงกับระเบียง ยกเว้นที่ประตู"""
    K = set(keep)
    out = {tuple(sorted(e[:2])) for e in used if e[0] in K and e[1] in K and same_room(e[0], e[1])}
    adj = {}
    for a, b, *_ in used:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    for x in ALL:
        if x in K:
            continue
        nb = sorted(n for n in adj.get(x, ()) if n in K)
        for i, a in enumerate(nb):
            for b in nb[i + 1:]:
                va, vb = pos[a] - pos[x], pos[b] - pos[x]
                cos = va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb))
                if (cos < math.cos(math.radians(110)) and same_room(a, b)
                        and np.linalg.norm(pos[a] - pos[b]) <= 2.2 * spacing):
                    out.add(tuple(sorted((a, b))))
    return sorted(out)


def main():
    import select_panos
    edges = load_edges()
    north, pos, used = solve_map.solve(ALL, edges, ALL[0])
    # ตัดภาพที่ซ้ำซ้อน: แผนผังคำนวณจากทุกภาพ (แม่นกว่า) แต่ทัวร์ใช้เฉพาะภาพที่เลือก
    keep = select_panos.select({k: np.asarray(v) for k, v in pos.items()})
    walks = walk_edges(pos, used, keep, select_panos.SPACING)
    # ห้องเป็นกล่อง: หมุนให้ผนังขนานแกน แล้วหมุนอีก 90° ให้ห้องยาวตามแนวนอนของจอ
    turn = solve_map.manhattan_angle(north, used) + 90
    R = math.radians(-turn)
    rot = np.array([[math.cos(R), -math.sin(R)], [math.sin(R), math.cos(R)]])
    pos = {n: rot @ p for n, p in pos.items()}
    north = {n: solve_map.wrap(v + turn) for n, v in north.items()}

    pos = {n: pos[n] for n in keep}
    north = {n: north[n] for n in keep}
    pts = np.array(list(pos.values()))
    lo, hi = pts.min(0), pts.max(0)
    scale = 92 / max(hi - lo)
    mp = {k: (v - lo) * scale + 4 for k, v in pos.items()}

    # รูปทรงห้องจากการวัดในภาพ (tools/geometry.py): ผนังห้องโถง, ระเบียง, ความสูงเพดาน
    corridor_ids = [n for n in keep if ALL.index(n) >= ALL.index("195")]
    m_scale, hall, corr, shift = geometry.solve(mp, corridor_ids)
    for n in corridor_ids:
        mp[n] = mp[n] + np.array([0.0, shift])
    # ระเบียงยาวเสมอห้องโถง (ข้อมูลจากผู้ดูแล + ภาพ): ประตู 195 อยู่ตรงประตู 194 ปลายฝั่งแท่นพระประธาน
    # ผู้ถ่ายออกประตูแล้วไปเริ่มที่ปลายระเบียงฝั่งตะวันตก (201) เดินกลับมาทางตะวันออก
    # จนถึงประตูที่มีป้าย "หอพุทธศิลป์" (212/220) ซึ่งอยู่ถัดจากประตู 194 ไปทางตะวันตก
    # ทิศการเดินและด้านของห้อง (ห้องอยู่ขวามือเมื่อเดินไปตะวันออก) เป็นไปตามภาพ จึงไม่ต้องสะท้อนภาพ
    # ส่วนระยะระหว่างจุด (เทียบภาพข้ามระเบียงกับห้องไม่ได้) ยืดให้เต็มความยาวห้อง
    line = [n for n in corridor_ids if n != DOOR[1]]
    xs = {n: mp[n][0] for n in line}
    lo_x, hi_x = min(xs.values()), max(xs.values())
    door_x = mp[DOOR[0]][0]
    x_west, x_east = hall["left"] + 2.0, door_x - 6.0
    for n in line:
        mp[n] = np.array([x_west + (xs[n] - lo_x) / (hi_x - lo_x) * (x_east - x_west), mp[n][1]])
    mp[DOOR[1]] = np.array([door_x, mp[DOOR[1]][1]])
    corr["left"], corr["right"] = hall["left"], hall["right"]
    rooms = []
    for (label, _, _), r in zip(ROOMS, (hall, corr)):
        rooms.append({"label": label, "x": round(r["left"], 2), "y": round(r["top"], 2),
                      "w": round(r["right"] - r["left"], 2), "h": round(r["bottom"] - r["top"], 2)})

    # ภาพ
    os.makedirs(OUT_IMG, exist_ok=True)
    order = keep
    for old in os.listdir(OUT_IMG):          # ลบภาพที่ไม่ได้ใช้แล้ว
        if old.startswith("p") and old.endswith(".jpg") and old[1:-4] not in keep:
            os.remove(os.path.join(OUT_IMG, old))
    for n in order:
        out = os.path.join(OUT_IMG, "p%s.jpg" % n)
        if not os.path.exists(out):
            im = cv2.imread(src(n, ""))
            im = cv2.resize(im, (OUT_W, OUT_W // 2), interpolation=cv2.INTER_AREA)
            cv2.imwrite(out, im, [cv2.IMWRITE_JPEG_QUALITY, 82, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
            print("   ภาพ", out, file=sys.stderr)

    links = {n: [] for n in order}
    walks = [e for e in walks if DOOR[1] not in e or set(e) == set(DOOR)]
    near = sorted(line, key=lambda n: abs(mp[n][0] - door_x))[:2]
    walks += [tuple(sorted((DOOR[1], n))) for n in near]
    for a, b in pick_links(mp, walks):
        links[a].append({"to": "p" + b})     # ลิงก์กลับสร้างอัตโนมัติในหน้าเว็บ
    for a, b in EXTRA_LINKS:
        if a in links and b in links and {"to": "p" + b} not in links[a] and {"to": "p" + a} not in links[b]:
            links[a].append({"to": "p" + b})
    infos = load_artworks(keep)

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
            "map": {"x": round(float(mp[n][0]), 2), "y": round(float(mp[n][1]), 2)},
            "northOffset": round(north[n], 1),
            "links": links[n],
            "infos": infos.get(n, []),
            **(FIRST_VIEW if n == FIRST else {}),
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
        "floorPlan": {"image": None, "rooms": rooms},
        "compass": compass(north),
        "model": {
            # หน่วย 3 มิติ = ความสูงกล้อง; พิกัด x,y ของแผนผัง × scale = ตำแหน่งบนพื้น
            "scale": round(m_scale, 5),
            "height": round(geometry.room_height(), 3),
            "railHeight": geometry.RAIL_HEIGHT,
            "rooms": [dict(r, kind=k) for r, k in zip(rooms, ("hall", "corridor"))],
            "atlas": build_atlas(order),
        },
        "scenes": scenes,
        "artworks": [{
            "id": a["id"], "card_no": a["card_no"], "title": a["title"], "title_en": a.get("title_en", ""),
            "card": "images/artworks/%s.jpg" % a["id"],
            "placements": [{"pano": p["pano"], "yaw": p["yaw"], "pitch": p["pitch"]}
                           | ({"approx": True} if p.get("approx") else {})
                           for p in a.get("placements", []) if p["pano"] in keep],
        } for a in artworks()],
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
