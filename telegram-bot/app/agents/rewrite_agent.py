from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
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
        result = self.parse_result(raw_text, expected_target_ids=post.target_channel_ids)
        if len(result.posts) <= 1 or _posts_are_distinct(result.posts):
            return result

        repair_raw_text = await self.hermes_client.chat_completion(
            system_prompt=self._system_prompt(),
            user_prompt=self._repair_user_prompt(post, review_result, result),
        )
        repair_result = self.parse_result(
            repair_raw_text,
            expected_target_ids=post.target_channel_ids,
        )
        if _posts_are_distinct(repair_result.posts):
            return repair_result

        return result

    def _system_prompt(self) -> str:
        return (
            "Ban la Rewrite Agent chuyen Telegram post thanh bai X/Twitter.\n"
            "Tuan thu skill ben duoi va tra ve JSON hop le, khong markdown.\n"
            "Output bat buoc dung schema:\n"
            "{\"posts\":[{\"target_channel_id\":-100123,\"text\":\"...\"}]}\n"
            "Quy tac runtime:\n"
            "- Tao dung 1 bai cho moi target_channel_id duoc cung cap.\n"
            "- So bai phai bang target_channel_count.\n"
            "- Neu co nhieu target_channel_id, moi bai phai la mot bien the text thuc su khac nhau.\n"
            "- Khong duoc chi doi CTA, emoji, xuong dong, hoac vai tu nho giua cac bai.\n"
            "- Moi bien the phai doi hook, goc viet, cau truc cau, thu tu y va cach dien dat.\n"
            "- Goi y bien the: recap ket qua, bai hoc ky luat, execution checklist, market insight.\n"
            "- Do tuong dong giua 2 bai phai thap; giu facts/gia/entry/SL/TP/pips chinh xac.\n"
            "- Moi bai <= 200 tu, co hook ro, noi dung gon, CTA co ly do ro de nguoi doc bam vao.\n"
            "- Moi bai BAT BUOC co emoji/icon lien quan o hook, signal lines, hoac y chinh.\n"
            "- Neu la signal, moi dong Entry/Zone phai co icon, moi dong TP phai co icon, moi dong SL phai co icon.\n"
            "- Icon signal chuan: Entry/Zone dung ✅, TP/Target dung 🎯, SL/Stop Loss dung ⛔.\n"
            "- Cac bai khac phai dat icon phu hop o cac y chinh/bullet quan trong.\n"
            "- Chi dat emoji/icon o hook, signal line, bullet diem nhan, hoac truoc CTA neu phu hop.\n"
            "- Khong spam emoji, khong lap chuoi icon, khong thay so/gia/SL/TP bang icon.\n"
            "- Neu bai co tin hieu entry/SL/TP, bat buoc dat thanh signal block rieng de de quet.\n"
            "- Khong viet entry, SL, TP chung trong cung mot cau/paragraph.\n"
            "- Format signal goi y: XAUUSD\\nBuy limit: 4153-4149\\nSL: 4140\\nTP1: 4166\\nTP2: 4179.\n"
            "- Moi bai bat buoc co CTA gan cuoi bai gom 2 phan: ly do/loi ich + Link in bio hoac Check my profile.\n"
            "- Vi du CTA: Need 1:1 guidance on entries and risk? Link in bio.\n"
            "- Vi du CTA: Want 24/7 market support and cleaner trade plans? Check my profile.\n"
            "- CTA khong duoc hua loi nhuan, khong cam ket winrate, khong tao cam giac dam bao ket qua.\n"
            "- Dong cuoi cung cua moi bai bat buoc la 2-4 hashtag phu hop voi noi dung.\n"
            "- Hashtag viet khong dau, uu tien tieng Anh, khong spam, khong hashtag chung chung qua muc.\n"
            "- Vi du hashtag: #XAUUSD #GoldTrading #ForexSignals #RiskManagement.\n"
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
            "Neu co nhieu target, cac bai phai la cac bien the doc lap: khac hook, khac cau truc, khac wording.\n"
            "Khong duoc tao cac bai gan nhu giong nhau roi chi doi CTA.\n"
            "Neu bai co tin hieu entry/SL/TP, hay tach thanh signal block rieng, moi muc mot dong de de nhin.\n"
            "Moi dong Entry/Zone, TP/Target, SL/Stop Loss phai co icon phu hop de lam noi bat tin hieu.\n"
            "Neu khong phai signal, cac y chinh/bullet quan trong can co icon phu hop nhung khong spam.\n"
            "CTA cuoi bai phai cho nguoi doc mot ly do cu the de bam vao profile/bio.\n"
            "Dong cuoi cung phai co 2-4 hashtag phu hop voi bai viet.\n"
            "Input JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _repair_user_prompt(
        self,
        post: PostObject,
        review_result: ReviewResult,
        previous_result: RewriteResult,
    ) -> str:
        previous_payload = {
            "posts": [
                {
                    "target_channel_id": item.target_channel_id,
                    "text": item.text,
                }
                for item in previous_result.posts
            ]
        }
        return (
            f"{self._user_prompt(post, review_result)}\n\n"
            "Ket qua truoc do bi loai vi cac bai qua giong nhau.\n"
            "Hay viet lai TOAN BO posts tu dau, khong sua nhe tren ban cu.\n"
            "Moi post can khac ro hook, goc nhin, cau truc cau va thu tu trien khai y.\n"
            "Van giu nguyen facts, gia, entry, SL, TP, pips va dung target_channel_id.\n"
            "Ket qua truoc do:\n"
            f"{json.dumps(previous_payload, ensure_ascii=False, indent=2)}"
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
                    text=_style_enhanced_icons(
                        _style_required_hashtags(
                            _style_value_cta(_style_signal_block(text.strip()))
                        )
                    ),
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
    decoder = json.JSONDecoder()

    try:
        payload, _ = decoder.raw_decode(text)
        if _is_rewrite_payload(payload):
            return payload
    except json.JSONDecodeError:
        pass

    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if _is_rewrite_payload(payload):
            return payload

    raise RuntimeError("Rewrite Agent did not return valid JSON.")


def _is_rewrite_payload(payload: Any) -> bool:
    if isinstance(payload, dict):
        return isinstance(payload.get("posts"), list)
    return isinstance(payload, list)


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _style_signal_block(text: str) -> str:
    lines = text.splitlines()
    styled_lines: list[str] = []

    for line in lines:
        facts = _extract_inline_signal_facts(line.strip())
        if not facts:
            styled_lines.append(line)
            continue

        leading_space = line[: len(line) - len(line.lstrip())]
        block = _build_signal_block(facts)
        commentary = _signal_commentary(line.strip(), facts["spans"])

        if styled_lines and styled_lines[-1].strip():
            styled_lines.append("")
        styled_lines.extend(f"{leading_space}{item}" for item in block)
        if commentary:
            styled_lines.extend(["", f"{leading_space}{commentary}"])

    return "\n".join(styled_lines)


def _extract_inline_signal_facts(line: str) -> dict[str, Any] | None:
    if not line:
        return None

    entry_match = _find_entry_match(line)
    if not entry_match:
        return None

    sl_match = re.search(
        r"\b(?:sl|stop\s*loss)\s*[:@]?\s*(?P<value>\d+(?:\.\d+)?)",
        line,
        flags=re.IGNORECASE,
    )
    tp_matches = list(
        re.finditer(
            r"\b(?:tp|target)\s*(?P<num>\d*)\s*[:@]?\s*(?P<value>open|\d+(?:\.\d+)?)",
            line,
            flags=re.IGNORECASE,
        )
    )
    if not sl_match and not tp_matches:
        return None

    symbol_match = re.search(
        r"\b(XAUUSD|BTCUSD|ETHUSD|EURUSD|GBPUSD|USDJPY|NAS100|US30)\b",
        line,
        flags=re.IGNORECASE,
    )
    spans = [entry_match.span(), *(match.span() for match in tp_matches)]
    if sl_match:
        spans.append(sl_match.span())
    if symbol_match:
        spans.append(symbol_match.span())

    return {
        "symbol": symbol_match.group(1).upper() if symbol_match else None,
        "entry_label": _entry_label(entry_match),
        "entry_value": _normalize_signal_value(entry_match.group("value")),
        "sl": _normalize_signal_value(sl_match.group("value")) if sl_match else None,
        "tps": [
            (
                f"TP{match.group('num')}" if match.group("num") else "TP",
                _normalize_signal_value(match.group("value")),
            )
            for match in tp_matches
        ],
        "spans": spans,
    }


def _find_entry_match(line: str) -> re.Match[str] | None:
    value_pattern = r"\d+(?:\.\d+)?(?:\s*(?:-|–|—|to)\s*\d+(?:\.\d+)?)?"
    patterns = [
        rf"\b(?P<direction>buy|sell)\s+(?P<order>limit|stop|market)?\s*(?:at|zone|entry)?\s*[:@]?\s*(?P<value>{value_pattern})",
        rf"\b(?P<label>entry(?:\s+point)?|zone)\s*[:@]?\s*(?P<value>{value_pattern})",
    ]
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _entry_label(match: re.Match[str]) -> str:
    direction = match.groupdict().get("direction")
    if not direction:
        return "Entry"

    order = match.groupdict().get("order") or ""
    label = f"{direction} {order}".strip()
    return label.capitalize()


def _normalize_signal_value(value: str) -> str:
    return re.sub(r"\s*(?:-|–|—|to)\s*", "-", value.strip(), flags=re.IGNORECASE)


def _build_signal_block(facts: dict[str, Any]) -> list[str]:
    block: list[str] = []
    if facts["symbol"]:
        block.append(str(facts["symbol"]))

    block.append(f"{facts['entry_label']}: {facts['entry_value']}")
    if facts["sl"]:
        block.append(f"SL: {facts['sl']}")
    for label, value in facts["tps"]:
        block.append(f"{label}: {value.upper() if value.lower() == 'open' else value}")
    return block


def _signal_commentary(line: str, spans: list[tuple[int, int]]) -> str:
    cleaned = line
    for start, end in sorted(spans, reverse=True):
        cleaned = f"{cleaned[:start]} {cleaned[end:]}"
    cleaned = re.sub(r"\s*[|•,;]\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-–—|")
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"(?:\.\s*){2,}", ". ", cleaned).strip(" .,-–—|")
    if not cleaned or not re.search(r"[A-Za-z0-9]", cleaned):
        return ""
    return f"{cleaned[:1].upper()}{cleaned[1:]}"


