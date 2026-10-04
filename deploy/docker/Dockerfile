# หอพุทธศิลป์ · ทัวร์ 360° — รันด้วย Docker (nginx)
# ต้องรัน deploy/build.sh ก่อน แล้ว build จากโฟลเดอร์ deploy/:
#   docker compose -f deploy/docker/docker-compose.yml up -d --build
FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/ /usr/share/nginx/html/
EXPOSE 80
