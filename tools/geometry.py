#!/usr/bin/env python3
"""รูปทรงห้องสำหรับโมเดล 3 มิติ จากการวัดในภาพ 360°

หน่วยความยาวของโมเดล = ความสูงกล้อง (h) — ไม่ต้องรู้ความสูงจริง
ถ้ามองตั้งฉากไปที่ผนังแล้วเห็นเส้นผนังจรดพื้นที่มุมก้ม p องศา
ระยะถึงผนัง = h / tan(-p)  เมื่อวัดหลายจุดก็แก้หาตำแหน่งผนังทั้ง 4 ด้าน
และมาตราส่วน (หน่วยแผนผัง → h) ได้พร้อมกันด้วย least squares

ค่ามุมอ่านจากภาพมุมมองตั้งฉากกับผนังที่มีขีดบอกองศา (ดู README)
"""
import math

import numpy as np

# (ภาพ, ผนังของห้องโถง, มุมก้มของเส้นผนังจรดพื้น)  — top = ฝั่งระเบียง
HALL_WALLS = [
    ("143", "top", -42), ("096", "top", -36), ("194", "top", -40), ("136", "top", -30),
    ("151", "bottom", -17), ("089", "bottom", -37), ("128", "bottom", -35),
    ("183", "right", -27), ("194", "right", -22), ("177", "right", -19),
    ("060", "left", -16),
]
# ความสูงเพดาน: (มุมเงยเส้นผนังจรดเพดาน, มุมก้มเส้นผนังจรดพื้น) ที่ผนังเดียวกัน
CEILING = [(45, -42), (22, -19)]          # จุด 143 (ผนังบน), 177 (ผนังขวา)
# ระเบียง: ระยะ (หน่วย h) จากแนวจุดถ่ายถึงผนังกระจกฝั่งใต้ และราว/ม้านั่งฝั่งเหนือ
CORRIDOR_GLASS = [(-35), (-35)]           # จุด 203, 210
CORRIDOR_RAIL = [(-38), (-45)]            # จุด 203, 210 (ฐานม้านั่งริมราว)
CORRIDOR_LINE = ["201", "203", "206", "210", "212"]
RAIL_HEIGHT = 0.6                         # ราวระเบียงสูงประมาณ 0.6 h


def dist(pitch):
    return 1 / math.tan(math.radians(-pitch))


def solve_hall(mp):
    walls = ["top", "bottom", "left", "right"]
    rows, rhs = [], []
    for n, w, p in HALL_WALLS:
        c = mp[n][0] if w in ("left", "right") else mp[n][1]
        sign = 1 if w in ("bottom", "right") else -1     # d = sign·(wall − c)·s
        r = np.zeros(5)
        r[walls.index(w)] = sign
        r[4] = -sign * c
        rows.append(r)
        rhs.append(dist(p))
    sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
    scale = float(sol[4])
    return scale, {w: float(sol[i] / scale) for i, w in enumerate(walls)}


def room_height():
    return float(np.mean([(math.tan(math.radians(up)) + math.tan(math.radians(-dn))) / math.tan(math.radians(-dn))
                          for up, dn in CEILING]))


def solve(mp, corridor_ids):
    """คืน (scale, ห้อง, ระยะเลื่อนระเบียง) — ระเบียงถูกเลื่อนให้ผนังกระจกตรงกับผนังบนของห้องโถง
    (ระยะระหว่างห้องโถงกับระเบียงคำนวณจากคู่ภาพที่ประตูเพียงคู่เดียว จึงคลาดเคลื่อนได้มาก)"""
    scale, hall = solve_hall(mp)
    glass = float(np.mean([dist(p) for p in CORRIDOR_GLASS])) / scale
    rail = float(np.mean([dist(p) for p in CORRIDOR_RAIL])) / scale
    line = [n for n in CORRIDOR_LINE if n in mp]
    yc = float(np.mean([mp[n][1] for n in line]))
    shift = hall["top"] - (yc + glass)
    yc += shift
    xs = [mp[n][0] for n in corridor_ids]
    ys = [mp[n][1] + shift for n in corridor_ids]
    corridor = {"left": min(xs) - 1.0 / scale, "right": max(xs) + 1.0 / scale,
                "top": min(yc - rail, min(ys) - 0.8 / scale), "bottom": hall["top"]}
    return scale, hall, corridor, shift
