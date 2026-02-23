# CLAUDE.md -- AnkiMinder

## Project Override

This is a **Python Anki add-on**, not a Salesforce project. All Salesforce-specific instructions from the global `CLAUDE.md` (metadata retrieval, deployment, scratch orgs, Apex standards, LWC, `.forceignore`, trigger patterns, etc.) are **not applicable** and must be ignored for this repo.

The following global instructions **do** apply:
- Git workflow and approval gates (`git push`, `gh pr create` require approval)
- Commit message standards (imperative mood, what + why)
- PR workflow (feature branches, concise titles, descriptive bodies)
- Never use `git add .` -- stage specific files
- General communication style (direct, no filler)

## Project Variables

| Variable | Value |
|---|---|
| Project | AnkiMinder |
| Repo | `rolemartyr-x/AnkiAddOn` |
| Language | Python 3.12+ |
| Framework | Anki add-on (aqt) |
| Integration | Beeminder API v1 |
| Test Framework | `unittest` (stdlib) |
| External Dependencies | None (stdlib only) |
| Entry Point | `__init__.py` → `ankiminder.addon.initialize_addon()` |
| Build | `python scripts/build_ankiaddon.py` → `dist/*.ankiaddon` |

## Repo Layout

```
ankiminder/              # Main package
  beeminder/             # API client layer (client, transport, models)
  services/              # Business logic (sync, automation, review counts)
  mocks/                 # Test doubles
  config.py              # Config dataclass + persistence
  addon.py               # Anki UI hooks and menus
  exceptions.py          # Custom exception hierarchy
tests/                   # Unit tests (unittest)
scripts/                 # Build and utility scripts
dist/                    # Build output (.ankiaddon packages)
```

## Commands

| Action | Command |
|---|---|
| Run all tests | `python -m unittest discover -s tests` |
| Run single test file | `python -m unittest tests.test_models` |
| Build .ankiaddon | `python scripts/build_ankiaddon.py` |

## Development Standards

- **No external dependencies.** The add-on runs inside Anki's Python environment. Use only stdlib + `aqt` modules.
- **Test every behavior change.** Happy path + error path + bulk where applicable.
- **Mock network calls.** Use `MockTransport` / `MockClient` from `ankiminder/mocks/`. Never hit live endpoints in tests.
- **No secrets in source.** Auth tokens come from Anki's add-on config manager.
- **Keep UI changes minimal.** Follow Anki UX patterns. No blocking operations on the main thread.
- **Type hints required** on all new code. Use modern syntax (`list[str] | None`, not `Optional[List[str]]`).
- **`from __future__ import annotations`** at the top of every Python file.

## Architecture Notes

The codebase follows a clean layered architecture:
1. **UI** (`addon.py`) -- Anki hooks/menus, delegates to services
2. **Services** (`services/`) -- Business logic, orchestration
3. **Client** (`beeminder/client.py`) -- Thin API wrapper
4. **Transport** (`beeminder/transport.py`) -- HTTP abstraction (injectable for testing)
5. **Models** (`beeminder/models.py`) -- Request/response dataclasses
6. **Config** (`config.py`) -- Anki config persistence

Dependencies flow downward only. Services depend on Client, Client depends on Transport. Never skip layers.

## Cross-Reference

See also:
- `AGENTS.md` -- Agent-specific guardrails (Beeminder integration rules, quality bar)
- `CONTRIBUTING.md` -- Contributor workflow and commit hygiene
- `config.md` -- User-facing configuration documentation
- `README.md` -- User-facing setup and usage guide
