# Pipeline Run Report

`scripts/generate_run_report.py` creates a machine-readable summary after a successful XAUUSD lead enrichment run.

The helper is read-only. It never modifies pipeline artifacts.

## Inputs

Required artifacts:

- `raw_leads.csv`
- `normalized_leads.json`
- `enriched_leads.normalized.json`
- `enriched_leads.csv`

Optional artifacts:

- Google Sheets sync JSON from `scripts/sync_google_sheet.py`
- Recent X helper JSON from `scripts/recent_x_activity.py`

## Output

Default output:

```text
run_report.json
```

Suggested archival output:

```text
runs/<timestamp>/run_report.json
```

The helper writes JSON to the output path and prints the same JSON to stdout.

## Runtime Command

From a working folder containing the pipeline artifacts:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/generate_run_report.py \
  --raw-csv /tmp/xauusd-real/raw_leads.csv \
  --normalized-json /tmp/xauusd-real/normalized_leads.json \
  --enriched-json /tmp/xauusd-real/enriched_leads.normalized.json \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --output /tmp/xauusd-real/run_report.json
```

With optional Google Sheets sync JSON:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/generate_run_report.py \
  --raw-csv /tmp/xauusd-real/raw_leads.csv \
  --normalized-json /tmp/xauusd-real/normalized_leads.json \
  --enriched-json /tmp/xauusd-real/enriched_leads.normalized.json \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --google-sheet-json /tmp/xauusd-real/google_sheet_sync.json \
  --output /tmp/xauusd-real/run_report.json
```

## Schema

```json
{
  "schema_version": "pipeline-run-report/v1",
  "run_id": "20260627-120000",
  "started_at": "2026-06-27T11:59:00Z",
  "finished_at": "2026-06-27T12:00:00Z",
  "duration_seconds": 60,
  "pipeline_version": "phase-3d",
  "input": {
    "raw_csv": "/tmp/xauusd-real/raw_leads.csv"
  },
  "normalize": {
    "raw_rows": 100,
    "unique_users": 84,
    "duplicates_removed": 16
  },
  "qualification": {
    "qualified": 32,
    "rejected": 52,
    "average_score": 6.85,
    "median_score": 7.0
  },
  "recent_x": {
    "attempted": 1,
    "completed": 1,
    "failed": 0,
    "skipped": 0,
    "cache_hits": 0
  },
  "google_sheet": {
    "rows_written": 32,
    "duplicates_skipped": 0
  },
  "outputs": {
    "normalized_json": "/tmp/xauusd-real/normalized_leads.json",
    "enriched_json": "/tmp/xauusd-real/enriched_leads.normalized.json",
    "csv": "/tmp/xauusd-real/enriched_leads.csv"
  },
  "warnings": [],
  "status": "completed"
}
```

## Metric Interpretation

`normalize.raw_rows`

- Read from `normalized_leads.json` field `raw_row_count`.

`normalize.unique_users`

- Read from `normalized_leads.json` field `unique_user_count`, falling back to `lead_count`.

`normalize.duplicates_removed`

- Computed from normalized artifact fields as `raw_rows - unique_users`.

`qualification.qualified`

- Count of non-empty data rows in `enriched_leads.csv`.

`qualification.rejected`

- Computed from artifact counts as `unique_users - qualified`.

`qualification.average_score` and `qualification.median_score`

- Calculated from `score_fit` values in `enriched_leads.normalized.json`.
- Falls back to `Score fit` values in `enriched_leads.csv` if enriched scores are unavailable.

`recent_x`

- If a Recent X helper JSON is supplied, metrics come from that helper output.
- Otherwise, metrics come from `recent_x_status` and `recent_x_cache_hit` fields in `enriched_leads.normalized.json`.
- If Recent X was not used, values should be zero.

`google_sheet`

- If Google Sheets sync JSON is supplied, rows are read from that artifact.
- If it is not supplied, `rows_written` and `duplicates_skipped` are `null`.

## Rules

- Never infer metrics from expectations, prompts, or logs.
- Read metrics from artifacts only.
- Emit JSON only.
- Do not modify pipeline artifacts.
- Do not send Telegram notifications.
- Do not call Google Sheets.
- Do not call Xquik.

## Validation

Syntax check:

```bash
python3 -m py_compile /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/generate_run_report.py
```

Check report file exists:

```bash
test -f /tmp/xauusd-real/run_report.json
```

Inspect high-level status:

```bash
python3 -m json.tool /tmp/xauusd-real/run_report.json
```
