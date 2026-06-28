# Pipeline Orchestrator

`scripts/run_pipeline.py` is the project-owned Phase 3E orchestration wrapper for the XAUUSD lead pipeline.

The orchestrator runs the complete pipeline from optional Apify raw lead fetch through `raw_leads.csv`, enrichment, Google Sheets sync, a machine-readable run report, and optional GitHub artifact sync. It captures subprocess output and emits a single JSON summary to stdout.

It does not implement lead scoring, Recent X lookup, Google Sheets sync, or report metrics itself. It calls the existing project-owned helpers and Hermes.

## Execution Order

```text
optional Apify raw fetch
  |
  v
raw_leads.csv
  |
  v
normalize
  |
  v
Hermes enrichment
  |
  v
validate enriched JSON
  |
  v
write enriched_leads.csv
  |
  v
Google Sheets sync
  |
  v
run report
  |
  v
GitHub sync
  |
  v
single JSON summary
```

Steps:

0. `fetch_apify`
   - Runs only when `--fetch-apify` is provided and `--skip-apify-fetch` is not provided.
   - Runs `scripts/fetch_apify_raw_leads.py`.
   - Produces `raw_leads.csv`.
   - Fatal if it fails.
   - If it fails, the orchestrator does not run normalize, Hermes, CSV write, Google Sheets sync, or GitHub sync. It still attempts `run_report`.

1. `normalize`
   - Runs `scripts/enrich_xauusd_leads.py normalize`.
   - Produces `normalized_leads.json`.
   - Fatal if it fails.

2. `hermes`
   - Runs `hermes chat --skills enrich-xauusd-leads-full --yolo -q "<prompt>"`.
   - Asks Hermes to read `normalized_leads.json` and write `enriched_leads.normalized.json`.
   - Runs the skill in orchestrator mode: Hermes must not call normalize, write the final CSV, sync Google Sheets, or generate the run report.
   - Requires every kept lead with `score_fit >= 7` to include `name`, `username`, `score_fit`, `first_line`, and `hook`.
   - Fatal if it fails.
   - Recent X failures are handled inside Hermes/SKILL instructions and should not stop the pipeline.

3. `validate_enriched_json`
   - Runs `scripts/enrich_xauusd_leads.py validate`.
   - Validates `enriched_leads.normalized.json` before CSV writing.
   - Checks that every kept lead with `score_fit >= 7` has `name`, `username`, numeric `score_fit`, `first_line`, and `hook`.
   - Emits JSON only and writes no files.
   - Fatal if it fails.

4. `write_csv`
   - Runs `scripts/enrich_xauusd_leads.py write`.
   - Produces `enriched_leads.csv`.
   - Fatal if it fails.

5. `google_sheet`
   - Runs `scripts/sync_google_sheet.py`.
   - Writes captured helper JSON to `google_sheet_sync.json`.
   - Non-fatal if it fails.

6. `run_report`
   - Runs `scripts/generate_run_report.py`.
   - Produces `run_report.json`.
   - Always attempted.
   - Non-fatal in orchestrator summary, because the orchestrator should still return machine-readable failure context.

7. `github_sync`
   - Runs `scripts/sync_github.py` after `run_report`, because the current run report must exist before GitHub artifact sync.
   - Copies `enriched_leads.csv`, `run_report.json`, and `google_sheet_sync.json` into the configured Git repo output directory.
   - Non-fatal if it fails.
   - Can be disabled with `--skip-github-sync`.

## Failure Policy

Fatal steps:

- fetch_apify
- normalize
- hermes
- validate_enriched_json
- write_csv

If a fatal step fails, the orchestrator stops downstream enrichment/sync steps and still attempts `run_report`.

Non-fatal steps:

- google_sheet
- run_report
- github_sync

Google Sheets sync, run report, and GitHub sync failures do not fail the core enrichment pipeline. The final orchestrator status becomes `completed_with_warnings` when core steps complete but a non-fatal step fails.

If a fatal step fails, final status is `failed`.

If all steps complete, final status is `completed`.

Recent X Activity failures are not managed directly by `run_pipeline.py`. Hermes and `SKILL.md` own that behavior. Recent X failure should be reflected inside `enriched_leads.normalized.json` and the run report.

## Retry Policy

The orchestrator does not retry steps automatically.

Manual retry guidance:

- If `normalize` fails, fix `raw_leads.csv` and rerun the whole pipeline.
- If `fetch_apify` fails, fix Apify credentials, actor id, actor input, or quota, then rerun with `--fetch-apify`, or use the manual raw CSV fallback.
- If `hermes` fails, inspect Hermes output/logs and rerun the whole pipeline.
- If `write_csv` fails, fix `enriched_leads.normalized.json` and rerun from the orchestrator or run the writer manually.
- If `google_sheet` fails, fix credentials/sheet permissions and rerun Sheets sync only or rerun the orchestrator.
- If `run_report` fails, fix missing artifacts and run `generate_run_report.py` manually.
- If `github_sync` fails, fix Git repo configuration, credentials, remote access, or artifact paths, then rerun `sync_github.py` manually or rerun the orchestrator.

Do not retry Google Sheets blindly until duplicate detection is confirmed active. `sync_google_sheet.py` uses `Username X` duplicate detection for append idempotency.

## One-Command Apify Production Run

This mode fetches raw leads from Apify and then runs the full enrichment pipeline.

