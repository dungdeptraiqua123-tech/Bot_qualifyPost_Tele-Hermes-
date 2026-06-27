#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


SCHEMA_VERSION = "google-sheets-sync/v1"
DEFAULT_SHEET_NAME = "XAUUSD_Leads"
DEFAULT_VALUE_INPUT_OPTION = "USER_ENTERED"
USERNAME_COLUMN = "Username X"


@dataclass(frozen=True)
class SyncConfig:
    sheet_id: str
    sheet_name: str
    credentials_file: str
    value_input_option: str = DEFAULT_VALUE_INPUT_OPTION


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def base_payload(
    *,
    status: str,
    rows_read: int = 0,
    rows_written: int = 0,
    duplicates_skipped: int = 0,
    sheet: str = DEFAULT_SHEET_NAME,
    warnings: Optional[list[str]] = None,
    error: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "rows_read": rows_read,
        "rows_written": rows_written,
        "duplicates_skipped": duplicates_skipped,
        "sheet": sheet,
        "warnings": warnings or [],
    }
    if error:
        payload["error"] = error
    return payload


def read_config(args: argparse.Namespace) -> SyncConfig:
    sheet_id = (args.sheet_id or os.environ.get("GOOGLE_SHEET_ID", "")).strip()
    sheet_name = (args.sheet_name or os.environ.get("GOOGLE_SHEET_NAME", DEFAULT_SHEET_NAME)).strip()
    credentials_file = (
        args.credentials_file
        or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    ).strip()
    return SyncConfig(
        sheet_id=sheet_id,
        sheet_name=sheet_name or DEFAULT_SHEET_NAME,
        credentials_file=credentials_file,
        value_input_option=(args.value_input_option or DEFAULT_VALUE_INPUT_OPTION).strip()
        or DEFAULT_VALUE_INPUT_OPTION,
    )


def validate_config(config: SyncConfig) -> Optional[str]:
    if not config.sheet_id:
        return "missing_sheet_id"
    if not config.credentials_file:
        return "missing_service_account_credentials"
    if not Path(config.credentials_file).is_file():
        return "service_account_file_not_found"
    return None


def row_is_empty(row: dict[str, str]) -> bool:
    return not any(str(value or "").strip() for value in row.values())


def read_csv_rows(csv_path: Path) -> tuple[list[str], list[list[str]], int, list[str]]:
    warnings: list[str] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError("missing_csv_header")
        rows_read = 0
        rows: list[list[str]] = []
        for row in reader:
            rows_read += 1
            normalized = {key: str(value or "") for key, value in row.items() if key is not None}
            if row_is_empty(normalized):
                continue
            rows.append([normalized.get(column, "") for column in fieldnames])
    if not rows:
        warnings.append("no_non_empty_rows_to_append")
    return fieldnames, rows, rows_read, warnings


def normalize_username_key(value: Any) -> str:
    return str(value or "").strip().lstrip("@").lower()


def username_column_index(fieldnames: list[str]) -> int:
    try:
        return fieldnames.index(USERNAME_COLUMN)
    except ValueError as exc:
        raise ValueError("missing_username_column") from exc


def build_values(fieldnames: list[str], rows: list[list[str]], include_header: bool) -> list[list[str]]:
    if not rows:
        return []
    if include_header:
        return [fieldnames, *rows]
    return rows


def find_existing_username_index(
    existing_values: list[list[Any]],
    csv_username_index: int,
    warnings: list[str],
) -> tuple[int, list[list[Any]]]:
    if not existing_values:
        return csv_username_index, []
    header = [str(value or "").strip() for value in existing_values[0]]
    if USERNAME_COLUMN in header:
        return header.index(USERNAME_COLUMN), existing_values[1:]
    warnings.append("existing_sheet_header_missing_username_x_assuming_csv_column_index")
    return csv_username_index, existing_values


def existing_username_keys(
    existing_values: list[list[Any]],
    csv_username_index: int,
    warnings: list[str],
) -> set[str]:
    existing_index, data_rows = find_existing_username_index(
        existing_values,
        csv_username_index,
        warnings,
    )
    keys = set()
    for row in data_rows:
        if existing_index >= len(row):
            continue
        key = normalize_username_key(row[existing_index])
        if key:
            keys.add(key)
    return keys


def filter_duplicate_rows(
    rows: list[list[str]],
    *,
    username_index: int,
    existing_keys: set[str],
    warnings: list[str],
) -> tuple[list[list[str]], int]:
    rows_to_append = []
    duplicates_skipped = 0
    empty_username_rows = 0
    for row in rows:
        username = row[username_index] if username_index < len(row) else ""
        key = normalize_username_key(username)
        if not key:
            empty_username_rows += 1
            rows_to_append.append(row)
            continue
        if key in existing_keys:
            duplicates_skipped += 1
            continue
        rows_to_append.append(row)
    if empty_username_rows:
        warnings.append(f"{empty_username_rows} row(s) with empty Username X appended")
    return rows_to_append, duplicates_skipped


def build_sheets_service(credentials_file: str) -> Any:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("google_client_dependency_missing") from exc

    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    except Exception as exc:
        raise RuntimeError("authentication_failed") from exc

    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def append_values(
    *,
    service: Any,
    sheet_id: str,
    sheet_name: str,
    values: list[list[str]],
    value_input_option: str,
) -> int:
    if not values:
        return 0
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        )
        .execute()
    )
    updates = result.get("updates", {}) if isinstance(result, dict) else {}
    return int(updates.get("updatedRows") or len(values))


