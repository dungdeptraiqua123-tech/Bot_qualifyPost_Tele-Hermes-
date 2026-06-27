# Recent X Activity SOP

This SOP covers the project-owned Recent X Activity helper used by `Enrich_XAUUSD_Leads_Full`.

The helper is not a scraper for the whole pipeline. It is a bounded evidence collector for selected high-potential XAUUSD leads.

## Scope

Use this helper only when Hermes has already normalized and scored leads from CSV evidence and selected a small number of uncertain accounts for optional research.

Allowed:

- X only.
- Xquik backend only.
- JSON output only.
- Same-day cache.
- Keyword-based evidence extraction.

Forbidden:

- Reddit, YouTube, TikTok, Instagram, Hacker News, GitHub, Polymarket, broad web search.
- HTML output.
- Markdown reports.
- Competitor mode.
- Browser-cookie extraction.
- LLM calls.
- CSV writes.
- Pipeline-blocking failures.

## Prerequisites

Runtime user:

```text
hermesads
```

Runtime skill path:

```text
/opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/
```

Required script:

```text
/opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/recent_x_activity.py
```

Cache directory:

```text
/home/hermesads/xauusd-leads/research-cache/
```

Optional backend credential:

```text
XQUIK_API_KEY
```

If `XQUIK_API_KEY` is not set, the helper returns `status: "skipped"` JSON and does not fail the pipeline.

## Environment Variables

Required for real Xquik lookup:

```bash
export XQUIK_API_KEY="<secret>"
```

Do not commit secrets.
Do not put secrets in `SKILL.md`.
Do not print secrets in logs.

Recommended operational defaults:

```text
RECENT_X_CACHE_DIR=/home/hermesads/xauusd-leads/research-cache
RECENT_X_TIMEOUT_SECONDS=120
RECENT_X_WINDOW_DAYS=30
RECENT_X_MAX_ACCOUNTS=1
```

The MVP script takes these as CLI values, not environment-driven config.

## Preflight Checks

Run on VPS:

```bash
test -f /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/recent_x_activity.py
```

```bash
sudo -u hermesads mkdir -p /home/hermesads/xauusd-leads/research-cache
sudo -u hermesads test -w /home/hermesads/xauusd-leads/research-cache
```

Check Python syntax:

```bash
python3 -m py_compile /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/recent_x_activity.py
```

Check no-key behavior without calling Xquik:

```bash
unset XQUIK_API_KEY

python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/recent_x_activity.py \
  --username "@goldtrader" \
  --query "@goldtrader XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /tmp/recent-x-cache-test \
  --timeout 5 \
  --emit json
```

Expected:

- Valid JSON.
- `status` is `skipped`.
- `source` is `none`.
- `warnings` includes `XQUIK_API_KEY is not set`.

## Run Command

Manual real lookup:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/recent_x_activity.py \
  --username "@goldtrader" \
  --query "@goldtrader XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /home/hermesads/xauusd-leads/research-cache \
  --timeout 120 \
  --emit json
