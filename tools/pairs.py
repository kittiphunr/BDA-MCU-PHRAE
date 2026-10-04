#!/usr/bin/env python3
"""เปรียบเทียบภาพ 360° ทีละคู่ (ทุกคู่ที่น่าจะอยู่ใกล้กัน) แล้วเก็บผลไว้ใน tools/links-cache.json

ใช้งาน:
  python3 tools/pairs.py window 4          # คู่ที่ห่างกันไม่เกิน 4 ภาพตามลำดับการถ่าย
  python3 tools/pairs.py list a>b c>d ...   # คู่ที่ระบุ
ผลแต่ละคู่: yaw (ทิศไปภาพปลายทาง), rot, inliers, cheirality  — ดู estimate_links.py
"""
import json
import os
import sys
from multiprocessing import Pool

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estimate_links as est  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "tools", "links-cache.json")
FEAT_DIR = os.path.join(ROOT, "tools", ".cache", "features")
WIDTH = 2560


def src(n):
    return os.path.join(ROOT, "Asset", "20210903_044411_%s-scaled.jpg" % n)


def features(n):
    path = os.path.join(FEAT_DIR, n + ".npz")
    if not os.path.exists(path):
        est.WIDTH = WIDTH
        im = est.load(src(n))
        kp, des = est.features(im)
        np.savez_compressed(path, pts=np.float32([k.pt for k in kp]), des=des,
                            wh=np.array([im.shape[1], im.shape[0]]))
    d = np.load(path)
    kps = [cv2.KeyPoint(float(x), float(y), 1) for x, y in d["pts"]]
    return (kps, d["des"]), tuple(int(v) for v in d["wh"])


def warm(n):
    features(n)


def run(pair):
    a, b = pair
    fa, wh = features(a)
    fb, _ = features(b)
    r = est.estimate(fa, fb, wh) or {"inliers": 0}
    return a + ">" + b, {k: float(v) for k, v in r.items()}


def main():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from build_tour import ALL  # ลำดับภาพทั้งหมด
    os.makedirs(FEAT_DIR, exist_ok=True)
    if sys.argv[1] == "window":
        w = int(sys.argv[2])
        pairs = [(ALL[i], ALL[j]) for i in range(len(ALL)) for j in range(i + 1, min(len(ALL), i + w + 1))]
    else:
        pairs = [tuple(p.split(">")) for p in sys.argv[2:]]
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [p for p in pairs if p[0] + ">" + p[1] not in cache]
    print("คู่ทั้งหมด", len(pairs), "ต้องคำนวณ", len(todo), file=sys.stderr)
    with Pool(4) as pool:
        pool.map(warm, sorted({x for p in todo for x in p}))
        for i, (key, r) in enumerate(pool.imap_unordered(run, todo)):
            cache[key] = r
            if i % 20 == 0:
                print(" ", i, key, r.get("inliers"), file=sys.stderr)
                json.dump(cache, open(CACHE, "w"), indent=1, sort_keys=True)
    json.dump(cache, open(CACHE, "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
