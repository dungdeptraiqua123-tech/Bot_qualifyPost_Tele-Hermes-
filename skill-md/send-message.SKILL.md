---
name: send-message
description: "Send/forward Telegram messages with media. FORWARD TEXT + IMAGES to target channel. Output: success or fail report."
version: 5.0.0
author: Duxq
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Telegram, Send, Forward, Media, Vietnamese]
    related_skills: [content-review, telegram]
---

# SEND MESSAGE v5.0 — FUNCTION CỨNG

## NHIỆM VỤ

Gửi bài viết (text + media) từ channel nguồn SANG channel đích theo ánh xạ chat_id.

## CẤM TUYỆT ĐỐI

- KHÔNG dùng send_message + MEDIA (tách text và ảnh thành 2 tin nhắn)
- KHÔNG ghi file
- KHÔNG tạo cron
- KHÔNG tự suy luận thêm bước

## CÁCH GỬI ĐÚNG

Số lượng media | Cách gửi
---|---
0 (chỉ text) | send_message(chat_id, text)
1 ảnh + text | send_photo(chat_id, photo=file, caption=text)
2-10 ảnh + text | send_media_group(chat_id, media=[InputMediaPhoto...] — caption ở ảnh đầu)
Video + text | send_video(chat_id, video=file, caption=text)

Luôn dùng:
```python
from telegram import Bot
from telegram.request import HTTPXRequest
req = HTTPXRequest(read_timeout=30, connect_timeout=30)
bot = Bot(token=token, request=req)
```

## ÁNH XẠ KÊNH

| Nguồn | Chat ID nguồn | → | Đích | Chat ID đích |
|---|---|---|---|---|
| Alex | -1002780727108 | → | Alex target | -1004328262936 |
| AZZAM | -1002742276977 | → | Azzam target | -1003849580412 |
| EDRIC | -1001606210890 | → | Eric target | -1004342644240 |
| Test | -1004391335313 | → | Target test | -1004398023536 |

## OUTPUT BẮT BUỘC

Sau khi gửi xong, CHỈ in ra:
Da gui: <channel dich>, message_id: <id>
Hoặc neu loi:
LOI: <noi dung loi>

KHÔNG thêm dòng nào khác.
