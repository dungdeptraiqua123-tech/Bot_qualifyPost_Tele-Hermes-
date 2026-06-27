# Phase 2 Runbook: Enrich XAUUSD Leads Full

This is the canonical Phase 2 reference for `skill-md/enrich-xauusd-leads-full/`.

Phase 2 covers selective Recent X Activity enrichment for XAUUSD / gold trading lead qualification. It does not cover Google Sheets, GitHub sync, CRM, production monitoring, or broad web research.

## 1. Purpose

Phase 2 improves lead quality after the CSV-only MVP.

The MVP already handles:

- reading Apify `raw_leads.csv`
- normalizing tweet rows into unique X accounts
- scoring accounts with Hermes / LLM reasoning
- writing `enriched_leads.csv`

Phase 2 adds a project-owned Recent X Activity helper for a narrow problem: when CSV evidence is thin but a lead looks promising, Hermes may check recent target-authored X activity for one selected account.

Recent X Activity exists because Apify rows are tweet snapshots, not a complete account view. A borderline lead may need a small amount of fresh account-owned evidence before Hermes can confidently refine score, persona, themes, and outreach copy.

The project no longer depends on `last30days` as the enrichment engine because `last30days` is intentionally broad and heavy. It can search many sources, produce broad reports, and carry operational complexity that is not needed for this lead-generation pipeline. Phase 2 needs only a bounded X-only recent activity check.

The project owns its own helper so the lead pipeline controls:

- exact X-only scope
- `from:<username>` account ownership behavior
- same-day cache
- timeout and failure isolation
- deterministic JSON schema
- evidence extraction rules
- no markdown or HTML output
- no LLM calls inside the helper

Hermes remains the orchestrator. Python helpers stay deterministic.

## 2. High-Level Architecture

```text
raw_leads.csv
  |
  v
normalize
  |
  v
normalized_leads.json
  |
  v
CSV-only scoring
  |
  v
candidate selection
  |
  v
Recent X Activity helper
  |
  v
merge evidence
  |
  v
enriched_leads.normalized.json
  |
  v
write
  |
  v
enriched_leads.csv
```

Stage responsibilities:

- `raw_leads.csv`: Apify export. It may contain multiple tweet rows for the same X account.
- `normalize`: deterministic Python step that reads CSV, normalizes headers, validates rows, deduplicates by handle, and merges recent tweets.
- `normalized_leads.json`: account-level JSON where one lead equals one unique X account.
- CSV-only scoring: Hermes reasons over normalized CSV evidence first. This is the primary evidence source.
- candidate selection: Hermes selects at most one uncertain, high-potential score 7-8 account for Recent X Activity.
- Recent X Activity helper: deterministic X-only evidence collector. It returns JSON only.
- merge evidence: Hermes reads helper JSON, validates schema, applies evidence policy, and refines only when helper output explicitly supports the change.
- `enriched_leads.normalized.json`: Hermes-produced internal JSON with audit fields and all enrichment decisions.
- `write`: deterministic Python step that validates enriched JSON and writes the final CSV.
- `enriched_leads.csv`: final human-facing lead export with exactly five columns.

## 3. Runtime Components

### `SKILL.md`

Owns Hermes orchestration instructions.

It defines:

- full enrichment workflow
- scoring rubric
- persona and theme rules
- Recent X Activity selection rules
- helper command shape
- helper evidence policy
- final CSV contract

Hermes uses this file to decide what to do. Do not put secrets in it.

### `scripts/enrich_xauusd_leads.py`

Owns deterministic CSV and JSON file handling.

Commands:

```bash
python scripts/enrich_xauusd_leads.py normalize raw_leads.csv --output normalized_leads.json
python scripts/enrich_xauusd_leads.py write --input enriched_leads.normalized.json --output enriched_leads.csv
```

It must not:

- score leads
- generate first-lines
- generate hooks
- call LLMs
- call Xquik
- call Recent X Activity
- call external APIs

### `scripts/recent_x_activity.py`

Owns deterministic Recent X Activity lookup.

It:

- accepts a username and query
- uses Xquik when `XQUIK_API_KEY` is present
- queries recent X activity with `from:<username>` and date window
- keeps only target-authored tweets
- discards other authors, mentions, replies by other users, and quoted tweets by other users
- extracts deterministic keyword evidence
- writes same-day cache
- returns JSON only

