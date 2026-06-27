# Google Sheets Sync SOP

This SOP covers the project-owned Google Sheets sync helper for `Enrich_XAUUSD_Leads_Full`.

The helper is deterministic orchestration glue. It reads `enriched_leads.csv`, appends rows to one configured Google Sheet, and returns JSON only. Hermes orchestrates it. Hermes must not call Google Sheets APIs directly.

## Scope

Allowed:

- Read `enriched_leads.csv`.
- Preserve CSV column order.
- Skip empty rows.
- Authenticate with a Google service account.
- Append rows to one configured Google Sheet.
- Return JSON only.

Forbidden:

- Modifying `enriched_leads.csv`.
- Changing normalize/write helper behavior.
- Changing scoring or enrichment logic.
- Calling LLMs.
- Producing markdown or HTML output.
- Syncing to CRM, GitHub, or other destinations.

## Files

Helper:

```text
skill-md/enrich-xauusd-leads-full/scripts/sync_google_sheet.py
```

Output contract:

```text
skill-md/enrich-xauusd-leads-full/references/google-sheets-output-contract.md
```

## Prerequisites

Runtime user:

```text
hermesads
```

Runtime skill path:

```text
/opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/
```

Python dependencies required for real sync:

```text
google-auth
google-api-python-client
```

No Google network call is required for syntax validation or `--dry-run`.

## Environment Variables

Required for real sync:

```bash
export GOOGLE_SHEET_ID="<sheet-id>"
export GOOGLE_SERVICE_ACCOUNT_FILE="/secure/path/service-account.json"
```

Alternative credential variable:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/service-account.json"
```

Optional:

```bash
export GOOGLE_SHEET_NAME="XAUUSD_Leads"
```

Do not commit service account JSON files. Do not print credentials in logs.

## Service Account Setup

1. Create a Google service account in the target Google Cloud project.
2. Create a JSON key for that service account.
3. Store the JSON file on the VPS outside the repository.
4. Share the target Google Sheet with the service account email.
5. Grant edit access.

## Preflight

Check syntax:

```bash
python3 -m py_compile /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/sync_google_sheet.py
```

Check dry-run without Google API call:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/sync_google_sheet.py \
  /tmp/xauusd-real/enriched_leads.csv \
  --sheet-id "dry-run-sheet-id" \
  --credentials-file "/tmp/nonexistent-service-account.json" \
  --dry-run
```

Expected:

- valid JSON
- `status = "completed"`
- `rows_read` equals non-header CSV rows
- `rows_written = 0`
- `duplicates_skipped` is calculated when credentials are valid and existing sheet rows can be read
- if credentials are unavailable, warning includes `duplicate_check_skipped: ...`
- warning includes `dry_run_no_google_api_call`

## Runtime Command

```bash
GOOGLE_SHEET_ID="<sheet-id>" \
GOOGLE_SERVICE_ACCOUNT_FILE="/secure/path/service-account.json" \
GOOGLE_SHEET_NAME="XAUUSD_Leads" \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/sync_google_sheet.py \
  /tmp/xauusd-real/enriched_leads.csv
```

The helper appends data rows only by default. Use `--include-header` only when intentionally appending the CSV header to an empty worksheet.

Before appending, the helper reads existing sheet rows and skips any CSV row whose `Username X` already exists in the sheet.

## Expected Output

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

## Common Failures

`missing_sheet_id`

- `GOOGLE_SHEET_ID` was not set and `--sheet-id` was not provided.
- Set the sheet ID and rerun.

`missing_service_account_credentials`

- No credential file was provided.
- Set `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_APPLICATION_CREDENTIALS`.

`service_account_file_not_found`

- The credential path does not exist from the runtime user's perspective.
- Fix path or permissions.

`google_client_dependency_missing`

- Python dependencies are not installed in the Hermes runtime venv.
- Install `google-auth` and `google-api-python-client` in the correct venv.

`authentication_failed`

- Service account JSON is invalid or unreadable.
- Replace credentials, check permissions, and verify the JSON key is active.

`append_failed: ...`

- Google Sheets API rejected the append request.
- Check sharing permissions, sheet ID, worksheet name, quota, and network access.

`read_existing_rows_failed: ...`

- Helper could not read existing sheet rows for duplicate detection.
- Pipeline action: treat sync as failed and do not append rows.
- Check sheet ID, worksheet name, service account sharing, network access, and API permissions.

## Idempotency

The helper is idempotent for append mode using `Username X` as the duplicate key.

Current behavior:

- reads CSV
- skips empty rows
- reads existing sheet rows
- normalizes existing and incoming `Username X` values
- skips rows whose username already exists
- appends remaining rows in original CSV order
- returns `duplicates_skipped`

Username normalization:

- trim whitespace
- lowercase
- remove leading `@`

Rows with empty `Username X` are appended and reported in `warnings`.

The helper remains append-only. It does not replace or upsert existing rows.

## Verification Checklist

- [ ] `enriched_leads.csv` exists.
- [ ] CSV header remains unchanged.
- [ ] Helper emits JSON only.
- [ ] `schema_version = "google-sheets-sync/v1"`.
- [ ] `status = "completed"` for successful sync.
- [ ] `rows_read` matches CSV data-row count.
- [ ] `rows_written` matches rows appended.
- [ ] `duplicates_skipped` matches CSV rows whose `Username X` already existed in the sheet.
- [ ] Running the same sync twice writes zero duplicate username rows on the second run.
- [ ] No secrets appear in stdout or logs.
