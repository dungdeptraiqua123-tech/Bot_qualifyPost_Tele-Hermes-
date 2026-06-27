# Recent X Activity Regression Plan

## Purpose

This regression plan verifies that Hermes orchestrates the project-owned Recent X Activity helper without hallucinating, inventing, or overusing helper output.

The helper is already tested standalone. These tests focus on Hermes behavior after receiving helper-style JSON.

Hermes may only use these helper fields:

- `status`
- `cache_hit`
- `posts`
- `evidence.summary`
- `evidence.themes`
- `evidence.persona_hint`
- `evidence.recent_activity`
- `warnings`

No other helper fields may be used to make claims, change scores, change persona, create themes, generate first-lines, generate hooks, or add reasons.

## Prerequisites

- Local skill source exists at `skill-md/enrich-xauusd-leads-full/`.
- Runtime skill is deployed to `/opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/`.
- Hermes runtime uses `HERMES_HOME=/opt/hermes-ads/hermes-home`.
- A small test folder contains a representative `raw_leads.csv`.
- Fixture JSONs are available under `examples/recent-x-fixtures/`.
- Do not call real Xquik during regression tests.
- Do not use production secrets.

## Test Input Strategy

Use a tiny `raw_leads.csv` with one or two borderline XAUUSD accounts that qualify for Phase 2B selection:

- CSV-only score should be around 7 or 8.
- CSV evidence should be thin, weak, or ambiguous enough that Recent X Activity would normally be selected.
- Include `recent_tweets` or Apify tweet rows that do not already prove every tested claim.

For each fixture, run Hermes with a prompt that tells it to treat the fixture as the exact JSON returned by `scripts/recent_x_activity.py`. This avoids real Xquik and isolates orchestration behavior.

Example prompt shape:

```text
Enrich /tmp/xauusd-regression/raw_leads.csv and write enriched_leads.csv.
For this regression test, do not call real Xquik.
Assume scripts/recent_x_activity.py returned exactly the JSON in:
skill-md/enrich-xauusd-leads-full/examples/recent-x-fixtures/completed_posts_summary.json
Apply the Recent X Activity orchestration rules exactly.
```

## Manual Verification Commands

Run Hermes from the working folder:

```bash
cd /tmp/xauusd-regression
HERMES_HOME=/opt/hermes-ads/hermes-home /opt/hermes-ads/venvs/hermes/bin/hermes chat --skills enrich-xauusd-leads-full --yolo "Enrich /tmp/xauusd-regression/raw_leads.csv and write enriched_leads.csv. For this regression test, do not call real Xquik. Assume scripts/recent_x_activity.py returned exactly the JSON in skill-md/enrich-xauusd-leads-full/examples/recent-x-fixtures/completed_posts_summary.json. Apply the Recent X Activity orchestration rules exactly."
```

Check output files:

```bash
test -f /tmp/xauusd-regression/enriched_leads.normalized.json
test -f /tmp/xauusd-regression/enriched_leads.csv
```

Check CSV header:

```bash
python3 -c 'import csv; p="/tmp/xauusd-regression/enriched_leads.csv"; print(next(csv.reader(open(p, newline="", encoding="utf-8"))))'
```

Expected header:

```text
['Name', 'Username X', 'First-line cá nhân hóa', 'Score fit', 'Hook']
```

Inspect internal audit fields:

```bash
python3 -c 'import json; p="/tmp/xauusd-regression/enriched_leads.normalized.json"; data=json.load(open(p, encoding="utf-8")); leads=data.get("leads", data if isinstance(data, list) else []); print([(x.get("username"), x.get("recent_x_status"), x.get("recent_x_summary"), x.get("recent_x_cache_hit")) for x in leads])'
```

Scan CSV for forbidden audit data:

```bash
python3 -c 'from pathlib import Path; s=Path("/tmp/xauusd-regression/enriched_leads.csv").read_text(encoding="utf-8"); bad=["schema_version","cache_hit","warnings","recent_x_status","recent_x_summary","recent_x_cache_hit","xquik request failed"]; print([x for x in bad if x in s])'
```

The forbidden audit-data scan must print:

```text
[]
```

## Cases

### 1. Completed With Posts And Summary

Fixture:

```text
examples/recent-x-fixtures/completed_posts_summary.json
```

Expected Hermes behavior:

- `recent_x_status = "completed"`.
- `recent_x_summary` is copied exactly from `evidence.summary`.
- `recent_x_cache_hit` equals fixture `cache_hit`.
- Hermes may refine `score_fit`, `persona`, `trading_themes`, `style_summary`, `reason`, `first_line`, or `hook`.
- Any new helper-backed reason must trace directly to `posts`, `evidence.summary`, `evidence.themes`, or `evidence.persona_hint`.

Reject conditions:

- `recent_x_summary` is rewritten, shortened, polished, or embellished.
- Any claim appears that is not present in helper JSON or CSV evidence.
- Raw helper posts or warnings appear in CSV.

### 2. Completed With Empty Posts And Empty Summary

Fixture:

```text
examples/recent-x-fixtures/completed_empty_posts_empty_summary.json
```

Expected Hermes behavior:

- `recent_x_status = "completed"`.
- `recent_x_summary = ""`.
- `recent_x_cache_hit` equals fixture `cache_hit`.
- No score change from helper output.
- No invented negative evidence.
- Empty posts means `No additional recent-X evidence`, not inactivity proof.

Reject conditions:

- Hermes treats the lookup as failed.
- Hermes lowers `score_fit` because `posts` is empty.
- Hermes adds reasons such as `inactive recently`, `no recent activity`, or `weak recent activity` unless CSV-only evidence independently supports them.

### 3. Skipped

Fixture:

```text
examples/recent-x-fixtures/skipped_no_backend.json
```

Expected Hermes behavior:

- Continue CSV-only.
- `recent_x_status = "skipped"`.
- `recent_x_summary = ""`.
- `recent_x_cache_hit` equals fixture `cache_hit` if present, otherwise `false`.
- No helper-based reason.

Reject conditions:

- Score, persona, themes, first-line, or hook change because of skipped helper output.
- Warning text appears in CSV.
- Hermes invents research conclusions.

### 4. Failed

Fixture:

```text
examples/recent-x-fixtures/failed_timeout.json
```

Expected Hermes behavior:

- Continue CSV-only.
- `recent_x_status = "failed"`.
- `recent_x_summary = ""`.
- No helper-based score change.
- No helper-based reason.

Reject conditions:

- Pipeline stops.
- CSV is not produced.
- Failed helper content affects lead quality.

### 5. Invalid Schema Version

Fixture:

```text
examples/recent-x-fixtures/invalid_schema_version.json
```

Expected Hermes behavior:

- Treat lookup as failed.
- Ignore all helper content, including posts, summary, themes, and persona hint.
- Continue CSV-only.
- `recent_x_status = "failed"`.

Reject conditions:

- Hermes uses posts, themes, persona, or summary from invalid schema.
- Score, persona, or themes change because of invalid helper output.

### 6. Completed With Warnings

Fixture:

```text
examples/recent-x-fixtures/completed_with_warnings.json
```

Expected Hermes behavior:

- `recent_x_status = "completed"`.
- `recent_x_summary` is copied exactly from `evidence.summary`.
- Warnings may be stored only in internal JSON audit fields.
- Warnings do not affect score, persona, themes, first-line, hook, or reason.
- Warnings never appear in CSV.

Reject conditions:

- Warning text appears in `First-line cá nhân hóa` or `Hook`.
- Hermes treats warnings as lead-quality evidence.

### 7. Completed With Cache Hit

Fixture:

```text
examples/recent-x-fixtures/completed_cache_hit.json
```

Expected Hermes behavior:

- `recent_x_cache_hit = true`.
- `recent_x_status = "completed"`.
- If schema is valid, evidence can be used normally.
- Cache hit alone does not change score.

Reject conditions:

- Score changes because `cache_hit = true`.
- Cache metadata appears in CSV.

### 8. Helper Evidence Contradicts CSV-Only Impression

Fixture:

```text
examples/recent-x-fixtures/completed_contradicts_csv_spam_signal.json
```

Scenario:

- CSV-only score is around 7.
- Helper posts and summary explicitly show spammy signal behavior or non-XAUUSD multi-asset promotion.

Expected Hermes behavior:

- Hermes may lower score only if helper `posts`, `evidence.summary`, `evidence.themes`, or `evidence.persona_hint` explicitly support the downgrade.
- New reasons must cite helper-supported evidence.
- No broader invented claims.

Reject conditions:

- Score is lowered from intuition.
- Hermes invents Telegram links, VIP claims, guaranteed profit claims, or unrelated spam claims not present in the fixture.
- Persona or themes change without direct fixture support.

## CSV Contract Checks

Every case must produce `enriched_leads.csv` with exactly:

```text
Name
Username X
First-line cá nhân hóa
Score fit
Hook
```

CSV must not contain:

- `recent_x_status`
- `recent_x_summary`
- `recent_x_cache_hit`
- `schema_version`
- `cache_hit`
- `warnings`
- raw `posts`
- helper error text

## Audit Field Checks

Every lead in `enriched_leads.normalized.json` must include:

- `recent_x_status`
- `recent_x_summary`
- `recent_x_cache_hit`

For non-selected leads:

- `recent_x_status = "skipped"`
- `recent_x_summary = ""`
- `recent_x_cache_hit = false`

For completed helper output:

- `recent_x_summary` must exactly equal fixture `evidence.summary`.
- `recent_x_cache_hit` must equal fixture `cache_hit`.

For skipped, failed, or invalid-schema output:

- no helper-backed reason
- no helper-backed score change
- no helper-backed persona or theme change

## Acceptance Criteria

A regression run passes when:

- Hermes writes both `enriched_leads.normalized.json` and `enriched_leads.csv`.
- CSV header is exactly the five required columns.
- CSV contains no helper audit fields, warnings, raw posts, or schema metadata.
- `recent_x_summary` exactly equals `evidence.summary` when helper status is completed.
- `completed` with empty posts remains completed and does not lower score by itself.
- `skipped`, `failed`, and invalid-schema fixtures do not influence lead quality.
- Every helper-backed reason traces to `posts`, `evidence.summary`, `evidence.themes`, or `evidence.persona_hint`.
- Hermes does not invent recent activity, engagement, Telegram links, VIP links, profit claims, persona changes, themes, or score reasons.
- `recent_x_cache_hit` mirrors fixture `cache_hit`.
- Warnings are audit-only and never exposed in CSV.

## Future Automation

Do not add a Python harness yet. After several manual runs stabilize the Hermes output shape, add a deterministic evaluator that checks:

- CSV header contract.
- forbidden CSV text.
- audit field presence.
- exact `recent_x_summary` copy behavior.
- no helper influence for skipped, failed, invalid-schema, or empty completed cases.
