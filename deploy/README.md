# การ deploy ขึ้นเซิร์ฟเวอร์จริง

เว็บทัวร์ 360° เป็นเว็บ static ล้วน (HTML/CSS/JS + ภาพ) ไม่ต้องมีฐานข้อมูลหรือ PHP
ใช้ได้กับเซิร์ฟเวอร์ทุกแบบ เลือกวิธีที่ตรงกับเซิร์ฟเวอร์ที่มี

```
deploy/
├── build.sh              รวมไฟล์ที่เว็บต้องใช้ลง dist/ + ทำไฟล์ zip
├── upload.sh             build แล้วอัปโหลดขึ้น VPS ผ่าน SSH (rsync)
├── nginx/bda-360.conf    ตั้งค่า Nginx สำหรับ VPS
├── apache/.htaccess      ตั้งค่า Apache / cPanel (ใส่ใน dist/ ให้อัตโนมัติ)
├── docker/               Dockerfile + docker-compose.yml (nginx)
└── dist/                 ← ไฟล์พร้อมขึ้นเซิร์ฟเวอร์ (ผลจาก build.sh, เก็บใน git แล้ว)
```

## ขั้นที่ 1: build

> `deploy/dist/` มีไฟล์พร้อมใช้อยู่ใน repo แล้ว — อัปโหลดโฟลเดอร์นี้ได้ทันทีโดยไม่ต้อง build
> **เมื่อแก้เว็บ (index.html, css, js, data, ภาพ) ต้องรัน build.sh ใหม่แล้ว commit `deploy/dist/` ด้วย**
> ไม่เช่นนั้นไฟล์ใน dist จะเป็นเวอร์ชันเก่า

```bash
bash deploy/build.sh
```

ได้โฟลเดอร์ `deploy/dist/` (~37 MB) และไฟล์ `deploy/bda-360-tour-<เวอร์ชัน>.zip`
มีเฉพาะไฟล์ที่เว็บใช้ **ไม่รวม `Asset/` (ภาพต้นฉบับ ~720 MB)** และใส่เลขเวอร์ชันท้ายไฟล์ css/js
ให้เบราว์เซอร์ของผู้ชมโหลดของใหม่ทุกครั้งที่ deploy

## ขั้นที่ 2: เลือกวิธีขึ้นเซิร์ฟเวอร์

### ก. โฮสติ้งทั่วไป / cPanel / DirectAdmin (Apache)

1. เข้า File Manager → `public_html/` (หรือโฟลเดอร์ย่อย เช่น `public_html/tour/`)
2. อัปโหลดไฟล์ `deploy/bda-360-tour-*.zip` แล้ว **Extract**
   (หรืออัปโหลดเนื้อหาใน `deploy/dist/` ผ่าน FTP — อย่าลืมไฟล์ซ่อน `.htaccess`)
3. เปิด `https://โดเมน/tour/` ได้เลย

### ข. VPS / เซิร์ฟเวอร์ของหน่วยงาน (Nginx)

```bash
# บนเซิร์ฟเวอร์ (ครั้งแรก)
sudo apt install nginx
sudo mkdir -p /var/www/bda-360 && sudo chown $USER /var/www/bda-360

# บนเครื่องตัวเอง: build + อัปโหลด
bash deploy/upload.sh user@server.example.ac.th /var/www/bda-360

# ส่งไฟล์ตั้งค่า nginx ขึ้นไป (แก้ server_name ในไฟล์เป็นโดเมนจริงก่อน)
scp deploy/nginx/bda-360.conf user@server.example.ac.th:~

# บนเซิร์ฟเวอร์: เปิดใช้งาน
sudo cp ~/bda-360.conf /etc/nginx/sites-available/bda-360
sudo ln -s /etc/nginx/sites-available/bda-360 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# HTTPS (แนะนำ — เต็มจอและเซนเซอร์มือถือต้องใช้ https)
sudo certbot --nginx -d tour.example.ac.th
```

ครั้งต่อไปที่แก้เว็บ รันแค่ `bash deploy/upload.sh ...` ซ้ำ

### ค. Docker

```bash
bash deploy/build.sh
docker compose -f deploy/docker/docker-compose.yml up -d --build
# เปิดที่ http://<server>:8080
```

### ง. GitHub Pages (ฟรี ไม่ต้องมีเซิร์ฟเวอร์)

Settings → Pages → Deploy from a branch → `main` / `/ (root)`
(ใช้ repo ตรง ๆ ได้เลย ไม่ต้อง build — แต่ repo มี `Asset/` ขนาดใหญ่ จึงไม่จำเป็นต้องใช้ dist)

## ตรวจหลัง deploy

- เปิดหน้าเว็บ → กด "เริ่มชมนิทรรศการ" → ภาพ 360° ต้องขึ้นและคลิกลูกศรเดินได้
- ถ้าภาพไม่ขึ้น: เปิด DevTools (F12) → Network ดูว่าไฟล์ `images/panoramas/*.jpg` ได้ 404 หรือไม่
  (มักเกิดจากอัปโหลดไม่ครบ หรือชื่อโฟลเดอร์ผิดตัวพิมพ์เล็ก/ใหญ่บนลินุกซ์)
- ฟอนต์ภาษาไทยโหลดจาก Google Fonts — ถ้าเครือข่ายของหน่วยงานบล็อกไว้ เว็บยังใช้งานได้ แต่จะใช้ฟอนต์ของเครื่องแทน

## การตั้งค่าแคชที่ใส่ไว้

| ไฟล์ | แคช | เหตุผล |
|---|---|---|
| `index.html` | ตรวจใหม่ทุกครั้ง | ให้เห็นเวอร์ชันล่าสุดทันที |
| css / js | 1 ปี | มีเลขเวอร์ชัน `?v=` เปลี่ยนทุก build |
| ภาพ 360° | 30 วัน | ไฟล์ใหญ่ ไม่ค่อยเปลี่ยน — ถ้าเปลี่ยนภาพ ให้เปลี่ยนชื่อไฟล์ด้วย |
