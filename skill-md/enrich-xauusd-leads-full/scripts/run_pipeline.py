#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


SCHEMA_VERSION = "xauusd-pipeline-orchestrator/v1"
DEFAULT_HERMES_BIN = "/opt/hermes-ads/venvs/hermes/bin/hermes"
DEFAULT_HERMES_HOME = "/opt/hermes-ads/hermes-home"
DEFAULT_SKILL = "enrich-xauusd-leads-full"
DEFAULT_PIPELINE_VERSION = "phase-3e"


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


def run_id_from_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def safe_tail(text: str, limit: int = 600) -> str:
    value = (text or "").strip()
    return value[-limit:] if len(value) > limit else value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with AtomicTextWriter(path) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_json_stdout(stdout: str) -> Optional[dict[str, Any]]:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def command_for_summary(command: list[str]) -> list[str]:
    return [str(part) for part in command]


def resolve_artifact_paths(args: argparse.Namespace, work_dir: Path) -> None:
    for attr in (
        "raw_csv",
        "normalized_json",
        "enriched_json",
        "csv",
        "google_sheet_json",
        "run_report",
        "github_sync_json",
    ):
        path = getattr(args, attr)
        if not path.is_absolute():
            setattr(args, attr, work_dir / path)


def skipped_step(name: str, *, fatal: bool = False, reason: str = "") -> dict[str, Any]:
    now = utc_now()
    step: dict[str, Any] = {
        "name": name,
        "status": "skipped",
        "fatal": fatal,
        "returncode": None,
        "command": [],
        "started_at": isoformat_utc(now),
        "finished_at": isoformat_utc(now),
        "duration_seconds": 0,
    }
    if reason:
        step["reason"] = reason
    return step


def run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: Optional[dict[str, str]] = None,
    timeout: Optional[int] = None,
    fatal: bool = True,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    started_at = utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        finished_at = utc_now()
        status = "completed" if completed.returncode == 0 else "failed"
        step = {
            "name": name,
            "status": status,
            "fatal": fatal,
            "returncode": completed.returncode,
            "command": command_for_summary(command),
            "started_at": isoformat_utc(started_at),
            "finished_at": isoformat_utc(finished_at),
            "duration_seconds": max(0, int((finished_at - started_at).total_seconds())),
        }
        if completed.returncode != 0:
            step["error"] = safe_tail(completed.stderr or completed.stdout)
        return step, completed
    except subprocess.TimeoutExpired as exc:
        finished_at = utc_now()
        step = {
            "name": name,
            "status": "failed",
            "fatal": fatal,
            "returncode": None,
            "command": command_for_summary(command),
            "started_at": isoformat_utc(started_at),
            "finished_at": isoformat_utc(finished_at),
            "duration_seconds": max(0, int((finished_at - started_at).total_seconds())),
            "error": f"timeout after {timeout}s: {safe_tail(str(exc))}",
        }
        completed = subprocess.CompletedProcess(command, returncode=124, stdout="", stderr=str(exc))
        return step, completed
    except OSError as exc:
        finished_at = utc_now()
        step = {
            "name": name,
            "status": "failed",
            "fatal": fatal,
            "returncode": None,
            "command": command_for_summary(command),
            "started_at": isoformat_utc(started_at),
            "finished_at": isoformat_utc(finished_at),
            "duration_seconds": max(0, int((finished_at - started_at).total_seconds())),
            "error": str(exc),
        }
        completed = subprocess.CompletedProcess(command, returncode=127, stdout="", stderr=str(exc))
        return step, completed


