# Ke Hoach Chuyen Sau: Hermes_ADS_X tren VPS

## 1. Muc tieu du an

Du an `Hermes_ADS_X` se clone/fork tu repo goc `nousresearch/hermes-agent`, sau do tuy bien de chay tren VPS cua Duxq. He thong muc tieu gom mot Hermes Manager Agent va mot doi agent/worker nho phuc vu workflow Telegram:

- Doc bai viet tu channel Telegram nguon.
- Chuan hoa noi dung bai viet: text, caption, media, link, source.
- Gui noi dung sang Hermes Manager Agent de danh gia.
- Xac dinh bai dat/khong dat theo rule.
- Dang/forward/copy bai dat sang channel dich hoac gui webhook.
- Luu log, trang thai xu ly, ket qua danh gia va chong trung bai.
- Chay 24/24 tren VPS va co CI/CD bang GitHub Actions.

Repo lam viec cua Duxq:

```text
https://github.com/dungdeptraiqua123-tech/Hermes_ADS_X.git
```

Repo upstream:

```text
https://github.com/nousresearch/hermes-agent
```

## 2. Ket luan sau khi doc repo Hermes upstream

### 2.1 Hermes phu hop de lam "manager brain"

Hermes co san:

- CLI chat bang lenh `hermes`.
- Messaging gateway cho Telegram/Discord/Slack/WhatsApp/etc.
- API server OpenAI-compatible tai `/v1/chat/completions`, `/v1/responses`, `/v1/runs`.
- Multi-profile gateways.
- Toolsets, memory, skills, cron, delegation/subagents.
- Systemd service va Docker mode de chay 24/24.

Do do, cach dung tot nhat la:

```text
Hermes Manager Agent = bo nao / evaluator / orchestrator
Telegram workers = doc channel, forward/copy, webhook, log
```

### 2.2 Telegram gateway mac dinh cua Hermes la bot hoi thoai

Hermes Telegram gateway duoc thiet ke de chat voi Hermes qua Telegram:

- DM voi bot.
- Group/forum bot.
- Voice, image, file attachments.
- Slash commands.
- Home channel cho cron.

No khong phai san pham chuyen dung de auto-copy bai tu channel nguon sang channel dich theo rule. Vi vay workflow ADS nen co worker Telegram rieng, dung Hermes API de danh gia.

### 2.3 Channel post co ho tro mot phan

Code upstream da co regression test cho `channel_post` text/command. Channel post khong co `from_user`, nen Hermes dung channel ID lam identity. De authorize channel, can dung:

```env
TELEGRAM_GROUP_ALLOWED_CHATS=-100xxxxxxxxxx
```

Tuy nhien, trong code Telegram media handler hien tai co diem can canh giac: mot so path media van doc `update.message` thay vi `effective_message`, nen can test ky voi channel post co anh/caption/album. Neu bot can doc channel co media, nen lam worker rieng bang Bot API/aiogram hoac patch adapter.

### 2.4 API server la be mat tich hop tot nhat

Hermes co API server:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/runs`
- `GET /health`
- `GET /v1/models`

Bot/worker nen goi Hermes qua API server noi bo:

```text
http://127.0.0.1:8642/v1/responses
```

Khong nen expose cong khai API server neu chua co reverse proxy + HTTPS + auth.

### 2.5 Gemini nen cau hinh trong Hermes, khong nam trong bot

Hermes native Gemini provider dung:

```env
GOOGLE_API_KEY=
# hoac
GEMINI_API_KEY=
```

Config model nen o `~/.hermes/config.yaml`:

```yaml
model:
  provider: gemini
  default: gemini-flash-latest
  base_url: https://generativelanguage.googleapis.com/v1beta
```

Bot/worker khong can biet Gemini key.

## 3. Kien truc de xuat

```text
Telegram source channels
        |
        v
telegram-reader-agent
        |
        v
Postgres / Redis queue
        |
        v
content-evaluator-agent
        |
        |  HTTP internal API
        v
Hermes Manager Agent
        |
        v
JSON decision
        |
        v
telegram-publisher-agent / webhook-agent
        |
        |-- copy/forward/send sang channel dich
        |-- gui webhook den n8n hoac he thong khac
        v
