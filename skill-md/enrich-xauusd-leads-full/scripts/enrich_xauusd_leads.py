#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


OUTPUT_COLUMNS = [
    "Name",
    "Username X",
    "First-line cá nhân hóa",
    "Score fit",
    "Hook",
]

CANONICAL_FIELDS = [
    "name",
    "user_handle",
    "handle",
    "username",
    "bio",
    "tweet_text",
    "profile_url",
    "location",
    "created_at",
    "favorite_count",
    "followers_count",
    "country",
    "source_query",
]

HEADER_ALIASES = {
    "name": {"name", "full name", "display name", "author name", "user.name"},
    "user_handle": {
        "user.handle",
        "user handle",
        "userHandle",
        "author.handle",
        "author handle",
    },
    "handle": {"handle", "screen name", "twitter handle", "x handle"},
    "username": {
        "username",
        "user name",
        "author username",
        "user",
        "user.username",
        "user username",
    },
    "bio": {
        "bio",
        "biography",
        "description",
        "profile bio",
        "user bio",
        "user.description",
        "user description",
    },
    "tweet_text": {
        "tweet text",
        "tweet",
        "text",
        "post text",
        "recent post",
        "recent tweet",
        "content",
        "full text",
    },
    "profile_url": {
        "profile url",
        "profileURL",
        "profile",
        "url",
        "user url",
        "twitter url",
        "x url",
        "user.profileUrl",
        "user.profile_url",
    },
    "location": {"location", "user location", "profile location"},
    "created_at": {"createdAt", "created at", "created_at", "date", "timestamp", "posted at"},
    "favorite_count": {
        "favorite_count",
        "favorite count",
        "favoriteCount",
        "favorites",
        "likes",
        "like count",
        "likeCount",
    },
    "followers_count": {
        "followers_count",
        "followers count",
        "followersCount",
        "user.followersCount",
        "user followers count",
        "followers",
    },
    "country": {"country", "source country", "target country"},
    "source_query": {"source query", "query", "search query", "keyword", "apify query"},
}


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
        self.handle = os.fdopen(fd, "w", encoding="utf-8", newline="")
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


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\x00", "").split()).strip()


def normalize_username(username: str, profile_url: str = "") -> str:
    raw = clean_cell(username)
    if not raw and profile_url:
        match = re.search(r"(?:x|twitter)\.com/([^/?#\s]+)", profile_url, flags=re.IGNORECASE)
        if match:
            raw = match.group(1)
    raw = raw.strip()
    if raw.startswith("http"):
        match = re.search(r"(?:x|twitter)\.com/([^/?#\s]+)", raw, flags=re.IGNORECASE)
        raw = match.group(1) if match else raw
    raw = raw.lstrip("@")
    return f"@{raw}" if raw else ""


def handle_key(username: str) -> str:
    return clean_cell(username).lstrip("@").lower()


def choose_username(row: dict[str, str]) -> str:
    for key in ("user_handle", "handle", "username"):
        username = normalize_username(row.get(key, ""))
        if username:
            return username
    return normalize_username("", row.get("profile_url", ""))


def coerce_int(value: Any, default: int = 0) -> int:
    text = clean_cell(value)
    if not text:
        return default
    text = text.replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return default


def parse_created_at(value: str) -> float:
    text = clean_cell(value)
    if not text:
        return float("-inf")
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return float("-inf")