def hermes_prompt(args: argparse.Namespace) -> str:
    return (
        "Run Enrich_XAUUSD_Leads_Full in orchestrator mode. "
        f"Read normalized leads from {args.normalized_json} once. "
        f"Produce exactly one enriched JSON file at {args.enriched_json}. "
        "Do not call normalize. "
        "Do not call scripts/enrich_xauusd_leads.py write. "
        "Do not inspect, create, or write the final CSV. "
        "Do not call scripts/sync_google_sheet.py. "
        "Do not call scripts/generate_run_report.py. "
        "Do not sync Google Sheets. "
        "Do not ask the user to edit JSON. "
        "Ensure every kept lead with score_fit >= 7 has non-empty name, username, score_fit, first_line, and hook. "
        "If source name is blank but username exists, set name to the @username display handle. "
        "If username is blank, reject the lead with score_fit <= 6. "
        "If first_line or hook cannot be produced from evidence, reject the lead with score_fit <= 6. "
        "Reject malformed leads instead of leaving missing fields for the writer to catch. "
        "Apply the current strict scoring, Recent X Activity, safety, and CSV-only evidence rules."
    )


def build_summary(
    *,
    args: argparse.Namespace,
    started_at: datetime,
    finished_at: datetime,
    steps: list[dict[str, Any]],
    google_payload: Optional[dict[str, Any]],
    run_report_payload: Optional[dict[str, Any]],
    github_payload: Optional[dict[str, Any]],
) -> dict[str, Any]:
    fatal_failed = any(step["status"] == "failed" and step.get("fatal") for step in steps)
    nonfatal_failed = any(step["status"] == "failed" and not step.get("fatal") for step in steps)
    if fatal_failed:
        status = "failed"
    elif nonfatal_failed:
        status = "completed_with_warnings"
    else:
        status = "completed"

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_id": args.run_id,
        "started_at": isoformat_utc(started_at),
        "finished_at": isoformat_utc(finished_at),
        "duration_seconds": max(0, int((finished_at - started_at).total_seconds())),
        "steps": steps,
        "outputs": {
            "normalized_json": str(args.normalized_json),
            "enriched_json": str(args.enriched_json),
            "csv": str(args.csv),
            "google_sheet_sync": str(args.google_sheet_json),
            "run_report": str(args.run_report),
            "github_sync": str(args.github_sync_json),
        },
    }
    if google_payload is not None:
        summary["google_sheet"] = {
            "status": google_payload.get("status"),
            "rows_written": google_payload.get("rows_written"),
            "duplicates_skipped": google_payload.get("duplicates_skipped"),
            "warnings": google_payload.get("warnings", []),
        }
    if run_report_payload is not None:
        summary["run_report"] = {
            "status": run_report_payload.get("status"),
            "schema_version": run_report_payload.get("schema_version"),
        }
    if github_payload is not None:
        summary["github_sync"] = {
            "status": github_payload.get("status"),
            "commit_created": github_payload.get("commit_created"),
            "commit_sha": github_payload.get("commit_sha"),
            "pushed": github_payload.get("pushed"),
            "warnings": github_payload.get("warnings", []),
        }
        if github_payload.get("error"):
            summary["github_sync"]["error"] = github_payload.get("error")
    return summary


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    if not args.run_id:
        args.run_id = run_id_from_time(started_at)

    scripts = script_dir()
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir = work_dir
    resolve_artifact_paths(args, work_dir)

    env = os.environ.copy()
    env["HERMES_HOME"] = args.hermes_home

    steps: list[dict[str, Any]] = []
    google_payload: Optional[dict[str, Any]] = None
    run_report_payload: Optional[dict[str, Any]] = None
    github_payload: Optional[dict[str, Any]] = None

    normalize_cmd = [
        sys.executable,
        str(scripts / "enrich_xauusd_leads.py"),
        "normalize",
        str(args.raw_csv),
        "--output",
        str(args.normalized_json),
    ]
    step, completed = run_command(
        name="normalize",
        command=normalize_cmd,
        cwd=work_dir,
        fatal=True,
        timeout=args.step_timeout,
    )
    steps.append(step)
    if completed.returncode != 0:
        return finish_with_report(args, started_at, steps, google_payload, run_report_payload, github_payload, work_dir)

    hermes_cmd = [
        args.hermes_bin,
        "chat",
        "--skills",
        args.skill,
        "--yolo",
        "-q",
        hermes_prompt(args),
    ]
    step, completed = run_command(
        name="hermes",
        command=hermes_cmd,
        cwd=work_dir,
        env=env,
        fatal=True,
        timeout=args.hermes_timeout,
    )
    steps.append(step)
    if completed.returncode != 0:
        return finish_with_report(args, started_at, steps, google_payload, run_report_payload, github_payload, work_dir)

    validate_cmd = [
        sys.executable,
        str(scripts / "enrich_xauusd_leads.py"),
        "validate",
        "--input",
        str(args.enriched_json),
    ]
    step, completed = run_command(
        name="validate_enriched_json",
        command=validate_cmd,
        cwd=work_dir,
        fatal=True,
        timeout=args.step_timeout,
    )
    steps.append(step)
    if completed.returncode != 0:
        return finish_with_report(args, started_at, steps, google_payload, run_report_payload, github_payload, work_dir)

    write_cmd = [
        sys.executable,
        str(scripts / "enrich_xauusd_leads.py"),
        "write",
        "--input",
        str(args.enriched_json),
        "--output",
        str(args.csv),
    ]
    step, completed = run_command(
        name="write_csv",
        command=write_cmd,
        cwd=work_dir,
        fatal=True,
        timeout=args.step_timeout,
    )
    steps.append(step)
    if completed.returncode != 0:
        return finish_with_report(args, started_at, steps, google_payload, run_report_payload, github_payload, work_dir)

    google_cmd = [
        sys.executable,
        str(scripts / "sync_google_sheet.py"),
        str(args.csv),
    ]
    step, completed = run_command(
        name="google_sheet",
        command=google_cmd,
        cwd=work_dir,
        fatal=False,
        timeout=args.google_timeout,
    )
    google_payload = parse_json_stdout(completed.stdout)
    if google_payload is None:
        google_payload = {
            "schema_version": "google-sheets-sync/v1",
            "status": "failed",
            "rows_read": 0,
            "rows_written": 0,
            "duplicates_skipped": 0,
            "sheet": "",
            "warnings": [],
            "error": step.get("error", "invalid_google_sheet_json"),
        }
    try:
        write_json(args.google_sheet_json, google_payload)
    except OSError as exc:
        step["status"] = "failed"
        step["error"] = f"google_sheet_json_write_failed: {exc}"
    if google_payload.get("status") != "completed":
        step["status"] = "failed"
        step.setdefault("error", str(google_payload.get("error", "google_sheet_sync_failed")))
    steps.append(step)

    return finish_with_report(args, started_at, steps, google_payload, run_report_payload, github_payload, work_dir)