logs + reports + review channel
```

## 4. Vai tro cac agent

### 4.1 Hermes Manager Agent

Trach nhiem:

- La bo nao chinh.
- Nhan payload bai viet.
- Danh gia theo rule.
- Cham diem.
- Giai thich ly do pass/reject.
- Tra JSON co schema on dinh.
- Co the goi subagents noi bo neu workflow phuc tap.

Khong nen de Manager Agent truc tiep forward Telegram, tru khi workflow don gian. Nen tach action co side effect ra worker rieng de de audit.

### 4.2 telegram-reader-agent

Trach nhiem:

- Ket noi Telegram Bot API.
- Lang nghe channel source.
- Lay text, caption, media, link, message id, channel id.
- Xu ly media group/album.
- Luu raw event vao database.
- Day task sang queue/evaluator.

Cong nghe de xuat:

- Python `aiogram`.
- Long polling o MVP.
- Webhook khi co domain HTTPS.

### 4.3 content-evaluator-agent

Trach nhiem:

- Lay task tu queue/database.
- Goi Hermes API server.
- Yeu cau Hermes tra JSON theo schema.
- Validate JSON.
- Luu ket qua.
- Neu JSON loi, retry hoac dua vao manual review.

### 4.4 telegram-publisher-agent

Trach nhiem:

- Nhan decision da pass.
- Copy/forward/send bai sang channel dich.
- Xu ly caption rewrite neu co.
- Luu delivery log.
- Dam bao idempotency, khong dang trung.

### 4.5 webhook-agent / n8n-agent

Trach nhiem:

- Gui rejected posts sang n8n.
- Gui alert loi.
- Gui daily report.
- Tao luong duyet thu cong.

## 5. Cau truc repo de xuat

Nen giu upstream Hermes o root repo, va them phan ADS vao thu muc rieng de de merge upstream ve sau.

```text
Hermes_ADS_X/
  upstream Hermes files...
  ads/
    README.md
    docker-compose.ads.yml
    .env.example
    agents/
      telegram_reader/
        Dockerfile
        requirements.txt
        app/
          main.py
          config.py
          handlers.py
          storage.py
      evaluator/
        Dockerfile
        requirements.txt
        app/
          main.py
          hermes_client.py
          schemas.py
          prompts.py
      publisher/
        Dockerfile
        requirements.txt
        app/
          main.py
          telegram_client.py
          storage.py
      webhook/
        Dockerfile
        requirements.txt
        app/
          main.py
    db/
      migrations/
      schema.sql
    prompts/
      evaluator.md
      rewrite_caption.md
    config/
      rules.default.yaml
      channels.example.yaml
    ops/
      nginx/
      systemd/
      scripts/
        backup.sh
        deploy.sh
        healthcheck.sh
  .github/
    workflows/
      deploy.yml
```

Ly do:

- Root repo van gan voi upstream Hermes.
- Code rieng cua Duxq nam trong `ads/`.
- Sau nay update upstream de hon.
- GitHub Actions chi can build/deploy stack ADS + Hermes.

## 6. Chien luoc Git remote

### 6.1 Clone upstream va day sang repo cua Duxq

Tren may local hoac VPS:

```bash
git clone https://github.com/nousresearch/hermes-agent.git Hermes_ADS_X
cd Hermes_ADS_X
git remote rename origin upstream
git remote add origin https://github.com/dungdeptraiqua123-tech/Hermes_ADS_X.git
git push -u origin main
```

Neu repo `Hermes_ADS_X.git` da co commit san, can pull/rebase hoac tao branch moi truoc khi push.

### 6.2 Cap nhat upstream ve sau

```bash
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

Nen giu custom code trong `ads/` de giam conflict khi merge.

## 7. Chien luoc deploy tren VPS

Co 2 lua chon.

### 7.1 Lua chon A - Docker Compose, khuyen nghi cho production

Dung official Docker model cua Hermes va cac worker rieng:

```text
hermes
postgres
redis
telegram-reader
evaluator
publisher
webhook-agent
n8n optional
```

Uu diem:

- De CI/CD bang GitHub Actions.
- De rollback.
- De chay 24/24 bang `restart: unless-stopped`.
- Tach service ro rang.
- Khong phu thuoc qua nhieu vao system Python cua VPS.

