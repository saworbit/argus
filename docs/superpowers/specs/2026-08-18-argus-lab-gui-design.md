# Argus lab GUI (deploy wizard)

Date: 2026-08-18
Status: shipped as 0.18 (2026-08-18). Operator guide
`tools/argus_mcp/README.md`.
Scope: human face of the existing lab tools. No new cartographer,
no engine change, no QuakeC.

## Problem

Attaching a BSP and putting it in the Argus mod is a four-gotcha
shell loop (navgen, register, fteqcc success line, copy to every
install). Agents have MCP. Humans do not.

## What it is

`argus-mcp gui` binds `127.0.0.1` (default port 7420) and opens a
one-page browser wizard. The page lists maps, accepts a `.bsp`
drop into `maps_local/`, generates nav (register), shows the nav
PNG plus the 0.17 brief, compiles, installs `progs.dat` to the
known copies, and restores from a dated backup.

The GUI only calls existing functions: `list_maps`, `cartograph`,
`nav_generate`, `compile_qc`, plus a new backup/restore helper.

## Non-goals

- 3D BSP view, in-engine overlay, packing id maps for shipping
- A second inspect API
- Binding a public interface
- Persisting path config to disk (process env only)

## Backups

`$ARGUS_ROOT/backups/<YYYYMMDD-HHMMSS>/` holds copies of
`lq1/progs.dat`, each install `progs.dat`, `src/progs.src`,
`src/argus_nav_dispatch.qc`, and every `src/argus_nav_*.qc`.
A `manifest.json` lists what was saved. Restore copies those
files back. Compile-and-install always takes a backup first.

## Launch

```
argus-mcp            # stdio MCP (unchanged)
argus-mcp gui        # wizard, opens the browser
argus-mcp gui --port 8080 --no-open
```
