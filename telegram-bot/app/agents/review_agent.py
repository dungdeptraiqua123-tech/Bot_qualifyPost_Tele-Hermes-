from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.hermes_client import HermesClient
from app.models import PostObject


@dataclass(frozen=True)
class ReviewResult:
    decision: str
    category: str | None
    reason: str | None
    raw_text: str

    @property
    def is_pass(self) -> bool:
        return self.decision == "pass"


class ReviewAgent:
    def __init__(self, *, hermes_client: HermesClient, skill_path: Path) -> None:
        self.hermes_client = hermes_client
        self.skill_path = skill_path
        self.skill_text = skill_path.read_text(encoding="utf-8")

    async def review(self, post: PostObject) -> ReviewResult:
        raw_text = await self.hermes_client.chat_completion(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(post),
        )
        return self.parse_result(raw_text)

    def _system_prompt(self) -> str:
        return (
            "Ban la Review Agent cho Telegram channel posts.\n"
            "Tuan thu tuyet doi skill ben duoi va chi tra ve dung format PASS/FAIL.\n"
            "Runtime notes:\n"
            "- Bot khong gui anh/video that, chi gui metadata has_media va media_type.\n"
            "- Neu has_media=true hoac media_count > 0, phai xem nhu bai viet CO media.\n"
            "- Khong duoc FAIL chi vi khong xem duoc noi dung anh/video that.\n"
            "- Review chi dua tren text va metadata media, khong xac thuc noi dung media.\n"
            "- Khong ap dung Tier 2 time limit vi bot khong cung cap lich su bai viet.\n"
            "- Khong viet them giai thich ngoai format bat buoc.\n\n"
            "<SKILL>\n"
            f"{self.skill_text}\n"
            "</SKILL>"
        )

    def _user_prompt(self, post: PostObject) -> str:
        payload = {
            "source_channel_id": post.source_channel_id,
            "source_channel_title": post.source_channel_title,
            "message_id": post.message_id,
            "text": post.text,
            "media_type": post.media_type,
            "has_media": post.has_media,
            "media_count": post.media_count,
            "media_group_id": post.media_group_id,
            "is_edited": post.is_edited,
            "target_channel_count": post.target_channel_count,
        }
        return (
            "Hay review bai viet Telegram sau theo skill content-review.\n"
            "Input JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def parse_result(raw_text: str) -> ReviewResult:
        text = raw_text.strip()
        normalized = _fold(text).lower()
        category = _extract_line_value(text, "The loai")
        reason = _extract_line_value(text, "Ly do")

        if re.search(r"ket\s*luan\s*:\s*pass", normalized, flags=re.IGNORECASE):
            return ReviewResult(
                decision="pass",
                category=category,
                reason=reason,
                raw_text=text,
            )
        if re.search(r"ket\s*luan\s*:\s*fail", normalized, flags=re.IGNORECASE):
            return ReviewResult(
                decision="fail",
                category=category,
                reason=reason,
                raw_text=text,
            )

        return ReviewResult(
            decision="unknown",
            category=category,
            reason="Unable to parse Review Agent verdict.",
            raw_text=text,
        )


def _extract_line_value(text: str, key: str) -> str | None:
    for line in text.splitlines():
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        if _fold(left).strip().lower() == _fold(key).lower():
            value = right.strip()
            return value or None
    return None


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")