Nhuoc diem:

- Can cai Docker/Compose tren VPS.
- Can quan ly volumes/secrets can than.

### 7.2 Lua chon B - Native install + systemd

Dung installer Hermes tren user `hermes`, sau do chay worker bang systemd services.

Uu diem:

- Gan voi docs Hermes.
- It container overhead.

Nhuoc diem:

- CI/CD update phuc tap hon.
- De bi lech dependency.
- Worker rieng can virtualenv/systemd rieng.

Khuyen nghi: chon Docker Compose cho `Hermes_ADS_X`.

## 8. Docker Compose production de xuat

File `ads/docker-compose.ads.yml`:

```yaml
services:
  hermes:
    image: nousresearch/hermes-agent:latest
    container_name: hermes-manager
    restart: unless-stopped
    command: ["gateway", "run"]
    volumes:
      - hermes_data:/opt/data
    environment:
      API_SERVER_ENABLED: "true"
      API_SERVER_HOST: "0.0.0.0"
      API_SERVER_PORT: "8642"
      API_SERVER_KEY: "${HERMES_API_KEY}"
      GOOGLE_API_KEY: "${GOOGLE_API_KEY}"
      TELEGRAM_BOT_TOKEN: "${HERMES_TELEGRAM_BOT_TOKEN}"
      TELEGRAM_ALLOWED_USERS: "${TELEGRAM_ALLOWED_USERS}"
    ports:
      - "127.0.0.1:8642:8642"

  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: hermes_ads
      POSTGRES_USER: hermes_ads
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data

  telegram-reader:
    build: ./agents/telegram_reader
    restart: unless-stopped
    depends_on:
      - postgres
      - redis
    environment:
      TELEGRAM_BOT_TOKEN: "${ADS_TELEGRAM_BOT_TOKEN}"
      DATABASE_URL: "${DATABASE_URL}"
      REDIS_URL: "${REDIS_URL}"

  evaluator:
    build: ./agents/evaluator
    restart: unless-stopped
    depends_on:
      - hermes
      - postgres
      - redis
    environment:
      HERMES_API_URL: "http://hermes:8642/v1"
      HERMES_API_KEY: "${HERMES_API_KEY}"
      DATABASE_URL: "${DATABASE_URL}"
      REDIS_URL: "${REDIS_URL}"

  publisher:
    build: ./agents/publisher
    restart: unless-stopped
    depends_on:
      - postgres
      - redis
    environment:
      TELEGRAM_BOT_TOKEN: "${ADS_TELEGRAM_BOT_TOKEN}"
      DATABASE_URL: "${DATABASE_URL}"
      REDIS_URL: "${REDIS_URL}"

volumes:
  hermes_data:
  postgres_data:
  redis_data:
```

Luu y bao mat:

- Port `8642` chi bind localhost tren host.
- Khong public Hermes API.
- Neu can public webhook, dung Nginx/Caddy + HTTPS.

## 9. File env production

`ads/.env.example`:

```env
# Hermes manager
HERMES_API_KEY=
GOOGLE_API_KEY=
HERMES_TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=

# ADS bot
ADS_TELEGRAM_BOT_TOKEN=
SOURCE_CHANNEL_IDS=
TARGET_CHANNEL_ID=
REVIEW_CHANNEL_ID=

# Storage
POSTGRES_PASSWORD=
DATABASE_URL=postgresql://hermes_ads:${POSTGRES_PASSWORD}@postgres:5432/hermes_ads
REDIS_URL=redis://redis:6379/0

# n8n/webhook optional
N8N_REJECT_WEBHOOK_URL=
N8N_ERROR_WEBHOOK_URL=
```

Nen tach:

- `HERMES_TELEGRAM_BOT_TOKEN`: bot chat voi Hermes Manager.
- `ADS_TELEGRAM_BOT_TOKEN`: bot worker doc/forward channel.

Dung 2 bot rieng de tranh conflict polling va tranh gateway voi worker cung dung 1 token.

## 10. Telegram channel workflow chi tiet

### 10.1 Dieu kien Telegram

Bot doc channel can:

- Duoc add vao source channel.
- Co quyen doc post/update.
- Neu doc group/supergroup thi can tat privacy mode hoac admin.
- Neu doc channel broadcast, bot nen la admin cua channel.