def read_existing_values(*, service: Any, sheet_id: str, sheet_name: str) -> list[list[Any]]:
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A:Z",
            majorDimension="ROWS",
        )
        .execute()
    )
    values = result.get("values", []) if isinstance(result, dict) else []
    return values if isinstance(values, list) else []


def sync_csv_to_sheet(
    *,
    csv_path: Path,
    config: SyncConfig,
    include_header: bool = False,
    dry_run: bool = False,
    service_factory: Callable[[str], Any] = build_sheets_service,
    read_existing_func: Callable[..., list[list[Any]]] = read_existing_values,
    append_func: Callable[..., int] = append_values,
) -> dict[str, Any]:
    if not csv_path.is_file():
        return base_payload(status="failed", sheet=config.sheet_name, error="input_csv_not_found")

    config_error = validate_config(config)
    if config_error and not dry_run:
        return base_payload(status="failed", sheet=config.sheet_name, error=config_error)

    try:
        fieldnames, rows, rows_read, warnings = read_csv_rows(csv_path)
    except ValueError as exc:
        return base_payload(status="failed", sheet=config.sheet_name, error=str(exc))
    except OSError as exc:
        return base_payload(status="failed", sheet=config.sheet_name, error=f"csv_read_failed: {exc}")

    try:
        username_index = username_column_index(fieldnames)
    except ValueError as exc:
        return base_payload(
            status="failed",
            rows_read=rows_read,
            sheet=config.sheet_name,
            warnings=warnings,
            error=str(exc),
        )

    if dry_run:
        duplicates_skipped = 0
        if config_error:
            warnings.append(f"duplicate_check_skipped: {config_error}")
        else:
            try:
                service = service_factory(config.credentials_file)
                existing_values = read_existing_func(
                    service=service,
                    sheet_id=config.sheet_id,
                    sheet_name=config.sheet_name,
                )
                existing_keys = existing_username_keys(existing_values, username_index, warnings)
                _, duplicates_skipped = filter_duplicate_rows(
                    rows,
                    username_index=username_index,
                    existing_keys=existing_keys,
                    warnings=warnings,
                )
            except RuntimeError as exc:
                return base_payload(
                    status="failed",
                    rows_read=rows_read,
                    sheet=config.sheet_name,
                    warnings=warnings,
                    error=str(exc),
                )
            except Exception as exc:
                return base_payload(
                    status="failed",
                    rows_read=rows_read,
                    sheet=config.sheet_name,
                    warnings=warnings,
                    error=f"read_existing_rows_failed: {exc}",
                )
        warnings.append("dry_run_no_google_api_call")
        return base_payload(
            status="completed",
            rows_read=rows_read,
            rows_written=0,
            duplicates_skipped=duplicates_skipped,
            sheet=config.sheet_name,
            warnings=warnings,
        )

    duplicates_skipped = 0
    try:
        service = service_factory(config.credentials_file)
    except RuntimeError as exc:
        return base_payload(
            status="failed",
            rows_read=rows_read,
            duplicates_skipped=duplicates_skipped,
            sheet=config.sheet_name,
            warnings=warnings,
            error=str(exc),
        )

    try:
        existing_values = read_existing_func(
            service=service,
            sheet_id=config.sheet_id,
            sheet_name=config.sheet_name,
        )
        existing_keys = existing_username_keys(existing_values, username_index, warnings)
    except Exception as exc:
        return base_payload(
            status="failed",
            rows_read=rows_read,
            sheet=config.sheet_name,
            warnings=warnings,
            error=f"read_existing_rows_failed: {exc}",
        )

    rows_to_append, duplicates_skipped = filter_duplicate_rows(
        rows,
        username_index=username_index,
        existing_keys=existing_keys,
        warnings=warnings,
    )
    values = build_values(fieldnames, rows_to_append, include_header)

    try:
        rows_written = append_func(
            service=service,
            sheet_id=config.sheet_id,
            sheet_name=config.sheet_name,
            values=values,
            value_input_option=config.value_input_option,
        )
    except Exception as exc:
        return base_payload(
            status="failed",
            rows_read=rows_read,
            duplicates_skipped=duplicates_skipped,
            sheet=config.sheet_name,
            warnings=warnings,
            error=f"append_failed: {exc}",
        )

    return base_payload(
        status="completed",
        rows_read=rows_read,
        rows_written=rows_written,
        duplicates_skipped=duplicates_skipped,
        sheet=config.sheet_name,
        warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append enriched XAUUSD lead CSV rows to a configured Google Sheet.",
    )
    parser.add_argument("csv_path", type=Path, help="Path to enriched_leads.csv.")
    parser.add_argument("--sheet-id", default="", help="Google Sheet ID. Defaults to GOOGLE_SHEET_ID.")
    parser.add_argument(
        "--sheet-name",
        default="",
        help=f"Worksheet/tab name. Defaults to GOOGLE_SHEET_NAME or {DEFAULT_SHEET_NAME}.",
    )
    parser.add_argument(
        "--credentials-file",
        default="",
        help="Service account JSON file. Defaults to GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_APPLICATION_CREDENTIALS.",
    )
    parser.add_argument("--value-input-option", default=DEFAULT_VALUE_INPUT_OPTION)
    parser.add_argument("--include-header", action="store_true", help="Append the CSV header row before data rows.")
    parser.add_argument("--dry-run", action="store_true", help="Read and validate CSV without calling Google APIs.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = read_config(args)
    payload = sync_csv_to_sheet(
        csv_path=args.csv_path,
        config=config,
        include_header=args.include_header,
        dry_run=args.dry_run,
    )
    emit(payload)


if __name__ == "__main__":
    main()
