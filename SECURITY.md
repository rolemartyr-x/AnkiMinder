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

### Known exposure surfaces for `beeminder_auth_token`

These are accepted, low-severity risks inherent to the add-on's platform and to the Beeminder API -- not bugs to be fixed here, but worth understanding:

- **Plaintext at rest.** The token is stored unencrypted in this add-on's `config.json`, under your Anki profile's add-on data directory (Anki's standard `addonManager.writeConfig`/`getConfig` storage -- there is no OS-keychain integration available to Anki add-ons). Anything with read access to that directory -- other local software, another Anki add-on, a synced/shared backup of your Anki profile -- can read it in cleartext.
- **Sent as a URL query parameter on some requests.** Beeminder's v1 API is query-parameter-only for `auth_token` on `GET` requests (there is no header-based alternative to switch to); this add-on's own datapoint-lookup calls use `GET`. Credentials in a URL are more exposed than in a header or POST body -- they can end up in server/proxy access logs on the request path, or get pasted into a bug report by a user copying a URL.

**What to do about it:**
- Avoid syncing or backing up your Anki profile to untrusted or shared locations while it contains a real token.
- Before pasting `config.json` contents, a screenshot, or a raw request/response log into a bug report or support request, redact `beeminder_auth_token`.
- If you suspect your token has leaked, revoke/regenerate it on Beeminder (`https://www.beeminder.com/api/v1/auth_token.json` after logging in) and update `config.json` with the new value.

## Hardening Notes

- API failures should be explicit and actionable.
- Do not silently swallow exceptions around sync/auth logic.
- Keep transport and business logic test-covered.