def _style_value_cta(text: str) -> str:
    lines = text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].strip()
        if not line:
            continue
        if _is_hashtag_line(line):
            continue
        anchor = _extract_cta_anchor(line)
        if not anchor:
            return text
        if _has_cta_reason(line):
            return text

        leading_space = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        lines[index] = f"{leading_space}{_build_value_cta(anchor, text)}"
        return "\n".join(lines)
    return text


def _style_required_hashtags(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    selected = _select_hashtags(text)

    while lines and not lines[-1].strip():
        lines.pop()
    while lines and _is_hashtag_line(lines[-1].strip()):
        lines.pop()

    if not lines:
        return " ".join(selected)

    return "\n".join([*lines, "", " ".join(selected)])


def _extract_cta_anchor(line: str) -> str | None:
    match = re.search(r"\b(link in bio|check my profile)\b", line, flags=re.IGNORECASE)
    if not match:
        return None
    anchor = match.group(1).lower()
    if anchor == "link in bio":
        return "Link in bio"
    return "Check my profile"


def _has_cta_reason(line: str) -> bool:
    without_anchor = re.sub(
        r"\b(?:link in bio|check my profile)\b",
        " ",
        line,
        flags=re.IGNORECASE,
    )
    words = re.findall(r"[A-Za-z0-9]+", without_anchor)
    return len(words) >= 4


def _build_value_cta(anchor: str, text: str) -> str:
    templates = _cta_templates_for(text)
    index = sum(ord(char) for char in text + anchor) % len(templates)
    return templates[index].format(anchor=anchor)


def _cta_templates_for(text: str) -> list[str]:
    lowered = text.lower()
    if re.search(r"\b(entry|sl|stop loss|tp|target|setup|signal)\b", lowered):
        return [
            "Need 1:1 guidance to plan entries and risk? {anchor}.",
            "Want cleaner trade plans with risk notes? {anchor}.",
            "Need 24/7 market support before the next setup? {anchor}.",
        ]
    if re.search(r"\b(profit|pips|secured|recap|session)\b", lowered):
        return [
            "Want the full session breakdown and risk notes? {anchor}.",
            "Need help turning clean execution into a repeatable plan? {anchor}.",
            "Want 1:1 support to review entries and exits? {anchor}.",
        ]
    if re.search(r"\b(analysis|market|structure|trend|price action)\b", lowered):
        return [
            "Need a clearer market read before your next entry? {anchor}.",
            "Want practical XAUUSD analysis and setup notes? {anchor}.",
            "Need 1:1 support building a cleaner trade plan? {anchor}.",
        ]
    return [
        "Need 1:1 support and practical trading guidance? {anchor}.",
        "Want market updates, risk notes, and cleaner plans? {anchor}.",
        "Need 24/7 support around trade planning? {anchor}.",
    ]


def _select_hashtags(text: str) -> list[str]:
    existing = [_normalize_hashtag(item) for item in re.findall(r"#\w+", text)]
    existing = [item for item in existing if item]
    candidates = [*existing, *_hashtag_candidates_for(text)]

    selected: list[str] = []
    for tag in candidates:
        if tag not in selected:
            selected.append(tag)
        if len(selected) >= 4:
            break

    while len(selected) < 2:
        for fallback in ["#Trading", "#Forex"]:
            if fallback not in selected:
                selected.append(fallback)
            if len(selected) >= 2:
                break

    return selected


def _hashtag_candidates_for(text: str) -> list[str]:
    lowered = text.lower()
    candidates: list[str] = []

    if re.search(r"\b(gold|xauusd)\b", lowered):
        candidates.extend(["#XAUUSD", "#GoldTrading"])
    if re.search(r"\b(entry|sl|stop loss|tp|target|setup|signal)\b", lowered):
        candidates.extend(["#ForexSignals", "#TradeSetup"])
    if re.search(r"\b(profit|pips|secured|recap|session)\b", lowered):
        candidates.extend(["#TradingRecap", "#RiskManagement"])
    if re.search(r"\b(analysis|market|structure|trend|price action)\b", lowered):
        candidates.extend(["#MarketAnalysis", "#PriceAction"])
    if re.search(r"\b(risk|break.?even|capital|management)\b", lowered):
        candidates.append("#RiskManagement")

    candidates.extend(["#Trading", "#Forex"])
    return candidates


def _normalize_hashtag(value: str) -> str | None:
    tag = re.sub(r"[^A-Za-z0-9_]", "", value.lstrip("#"))
    if not tag:
        return None
    return f"#{tag[:40]}"


def _is_hashtag_line(line: str) -> bool:
    tokens = line.split()
    if not tokens:
        return False
    return all(re.fullmatch(r"#[A-Za-z0-9_]+", token) for token in tokens)


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


ICON_ENTRY = "\u2705"
ICON_TP = "\U0001f3af"
ICON_SL = "\u26d4"
ICON_CTA = "\U0001f449"
ICON_KEY = "\U0001f4cc"
ICON_BUY = "\U0001f4c8"
ICON_SELL = "\U0001f4c9"
ICON_PROFIT = "\u2705"
ICON_GOLD = "\U0001f947"
ICON_ANALYSIS = "\U0001f9e0"
ICON_DEFAULT = "\U0001f4cc"


def _style_enhanced_icons(text: str) -> str:
    text = _ensure_topic_icon(text)
    lines = text.splitlines()

    _prefix_all_icon_lines(
        lines,
        pattern=r"\b(?:(?:buy|sell)\s+(?:limit|stop|market)?|entry|entry point|zone|buy zone|sell zone)\s*:",
        icon=ICON_ENTRY,
    )
    _prefix_all_icon_lines(
        lines,
        pattern=r"\b(?:sl|stop loss|stoploss)\s*:",
        icon=ICON_SL,
    )
    _prefix_all_icon_lines(
        lines,
        pattern=r"\b(?:tp|target)\s*\d*\s*:",
        icon=ICON_TP,
    )
    _prefix_first_icon_line(
        lines,
        pattern=r"\b(?:link in bio|check my profile)\b",
        icon=ICON_CTA,
    )
    _prefix_key_point_lines(lines)

    return "\n".join(lines)


def _ensure_topic_icon(text: str) -> str:
    if _has_icon(text):
        return text

    icon = _choose_enhanced_icon(text)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip():
            leading_space = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{leading_space}{icon} {line.lstrip()}"
            return "\n".join(lines)

    return f"{icon} {text}".strip()


def _prefix_all_icon_lines(lines: list[str], *, pattern: str, icon: str) -> None:
    regex = re.compile(pattern, flags=re.IGNORECASE)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or _has_icon(stripped) or not regex.search(stripped):
            continue
        leading_space = line[: len(line) - len(line.lstrip())]
        lines[index] = f"{leading_space}{icon} {line.lstrip()}"


def _prefix_first_icon_line(lines: list[str], *, pattern: str, icon: str) -> None:
    regex = re.compile(pattern, flags=re.IGNORECASE)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or _has_icon(stripped) or not regex.search(stripped):
            continue
        leading_space = line[: len(line) - len(line.lstrip())]
        lines[index] = f"{leading_space}{icon} {line.lstrip()}"
        return


def _prefix_key_point_lines(lines: list[str]) -> None:
    added = 0
    patterns = [
        r"^\s*[-*•]\s+\S+",
        r"\b(?:key levels?|what worked|risk|plan|setup|support|resistance|market structure|trade plan|bulls?|bears?|momentum)\b",
    ]
    regexes = [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]

    for index, line in enumerate(lines):
        stripped = line.strip()
        if (
            not stripped
            or _has_icon(stripped)
            or _is_hashtag_line(stripped)
            or re.search(r"\b(?:link in bio|check my profile)\b", stripped, flags=re.IGNORECASE)
        ):
            continue
        if not any(regex.search(stripped) for regex in regexes):
            continue

        leading_space = line[: len(line) - len(line.lstrip())]
        lines[index] = f"{leading_space}{ICON_KEY} {line.lstrip()}"
        added += 1
        if added >= 3:
            return


def _choose_enhanced_icon(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(sell|short|bearish)\b", lowered):
        return ICON_SELL
    if re.search(r"\b(buy|long|bullish)\b", lowered):
        return ICON_BUY
    if re.search(r"\b(profit|pips|secured|tp|target|hit)\b", lowered):
        return ICON_PROFIT
    if re.search(r"\b(gold|xauusd)\b", lowered):
        return ICON_GOLD
    if re.search(r"\b(analysis|education|plan|setup)\b", lowered):
        return ICON_ANALYSIS
    return ICON_DEFAULT


def _posts_are_distinct(posts: list[RewritePost]) -> bool:
    for index, left in enumerate(posts):
        for right in posts[index + 1 :]:
            if _text_similarity(left.text, right.text) >= 0.78:
                return False
    return True


def _text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None,
        _normalize_for_similarity(left),
        _normalize_for_similarity(right),
    ).ratio()


def _normalize_for_similarity(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.lower()
    text = re.sub(r"\b(?:link in bio|check my profile)\b", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
