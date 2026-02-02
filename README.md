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