def finish_with_report(
    args: argparse.Namespace,
    started_at: datetime,
    steps: list[dict[str, Any]],
    google_payload: Optional[dict[str, Any]],
    run_report_payload: Optional[dict[str, Any]],
    github_payload: Optional[dict[str, Any]],
    work_dir: Path,
) -> dict[str, Any]:
    scripts = script_dir()
    finished_for_report = utc_now()
    report_cmd = [
        sys.executable,
        str(scripts / "generate_run_report.py"),
        "--raw-csv",
        str(args.raw_csv),
        "--normalized-json",
        str(args.normalized_json),
        "--enriched-json",
        str(args.enriched_json),
        "--csv",
        str(args.csv),
        "--google-sheet-json",
        str(args.google_sheet_json),
        "--output",
        str(args.run_report),
        "--run-id",
        args.run_id,
        "--started-at",
        isoformat_utc(started_at),
        "--finished-at",
        isoformat_utc(finished_for_report),
        "--pipeline-version",
        args.pipeline_version,
    ]
    step, completed = run_command(
        name="run_report",
        command=report_cmd,
        cwd=work_dir,
        fatal=False,
        timeout=args.step_timeout,
    )
    run_report_payload = parse_json_stdout(completed.stdout)
    if run_report_payload is None and completed.returncode != 0:
        step.setdefault("error", safe_tail(completed.stderr or completed.stdout))
    steps.append(step)

    if args.skip_github_sync:
        github_payload = {
            "schema_version": "github-sync/v1",
            "status": "skipped",
            "files_copied": [],
            "commit_created": False,
            "commit_sha": "",
            "pushed": False,
            "warnings": ["github_sync_skipped_by_cli"],
        }
        step = skipped_step("github_sync", fatal=False, reason="skip_github_sync")
        try:
            write_json(args.github_sync_json, github_payload)
        except OSError as exc:
            step["status"] = "failed"
            step["error"] = f"github_sync_json_write_failed: {exc}"
        steps.append(step)
    else:
        github_cmd = [
            sys.executable,
            str(scripts / "sync_github.py"),
            "--csv",
            str(args.csv),
            "--run-report",
            str(args.run_report),
            "--google-sheet-json",
            str(args.google_sheet_json),
            "--run-id",
            args.run_id,
            "--repo-dir",
            args.github_repo_dir,
            "--output-dir",
            args.github_output_dir,
        ]
        step, completed = run_command(
            name="github_sync",
            command=github_cmd,
            cwd=work_dir,
            fatal=False,
            timeout=args.step_timeout,
        )
        github_payload = parse_json_stdout(completed.stdout)
        if github_payload is None:
            github_payload = {
                "schema_version": "github-sync/v1",
                "status": "failed",
                "files_copied": [],
                "commit_created": False,
                "commit_sha": "",
                "pushed": False,
                "warnings": [],
                "error": step.get("error", "invalid_github_sync_json"),
            }
        try:
            write_json(args.github_sync_json, github_payload)
        except OSError as exc:
            step["status"] = "failed"
            step["error"] = f"github_sync_json_write_failed: {exc}"
        if github_payload.get("status") != "completed":
            step["status"] = "failed"
            step.setdefault("error", str(github_payload.get("error", "github_sync_failed")))
        steps.append(step)

    return build_summary(
        args=args,
        started_at=started_at,
        finished_at=utc_now(),
        steps=steps,
        google_payload=google_payload,
        run_report_payload=run_report_payload,
        github_payload=github_payload,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the XAUUSD lead enrichment pipeline from raw CSV to Sheets sync and run report.",
    )
    parser.add_argument("--work-dir", type=Path, default=Path.cwd())
    parser.add_argument("--raw-csv", type=Path, default=Path("raw_leads.csv"))
    parser.add_argument("--normalized-json", type=Path, default=Path("normalized_leads.json"))
    parser.add_argument("--enriched-json", type=Path, default=Path("enriched_leads.normalized.json"))
    parser.add_argument("--csv", type=Path, default=Path("enriched_leads.csv"))
    parser.add_argument("--google-sheet-json", type=Path, default=Path("google_sheet_sync.json"))
    parser.add_argument("--run-report", type=Path, default=Path("run_report.json"))
    parser.add_argument("--github-sync-json", type=Path, default=Path("github_sync.json"))
    parser.add_argument("--github-repo-dir", default=os.environ.get("GITHUB_SYNC_REPO_DIR", ""))
    parser.add_argument("--github-output-dir", default=os.environ.get("GITHUB_SYNC_OUTPUT_DIR", ""))
    parser.add_argument("--skip-github-sync", action="store_true")
    parser.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", DEFAULT_HERMES_BIN))
    parser.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", DEFAULT_HERMES_HOME))
    parser.add_argument("--skill", default=DEFAULT_SKILL)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--pipeline-version", default=DEFAULT_PIPELINE_VERSION)
    parser.add_argument("--step-timeout", type=int, default=300)
    parser.add_argument("--hermes-timeout", type=int, default=1800)
    parser.add_argument("--google-timeout", type=int, default=300)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    summary = run_pipeline(args)
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if summary.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
