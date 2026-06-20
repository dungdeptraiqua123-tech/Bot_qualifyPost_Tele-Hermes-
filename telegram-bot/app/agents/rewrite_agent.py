from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.review_agent import ReviewResult
from app.hermes_client import HermesClient
from app.models import PostObject


@dataclass(frozen=True)
class RewritePost:
    target_channel_id: int
    text: str


@dataclass(frozen=True)
class RewriteResult:
    posts: list[RewritePost]
    raw_text: str


class RewriteAgent:
    def __init__(self, *, hermes_client: HermesClient, skill_path: Path) -> None:
        self.hermes_client = hermes_client
        self.skill_path = skill_path
        self.skill_text = skill_path.read_text(encoding="utf-8")

    async def rewrite(self, post: PostObject, review_result: ReviewResult) -> RewriteResult:
        raw_text = await self.hermes_client.chat_completion(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(post, review_result),
        )
        return self.parse_result(raw_text, expected_target_ids=post.target_channel_ids)

    def _system_prompt(self) -> str:
        return (
            "Ban la Rewrite Agent chuyen Telegram post thanh bai X/Twitter.\n"
            "Tuan thu skill ben duoi va tra ve JSON hop le, khong markdown.\n"
            "Output bat buoc dung schema:\n"
            "{\"posts\":[{\"target_channel_id\":-100123,\"text\":\"...\"}]}\n"
            "Quy tac runtime:\n"
            "- Tao dung 1 bai cho moi target_channel_id duoc cung cap.\n"
            "- So bai phai bang target_channel_count.\n"
            "- Moi bai <= 200 tu, co hook ro, noi dung gon, CTA text thuan.\n"
            "- Moi bai BAT BUOC co 1-3 emoji/icon lien quan; toi da 4 emoji/icon.\n"
            "- Chi dat emoji/icon o hook, bullet diem nhan, hoac truoc CTA neu phu hop.\n"
            "- Khong spam emoji, khong lap chuoi icon, khong thay so/gia/SL/TP bang icon.\n"
            "- Moi bai bat buoc ket thuc bang dung mot CTA: Link in bio hoac Check my profile.\n"
            "- Khong chen link Telegram, khong @handle, khong keu goi DM.\n"
            "- Khong bia so lieu moi. Neu la signal, giu nguyen entry/SL/TP/gia.\n"
            "- Bot se tu gui media goc sau, nen JSON chi can text.\n\n"
            "<SKILL>\n"
            f"{self.skill_text}\n"
            "</SKILL>"
        )

    def _user_prompt(self, post: PostObject, review_result: ReviewResult) -> str:
        payload = {
            "source_post": {
                "source_channel_id": post.source_channel_id,
                "source_channel_title": post.source_channel_title,
                "message_id": post.message_id,
                "text": post.text,
                "media_type": post.media_type,
                "has_media": post.has_media,
                "media_count": post.media_count,
                "media_group_id": post.media_group_id,
                "is_edited": post.is_edited,
                "target_channel_ids": post.target_channel_ids,
                "target_channel_count": post.target_channel_count,
            },
            "review": {
                "decision": review_result.decision,
                "category": review_result.category,
                "reason": review_result.reason,
            },
        }
        return (
            "Hay viet lai bai Telegram nay thanh cac bai X/Twitter rieng biet.\n"
            "Moi target_channel_id nhan dung 1 bai.\n"
            "Input JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def parse_result(raw_text: str, *, expected_target_ids: list[int]) -> RewriteResult:
        payload = _loads_json_payload(raw_text)
        raw_posts = payload.get("posts") if isinstance(payload, dict) else payload
        if not isinstance(raw_posts, list):
            raise RuntimeError("Rewrite Agent response must contain a posts list.")

        posts: list[RewritePost] = []
        for item in raw_posts:
            if not isinstance(item, dict):
                raise RuntimeError("Each rewritten post must be an object.")
            target_channel_id = item.get("target_channel_id")
            text = item.get("text")
            if target_channel_id is None or not isinstance(text, str) or not text.strip():
                raise RuntimeError("Each rewritten post needs target_channel_id and text.")
            posts.append(
                RewritePost(
                    target_channel_id=int(target_channel_id),
                    text=_style_required_icons(text.strip()),
                )
            )

        expected = [int(target_id) for target_id in expected_target_ids]
        actual = [post.target_channel_id for post in posts]
        if len(posts) != len(expected):
            raise RuntimeError(
                f"Rewrite Agent returned {len(posts)} posts, expected {len(expected)}."
            )
        if sorted(actual) != sorted(expected):
            raise RuntimeError(
                f"Rewrite Agent target ids mismatch. actual={actual!r} expected={expected!r}"
            )

        return RewriteResult(posts=posts, raw_text=raw_text.strip())


def _loads_json_payload(raw_text: str) -> Any:
    text = _strip_code_fence(raw_text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start != -1 and object_end != -1 and object_end > object_start:
        return json.loads(text[object_start : object_end + 1])

    array_start = text.find("[")
    array_end = text.rfind("]")
    if array_start != -1 and array_end != -1 and array_end > array_start:
        return json.loads(text[array_start : array_end + 1])

    raise RuntimeError("Rewrite Agent did not return valid JSON.")


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _style_required_icons(text: str) -> str:
    text = _ensure_required_icon(text)
    lines = text.splitlines()

    _prefix_first_matching_line(
        lines,
        pattern=r"\b(?:sl|stop loss|stoploss)\s*:",
        icon="🛑",
    )
    _prefix_first_matching_line(
        lines,
        pattern=r"\btp\s*\d*\s*:",
        icon="🎯",
    )
    _prefix_first_matching_line(
        lines,
        pattern=r"\b(?:link in bio|check my profile)\b",
        icon="👉",
    )
    if _icon_count("\n".join(lines)) < 2:
        _prefix_first_matching_line(
            lines,
            pattern=r"\b(?:entry|zone)\s*:",
            icon="✅",
        )

    return "\n".join(lines)


def _ensure_required_icon(text: str) -> str:
    if _has_icon(text):
        return text

    icon = _choose_icon(text)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip():
            leading_space = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{leading_space}{icon} {line.lstrip()}"
            return "\n".join(lines)

    return f"{icon} {text}".strip()


def _has_icon(text: str) -> bool:
    return _icon_count(text) > 0


def _icon_count(text: str) -> int:
    return sum(
        1
        for char in text
        if (0x1F000 <= ord(char) <= 0x1FAFF)
        or (0x2600 <= ord(char) <= 0x27BF)
    )


def _prefix_first_matching_line(lines: list[str], *, pattern: str, icon: str) -> None:
    if _icon_count("\n".join(lines)) >= 4:
        return
    regex = re.compile(pattern, flags=re.IGNORECASE)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or _has_icon(stripped) or not regex.search(stripped):
            continue
        leading_space = line[: len(line) - len(line.lstrip())]
        lines[index] = f"{leading_space}{icon} {line.lstrip()}"
        return


def _choose_icon(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(sell|short|bearish)\b", lowered):
        return "📉"
    if re.search(r"\b(buy|long|bullish)\b", lowered):
        return "📈"
    if re.search(r"\b(profit|pips|secured|tp|target|hit)\b", lowered):
        return "✅"
    if re.search(r"\b(gold|xauusd)\b", lowered):
        return "🥇"
    if re.search(r"\b(analysis|education|plan|setup)\b", lowered):
        return "🧠"
    return "📌"