Bot post channel can:

- Duoc add vao target channel.
- Co quyen post message.

### 10.2 Luong xu ly

```text
1. Source channel co bai moi.
2. telegram-reader nhan update.
3. Tao event_key = source_channel_id + message_id.
4. Neu event_key da ton tai thi bo qua.
5. Luu raw post vao DB.
6. Day task vao Redis queue.
7. evaluator lay task, build prompt.
8. evaluator goi Hermes API.
9. Hermes tra JSON decision.
10. Validate JSON.
11. Neu passed=true: publisher dang sang target.
12. Neu requires_manual_review=true: gui sang review channel/webhook.
13. Neu rejected: log + optional n8n.
```

### 10.3 Response schema tu Hermes

```json
{
  "passed": true,
  "score": 86,
  "decision": "publish",
  "reason": "Bai viet dung chu de va du thong tin.",
  "target_channel_id": "-1009876543210",
  "publish_mode": "copy",
  "rewrite_caption": "Caption da chuan hoa neu can",
  "tags": ["ads", "qualified"],
  "requires_manual_review": false
}
```

### 10.4 Idempotency

Database can co unique key:

```text
source_channel_id + message_id
```

Delivery log can co:

```text
source_channel_id + message_id + target_channel_id
```

Neu service restart, khong duoc dang trung.

## 11. Database schema MVP

```sql
CREATE TABLE telegram_posts (
  id BIGSERIAL PRIMARY KEY,
  source_channel_id TEXT NOT NULL,
  source_channel_username TEXT,
  message_id BIGINT NOT NULL,
  media_group_id TEXT,
  text TEXT,
  caption TEXT,
  raw_json JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'received',
  UNIQUE (source_channel_id, message_id)
);

CREATE TABLE evaluations (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES telegram_posts(id),
  passed BOOLEAN NOT NULL,
  score INTEGER,
  decision TEXT,
  reason TEXT,
  target_channel_id TEXT,
  publish_mode TEXT,
  rewrite_caption TEXT,
  tags JSONB,
  raw_response JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE deliveries (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES telegram_posts(id),
  target_channel_id TEXT NOT NULL,
  target_message_id BIGINT,
  delivery_type TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (post_id, target_channel_id)
);
```

## 12. GitHub Actions deploy plan

### 12.1 Secrets can tao trong GitHub

Trong repo `Hermes_ADS_X` vao:

```text
Settings -> Secrets and variables -> Actions
```

Them:

```text
VPS_HOST=103.75.187.76
VPS_PORT=24700
VPS_USER=root
VPS_SSH_KEY=<private key deploy>
DEPLOY_PATH=/opt/hermes-ads-x
PROD_ENV_FILE=<noi dung file .env production>
```

Khuyen nghi tao SSH key deploy rieng tren may Duxq:

```bash
ssh-keygen -t ed25519 -C "github-actions-hermes-ads-x"
```

Add public key vao VPS:

```bash
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### 12.2 Workflow de xuat

`.github/workflows/deploy.yml`:

```yaml
name: Deploy Hermes ADS X

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install SSH key
        uses: shimataro/ssh-key-action@v2
        with:
          key: ${{ secrets.VPS_SSH_KEY }}
          known_hosts: unnecessary

      - name: Add known host
        run: |
          ssh-keyscan -p "${{ secrets.VPS_PORT }}" "${{ secrets.VPS_HOST }}" >> ~/.ssh/known_hosts

      - name: Deploy over SSH
        run: |
          ssh -p "${{ secrets.VPS_PORT }}" "${{ secrets.VPS_USER }}@${{ secrets.VPS_HOST }}" <<'EOF'
            set -e
            mkdir -p "${{ secrets.DEPLOY_PATH }}"
            cd "${{ secrets.DEPLOY_PATH }}"

            if [ ! -d .git ]; then
              git clone https://github.com/dungdeptraiqua123-tech/Hermes_ADS_X.git .
            else
              git fetch origin
              git reset --hard origin/main
            fi

            cat > ads/.env <<'ENVEOF'
          ${{ secrets.PROD_ENV_FILE }}
          ENVEOF

            docker compose -f ads/docker-compose.ads.yml --env-file ads/.env up -d --build
            docker compose -f ads/docker-compose.ads.yml ps
          EOF
