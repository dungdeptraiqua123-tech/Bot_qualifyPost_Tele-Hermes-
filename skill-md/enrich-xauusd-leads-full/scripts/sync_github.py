#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


SCHEMA_VERSION = "github-sync/v1"
DEFAULT_OUTPUT_DIR = "xauusd-leads"


class AtomicCopy:
    def __init__(self, source: Path, destination: Path) -> None:
        self.source = source
        self.destination = destination
        self.tmp_path: Optional[Path] = None
        self.handle: Optional[TextIO] = None

    def copy(self) -> None:
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.destination.name}.",
            suffix=".tmp",
            dir=str(self.destination.parent),
        )
        os.close(fd)
        self.tmp_path = Path(tmp_name)
        try:
            shutil.copy2(self.source, self.tmp_path)
            self.tmp_path.replace(self.destination)
        except Exception:
            try:
                self.tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise


@dataclass(frozen=True)
class Artifact:
    label: str
    source: Path
    destination: Path
    relative_destination: str


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_run_id() -> str:
    return utc_now().strftime("%Y%m%d-%H%M%S")


def base_payload(
    *,
    status: str,
    files_copied: Optional[list[str]] = None,
    commit_created: bool = False,
    commit_sha: str = "",
    pushed: bool = False,
    warnings: Optional[list[str]] = None,
    error: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "files_copied": files_copied or [],
        "commit_created": commit_created,
        "commit_sha": commit_sha,
        "pushed": pushed,
        "warnings": warnings or [],
        "dry_run": dry_run,
    }
    if error:
        payload["error"] = error
    return payload


def safe_tail(text: str, limit: int = 800) -> str:
    value = str(text or "").strip()
    return value[-limit:] if len(value) > limit else value


def run_git(repo_dir: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        text=True,
        capture_output=True,
        check=False,
    )


def require_git_success(repo_dir: Path, args: list[str], error_prefix: str) -> subprocess.CompletedProcess[str]:
    completed = run_git(repo_dir, args)
    if completed.returncode != 0:
        detail = safe_tail(completed.stderr or completed.stdout)
        raise RuntimeError(f"{error_prefix}: {detail}")
    return completed


