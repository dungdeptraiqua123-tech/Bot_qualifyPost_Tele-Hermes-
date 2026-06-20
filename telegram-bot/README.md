# Telegram Channel Reader

Bot reader local cho buoc dau cua du an Hermes ADS.

Muc tieu buoc 1:

- Chay bot Telegram bang long polling tren may local.
- Doc bai moi tu Telegram channel qua update `channel_post`.
- Doc bai channel bi sua qua `edited_channel_post`.
- Log object bai dang ra terminal.
- Quan ly mapping source channel -> target channels bang command trong bot.
- Goi Hermes Review Agent de danh gia PASS/FAIL khi post co mapping target.
- Neu PASS, goi Hermes Rewrite Agent de tao dung 1 bai moi cho moi channel dich.
- Publish bai rewrite kem media goc sang dung channel dich.

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
cho bot se bi tu choi. Channel post duoc xu ly rieng theo `ALLOWED_CHANNEL_IDS`
va mapping.

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
```

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

Allowed source channels duoc luu tai `config/allowed_channels.json`. Neu file nay
rong hoac khong co channel nao, bot se chap nhan moi channel ma no doc duoc. Sau
khi bot da chay, dung `/allow_add` thay vi sua `.env`.

## Dieu kien de doc channel

- Bot phai duoc them vao channel nguon.
- Bot nen la admin cua channel nguon.
- Bot phai la admin cua channel dich va co quyen dang bai de publish.
- Bot chi nhan bai moi sau khi duoc them vao channel.
- Neu bot tung dung webhook, app se tu goi `deleteWebhook` khi khoi dong.

## Luu y

Bot hien khong luu lich su bai viet xuong dia. Trong mot phien chay, bot chi
giu mot bo nho tam de tranh log trung cung mot `source_channel_id + message_id + update_type`.
