# Contabo VPS'ga deploy

Bu yo'riqnoma `docker-compose.yml` bilan birga ishlaydi: TLS compose'dan **tashqarida**,
serverdagi nginx tomonidan tugatiladi, barcha konteyner portlari esa `127.0.0.1` ga
bog'langan.

```
Internet ──TLS──> nginx (host) ──HTTP──> 127.0.0.1:8000  quiz_back    (API + WebSocket + /media)
                               └─HTTP──> 127.0.0.1:8080  quiz_webapp  (Mini App statik)
```

Misol domenlar (o'zingiznikiga almashtiring):

| Domen | Nima |
|---|---|
| `api.myedunova.uz` | API, WebSocket, `/media` |
| `app.myedunova.uz` | Telegram Mini App |

---

## 0. Oldindan kerak bo'ladi

- Contabo VPS, Ubuntu 22.04 yoki 24.04, **kamida 8 GB RAM**
- Ikkita domen (yoki subdomen) DNS'i serverning IP'siga qaragan
- Telegram bot tokeni, Gemini va Mistral API kalitlari

**DNS.** Deploydan oldin ikkala `A` yozuvni ham qo'ying va tarqalishini kuting —
Let's Encrypt sertifikat olishda DNS allaqachon ishlayotgan bo'lishi shart:

```
api.myedunova.uz.   A   <SERVER_IP>
app.myedunova.uz.   A   <SERVER_IP>
```

Tekshirish: `dig +short api.myedunova.uz` serverning IP'sini qaytarishi kerak.

---

## 1. Server tayyorlash

`root` bilan kiring, so'ng ishchi foydalanuvchi yarating — konteynerlarni `root`
ostida ishlatmang.

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy/
```

Endi `deploy` bilan qayta kiring va tizimni yangilang:

```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone Asia/Tashkent
```

### Firewall

Faqat SSH va HTTP(S) ochiq bo'lsin. Postgres, Redis va Mongo portlari compose'da
`127.0.0.1` ga bog'langan, shuning uchun tashqaridan ko'rinmaydi.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

### Swap

Contabo'ning ba'zi tariflarida swap yo'q. AI/PDF ishlari xotira tepasini urganda
bu OOM'ga olib keladi:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
newgrp docker
docker compose version    # v2 bo'lishi kerak
```

---

## 2. Kod va media katalogi

```bash
sudo mkdir -p /home/quiz_app/media
sudo chown -R 1000:1000 /home/quiz_app/media    # image ichidagi appuser uid=1000

sudo mkdir -p /srv && sudo chown deploy:deploy /srv
cd /srv
git clone <repo-url> quiz_app
cd quiz_app
```

> `/home/quiz_app/media` — `quiz_back`, `quiz_bot` va `quiz_celery` uchun **umumiy**
> katalog. Celery PDF'dan chiqargan rasmlarni shu yerga yozadi, API esa shu yerdan
> `/media` orqali beradi. Egalik `1000:1000` bo'lmasa, konteyner yoza olmaydi.

---

## 3. `.env`

`.env` ni serverda yarating — repoga **hech qachon** qo'ymang.

```bash
cd /srv/quiz_app
nano .env
```

Domenga bog'liq uchta qiymat eng muhimi:

```bash
# --- domenlar ---
BASE_URL=https://api.myedunova.uz
TELEGRAM_WEBAPP_URL=https://app.myedunova.uz/
VITE_API_BASE_URL=https://api.myedunova.uz

# --- Postgres ---
POSTGRES_USER=quiz
POSTGRES_PASSWORD=<kuchli-parol>
POSTGRES_DB=quiz
DATABASE_URL=postgresql+asyncpg://quiz:<kuchli-parol>@quiz-db:5432/quiz

# --- Redis / Celery ---
REDIS_URL=redis://quiz-redis:6379/0
REDIS_DSN=redis://quiz-redis:6379/0
CELERY_BROKER_URL=redis://quiz-redis:6379/1
CELERY_RESULT_BACKEND=redis://quiz-redis:6379/2

# --- Mongo (chat) ---
MONGO_INITDB_ROOT_USERNAME=quiz
MONGO_INITDB_ROOT_PASSWORD=<kuchli-parol>
MONGODB_URL=mongodb://quiz:<kuchli-parol>@quiz-mongo:27017/?authSource=admin
MONGODB_DB_NAME=quiz_chat

# --- JWT ---
SECRET_KEY=<openssl rand -hex 32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# --- tashqi xizmatlar ---
TELEGRAM_BOT_TOKEN=<BotFather tokeni>
GEMINI_API_KEY=...
MISTRAL_API_KEY=...

APP_TIME_ZONE=Asia/Tashkent
DATABASE_TIME_ZONE=UTC
```

```bash
chmod 600 .env
```

Hostnomlar (`quiz-db`, `quiz-redis`, `quiz-mongo`) — compose tarmog'idagi servis
nomlari, `localhost` emas.

**Diqqat:** `VITE_API_BASE_URL` Mini App bundle'iga **build paytida** kiritiladi.
Uni keyin o'zgartirsangiz, `quiz_webapp` ni qayta **build** qilish kerak, restart
yetarli emas.

---

## 4. Image'larni qurish va ishga tushirish

```bash
cd /srv/quiz_app
docker compose build
docker compose up -d
docker compose ps
```

Hammasi `healthy` yoki `running` bo'lishi kerak. Bir necha daqiqa kuting — Postgres
va Mongo birinchi ishga tushishda bazani yaratadi.

### Migratsiyalar

```bash
docker compose exec quiz_back alembic upgrade head
```

Zanjir bo'sh bazadan boshlanadi: `20260901_0000` barcha jadvallarni yaratadi,
qolganlari ustiga qo'shiladi. Alembic baza manzilini `.env` dagi `DATABASE_URL`
dan oladi — `alembic.ini` ga parol yozish shart emas.

### Fanlar va boshlang'ich testlar

```bash
docker compose exec quiz_back python tool/seed_subjects.py
```

8 ta fan va 24 ta test yoziladi. Skript idempotent: qayta yurgizsangiz hech narsa
o'zgarmaydi, mavjud testlarga tegmaydi.

---

## 5. Nginx va SSL

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### WebSocket upgrade xaritasi

Buni alohida faylga qo'ying — u `http {}` blokiga tushadi:

```bash
sudo tee /etc/nginx/conf.d/upgrade.conf >/dev/null <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF
```

### API sayti

```bash
sudo tee /etc/nginx/sites-available/api.myedunova.uz >/dev/null <<'EOF'
server {
    listen 80;
    server_name api.myedunova.uz;

    # PDF yuklash uchun (ilovadagi chegara 5 MB, bu esa zaxira bilan)
    client_max_body_size 20m;

    # Ilovadagi BARCHA WebSocket'lar /ws/ ostida:
    #   /ws/chat  /ws/notifications/{id}  /ws/jobs/{id}/
    #   /ws/quiz/sessions/{id}  /ws/quiz-sessions/{id}[/participant]
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Uzoq yashaydigan ulanish: buferlash o'chirilgan, taymaut uzun.
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # Qolgan hammasi. /api/ dan tashqari /chats, /messages va /media ham bor,
    # shuning uchun yo'llar sanab chiqilmaydi.
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # AI/PDF so'rovlari sekin bo'lishi mumkin.
        proxy_read_timeout 300s;
    }
}
EOF
```

### Mini App sayti

```bash
sudo tee /etc/nginx/sites-available/app.myedunova.uz >/dev/null <<'EOF'
server {
    listen 80;
    server_name app.myedunova.uz;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

### Yoqish va sertifikat olish

```bash
sudo ln -sf /etc/nginx/sites-available/api.myedunova.uz /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/app.myedunova.uz /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d api.myedunova.uz -d app.myedunova.uz --redirect --agree-tos -m siz@example.com
```

Certbot server bloklariga TLS'ni o'zi qo'shadi va HTTP'dan HTTPS'ga yo'naltirishni
sozlaydi. Avtomatik yangilanish `certbot.timer` orqali ishlaydi:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

---

## 6. Tekshirish ro'yxati

```bash
# 1. API
curl -s https://api.myedunova.uz/ | jq .
# {"status": "API running"}

# 2. HTTPS majburiymi
curl -sI http://api.myedunova.uz/ | head -1        # 301

# 3. Mini App
curl -s https://app.myedunova.uz/ | grep -o '/assets/[^"]*\.js' | head -1
curl -sI https://app.myedunova.uz/qandaydir/yolak | head -1   # 200 (SPA fallback)

# 4. Bundle backendni to'g'ri ko'rsatyaptimi
curl -s "https://app.myedunova.uz$(curl -s https://app.myedunova.uz/ \
  | grep -o '/assets/index-[^\"]*\.js' | head -1)" | grep -o 'https://api\.myedunova\.uz' | head -1

# 5. WebSocket. Tokensiz 403 qaytadi va bu TO'G'RI: so'rov ilovagacha yetgan,
#    ilova esa avtorizatsiya yo'qligi uchun rad etgan. 502/504 bo'lsa — nginx
#    xato sozlangan. (-I ishlatmang: HEAD upgrade qilmaydi.)
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  https://api.myedunova.uz/ws/chat

# 5b. Root'dagi yo'llar ham o'tyaptimi (chat /api ostida emas)
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://api.myedunova.uz/chats          # 401
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://api.myedunova.uz/api/v1/subject/list/   # 200

# 6. Media
docker compose exec quiz_back sh -c 'echo ok > media/_probe.txt'
curl -s https://api.myedunova.uz/media/_probe.txt      # ok
docker compose exec quiz_back rm media/_probe.txt

# 7. Celery navbatlari
docker compose logs --tail=30 quiz_celery | grep -E "celery@|\. telegram\."

# 8. Bot
docker compose logs --tail=30 quiz_bot
```

**Telegramda:** botga `/start` yozing → ro'yxatdan o'ting → `➕ Test yaratish` →
`✨ AI orqali` → fan, mavzu, savol soni. Test tayyor bo'lgach
`🔍 Savollarni tekshirish` tugmasi Mini App'ni ochishi kerak. Ochilmasa — 99%
hollarda `TELEGRAM_WEBAPP_URL` HTTPS emas yoki noto'g'ri.

---

## 7. Yangilanish

```bash
cd /srv/quiz_app
git pull
docker compose build
docker compose up -d
docker compose exec quiz_back alembic upgrade head
```

Faqat Mini App o'zgargan bo'lsa:

```bash
docker compose build quiz_webapp && docker compose up -d quiz_webapp
```

Orqaga qaytarish:

```bash
git checkout <oldingi-commit>
docker compose build && docker compose up -d
# Migratsiya qaytarish kerak bo'lsa: alembic downgrade -1
```

---

## 8. Zaxira nusxa

```bash
sudo mkdir -p /srv/backups && sudo chown deploy:deploy /srv/backups
cd /srv/quiz_app

# Postgres
docker compose exec -T quiz-db pg_dump -U quiz quiz | gzip > /srv/backups/pg-$(date +%F).sql.gz

# Mongo (chat)
docker compose exec -T quiz-mongo mongodump --archive --gzip \
  -u quiz -p '<parol>' --authenticationDatabase admin > /srv/backups/mongo-$(date +%F).gz

# Media
tar czf /srv/backups/media-$(date +%F).tar.gz -C /home/quiz_app media
```

Kunlik cron:

```bash
crontab -e
# 0 3 * * * cd /srv/quiz_app && docker compose exec -T quiz-db pg_dump -U quiz quiz | gzip > /srv/backups/pg-$(date +\%F).sql.gz
```

---

## 9. Muhim sozlamalar

### Celery concurrency

`docker-compose.yml` da `--concurrency=24` turibdi. Bu **24 ta alohida Python
jarayoni** demak — 8 GB RAM'li serverda Postgres, Mongo va Redis bilan birga
xotira yetmasligi mumkin.

VPS hajmiga qarab kamaytiring:

| RAM | Tavsiya |
|---|---|
| 8 GB | `--concurrency=6` |
| 16 GB | `--concurrency=12` |
| 32 GB | `24` qolsa bo'ladi |

Ishlar asosan AI javobini kutish bilan o'tadi, shuning uchun kam concurrency
o'tkazuvchanlikni deyarli kamaytirmaydi.

### `--workers 1` ni oshirmang

`quiz_back` bitta gunicorn worker bilan ishlaydi. Bu ataylab: chat, bildirishnoma
va jonli sessiya WebSocket ro'yxatlari **jarayon xotirasida** saqlanadi. Ikkinchi
worker o'z ulanishlarini ushlaydi va boshqa workerdagi foydalanuvchiga xabar
jimgina yetmaydi. Ko'proq worker kerak bo'lsa, avval barcha WebSocket
broadcast'larini Redis orqali o'tkazish kerak.

### Postgres `max_connections`

`200` ga qo'yilgan. Celery concurrency'ni oshirsangiz, ulanishlar soni ham ortadi —
`max_connections` ni ham mos ravishda tekshiring.

---

## 10. Nosozliklar

| Belgi | Sabab | Yechim |
|---|---|---|
| Mini App tugmasi chiqmaydi | `TELEGRAM_WEBAPP_URL` bo'sh yoki HTTPS emas | `.env` ni to'g'rilang, `quiz_bot` va `quiz_celery` ni restart qiling |
| Mini App ochiladi, lekin "So'rov bajarilmadi" | `VITE_API_BASE_URL` noto'g'ri yoki CORS | Bundle ichini 6-bo'limdagi 4-buyruq bilan tekshiring; kerak bo'lsa `quiz_webapp` ni qayta **build** qiling |
| WebSocket 502/504 | nginx'da `/ws/` bloki yo'q yoki `upgrade.conf` qo'yilmagan | 5-bo'limni qayta bajaring, `nginx -t` |
| WebSocket 1 daqiqada uziladi | `proxy_read_timeout` kichik | `/ws/` blokida `3600s` ekanini tekshiring |
| Savol rasmlari ko'rinmaydi | media katalogi mos emas yoki egalik xato | `ls -ld /home/quiz_app/media` → `1000:1000` bo'lsin |
| API ko'tarilmaydi | Mongo tayyor emas | `docker compose logs quiz-mongo`; `MONGODB_URL` da `authSource=admin` bormi |
| Chat ishlamaydi | Mongo ulanmagan | `docker compose exec quiz_back python -c "import motor; print('ok')"` |
| `relation "..." does not exist` | Image eski — boshlang'ich migratsiyasiz | `git pull && docker compose build quiz_back` |
| `Can't load plugin: sqlalchemy.dialects` | `DATABASE_URL` da noto'g'ri drayver | `postgresql+asyncpg://...` shaklida bo'lsin; alembic uni o'zi psycopg2 ga o'giradi |
| Celery ish bajarmaydi | Navbat nomi mos emas | `docker compose logs quiz_celery | grep "\. telegram\."` — vazifalar ro'yxatda bormi |

Loglar:

```bash
docker compose logs -f --tail=100 quiz_back
docker compose logs -f --tail=100 quiz_bot
docker compose logs -f --tail=100 quiz_celery
sudo tail -f /var/log/nginx/error.log
```

---

## 11. Veb frontend (alohida React ilova)

Bu ilova shu repoda emas — lokal kompyuterda build qilinadi, `dist/` server ga
yuklanadi va nginx uni to'g'ridan-to'g'ri beradi. Serverda Node kerak emas.

```
myedunova.uz       ->  /var/www/myedunova.uz   (statik fayllar, Docker'siz)
api.myedunova.uz   ->  127.0.0.1:8000
app.myedunova.uz   ->  127.0.0.1:8080
```

### 11.1 DNS

Apex domen va `www` uchun yozuvlar:

```
myedunova.uz.       A   <SERVER_IP>
www.myedunova.uz.   A   <SERVER_IP>
```

### 11.2 Lokalda build

Frontend API manzilini qayerdan olishini avval tekshiring:

```bash
grep -rn "VITE_API\|REACT_APP_API\|API_BASE\|baseURL" src/ | head
```

So'ng shu o'zgaruvchi bilan build qiling — **manzil build paytida bundle ichiga
kiritiladi**, keyin o'zgartirib bo'lmaydi:

```bash
# Vite bo'lsa
VITE_API_BASE_URL=https://api.myedunova.uz npm run build

# Create React App bo'lsa
REACT_APP_API_BASE_URL=https://api.myedunova.uz npm run build
```

Manzil kodda qattiq yozilgan bo'lsa, avval uni env o'zgaruvchisiga chiqaring —
aks holda har deployda kodni tahrirlashga to'g'ri keladi.

Build natijasini tekshiring:

```bash
grep -ro "https://api\.myedunova\.uz" dist/ | head -1    # topilishi kerak
grep -ro "localhost:8000" dist/ | head -1                  # topilmasligi kerak
```

### 11.3 Serverga yuklash

Katalogni bir marta yarating:

```bash
sudo mkdir -p /var/www/myedunova.uz
sudo chown -R $USER:$USER /var/www/myedunova.uz
```

Lokal kompyuterdan:

```bash
rsync -avz --delete dist/ deploy@<SERVER_IP>:/var/www/myedunova.uz/
```

`--delete` eski fayllarni tozalaydi — hash nomli assetlar to'planib qolmaydi.

### 11.4 Nginx

Nginx'da `add_header` merosi "hammasi yoki hech nima": o'z `add_header` i bor
`location` server blokidagi barcha sarlavhalarni **tushirib qoldiradi**. Shuning
uchun xavfsizlik sarlavhalari alohida snippet'ga chiqarilib, har bir blokka
qo'shiladi.

```bash
sudo mkdir -p /etc/nginx/snippets
sudo tee /etc/nginx/snippets/myedunova-headers.conf >/dev/null <<'EOF'
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
EOF

sudo tee /etc/nginx/sites-available/myedunova.uz >/dev/null <<'EOF'
server {
    listen 80;
    server_name myedunova.uz www.myedunova.uz;

    root /var/www/myedunova.uz;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    # Fayl nomida hash bor - mazmuni hech qachon eskirmaydi.
    location /assets/ {
        include /etc/nginx/snippets/myedunova-headers.conf;
        add_header Cache-Control "public, immutable, max-age=31536000";
        try_files $uri =404;
    }

    # index.html kesh qilinmaydi: u joriy asset nomlarini ko'rsatadi, eski
    # nusxa deployni ko'rinmas qiladi.
    location = /index.html {
        include /etc/nginx/snippets/myedunova-headers.conf;
        add_header Cache-Control "no-store";
        try_files $uri =404;
    }

    # SPA: noma'lum yo'l - bu marshrut, yo'qolgan fayl emas.
    location / {
        include /etc/nginx/snippets/myedunova-headers.conf;
        try_files $uri $uri/ /index.html;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/myedunova.uz /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 11.5 Sertifikat

```bash
sudo certbot --nginx -d myedunova.uz -d www.myedunova.uz --redirect --agree-tos -m siz@example.com
```

### 11.6 Tekshirish

```bash
curl -sI https://myedunova.uz/ | head -1                         # 200
curl -sI https://myedunova.uz/qandaydir/yolak | head -1           # 200 (SPA)
curl -s https://myedunova.uz/ | grep -o '/assets/[^"]*\.js' | head -1

# Bundle to'g'ri backendni ko'rsatyaptimi
curl -s "https://myedunova.uz$(curl -s https://myedunova.uz/ \
  | grep -o '/assets/index-[^"]*\.js' | head -1)" \
  | grep -o 'https://api\.myedunova\.uz' | head -1
