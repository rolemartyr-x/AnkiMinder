# AnkiMinder Add-on

Sync your **daily Anki review count** to a Beeminder **do-more** goal, with
two optional binary signals to separate goals: **"did I review at all
today"** and **"did I clear all of today's due cards"**.

This add-on supports:
- Manual sync from the Anki Tools menu.
- Automatic sync on Anki startup and/or after sync.
- Historical window "upsert" behavior:
  - sync each day in the configured lookback window
  - create missing day datapoints for days with reviews
  - update existing day datapoints when totals change
  - skip day writes already up-to-date in Beeminder or with `0` reviews
- An optional, independent binary completion signal (`review_completion_sync_enabled`):
  posts a `0`/`1` "did I review today" datapoint to a *second* Beeminder
  goal every day in the lookback window, including zero-review days (see
  "Binary Completion Sync" below).
- An optional, independent binary due-cards-cleared signal
  (`due_cards_cleared_sync_enabled`): posts a `0`/`1` "did I clear all of
  today's due cards" datapoint to a *third* Beeminder goal, computed live
  from Anki's scheduler (see "Due Cards Cleared Sync" below).

---

## Core Features

- Tracks total reviews for a specific day from Anki's `revlog`.
- Sends data to Beeminder via API v1.
- Uses a deterministic `requestid` for daily idempotency.
- Uses non-blocking toast notifications in Anki (no click-through dialogs).
- Includes `dry_run` mode for safe testing.
- Includes unit tests with mocked Beeminder API behavior.

---

## How It Works

For each sync attempt:
1. Build a date range from `today - historical_lookback_days` through `today`.
2. Count reviews for each day in that range.
3. Read recent datapoints from Beeminder once.
4. For each day:
5. If datapoint exists and value differs, update it.
6. If datapoint exists and value matches, do nothing.
7. If datapoint does not exist, create it for days with reviews.

This design recovers missed review days and supports multiple sessions per day without duplicates.

---

## Binary Completion Sync (Optional)

In addition to the numeric review-count sync above, you can enable a second,
independent signal: a binary `0`/`1` "did I review today" datapoint, useful
for a Beeminder goal that just tracks streak-style consistency rather than
volume.

To enable it:

1. Create a **second** Beeminder do-more goal (separate from the one used
   for `review_count_goal_slug`/`default_goal_slug`).
2. In `config.json`, set:
   - `review_completion_goal_slug`: the second goal's slug.
   - `review_completion_sync_enabled: true`.

**The completion goal slug must be different from the numeric goal slug.**
Both syncs upsert a datapoint for the same day, and pointing them at the
same goal risks one signal's write overwriting the other's data. The
add-on checks for this and will refuse to run the completion sync (with a
clear error message, no partial writes) if the two slugs resolve to the
same goal.

For each sync attempt, once completion sync is enabled:
1. Uses the same date range as the numeric sync (`today - historical_lookback_days` through `today`).
2. For each day, posts `1` if any reviews happened that day, `0` otherwise.
3. **Unlike the numeric sync, zero-review days are never skipped** -- posting
   `0` on a no-review day *is* the point of the completion signal (the
   numeric sync, by contrast, skips writing anything on a `0`-review day).
4. Uses its own distinct `requestid` prefix, so it can never collide with
   the numeric sync's datapoints even before the goal-slug check above.

---

## Due Cards Cleared Sync (Optional)

A third, independent signal: a binary `0`/`1` "did I clear all of today's
due cards" datapoint, useful for a Beeminder goal that tracks whether you
actually finished your queue for the day, rather than whether you did any
reviews at all or how many.

To enable it:

1. Create a **third** Beeminder do-more goal (separate from both the goal
   used for `review_count_goal_slug`/`default_goal_slug` *and* the one used
   for `review_completion_goal_slug`).
2. In `config.json`, set:
   - `due_cards_cleared_goal_slug`: the third goal's slug.
   - `due_cards_cleared_sync_enabled: true`.
   - Optionally, `due_cards_cleared_deck_names`: a list of deck names to
     restrict the check to (default: all decks).

