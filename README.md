# Template — Salesforce DX Project

A Salesforce DX mono‑repo for <client>, containing metadata, configuration, and scripts for developing, testing, and deploying to Salesforce orgs. The primary package directory is `force-app` and the project targets API version 64.0.

## Overview

- Package dir: `force-app` (default)
- Config: `sfdx-project.json`, `config/project-scratch-def.json`
- Scripts: `scripts/apex/*.apex`, `scripts/soql/*.soql`
- Tooling: Salesforce CLI, LWC Jest, ESLint, Prettier, Husky/lint‑staged

## Requirements

- Node.js 18+ (LTS recommended)
- npm 9+
- Salesforce CLI (`sf`) installed and authenticated
  - Legacy `sfdx` works but `sf` is preferred

## Deploy to Sandbox or Dev Org

Use this path when working against a persistent org (e.g., a Developer Sandbox):

1) Authenticate:

   - `sf org login web -a <client sandbox>`

2) Deploy source:

   - `sf project deploy start -o <client sandbox>`

3) Open the org:

   - `sf org open -o <client sandbox>`

## Scripts

Defined in `package.json`:

- `npm run lint` — ESLint for Aura/LWC JS
- `npm test` / `npm run test:unit` — LWC Jest tests
- `npm run test:unit:watch` — Watch mode for tests
- `npm run test:unit:coverage` — Coverage report
- `npm run prettier` — Format supported files
- `npm run prettier:verify` — Check formatting

Pre-commit hooks (Husky + lint‑staged) format and lint changed files, and run related LWC tests.

## Project Structure

- `force-app/` — Default package directory with metadata
- `config/project-scratch-def.json` — Scratch org shape
- `scripts/apex/*.apex` — Apex snippets for developer use
- `scripts/soql/*.soql` — SOQL queries for investigations
- `jest.config.js` — LWC Jest configuration
- `eslint.config.js` — ESLint configuration
- `sfdx-project.json` — SFDX project config (API `64.0`)

## Development Flow

- Create a feature branch from `main`
- Open a Pull Request for review when ready

## Testing

## Linting & Formatting

- Lint: `npm run lint`
- Format: `npm run prettier`

The repo uses ESLint (including Salesforce plugins) and Prettier (with Apex and XML plugins). Pre-commit hooks enforce formatting and basic linting on staged files.

## Troubleshooting

- CLI not found: ensure `sf` is installed and on your PATH
- Auth errors: re-run `sf org login web -a <alias>`
- Deploy warnings: confirm target org alias and API version compatibility
- Node errors: use Node 18+ and run `npm ci` to install dev dependencies

## References

- Salesforce CLI: https://developer.salesforce.com/tools/sfcli
- SFDX Project Config: https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_ws_config.htm
- LWC Jest: https://github.com/salesforce/sfdx-lwc-jest
- VS Code Extensions: https://developer.salesforce.com/tools/vscode/
