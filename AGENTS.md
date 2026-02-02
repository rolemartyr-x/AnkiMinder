# AGENTS.md (Salesforce repo standard)

## Project context
- This is a Salesforce DX project.
- Source of truth for metadata is under `force-app/`.
- Prefer Salesforce best practices at all times.
- Prefer declarative solutions first, then Apex, then integrations.
- Use the **new `sf` CLI only**. Do not use legacy `sfdx` commands.

## Repo layout
- Salesforce metadata: `force-app/main/default/`
- Apex: `force-app/main/default/classes/`
- Flows: `force-app/main/default/flows/`
- Lightning Web Components: `force-app/main/default/lwc/`

## Org configuration (repo-specific)
- Target org alias for this repo: **MarlinPricing**
- Default target org must be set before running any commands:
  - `sf config set target-org=MarlinPricing`

## Setup commands
- Use `python3` for scripts; `python` may be unavailable in this environment.
- Authenticate (choose one):
  - Web login:  
    `sf org login web -a MarlinPricing -r https://test.salesforce.com`
  - Device login:  
    `sf org login device -a MarlinPricing -r https://test.salesforce.com`
- Confirm target org:
  - `sf org display --target-org MarlinPricing`

## Common dev commands (only when explicitly requested)
### Deploy / retrieve
- Deploy source to org:
  - `sf project deploy start --source-dir force-app --target-org MarlinPricing`
- Retrieve source from org:
  - `sf project retrieve start --source-dir force-app --target-org MarlinPricing`

## Testing
### Apex tests
- Run all local Apex tests:
  - `sf apex run test --test-level RunLocalTests --target-org MarlinPricing`
- Run specific Apex test classes:
  - `sf apex run test --class-names MyClassTest --target-org MarlinPricing`

### Flow tests
- When Flows are created or modified, prefer running Flow tests.
- If supported by the org, use the unified test runner:
  - `sf logic run test --test-category Flow --test-level RunLocalTests --synchronous --target-org MarlinPricing`
- Preferred combined run for final validation (Apex + Flow):
  - `sf logic run test --test-category Apex --test-category Flow --test-level RunLocalTests --synchronous --target-org MarlinPricing`
- Notes:
  - Flow tests use the `FlowTesting.<...>` naming convention.
  - Running Flow tests may require elevated permissions such as “View All Data”.
  - If Flow tests are not available or fail due to org constraints, use Apex-based validation via `Flow.Interview` and document the limitation.

## Working agreements (quality bar)
- Any Apex change must include:
  - New or updated unit tests covering the change.
  - Unit-testable seams for callouts, time, randomness, and external dependencies.
- Any Flow change must include:
  - Explicit fault paths on elements that can fail.
  - Flow Tests where feasible, otherwise documented Apex or manual validation.
- Do not introduce brittle logic:
  - No hard-coded IDs.
  - No environment-specific branching unless explicitly required.
- Keep changes scoped:
  - Do not reformat or rename unrelated files.
  - Do not rename metadata unless required by the task.

## Apex conventions
- Bulk-safe and governor-safe code only.
- No SOQL or DML in loops.
- Prefer Custom Metadata or Custom Settings for configuration.
- Surface meaningful, actionable error messages.
- Follow consistent naming and layering patterns (service, selector, domain, test).

## Flow conventions
- Prefer subflows for reuse and testability.
- Use consistent entry criteria and decision outcomes.
- Use fault connectors on:
  - Create, Update, Delete Records
  - Callouts
  - Subflows
  - Invocable actions

## What to do before finishing
- **Do NOT deploy or retrieve unless explicitly instructed.**
- Prefer “prepare and prove” over “apply”.

### Required before final response
- Validate locally where possible.
- Run tests against the target org when feasible:
  - Apex:
    - `sf apex run test --test-level RunLocalTests --target-org MarlinPricing`
  - Apex + Flow (if Flow work was involved and supported):
    - `sf logic run test --test-category Apex --test-category Flow --test-level RunLocalTests --synchronous --target-org MarlinPricing`
- Summarize clearly:
  - Files changed (with paths)
  - Commands executed and results
  - Tests added or updated (names)
  - Follow-ups, risks, or manual steps for the reviewer
  - The exact deploy command the reviewer should run if they choose to deploy

## Boundaries
- If a task requires changes to:
  - Org configuration
  - Permissions
  - Connected apps
  - Managed packages  
  stop and call it out explicitly.
- If requirements are ambiguous, propose a default approach and list assumptions instead of stalling.