```bash
APIFY_TOKEN="<secret>" \
APIFY_ACTOR_ID="<actor-id>" \
HERMES_HOME=/opt/hermes-ads/hermes-home \
GOOGLE_SHEET_ID="<sheet-id>" \
GOOGLE_SERVICE_ACCOUNT_FILE="/secure/path/service-account.json" \
GOOGLE_SHEET_NAME="XAUUSD_Leads" \
GITHUB_SYNC_REPO_DIR="/home/hermesads/xauusd-leads-history" \
GITHUB_SYNC_OUTPUT_DIR="xauusd-leads" \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/run_pipeline.py \
  --fetch-apify \
  --country-group english \
  --apify-max-items 800 \
  --work-dir /tmp/xauusd-real \
  --raw-csv /tmp/xauusd-real/raw_leads.csv \
  --normalized-json /tmp/xauusd-real/normalized_leads.json \
  --enriched-json /tmp/xauusd-real/enriched_leads.normalized.json \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --google-sheet-json /tmp/xauusd-real/google_sheet_sync.json \
  --run-report /tmp/xauusd-real/run_report.json \
  --github-sync-json /tmp/xauusd-real/github_sync.json
```

Use `--apify-actor-id <actor-id>` to override `APIFY_ACTOR_ID`.

## Manual Raw CSV Fallback Run

From a working directory containing `raw_leads.csv`:

```bash
HERMES_HOME=/opt/hermes-ads/hermes-home \
GOOGLE_SHEET_ID="<sheet-id>" \
GOOGLE_SERVICE_ACCOUNT_FILE="/secure/path/service-account.json" \
GOOGLE_SHEET_NAME="XAUUSD_Leads" \
GITHUB_SYNC_REPO_DIR="/home/hermesads/xauusd-leads-history" \
GITHUB_SYNC_OUTPUT_DIR="xauusd-leads" \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/run_pipeline.py \
  --work-dir /tmp/xauusd-real \
  --raw-csv /tmp/xauusd-real/raw_leads.csv \
  --normalized-json /tmp/xauusd-real/normalized_leads.json \
  --enriched-json /tmp/xauusd-real/enriched_leads.normalized.json \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --google-sheet-json /tmp/xauusd-real/google_sheet_sync.json \
  --run-report /tmp/xauusd-real/run_report.json \
  --github-sync-json /tmp/xauusd-real/github_sync.json
```

This is also the default behavior when neither `--fetch-apify` nor `--skip-apify-fetch` is provided.

Use `--skip-github-sync` to disable the GitHub step for local tests or environments without a configured Git repo.

Use `--skip-apify-fetch` to explicitly force the manual raw CSV path even when a wrapper or operator normally adds `--fetch-apify`.

## Output Summary

The orchestrator emits JSON only:

Every step object includes `started_at`, `finished_at`, and `duration_seconds` for bottleneck analysis while preserving the existing `name`, `status`, `fatal`, `returncode`, and `command` fields.

```json
{
  "schema_version": "xauusd-pipeline-orchestrator/v1",
  "status": "completed",
  "run_id": "20260627-120000",
  "started_at": "2026-06-27T12:00:00Z",
  "finished_at": "2026-06-27T12:03:00Z",
  "duration_seconds": 180,
  "steps": [
    {
      "name": "fetch_apify",
      "status": "completed"
    },
    {
      "name": "normalize",
      "status": "completed",
      "started_at": "2026-06-27T12:00:00Z",
      "finished_at": "2026-06-27T12:00:02Z",
      "duration_seconds": 2
    },
    {
      "name": "hermes",
      "status": "completed"
    },
    {
      "name": "validate_enriched_json",
      "status": "completed"
    },
    {
      "name": "write_csv",
      "status": "completed"
    },
    {
      "name": "google_sheet",
      "status": "completed"
    },
    {
      "name": "run_report",
      "status": "completed"
    },
    {
      "name": "github_sync",
      "status": "completed"
    }
  ],
  "outputs": {
    "normalized_json": "/tmp/xauusd-real/normalized_leads.json",
    "enriched_json": "/tmp/xauusd-real/enriched_leads.normalized.json",
    "csv": "/tmp/xauusd-real/enriched_leads.csv",
    "google_sheet_sync": "/tmp/xauusd-real/google_sheet_sync.json",
    "run_report": "/tmp/xauusd-real/run_report.json",
    "github_sync": "/tmp/xauusd-real/github_sync.json"
  }
}
```

The actual JSON includes command arrays and return codes for auditability. It does not include service account secrets.

## Validation

Syntax check:

```bash
python3 -m py_compile /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/run_pipeline.py
```

The orchestrator requires a real Hermes runtime for an end-to-end test. For local development, validate individual helpers first:

```bash
python3 -m py_compile skill-md/enrich-xauusd-leads-full/scripts/run_pipeline.py
python3 -m py_compile skill-md/enrich-xauusd-leads-full/scripts/fetch_apify_raw_leads.py
python3 -m py_compile skill-md/enrich-xauusd-leads-full/scripts/generate_run_report.py
python3 -m py_compile skill-md/enrich-xauusd-leads-full/scripts/sync_google_sheet.py
python3 -m py_compile skill-md/enrich-xauusd-leads-full/scripts/sync_github.py
```

## Notes

- No Telegram notification is implemented in Phase 3E.
- No Google Sheets replace/upsert mode is implemented.
- GitHub sync is optional and non-fatal.
- The orchestrator does not modify production helper behavior.
