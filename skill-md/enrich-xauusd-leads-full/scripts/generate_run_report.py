#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


SCHEMA_VERSION = "pipeline-run-report/v1"
DEFAULT_PIPELINE_VERSION = "phase-3d"


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


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_id_from_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_leads(payload: Any) -> list[dict[str, Any]]:
    leads = payload.get("leads") if isinstance(payload, dict) else payload
    if not isinstance(leads, list):
        return []
    return [lead for lead in leads if isinstance(lead, dict)]


def first_value(record: dict[str, Any], *keys: str) -> Any:
    normalized = {str(key).strip().lower().replace(" ", "_"): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(str(key).strip().lower().replace(" ", "_"))
        if value not in (None, ""):
            return value
    return None


def coerce_score(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def score_stats(scores: list[float]) -> tuple[float, float]:
    if not scores:
        return 0, 0
    return round(sum(scores) / len(scores), 2), round(float(statistics.median(scores)), 2)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [
            {key: str(value or "") for key, value in row.items() if key is not None}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    return fieldnames, rows


def normalize_metrics(normalized_payload: dict[str, Any], warnings: list[str]) -> dict[str, int]:
    raw_rows = int(normalized_payload.get("raw_row_count") or 0)
    unique_users = int(normalized_payload.get("unique_user_count") or normalized_payload.get("lead_count") or 0)
    if not raw_rows:
        warnings.append("normalize.raw_rows_missing_or_zero")
    if not unique_users:
        warnings.append("normalize.unique_users_missing_or_zero")
    return {
        "raw_rows": raw_rows,
        "unique_users": unique_users,
        "duplicates_removed": max(0, raw_rows - unique_users),
    }


def qualification_metrics(
    *,
    unique_users: int,
    enriched_leads: list[dict[str, Any]],
    csv_rows: list[dict[str, str]],
    warnings: list[str],
) -> dict[str, Any]:
    qualified = len(csv_rows)
    rejected = max(0, unique_users - qualified) if unique_users else 0
    if unique_users and qualified > unique_users:
        warnings.append("qualification.qualified_exceeds_unique_users")

    scores = [
        score
        for score in (
            coerce_score(first_value(lead, "score_fit", "score fit", "score"))
            for lead in enriched_leads
        )
        if score is not None
    ]
    if not scores:
        scores = [
            score
            for score in (coerce_score(row.get("Score fit")) for row in csv_rows)
            if score is not None
        ]
        if scores:
            warnings.append("qualification.score_metrics_from_csv_only")
    if not scores:
        warnings.append("qualification.no_scores_found")

    average_score, median_score = score_stats(scores)
    return {
        "qualified": qualified,
        "rejected": rejected,
        "average_score": average_score,
        "median_score": median_score,
    }


def recent_x_metrics(
    *,
    enriched_leads: list[dict[str, Any]],
    recent_x_payload: Optional[dict[str, Any]],
) -> dict[str, int]:
    if recent_x_payload:
        status = str(recent_x_payload.get("status") or "").strip().lower()
        return {
            "attempted": 1 if status in {"completed", "failed", "skipped"} else 0,
            "completed": 1 if status == "completed" else 0,
            "failed": 1 if status == "failed" else 0,
            "skipped": 1 if status == "skipped" else 0,
            "cache_hits": 1 if bool(recent_x_payload.get("cache_hit")) else 0,
        }

    completed = sum(1 for lead in enriched_leads if lead.get("recent_x_status") == "completed")
    failed = sum(1 for lead in enriched_leads if lead.get("recent_x_status") == "failed")
    cache_hits = sum(1 for lead in enriched_leads if bool(lead.get("recent_x_cache_hit")))
    return {
        "attempted": completed + failed,
        "completed": completed,
        "failed": failed,
        "skipped": 0,
        "cache_hits": cache_hits,
    }


def google_sheet_metrics(payload: Optional[dict[str, Any]]) -> dict[str, Optional[int]]:
    if not payload:
        return {
            "rows_written": None,
            "duplicates_skipped": None,
        }
    return {
        "rows_written": int(payload.get("rows_written") or 0),
        "duplicates_skipped": int(payload.get("duplicates_skipped") or 0),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    finished_at = parse_timestamp(args.finished_at) or utc_now()
    started_at = parse_timestamp(args.started_at) or finished_at
    duration_seconds = max(0, int((finished_at - started_at).total_seconds()))
    run_id = args.run_id or run_id_from_time(finished_at)

    try:
        normalized_payload = read_json(args.normalized_json)
        enriched_payload = read_json(args.enriched_json)
        _, csv_rows = read_csv_rows(args.csv)
    except (OSError, json.JSONDecodeError, csv.Error) as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "started_at": isoformat_utc(started_at),
            "finished_at": isoformat_utc(finished_at),
            "duration_seconds": duration_seconds,
            "pipeline_version": args.pipeline_version,
            "input": {"raw_csv": str(args.raw_csv)},
            "warnings": [f"artifact_read_failed: {exc}"],
            "status": "failed",
        }

    normalized = normalize_metrics(normalized_payload if isinstance(normalized_payload, dict) else {}, warnings)
    enriched_leads = extract_leads(enriched_payload)
    qualification = qualification_metrics(
        unique_users=normalized["unique_users"],
        enriched_leads=enriched_leads,
        csv_rows=csv_rows,
        warnings=warnings,
    )

    recent_x_payload = None
    if args.recent_x_json:
        try:
            recent_x_payload = read_json(args.recent_x_json)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"recent_x_summary_unavailable: {exc}")

    google_sheet_payload = None
    if args.google_sheet_json:
        try:
            google_sheet_payload = read_json(args.google_sheet_json)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"google_sheet_sync_json_unavailable: {exc}")

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": isoformat_utc(started_at),
        "finished_at": isoformat_utc(finished_at),
        "duration_seconds": duration_seconds,
        "pipeline_version": args.pipeline_version,
        "input": {
            "raw_csv": str(args.raw_csv),
        },
        "normalize": normalized,
        "qualification": qualification,
        "recent_x": recent_x_metrics(
            enriched_leads=enriched_leads,
            recent_x_payload=recent_x_payload if isinstance(recent_x_payload, dict) else None,
        ),
        "google_sheet": google_sheet_metrics(
            google_sheet_payload if isinstance(google_sheet_payload, dict) else None
        ),
        "outputs": {
            "normalized_json": str(args.normalized_json),
            "enriched_json": str(args.enriched_json),
            "csv": str(args.csv),
        },
        "warnings": warnings,
        "status": "completed",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with AtomicTextWriter(path) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a machine-readable XAUUSD lead pipeline run report.",
    )
    parser.add_argument("--raw-csv", type=Path, default=Path("raw_leads.csv"))
    parser.add_argument("--normalized-json", type=Path, default=Path("normalized_leads.json"))
    parser.add_argument("--enriched-json", type=Path, default=Path("enriched_leads.normalized.json"))
    parser.add_argument("--csv", type=Path, default=Path("enriched_leads.csv"))
    parser.add_argument("--google-sheet-json", type=Path)
    parser.add_argument("--recent-x-json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("run_report.json"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--finished-at", default="")
    parser.add_argument("--pipeline-version", default=DEFAULT_PIPELINE_VERSION)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    report = build_report(args)
    try:
        write_json(args.output, report)
    except OSError as exc:
        report["status"] = "failed"
        report.setdefault("warnings", []).append(f"report_write_failed: {exc}")
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if report.get("status") != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