It must not:

- call an LLM
- write CSV
- generate outreach copy
- score leads
- output markdown or HTML

### `references/recent-x-activity-output-schema.md`

Owns the helper JSON contract.

It documents:

- schema version
- top-level fields
- `posts` shape
- `evidence` shape
- status meanings
- failure contract
- completed-empty behavior

Hermes must validate:

```text
schema_version == "recent-x-activity/v1"
```

before using helper output.

### `references/recent-x-activity-sop.md`

Owns operational helper procedures.

It documents:

- prerequisites
- environment variables
- preflight checks
- run command
- cache behavior
- common errors
- recovery steps
- quality verification

### `references/recent-x-activity-regression-plan.md`

Owns Phase 2 orchestration regression testing.

It documents:

- fixture strategy
- manual regression commands
- expected Hermes behavior per helper status
- reject conditions
- acceptance criteria

### `examples/`

Owns local examples and fixtures.

Current contents:

- `raw_leads.sample.csv`: small deterministic normalize/write sample.
- `recent-x-fixtures/`: static helper-output fixtures for manual regression.

### `evaluation/`

Reserved for future evaluation automation. It does not currently exist in this skill source. When Phase 5 begins, this should contain deterministic evaluators and benchmark reports, not production pipeline logic.

## 4. Internal Data Flow

```text
raw rows
  |
  v
normalized accounts
  |
  v
internal reasoning fields
  |
  v
recent_x fields
  |
  v
CSV export
```

Raw rows:

- input comes from Apify
- rows are tweet-level, not account-level
- duplicate usernames are expected

Normalized accounts:

- one normalized lead equals one unique X account
- handles are normalized case-insensitively
- duplicate tweet rows merge into `recent_tweets`
- up to 3 recent/best tweets are kept per account

Internal reasoning fields:

- `score_fit`
- `persona`
- `style_summary`
- `reason`
- `evidence`

Recent X fields:

- `recent_x_status`
- `recent_x_summary`
- `recent_x_cache_hit`

CSV export fields:

- `Name`
- `Username X`
- `First-line cá nhân hóa`
- `Score fit`
- `Hook`

JSON-only fields:

- `score_fit`
- `persona`
- `style_summary`
- `reason`
- `evidence`
- `recent_x_status`
- `recent_x_summary`
- `recent_x_cache_hit`
- helper `posts` if stored for audit
- helper `warnings` if stored for audit

Only the final five CSV columns may appear in `enriched_leads.csv`.

## 5. Recent X Activity

### Selection Rules

Hermes scores every lead using CSV evidence first. Then it may select at most one account per run.

Select only one lead that best matches:

- `score_fit` is 7 or 8
- high-potential account with thin CSV evidence
- missing or weak `recent_tweets`
- unclear persona
- low confidence

Priority:

1. Score 8 before score 7.
2. Missing or weak `recent_tweets`.
3. Strong bio/source-query match for XAUUSD, gold, forex, or trading.
4. Higher CSV account-quality signals.
5. Most unclear persona where Recent X Activity could materially improve first-line or hook.

### Skip Rules

Skip Recent X Activity when:

- user says `Do not use Recent X Activity`
- `score_fit <= 6`
- `score_fit >= 9` with strong CSV evidence
- account is obvious spam, irrelevant, fake-profit, adult, crypto-only with no gold/forex angle, or low-information
- the username was already researched in the same run
- one lookup has already been attempted in the run

Every non-selected lead must receive:

```json
{
  "recent_x_status": "skipped",
  "recent_x_summary": "",
  "recent_x_cache_hit": false
}
```

### Command

Template:

```bash
python3 {skill_dir}/scripts/recent_x_activity.py \
  --username "@username" \
  --query "@username XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /home/hermesads/xauusd-leads/research-cache \
  --timeout 120 \
  --emit json
```

VPS command:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/recent_x_activity.py \
  --username "@username" \
  --query "@username XAUUSD gold trading" \
  --window-days 30 \
  --cache-dir /home/hermesads/xauusd-leads/research-cache \
  --timeout 120 \
  --emit json
