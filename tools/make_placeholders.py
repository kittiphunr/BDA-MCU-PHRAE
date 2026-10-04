#!/usr/bin/env python3
"""สร้างภาพ 360° ตัวอย่าง (placeholder) สำหรับทดสอบทัวร์ก่อนมีภาพจริง

ใช้งาน:  pip install pillow && python3 tools/make_placeholders.py
ต้องมี Node.js เพื่ออ่าน data/tour.js
ภาพที่มีอยู่แล้วจะไม่ถูกเขียนทับ (ใช้ --force เพื่อเขียนทับ)
"""
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 4096, 2048
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_tour():
    js = "global.window={};require(process.argv[1]);console.log(JSON.stringify(window.TOUR))"
    out = subprocess.check_output(["node", "-e", js, os.path.join(ROOT, "data", "tour.js")])
    return json.loads(out)


def bearing(a, b):
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    return math.degrees(math.atan2(dx, -dy))


def yaw_to_x(yaw):
    return ((yaw + 180) % 360) / 360 * W


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def draw_scene(scene, scenes_by_id, neighbours, path):
    img = Image.new("RGB", (W, H))
    horizon = H // 2
    # ไล่สีเพดาน / ผนัง / พื้น
    d = ImageDraw.Draw(img)
    for y in range(H):
        if y < H * 0.3:
            t = y / (H * 0.3)
            c = (int(70 + 60 * t), int(30 + 30 * t), int(25 + 15 * t))
        elif y < horizon + 120:
            c = (176, 132, 72)
        else:
            t = (y - horizon) / (H - horizon)
            c = (int(110 - 60 * t), int(60 - 30 * t), int(35 - 20 * t))
        d.line([(0, y), (W, y)], fill=c)

    # เส้นแบ่งทุก 30°
    for deg in range(-180, 180, 30):
        x = yaw_to_x(deg)
        d.line([(x, H * 0.3), (x, horizon + 120)], fill=(140, 100, 50), width=4)

    # ทิศตามแผนผัง
    north = scene.get("northOffset", 0)
    for b, label in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        x = yaw_to_x(north + b)
        d.text((x, H * 0.3 + 40), label, font=font(90), fill=(250, 230, 170), anchor="mm")

    # ประตูไปยังจุดข้างเคียง
    for nid in neighbours:
        other = scenes_by_id[nid]
        yaw = north + bearing(scene["map"], other["map"])
        x = yaw_to_x(yaw)
        d.rectangle([x - 170, horizon - 360, x + 170, horizon + 120], fill=(45, 25, 15), outline=(212, 175, 55), width=10)
        d.text((x, horizon - 200), "TO", font=font(48), fill=(212, 175, 55), anchor="mm")
        d.text((x, horizon - 130), nid.upper(), font=font(52), fill=(255, 240, 200), anchor="mm")

    # ชื่อจุด
    d.text((W / 2, H * 0.17), scene["id"].upper(), font=font(150), fill=(255, 236, 190), anchor="mm")
    d.text((W / 2, H * 0.17 + 120), "PLACEHOLDER 360 - replace with real photo", font=font(56), fill=(230, 200, 150), anchor="mm")
    d.text((W / 2, H * 0.92), "BUDDHIST ART HALL", font=font(80), fill=(160, 120, 70), anchor="mm")

    img.save(path, quality=72, optimize=True, progressive=True)


def main():
    force = "--force" in sys.argv
    tour = load_tour()
    by_id = {s["id"]: s for s in tour["scenes"]}
    neighbours = {s["id"]: [] for s in tour["scenes"]}
    for s in tour["scenes"]:
        for link in s.get("links", []):
            neighbours[s["id"]].append(link["to"])
            if not link.get("oneWay"):
                neighbours[link["to"]].append(s["id"])
    for s in tour["scenes"]:
        path = os.path.join(ROOT, s["image"])
        if os.path.exists(path) and not force:
            print("ข้าม (มีอยู่แล้ว):", s["image"])
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        draw_scene(s, by_id, sorted(set(neighbours[s["id"]])), path)
        print("สร้าง:", s["image"])


if __name__ == "__main__":
    main()
