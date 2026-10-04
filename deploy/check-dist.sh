#!/usr/bin/env bash
# ตรวจว่า deploy/dist/ ตรงกับไฟล์ต้นฉบับ (index.html, css, js, data, ภาพ, vendor)
# ถ้าไม่ตรง แปลว่าแก้เว็บแล้วลืมรัน `bash deploy/build.sh` — เซิร์ฟเวอร์จะได้เวอร์ชันเก่า
# ใช้งาน:  bash deploy/check-dist.sh   (GitHub Actions รันให้อัตโนมัติทุก PR และทุก push เข้า main)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/deploy/dist"
fail=0

# เทียบไฟล์/โฟลเดอร์: <ต้นฉบับ> <ใน dist>
check() {
  local out
  if ! out="$(diff -rq "$ROOT/$1" "$DIST/$2" 2>&1)"; then
    echo "✗ deploy/dist/$2 ไม่ตรงกับ $1"
    echo "$out" | sed "s#$ROOT/##g" | head -20 | sed 's/^/    /'
    fail=1
  fi
}

for d in css js data images/panoramas images/artworks images/logo images/model images/about \
         vendor/pannellum vendor/three; do
  check "$d" "$d"
done
check .nojekyll .nojekyll
check deploy/apache/.htaccess .htaccess
if [ -f "$ROOT/images/floorplan.png" ]; then check images/floorplan.png images/floorplan.png; fi

# index.html ใน dist มีเลขเวอร์ชัน ?v=... ท้ายไฟล์ css/js/data — ตัดออกก่อนเทียบ
if ! diff -q <(sed -E 's#\?v=[0-9A-Za-z]+"#"#g' "$DIST/index.html") "$ROOT/index.html" >/dev/null; then
  echo "✗ index.html ไม่ตรงกับ deploy/dist/index.html"
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "deploy/dist/ ยังเป็นเวอร์ชันเก่า — รัน  bash deploy/build.sh  แล้ว commit deploy/dist/ ด้วย"
  exit 1
fi
echo "✓ deploy/dist/ ตรงกับไฟล์ต้นฉบับ"
