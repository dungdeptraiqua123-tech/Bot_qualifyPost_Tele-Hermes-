---
name: enrich-xauusd-leads-full
description: "Enrich X/Twitter raw_leads.csv files for XAUUSD/gold trading lead generation: have Hermes normalize Apify lead rows, score fit 1-10 with strict qualification, keep score >=7, generate diverse persona-aware first lines/hooks, and write enriched_leads.csv."
version: 1.3.0
author: Duxq
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Lead-Gen, XAUUSD, Gold, Forex, X, Twitter, CSV, Outreach]
    related_skills: [xurl]
---

# Enrich_XAUUSD_Leads_Full

## Mục đích

Run a fully automated Hermes enrichment workflow for X/Twitter XAUUSD / Gold Trading leads.

Hermes must orchestrate the whole job:

1. Normalize `raw_leads.csv` with the helper script.
2. Enrich each normalized lead with LLM reasoning. One normalized lead is one unique X account, not one tweet.
3. Use only normalized CSV evidence for Phase 1.6 unless the user explicitly asks for external research.
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

Use `recent_tweets` as the primary evidence. Reason over the account as a trader or finance profile, not as a single tweet row. Look for recurring patterns across the bio, source query, country/location context, follower count, and up to 3 recent tweets.

The personalized first-line should be about the trader's apparent style, market focus, or repeated trading behavior. Avoid making it about one isolated tweet unless there is only one usable evidence item. If you reference a specific tweet, frame it as evidence of a broader style.

Before writing the enrichment object, infer:

- `trading_themes`: recurring themes from the taxonomy below.
- `persona`: one best-fit persona from the persona taxonomy below.
- `style_summary`: one short internal phrase describing the trader/account style.
- `reason`: an internal list explaining why the score was assigned.

Do not export `trading_themes`, `persona`, `style_summary`, `reason`, or `evidence` to CSV. They are only for auditability in `enriched_leads.normalized.json`.

Use this internal enrichment object shape:

```json
{
  "row_id": 1,
  "name": "Gold Macro Notes",
  "username": "@goldmacronotes",
  "profile_url": "https://x.com/goldmacronotes",
  "score_fit": 9,
  "trading_themes": ["Price Action", "Gold only"],
  "persona": "Price Action Trader",
  "style_summary": "Intraday price-action analyst focused on gold confirmation zones",
  "first_line": "Your gold notes come across as a patient price-action style, with confirmation around key zones doing most of the filtering.",
  "hook": "For price-action gold traders, the useful edge is often in cleaner zone selection before the entry ever appears.",
  "evidence": {
    "bio": "XAUUSD trader. London session charts and risk plans.",
    "recent_tweets_used": [
      "XAUUSD respected the 4H supply zone.",
      "London open plan: gold needs a clean break before I touch it."
    ]
  },
  "reason": [
    "Bio explicitly positions the account around XAUUSD trading",
    "Recent tweets repeatedly discuss gold levels and confirmation",
    "Uses technical zone language rather than generic market commentary",
    "Shows risk-aware behavior by waiting before entries",
    "Relevant UK source-query context supports fit"
  ],
  "recent_activity_used": false
}
```

Only `name`, `username`, `score_fit`, `first_line`, and `hook` are needed for the final CSV, but keep `trading_themes`, `persona`, `style_summary`, `evidence`, and `reason` in the intermediate JSON to make the run auditable.

## Account-Level Reasoning

Treat each normalized lead as one account profile. Do not let a single noisy tweet override the whole account if the bio and other recent tweets show a consistent trading pattern. Conversely, do not assign a high score from one gold keyword if the account looks unrelated, spammy, inactive, or generic.

Think like a lead qualification system. The goal is not to export every normalized account. A useful run should reject weak accounts. If evidence is thin, repetitive, copied, spammy, crypto-only, or not clearly relevant to XAUUSD/gold/forex, score `6` or below so the helper excludes it from CSV.

Evidence priority:

1. `recent_tweets`: repeated topics, market names, trading method, recency, and engagement.
2. `bio`: self-declared trader/investor/finance/signal/community identity.
3. `source_query` and `country`: acquisition context, never sole proof of fit.
4. `followers_count`: weak supporting signal only; do not score high just because the account is large.
5. External research: do not use in Phase 1.6 unless the user explicitly asks.

When multiple recent tweets are available, summarize the account-level pattern:

