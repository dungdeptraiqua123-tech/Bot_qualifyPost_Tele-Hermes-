# Google Sheets Sync Output Contract

This document defines the JSON contract for `scripts/sync_google_sheet.py`.

The helper is deterministic around file handling and emits JSON only. It appends rows from `enriched_leads.csv` into one configured Google Sheet. Hermes orchestrates the helper and must not call Google Sheets APIs directly.

## Success

```json
{
  "schema_version": "google-sheets-sync/v1",
  "status": "completed",
  "rows_read": 70,
  "rows_written": 68,
  "duplicates_skipped": 2,
  "sheet": "XAUUSD_Leads",
  "warnings": []
}
```

## Failure

```json
{
  "schema_version": "google-sheets-sync/v1",
  "status": "failed",
  "rows_read": 0,
  "rows_written": 0,
  "duplicates_skipped": 0,
  "sheet": "XAUUSD_Leads",
  "warnings": [],
  "error": "authentication_failed"
}
```

## Fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Always `google-sheets-sync/v1`. |
| `status` | string | `completed` or `failed`. |
| `rows_read` | number | Non-header CSV rows read, including empty rows. |
| `rows_written` | number | Rows appended to Google Sheets. |
| `duplicates_skipped` | number | CSV rows skipped because their normalized `Username X` already exists in the target sheet. |
| `sheet` | string | Worksheet/tab name. Defaults to `XAUUSD_Leads`. |
| `warnings` | array | Non-fatal diagnostics. |
| `error` | string | Present only when `status = "failed"`. |

## Error Values

Common error values:

- `input_csv_not_found`
- `missing_sheet_id`
- `missing_service_account_credentials`
- `service_account_file_not_found`
- `missing_csv_header`
- `google_client_dependency_missing`
- `authentication_failed`
- `read_existing_rows_failed: ...`
- `append_failed: ...`
- `csv_read_failed: ...`

## CSV Contract

The helper preserves CSV column order exactly as read from the file. For this pipeline, the expected CSV columns are:

```text
Name
Username X
First-line cá nhân hóa
Score fit
Hook
```

The helper does not modify `enriched_leads.csv`.

## Duplicate Detection

The helper is idempotent for append mode using `Username X` as the duplicate key.

Before appending, it reads existing sheet rows, finds existing `Username X` values, and skips CSV rows whose normalized username already exists.

Username normalization:

- trim whitespace
- lowercase
- remove a leading `@`

Rows with empty `Username X` are appended and reported through `warnings`.

The helper does not implement replace or upsert. It remains append-only.
