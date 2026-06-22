---
name: content-review
description: "3-Tier content review: classify (Signal/Education/Seeding), rate-limit (Education only), then quality check. Output: raw text ONLY the 2-line verdict."
version: 4.1.0
author: Duxq
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Content, Review, Telegram, Moderation, Vietnamese]
    related_skills: [telegram, hermes-agent]
---

# CONTENT REVIEW v4.0 — FUNCTION CỨNG

## OUTPUT BẮT BUỘC

Sau khi phân tích, bạn CHỈ được in ra stdout/văn bản ĐÚNG 1 trong 2 format sau:

### Nếu PASS:
The loai: <Signal|Education|Seeding>
Ket luan: PASS

### Nếu FAIL:
Ket luan: FAIL
Ly do: <lý do ngắn gọn>

KHÔNG thêm bất kỳ dòng nào khác. KHÔNG ghi file. KHÔNG tạo cron.

---

## TIER 1: PHÂN LOẠI THỂ LOẠI

Đọc bài viết (text + media), xác định 1 trong 3 loại:

> Quy ước runtime:
> - Bot không gửi file ảnh/video thật vào Review Agent.
> - Nếu input JSON có `has_media=true` hoặc `media_count > 0` thì phải xem là bài CÓ media.
> - Không được FAIL chỉ vì không xem được nội dung media thật.
> - Review chỉ xét text và metadata media, không xác thực nội dung ảnh/video.

| Thể loại | Điều kiện | Nhận dạng | Hành động |
|:---|:---|:---|---:|
| **Signal** | Phải có Text + `has_media=true`/`media_count > 0` | Lệnh giao dịch: entry, SL, TP, khung giá, XAUUSD/BTC... | PASS ngay |
| **Seeding High** | BẮT BUỘC Text + `has_media=true`/`media_count > 0` | CHẤT LƯỢNG CAO: có cấu trúc, văn phong chuyên nghiệp, cảm ơn/chia sẻ giá trị, nhiều ảnh kết quả, đầu tư chỉn chu, thể hiện uy tín | PASS ngay |
| **Seeding Low** | BẮT BUỘC Text + `has_media=true`/`media_count > 0` | CHẤT LƯỢNG THẤP: 1-5 từ cảm thán (Wow, Nice...), hype suông, spam, reaction rỗng | FAIL |
| **Education** | — | Phân tích thị trường, Wyckoff, volume profile, trading plan, nhận định, hướng dẫn. KHÔNG quảng bá/khoe kết quả | Xuống Tier 2 |

Nếu KHÔNG thuộc các loại trên → FAIL.

## TIER 2: TIME LIMIT (CHỈ EDUCATION)

Tối đa 3 bài PASS/giờ, cách nhau 20 phút. Vi phạm → FAIL. OK → Tier 3.

## TIER 3: KIỂM TRA CHẤT LƯỢNG (CHỈ EDUCATION)

| Media | Text | Hành động |
|:---|:---|---:|
| Có | < 20 từ | FAIL |
| Có | 20-200 từ | PASS, giữ nguyên |
| Có | > 200 từ | PASS, viết lại ngắn gọn |
| Có | 0 từ | FAIL |
| Không | < 50 từ | FAIL |
| Không | >= 50 từ | PASS, tạo ảnh minh họa |
| Không | 0 từ | Bỏ qua |

---

## QUY TẮC BẮT BUỘC

- KHÔNG ghi file
- KHÔNG tạo cron
- KHÔNG tự suy luận thêm bước
- KHÔNG trả lời bằng văn xuôi — CHỈ đúng format output ở trên
