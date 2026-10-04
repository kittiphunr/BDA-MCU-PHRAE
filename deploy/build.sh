#!/usr/bin/env bash
# รวมไฟล์ที่เว็บต้องใช้ลง deploy/dist/ และทำไฟล์ zip สำหรับอัปโหลดขึ้นเซิร์ฟเวอร์
# ใช้งาน (จากที่ใดก็ได้):  bash deploy/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/deploy/dist"
VERSION="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)"

rm -rf "$DIST"
mkdir -p "$DIST/images" "$DIST/vendor"

cp "$ROOT/index.html" "$ROOT/.nojekyll" "$DIST/"
cp -r "$ROOT/css" "$ROOT/js" "$ROOT/data" "$DIST/"
cp -r "$ROOT/images/panoramas" "$ROOT/images/artworks" "$ROOT/images/logo" "$DIST/images/"
cp -r "$ROOT/vendor/pannellum" "$DIST/vendor/"
[ -f "$ROOT/images/floorplan.png" ] && cp "$ROOT/images/floorplan.png" "$DIST/images/"

# ใส่เลขเวอร์ชันท้ายไฟล์ css/js เพื่อให้เบราว์เซอร์โหลดไฟล์ใหม่ทุกครั้งที่ deploy
sed -i.bak -E "s#(href|src)=\"(css/[^\"?]+|js/[^\"?]+|data/[^\"?]+)\"#\1=\"\2?v=$VERSION\"#g" "$DIST/index.html"
rm -f "$DIST/index.html.bak"

# .htaccess สำหรับเซิร์ฟเวอร์ Apache / โฮสติ้ง cPanel
cp "$ROOT/deploy/apache/.htaccess" "$DIST/.htaccess"

# ไฟล์ zip สำหรับอัปโหลดผ่าน cPanel / FTP
ZIP="$ROOT/deploy/bda-360-tour-$VERSION.zip"
rm -f "$ROOT"/deploy/bda-360-tour-*.zip
if command -v zip >/dev/null; then
  (cd "$DIST" && zip -qr "$ZIP" .)
  echo "zip: $ZIP"
fi

echo "เวอร์ชัน: $VERSION"
echo "ไฟล์พร้อม deploy: $DIST ($(du -sh "$DIST" | cut -f1), $(find "$DIST" -type f | wc -l) ไฟล์)"
