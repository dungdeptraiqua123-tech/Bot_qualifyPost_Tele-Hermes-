#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


SCHEMA_VERSION = "recent-x-activity/v1"
XQUIK_ENDPOINT = "https://xquik.com/api/v1/x/tweets/search"
SOURCE_XQUIK = "xquik"
SOURCE_NONE = "none"

THEME_KEYWORDS = {
    "ICT": [
        "ict",
        "fair value gap",
        "fvg",
        "order block",
        "displacement",
        "killzone",
        "premium",
        "discount",
    ],
    "SMC": [
        "smc",
        "smart money",
        "bos",
        "choch",
        "liquidity grab",
        "market structure",
        "imbalance",
    ],
    "Price Action": [
        "price action",
        "support",
        "resistance",
        "supply",
        "demand",
        "break and retest",
        "zone",
        "confirmation",
    ],
    "Scalping": [
        "scalp",
        "scalping",
        "m1",
        "m5",
        "m15",
        "london session",
        "ny session",
    ],
    "Swing": [
        "swing",
        "h4",
        "d1",
        "daily bias",
        "weekly",
        "multi-day",
    ],
    "Prop Firm": [
        "prop firm",
        "funded",
        "ftmo",
        "challenge",
        "drawdown",
        "evaluation",
    ],
    "Signal Provider": [
        "signal",
        "signals",
        "vip",
        "tp",
        "sl",
        "entry",
        "copy trade",
    ],
    "Gold only": [
        "xauusd",
        "gold",
        "bullion",
    ],
    "Multi-asset": [
        "eurusd",
        "gbpusd",
        "us30",
        "nasdaq",
        "spx",
        "oil",
        "btc",
        "crypto",
        "indices",
    ],
}

TRADING_TERMS = [
    "xauusd",
    "gold",
    "forex",
    "liquidity",
    "order block",
    "fair value gap",
    "fvg",
    "smc",
    "ict",
    "support",
    "resistance",
    "supply",
    "demand",
    "breakout",
    "retest",
    "scalp",
    "swing",
    "entry",
    "stop loss",
    "sl",
    "take profit",
    "tp",
    "risk",
    "drawdown",
    "funded",
    "prop firm",
    "news",
    "cpi",
    "nfp",
    "fomc",
]

AUTHOR_FIELD_NAMES = [
    "author_username",
    "authorUserName",
    "author_handle",
    "authorHandle",
    "author_screen_name",
    "screen_name",
    "screenName",
    "username",
    "userName",
    "handle",
]

AUTHOR_OBJECT_FIELD_NAMES = [
    "author",
    "user",
    "account",
    "profile",
    "creator",
    "owner",
]

TEXT_FIELD_NAMES = ["text", "full_text", "content", "tweet", "body"]


class AtomicTextWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tmp_path: Optional[Path] = None
        self.handle: Optional[TextIO] = None

    def __enter__(self) -> TextIO:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
            text=True,
        )
        self.tmp_path = Path(tmp_name)
        self.handle = os.fdopen(fd, "w", encoding="utf-8")
        return self.handle

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.handle is not None
        assert self.tmp_path is not None
        self.handle.close()
        if exc_type is not None:
            try:
                self.tmp_path.unlink()
            except FileNotFoundError:
                pass
            return False
        self.tmp_path.replace(self.path)
        return False


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_username(username: str) -> str:
    value = (username or "").strip()
    value = re.sub(r"^https?://(?:www\.)?(?:x|twitter)\.com/", "", value, flags=re.I)
    value = value.split("/", 1)[0].split("?", 1)[0].strip()
    value = value.lstrip("@")
    return value.lower()


def display_username(username: str) -> str:
    normalized = normalize_username(username)
    return f"@{normalized}" if normalized else ""


def author_candidates_from_value(value: Any) -> list[str]:
    candidates = []
    if isinstance(value, str):
        normalized = normalize_username(value)
        if normalized:
            candidates.append(normalized)
    elif isinstance(value, dict):
        for key in AUTHOR_FIELD_NAMES:
            item = value.get(key)
            if isinstance(item, str):
                normalized = normalize_username(item)
                if normalized:
                    candidates.append(normalized)
    return candidates


def author_candidates(record: dict[str, Any]) -> list[str]:
    candidates = []
    for key in AUTHOR_FIELD_NAMES:
        candidates.extend(author_candidates_from_value(record.get(key)))
    for key in AUTHOR_OBJECT_FIELD_NAMES:
        candidates.extend(author_candidates_from_value(record.get(key)))
    return list(dict.fromkeys(candidates))


def is_target_author(record: dict[str, Any], target_username: str) -> bool:
    target = normalize_username(target_username)
    if not target:
        return False
    return any(candidate == target for candidate in author_candidates(record))


def cache_path(cache_dir: Path, username: str, today: str) -> Path:
    return cache_dir / f"{normalize_username(username)}-{today}.json"