**The due-cards-cleared goal slug must differ from both other goal slugs.**
All three syncs upsert datapoints, and a colliding slug risks one signal's
write overwriting another's data. The add-on refuses to run this sync (no
partial writes) if it collides with either other slug.

Key differences from the other two signals:
- **Live, not historical.** This reads Anki's scheduler (what's due *right
  now*), not the revlog, so it can only ever report on "today" -- there is
  no way to retroactively check a past day. `historical_lookback_days`
  does not apply to it.
- **Sticky, not flip-able.** Once today's datapoint reads `1` (all clear),
  a later sync the same day that finds new due cards will NOT downgrade it
  back to `0`. Clearing your queue once counts for the day, even if
  learning-step cards return or you add new cards afterward.
- **Deck-name filtering.** An unresolvable/misspelled deck name in
  `due_cards_cleared_deck_names` silently contributes zero due cards
  rather than erroring.

---

## Install in Anki (Recommended: AnkiWeb)

1. Visit the [AnkiMinder AnkiWeb listing](https://ankiweb.net/shared/info/221391424).
2. In Anki, go to `Tools -> Add-ons -> Get Add-ons...` and paste the code `221391424` (or use AnkiWeb's "Download" button on the page above).
3. Restart Anki.

This is the easiest path for most users -- Anki checks AnkiWeb for updates automatically, so you won't need to manually re-download new releases.

---

## Install via `.ankiaddon` File (Alternative / Offline)

Use this if you'd rather install a specific release manually, or don't want AnkiWeb's auto-update checks.

1. Download the release file (e.g. `ankiminderV1.1.0.ankiaddon`) from this repo's [GitHub Releases](https://github.com/rolemartyr-x/AnkiMinder/releases).
2. In Anki, go to:
   - `Tools -> Add-ons -> Install from file...`
3. Select the `.ankiaddon` file.
4. Restart Anki.

---

## Build Package

Build a distributable `.ankiaddon` file:

```bash
python scripts/build_ankiaddon.py --version 1.1.0
```

The output file name is always enforced as:
`ankiminderV<version>.ankiaddon`

Optional custom path (same enforced file name):

```bash
python scripts/build_ankiaddon.py --version 1.1.0 --output dist/ankiminderV1.1.0.ankiaddon
```

---

## Install in Anki (Manual / Dev Fallback)

1. Open your Anki add-ons directory:
   - Windows: `%APPDATA%\Anki2\addons21\`
2. Create an add-on folder name (example: `ankiminder`).
3. Copy these from this repo into that folder:
   - `__init__.py`
   - `config.json`
   - `ankiminder/` (entire directory)
4. Restart Anki.

---

## Configure the Add-on

In Anki:
`Tools -> Add-ons -> AnkiMinder -> Config`

Config options (all current keys):
- `beeminder_username` (string): your Beeminder username.
- `beeminder_auth_token` (string): your Beeminder auth token.
- `default_goal_slug` (string): fallback goal slug if review-specific slug is empty.
- `review_count_goal_slug` (string): primary goal slug for review totals.
- `review_completion_goal_slug` (string): goal slug for the optional binary "did I review today" (0/1) signal. Must differ from `review_count_goal_slug`/`default_goal_slug` -- see "Binary Completion Sync" above. Never falls back to another slug; leave blank to keep completion sync disabled.
- `review_completion_sync_enabled` (bool): enable the binary completion sync. Only takes effect when `review_completion_goal_slug` is also set and distinct from the numeric goal slug.
- `due_cards_cleared_goal_slug` (string): goal slug for the optional binary "all due cards cleared today" (0/1) signal. Must differ from both `review_count_goal_slug`/`default_goal_slug` *and* `review_completion_goal_slug` -- see "Due Cards Cleared Sync" above. Never falls back to another slug; leave blank to keep this sync disabled.
- `due_cards_cleared_sync_enabled` (bool): enable the due-cards-cleared sync. Only takes effect when `due_cards_cleared_goal_slug` is also set and distinct from the other two goal slugs.
- `due_cards_cleared_deck_names` (list[string]): decks to restrict the due-cards-cleared check to. Empty (default) means all decks.
- `automation_enabled` (bool): enable automatic sync.
- `automation_triggers` (list[string]): automatic triggers; supported values: `"sync"`, `"startup"`.
- `last_review_count_sync_date` (string): internal metadata (`YYYY-MM-DD`), auto-managed.
- `last_review_count_value` (int): internal metadata, auto-managed.
- `last_review_count_datapoint_id` (string): internal metadata, auto-managed.
- `last_review_completion_sync_date` (string): internal metadata (`YYYY-MM-DD`), auto-managed.
- `last_review_completion_value` (int): internal metadata, auto-managed.
- `last_review_completion_datapoint_id` (string): internal metadata, auto-managed.
- `last_due_cards_cleared_sync_date` (string): internal metadata (`YYYY-MM-DD`), auto-managed.
- `last_due_cards_cleared_value` (int): internal metadata, auto-managed.
- `last_due_cards_cleared_datapoint_id` (string): internal metadata, auto-managed.
- `request_timeout_seconds` (int): Beeminder API timeout.
- `historical_lookback_days` (int): number of days to re-sync each run (default `7`, clamped to a maximum of 365). A large value combined with completion sync roughly doubles the number of Beeminder API round-trips for that run -- see `config.md`.
- `dry_run` (bool): if true, no write is sent to Beeminder.

Recommended first run:
- `dry_run: true`

Example:

```json
{
  "beeminder_username": "your_username",
  "beeminder_auth_token": "your_auth_token",
  "review_count_goal_slug": "anki-reviews",
  "review_completion_goal_slug": "anki-review-streak",
  "review_completion_sync_enabled": true,
  "due_cards_cleared_goal_slug": "anki-due-cleared",
  "due_cards_cleared_sync_enabled": true,
  "due_cards_cleared_deck_names": [],
  "automation_enabled": true,
  "automation_triggers": ["sync", "startup"],
  "request_timeout_seconds": 10,
  "historical_lookback_days": 7,
  "dry_run": true
}
```

---

## Testing Checklist in Anki

1. Set `dry_run: true`.
2. Trigger manual sync (`Tools -> Sync Review Counts to Beeminder`).
3. Trigger automatic sync via Anki sync/startup.
4. Set `dry_run: false`.
5. Confirm Beeminder datapoints are created/updated for dates in your lookback window.
6. Confirm zero-review days are skipped (no datapoint written for `0`).
7. Do more reviews and sync again, then confirm the same-day datapoint updates.
8. To test completion sync: create a second goal, set `review_completion_goal_slug` (distinct from `review_count_goal_slug`) and `review_completion_sync_enabled: true`, then sync again.
9. Confirm completion sync posts a `0` datapoint on a zero-review day (opposite of the numeric sync's skip behavior) and a `1` on a day with reviews.
10. Confirm setting `review_completion_goal_slug` to the same value as `review_count_goal_slug` makes the add-on refuse to sync completion data (error message, no datapoint written or overwritten on either goal).
11. To test due-cards-cleared sync: create a third goal, set `due_cards_cleared_goal_slug` (distinct from the other two) and `due_cards_cleared_sync_enabled: true`. Sync while cards are still due (expect `0`), then use `Study Now` until none remain and sync again (expect `1`). Do more reviews later the same day (making cards due again) and sync once more -- confirm the value stays `1` (sticky), not `0`.

---

## Contributing

Please read `CONTRIBUTING.md` before opening a PR.

At minimum:
- keep changes scoped
- add/update tests for behavior changes
- avoid committing credentials or environment-specific secrets

---

## Security

If you discover a security issue, see `SECURITY.md`.

Never commit:
- Beeminder auth tokens
- local Anki profile data
- private keys or credential files

---

## License

MIT. See `LICENSE`.
