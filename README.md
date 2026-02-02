# AnkiMinder Add-on

Sync your **daily Anki review count** to a Beeminder **do-more** goal.

This add-on supports:
- Manual sync from the Anki Tools menu.
- Automatic sync on Anki startup and/or after sync.
- Daily "upsert" behavior:
  - create today's datapoint if it does not exist
  - update today's datapoint if total changed
  - skip write if Beeminder already has the same total

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
1. Count today's reviews from Anki.
2. Read recent datapoints from Beeminder.
3. Find a datapoint for today.
4. If found and value differs, update it.
5. If found and value matches, do nothing.
6. If not found, create today's datapoint.

This design supports multiple study sessions per day without creating duplicate datapoints.

---

## Install in Anki (Manual / Dev)

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
`Tools -> Add-ons -> <your-addon-folder-name> -> Config`

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
  "dry_run": true
}
```

---

## Local Development

### Prerequisites

- Python 3.10+ (using `python3`)

### Run Tests

```bash
python3 -m unittest discover -s tests
```

### Build a Shareable Package

This repo includes a packager for `.ankiaddon` output:

```bash
python3 scripts/build_ankiaddon.py
```

Optional custom output path:

```bash
python3 scripts/build_ankiaddon.py --output dist/AnkiMinder-v1.0.0.ankiaddon
```

The package is written to `dist/` and includes:
- `__init__.py`
- `manifest.json`
- `config.json`
- `config.md`
- `ankiminder/`

Install by sharing the `.ankiaddon` file and using:
`Tools -> Add-ons -> Install from file...`

### Repo Layout

- `__init__.py`: Anki add-on entrypoint
- `config.json`: default add-on config schema
- `config.md`: user-facing config explanation
- `manifest.json`: add-on manifest used by packaged distribution
- `ankiminder/addon.py`: Anki UI/hooks wiring
- `ankiminder/beeminder/`: API client, transport, models
- `ankiminder/services/`: business logic (review sync + automation policy)
- `ankiminder/mocks/`: test doubles
- `tests/`: unit tests

---

## Testing Checklist in Anki

1. Set `dry_run: true`.
2. Trigger manual sync (`Tools -> Send Today's Review Count to Beeminder`).
3. Trigger automatic sync via Anki sync/startup.
4. Set `dry_run: false`.
5. Confirm Beeminder datapoint is created.
6. Do more reviews and sync again.
7. Confirm same-day datapoint is updated, not duplicated.

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

No license file is currently included. Add one before public distribution if needed.
