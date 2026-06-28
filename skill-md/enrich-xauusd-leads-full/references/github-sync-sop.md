# GitHub Sync SOP

`scripts/sync_github.py` copies completed XAUUSD pipeline artifacts into a configured Git repository and pushes a run commit for audit/history.

The helper is deterministic. Hermes or the orchestrator may call it, but the helper owns all Git operations.

## Purpose

Archive these artifacts after enrichment:

- `enriched_leads.csv`
- `run_report.json`
- optional `google_sheet_sync.json`

The helper copies artifacts to:

```text
{repo_dir}/{output_dir}/{run_id}/
```

Then it runs Git only for the copied artifact paths.

## Prerequisites

- `git` is installed.
- `GITHUB_SYNC_REPO_DIR` points to a local Git worktree.
- The repo has a configured remote and push permissions.
- The runtime user can read pipeline artifacts.
- The runtime user can write to the repo output directory.
- The runtime user can run `git add`, `git commit`, and `git push`.

Do not put secrets in the artifact directory.

## Environment Variables

```bash
GITHUB_SYNC_REPO_DIR=/home/hermesads/xauusd-leads-history
GITHUB_SYNC_OUTPUT_DIR=xauusd-leads
```

`GITHUB_SYNC_OUTPUT_DIR` defaults to `xauusd-leads`.

## Runtime Command

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/sync_github.py \
  --repo-dir "$GITHUB_SYNC_REPO_DIR" \
  --output-dir "$GITHUB_SYNC_OUTPUT_DIR" \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --run-report /tmp/xauusd-real/run_report.json \
  --google-sheet-json /tmp/xauusd-real/google_sheet_sync.json \
  --run-id 20260628-120000
```

## Orchestrator Integration

`scripts/run_pipeline.py` runs GitHub sync after `run_report`, so the current `run_report.json` can be archived with the final CSV and Google Sheets sync JSON.

The orchestrator passes:

```text
--csv <csv>
--run-report <run_report>
--google-sheet-json <google_sheet_json>
--run-id <run_id>
--repo-dir <github_repo_dir>
--output-dir <github_output_dir>
```

Use `--skip-github-sync` on `run_pipeline.py` when GitHub sync should be disabled for a test run.

Without the optional Google Sheets artifact:

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/sync_github.py \
  --repo-dir "$GITHUB_SYNC_REPO_DIR" \
  --output-dir "$GITHUB_SYNC_OUTPUT_DIR" \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --run-report /tmp/xauusd-real/run_report.json \
  --run-id 20260628-120000
```

## Dry Run

Dry-run validates inputs and repo status without copying files, running `git add`, committing, or pushing.

```bash
python3 /opt/hermes-ads/hermes-home/skills/lead-gen/enrich-xauusd-leads-full/scripts/sync_github.py \
  --repo-dir "$GITHUB_SYNC_REPO_DIR" \
  --output-dir "$GITHUB_SYNC_OUTPUT_DIR" \
  --csv /tmp/xauusd-real/enriched_leads.csv \
  --run-report /tmp/xauusd-real/run_report.json \
  --google-sheet-json /tmp/xauusd-real/google_sheet_sync.json \
  --run-id 20260628-120000 \
  --dry-run
```

Expected dry-run response:

```json
{
  "schema_version": "github-sync/v1",
  "status": "completed",
  "files_copied": [
    "xauusd-leads/20260628-120000/enriched_leads.csv",
    "xauusd-leads/20260628-120000/run_report.json",
    "xauusd-leads/20260628-120000/google_sheet_sync.json"
  ],
  "commit_created": false,
  "commit_sha": "",
  "pushed": false,
  "warnings": ["dry_run_no_files_copied_no_git_mutation"],
  "dry_run": true
}
```

## Safety Rules

- Do not add the entire repo.
- Do not run `git add .`.
- Only add copied artifact paths.
- Do not commit secrets, credentials, `.env`, service account files, caches, or runtime logs.
- Keep GitHub sync separate from Google Sheets sync.
- The helper emits JSON only. Do not rely on human-readable stdout.

## Git Behavior

The helper runs:

```text
git status --short -- <copied artifacts>
git add -- <copied artifacts>
git diff --cached --quiet -- <copied artifacts>
git commit -m "Sync XAUUSD lead artifacts <run_id>" -- <copied artifacts>
git rev-parse HEAD
git push
```

If no selected artifact changed after `git add`, the helper returns:

```json
{
  "status": "completed",
  "commit_created": false,
  "pushed": false,
  "warnings": ["no_changes_to_commit"]
}
```

## Common Errors

### `missing_repo_dir`

Set `GITHUB_SYNC_REPO_DIR` or pass `--repo-dir`.

### `repo_dir_not_found`

Create or clone the Git repo before running sync.

### `not_a_git_repo`

The configured directory is not inside a Git worktree. Use the correct local clone.

### `csv_not_found`

Run the enrichment pipeline first and verify `enriched_leads.csv` exists.

### `run_report_not_found`

Run `scripts/generate_run_report.py` or the full orchestrator first.

### `git_commit_failed`

Check Git user configuration:

```bash
git config user.name
git config user.email
```

### `git_push_failed`

Check remote, branch permissions, SSH key, token, or network access.

## Recovery

1. Inspect the JSON `error` field.
2. Fix missing artifacts, repo path, permissions, or Git configuration.
3. Re-run with `--dry-run`.
4. Re-run without `--dry-run`.

If a commit was created but push failed, fix Git remote/auth and run:

```bash
git -C "$GITHUB_SYNC_REPO_DIR" push
```

## Verification Checklist

- JSON output has `schema_version = "github-sync/v1"`.
- `status = "completed"`.
- `files_copied` contains only expected artifact paths.
- `commit_created = true` when changes exist.
- `commit_sha` is non-empty when a commit was created.
- `pushed = true` when a commit was created and pushed.
- No secrets were copied into the repo output directory.
- `git log -1` shows the run-id commit message.