- What markets do they repeatedly mention?
- What trading method or language appears more than once?
- Do they appear educational, analytical, signal-driven, personal journal, prop-firm focused, or spammy?
- Do they show current activity and real trading discussion?
- Is the account focused on gold/XAUUSD or broader multi-asset trading?

## Trading Theme Extraction

Populate `trading_themes` with any clearly supported recurring themes. Use only evidence from `bio`, `recent_tweets`, and normalized account fields. Do not infer themes from stereotypes, country, language, or username alone.

Preferred theme labels:

| Theme | Evidence examples |
|---|---|
| ICT | Mentions ICT, liquidity sweep, fair value gap/FVG, order block, displacement, killzone, premium/discount in an ICT-style context |
| SMC | Mentions smart money, BOS/CHOCH, order blocks, liquidity grabs, imbalance, market structure |
| Price Action | Mentions support/resistance, supply/demand, break and retest, candles, trendlines, zones, confirmation |
| Scalping | Mentions scalping, M1/M5/M15, quick entries, London/NY session scalp plans |
| Swing | Mentions swing setups, H4/D1, multi-day holds, higher timeframe bias |
| Prop Firm | Mentions funded accounts, FTMO, prop challenges, drawdown rules, evaluation accounts |
| Gold only | Mostly or exclusively discusses gold, XAUUSD, bullion, or gold market plans |
| Multi-asset | Discusses gold plus forex pairs, indices, crypto, commodities, or macro markets |

If no theme is clearly supported, use an empty list and score conservatively.

## Persona Classification

Populate `persona` with exactly one value from this list:

- `ICT Trader`
- `SMC Trader`
- `Price Action Trader`
- `Gold Analyst`
- `Swing Trader`
- `Scalper`
- `Prop Trader`
- `Educator`
- `Signal Provider`
- `Institutional Trader`
- `Macro Trader`
- `News Trader`
- `Hybrid`

Persona rules:

- Choose `ICT Trader` only when ICT-specific language is explicit or strongly repeated.
- Choose `SMC Trader` when smart-money/structure concepts dominate but ICT is not explicit.
- Choose `Price Action Trader` for chart/zone/confirmation traders without clear ICT/SMC branding.
- Choose `Gold Analyst` for accounts focused on gold commentary, XAUUSD levels, or gold news without clear trade execution style.
- Choose `Swing Trader` or `Scalper` only when timeframe/holding-style evidence supports it.
- Choose `Prop Trader` when funded-account/challenge/drawdown language is visible.
- Choose `Educator` when the account primarily teaches, explains, threads lessons, or builds community.
- Choose `Signal Provider` only when the account mainly posts calls, entries, TP/SL, VIP/channel prompts, or signal marketing. Score strictly; generic or spammy signal providers should usually be `6` or below.
- Choose `Institutional Trader` only for institutional/order-flow/liquidity/desk-style language with original analysis.
- Choose `Macro Trader` for accounts led by macro, rates, USD, data, or cross-market drivers.
- Choose `News Trader` for accounts focused on event/data/news reactions.
- Choose `Hybrid` when two or more styles are genuinely balanced and no single persona dominates.

`persona` is internal-only and must not appear in `enriched_leads.csv`.

### Step 4: External Research

For Phase 1.6, do not call `last30days` or any external API unless the user explicitly asks. Use only `normalized_leads.json` evidence. If normalized evidence is too weak to qualify the lead, score `6` or below instead of researching around the weakness.

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
    "trading_themes": ["Price Action", "Gold only"],
    "persona": "Price Action Trader",
    "style_summary": "Intraday price-action analyst focused on gold confirmation zones",
    "first_line": "Your gold notes come across as a patient price-action style, with confirmation around key zones doing most of the filtering.",
    "hook": "For price-action gold traders, the useful edge is often in cleaner zone selection before the entry ever appears.",
    "reason": [
      "Bio explicitly positions the account around XAUUSD trading",
      "Recent tweets repeatedly discuss gold levels and confirmation",
      "Uses technical zone language rather than generic market commentary",
      "Shows risk-aware behavior by waiting before entries",
      "Relevant UK source-query context supports fit"
    ]
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
      "trading_themes": ["Price Action", "Gold only"],
      "persona": "Price Action Trader",
      "style_summary": "Intraday price-action analyst focused on gold confirmation zones",
      "first_line": "Your gold notes come across as a patient price-action style, with confirmation around key zones doing most of the filtering.",
      "hook": "For price-action gold traders, the useful edge is often in cleaner zone selection before the entry ever appears.",
      "reason": [
        "Bio explicitly positions the account around XAUUSD trading",
        "Recent tweets repeatedly discuss gold levels and confirmation",
        "Uses technical zone language rather than generic market commentary",
        "Shows risk-aware behavior by waiting before entries",
        "Relevant UK source-query context supports fit"
      ]
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

