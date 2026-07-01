# Telegram Channel Reader

Bot reader local cho buoc dau cua du an Hermes ADS.

Muc tieu buoc 1:

- Chay bot Telegram bang long polling tren may local.
- Doc bai moi tu Telegram channel qua update `channel_post`.
- Doc bai channel bi sua qua `edited_channel_post`.
- Doc tin nhan moi trong group/supergroup neu nguoi gui la admin.
- Ho tro admin group thuong va admin dang an danh.
- Log object bai dang ra terminal.
- Quan ly mapping source channel -> target channels bang command trong bot.
- Goi Hermes Review Agent de danh gia PASS/FAIL khi post co mapping target.
- Neu PASS, goi Hermes Rewrite Agent de tao dung 1 bai moi cho moi channel dich.
- Publish bai rewrite kem media goc sang dung channel dich.
- Luu bai vao hang cho JSON ben vung va xu ly pipeline theo thu tu FIFO.

## Cai dat local

Neu dang dung PowerShell:

```powershell
cd C:\Users\20119\Desktop\Hermes_Agent\telegram-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Neu dang dung Command Prompt / CMD:

```bat
cd C:\Users\20119\Desktop\Hermes_Agent\telegram-bot
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Sau do mo file `.env` va dien token bot vao `TELEGRAM_BOT_TOKEN`.

De chi ban duoc dung bot commands va sua mapping, dien Telegram user ID vao:

```env
ADMIN_USER_IDS=5323156921
```

Nguoi khac van co the tim thay bot neu biet username, nhung khi nhan tin/lenh
cho bot se bi tu choi. Channel post va group admin post duoc xu ly rieng theo
`ALLOWED_CHANNEL_IDS` va mapping. Thanh vien thuong trong group se bi bo qua im
lang.

## Chay bot

```powershell
python -m app.main
```

Neu gap loi `telegram.error.TimedOut`, giu nguyen bot va chay lai. Bot da cau
hinh timeout dai hon mac dinh. Co the tang cac gia tri nay trong `.env`:

```env
TELEGRAM_REQUEST_TIMEOUT_SECONDS=30
TELEGRAM_POLLING_TIMEOUT_SECONDS=30
TELEGRAM_POLLING_READ_TIMEOUT_SECONDS=45
TELEGRAM_MEDIA_GROUP_FLUSH_DELAY_SECONDS=2
POST_QUEUE_PATH=config/post_queue.json
POST_QUEUE_MAX_ATTEMPTS=3
POST_QUEUE_RETRY_DELAY_SECONDS=10
POST_QUEUE_POLL_INTERVAL_SECONDS=1
```

## Hang cho bai viet

Ngay khi bot nhan va chuan hoa bai viet, snapshot text, Telegram media `file_id`,
source va target IDs duoc luu vao `POST_QUEUE_PATH`. Mot worker duy nhat xu ly
review -> rewrite -> publish theo thu tu nhan. Bai thanh cong duoc xoa khoi file.

Neu review, rewrite hoac publish loi, job duoc thu lai toi da
`POST_QUEUE_MAX_ATTEMPTS` lan. Target da publish thanh cong duoc ghi nhan de lan
retry khong dang trung. Job het so lan retry se giu trang thai `failed` trong
file de kiem tra, nhung khong chan cac job phia sau.

Album duoc tao thanh mot job `collecting` ngay tu media dau tien. Worker doi den
khi album duoc gom xong roi moi dua ca album vao pipeline. Khi bot restart, job
`processing` hoac album dang `collecting` se duoc dua ve `pending`.

## Hermes Review Agent

Bot se goi Hermes local qua OpenAI-compatible API sau khi channel post co mapping
target. Cau hinh trong `.env`:

```env
REVIEW_ENABLED=true
HERMES_API_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=<API_SERVER_KEY trong %USERPROFILE%\.hermes\.env>
HERMES_MODEL=hermes-agent
HERMES_REQUEST_TIMEOUT_SECONDS=120
REVIEW_SKILL_PATH=../skill-md/content-review.SKILL.md
REWRITE_ENABLED=true
REWRITE_SKILL_PATH=../skill-md/twitter-create-post.SKILL.md
PUBLISH_ENABLED=true
```

Khi review thanh cong, terminal se co log dang:

```text
[REVIEW_RESULT] source_channel_id=-100... message_id=... decision=pass category='Signal' reason=None raw='The loai: Signal Ket luan: PASS'
[REWRITE_RESULT] source_channel_id=-100... message_id=... expected_count=2 actual_count=2 targets=[-100..., -100...]
[REWRITE_POST] source_channel_id=-100... message_id=... target_channel_id=-100... text='...'
[PUBLISH_RESULT] source_channel_id=-100... message_id=... target_channel_id=-100... telegram_message_ids=[...] media_count=2
```

Neu publish loi `Chat not found`, bot khong truy cap duoc channel dich hoac
channel id sai. Kiem tra truc tiep bang:

```text
/chat_check <channel_id>
```

Khi bot dang chay, dang bai moi vao channel nguon. Terminal se hien log dang:

```text
[POST_OBJECT] source_channel_id=-100... message_id=... media_type=photo media_file_id='...' media_count=2 targets=[-100...] text='...'
```

Neu bai la album nhieu anh, Telegram se gui nhieu `channel_post` cung
`media_group_id`. Bot se gom cac message trong `TELEGRAM_MEDIA_GROUP_FLUSH_DELAY_SECONDS`
giay roi moi review/rewrite mot lan cho ca album.

## Mapping commands

Gui lenh truc tiep cho bot:

```text
/map_add <source_channel_id> <target_channel_id>
/map_remove <source_channel_id> <target_channel_id>
/map_list
/allow_add <source_channel_id>
/allow_remove <source_channel_id>
/allow_list
/chat_check <channel_id>
```

Vi du:

```text
/map_add -1001111111111 -1002222222222
/map_add -1001111111111 -1003333333333
/map_list
/map_remove -1001111111111 -1002222222222
```

Mapping duoc luu tai `config/mappings.json`. Day la cau hinh he thong, khong phai lich su bai viet.

`source_channel_id` co the la ID cua channel, group hoac supergroup. Vi du:

```text
/allow_add -1001111111111
/map_add -1001111111111 -1002222222222
```

Allowed source channels duoc luu tai `config/allowed_channels.json`. Neu file nay
rong hoac khong co channel nao, bot se chap nhan moi channel ma no doc duoc. Sau
khi bot da chay, dung `/allow_add` thay vi sua `.env`.

## Dieu kien de doc channel

- Bot phai duoc them vao channel nguon.
- Bot nen la admin cua channel nguon.
- Bot phai la admin cua channel dich va co quyen dang bai de publish.
- Bot chi nhan bai moi sau khi duoc them vao channel.
- Neu bot tung dung webhook, app se tu goi `deleteWebhook` khi khoi dong.

## Dieu kien de doc group

- Bot phai duoc them vao group/supergroup va duoc cap quyen admin.
- Them group ID bang `/allow_add <group_id>`.
- Tao mapping bang `/map_add <group_id> <target_channel_id>`.
- Tin nhan cua `administrator` va `creator` se vao pipeline nhu channel post.
- Tin nhan cua thanh vien thuong va bot khac se bi bo qua im lang.
- Admin an danh duoc chap nhan khi Telegram gui `sender_chat` chinh la group.
- Bai dang duoi danh nghia mot channel khac trong group se bi bo qua vi bot khong
  the xac minh an toan admin ca nhan da gui bai do.

## Luu y

Hang cho chi la du lieu van hanh tam thoi, khong phai lich su bai viet. Job thanh
cong se bi xoa. Bot khong tai file anh/video ve dia; Telegram `file_id` duoc dung
de publish lai media bang chinh bot nay.
