---
name: enrich-xauusd-leads-full
description: "Enrich X/Twitter raw_leads.csv files for XAUUSD/gold trading lead generation: have Hermes normalize Apify lead rows, optionally use last30days for recent activity, score fit 1-10, keep score >=7, generate personalized first lines/hooks, and write enriched_leads.csv."
version: 1.1.0
author: Duxq
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Lead-Gen, XAUUSD, Gold, Forex, X, Twitter, CSV, Outreach]
    related_skills: [last30days, xurl]
---

# Enrich_XAUUSD_Leads_Full

## Mục đích

Run a fully automated Hermes enrichment workflow for X/Twitter XAUUSD / Gold Trading leads.

Hermes must orchestrate the whole job:

1. Normalize `raw_leads.csv` with the helper script.
2. Enrich each normalized lead with LLM reasoning. One normalized lead is one unique X account, not one tweet.
3. Use `last30days` only when recent activity would improve scoring or personalization.
4. Keep only leads with `score_fit >= 7`.
5. Write `enriched_leads.normalized.json` automatically.
6. Call the helper script to write `enriched_leads.csv`.

There must be no manual JSONL editing or manual decision file editing.

## Output Contract

Final CSV must be named `enriched_leads.csv` unless the user asks for another path.

Final CSV must contain exactly these columns:

```text
Name
Username X
First-line cá nhân hóa
Score fit
Hook
```

## Helper Script Contract

The helper script is deterministic only. It must not score leads, generate copy, call models, call `last30days`, scrape X/Twitter, or use external APIs.

Use it only for:

- reading CSV
- normalizing headers
- validating row shape
- writing normalized JSON
- validating Hermes-produced enrichment JSON
- writing final CSV

## Execution Flow

### Step 1: Locate Files

Use the current working directory unless the user provides explicit paths.

Expected input:

```text
raw_leads.csv
```

Expected intermediate files:

```text
normalized_leads.json
enriched_leads.normalized.json
```

Expected output:

```text
enriched_leads.csv
```

### Step 2: Normalize Raw Leads

Call the helper script first:

```bash
python scripts/enrich_xauusd_leads.py normalize raw_leads.csv --output normalized_leads.json
```

If running from outside the skill directory, use the absolute path to `scripts/enrich_xauusd_leads.py`.

The helper writes JSON like:

```json
{
  "schema_version": "xauusd-leads-normalized/v1",
  "source_file": "raw_leads.csv",
  "raw_row_count": 2,
  "lead_count": 1,
  "unique_user_count": 1,
  "leads": [
    {
      "row_id": 1,
      "csv_row_numbers": [2, 3],
      "raw_row_count": 2,
      "name": "Gold Macro Notes",
      "username": "@goldmacronotes",
      "bio": "XAUUSD trader. London session charts and risk plans.",
      "profile_url": "https://x.com/goldmacronotes",
      "location": "London UK",
      "followers_count": "18400",
      "country": "UK",
      "source_query": "XAUUSD trader UK",
      "recent_tweets": [
        {
          "text": "XAUUSD respected the 4H supply zone.",
          "created_at": "2026-06-20T09:15:00Z",
          "favorite_count": 42,
          "csv_row_number": 2
        }
      ]
    }
  ]
}
```

The helper deduplicates raw Apify tweet rows by X handle. It normalizes handles case-insensitively, strips a leading `@`, and prefers `user.handle`, then `handle`, then `username`. Multiple tweet rows for the same account become one lead with `recent_tweets`, capped at 3 tweets sorted by newest `created_at` first, then highest `favorite_count`.

### Step 3: Enrich Leads Automatically

Read `normalized_leads.json`. For each unique X account, decide score and copy using the scoring and safety rules below. Do not score the same username twice and do not output duplicate usernames.

Use `recent_tweets` as evidence. The personalized first-line may reference the best tweet or recent-tweets pattern, but only if the evidence is present in `normalized_leads.json` or a successful `last30days` result.

Use this internal enrichment object shape:

```json
{
  "row_id": 1,
  "name": "Gold Macro Notes",
  "username": "@goldmacronotes",
  "profile_url": "https://x.com/goldmacronotes",
  "score_fit": 9,
  "first_line": "Saw your XAUUSD supply-zone note; your patience around confirmation stood out.",
  "hook": "Gold traders who wait for confirmation usually care about cleaner risk zones.",
  "evidence": "bio mentions XAUUSD; tweet discusses gold supply zone",
  "recent_activity_used": false
}
```

Only `name`, `username`, `score_fit`, `first_line`, and `hook` are needed for the final CSV, but keep `evidence` in the intermediate JSON to make the run auditable.

### Step 4: Use last30days Selectively

Use `last30days` when:

- The lead has a username or profile URL.
- The lead appears relevant or borderline from CSV context.
- Recent activity would materially improve score confidence or personalization.
- The raw CSV has weak/short tweet text.

Do not use `last30days` when:

- The row is obvious spam.
- The row is unrelated.
- The row has no usable X username/profile URL.
- The CSV already provides enough evidence for a confident score.

If `last30days` fails, returns no recent activity, or lacks evidence, do not invent recent activity. Score conservatively using only the normalized CSV fields.

### Step 5: Write Enriched JSON Automatically

Hermes must create `enriched_leads.normalized.json` itself. Do not ask the user to edit it.

The file may be either a list:

```json
[
  {
    "row_id": 1,
    "name": "Gold Macro Notes",
    "username": "@goldmacronotes",
    "score_fit": 9,
    "first_line": "Saw your XAUUSD supply-zone note; your patience around confirmation stood out.",
    "hook": "Gold traders who wait for confirmation usually care about cleaner risk zones."
  }
]
```

or an object:

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

Include all processed leads or only kept leads. The helper will filter out any lead with `score_fit < 7`.

### Step 6: Write Final CSV

Call the helper script:

```bash
python scripts/enrich_xauusd_leads.py write --input enriched_leads.normalized.json --output enriched_leads.csv
```

Then inspect the CSV header and confirm the row count.

## Input Columns

The raw CSV may include Apify-style columns:

- `name`
- `username`
- `bio`
- `tweet text`
- `profile URL`
- `location`
- `createdAt`
- `favorite_count`
- `followers_count`
- `country`
- `source query`

The helper accepts common header variants and normalizes them.

## Countries

Use country/query context when available:

| Group | Countries |
|---|---|
| English easier | UK, Canada, Germany |
| Europe mixed languages | France, Italy, Poland |
| Middle East / Arabic | UAE, Saudi Arabia |

Use English outreach by default. If the raw profile/tweet context is clearly non-English, keep the first-line natural and simple; do not force slang or over-localize.

## Scoring

Score from 1 to 10 for XAUUSD / forex / gold trading lead generation.

High score signals:

- Talks about `XAUUSD`, gold trading, forex, commodities, trading setups, signals, chart analysis, risk management, or market structure.
- Bio suggests trader, investor, signal user, finance account, trading community member, prop firm trader, or trading education audience.
- Recently active within 30 days.
- Posts market analysis, trading screenshots, entries, SL/TP, gold news, or education.
- Country/query context matches Canada, UK, Germany, France, Italy, Poland, UAE, or Saudi Arabia.

Low score signals:

- Inactive or no recent evidence.
- Bot/spam/giveaway profile.
- Generic crypto spam with no forex/gold angle.
- Unrelated lifestyle, entertainment, politics, or adult content.
- No trading/investing interest.
- Empty bio and weak tweet context.

Suggested score bands:

| Score | Meaning |
|---|---|
| 9-10 | Strong XAUUSD/gold/forex fit with recent relevant activity |
| 7-8 | Good finance/trading fit or likely trading audience |
| 5-6 | Weak/borderline; do not keep unless new evidence improves fit |
| 1-4 | Unrelated, inactive, spam, or unsafe |

Keep only score `>= 7`.

## Personalization Rules

For `first_line`:

- Write one short, natural first-line.
- Refer only to evidence from CSV or `last30days`.
- Do not invent recent posts, profits, location, identity, or trading behavior.
- Do not sound spammy or generic.
- Avoid fake flattery.

Good:

```text
Saw your recent gold chart notes; your focus on entry zones stood out.
```

Bad:

```text
I saw you made huge profits trading gold last week.
```

For `hook`:

- Write one short outreach hook.
- Keep it relevant to gold/forex/trading discipline.
- Do not promise profit, guaranteed income, win rate, risk-free results, or financial certainty.

Safe hook examples:

```text
Gold traders who care about cleaner entries usually watch the same risk zones.
```

```text
If you trade XAUUSD, cleaner planning usually starts before price reaches the zone.
```

## Safety Rules

- Do not promise profit.
- Do not write guaranteed-income claims.
- Do not say `100% win`, `risk-free`, `guaranteed profit`, or similar.
- Do not invent facts about the lead.
- Do not fabricate recent activity.
- Do not include aggressive pressure, fake scarcity, or misleading claims.
- Keep outreach natural, short, and human.

## Verification Checklist

- [ ] `normalize` ran successfully and produced `normalized_leads.json`.
- [ ] Normalized leads are unique X accounts; duplicate raw tweet rows are merged into `recent_tweets`.
- [ ] Hermes generated `score_fit`, `first_line`, and `hook`; Python did not.
- [ ] `last30days` was used only when useful and never fabricated.
- [ ] `enriched_leads.normalized.json` was created automatically by Hermes.
- [ ] `write` produced `enriched_leads.csv`.
- [ ] `enriched_leads.csv` has exactly the 5 required columns.
- [ ] `enriched_leads.csv` has no duplicate usernames.
- [ ] Every output row has `Score fit >= 7`.
- [ ] First-lines are evidence-based.
- [ ] Hooks do not promise profit or risk-free trading.
