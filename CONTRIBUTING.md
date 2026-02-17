# Contributing

Thanks for contributing.

## Development Rules

- Keep changes scoped to the task.
- Add or update tests for any behavior change.
- Prefer simple, testable Python code.
- Use Anki-supported hooks/APIs.

## Local Workflow

1. Create a branch from your release/develop branch.
2. Implement changes.
3. Run tests:
   - `python -m unittest discover -s tests`
4. Update docs if behavior or config changed.
5. Open a PR with:
   - summary of changes
   - test evidence
   - manual test notes (if Anki UI behavior changed)

## Commit Hygiene

- Use clear commit messages.
- Do not bundle unrelated refactors.
- Do not commit generated/local editor files.

## Sensitive Data Policy

Never commit:
- `beeminder_auth_token` values
- personal Anki profile data
- `.env` secrets
- key/cert files

If you accidentally commit a secret, rotate it immediately and clean history as needed.
