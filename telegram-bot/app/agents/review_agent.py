from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.hermes_client import HermesClient
from app.models import PostObject


NO_MEDIA_REASON = "Bai viet khong co anh/video."


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
        if not _post_has_media(post):
            raw_text = f"Ket luan: FAIL\nLy do: {NO_MEDIA_REASON}"
            return ReviewResult(
                decision="fail",
                category=None,
                reason=NO_MEDIA_REASON,
                raw_text=raw_text,
            )

        raw_text = await self.hermes_client.chat_completion(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(post),
        )
        result = self.parse_result(raw_text)
        if not _is_false_no_media_fail(post, result):
            return result

        retry_raw_text = await self.hermes_client.chat_completion(
            system_prompt=self._media_retry_system_prompt(),
            user_prompt=self._media_retry_user_prompt(post, result),
        )
        return self.parse_result(retry_raw_text)

    def _system_prompt(self) -> str:
        return (
            "Ban la Review Agent cho Telegram channel posts.\n"
            "Tuan thu tuyet doi skill ben duoi va chi tra ve dung format PASS/FAIL.\n"
            "Runtime notes:\n"
            "- Bot khong gui anh/video that, chi gui metadata has_media va media_type.\n"
            "- Neu has_media=true hoac media_count > 0, phai xem nhu bai viet CO media.\n"
            "- Bai khong co media da bi bot chan truoc khi goi Review Agent.\n"
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

    def _media_retry_system_prompt(self) -> str:
        return (
            "Ban la Review Agent cho Telegram channel posts.\n"
            "CHI tra ve dung format PASS/FAIL, khong giai thich ngoai format.\n"
            "Quan trong: input co has_media=true hoac media_count > 0 thi bat buoc xem la CO media.\n"
            "Khong duoc FAIL voi ly do bai khong co anh/video neu metadata cho thay co media.\n"
            "Bot khong gui file media that; chi metadata media la du dieu kien media.\n\n"
            "<SKILL>\n"
            f"{self.skill_text}\n"
            "</SKILL>"
        )

    def _media_retry_user_prompt(self, post: PostObject, previous_result: ReviewResult) -> str:
        return (
            "Ket qua truoc do bi nghi la sai vi fail voi ly do khong co media, "
            "nhung metadata cua bai viet cho thay bai CO media.\n"
            "Hay review lai dua tren text va metadata. Khong fail vi khong xem duoc file media that.\n\n"
            f"{self._user_prompt(post)}\n\n"
            "Ket qua truoc do:\n"
            f"{previous_result.raw_text}"
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


def _post_has_media(post: PostObject) -> bool:
    return bool(post.has_media or post.media_count > 0)


def _is_false_no_media_fail(post: PostObject, result: ReviewResult) -> bool:
    if not _post_has_media(post) or result.decision != "fail":
        return False

    text = _fold(" ".join(part for part in [result.reason, result.raw_text] if part)).lower()
    no_media_phrases = (
        "khong co anh",
        "khong co video",
        "khong co media",
        "khong co hinh",
        "no media",
        "without media",
    )
    return any(phrase in text for phrase in no_media_phrases)


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
