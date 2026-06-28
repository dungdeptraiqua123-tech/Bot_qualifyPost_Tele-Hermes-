#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any, Optional, TextIO


SCHEMA_VERSION = "apify-raw-fetch/v1"
APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_MAX_ITEMS = 800
DEFAULT_ACTOR_TIMEOUT_SECONDS = 900
DEFAULT_SEARCH_SORT = "Latest"
DEFAULT_TWEET_TYPE = "exclude_retweets"
DEFAULT_SOURCE_MODE = "search"
ALLOWED_TWEET_TYPES = [
    "all",
    "originals_only",
    "replies_only",
    "retweets_only",
    "exclude_replies",
    "exclude_retweets",
]

OUTPUT_COLUMNS = [
    "country",
    "handle",
    "display_name",
    "followers_estimate",
    "bio_snippet",
    "profile_url",
    "why_relevant",
    "niche",
    "source_urls",
    "discovered_at",
    "created_at",
]

COUNTRY_GROUPS = {
    "english": ["UK", "Canada", "Germany"],
    "europe": ["France", "Italy", "Poland"],
    "middle-east": ["UAE", "Saudi Arabia"],
}

COUNTRY_TERMS = {
    "UK": ["UK", "United Kingdom", "London", "British"],
    "Canada": ["Canada", "Toronto", "Vancouver", "Canadian"],
    "Germany": ["Germany", "Berlin", "Frankfurt", "German"],
    "France": ["France", "Paris", "French"],
    "Italy": ["Italy", "Milan", "Rome", "Italian"],
    "Poland": ["Poland", "Warsaw", "Polish"],
    "UAE": ["UAE", "Dubai", "Abu Dhabi"],
    "Saudi Arabia": ["Saudi Arabia", "Riyadh", "Jeddah", "Saudi"],
}

LANG_FILTERS = {
    "UK": "lang:en",
    "Canada": "lang:en",
    "Germany": "lang:en",
    "France": "lang:fr",
    "Italy": "lang:it",
    "Poland": "lang:pl",
    "UAE": "lang:ar",
    "Saudi Arabia": "lang:ar",
}

