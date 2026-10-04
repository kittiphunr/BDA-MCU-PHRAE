#!/usr/bin/env bash
# อัปโหลด deploy/dist/ ขึ้นเซิร์ฟเวอร์ผ่าน SSH (rsync)
# ใช้งาน:  bash deploy/upload.sh user@server.example.ac.th /var/www/bda-360
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "ใช้งาน: bash deploy/upload.sh <user@host> <โฟลเดอร์ปลายทางบนเซิร์ฟเวอร์>"
  exit 1
fi
TARGET="$1"
REMOTE_DIR="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

bash "$ROOT/deploy/build.sh"
# --delete ลบไฟล์เก่าที่ไม่มีแล้วบนเซิร์ฟเวอร์ ให้ตรงกับ dist/
rsync -avz --delete "$ROOT/deploy/dist/" "$TARGET:$REMOTE_DIR/"
echo "อัปโหลดเสร็จ: $TARGET:$REMOTE_DIR"
