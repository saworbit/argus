# Security Policy

## Supported Versions

Argus actively maintains the latest release and the `main` branch.

| Version / Branch | Supported          |
| ---------------- | ------------------ |
| `main`           | :white_check_mark: |
| Releases (latest)| :white_check_mark: |
| Older releases   | :x:                |

## Security Scope & Boundaries

- **QuakeC Mod (`src/`, `game/`)**: Pure QuakeC code runs entirely inside the Quake engine virtual machine (NetQuake protocol 15) with strict bounds and no filesystem or native system calls.
- **MCP Server & Wizard (`tools/argus_mcp`)**: The local web UI (`argus-mcp gui`) and MCP stdio server bind locally (`127.0.0.1`) by default.
- **Python Tooling (`tools/*.py`)**: Command-line utilities designed for local development and CI match analysis.

## Reporting a Vulnerability

If you discover a security vulnerability in the Argus tooling, MCP server, or distribution packages:

1. **Do not open a public issue.**
2. Please report the issue privately using [GitHub Security Advisories](https://github.com/saworbit/argus/security/advisories/new) on the repository.
3. If GitHub Private Vulnerability Reporting is unavailable, contact the project maintainer via their GitHub profile contact info.

### What to Include

- A clear description of the vulnerability.
- Steps or proof-of-concept to reproduce the behavior safely.
- Impact assessment (e.g. local privilege escalation, arbitrary command injection via CLI flags, network exposure).

We will acknowledge receipt within 48 hours and coordinate a fix and advisory disclosure.
