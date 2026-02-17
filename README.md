# AnkiMinder Add-on

Sync your **daily Anki review count** to a Beeminder **do-more** goal.

This add-on supports:
- Manual sync from the Anki Tools menu.
- Automatic sync on Anki startup and/or after sync.
- Historical window "upsert" behavior:
  - sync each day in the configured lookback window
  - create missing day datapoints for days with reviews
  - update existing day datapoints when totals change
  - skip day writes already up-to-date in Beeminder or with `0` reviews

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

## Install in Anki (Recommended: `.ankiaddon`)

1. Download the release file named like `ankiminderV1.0.3.ankiaddon`.
2. In Anki, go to:
   - `Tools -> Add-ons -> Install from file...`
3. Select the `.ankiaddon` file.
4. Restart Anki.

---

## Build Package

Build a distributable `.ankiaddon` file:

```bash
python3 scripts/build_ankiaddon.py --version 1.0.3
```

The output file name is always enforced as:
`ankiminderV<version>.ankiaddon`

Optional custom path (same enforced file name):

```bash
python3 scripts/build_ankiaddon.py --version 1.0.3 --output dist/ankiminderV1.0.3.ankiaddon
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
- `automation_enabled` (bool): enable automatic sync.
- `automation_triggers` (list[string]): automatic triggers; supported values: `"sync"`, `"startup"`.
- `last_review_count_sync_date` (string): internal metadata (`YYYY-MM-DD`), auto-managed.
- `last_review_count_value` (int): internal metadata, auto-managed.
- `last_review_count_datapoint_id` (string): internal metadata, auto-managed.
- `request_timeout_seconds` (int): Beeminder API timeout.
- `historical_lookback_days` (int): number of days to re-sync each run (default `7`).
- `dry_run` (bool): if true, no write is sent to Beeminder.

Recommended first run:
- `dry_run: true`

Example:

```json
{
  "beeminder_username": "your_username",
  "beeminder_auth_token": "your_auth_token",
  "review_count_goal_slug": "anki-reviews",
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
