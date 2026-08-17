# AnkiMinder Config

This add-on reads settings from `config.json`.

## Required

- `beeminder_username`: Your Beeminder username.
- `beeminder_auth_token`: Your Beeminder auth token.
- `review_count_goal_slug`: Your Beeminder do-more goal slug.

## Optional

- `default_goal_slug`: Fallback goal slug if `review_count_goal_slug` is blank.
- `review_completion_goal_slug`: Beeminder do-more goal slug for the binary "did I review today" (0/1) signal. This is a separate goal from `review_count_goal_slug`/`default_goal_slug` and is **never** filled in by falling back to either of them -- leave it blank to keep completion sync fully disabled, even if `review_completion_sync_enabled` is `true`.
- `review_completion_sync_enabled`: Enable the binary completion sync (`true` / `false`, default `false`). Completion sync only runs when this is `true` *and* `review_completion_goal_slug` is non-empty.
- `automation_enabled`: Enable automatic sync (`true` / `false`).
- `automation_triggers`: Automatic trigger list. Supported values:
  - `"sync"`
  - `"startup"`
- `request_timeout_seconds`: API timeout in seconds.
- `historical_lookback_days`: Number of days to sync on each run (default `7`).
- `dry_run`: If `true`, do not write to Beeminder.

## Internal Metadata (Auto-managed)

These are maintained by the add-on:
- `last_review_count_sync_date`
- `last_review_count_value`
- `last_review_count_datapoint_id`
- `last_review_completion_sync_date`
- `last_review_completion_value`
- `last_review_completion_datapoint_id`

Do not edit them unless you are debugging.