Score from 1 to 10 for XAUUSD / forex / gold trading lead generation. Be strict. The expected output is a qualified subset, not every account. If the evidence does not clearly justify outreach, score `6` or below.

Hard gates before scoring:

- If the account is spam, giveaway, fake-profit, adult, unrelated lifestyle, generic engagement bait, or empty/low-information, score `1-4`.
- If the account is crypto-only with no visible gold/forex angle, score `1-5`.
- If the account is a generic signal channel with copied-looking calls, VIP spam, guaranteed-profit language, or no original analysis, score `3-6`.
- If the account mentions gold once but has no recurring XAUUSD/gold/forex pattern, score `5-6`.
- If the account is multi-asset but gold/XAUUSD is weak or incidental, score no higher than `6` unless the trading quality is clearly strong.
- If there are fewer than two meaningful evidence points across bio and `recent_tweets`, score no higher than `6`.

Strict score ladder:

| Score | Meaning |
|---|---|
| 10 | Exceptional XAUUSD authority: original gold analysis, strong recurring XAUUSD focus, clear expertise/education, strong engagement or authority signals |
| 9 | Very strong trader or educator: repeated gold/forex analysis, clear method/persona, original insights, recent activity, good fit |
| 8 | Good quality trader: credible trading style, repeated relevant market focus, useful analysis, enough evidence for confident outreach |
| 7 | Acceptable outreach target: relevant and active enough, but less authority, weaker originality, lower engagement, or broader market focus |
| 6 | Borderline: some trading relevance but weak XAUUSD fit, thin evidence, generic style, low information, or not clearly worth outreach |
| 1-5 | Reject: spam, copied signals, crypto-only, unrelated, inactive, low-information, fake-profit, or no clear trading relevance |

High-score evidence should be specific:

- Repeated XAUUSD/gold discussion across `recent_tweets`.
- Original analysis, levels, structure, macro reasoning, risk commentary, or education.
- Clear persona such as ICT/SMC/Price Action/Macro/Educator with supporting language.
- Consistent recent activity and non-spam engagement.
- Bio and tweets reinforce the same trading identity.

Low-score evidence should be applied aggressively:

- Vague “forex lifestyle” branding without analysis.
- Signal/VIP/channel promotion without original reasoning.
- Generic motivational posts with trading hashtags.
- One gold keyword from search context but no account-level pattern.
- Copied-looking calls, guaranteed results, pump language, or excessive emojis.
- Large follower count with weak content. Followers alone do not qualify a lead.

Keep only score `>= 7`. It is acceptable and expected that many normalized accounts are excluded.

## Reason, Persona, and Style Quality

`reason` must explain the score with concrete, evidence-backed bullets. Avoid generic phrases like “good fit”, “active account”, “relevant content”, or “trading interest” unless they are paired with specific evidence.

Good `reason` examples:

- `Posts XAUUSD across multiple recent tweets`
- `Uses SMC concepts such as liquidity and structure`
- `Shows original analysis rather than copied signal calls`
- `Uses higher-timeframe swing context`
- `Bio and tweets both focus on gold trading`
- `Engagement is visible on recent analytical posts`
- `Risk management appears in the account's entry language`

Bad `reason` examples:

- `Relevant trader`
- `Good account`
- `Talks about markets`
- `Might be interested`

`style_summary` should be specific and compact. Use a phrase that could help a human SDR understand the account quickly.

Good `style_summary` examples:

- `Gold-focused ICT educator`
- `Swing trader using SMC`
- `Intraday price-action analyst`
- `Gold signal provider with structured risk`
- `Macro-driven gold commentator`
- `Prop trader focused on disciplined execution`
- `Scalper watching London and New York gold sessions`

Bad `style_summary` examples:

- `signal provider`
- `trader`
- `finance account`
- `gold person`

## Personalization Rules

For `first_line`:

- Write one short, natural first-line about the trader's apparent style, market focus, or repeated behavior.
- Prefer account-level wording over tweet-level wording.
- Refer only to evidence from CSV `recent_tweets`, bio, and normalized account fields.
- Do not invent recent posts, profits, location, identity, or trading behavior.
- Do not sound spammy or generic.
- Avoid fake flattery.
- Avoid repetitive openers across leads. Do not overuse phrases like `You provide clear`, `Your gold analysis`, `You blend`, `I noticed`, or `Saw your`.
- Vary sentence shape. Some first-lines can start with the style, some with the market focus, some with the discipline, and some with the account's teaching/personality.
- Use the account's `persona`, `trading_themes`, and `style_summary` to make the line feel individually written.