def repo_relative_path(repo_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path_outside_repo: {path}") from exc


def resolve_output_root(repo_dir: Path, output_dir: str) -> Path:
    raw = Path(output_dir)
    if raw.is_absolute():
        output_root = raw.resolve()
        repo_relative_path(repo_dir, output_root)
        return output_root
    return (repo_dir / raw).resolve()


def validate_source_file(path: Path, label: str) -> Optional[str]:
    if not path:
        return f"missing_{label}_path"
    if not path.is_file():
        return f"{label}_not_found: {path}"
    return None


def build_artifacts(args: argparse.Namespace, repo_dir: Path, output_root: Path) -> tuple[list[Artifact], list[str]]:
    warnings: list[str] = []
    sources: list[tuple[str, Optional[Path]]] = [
        ("csv", args.csv),
        ("run_report", args.run_report),
        ("google_sheet_json", args.google_sheet_json),
    ]
    artifacts: list[Artifact] = []
    run_output_dir = output_root / args.run_id

    for label, source in sources:
        if source is None:
            continue
        error = validate_source_file(source, label)
        if error:
            if label == "google_sheet_json":
                warnings.append(f"optional_{error}")
                continue
            raise ValueError(error)
        destination = run_output_dir / source.name
        artifacts.append(
            Artifact(
                label=label,
                source=source.resolve(),
                destination=destination,
                relative_destination=repo_relative_path(repo_dir, destination),
            )
        )

    if not artifacts:
        raise ValueError("no_artifacts_to_sync")
    return artifacts, warnings


def copy_artifacts(artifacts: list[Artifact]) -> list[str]:
    copied: list[str] = []
    for artifact in artifacts:
        AtomicCopy(artifact.source, artifact.destination).copy()
        copied.append(artifact.relative_destination)
    return copied


def read_config(args: argparse.Namespace) -> tuple[Path, str]:
    repo_dir = Path(args.repo_dir or os.environ.get("GITHUB_SYNC_REPO_DIR", "")).expanduser()
    output_dir = args.output_dir or os.environ.get("GITHUB_SYNC_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
    if not str(repo_dir).strip():
        raise ValueError("missing_repo_dir")
    if not str(output_dir).strip():
        raise ValueError("missing_output_dir")
    return repo_dir.resolve(), str(output_dir).strip()


def validate_repo(repo_dir: Path) -> None:
    if not repo_dir.is_dir():
        raise ValueError(f"repo_dir_not_found: {repo_dir}")
    require_git_success(repo_dir, ["rev-parse", "--is-inside-work-tree"], "not_a_git_repo")


def sync_to_github(args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        repo_dir, output_dir = read_config(args)
        validate_repo(repo_dir)
        output_root = resolve_output_root(repo_dir, output_dir)
        artifacts, artifact_warnings = build_artifacts(args, repo_dir, output_root)
        warnings.extend(artifact_warnings)
    except (ValueError, RuntimeError) as exc:
        return base_payload(status="failed", warnings=warnings, error=str(exc), dry_run=args.dry_run)

    relative_paths = [artifact.relative_destination for artifact in artifacts]

    if args.dry_run:
        status = run_git(repo_dir, ["status", "--short", "--", *relative_paths])
        if status.returncode != 0:
            return base_payload(
                status="failed",
                files_copied=relative_paths,
                warnings=warnings,
                error=f"git_status_failed: {safe_tail(status.stderr or status.stdout)}",
                dry_run=True,
            )
        warnings.append("dry_run_no_files_copied_no_git_mutation")
        return base_payload(
            status="completed",
            files_copied=relative_paths,
            commit_created=False,
            pushed=False,
            warnings=warnings,
            dry_run=True,
        )

    try:
        files_copied = copy_artifacts(artifacts)
        require_git_success(repo_dir, ["status", "--short", "--", *files_copied], "git_status_failed")
        require_git_success(repo_dir, ["add", "--", *files_copied], "git_add_failed")
        diff = run_git(repo_dir, ["diff", "--cached", "--quiet", "--", *files_copied])
        if diff.returncode == 0:
            warnings.append("no_changes_to_commit")
            return base_payload(
                status="completed",
                files_copied=files_copied,
                commit_created=False,
                pushed=False,
                warnings=warnings,
            )
        if diff.returncode not in {0, 1}:
            raise RuntimeError(f"git_diff_failed: {safe_tail(diff.stderr or diff.stdout)}")

        message = f"Sync XAUUSD lead artifacts {args.run_id}"
        require_git_success(repo_dir, ["commit", "-m", message, "--", *files_copied], "git_commit_failed")
        sha = require_git_success(repo_dir, ["rev-parse", "HEAD"], "git_rev_parse_failed").stdout.strip()
        require_git_success(repo_dir, ["push"], "git_push_failed")
    except (OSError, RuntimeError) as exc:
        return base_payload(
            status="failed",
            files_copied=[artifact.relative_destination for artifact in artifacts],
            warnings=warnings,
            error=str(exc),
        )

    return base_payload(
        status="completed",
        files_copied=files_copied,
        commit_created=True,
        commit_sha=sha,
        pushed=True,
        warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy XAUUSD lead artifacts to a GitHub-backed repo and push a run commit.",
    )
    parser.add_argument("--repo-dir", default="", help="Git repo path. Defaults to GITHUB_SYNC_REPO_DIR.")
    parser.add_argument(
        "--output-dir",
        default="",
        help=f"Output directory inside repo. Defaults to GITHUB_SYNC_OUTPUT_DIR or {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument("--csv", type=Path, default=Path("enriched_leads.csv"))
    parser.add_argument("--run-report", type=Path, default=Path("run_report.json"))
    parser.add_argument("--google-sheet-json", type=Path)
    parser.add_argument("--run-id", default="", help="Run id used for output folder and commit message.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and git status without copying or mutating git.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.run_id:
        args.run_id = default_run_id()
    payload = sync_to_github(args)
    emit(payload)
    if payload.get("status") != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
