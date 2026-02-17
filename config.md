# AnkiMinder Config

This add-on reads settings from `config.json`.

## Required

- `beeminder_username`: Your Beeminder username.
- `beeminder_auth_token`: Your Beeminder auth token.
- `review_count_goal_slug`: Your Beeminder do-more goal slug.

## Optional

- `default_goal_slug`: Fallback goal slug if `review_count_goal_slug` is blank.
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

Do not edit them unless you are debugging.
