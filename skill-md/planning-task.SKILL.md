---
name: planning-task
description: "Channel post handler: content-review → send-message → report. Agent tự xử lý, không dùng pipeline.py."
version: 3.0.0
author: Duxq
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Workflow, Orchestrator, Pipeline, Telegram, Content, Vietnamese]
    related_skills: [content-review, send-message]
---

# Planning Task v3.0 — Agent tự xử lý channel_post

## Mục đích

Khi có bài viết mới từ Telegram channel, Hermes agent tự xử lý bằng skill, không cần pipeline.py.

## Quy trình

1. **Content Review** (skill content-review v3.6.0) — phân loại 3 tầng
2. **Gửi Telegram** (skill send-message v4.0.0) — forward sang channel đích nếu PASS
3. **Báo cáo** DM 5323156921

## Lưu ý

- KHÔNG ghi file
- KHÔNG tạo cron
- KHÔNG tự suy luận thêm bước