```

Can sua lai indentation heredoc khi viet file that de tranh YAML loi.

### 12.3 Deploy an toan hon

Ban nang cap sau:

- Build Docker images trong GitHub Actions.
- Push image len GHCR.
- VPS chi pull image, khong build tren VPS.
- Dung tag theo commit SHA.
- Co rollback bang tag cu.

## 13. Cai dat VPS

Hien tai VPS cua Duxq da xac nhan la AlmaLinux 8.10, khong phai Ubuntu. Co 2 huong:

### 13.1 Neu giu AlmaLinux

```bash
dnf update -y
dnf install -y git curl ca-certificates openssl sudo nano dnf-plugins-core
```

Cai Docker:

```bash
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version
docker compose version
```

### 13.2 Neu muon dung Ubuntu dung nhu muc tieu ban dau

Reinstall VPS sang Ubuntu 22.04/24.04 LTS tren panel iNET, sau do:

```bash
apt update && apt upgrade -y
apt install -y git curl ca-certificates openssl sudo nano
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

## 14. Cai Hermes Manager tren VPS bang Docker

Thu muc production:

```bash
mkdir -p /opt/hermes-ads-x
cd /opt/hermes-ads-x
git clone https://github.com/dungdeptraiqua123-tech/Hermes_ADS_X.git .
cp ads/.env.example ads/.env
nano ads/.env
docker compose -f ads/docker-compose.ads.yml --env-file ads/.env up -d --build
```

Kiem tra:

```bash
docker compose -f ads/docker-compose.ads.yml ps
docker logs -f hermes-manager
curl -s http://127.0.0.1:8642/health
```

Test Hermes API:

```bash
curl -s http://127.0.0.1:8642/v1/chat/completions \
  -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"Tra loi ngan: API OK?"}],"stream":false}'
```

## 15. Cai Hermes Manager native neu khong dung Docker

Chi dung neu muon giu cach hien tai:

```bash
useradd -m -s /bin/bash hermes || true
su - hermes
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser
source ~/.bashrc
hermes setup
hermes model
hermes gateway setup
exit
sudo -u hermes hermes gateway install --system --run-as-user hermes
sudo hermes gateway start --system
sudo hermes gateway status --system
```

Luu y: lenh system service khong nen chay gateway bang root.

## 16. Rule danh gia ban dau

File `ads/config/rules.default.yaml`:

```yaml
minimum_score: 80
manual_review_score_min: 65
manual_review_score_max: 79
publish_mode: copy

blocked_keywords:
  - scam
  - casino
  - 18+

required_fields:
  - text_or_caption

categories:
  ads:
    target_channel_id: "-100xxxxxxxxxx"
    description: "Bai quang cao hop le theo tieu chi cua Duxq"
```

Prompt evaluator nen bat Hermes tra JSON duy nhat, khong giai thich ngoai JSON.

## 17. Ke hoach trien khai theo giai doan

### Phase 0 - Chuan hoa repo

Ket qua can co:

- Repo `Hermes_ADS_X` da clone tu upstream.
- Remote `upstream` tro toi Nous.
- Remote `origin` tro toi GitHub cua Duxq.
- File plan va overview trong repo.

### Phase 1 - Hermes Manager chay on dinh

Ket qua can co:

- Hermes chay bang Docker hoac systemd.
- Gemini provider cau hinh OK.
- API server noi bo bat tai port `8642`.
- `curl /health` OK.
- `curl /v1/chat/completions` OK.
- Telegram chat bot Hermes optional OK.

### Phase 2 - Telegram reader MVP

Ket qua can co:

- Bot doc duoc bai text tu 1 source channel test.
- Luu post vao DB.
- Chong trung theo channel/message id.

### Phase 3 - Evaluator MVP

Ket qua can co:

- Worker goi Hermes API.
- Hermes tra JSON pass/reject.
- Validate JSON.
- Luu bang `evaluations`.

### Phase 4 - Publisher MVP

Ket qua can co:

- Bai pass duoc copy/send sang channel dich test.
- Bai reject khong duoc dang.
- Delivery log day du.

