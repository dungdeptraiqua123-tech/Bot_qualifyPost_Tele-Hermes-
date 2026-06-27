#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
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
    "username",
    "bio",
    "tweet_text",
    "profile_url",
    "location",
    "created_at",
    "country",
    "source_query",
]

HEADER_ALIASES = {
    "name": {"name", "full name", "display name", "author name"},
    "username": {
        "username",
        "user name",
        "handle",
        "screen name",
        "author username",
        "user",
    },
    "bio": {"bio", "biography", "description", "profile bio", "user bio"},
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
    },
    "location": {"location", "user location", "profile location"},
    "created_at": {"createdAt", "created at", "created_at", "date", "timestamp", "posted at"},
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
            normalized["username"] = normalize_username(
                normalized.get("username", ""),
                normalized.get("profile_url", ""),
            )
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


def normalized_payload(source: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "xauusd-leads-normalized/v1",
        "source_file": str(source),
        "lead_count": len(rows),
        "leads": rows,
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
    for index, record in enumerate(enriched_leads, start=1):
        try:
            converted = output_record(record, index)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if converted is not None:
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
    payload = normalized_payload(args.input, rows)
    if args.output == Path("-"):
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        write_json(args.output, payload)
        print(f"Normalized {len(rows)} leads: {args.output}")


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
