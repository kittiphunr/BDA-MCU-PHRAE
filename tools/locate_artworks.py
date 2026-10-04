#!/usr/bin/env python3
"""หาว่างานศิลปะในป้ายข้อมูล (Asset/bda-mcupr-N.png) อยู่ตรงไหนในภาพ 360°

1. ตัดภาพ 360° ต้นฉบับเป็นมุมมองปกติ (perspective) หลายมุม ความละเอียดเต็ม
2. ตัดเฉพาะภาพถ่ายวัตถุด้านซ้ายของป้าย (ไม่เอาตราสัญลักษณ์มุมล่าง)
3. จับคู่จุดเด่น SIFT + homography RANSAC กับทุกมุมมอง
4. แปลงกึ่งกลางวัตถุกลับเป็น yaw/pitch ในภาพ 360°
ผลลัพธ์: tools/artwork-matches.json  (ทุกภาพที่พบ เรียงตามจำนวนจุดที่ตรงกัน)

ใช้งาน: python3 tools/locate_artworks.py
"""
import glob
import json
import math
import os
import re
import sys
from multiprocessing import Pool

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_tour import ALL  # noqa: E402

VIEW_DIR = os.path.join(ROOT, "tools", ".cache", "views")
OUT = os.path.join(ROOT, "tools", "artwork-matches.json")
FOV, SIZE = 60, 1024
YAWS = list(range(-180, 180, 30))
PITCHES = [-22, 8]


def rotation(yaw, pitch):
    p, y = math.radians(pitch), math.radians(yaw)
    Rx = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]])
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    return Ry @ Rx


def focal():
    return (SIZE / 2) / math.tan(math.radians(FOV / 2))