SEARCH_TERMS = [
    "XAUUSD",
    '"gold trading"',
    '"gold trader"',
    '"gold analysis"',
    '"forex gold"',
]


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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def base_payload(
    *,
    status: str,
    country_group: str,
    rows_written: int = 0,
    output_csv: str = "",
    warnings: Optional[list[str]] = None,
    error: str = "",
    planned_actor_inputs: Optional[list[dict[str, Any]]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "country_group": country_group,
        "rows_written": rows_written,
        "output_csv": output_csv,
        "warnings": warnings or [],
        "dry_run": dry_run,
    }
    if planned_actor_inputs is not None:
        payload["planned_actor_inputs"] = planned_actor_inputs
    if error:
        payload["error"] = error
    return payload


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\x00", "").split()).strip()


def countries_for_group(country_group: str) -> list[str]:
    if country_group == "all":
        return [country for group in ("english", "europe", "middle-east") for country in COUNTRY_GROUPS[group]]
    return COUNTRY_GROUPS[country_group]


def or_group(terms: list[str]) -> str:
    return "(" + " OR ".join(terms) + ")"


def build_search_query(country: str) -> str:
    country_terms = [f'"{term}"' if " " in term else term for term in COUNTRY_TERMS[country]]
    language = LANG_FILTERS.get(country, "")
    parts = [or_group(SEARCH_TERMS), or_group(country_terms)]
    if language:
        parts.append(language)
    return " ".join(parts)


def actor_input_for_country(args: argparse.Namespace, country: str, max_items: int) -> dict[str, Any]:
    return {
        "blue_verified_only": args.blue_verified_only,
        "verified_only": args.verified_only,
        "max_items": max_items,
        "min_likes": args.min_likes,
        "search_query": build_search_query(country),
        "search_sort": args.search_sort,
        "tweet_type": args.tweet_type,
        "source_mode": args.source_mode,
    }


def build_actor_inputs(args: argparse.Namespace) -> list[dict[str, Any]]:
    countries = countries_for_group(args.country_group)
    max_per_country = max(1, ceil(args.max_items / len(countries)))
    return [
        {
            "country": country,
            "actor_input": actor_input_for_country(args, country, max_per_country),
        }
        for country in countries
    ]


def request_json(method: str, url: str, token: str, payload: Optional[dict[str, Any]] = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"apify_http_{exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"apify_network_error: {exc.reason}") from exc
    return json.loads(raw) if raw else {}


def run_actor(token: str, actor_id: str, actor_input: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    encoded_actor_id = urllib.parse.quote(actor_id, safe="")
    start_url = f"{APIFY_BASE_URL}/acts/{encoded_actor_id}/runs"
    started = request_json("POST", start_url, token, actor_input)
    run = started.get("data") if isinstance(started, dict) else None
    if not isinstance(run, dict) or not run.get("id"):
        raise RuntimeError("actor_failed: missing_run_id")

    run_id = run["id"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status_url = f"{APIFY_BASE_URL}/actor-runs/{urllib.parse.quote(run_id, safe='')}"
        current = request_json("GET", status_url, token)
        run_data = current.get("data") if isinstance(current, dict) else None
        if not isinstance(run_data, dict):
            raise RuntimeError("actor_failed: invalid_run_status")
        status = str(run_data.get("status") or "")
        if status == "SUCCEEDED":
            return run_data
        if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            raise RuntimeError(f"actor_failed: {status.lower()}")
        time.sleep(5)
    raise RuntimeError("actor_failed: timeout")


def fetch_dataset_items(token: str, dataset_id: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"clean": "true", "format": "json", "limit": str(limit)})
    url = f"{APIFY_BASE_URL}/datasets/{urllib.parse.quote(dataset_id, safe='')}/items?{query}"
    payload = request_json("GET", url, token)
    if not isinstance(payload, list):
        raise RuntimeError("invalid_actor_output")
    return [item for item in payload if isinstance(item, dict)]


def nested_value(item: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = item
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return ""


def normalize_handle(value: Any) -> str:
    text = clean_cell(value)
    if text.startswith("@"):
        return text
    if text:
        return f"@{text}"
    return ""


def profile_url_for(handle: str, item: dict[str, Any]) -> str:
    url = clean_cell(
        nested_value(
            item,
            "user.profileUrl",
            "user.url",
            "author.profileUrl",
            "author.url",
            "profileUrl",
            "profile_url",
        )
    )
    if url:
        return url
    return f"https://x.com/{handle.lstrip('@')}" if handle else ""


def tweet_url_for(handle: str, item: dict[str, Any]) -> str:
    url = clean_cell(nested_value(item, "url", "tweetUrl", "tweet_url", "link"))
    if url:
        return url
    tweet_id = clean_cell(nested_value(item, "id", "tweetId", "tweet_id"))
    return f"https://x.com/{handle.lstrip('@')}/status/{tweet_id}" if handle and tweet_id else ""


def infer_niche(text: str, query: str) -> str:
    combined = f"{text} {query}".lower()
    if "xauusd" in combined:
        return "XAUUSD"
    if "gold" in combined and "forex" in combined:
        return "Forex gold"
    if "gold" in combined:
        return "Gold trading"
    return "Trading"


def item_to_row(item: dict[str, Any], *, country: str, query: str, discovered_at: str) -> Optional[dict[str, str]]:
    handle = normalize_handle(
        nested_value(
            item,
            "user.handle",
            "user.username",
            "author.handle",
            "author.username",
            "handle",
            "username",
            "screenName",
        )
    )
    if not handle:
        return None

    text = clean_cell(nested_value(item, "text", "fullText", "tweetText", "content", "body"))
    display_name = clean_cell(nested_value(item, "user.name", "author.name", "displayName", "name"))
    bio = clean_cell(
        nested_value(
            item,
            "user.description",
            "user.bio",
            "author.description",
            "author.bio",
            "bio",
            "description",
        )
    )
    followers = clean_cell(
        nested_value(
            item,
            "user.followersCount",
            "user.followers_count",
            "author.followersCount",
            "author.followers_count",
            "followersCount",
            "followers_count",
            "followers",
        )
    )
    tweet_url = tweet_url_for(handle, item)
    why = text[:280] if text else f"Matched query: {query}"
    return {
        "country": country,
        "handle": handle,
        "display_name": display_name or handle,
        "followers_estimate": followers,
        "bio_snippet": bio,
        "profile_url": profile_url_for(handle, item),
        "why_relevant": why,
        "niche": infer_niche(text, query),
        "source_urls": json.dumps([tweet_url] if tweet_url else [], ensure_ascii=False),
        "discovered_at": discovered_at,
        "created_at": clean_cell(nested_value(item, "createdAt", "created_at", "timestamp", "date")),
    }


def convert_items_to_rows(items: list[dict[str, Any]], *, country: str, query: str, discovered_at: str) -> tuple[list[dict[str, str]], int]:
    rows: list[dict[str, str]] = []
    skipped = 0
    for item in items:
        row = item_to_row(item, country=country, query=query, discovered_at=discovered_at)
        if row is None:
            skipped += 1
            continue
        rows.append(row)
    return rows, skipped


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with AtomicTextWriter(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_rows(args: argparse.Namespace, token: str, actor_id: str, planned_inputs: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    discovered_at = isoformat_utc(utc_now())

    for plan in planned_inputs:
        country = plan["country"]
        actor_input = plan["actor_input"]
        run_data = run_actor(token, actor_id, actor_input, args.actor_timeout)
        dataset_id = clean_cell(run_data.get("defaultDatasetId"))
        if not dataset_id:
            raise RuntimeError("actor_failed: missing_dataset_id")
        items = fetch_dataset_items(token, dataset_id, actor_input["max_items"])
        if not items:
            warnings.append(f"dataset_empty:{country}")
            continue
        converted, skipped = convert_items_to_rows(
            items,
            country=country,
            query=actor_input["search_query"],
            discovered_at=discovered_at,
        )
        if skipped:
            warnings.append(f"skipped_items_missing_handle:{country}:{skipped}")
        rows.extend(converted)
        if len(rows) >= args.max_items:
            rows = rows[: args.max_items]
            break

    if not rows:
        raise RuntimeError("dataset_empty")
    return rows, warnings


def run(args: argparse.Namespace) -> dict[str, Any]:
    actor_id = clean_cell(args.actor_id or os.environ.get("APIFY_ACTOR_ID", ""))
    token = clean_cell(os.environ.get("APIFY_TOKEN", ""))
    planned_inputs = build_actor_inputs(args)

    if args.dry_run:
        if args.write_dry_run_fixture:
            fixture_rows = [
                {
                    "country": planned_inputs[0]["country"],
                    "handle": "@example_gold_trader",
                    "display_name": "Example Gold Trader",
                    "followers_estimate": "1000",
                    "bio_snippet": "XAUUSD and gold trading notes.",
                    "profile_url": "https://x.com/example_gold_trader",
                    "why_relevant": "Dry-run fixture for XAUUSD search planning.",
                    "niche": "XAUUSD",
                    "source_urls": json.dumps(["https://x.com/example_gold_trader/status/1"]),
                    "discovered_at": isoformat_utc(utc_now()),
                    "created_at": "",
                }
            ]
            try:
                write_csv(args.output_csv, fixture_rows)
            except OSError as exc:
                return base_payload(
                    status="failed",
                    country_group=args.country_group,
                    output_csv=str(args.output_csv),
                    planned_actor_inputs=planned_inputs,
                    dry_run=True,
                    error=f"csv_write_failed: {exc}",
                )
            rows_written = len(fixture_rows)
        else:
            rows_written = 0
        return base_payload(
            status="completed",
            country_group=args.country_group,
            rows_written=rows_written,
            output_csv=str(args.output_csv),
            warnings=["dry_run_no_apify_call"],
            planned_actor_inputs=planned_inputs,
            dry_run=True,
        )

    if not token:
        return base_payload(status="failed", country_group=args.country_group, output_csv=str(args.output_csv), error="missing_APIFY_TOKEN")
    if not actor_id:
        return base_payload(status="failed", country_group=args.country_group, output_csv=str(args.output_csv), error="missing_APIFY_ACTOR_ID")

    try:
        rows, warnings = fetch_rows(args, token, actor_id, planned_inputs)
    except RuntimeError as exc:
        return base_payload(
            status="failed",
            country_group=args.country_group,
            output_csv=str(args.output_csv),
            error=str(exc),
        )

    try:
        write_csv(args.output_csv, rows)
    except OSError as exc:
        return base_payload(
            status="failed",
            country_group=args.country_group,
            output_csv=str(args.output_csv),
            warnings=warnings,
            error=f"csv_write_failed: {exc}",
        )

    return base_payload(
        status="completed",
        country_group=args.country_group,
        rows_written=len(rows),
        output_csv=str(args.output_csv),
        warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch raw XAUUSD lead candidates from Apify into raw_leads.csv.")
    parser.add_argument("--actor-id", default="", help="Apify actor id. Defaults to APIFY_ACTOR_ID.")
    parser.add_argument("--country-group", choices=["english", "europe", "middle-east", "all"], required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-dry-run-fixture", action="store_true")
    parser.add_argument("--blue-verified-only", action="store_true")
    parser.add_argument("--verified-only", action="store_true")
    parser.add_argument("--min-likes", type=int, default=0)
    parser.add_argument("--search-sort", default=DEFAULT_SEARCH_SORT)
    parser.add_argument("--tweet-type", choices=ALLOWED_TWEET_TYPES, default=DEFAULT_TWEET_TYPE)
    parser.add_argument("--source-mode", default=DEFAULT_SOURCE_MODE)
    parser.add_argument("--actor-timeout", type=int, default=DEFAULT_ACTOR_TIMEOUT_SECONDS)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    payload = run(args)
    emit(payload)
    if payload.get("status") != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
