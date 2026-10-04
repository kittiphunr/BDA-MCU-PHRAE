#!/usr/bin/env python3
"""ประมาณทิศเดินระหว่างภาพ 360° ที่ถ่ายต่อเนื่องกัน (ใช้ช่วยผูกลูกศรแบบ Street View)

จับคู่จุดเด่น (SIFT) ระหว่างภาพคู่ติดกัน แปลงเป็นเวกเตอร์ทิศบนทรงกลม
แล้วหา Essential matrix ด้วย RANSAC เพื่อแยกเป็น
  - การหมุนของกล้อง (กล้องหันต่างกันกี่องศา)
  - ทิศการเคลื่อนที่ (ภาพถัดไปอยู่ทาง yaw เท่าไรในภาพนี้)

ใช้งาน:
  pip install numpy opencv-python-headless
  python3 tools/estimate_links.py ภาพ1.jpg ภาพ2.jpg ... > links.json
"""
import json
import math
import sys

import cv2
import numpy as np

WIDTH = 2048
rng = np.random.default_rng(0)


def load(path):
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return cv2.resize(im, (WIDTH, WIDTH // 2), interpolation=cv2.INTER_AREA)


def bearings(pts, w, h):
    yaw = np.radians(pts[:, 0] / w * 360 - 180)
    pitch = np.radians(90 - pts[:, 1] / h * 180)
    return np.stack([np.cos(pitch) * np.sin(yaw), np.sin(pitch), np.cos(pitch) * np.cos(yaw)], 1)


def features(img):
    sift = cv2.SIFT_create(nfeatures=6000)
    mask = np.zeros_like(img)
    h = img.shape[0]
    mask[int(h * 0.15):int(h * 0.85)] = 255   # ตัดขั้วบน/ล่างที่บิดเบี้ยวมาก
    return sift.detectAndCompute(img, mask)


def match(fa, fb):
    ka, da = fa
    kb, db = fb
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    good = [p[0] for p in m if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    pa = np.float32([ka[g.queryIdx].pt for g in good])
    pb = np.float32([kb[g.trainIdx].pt for g in good])
    return pa, pb


def eight_point(v1, v2):
    A = np.stack([np.outer(b, a).ravel() for a, b in zip(v1, v2)])
    _, _, vt = np.linalg.svd(A)
    E = vt[-1].reshape(3, 3)
    u, _, vt = np.linalg.svd(E)
    return u @ np.diag([1, 1, 0]) @ vt


def residual(E, v1, v2):
    l = v1 @ E.T                                   # E v1
    return np.abs(np.sum(v2 * l, 1)) / (np.linalg.norm(l, axis=1) + 1e-12)


def ransac(v1, v2, iters=3000, thr=0.004):
    best, best_in = None, None
    n = len(v1)
    for _ in range(iters):
        idx = rng.choice(n, 8, replace=False)
        E = eight_point(v1[idx], v2[idx])
        inl = residual(E, v1, v2) < thr
        if best_in is None or inl.sum() > best_in.sum():
            best, best_in = E, inl
    E = eight_point(v1[best_in], v2[best_in])
    inl = residual(E, v1, v2) < thr
    return E, inl


def decompose(E, v1, v2):
    u, _, vt = np.linalg.svd(E)
    if np.linalg.det(u) < 0: u = -u
    if np.linalg.det(vt) < 0: vt = -vt
    Wm = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    best = None
    for R in (u @ Wm @ vt, u @ Wm.T @ vt):
        for t in (u[:, 2], -u[:, 2]):
            # X2 = R X1 + t ;  λ2 v2 = λ1 R v1 + t  → แก้หา λ1, λ2
            Rv1 = v1 @ R.T
            good = 0
            for a, b in zip(Rv1, v2):
                M = np.stack([a, -b], 1)
                lam, *_ = np.linalg.lstsq(M, -t, rcond=None)
                good += lam[0] > 0 and lam[1] > 0
            if best is None or good > best[0]:
                best = (good, R, t)
    return best


def yaw_of(v):
    return math.degrees(math.atan2(v[0], v[2]))


def estimate(fa, fb, wh):
    pa, pb = match(fa, fb)
    if len(pa) < 30:
        return None
    v1, v2 = bearings(pa, *wh), bearings(pb, *wh)
    E, inl = ransac(v1, v2)
    good, R, t = decompose(E, v1[inl], v2[inl])
    c2 = -R.T @ t                                 # ตำแหน่งกล้อง 2 ในพิกัดกล้อง 1
    fwd2 = R.T @ np.array([0, 0, 1.0])            # yaw 0 ของภาพ 2 ในพิกัดกล้อง 1
    return {
        "yaw": round(yaw_of(c2), 1),              # ทิศไปภาพถัดไป (yaw ในภาพนี้)
        "dz": round(float(c2[1]), 2),             # องค์ประกอบแนวดิ่ง (ควรใกล้ 0)
        "rot": round(yaw_of(fwd2), 1),            # yaw ในภาพนี้ ที่ตรงกับ yaw 0 ของภาพถัดไป
        "matches": int(len(pa)),
        "inliers": int(inl.sum()),
        "cheirality": round(good / max(1, inl.sum()), 2),
    }


def main(paths):
    imgs = [load(p) for p in paths]
    wh = (imgs[0].shape[1], imgs[0].shape[0])
    feats = [features(i) for i in imgs]
    out = []
    for i in range(len(paths) - 1):
        r = estimate(feats[i], feats[i + 1], wh) or {}
        r.update({"from": paths[i], "to": paths[i + 1]})
        print(json.dumps(r, ensure_ascii=False), file=sys.stderr)
        out.append(r)
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