def build_header_map(fieldnames: Optional[list[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    normalized_to_original = {
        normalize_key(header): header for header in (fieldnames or []) if header is not None
    }
    for canonical, aliases in HEADER_ALIASES.items():
        candidates = {normalize_key(canonical), *(normalize_key(alias) for alias in aliases)}
        for candidate in candidates:
            original = normalized_to_original.get(candidate)
            if original is not None:
                result[canonical] = original
                break
    return result


def read_raw_leads(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Input CSV not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit(f"Input CSV has no header row: {path}")
        header_map = build_header_map(reader.fieldnames)
        rows: list[dict[str, Any]] = []
        for csv_row_number, raw in enumerate(reader, start=2):
            normalized = {
                field: clean_cell(raw.get(header_map.get(field, ""), ""))
                for field in CANONICAL_FIELDS
            }
            normalized["username"] = choose_username(normalized)
            if not any(normalized.values()):
                continue
            rows.append(
                {
                    "row_id": len(rows) + 1,
                    "csv_row_number": csv_row_number,
                    **normalized,
                }
            )
    return rows


def tweet_from_row(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    text = clean_cell(row.get("tweet_text"))
    if not text:
        return None
    return {
        "text": text,
        "created_at": clean_cell(row.get("created_at")),
        "favorite_count": coerce_int(row.get("favorite_count")),
        "csv_row_number": row.get("csv_row_number"),
    }


def merge_source_value(existing: str, new_value: str) -> str:
    current = [part.strip() for part in clean_cell(existing).split("|") if part.strip()]
    new_parts = [part.strip() for part in clean_cell(new_value).split("|") if part.strip()]
    seen = {part.lower() for part in current}
    for part in new_parts:
        if part.lower() not in seen:
            current.append(part)
            seen.add(part.lower())
    return " | ".join(current)


def dedupe_tweets(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_text: dict[str, dict[str, Any]] = {}
    for tweet in tweets:
        text_key = clean_cell(tweet.get("text")).lower()
        if not text_key:
            continue
        current = best_by_text.get(text_key)
        if current is None:
            best_by_text[text_key] = tweet
            continue
        tweet_sort = (parse_created_at(tweet.get("created_at", "")), coerce_int(tweet.get("favorite_count")))
        current_sort = (
            parse_created_at(current.get("created_at", "")),
            coerce_int(current.get("favorite_count")),
        )
        if tweet_sort > current_sort:
            best_by_text[text_key] = tweet
    return sorted(
        best_by_text.values(),
        key=lambda item: (
            parse_created_at(item.get("created_at", "")),
            coerce_int(item.get("favorite_count")),
        ),
        reverse=True,
    )[:3]


def merge_raw_rows_by_username(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    no_handle_rows: list[dict[str, Any]] = []

    for row in rows:
        username = normalize_username(row.get("username", ""), row.get("profile_url", ""))
        key = handle_key(username)
        if not key:
            no_handle_rows.append(row)
            continue

        existing = grouped.get(key)
        if existing is None:
            existing = {
                "row_id": 0,
                "csv_row_numbers": [],
                "raw_row_count": 0,
                "name": "",
                "username": username,
                "bio": "",
                "profile_url": "",
                "location": "",
                "followers_count": "",
                "country": "",
                "source_query": "",
                "recent_tweets": [],
            }
            grouped[key] = existing

        existing["csv_row_numbers"].append(row.get("csv_row_number"))
        existing["raw_row_count"] += 1
        for field in ("name", "bio", "profile_url", "location", "followers_count", "country"):
            if not existing.get(field) and row.get(field):
                existing[field] = row[field]
        existing["source_query"] = merge_source_value(
            existing.get("source_query", ""),
            row.get("source_query", ""),
        )
        tweet = tweet_from_row(row)
        if tweet:
            existing["recent_tweets"].append(tweet)

    leads = list(grouped.values())
    for row in no_handle_rows:
        tweet = tweet_from_row(row)
        lead = {
            "row_id": 0,
            "csv_row_numbers": [row.get("csv_row_number")],
            "raw_row_count": 1,
            "name": row.get("name", ""),
            "username": "",
            "bio": row.get("bio", ""),
            "profile_url": row.get("profile_url", ""),
            "location": row.get("location", ""),
            "followers_count": row.get("followers_count", ""),
            "country": row.get("country", ""),
            "source_query": row.get("source_query", ""),
            "recent_tweets": [tweet] if tweet else [],
        }
        leads.append(lead)

    for index, lead in enumerate(leads, start=1):
        lead["row_id"] = index
        lead["recent_tweets"] = dedupe_tweets(lead.get("recent_tweets", []))

    return leads


def write_json(path: Path, payload: Any) -> None:
    with AtomicTextWriter(path) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Input JSON not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def normalized_payload(source: Path, raw_rows: list[dict[str, Any]], leads: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "xauusd-leads-normalized/v1",
        "source_file": str(source),
        "raw_row_count": len(raw_rows),
        "lead_count": len(leads),
        "unique_user_count": len(leads),
        "leads": leads,
    }


def extract_leads_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        leads = payload.get("leads")
    else:
        leads = payload
    if not isinstance(leads, list):
        raise SystemExit("Enriched input JSON must be a list or an object with a 'leads' list.")
    for index, item in enumerate(leads, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"Enriched lead #{index} must be an object.")
    return leads


def value_from(record: dict[str, Any], *keys: str) -> Any:
    by_normalized_key = {normalize_key(key): value for key, value in record.items()}
    for key in keys:
        value = by_normalized_key.get(normalize_key(key))
        if value is not None:
            return value
    return None


def coerce_score(value: Any, *, row_label: str) -> int:
    if value is None or value == "":
        raise ValueError(f"{row_label}: score is required")
    try:
        score = int(float(str(value).strip()))
    except ValueError as exc:
        raise ValueError(f"{row_label}: score must be a number, got {value!r}") from exc
    if score < 1 or score > 10:
        raise ValueError(f"{row_label}: score must be between 1 and 10, got {score}")
    return score


def output_record(record: dict[str, Any], index: int) -> Optional[dict[str, str]]:
    row_id = value_from(record, "row_id", "id")
    row_label = f"lead #{index}" if row_id in {None, ""} else f"row_id={row_id}"

    score = coerce_score(
        value_from(record, "score_fit", "score fit", "score"),
        row_label=row_label,
    )
    if score < 7:
        return None

    name = clean_cell(value_from(record, "Name", "name"))
    username = normalize_username(
        clean_cell(value_from(record, "Username X", "username_x", "username", "handle")),
        clean_cell(value_from(record, "profile_url", "profile url")),
    )
    first_line = clean_cell(
        value_from(
            record,
            "First-line cá nhân hóa",
            "first_line",
            "first line",
            "personalized_first_line",
            "personalized first line",
        )
    )
    hook = clean_cell(value_from(record, "Hook", "hook"))

    missing = []
    if not name:
        missing.append("Name/name")
    if not username:
        missing.append("Username X/username")
    if not first_line:
        missing.append("First-line cá nhân hóa/first_line")
    if not hook:
        missing.append("Hook/hook")
    if missing:
        raise ValueError(f"{row_label}: kept lead missing {', '.join(missing)}")

    return {
        "Name": name,
        "Username X": username,
        "First-line cá nhân hóa": first_line,
        "Score fit": str(score),
        "Hook": hook,
    }


def build_output_records(enriched_leads: list[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    errors: list[str] = []
    seen_usernames: set[str] = set()
    for index, record in enumerate(enriched_leads, start=1):
        try:
            converted = output_record(record, index)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if converted is not None:
            username_key = handle_key(converted.get("Username X", ""))
            if username_key and username_key in seen_usernames:
                continue
            if username_key:
                seen_usernames.add(username_key)
            output.append(converted)
    if errors:
        raise SystemExit("Cannot write enriched CSV:\n- " + "\n- ".join(errors))
    return output


def write_enriched_csv(path: Path, records: list[dict[str, str]]) -> None:
    with AtomicTextWriter(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def cmd_normalize(args: argparse.Namespace) -> None:
    rows = read_raw_leads(args.input)
    leads = merge_raw_rows_by_username(rows)
    payload = normalized_payload(args.input, rows, leads)
    if args.output == Path("-"):
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        write_json(args.output, payload)
        print(f"Normalized {len(rows)} raw rows into {len(leads)} unique X accounts: {args.output}")


def cmd_write(args: argparse.Namespace) -> None:
    payload = read_json(args.input)
    enriched_leads = extract_leads_payload(payload)
    records = build_output_records(enriched_leads)
    write_enriched_csv(args.output, records)
    print(f"Wrote {len(records)} enriched leads: {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic CSV utilities for XAUUSD X/Twitter lead enrichment.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser(
        "normalize",
        help="Read raw_leads.csv, normalize headers, validate rows, and write normalized JSON.",
    )
    normalize.add_argument("input", type=Path, nargs="?", default=Path("raw_leads.csv"))
    normalize.add_argument("--output", type=Path, default=Path("normalized_leads.json"))
    normalize.set_defaults(func=cmd_normalize)

    write = subparsers.add_parser(
        "write",
        help="Validate Hermes-produced enriched JSON and write enriched_leads.csv.",
    )
    write.add_argument("--input", type=Path, default=Path("enriched_leads.normalized.json"))
    write.add_argument("--output", type=Path, default=Path("enriched_leads.csv"))
    write.set_defaults(func=cmd_write)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
