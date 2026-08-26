# AnkiMinder Config

This add-on reads settings from `config.json`.

## Required

- `beeminder_username`: Your Beeminder username.
- `beeminder_auth_token`: Your Beeminder auth token.
- `review_count_goal_slug`: Your Beeminder do-more goal slug.

## Optional

- `default_goal_slug`: Fallback goal slug if `review_count_goal_slug` is blank.
- `review_completion_goal_slug`: Beeminder do-more goal slug for the binary "did I review today" (0/1) signal. This is a separate goal from `review_count_goal_slug`/`default_goal_slug` and is **never** filled in by falling back to either of them -- leave it blank to keep completion sync fully disabled, even if `review_completion_sync_enabled` is `true`.

  **`review_completion_goal_slug` MUST be different from `review_count_goal_slug` (and from `default_goal_slug`, if that's what the numeric sync resolves to).** Both syncs upsert datapoints for the same day; pointing them at the same goal risks one signal's write silently overwriting the other's datapoint. The add-on detects this and **refuses to run the completion sync** (returning an error result instead of writing anything) whenever the two slugs resolve to the same goal -- create a second, dedicated Beeminder goal for completion tracking instead.
- `review_completion_sync_enabled`: Enable the binary completion sync (`true` / `false`, default `false`). Completion sync only runs when this is `true` *and* `review_completion_goal_slug` is non-empty *and* it does not collide with the numeric goal slug (see above).
- `due_cards_cleared_goal_slug`: Beeminder do-more goal slug for a third, independent binary "all due cards cleared today" (0/1) signal. **Must be different from both `review_count_goal_slug`/`default_goal_slug` AND `review_completion_goal_slug`** -- the add-on refuses to run this sync (no partial writes) if it collides with either. Leave blank to keep it disabled, even if `due_cards_cleared_sync_enabled` is `true`.
- `due_cards_cleared_sync_enabled`: Enable the due-cards-cleared sync (`true` / `false`, default `false`). Only runs when this is `true` *and* `due_cards_cleared_goal_slug` is non-empty *and* it does not collide with either other goal slug.
- `due_cards_cleared_deck_names`: Optional list of deck names that count toward "today's due cards" (e.g. `["Japanese", "Spanish::Verbs"]`). Empty (the default) means all decks in the collection. A name that doesn't match any deck is silently treated as contributing zero due cards rather than erroring -- double-check spelling if a filtered deck's cards don't seem to be counted.

  **Unlike the numeric and completion signals, this signal is never backfilled historically -- `historical_lookback_days` does not apply to it.** It reads Anki's scheduler (what's due *right now*), not the revlog, so there is no way to retroactively determine whether all due cards were cleared on a past day. Each sync writes only "today," computed live at the moment sync runs.

  It is also **sticky, not live-flipping**: once today's datapoint is posted as `1` (all clear), a later sync the same day that finds new due cards (e.g. a learning-step card returning, or a newly added card) will NOT downgrade it back to `0`. Clearing your queue once counts for the day.
- `automation_enabled`: Enable automatic sync (`true` / `false`).
- `automation_triggers`: Automatic trigger list. Supported values:
  - `"sync"`
  - `"startup"`
- `request_timeout_seconds`: API timeout in seconds.
- `historical_lookback_days`: Number of days to sync on each run (default `7`). Clamped to a maximum of 365 -- values above that are silently capped rather than rejected. Each day in the window costs one sequential HTTP write per enabled signal (numeric count, and binary completion if enabled), with no bulk-API path, so a large lookback combined with completion sync roughly doubles the number of Beeminder API round-trips for that run; prefer a smaller value for routine syncs and only raise it temporarily for a one-time historical backfill.
- `dry_run`: If `true`, do not write to Beeminder.

## Internal Metadata (Auto-managed)

These are maintained by the add-on:
- `last_review_count_sync_date`
- `last_review_count_value`
- `last_review_count_datapoint_id`
- `last_review_completion_sync_date`
- `last_review_completion_value`
- `last_review_completion_datapoint_id`
- `last_due_cards_cleared_sync_date`
- `last_due_cards_cleared_value`
- `last_due_cards_cleared_datapoint_id`

Do not edit them unless you are debugging.
