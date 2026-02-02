# Security Policy

## Supported Scope

This project handles:
- Anki review metadata
- Beeminder API authentication tokens

## Reporting a Vulnerability

Please report vulnerabilities privately to the maintainer before public disclosure.

Include:
- affected version/commit
- reproduction steps
- impact assessment
- suggested mitigation (if available)

## Secret Handling

- Do not commit real API tokens.
- Keep local secrets in user-local config only.
- Use blank/default placeholders in repository config files.

## Hardening Notes

- API failures should be explicit and actionable.
- Do not silently swallow exceptions around sync/auth logic.
- Keep transport and business logic test-covered.