### Phase 5 - Media/album/caption

Ket qua can co:

- Anh + caption duoc xu ly.
- Album/media group khong bi tach thanh nhieu bai sai.
- Video/document neu can duoc xu ly dung rule.

### Phase 6 - n8n/webhook/review

Ket qua can co:

- Reject post gui webhook.
- Manual review channel co approve/reject.
- Daily report.

### Phase 7 - CI/CD

Ket qua can co:

- Push main tu GitHub la VPS auto pull/build/restart.
- Secrets nam trong GitHub Actions.
- Khong commit `.env`.
- Co healthcheck sau deploy.

### Phase 8 - Production hardening

Ket qua can co:

- Backup Postgres.
- Log rotation.
- Firewall.
- SSH key only.
- Docker restart policy.
- Monitoring/alert.
- Rollback process.

## 18. Rủi ro va diem can quyet dinh

### 18.1 Co dung Telegram Bot API duoc khong?

Neu Duxq quan ly source channel va add bot duoc vao channel: dung Bot API.

Neu khong add bot vao source channel: Bot API khong doc duoc. Khi do phai dung user client nhu Telethon/Pyrogram, rui ro hon.

### 18.2 Forward hay copy?

- `forward`: giu nguon goc, minh bach.
- `copy`: dang lai sach hon, co the rewrite caption.
- `send`: linh hoat nhat, nhung can tu xu ly media.

De xuat MVP: `copy`.

### 18.3 Dung Hermes Telegram gateway hay worker rieng?

De xuat:

- Dung Hermes Telegram gateway cho chat/admin/control.
- Dung worker rieng cho channel pipeline.

Ly do: channel automation can idempotency, DB, retry, media group, publish mode, webhook. Gateway mac dinh khong sinh ra de lam toan bo viec nay.

### 18.4 Dung 1 bot token hay 2 bot token?

De xuat 2 bot:

- Bot 1: Hermes Manager chat bot.
- Bot 2: ADS pipeline bot doc/forward channel.

Ly do: tranh conflict polling/webhook va de tach quyen.

## 19. Viec can Duxq cung cap de bat dau code

Can chot:

- Source channel ID/username.
- Target channel ID/username.
- Review channel neu co.
- Bot token cho ADS pipeline.
- Bot token cho Hermes Manager neu muon chat truc tiep.
- Gemini API key.
- Tieu chi bai dat/khong dat.
- Muon copy, forward hay send lai.
- Co can n8n ngay MVP khong.
- VPS se giu AlmaLinux hay reinstall Ubuntu.

## 20. Checklist lenh quan trong

### VPS SSH

```bash
ssh -p 24700 root@103.75.187.76
```

### Kiem tra OS

```bash
cat /etc/os-release
```

### Kiem tra Docker

```bash
docker version
docker compose version
```

### Deploy

```bash
cd /opt/hermes-ads-x
git pull origin main
docker compose -f ads/docker-compose.ads.yml --env-file ads/.env up -d --build
```

### Logs

```bash
docker compose -f ads/docker-compose.ads.yml logs -f hermes
docker compose -f ads/docker-compose.ads.yml logs -f telegram-reader
docker compose -f ads/docker-compose.ads.yml logs -f evaluator
docker compose -f ads/docker-compose.ads.yml logs -f publisher
```

### Health

```bash
curl -s http://127.0.0.1:8642/health
```

## 21. Buoc tiep theo de thuc hien

Thu tu nen lam ngay sau file plan nay:

1. Clone upstream Hermes vao repo `Hermes_ADS_X`.
2. Tao branch `ads-x/bootstrap`.
3. Them thu muc `ads/`.
4. Them Docker Compose ADS.
5. Them `.env.example`.
6. Them schema database.
7. Scaffold `telegram-reader`, `evaluator`, `publisher`.
8. Chay local/VPS voi channel test.
9. Push len GitHub cua Duxq.
10. Them GitHub Actions deploy.

Ket luan: Hermes nen la manager/evaluator, con pipeline Telegram nen la doi worker rieng nam trong cung repo. Cach nay giu duoc suc manh cua Hermes, nhung van dam bao workflow channel ADS on dinh, co log, retry, chong trung va de deploy 24/24.
