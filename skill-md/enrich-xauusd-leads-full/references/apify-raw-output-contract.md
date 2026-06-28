# Apify Raw Fetch Output Contract

`scripts/fetch_apify_raw_leads.py` emits JSON only.

Schema:

```json
{
  "schema_version": "apify-raw-fetch/v1",
  "status": "completed",
  "country_group": "english",
  "rows_written": 800,
  "output_csv": "/tmp/xauusd-real/raw_leads.csv",
  "warnings": [],
  "dry_run": false
}
```

## Fields

- `schema_version`: Always `apify-raw-fetch/v1`.
- `status`: `completed` or `failed`.
- `country_group`: `english`, `europe`, `middle-east`, or `all`.
- `rows_written`: Number of CSV rows written.
- `output_csv`: Path to the generated raw lead CSV.
- `warnings`: Operational warnings.
- `dry_run`: `true` when `--dry-run` was used.
- `planned_actor_inputs`: Present in dry-run mode.
- `error`: Present only on failure.

## Output CSV Columns

The helper writes account-level raw leads compatible with `enrich_xauusd_leads.py normalize`:

```text
country
handle
display_name
followers_estimate
bio_snippet
profile_url
why_relevant
niche
source_urls
discovered_at
created_at
```

`source_urls` is written as a JSON list string when tweet URLs are available.

## Success

```json
{
  "schema_version": "apify-raw-fetch/v1",
  "status": "completed",
  "country_group": "english",
  "rows_written": 800,
  "output_csv": "/tmp/xauusd-real/raw_leads.csv",
  "warnings": [],
  "dry_run": false
}
```

## Dry Run

```json
{
  "schema_version": "apify-raw-fetch/v1",
  "status": "completed",
  "country_group": "english",
  "rows_written": 0,
  "output_csv": "/tmp/xauusd-real/raw_leads.csv",
  "warnings": ["dry_run_no_apify_call"],
  "dry_run": true,
  "planned_actor_inputs": [
    {
      "country": "UK",
      "actor_input": {
        "blue_verified_only": false,
        "verified_only": false,
        "max_items": 267,
        "min_likes": 0,
        "search_query": "(XAUUSD OR \"gold trading\" OR \"gold trader\" OR \"gold analysis\" OR \"forex gold\") (UK OR \"United Kingdom\" OR London OR British) lang:en",
        "search_sort": "Latest",
        "tweet_type": "exclude_retweets",
        "source_mode": "search"
      }
    }
  ]
}
```

## Failure

```json
{
  "schema_version": "apify-raw-fetch/v1",
  "status": "failed",
  "country_group": "english",
  "rows_written": 0,
  "output_csv": "/tmp/xauusd-real/raw_leads.csv",
  "warnings": [],
  "dry_run": false,
  "error": "missing_APIFY_TOKEN"
}
```

Common errors:

- `missing_APIFY_TOKEN`
- `missing_APIFY_ACTOR_ID`
- `actor_failed: ...`
- `dataset_empty`
- `invalid_actor_output`
- `csv_write_failed: ...`

## Compatibility Rules

- Consumers must parse stdout as JSON only.
- Unknown fields are optional.
- The helper must not expose `APIFY_TOKEN`.
- The CSV remains the handoff artifact for `run_pipeline.py`.