```

Brauzerda oching va **konsolni tekshiring**: CORS yoki `mixed content` xatosi
bo'lmasligi kerak. WebSocket ishlatilsa, manzil `wss://api.myedunova.uz/ws/...`
bo'lishi shart — `ws://` HTTPS sahifadan bloklanadi.

### 11.7 Keyingi deploylar

Bir buyruq yetarli:

```bash
VITE_API_BASE_URL=https://api.myedunova.uz npm run build \
  && rsync -avz --delete dist/ deploy@<SERVER_IP>:/var/www/myedunova.uz/
```

Nginx'ni qayta yuklash shart emas — statik fayllar har so'rovda diskdan o'qiladi.

### 11.8 Nosozliklar

| Belgi | Sabab | Yechim |
|---|---|---|
| Sahifa ochiladi, so'rovlar ishlamaydi | Bundle'da eski/lokal API manzili | 11.2 dagi `grep` bilan tekshiring, qayta build qiling |
| Konsolda CORS xatosi | API `Access-Control-Allow-Origin` bermayapti | `curl -sI -H "Origin: https://myedunova.uz" https://api.myedunova.uz/` |
| Ichki yo'lda 404 (masalan `/dashboard`) | `try_files` yo'q | 11.4 dagi `location /` blokini tekshiring |
| `mixed content` | Bundle'da `http://` manzil | HTTPS ga o'tkazing va qayta build qiling |
| Eski versiya ko'rinaveradi | `index.html` keshlangan | `location = /index.html` da `no-store` borligini tekshiring |
| Xavfsizlik sarlavhalari yo'q | `location` o'z `add_header` i bilan meros uzilgan | Har bir blokda `include .../myedunova-headers.conf` borligini tekshiring |
