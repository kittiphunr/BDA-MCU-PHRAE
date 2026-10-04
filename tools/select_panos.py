#!/usr/bin/env python3
"""เลือกภาพ 360° ที่ใช้จริง ตัดภาพที่ซ้ำซ้อน (ถ่ายใกล้กันเกินไป)

หลักการ
  1. ใช้ตำแหน่งบนแผนผังจาก solve_map (คำนวณจากภาพทุกภาพ)
  2. บังคับเก็บ: จุดสำคัญ (ทางเข้า ประตู) + ให้งานศิลปะทุกชิ้นที่มีตำแหน่ง
     ยังเห็นได้จากอย่างน้อยหนึ่งจุด (เลือกจุดที่เห็นงานศิลปะมากที่สุดก่อน)
  3. เติมจุดอื่นทีละจุด ถ้าห่างจากจุดที่เลือกแล้วทุกจุด >= MIN_SPACING
     ภาพที่ถูกตัดจึงอยู่ใกล้ภาพที่เก็บไว้เสมอ (มุมมองแทบเหมือนกัน)

ใช้งาน: python3 tools/select_panos.py [ระยะห่างขั้นต่ำ]   → พิมพ์รายการภาพที่เลือก
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_tour import ALL, load_edges, artworks  # noqa: E402
import solve_map  # noqa: E402

LANDMARKS = ["220", "212", "195", "194"]  # ทางเข้า, หัวมุมระเบียง, ประตูด้านนอก, ประตูด้านใน
EXCLUDE = {"181", "113"}               # มุมมองที่ไม่ช่วยการเดินชม: หลังองค์พระ, ยืนที่ประตูข้างมองออกนอก
SPACING = 0.85                         # ระยะห่างขั้นต่ำ (หน่วยเดียวกับ solve_map: ระยะก้าวเฉลี่ย = 1)


def select(pos, min_spacing=SPACING):
    arts = [a for a in artworks() if a.get("placements")]
    views = {}
    for a in arts:
        for p in a["placements"]:
            views.setdefault(p["pano"], set()).add(a["id"])
    keep = list(LANDMARKS)
    # set cover: งานศิลปะทุกชิ้นต้องเห็นได้จากจุดที่เก็บไว้
    todo = {a["id"] for a in arts} - set().union(*(views.get(k, set()) for k in keep))
    while todo:
        best = max(views, key=lambda n: (len(views[n] & todo), -ALL.index(n)))
        keep.append(best)
        todo -= views[best]

    def far(n):
        return all(np.linalg.norm(pos[n] - pos[k]) >= min_spacing for k in keep)
    # เติมจุดที่เห็นงานศิลปะมากก่อน แล้วตามลำดับการถ่าย
    for n in sorted(ALL, key=lambda n: (-len(views.get(n, ())), ALL.index(n))):
        if n not in keep and n not in EXCLUDE and far(n):
            keep.append(n)
    return [n for n in ALL if n in keep]


def main():
    spacing = float(sys.argv[1]) if len(sys.argv) > 1 else SPACING
    north, pos, used = solve_map.solve(ALL, load_edges(), ALL[0])
    pos = {k: np.asarray(v) for k, v in pos.items()}
    keep = select(pos, spacing)
    dropped = [n for n in ALL if n not in keep]
    print(json.dumps({"spacing": spacing, "keep": keep, "dropped": dropped}))
    print(len(keep), "จาก", len(ALL), file=sys.stderr)


if __name__ == "__main__":
    main()
