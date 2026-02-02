# Anki Beeminder Add-on (Framework)

Starter framework for an Anki add-on that posts study data to Beeminder.

## What is included

- Anki add-on entrypoint: `__init__.py`
- Runtime wiring and menu action: `anki_beeminder/addon.py`
- Config model + Anki config persistence: `anki_beeminder/config.py`
- Beeminder API client + transport layer:
  - `anki_beeminder/beeminder/client.py`
  - `anki_beeminder/beeminder/transport.py`
  - `anki_beeminder/beeminder/models.py`
- Service layer for sync behavior: `anki_beeminder/services/sync_service.py`
- Review-count sync helpers:
  - `anki_beeminder/services/review_count_service.py`
- Automation trigger policy:
  - `anki_beeminder/services/automation_service.py`
- Mocks/test doubles:
  - `anki_beeminder/mocks/mock_transport.py`
  - `anki_beeminder/mocks/mock_client.py`
- Unit tests in `tests/`

## Quick local test run

```bash
python3 -m unittest discover -s tests
```

## Notes

- This is intentionally lightweight scaffolding, not a full product feature set.
- API calls are structured for easy mocking and expansion.
- `dry_run` defaults to `True` in config to prevent accidental live writes.
- Includes a daily review-count sync path for Beeminder do-more goals.
- Includes a Tools menu action that syncs today's review count.
- Includes automation hooks for startup/sync triggers.
- Daily sync uses an upsert model (create once, then update same-day datapoint).

## Automation config keys

- `automation_enabled`: Turn automated sync on/off.
- `automation_triggers`: Trigger list (currently supports `sync` and `startup`).
- `automation_only_once_per_day`: Optional hard guard; default is `false` so totals can update across sessions.
- `last_automation_sync_date`: Internal marker updated after successful automation.
- `last_review_count_sync_date`, `last_review_count_value`, `last_review_count_datapoint_id`: Internal cache used to avoid redundant writes and update same-day totals.
