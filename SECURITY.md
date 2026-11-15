# Security policy

## Supported versions

Argus actively maintains the latest release and the `main` branch.

| Version or branch | Supported          |
| ----------------- | ------------------ |
| `main`            | :white_check_mark: |
| Latest release    | :white_check_mark: |
| Older releases    | :x:                |

## Scope

- **QuakeC mod (`src/`, `game/`)**: Pure QuakeC runs entirely inside the Quake engine's virtual machine (NetQuake protocol 15) with strict bounds and no filesystem or native system calls.
- **MCP server and wizard (`tools/argus_mcp`)**: The local web UI (`argus-mcp gui`) and the MCP stdio server bind locally (`127.0.0.1`) by default.
- **Python tooling (`tools/*.py`)**: Command-line utilities for local development and CI match analysis.
- **Release packages**: Each release zip is built by the `release` workflow from the tagged source and carries a build provenance attestation, attached to the release as `argus-<tag>.zip.sigstore.json`. Verify one with `gh attestation verify argus-<tag>.zip --repo saworbit/argus`, or offline with `--bundle argus-<tag>.zip.sigstore.json`.

## Reporting a vulnerability

If you discover a security vulnerability in the Argus tooling, the MCP server or a release package:

1. **Do not open a public issue.**
2. Report it privately through [GitHub security advisories](https://github.com/saworbit/argus/security/advisories/new). Sign in to GitHub to use the private reporting form.

### What to include

- A clear description of the vulnerability.
- Steps or a proof of concept that reproduces the behaviour safely.
- An impact assessment (for example local privilege escalation, command injection through CLI flags, or network exposure).

We will acknowledge receipt within 48 hours and coordinate a fix and advisory disclosure.

## How the repository is protected

Private vulnerability reporting, Dependabot alerts and security updates, secret scanning with push protection, CodeQL analysis and OpenSSF Scorecard are enabled. Every workflow pins its actions to a full commit SHA, and pull requests are checked by dependency review, `cargo deny` and a workflow security audit.
