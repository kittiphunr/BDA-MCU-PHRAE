#!/usr/bin/env python3
"""คำนวณแผนผังของทุกจุดพร้อมกันจากผลเปรียบเทียบภาพทุกคู่ (tools/links-cache.json)

1. มุมหันของกล้องแต่ละภาพ (northOffset): rotation averaging จากทุกคู่ที่เชื่อถือได้
2. ตำแหน่ง: translation averaging — ทุกคู่ให้ "ทิศ" จาก A ไป B แก้ระบบสมการเชิงเส้นหา
   ตำแหน่งทั้งหมด + ระยะของแต่ละคู่ (ตัดคู่ที่ขัดแย้งออกอัตโนมัติ)
3. หมุนแผนผังให้ผนังห้อง (ห้องเป็นกล่องสี่เหลี่ยม) ขนานแกน
"""
import math

import numpy as np
from scipy.optimize import lsq_linear


def reliable(r):
    return (r.get("inliers", 0) >= 40 and r.get("cheirality", 0) >= 0.9
            and abs(r.get("dz", 1)) < 0.15)


def wrap(a):
    return (a + 180) % 360 - 180


def unit(b):
    r = math.radians(b)
    return np.array([math.sin(r), -math.cos(r)])


def solve(nodes, edges, root):
    """edges: list of (a, b, yaw, rot, weight)  — yaw: ทิศไป b ในภาพ a, rot: ดู estimate_links
    คืน north{}, pos{}, used_edges"""
    edges = list(edges)
    for _ in range(60):
        # --- rotation averaging -------------------------------------------------
        north = {root: 0.0}
        adj = {n: [] for n in nodes}
        for a, b, y, r, w in edges:
            adj[a].append((b, -r, w))          # n_b = n_a - rot
            adj[b].append((a, r, w))
        frontier = [root]
        while frontier:                         # spanning tree (BFS, น้ำหนักมากก่อน)
            nxt = []
            for a in frontier:
                for b, d, w in sorted(adj[a], key=lambda t: -t[2]):
                    if b not in north:
                        north[b] = north[a] + d
                        nxt.append(b)
            frontier = nxt
        missing = [n for n in nodes if n not in north]
        if missing:
            raise ValueError("จุดที่ไม่เชื่อมกับแผนผัง: %s" % missing)
        for _ in range(100):                    # Gauss-Seidel บนวงกลม
            for n in nodes:
                if n == root:
                    continue
                s = c = 0.0
                for b, d, w in adj[n]:
                    v = math.radians(north[b] - d)
                    s += w * math.sin(v)
                    c += w * math.cos(v)
                north[n] = math.degrees(math.atan2(s, c))
        rot_res = {i: abs(wrap(north[b] - (north[a] - r))) for i, (a, b, y, r, w) in enumerate(edges)}

        # --- translation averaging ----------------------------------------------
        idx = {n: i for i, n in enumerate(nodes)}
        N, M = len(nodes), len(edges)
        rows, rhs = [], []
        for e, (a, b, y, r, w) in enumerate(edges):
            u = unit(y - north[a])
            sw = math.sqrt(w)
            for k in range(2):
                row = np.zeros(2 * N + M)
                row[2 * idx[b] + k] = sw
                row[2 * idx[a] + k] = -sw
                row[2 * N + e] = -sw * u[k]
                rows.append(row)
                rhs.append(0.0)
        for e in range(M):                      # prior อ่อน ๆ: ระยะก้าว ≈ 1 (ช่วงที่มีคู่เดียวจะไม่ยืดผิดปกติ)
            row = np.zeros(2 * N + M)
            row[2 * N + e] = 1.0
            rows.append(row)
            rhs.append(1.0)
        big = 100.0
        for k in range(2):                      # ตรึง root ที่ (0,0)
            row = np.zeros(2 * N + M)
            row[2 * idx[root] + k] = big
            rows.append(row)
            rhs.append(0.0)
        row = np.zeros(2 * N + M)               # ขนาด: ระยะเฉลี่ย = 1
        row[2 * N:] = big / M
        rows.append(row)
        rhs.append(big)
        # ระยะของทุกคู่ต้องเป็นบวก (ไม่เช่นนั้นจุดจะยุบทับกัน)
        lo = np.r_[np.full(2 * N, -np.inf), np.full(M, 0.3)]
        hi = np.r_[np.full(2 * N, np.inf), np.full(M, 8.0)]
        sol = lsq_linear(np.array(rows), np.array(rhs), bounds=(lo, hi)).x
        pos = {n: sol[2 * idx[n]:2 * idx[n] + 2] for n in nodes}
        dist = sol[2 * N:]

        # --- ตัดคู่ที่ขัดแย้ง --------------------------------------------------
        bad = set()
        for e, (a, b, y, r, w) in enumerate(edges):
            v = pos[b] - pos[a]
            ang = math.degrees(math.atan2(v[0], -v[1]))
            if rot_res[e] > 12 or abs(wrap(ang - (y - north[a]))) > 25:
                bad.add(e)
        removable = [e for e in bad if _bridge(edges, e)]
        if not removable:
            break
        # ตัดคู่ที่ผิดมากที่สุดทีละคู่ แล้วคำนวณใหม่
        worst = max(removable, key=lambda e: (rot_res[e] / 12 + abs(wrap(
            math.degrees(math.atan2(*(pos[edges[e][1]] - pos[edges[e][0]]) * [1, -1]))
            - (edges[e][2] - north[edges[e][0]]))) / 25))
        edges.pop(worst)
    return north, pos, edges


def _bridge(edges, i):
    """ตัดคู่ i ได้หรือไม่ (ยังเชื่อมกันครบ)"""
    a0, b0 = edges[i][0], edges[i][1]
    adj = {}
    for j, (a, b, *_) in enumerate(edges):
        if j == i:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen, st = {a0}, [a0]
    while st:
        x = st.pop()
        for y in adj.get(x, ()):
            if y not in seen:
                seen.add(y)
                st.append(y)
    return b0 in seen


def manhattan_angle(north, edges):
    """มุมที่ทำให้ทิศเดินส่วนใหญ่ขนานแกน (ห้องเป็นกล่อง)"""
    s = c = 0.0
    for a, b, y, r, w in edges:
        t = math.radians(4 * (y - north[a]))
        s += w * math.sin(t)
        c += w * math.cos(t)
    return math.degrees(math.atan2(s, c)) / 4