def render(pano, yaw, pitch):
    H, W = pano.shape[:2]
    f = focal()
    xs, ys = np.meshgrid(np.arange(SIZE) - SIZE / 2, np.arange(SIZE) - SIZE / 2)
    d = np.stack([xs, -ys, np.full_like(xs, f)], -1).astype(np.float64)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    d = d @ rotation(yaw, pitch).T
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    mx = ((lon / np.pi + 1) / 2 * W).astype(np.float32)
    my = ((0.5 - lat / np.pi) * H).astype(np.float32)
    return cv2.remap(pano, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def view_to_yawpitch(x, y, yaw, pitch):
    v = np.array([x - SIZE / 2, -(y - SIZE / 2), focal()])
    v = rotation(yaw, pitch) @ (v / np.linalg.norm(v))
    return math.degrees(math.atan2(v[0], v[2])), math.degrees(math.asin(np.clip(v[1], -1, 1)))


def view_features(n):
    path = os.path.join(VIEW_DIR, n + ".npz")
    if os.path.exists(path):
        return path
    pano = cv2.imread(os.path.join(ROOT, "Asset", "20210903_044411_%s.jpg" % n), cv2.IMREAD_GRAYSCALE)
    sift = cv2.SIFT_create(nfeatures=3000)
    pts, des, vid = [], [], []
    for i, (y, p) in enumerate((y, p) for p in PITCHES for y in YAWS):
        kp, d = sift.detectAndCompute(render(pano, y, p), None)
        if d is None:
            continue
        pts.append(np.float32([k.pt for k in kp]))
        des.append(d)
        vid.append(np.full(len(kp), i, np.int16))
    np.savez_compressed(path, pts=np.concatenate(pts), des=np.concatenate(des), vid=np.concatenate(vid))
    return path


def card_photo(path):
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    col = (im < 235).mean(0)
    right = next((x for x in range(150, 700) if col[x:x + 15].max() < 0.3), 470)
    photo = im[:, :right].copy()
    mask = np.full(photo.shape, 255, np.uint8)
    cv2.circle(mask, (75, 605), 90, 0, -1)          # ตราสัญลักษณ์มุมล่างซ้าย
    cv2.rectangle(mask, (0, 0), (60, 45), 0, -1)     # เผื่อเลขมุมบน
    return photo, mask


CARDS = {}


def card_features(path):
    n = int(re.findall(r"bda-mcupr-(\d+)\.png", path)[0])
    photo, mask = card_photo(path)
    photo = cv2.resize(photo, None, fx=1.5, fy=1.5)
    mask = cv2.resize(mask, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST)
    kp, des = cv2.SIFT_create(nfeatures=2500).detectAndCompute(photo, mask)
    return n, np.float32([k.pt for k in kp]), des, photo.shape


def match_pano(pano):
    """จับคู่ป้ายทุกใบกับภาพ 360° หนึ่งภาพ — คืนผลดีที่สุดของแต่ละป้าย"""
    done = os.path.join(VIEW_DIR, pano + ".matches.json")
    if os.path.exists(done):
        return {int(k): v for k, v in json.load(open(done)).items()}
    d = np.load(os.path.join(VIEW_DIR, pano + ".npz"))
    views = [(y, p) for p in PITCHES for y in YAWS]
    split = [(i, d["vid"] == i) for i in range(len(views))]
    vdes = {i: d["des"][sel] for i, sel in split}
    vpts = {i: d["pts"][sel] for i, sel in split}
    # FLANN (kd-tree) หนึ่งชุดต่อมุมมอง — เร็วกว่าจับคู่ทีละจุดมาก
    flann = {}
    for i in vdes:
        if len(vdes[i]) >= 10:
            f = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 4}, {"checks": 48})
            f.add([vdes[i]])
            f.train()
            flann[i] = f
    best = {}
    for n, (cpts, des, (h, w)) in CARDS.items():
        if des is None:
            continue
        centre = np.float32([[[w / 2, h / 2]]])
        for i, (vy, vp) in enumerate(views):
            if i not in flann:
                continue
            m = flann[i].knnMatch(des, k=2)
            good = [a for a, b in (x for x in m if len(x) == 2) if a.distance < 0.75 * b.distance]
            if len(good) < 10:
                continue
            src = cpts[[g.queryIdx for g in good]]
            dst = vpts[i][[g.trainIdx for g in good]]
            Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
            if Hm is None or inl.sum() < 10:
                continue
            c = cv2.perspectiveTransform(centre, Hm)[0, 0]
            if not (0 <= c[0] < SIZE and 0 <= c[1] < SIZE):
                continue
            corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), Hm)
            area = cv2.contourArea(corners)
            if area < 200 or not cv2.isContourConvex(corners.astype(np.int32)):
                continue
            yaw, pitch = view_to_yawpitch(c[0], c[1], vy, vp)
            r = {"pano": pano, "yaw": round(yaw, 1), "pitch": round(pitch, 1),
                 "inliers": int(inl.sum()), "area": round(float(area))}
            if n not in best or r["inliers"] > best[n]["inliers"]:
                best[n] = r
    print(pano, sorted((n, r["inliers"]) for n, r in best.items()), file=sys.stderr, flush=True)
    json.dump(best, open(done, "w"))
    return best


def main():
    os.makedirs(VIEW_DIR, exist_ok=True)
    cards = [p for p in glob.glob(os.path.join(ROOT, "Asset", "bda-mcupr-*.png"))
             if re.search(r"bda-mcupr-\d+\.png$", p)]
    for c in cards:
        n, pts, des, shape = card_features(c)
        CARDS[n] = (pts, des, shape)
    with Pool(4) as pool:
        pool.map(view_features, ALL)
        print("views ready", file=sys.stderr, flush=True)
        per_pano = pool.map(match_pano, ALL)
    out = {}
    for best in per_pano:
        for n, r in best.items():
            out.setdefault(n, []).append(r)
    json.dump({str(n): sorted(out.get(n, []), key=lambda r: -r["inliers"]) for n in sorted(CARDS)},
              open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
