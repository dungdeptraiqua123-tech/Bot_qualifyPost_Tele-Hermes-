# Enrich XAUUSD Leads Full

Native Hermes skill source for enriching Apify X/Twitter lead exports for XAUUSD / gold trading outreach.

## Files

- `SKILL.md` - Hermes orchestration instructions.
- `scripts/enrich_xauusd_leads.py` - deterministic CSV/JSON helper.
- `scripts/recent_x_activity.py` - optional project-owned X-only research helper for one selected uncertain lead.
- `examples/raw_leads.sample.csv` - small local test input.
- `references/recent-x-activity-sop.md` - SOP for the Recent X Activity helper.
- `references/recent-x-activity-output-schema.md` - JSON evidence contract for Recent X Activity.

The normalize/write helper does not score leads, generate copy, call models, scrape X/Twitter, or call external APIs. Hermes does the enrichment. The separate Recent X Activity helper is optional and may be called by Hermes for at most one selected uncertain lead.

## Automated Hermes Flow

From a working folder containing `raw_leads.csv`, run Hermes with this skill:

```bash
HERMES_HOME=/opt/hermes-ads/hermes-home \
/opt/hermes-ads/venvs/hermes/bin/hermes --skills enrich-xauusd-leads-full \
"Enrich raw_leads.csv and write enriched_leads.csv"
```

Hermes should:

1. Call `normalize` to create `normalized_leads.json`.
2. Enrich each unique X account using LLM reasoning.
3. Optionally call `scripts/recent_x_activity.py` for at most one uncertain/high-potential account after initial CSV-only scoring.
4. Write `enriched_leads.normalized.json` automatically.
5. Call `write` to create `enriched_leads.csv`.

There is no manual JSONL editing step.

Apify exports tweet rows, not unique people. The normalize step deduplicates by X handle, so one normalized lead equals one X account with up to 3 `recent_tweets` as evidence.

## Helper-Only Local Test

These commands test deterministic file handling only. They do not test LLM scoring or Recent X Activity.

From the repository root:

```bash
mkdir -p /tmp/xauusd-leads-test
cp skill-md/enrich-xauusd-leads-full/examples/raw_leads.sample.csv /tmp/xauusd-leads-test/raw_leads.csv

python skill-md/enrich-xauusd-leads-full/scripts/enrich_xauusd_leads.py normalize \
  /tmp/xauusd-leads-test/raw_leads.csv \
  --output /tmp/xauusd-leads-test/normalized_leads.json
```

The sample contains duplicate handles. Normalize should report fewer unique X accounts than raw CSV rows.

Create a small Hermes-like enriched JSON fixture:

```json
{
  "schema_version": "xauusd-leads-enriched/v1",
  "leads": [
    {
      "row_id": 1,
      "name": "Gold Macro Notes",
      "username": "@goldmacronotes",
      "score_fit": 9,
      "first_line": "Saw your XAUUSD supply-zone note; your patience around confirmation stood out.",
      "hook": "Gold traders who wait for confirmation usually care about cleaner risk zones."
    }
  ]
}
```

Save that fixture at `/tmp/xauusd-leads-test/enriched_leads.normalized.json`, then write the CSV:

```bash
python skill-md/enrich-xauusd-leads-full/scripts/enrich_xauusd_leads.py write \
  --input /tmp/xauusd-leads-test/enriched_leads.normalized.json \
  --output /tmp/xauusd-leads-test/enriched_leads.csv
```

The output CSV columns are exactly:

```text
Name
Username X
First-line cá nhân hóa
Score fit
Hook
```

The writer also drops duplicate output usernames defensively if Hermes accidentally repeats an account in the enriched JSON.

## Optional Recent X Activity Helper Test

This test verifies the helper's no-key behavior without calling Xquik:

```bash
mkdir -p /tmp/recent-x-cache-test
unset XQUIK_API_KEY

python3 skill-md/enrich-xauusd-leads-full/scripts/recent_x_activity.py \
  --username "@GoldTrader" \
  --query "@GoldTrader XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /tmp/recent-x-cache-test \
  --timeout 5 \
  --emit json
```

Expected: valid JSON with `status` set to `skipped`, `source` set to `none`, and no pipeline failure.

## Production Deploy Target

This project uses:

```text
HERMES_HOME=/opt/hermes-ads/hermes-home
```

Runtime skill target:

```text
/opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/
```

Do not deploy this under `~/.hermes` for the VPS.
