# AGENTS.md (Anki Add-on + Beeminder repo standard)

## Project context
- This repo is for an Anki add-on that integrates with Beeminder.
- Follow official Anki add-on guidance: `https://addon-docs.ankiweb.net/`.
- Follow official Beeminder API reference: `https://api.beeminder.com/#beeminder-api-reference`.
- Prefer simple, maintainable Python-first solutions.
- Keep user data safe and changes reversible.

## Repo layout
- Keep production add-on code in a dedicated package directory (for example `src/` or the add-on root package).
- Keep tests in `tests/`.
- Keep scripts and one-off tooling in `scripts/`.
- Treat `README.md` as the user-facing source of setup and usage truth.

## Setup and environment
- Use `python3` for scripts and local commands.
- Prefer a virtual environment for local development.
- Do not require network access for tests.
- If a local dev setup command is needed, document it in `README.md`.

## Beeminder integration rules
- Never hard-code API tokens, usernames, or secrets.
- Read secrets from config/environment and keep them out of source control.
- Use explicit error handling for HTTP failures, auth failures, and malformed responses.
- Handle time-based data carefully (timezone-aware where applicable).
- Keep API interactions behind a thin client/service layer to make testing easy.
- Mock Beeminder API calls in tests; do not hit live endpoints in automated tests.

## Anki add-on conventions
- Prefer Anki-supported hooks/APIs over monkey-patching internal behavior.
- Keep UI changes minimal, clear, and consistent with Anki UX patterns.
- Avoid blocking operations on the main UI thread.
- Surface actionable error messages to users (what failed and how to recover).
- Keep configuration migration-safe when fields/settings evolve.

## Working agreements (quality bar)
- Any behavior change must include new or updated tests.
- Keep changes scoped; do not rename or reformat unrelated files.
- No brittle logic:
  - no hard-coded machine-specific paths
  - no silent exception swallowing
  - no hidden network side effects
- If requirements are ambiguous, choose a reasonable default and document assumptions.

## What to do before finishing
- Prefer "prepare and prove" over "apply and hope."
- Validate locally where possible (lint, tests, static checks if available).
- Summarize clearly:
  - files changed (with paths)
  - commands executed and results
  - tests added or updated (names)
  - follow-ups, risks, or manual validation steps

## Boundaries
- Stop and call out explicitly if work requires:
  - account-level Beeminder permission changes
  - credential rotation or secret-manager changes
  - OS-level automation permissions
  - destructive data migration