```

Hermes should run this only for selected leads, not every account.

When using Xquik, the helper builds a backend query with `from:<username>` plus the requested date window. It then validates returned records and keeps only tweets whose author handle matches the requested username. Replies, mentions, quoted tweets, or nested records authored by other accounts are discarded before evidence extraction.

Hermes must set these internal audit fields for every non-selected lead:

```json
{
  "recent_x_status": "skipped",
  "recent_x_summary": "",
  "recent_x_cache_hit": false
}
```

Selection rules:

- Max 1 account per enrichment run in the Phase 2B MVP.
- Score 7-8 leads only.
- High-potential but thin CSV evidence.
- Weak/missing `recent_tweets`.
- Unclear persona.
- Low confidence.

Skip:

- Score <= 6.
- Score >= 9 with strong CSV evidence.
- Spam, fake-profit, irrelevant, crypto-only, low-information accounts.
- Username already researched in the same run.

## Expected Output

The helper emits JSON only.

Successful or empty successful lookup:

```json
{
  "schema_version": "recent-x-activity/v1",
  "username": "@goldtrader",
  "query": "@goldtrader XAUUSD gold trading",
  "window_days": 30,
  "status": "completed",
  "source": "xquik",
  "fetched_at": "2026-06-27T10:00:00Z",
  "cache_hit": false,
  "posts": [],
  "evidence": {
    "recent_activity": false,
    "xauusd_mentions": 0,
    "gold_mentions": 0,
    "trading_terms": [],
    "themes": [],
    "persona_hint": "",
    "summary": ""
  },
  "warnings": []
}
```

An empty successful lookup with `status: "completed"` and `posts: []` is valid. It means no target-authored recent posts were found or every returned post was discarded by the helper's author filter. Do not treat it as failed, do not fabricate evidence, and continue with CSV-only evidence plus audit status `completed`.

Before using helper output, Hermes must validate:

```text
schema_version == "recent-x-activity/v1"
```

If the schema version is missing or different, treat the lookup as failed and continue CSV-only.

Skipped lookup:

```json
{
  "status": "skipped",
  "source": "none",
  "cache_hit": false,
  "warnings": ["XQUIK_API_KEY is not set"]
}
```

Failed lookup:

```json
{
  "status": "failed",
  "source": "xquik",
  "posts": [],
  "warnings": ["xquik request failed: ..."]
}
```

## Cache

Cache path:

```text
{cache_dir}/{username}-{YYYY-MM-DD}.json
```

Example:

```text
/home/hermesads/xauusd-leads/research-cache/goldtrader-2026-06-27.json
```

Rules:

- Username is lowercase without `@`.
- Date is UTC `YYYY-MM-DD`.
- Same-day cache is reused.
- Cached output is returned with `cache_hit: true`.
- Corrupt cache is ignored and replaced when a lookup succeeds or skips.

## Common Errors

`XQUIK_API_KEY is not set`

- Meaning: backend unavailable.
- Recovery: set `XQUIK_API_KEY` or run CSV-only enrichment.
- Pipeline action: mark research skipped.

`xquik request failed`

- Meaning: network, auth, rate limit, or service error.
- Recovery: inspect API key, account quota, and network.
- Pipeline action: mark research failed, continue CSV-only.

`timeout after Ns`

- Meaning: lookup exceeded timeout.
- Recovery: lower selected account count, retry manually if needed.
- Pipeline action: mark failed, continue CSV-only.

`Xquik returned no usable target-authored posts`

- Meaning: backend response was valid, but no returned text post could be verified as authored by the requested username.
- Recovery: inspect raw cache/output manually if needed.
- Pipeline action: keep evidence empty and continue.

`cache write failed`

- Meaning: cache directory permission issue.
- Recovery:

```bash
sudo mkdir -p /home/hermesads/xauusd-leads/research-cache
sudo chown -R hermesads:hermesads /home/hermesads/xauusd-leads
```

## Recovery Steps

If one lookup fails:

- Do not retry more than once manually.
- Keep CSV-only enrichment for that lead.
- Continue the main pipeline.

If the helper keeps failing during an operational run:

- Disable Phase 2B for that run.
- Verify final CSV still writes.
- Diagnose Xquik separately.

If cache is corrupt:

- Delete only the affected cache file.
- Re-run the single lookup manually.

If output is not JSON:

- Treat lookup as failed.
- Do not feed it to Hermes as evidence.

## Quality Verification

After a selective-research run, verify:

- No more than 1 username was researched.
- No username researched twice.
- Cache files exist for completed/skipped/failed lookups.
- `recent_x_status` is present for every enriched lead.
- `recent_x_summary` is short.
- `reason` uses research evidence only when `recent_x_status` is `completed`.
- Non-selected leads have `recent_x_status: "skipped"`, empty `recent_x_summary`, and `recent_x_cache_hit: false`.
- Helper warnings, if preserved, are stored only in JSON-internal audit fields.
- Helper posts, if preserved, are stored only in JSON-internal audit fields and never copied wholesale into the final CSV.
- Final CSV columns remain exactly:

```text
Name
Username X
First-line cá nhân hóa
Score fit
Hook
```

## Local Helper Tests

These tests do not call real Xquik.

From repo root:

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

Expected:

- JSON only.
- `username` is `@goldtrader`.
- `status` is `skipped`.
- `source` is `none`.
- Cache file exists at `/tmp/recent-x-cache-test/goldtrader-YYYY-MM-DD.json`.

Run it again:

```bash
python3 skill-md/enrich-xauusd-leads-full/scripts/recent_x_activity.py \
  --username "@GoldTrader" \
  --query "@GoldTrader XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /tmp/recent-x-cache-test \
  --timeout 5 \
  --emit json
```

Expected:

- `cache_hit` is `true`.

Manual real Xquik test:

```bash
export XQUIK_API_KEY="<secret>"

python3 skill-md/enrich-xauusd-leads-full/scripts/recent_x_activity.py \
  --username "@GoldTrader" \
  --query "@GoldTrader XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /tmp/recent-x-cache-test \
  --timeout 120 \
  --emit json
```

Only run the real test intentionally. Do not run it in automated tests.