Good:

```text
Your gold notes read like a patient price-action approach, especially around waiting for confirmation before entries.
```

```text
You seem to lean toward multi-asset macro context while still keeping gold levels in focus.
```

Bad:

```text
Saw your tweet about gold yesterday.
```

```text
I saw you made huge profits trading gold last week.
```

For `hook`:

- Write one short outreach hook.
- Keep it relevant to gold/forex/trading discipline.
- Do not promise profit, guaranteed income, win rate, risk-free results, or financial certainty.
- Vary hooks by `persona`. Do not reuse one generic hook pattern for every lead.
- The hook should feel like a natural continuation of the first-line, not a template.

Persona-based hook guidance:

| Persona | Hook direction |
|---|---|
| ICT Trader | Liquidity timing, session context, cleaner confirmation, fair-value-gap/order-block discipline |
| SMC Trader | Structure, BOS/CHOCH, liquidity mapping, avoiding forced entries |
| Price Action Trader | Cleaner zones, confirmation, candle behavior, practical execution filters |
| Gold Analyst | Gold levels, macro context, volatility planning, market narrative |
| Swing Trader | Higher-timeframe bias, patience, multi-day levels, risk before entry |
| Scalper | Session timing, fast decision filters, avoiding noisy moves |
| Prop Trader | Drawdown discipline, rule-based execution, consistency under evaluation constraints |
| Educator | Clearer teaching angles, useful frameworks, making analysis easier to apply |
| Signal Provider | Structured context around calls, risk clarity, avoiding blind entries |
| Institutional Trader | Liquidity, order-flow framing, professional market structure |
| Macro Trader | USD, rates, data, cross-market drivers behind gold |
| News Trader | Event risk, data-release planning, volatility filters |
| Hybrid | Bridge the strongest two supported styles without sounding generic |

Safe hook examples:

```text
Gold traders who care about cleaner entries usually watch the same risk zones.
```

```text
If you trade XAUUSD, cleaner planning usually starts before price reaches the zone.
```

## Diversity Self-Check

Before writing `enriched_leads.normalized.json`, perform a final quality pass over all kept leads:

- If two `first_line` values have nearly identical wording or sentence structure, rewrite one.
- If two `hook` values have nearly identical wording or sentence structure, rewrite one.
- Avoid repeating the same opening phrase more than twice in the whole output.
- Avoid repeating the same hook noun phrase, such as `signal providers`, across many personas.
- Make sure first-lines are about account-level style, recurring themes, personality, teaching style, risk management style, market focus, or consistency.
- Make sure hooks vary by `persona`.
- Keep every rewrite evidence-based. Do not add facts that are not in `normalized_leads.json`.

Simple diversity test:

- Read the first 5 words of each first-line. If several are the same, rewrite.
- Read the first 5 words of each hook. If several are the same, rewrite.
- Scan for repeated phrases like `clear analysis`, `gold analysis`, `you blend`, `signal providers`, `risk zones`. If repeated, rewrite with persona-specific language.

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
- [ ] Hermes reasoned over the account, not one isolated tweet.
- [ ] Hermes applied strict qualification; weak, spammy, generic, crypto-only, or low-information accounts scored `6` or below.
- [ ] Hermes generated `score_fit`, `trading_themes`, `persona`, `style_summary`, `reason`, `first_line`, and `hook`; Python did not.
- [ ] No `last30days`, Google Sheets, GitHub sync, CRM, or external API work was used in Phase 1.6.
- [ ] `enriched_leads.normalized.json` was created automatically by Hermes.
- [ ] `write` produced `enriched_leads.csv`.
- [ ] `enriched_leads.csv` has exactly the 5 required columns.
- [ ] `enriched_leads.csv` has no duplicate usernames.
- [ ] Every output row has `Score fit >= 7`.
- [ ] `persona` exists in `enriched_leads.normalized.json` and is not exported to CSV.
- [ ] First-lines describe trader style or recurring market focus, not just one tweet.
- [ ] First-lines and hooks passed the diversity self-check.
- [ ] Internal `reason` lists are specific, evidence-backed, and not exported to CSV.
- [ ] Hooks do not promise profit or risk-free trading.
