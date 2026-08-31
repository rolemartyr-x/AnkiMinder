# MERGE_POLICY.md -- AnkiMinder

Written policy for what a Claude session may merge on its own versus what
always requires the repo owner's click. This exists so that "watch this PR"
has real signal to gate on (see `.github/workflows/ci.yml`), and so a
platform-level PR subscription -- which can happen without any explicit
tool call, see "Subscription is not authorization" below -- can never by
itself result in an unreviewed merge.

## Preconditions (apply to every tier)

No merge, of any tier, happens unless **all** of the following hold on the
PR's current head:

- CI (`test` and `lint` jobs in `.github/workflows/ci.yml`) is green.
- No merge conflict with the base branch.
- No open, unaddressed review thread.
- The PR is not a draft.
- The PR's diff matches its stated scope -- no unrelated files snuck in.

If any of these don't hold, the PR is not mergeable by Claude regardless of
tier -- keep driving it toward green/resolved (per the repo's PR-babysitting
rules) and wait.

## Risk factors

Four things decide a change's tier:

1. **What files it touches.**
   - *User-facing docs*: `README.md`, `config.md`.
   - *Tests only*: `tests/`.
   - *Core logic*: `ankiminder/beeminder/`, `ankiminder/services/`,
     `ankiminder/addon.py`, `ankiminder/config.py`, `ankiminder/exceptions.py`.
   - *Governance / how Claude operates*: `CLAUDE.md`, `AGENTS.md`,
     `MERGE_POLICY.md`, `.github/workflows/*`, `CONTRIBUTING.md`,
     `SECURITY.md`.
   - *Packaging*: `scripts/`, `manifest.json`, `dist/`.
2. **Additive-only vs. behavior-changing.** New tests, new docs, or a new
   opt-in config field that defaults to today's behavior is additive.
   Anything that changes what already-shipped code does for an existing
   user (including a bug fix -- by definition it changes behavior) is
   behavior-changing.
3. **Pre-approved batch or not.** Did the user, in the current
   conversation, explicitly review and approve the specific set of changes
   this PR contains (e.g. "yes, do all of bucket 1"), as opposed to Claude
   picking the work on its own initiative?
4. **Sensitive surface, regardless of size.** Anything touching the
   `beeminder_auth_token` path, HTTP transport/redirect handling, or what
   gets sent to the Beeminder API is inherently higher risk even as a
   one-line change.

## Tiers

### Tier 0 -- Auto-mergeable
Docs-only (user-facing docs) **or** tests-only, additive, no core-logic or
governance files touched, nothing on the sensitive surface (factor 4), and
CI green. Example: adding a regression test, fixing a typo in `README.md`.

### Tier 1 -- Auto-mergeable if pre-approved
Anything else the user explicitly pre-approved as a named, itemized batch
in the current conversation, where the pushed diff matches that batch with
no scope creep, CI green. Example: PR #20's bucket of independently-scoped,
pre-approved low-risk fixes.

### Tier 2 -- Always requires the user's click
Everything else, including:
- Any change to `ankiminder/beeminder/`, `ankiminder/services/`,
  `ankiminder/addon.py`, or `ankiminder/config.py` that was **not**
  pre-approved as a named batch (i.e. Claude proposing new behavior on its
  own).
- Any change to a *governance* file (`CLAUDE.md`, `AGENTS.md`,
  `MERGE_POLICY.md`, `.github/workflows/*`) -- these change what Claude is
  allowed to do, so they are never self-certifying no matter how small or
  "docs-only" they look. (PR #22, which edits `CLAUDE.md` itself, is Tier 2
  for exactly this reason, despite touching no code.)
- Anything on the sensitive surface (factor 4).
- Any PR that mixes a Tier 0/1 file with a Tier 2 file -- the whole PR
  inherits the higher tier.
- Anything where the tier is ambiguous. Default to Tier 2.

## Subscription is not authorization

A Claude session can end up subscribed to a PR's activity at the platform
level without any explicit `subscribe_pr_activity` call (this has happened
before -- see the note in `CLAUDE.md`). Because of that, **being subscribed
to a PR must never be treated as permission to merge it.** Subscription
only ever grants "watch, drive CI to green, resolve conflicts, respond to
review comments" behavior. The decision to actually merge is gated
exclusively by the tier rules above, checked fresh against the PR's current
diff and history each time -- not by whether or how the session came to be
watching.

## How this wires into PR-babysitting

- Claude may resume auto-subscribing to PRs it opens (see `CLAUDE.md`'s
  "Claude Session Behavior" section) now that CI gives a subscription
  something real to check.
- On a **Tier 0/1** PR: once the preconditions all hold, Claude may merge
  it without asking, then tell the user it did so and why (tier + which
  preconditions were verified).
- On a **Tier 2** PR: Claude keeps driving it to green and addressing
  review feedback as usual, but never clicks merge. Once every
  precondition holds, it posts a single "ready to merge" status (on the PR
  for a PR it owns, or to the user directly for a PR it's only watching)
  and stops -- no repeated pings once that status has been posted and
  nothing has changed since.