```

### Cache

Cache directory:

```text
/home/hermesads/xauusd-leads/research-cache/
```

Cache key:

```text
lowercase username without @ + current date
```

Example:

```text
/home/hermesads/xauusd-leads/research-cache/goldmacronotes-2026-06-27.json
```

Hermes uses helper `cache_hit` to set `recent_x_cache_hit`.

### Timeout

Max time per lookup:

```text
120 seconds
```

Timeout must not stop the pipeline. Treat it as failed and continue CSV-only.

### Schema Validation

Before using helper output, Hermes must validate:

```text
schema_version == "recent-x-activity/v1"
```

If schema is missing or different:

- treat as failed
- ignore helper content
- continue CSV-only

### Status Handling

`completed`:

- valid helper response
- may have posts or empty posts
- use only allowed fields
- copy `evidence.summary` exactly into `recent_x_summary`
- set `recent_x_cache_hit` from `cache_hit`

`skipped`:

- helper did not run or backend unavailable
- continue CSV-only
- no helper-based reason

`failed`:

- timeout, request error, invalid JSON, wrong schema, or helper failure
- continue CSV-only
- no helper-based reason

Invalid schema:

- treat as failed
- ignore helper content

Empty completed:

- `status = "completed"` with `posts = []` and/or `evidence.summary = ""` is valid
- means no additional Recent X evidence
- is not negative evidence
- do not lower score just because posts are empty

### Author Validation

The helper queries with account ownership in mind:

```text
from:<username>
```

It then validates returned records and keeps only tweets authored by the target handle.

The helper discards:

- other authors
- mentions of the account by other users
- replies written by other users
- quoted tweets by other users
- nested non-target records

### Xquik

Xquik is the current backend when `XQUIK_API_KEY` is present.

If `XQUIK_API_KEY` is missing, the helper returns `status = "skipped"` and the pipeline continues CSV-only.

Do not commit or print the key.

## 6. Evidence Policy

CSV evidence comes first.

Hermes must score each account using normalized CSV evidence before Recent X Activity is considered.

Recent X Activity comes second.

It is a selective assist for one uncertain account, not the main enrichment engine.

The Recent X helper is the single source of truth for Phase 2 evidence.

Hermes may use only:

- `status`
- `cache_hit`
- `posts`
- `evidence.summary`
- `evidence.themes`
- `evidence.persona_hint`
- `evidence.recent_activity`
- `warnings`

No hallucination policy:

- If helper JSON does not contain evidence for a claim, do not state it.
- If `posts = []`, treat it as no additional Recent X evidence.
- If `evidence.summary = ""`, treat it as no additional Recent X evidence.
- Do not invent engagement.
- Do not invent Telegram links.
- Do not invent VIP/channel behavior.
- Do not invent multi-asset behavior.
- Do not invent persona changes.
- Do not invent trading themes.
- Do not invent reasons from intuition.
- Do not treat warnings as lead-quality evidence.

Score adjustment policy:

- raise or lower `score_fit` only when helper `posts`, `evidence.summary`, `evidence.themes`, or `evidence.persona_hint` explicitly supports the change
- leave `score_fit` unchanged if helper output does not explicitly support a score change
- never change score based only on `cache_hit`, `status`, `warnings`, empty `posts`, or empty `summary`

Reason policy:

- every helper-backed reason must trace to helper summary, posts, themes, or persona hint
- warnings are audit-only
- helper posts may be stored internally for audit but must not appear in CSV

## 7. CSV Contract

Final CSV must contain exactly:

```text
Name
Username X
First-line cá nhân hóa
Score fit
Hook
```

This contract must never change without a version bump and explicit downstream coordination.

CSV must not contain:

- `persona`
- `style_summary`
- `reason`
- `evidence`
- `recent_x_status`
- `recent_x_summary`
- `recent_x_cache_hit`
- helper warnings
- helper posts
- helper schema metadata
- cache metadata

## 8. Regression Testing

Regression docs:

```text
references/recent-x-activity-regression-plan.md
```

Fixture directory:

```text
examples/recent-x-fixtures/
```

Fixtures:

- `completed_posts_summary.json`
- `completed_empty_posts_empty_summary.json`
- `skipped_no_backend.json`
- `failed_timeout.json`
- `invalid_schema_version.json`
- `completed_with_warnings.json`
- `completed_cache_hit.json`
- `completed_contradicts_csv_spam_signal.json`

Manual regression strategy:

1. Prepare a tiny `raw_leads.csv` with one or two borderline accounts.
2. Run Hermes with the skill.
3. Prompt Hermes not to call real Xquik.
4. Tell Hermes to treat one fixture as the exact helper output.
5. Inspect `enriched_leads.normalized.json`.
6. Inspect `enriched_leads.csv`.

Example command:

```bash
cd /tmp/xauusd-regression
HERMES_HOME=/opt/hermes-ads/hermes-home /opt/hermes-ads/venvs/hermes/bin/hermes chat --skills enrich-xauusd-leads-full --yolo "Enrich /tmp/xauusd-regression/raw_leads.csv and write enriched_leads.csv. For this regression test, do not call real Xquik. Assume scripts/recent_x_activity.py returned exactly the JSON in skill-md/enrich-xauusd-leads-full/examples/recent-x-fixtures/completed_posts_summary.json. Apply the Recent X Activity orchestration rules exactly."
```

Verify:

- CSV header is exactly five columns.
- no helper audit fields appear in CSV.
- `recent_x_summary` equals helper `evidence.summary` exactly.
- skipped/failed/invalid-schema fixtures do not influence lead quality.
- completed-empty does not lower score by itself.
- warnings remain JSON-only.
- cache hit is copied into `recent_x_cache_hit`.
- every helper-backed reason traces to allowed helper evidence.

Acceptance criteria:

- pipeline writes both output files
- no duplicate usernames in CSV
- every CSV row has `Score fit >= 7`
- no hallucinated Recent X evidence
- no raw helper posts or warnings in CSV
- no score changes unsupported by helper output or CSV evidence

## 9. Operational Runbook

### Deployment

Local source:

```text
skill-md/enrich-xauusd-leads-full/
```

Runtime target:

```text
/opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/
```

Deploy with a copy/sync command appropriate to the VPS environment, then ensure ownership:

```bash
sudo chown -R hermesads:hermesads /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full
```

### Restart

Hermes gateway runs under:

```text
hermes-api.service
```

Restart when the runtime skill source changes:

```bash
sudo systemctl restart hermes-api.service
```

Check status:

```bash
sudo systemctl status hermes-api.service --no-pager
```

### Cache

Cache directory:

```text
/home/hermesads/xauusd-leads/research-cache/
```

Create and set permissions:

```bash
sudo mkdir -p /home/hermesads/xauusd-leads/research-cache
sudo chown -R hermesads:hermesads /home/hermesads/xauusd-leads
```

### Permissions

Runtime user:

```text
hermesads
```

The runtime user needs:

- read access to the deployed skill
- execute/read access to Python scripts
- write access to the research cache directory
- read/write access to the working folder containing lead CSVs

### Run

No Recent X Activity:

```bash
cd /tmp/xauusd-real
HERMES_HOME=/opt/hermes-ads/hermes-home /opt/hermes-ads/venvs/hermes/bin/hermes chat --skills enrich-xauusd-leads-full --yolo "Enrich /tmp/xauusd-real/raw_leads.csv and write enriched_leads.csv. Do not use Recent X Activity."
```

Selective Recent X Activity:

```bash
cd /tmp/xauusd-real
HERMES_HOME=/opt/hermes-ads/hermes-home /opt/hermes-ads/venvs/hermes/bin/hermes chat --skills enrich-xauusd-leads-full --yolo "Enrich /tmp/xauusd-real/raw_leads.csv and write enriched_leads.csv. Use Recent X Activity only for at most 1 uncertain high-potential score 7-8 lead after CSV-only scoring."
```

### Common Failures

`XQUIK_API_KEY` missing:

- helper returns `status = "skipped"`
- pipeline continues CSV-only
- no helper-based reason or score change

Timeout:

- helper returns or is treated as `status = "failed"`
- pipeline continues CSV-only
- no helper-based reason or score change

Invalid schema:

- Hermes treats helper output as failed
- helper content is ignored
- pipeline continues CSV-only

Helper skipped:

- `recent_x_status = "skipped"`
- `recent_x_summary = ""`
- no helper-based influence

Cache permission failure:

- fix ownership on `/home/hermesads/xauusd-leads`
- rerun or continue CSV-only

Empty completed:

- valid completed lookup
- no additional Recent X evidence
- do not treat as failed
- do not lower score solely because it is empty

## 10. Future Roadmap

These are placeholders only. Do not design or implement them in Phase 2.

Phase 3:

- Google Sheets

Phase 4:

- CRM

Phase 5:

- Evaluation automation

Phase 6:

- Production monitoring