def base_payload(
    *,
    username: str,
    query: str,
    window_days: int,
    status: str,
    source: str,
    cache_hit: bool = False,
    posts: Optional[list[dict[str, Any]]] = None,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "username": display_username(username),
        "query": query,
        "window_days": window_days,
        "status": status,
        "source": source,
        "fetched_at": iso_now(),
        "cache_hit": cache_hit,
        "posts": posts or [],
        "evidence": build_evidence(posts or []),
        "warnings": warnings or [],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with AtomicTextWriter(path) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_cached(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["cache_hit"] = True
    payload["fetched_at"] = iso_now()
    return payload


def text_contains(text: str, needle: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(needle.lower())}(?![a-z0-9])", text.lower()) is not None


def count_term(texts: list[str], term: str) -> int:
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", re.I)
    return sum(len(pattern.findall(text)) for text in texts)


def extract_trading_terms(texts: list[str]) -> list[str]:
    joined = "\n".join(texts).lower()
    found = []
    for term in TRADING_TERMS:
        if text_contains(joined, term):
            found.append(term)
    return found


def extract_themes(texts: list[str]) -> list[str]:
    joined = "\n".join(texts).lower()
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(text_contains(joined, keyword) for keyword in keywords):
            themes.append(theme)
    if "Gold only" in themes and "Multi-asset" in themes:
        gold_count = count_term(texts, "gold") + count_term(texts, "xauusd")
        multi_count = sum(count_term(texts, term) for term in THEME_KEYWORDS["Multi-asset"])
        if multi_count >= gold_count:
            themes.remove("Gold only")
    return themes


def infer_persona(themes: list[str], texts: list[str]) -> str:
    joined = "\n".join(texts).lower()
    if "ICT" in themes:
        return "ICT Trader"
    if "SMC" in themes:
        return "SMC Trader"
    if "Prop Firm" in themes:
        return "Prop Trader"
    if "Scalping" in themes:
        return "Scalper"
    if "Swing" in themes:
        return "Swing Trader"
    if any(text_contains(joined, term) for term in ["teach", "lesson", "thread", "education", "mentor"]):
        return "Educator"
    if "Signal Provider" in themes:
        return "Signal Provider"
    if any(text_contains(joined, term) for term in ["cpi", "nfp", "fomc", "rates", "dxy", "fed"]):
        return "Macro Trader"
    if "Price Action" in themes:
        return "Price Action Trader"
    if "Gold only" in themes:
        return "Gold Analyst"
    if len(themes) > 1:
        return "Hybrid"
    return ""


def build_summary(posts: list[dict[str, Any]], themes: list[str], persona_hint: str) -> str:
    if not posts:
        return ""
    pieces = []
    if persona_hint:
        pieces.append(f"Recent X activity suggests {persona_hint.lower()}")
    else:
        pieces.append("Recent X activity found")
    if themes:
        pieces.append("with themes: " + ", ".join(themes[:4]))
    xauusd_count = sum(count_term([str(post.get("text", ""))], "xauusd") for post in posts)
    gold_count = sum(count_term([str(post.get("text", ""))], "gold") for post in posts)
    if xauusd_count or gold_count:
        pieces.append(f"across {xauusd_count} XAUUSD and {gold_count} gold mention(s)")
    return "; ".join(pieces) + "."


def build_evidence(posts: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [str(post.get("text", "")) for post in posts if str(post.get("text", "")).strip()]
    themes = extract_themes(texts)
    persona_hint = infer_persona(themes, texts)
    return {
        "recent_activity": bool(posts),
        "xauusd_mentions": count_term(texts, "xauusd"),
        "gold_mentions": count_term(texts, "gold"),
        "trading_terms": extract_trading_terms(texts),
        "themes": themes,
        "persona_hint": persona_hint,
        "summary": build_summary(posts, themes, persona_hint),
    }


def parse_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return default


def first_value(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def record_text(record: dict[str, Any]) -> Any:
    return first_value(record, TEXT_FIELD_NAMES)


def post_from_record(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    text = record_text(record)
    if not text or not str(text).strip():
        return None
    url = first_value(record, ["url", "tweet_url", "link", "expanded_url"])
    metrics = record.get("public_metrics") if isinstance(record.get("public_metrics"), dict) else {}
    return {
        "text": " ".join(str(text).split()),
        "created_at": str(first_value(record, ["created_at", "createdAt", "date", "timestamp"]) or ""),
        "url": str(url or ""),
        "like_count": parse_int(first_value(record, ["like_count", "favorite_count", "favorites", "likes"]) or metrics.get("like_count")),
        "reply_count": parse_int(first_value(record, ["reply_count", "replies"]) or metrics.get("reply_count")),
        "repost_count": parse_int(first_value(record, ["repost_count", "retweet_count", "retweets"]) or metrics.get("retweet_count")),
    }


def iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def extract_posts(response_payload: Any, limit: int, target_username: str) -> tuple[list[dict[str, Any]], int]:
    posts = []
    seen = set()
    discarded_author_count = 0
    for record in iter_dicts(response_payload):
        if not is_target_author(record, target_username):
            if record_text(record):
                discarded_author_count += 1
            continue
        post = post_from_record(record)
        if not post:
            continue
        key = (post["text"], post["created_at"], post["url"])
        if key in seen:
            continue
        seen.add(key)
        posts.append(post)
        if len(posts) >= limit:
            break
    return posts, discarded_author_count


def build_backend_query(username: str, query: str, window_days: int) -> str:
    handle = normalize_username(username)
    until_date = utc_now().date()
    since_date = until_date - timedelta(days=max(1, window_days))
    terms = []
    for token in re.split(r"\s+", query or ""):
        clean = token.strip()
        if not clean or clean.lower().lstrip("@") == handle:
            continue
        if clean.lower() in {"from:" + handle}:
            continue
        terms.append(clean)
    suffix = " ".join(terms).strip()
    base = f"from:{handle} since:{since_date.isoformat()} until:{until_date.isoformat()}"
    return f"{base} {suffix}".strip()


def fetch_xquik(api_key: str, backend_query: str, timeout: int, limit: int) -> Any:
    params = urllib.parse.urlencode(
        {
            "q": backend_query,
            "queryType": "Top",
            "limit": str(limit),
        }
    )
    request = urllib.request.Request(
        f"{XQUIK_ENDPOINT}?{params}",
        headers={
            "x-api-key": api_key,
            "accept": "application/json",
            "user-agent": "hermes-xauusd-recent-x-activity/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def run(args: argparse.Namespace) -> dict[str, Any]:
    today = utc_now().date().isoformat()
    username = display_username(args.username)
    warnings = []

    if not username:
        return base_payload(
            username=args.username,
            query=args.query,
            window_days=args.window_days,
            status="failed",
            source=SOURCE_NONE,
            warnings=["username is required"],
        )

    cache_file = cache_path(args.cache_dir, username, today)
    cached = read_cached(cache_file)
    if cached is not None:
        return cached

    api_key = os.environ.get("XQUIK_API_KEY", "").strip()
    if not api_key:
        payload = base_payload(
            username=username,
            query=args.query,
            window_days=args.window_days,
            status="skipped",
            source=SOURCE_NONE,
            warnings=["XQUIK_API_KEY is not set"],
        )
        write_json(cache_file, payload)
        return payload

    backend_query = build_backend_query(username, args.query, args.window_days)
    try:
        response_payload = fetch_xquik(api_key, backend_query, args.timeout, args.limit)
        posts, discarded_author_count = extract_posts(response_payload, args.limit, username)
        if discarded_author_count:
            warnings.append(
                f"discarded {discarded_author_count} post(s) not authored by {username}"
            )
        if not posts:
            warnings.append("Xquik returned no usable target-authored posts")
        payload = base_payload(
            username=username,
            query=args.query,
            window_days=args.window_days,
            status="completed",
            source=SOURCE_XQUIK,
            posts=posts,
            warnings=warnings,
        )
    except TimeoutError as exc:
        payload = base_payload(
            username=username,
            query=args.query,
            window_days=args.window_days,
            status="failed",
            source=SOURCE_XQUIK,
            warnings=[f"timeout after {args.timeout}s: {exc}"],
        )
    except urllib.error.URLError as exc:
        payload = base_payload(
            username=username,
            query=args.query,
            window_days=args.window_days,
            status="failed",
            source=SOURCE_XQUIK,
            warnings=[f"xquik request failed: {exc}"],
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = base_payload(
            username=username,
            query=args.query,
            window_days=args.window_days,
            status="failed",
            source=SOURCE_XQUIK,
            warnings=[f"xquik response error: {exc}"],
        )

    try:
        write_json(cache_file, payload)
    except OSError as exc:
        payload["warnings"].append(f"cache write failed: {exc}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Narrow X-only recent activity evidence collector for XAUUSD lead enrichment.",
    )
    parser.add_argument("--username", required=True, help="X username or handle, with or without @.")
    parser.add_argument("--query", required=True, help="Human-readable research query for output/audit.")
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--cache-dir", type=Path, default=Path("/home/hermesads/xauusd-leads/research-cache"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--emit", choices=["json"], default="json")
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = run(args)
    except Exception as exc:  # Last-resort guard: never crash the pipeline.
        payload = base_payload(
            username=getattr(args, "username", ""),
            query=getattr(args, "query", ""),
            window_days=getattr(args, "window_days", 30),
            status="failed",
            source=SOURCE_NONE,
            warnings=[f"unexpected failure: {type(exc).__name__}: {exc}"],
        )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
