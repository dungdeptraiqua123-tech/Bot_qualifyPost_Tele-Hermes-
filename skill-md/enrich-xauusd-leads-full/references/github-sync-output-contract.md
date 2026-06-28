# GitHub Sync Output Contract

`scripts/sync_github.py` emits JSON only.

Schema:

```json
{
  "schema_version": "github-sync/v1",
  "status": "completed",
  "files_copied": [],
  "commit_created": true,
  "commit_sha": "",
  "pushed": true,
  "warnings": [],
  "dry_run": false
}
```

## Fields

- `schema_version`: Always `github-sync/v1`.
- `status`: `completed` or `failed`.
- `files_copied`: Repo-relative artifact paths selected for sync.
- `commit_created`: `true` only when a new commit was created.
- `commit_sha`: SHA of the created commit, or empty when no commit was created.
- `pushed`: `true` only when `git push` completed successfully.
- `warnings`: Operational warnings. These are not lead-quality signals.
- `dry_run`: `true` when `--dry-run` was used.
- `error`: Present only on failure.

## Success With Commit

```json
{
  "schema_version": "github-sync/v1",
  "status": "completed",
  "files_copied": [
    "xauusd-leads/20260628-120000/enriched_leads.csv",
    "xauusd-leads/20260628-120000/run_report.json"
  ],
  "commit_created": true,
  "commit_sha": "abc123",
  "pushed": true,
  "warnings": [],
  "dry_run": false
}
```

## Success With No Changes

```json
{
  "schema_version": "github-sync/v1",
  "status": "completed",
  "files_copied": [
    "xauusd-leads/20260628-120000/enriched_leads.csv",
    "xauusd-leads/20260628-120000/run_report.json"
  ],
  "commit_created": false,
  "commit_sha": "",
  "pushed": false,
  "warnings": ["no_changes_to_commit"],
  "dry_run": false
}
```

## Failure

```json
{
  "schema_version": "github-sync/v1",
  "status": "failed",
  "files_copied": [],
  "commit_created": false,
  "commit_sha": "",
  "pushed": false,
  "warnings": [],
  "dry_run": false,
  "error": "repo_dir_not_found: /path/to/repo"
}
```

## Compatibility Rules

- Consumers must treat unknown fields as optional.
- Consumers must not parse stdout as markdown or human text.
- Secrets must never appear in the JSON payload.
- `files_copied` must only include selected artifact paths copied by the helper.
