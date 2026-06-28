# Apify Raw Scrape SOP

`scripts/fetch_apify_raw_leads.py` runs the configured Apify X scraper actor and writes account-level raw leads to `raw_leads.csv`.

This helper only fetches raw leads. It does not enrich, score, sync Google Sheets, sync GitHub, or call Hermes.

## Purpose

Create the input artifact for:

```bash
scripts/run_pipeline.py --raw-csv /tmp/xauusd-real/raw_leads.csv
```

The helper writes CSV columns already supported by `scripts/enrich_xauusd_leads.py normalize`.

## Prerequisites

- Apify actor configured for X/Twitter search.
- `APIFY_TOKEN` available in the runtime environment.
- `APIFY_ACTOR_ID` set, or pass `--actor-id`.
- Working folder exists and is writable.

Do not commit or print `APIFY_TOKEN`.

## Environment

```bash
export APIFY_TOKEN="<secret>"
export APIFY_ACTOR_ID="<actor-id>"
```

## Country Groups

`english`:

- UK
- Canada
- Germany

`europe`:

- France
- Italy
- Poland

`middle-east`:

- UAE
- Saudi Arabia

`all` runs all groups.

## Query Strategy

For each country, the helper builds an X search query using:

- `XAUUSD`
- `"gold trading"`
- `"gold trader"`
- `"gold analysis"`
- `"forex gold"`
- country/location terms
- language filter when configured

Examples:

```text
(XAUUSD OR "gold trading" OR "gold trader" OR "gold analysis" OR "forex gold") (UK OR "United Kingdom" OR London OR British) lang:en
```

```text
(XAUUSD OR "gold trading" OR "gold trader" OR "gold analysis" OR "forex gold") (France OR Paris OR French) lang:fr
```

## Actor Input

The helper passes one actor input per country:

```json
{
  "blue_verified_only": false,
  "verified_only": false,
  "max_items": 267,
  "min_likes": 0,
  "search_query": "...",
  "search_sort": "Latest",
  "tweet_type": "exclude_retweets",
  "source_mode": "search"
}
```

`max_items` is split across countries in the selected group.

Allowed `tweet_type` values:

- `all`
- `originals_only`
- `replies_only`
- `retweets_only`
- `exclude_replies`
- `exclude_retweets`

Do not use `Latest` as `tweet_type`. Use `search_sort = "Latest"` for latest sorting.

## Dry Run

Dry-run does not call Apify.

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/fetch_apify_raw_leads.py \
  --country-group english \
  --output-csv /tmp/xauusd-real/raw_leads.csv \
  --max-items 800 \
  --dry-run
```

Dry-run with fixture CSV:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/fetch_apify_raw_leads.py \
  --country-group english \
  --output-csv /tmp/xauusd-real/raw_leads.csv \
  --max-items 800 \
  --dry-run \
  --write-dry-run-fixture
```

## Real Run

```bash
APIFY_TOKEN="<secret>" \
APIFY_ACTOR_ID="<actor-id>" \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/fetch_apify_raw_leads.py \
  --country-group english \
  --output-csv /tmp/xauusd-real/raw_leads.csv \
  --max-items 800
```

All countries:

```bash
APIFY_TOKEN="<secret>" \
APIFY_ACTOR_ID="<actor-id>" \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/fetch_apify_raw_leads.py \
  --country-group all \
  --output-csv /tmp/xauusd-real/raw_leads.csv \
  --max-items 800
```

## Expected CSV

```text
country,handle,display_name,followers_estimate,bio_snippet,profile_url,why_relevant,niche,source_urls,discovered_at,created_at
```

This is the team-account raw CSV format supported by normalize.

## Next Step

After fetch completes, run the pipeline against the generated raw CSV:

```bash
HERMES_HOME=/opt/hermes-ads/hermes-home \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/run_pipeline.py \
  --work-dir /tmp/xauusd-real \
  --raw-csv /tmp/xauusd-real/raw_leads.csv
```

Or run the complete Apify-to-sync workflow in one command:

```bash
APIFY_TOKEN="<secret>" \
APIFY_ACTOR_ID="<actor-id>" \
HERMES_HOME=/opt/hermes-ads/hermes-home \
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/run_pipeline.py \
  --fetch-apify \
  --country-group english \
  --apify-max-items 800 \
  --work-dir /tmp/xauusd-real \
  --raw-csv /tmp/xauusd-real/raw_leads.csv
```

## Common Errors

### `missing_APIFY_TOKEN`

Set `APIFY_TOKEN`.

### `missing_APIFY_ACTOR_ID`

Set `APIFY_ACTOR_ID` or pass `--actor-id`.

### `actor_failed`

Check the actor run page in Apify. Common causes are invalid actor input, actor quota, X scraper limitations, or actor timeout.

### `dataset_empty`

The actor completed but returned no usable dataset rows. Try a broader country group, lower filters, or inspect the actor run dataset.

### `invalid_actor_output`

The dataset response was not a JSON list. Inspect the actor output format before changing the converter.

### `csv_write_failed`

Check output directory permissions and disk space.

## Verification Checklist

- JSON stdout has `schema_version = "apify-raw-fetch/v1"`.
- `status = "completed"`.
- `rows_written > 0` for real runs.
- `raw_leads.csv` exists.
- CSV header matches the output contract.
- Normalize accepts the CSV:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/enrich_xauusd_leads.py \
  normalize /tmp/xauusd-real/raw_leads.csv \
  --output /tmp/xauusd-real/normalized_leads.json
```

## Safety

- Do not store `APIFY_TOKEN` in repo files.
- Do not print raw secrets.
- `run_pipeline.py` may call this helper in Phase 6A when `--fetch-apify` is provided.
- Do not treat Apify output as qualified leads. Hermes still scores and filters later.
