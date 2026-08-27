# Argus lab MCP server

Date: 2026-08-17
Status: implemented through 0.18.0. Operator guide
`tools/argus_mcp/README.md` is authoritative for the shipped tool
surface; this file is the design history.
Scope: offline toolchain only. No QuakeC, no engine patches, no protocol change.
Operator guide: `tools/argus_mcp/README.md` (authoritative for the
shipped tool surface). This file is the design history.

This is the vanilla-charter reading of the KINETIC "Quake dev MCP server"
(docs/kinetic_ideas.md section 10). The durable idea is a structured lab
loop for the LLM. The parked parts (mvdsv, 100x tickrate, UDP RCON,
QuakeWorld) stay parked.

## Problem

Every behaviour change is supposed to be an A/B match. Today that loop is
tribal knowledge: compile from `src/` with a modern fteqcc, distrust the
exit code, copy `progs.dat`, `cd` to the right place so QuakeSpasm writes
`qconsole.log`, run a timed dedicated server, then hand `analyze_match.py`
two logs. Agents re-derive those steps from CLAUDE.md and regularly miss a
gotcha.

The MCP server is that loop as tools. The bot itself does not change.

## Goals

- An agent can compile, generate nav, run a timed headless match, and
  produce an A/B plot plus structured metrics without inventing a shell
  pipeline.
- The same binary works on any machine. Every executable and directory
  comes from config or environment. No baked-in Windows or Linux paths.
- A live dedicated server can be started, given console lines, inspected,
  and stopped inside one MCP session.
- Failure is structured. fteqcc warnings and errors come back as objects,
  not a raw blob. A missing `ARGUS_FTEQCC` names that key.

## Non-goals (v1)

- Reimplementing `argus_navgen.py` or `analyze_match.py` in Rust.
- QuakeWorld RCON, mvdsv, fast-forward simulation, memory inspect.
- Writing or rewriting QuakeC.
- More than one live match process.
- HTTP/SSE transport. stdio only.
- Guessing `python` vs `py` vs `python3`. `ARGUS_PYTHON` is required.

## Architecture

A long-lived Rust stdio MCP server. Crate name `argus-mcp`, tree path
`tools/argus_mcp/`. Official SDK: `rmcp` with features `server`, `macros`,
`schemars`, `transport-io`. Tokio for the match child and timers.

```
[Grok / Claude]
      stdio JSON-RPC
           |
      argus-mcp
        |  |  \
        |  |   `-- at most one QuakeSpasm dedicated child
        |  |         Unix: stdin = console (piped)
        |  |         Windows: CREATE_NEW_CONSOLE, no stdio pipe
        |  |         cwd    = the run directory
        |  |         qconsole.log harvested to runs/<name>.log
        |  |
        |  +-- $ARGUS_FTEQCC   (cwd = $ARGUS_SRC)
        |
        +-- $ARGUS_PYTHON $ARGUS_ROOT/tools/argus_navgen.py
        +-- $ARGUS_PYTHON $ARGUS_ROOT/tools/analyze_match.py
```

The MCP process is the session. There is no extra daemon. When the client
drops stdio, the server tears down the match child (send `quit`, then
kill) and exits.

The engine stays a harness. The server always launches with `-game` so
`autoexec.cfg` still enforces `sv_protocol 15` and `max_edicts 600`. The
server never passes protocol overrides.

## Config

No defaults that point at `C:\argus` or `/home/...`.

Load order (later wins):

1. Optional TOML, first hit: `$ARGUS_MCP_CONFIG`, else
   `$ARGUS_ROOT/tools/argus_mcp.toml` if `ARGUS_ROOT` is already in the
   environment, else `./tools/argus_mcp.toml` relative to the process cwd.
2. Process environment. Env always overrides the file.

`ARGUS_ROOT` is set in the environment or the TOML. If it is still
unset, 0.15 walks parents from the process cwd for
`game/argus/autoexec.cfg` and fills fteqcc / engine / basedir /
python when those files exist in the usual lab layout. The server
does not infer the root from the binary location. Explicit env
wins over discovery.

Required:

| Key | Meaning |
|-----|---------|
| `ARGUS_ROOT` | Repo root. Scripts live at `$ARGUS_ROOT/tools/`. |
| `ARGUS_FTEQCC` | Modern fteqcc executable. |
| `ARGUS_ENGINE` | Dedicated-capable Quake executable (QuakeSpasm in the lab). |
| `ARGUS_BASEDIR` | Engine `-basedir` (contains `id1/` and the game dir). |
| `ARGUS_PYTHON` | Python 3 interpreter used only to run the two known scripts. |

Optional, with defaults that are paths under the required keys:

| Key | Default |
|-----|---------|
| `ARGUS_GAME` | `argus` |
| `ARGUS_SRC` | `$ARGUS_ROOT/src` |
| `ARGUS_RUNS` | `$ARGUS_ROOT/runs` |
| `ARGUS_PROGS` | `$ARGUS_ROOT/lq1/progs.dat` (fteqcc pragma output) |
| `ARGUS_MAPS` | `$ARGUS_ROOT/maps_local` |

`config_check` always returns the resolved table (key, path, exists).
It never errors and never spawns. Other tools refuse to run if a
required key is missing or its path does not exist, and the error
names that key.

Install destinations after a successful compile (deduplicated):

1. `$ARGUS_ROOT/game/argus/progs.dat` (shippable master)
2. `$ARGUS_BASEDIR/$ARGUS_GAME/progs.dat` (what the next match will load)

Create parent dirs if needed. Never copy if compile did not print the
success line.

## Tool surface (v1, as designed)

Nine tools were the v1 API. 0.12 still has all of them. The shipped
surface is larger. Names below stay stable. The operator guide lists
the current set.

As of 0.16 the agent-facing loop is:

- `see` (one inspect): `project|lab|map|node|path|item|fn|file|search|const|live|bot|timeline|around|plan|run|last|knobs`
- `experiment` (compile + short match + duration-scaled lite A/B)
- `matrix_experiment` (one compile, short probe on each known map)
- `compare_runs` (unscaled, lite by default, `detail=full` for both
  tapes)
- MCP resources `argus://project`, `argus://map/{name}`,
  `argus://fn/{name}`, `argus://path/{spec}`, `argus://search/{needle}`,
  `argus://run/{name}`
- Extra spec tools stay, descriptions start with "Prefer …"

### `config_check`

No arguments. Returns each key, resolved path, and whether it exists.
This is the first call on a new machine.

### `compile_qc`

Optional argument: `install` (bool, default true).

Runs `$ARGUS_FTEQCC` with cwd `$ARGUS_SRC`. Creates `$ARGUS_ROOT/lq1`
first (fteqcc exits 0 on a failed write if the dir is missing).

Success is the line `Compile finished` containing `id format`, not the
process exit code. On success and `install=true`, copy `ARGUS_PROGS` to
the two install paths. On failure, do not copy.

Return: `ok`, `success_line`, `diagnostics` (list of `{severity, file,
line, message}` parsed from fteqcc stdout/stderr), `progs_bytes`,
`installed_to`.

### `nav_generate`

Arguments: `bsp` (path or short name), `map` (mapname used in the QC
symbol), optional `out_qc`, optional `out_png`.

`bsp` resolves in order: as given if the path exists; `$ARGUS_MAPS/<bsp>`;
`$ARGUS_MAPS/<bsp>.bsp`. Same rule for `analyze_match`.

Defaults: `$ARGUS_SRC/argus_nav_<map>.qc` and
`$ARGUS_RUNS/nav_<map>.png`. Always passes `--no-dispatcher`. The
dispatcher file is hand-maintained and this tool must not overwrite it.

Invokes `$ARGUS_PYTHON $ARGUS_ROOT/tools/argus_navgen.py ...`.
Return: stdout tail, output paths, ok/fail.

### `match_run`

The A/B workhorse. Starts a dedicated match, waits `duration_sec`,
stops, harvests the log, returns a structured ARGLOG/ARGEVT summary.

Arguments:

- `map` (required)
- `duration_sec` (required, integer, min 10, max 600)
- `run_name` (optional; default `mcp_YYYYMMDD_HHMMSS` in UTC)
- `dedicated_slots` (optional; default 8)

Launch line (fixed flags, no free-form command string):

```
$ARGUS_ENGINE -dedicated <slots> -basedir $ARGUS_BASEDIR -game $ARGUS_GAME
    -condebug +developer 1 +deathmatch 1 +map <map>
```

The server creates `$ARGUS_RUNS/<run_name>/` and uses it as the child
cwd. After stop, it copies `qconsole.log` (falling back to captured
stdout if that file is missing) to `$ARGUS_RUNS/<run_name>.log` so
`analyze_match.py` keeps its current calling convention.

Error if a match is already live. Duration is wall-clock of the child,
not in-game `time`.

### `match_start` / `match_command` / `match_status` / `match_stop`

Interactive control of the same single child `match_run` uses.

- `match_start`: as `match_run` but returns once the process is up.
  Optional `duration_sec` still auto-sends `quit` later.
- `match_command`: one console line on stdin. Reject empty strings and
  anything containing a newline. No raw shell.
- `match_status`: `running`, pid, map, elapsed_sec, remaining_sec if
  timed, `log_path`, last 40 log lines, `exit_code` if dead.
- `match_stop`: write `quit\n`, wait `timeout_sec` (default 5), kill if
  still alive, harvest the log. Always safe to call.

`match_run` is implemented as start + wait + stop on that controller.
A session drop runs the same teardown.

### `analyze_match`

Arguments: `bsp`, `log_a`, `out_png`, optional `log_b`, optional
`nav_json`. Paths may be absolute or relative to `ARGUS_ROOT`.

Invokes `$ARGUS_PYTHON $ARGUS_ROOT/tools/analyze_match.py` with the
existing positional convention. Also parses `log_a` (and `log_b` if
present) in Rust and returns the same per-bot metrics the plotter
prints (`avg` speed, `cover` cells, `goals`, `stalls`, `frags`,
`deaths`) plus ARGEVT counts by type (`engage`, `hazard`, `abandon`,
`routefail`, `weapon`, `death`, ...).

The PNG is a side effect for humans. The JSON metrics are what the
agent should read.

### `list_runs`

Lists top-level `*.log` in `ARGUS_RUNS` only (the harvested
`<name>.log` files, not `<name>/qconsole.log` inside run cwd dirs).
Return name, bytes, mtime. Newest first.

## Match process rules

- At most one child. A second start is a tool error, not a silent kill.
- Unix: stdin is the console. This is the NetQuake-legal substitute
  for the parked QW RCON idea.
- Windows: QuakeSpasm `Host_Error`s on `GetNumberOfConsoleInputEvents`
  if stdin is a pipe. 0.13+ uses `CreateProcess` with
  `bInheritHandles=FALSE` and a hidden `CREATE_NEW_CONSOLE`. Harvest
  is `qconsole.log`. 0.15 injects `tune` / `match_command` via
  `AttachConsole` + `WriteConsoleInputW` and restores the MCP stdio
  handles so JSON-RPC is not stolen. Not live-verified against
  QuakeSpasm; if inject fails, pass `+skill` at start.
- A harvested log with no `ARGLOG`/`ARGEVT` is a tool error, not
  `ok: true`.
- QuakeSpasm on Windows writes `qconsole.log` to cwd, not the game dir.
  Setting cwd to the run directory is the portability fix, not an
  `#ifdef`.
- On MCP shutdown: `quit` (Unix stdin), wait 2 s, kill. Never leave a
  dedicated server orphaned.
- Do not pass `+sv_protocol`, `+max_edicts`, or any flag that would
  override `game/argus/autoexec.cfg`.

## Log summary parser

A small Rust reader, aligned with `tools/analyze_match.py`:

- `ARGLOG`/`BOTLOG` v1: name, t, pos, spd, mode, stalls, goals,
  optional hp/frags.
- `ARGEVT` death lines for the death count.
- Other `ARGEVT` verbs counted by token.

Per bot, last ARGLOG sample wins for counters (same as the Python
script). Used by `match_run` and `analyze_match`. Fixtures come from
a trimmed real log in `tools/argus_mcp/tests/fixtures/`.

fteqcc diagnostics: one regex family for `file:line: severity: message`
plus a boolean on the `Compile finished ... (id format)` line. Unknown
lines stay in a `raw_tail` (last 30) so we do not drop surprises.

## Error handling

| Case | Behaviour |
|------|-----------|
| Missing config key or path | All tools except `config_check`: error naming the key |
| fteqcc no success line | `ok=false`, diagnostics, no copy |
| Python script non-zero | `ok=false`, stderr tail |
| Match already running | Tool error with current `run_name` |
| `match_command` with no child | Tool error |
| Child exits early | `match_status` / `match_run` report `exit_code` and log path |
| `duration_sec` out of range | Schema/validation error before spawn |
| Path escape in `run_name` | Reject. `run_name` is `[A-Za-z0-9._-]+` only |

The server executes four programs only: `ARGUS_FTEQCC`, `ARGUS_ENGINE`,
`ARGUS_PYTHON` on `argus_navgen.py`, `ARGUS_PYTHON` on
`analyze_match.py`. No `cmd /c`, no `sh -c`.

## Crate layout

```
tools/argus_mcp/
  Cargo.toml
  Cargo.lock          # committed, reproducible builds
  README.md           # operator guide (authoritative)
  src/
    main.rs           # stdio entry, graceful shutdown
    server.rs         # tools, prompts, resources, ServerHandler
    config.rs
    compile.rs
    navgen.rs
    match_ctrl.rs
    analyze.rs
    parse_fteqcc.rs
    parse_arglog.rs
    cartograph.rs     # BSP ingest + brief
    intel.rs          # brief, compare, lite, scaled
    lab.rs
    live.rs
    learn.rs
    project.rs        # see what=project
    qc_index.rs       # fn/file/search, calls/callers
    nav_graph.rs      # path/item/around, BFS
    tape_view.rs      # deep bot + timeline
    diagnose.rs
    engine.rs         # Unix pipe / Windows CreateProcess
    see_alias.rs
    resources.rs      # argus://...
    session.rs        # last-seen
    bsp.rs
    paths.rs
  tests/
    fixtures/
      compile_ok.txt
      compile_fail.txt
      snippet.log
```

Edition 2021. Commit the lockfile. Do not commit `target/`. Add
`tools/argus_mcp/target/` to `.gitignore` if the repo has one; otherwise
a crate-local note in the README is enough.

## Client wiring

stdio only. Recommend a release binary so session startup is not a
cargo build:

```
cargo build --release --manifest-path tools/argus_mcp/Cargo.toml
```

Project-scoped examples (paths filled by the operator, never committed
with machine-local exe paths that we invent):

Grok (`.grok/config.toml`):

```toml
[mcp_servers.argus]
command = "C:/path/to/argus-mcp.exe"
startup_timeout_sec = 15
tool_timeout_sec = 700
tool_timeouts = { match_run = 700, compile_qc = 120, nav_generate = 180, cartograph = 60, experiment = 400, probe = 180 }
```

Claude-compatible (`.mcp.json`) uses the same command and an `env` block
for the required keys. A committed `.mcp.json.example` and
`tools/argus_mcp.toml.example` show the keys. Real env values stay
uncommitted.

`match_run` at 600 s plus harvest needs a client tool timeout above
that. Document 700 s. The server itself does not need the client to
poll if `match_run` is used.

## Testing

Must pass without Quake installed:

- `config` merge: env overrides TOML, defaults fill optional keys,
  missing required keys error by name.
- `parse_fteqcc`: success fixture is `ok`; failure fixture is not;
  a log with exit-looking noise but no `Compile finished` / `id format`
  line is failure.
- `parse_arglog`: fixture yields known per-bot stalls/goals/frags and
  ARGEVT counts.
- `see` vocabulary covers `project` / `last` / `run`.
- `compare_briefs_scaled` does not flag a short tape as an engagement
  collapse.
- Resource list includes `argus://project`.
- Nav BFS finds a two-hop walk+jump. Path refs parse `dm4:56-72`
  and `dm4:quad->lg`. QC search hits `CONTENT_LAVA` in this tree.

Gated behind the required env (ignored if unset):

- `config_check` integration.
- `compile_qc` against this tree, assert install paths exist and are
  non-empty.

No CI requirement to launch the engine. A live `match_run` is a
manual lab check, recorded the usual way under `runs/`.

## What this is not

This is not the KINETIC Rust/mvdsv sketch. It does not fast-forward
physics, inspect VM memory, or speak RCON. If that track is ever
opened it is a second deliverable beside this server, the same way a
forked engine would sit beside vanilla `progs.dat`.

## v0.11 (LLM usability)

`see what=project` orients on the tree. `experiment` is compile plus
a short match plus a duration-scaled compare, so a 30 s probe is not
judged as an engagement collapse against the 185 s baseline. Session
last-seen (`see what=last`) and MCP resources (`argus://project`,
`argus://map/{name}`, `argus://fn/{name}`) give a client a way to look
into the project and into Quake without inventing a pipeline.

## v0.12 (effective defaults)

Default `experiment` / `compare_runs` / `brief_run` returns are lite
(verdict, gates, totals, next_steps), not two full briefs. `lab_status`
no longer cartographs every map. Windows dedicated spawn uses
`CREATE_NEW_CONSOLE` so the child does not `Host_Error` on a piped
stdin; harvest is still `qconsole.log`. Live `tune` on that path is
not available. Extra spec tools stay, but their descriptions defer
to the native set.

## v0.13 (resilience)

Windows spawn uses `CreateProcess` with `bInheritHandles=FALSE` and a
hidden `CREATE_NEW_CONSOLE`, so the child does not inherit the MCP
JSON-RPC pipe. Matches fail fast if the dedicated process dies before
ARGLOG, with a diagnosis and log tail. Dead children are reaped before
the next start. `see` accepts aliases and defaults to `project`. Tool
errors are `{error, hint}`. `compile_qc` times out at 90 s.

## v0.14 (deeper see)

`see` can walk the nav graph (`path` / `item` / `around` / deeper
`node` with link kinds), read QC with calls and callers, grep the
Argus tree (`search`), slice a file, and open a bot tape
(`bot` / `timeline`). Still one inspect tool.

## v0.15 (fixes)

MegaHealth is `item_health` spawnflags 2. QC function slice ignores
braces in comments and strings. `call_re` matches every `keep_fn`
name. Bare `ARGEVT death` is not double-counted. Windows `tune`
injects via `AttachConsole`/`WriteConsoleInputW` and restores MCP
stdio. `analyze_match` / `nav_generate` attach PNG image blocks.
`nav_sync_dispatch` and `matrix_experiment` landed. `see what=plan`
reads GOAP plan events. Config can discover the tree from
`game/argus/autoexec.cfg`. Cartograph reports an edict estimate
(waypoints plus entity lump) against vanilla `max_edicts 600`.

Alongside this crate, the QC tree shipped prize-only rocket-jump
pads, `Argus_HazardSteer`, and GL/RL loft. Those are bot behaviour,
not MCP tools; the operator guide points at them so a `see` session
does not treat dm4 quad as a parked idea.

## v0.16 (closed-loop lab)

Cursor `since_line` on `match_status`, `see what=status`, and
`live_snapshot`. Atlas and nav-graph caches invalidate on file
mtime. Item snap prefers a hull-1-clear eye line and labels
elevator / blocked_by_door. Causality follows one relay hop and
tags `func_door_secret`. Spawnflags 2048 items drop out of
deathmatch control. Inspect BFS walks rocket, lift and swim.
`cartograph generate_nav=true` passes `--register` by default.
`matrix_experiment` includes dm3. Experiment baseline is
`ab_dm4_water` (fallback `ab_dm4_parity`). `learn_hotspots`
stays report-only.

## v0.17 (honest judge, islands, costs)

Hull-0 lava in Rust briefs, same rule as `analyze_match.py`.
Per-map A/B bars (dm4 / dm2 / dm3). dm2 baseline `ab_dm2_lava`.
Cartograph briefs add `graph_cuts`, `door_cuts`, `corridor_misses`.
`learn_hotspots` writes `src/argus_nav_<map>.costs.json`; navgen
inflates those cells and drops lava-crossing walk links.

## v0.18 (human deploy wizard)

`argus-mcp gui` binds `127.0.0.1` and opens a one-page wizard:
attach BSP, generate nav, show the nav PNG plus the 0.17 brief,
compile, install, dated backup and restore. Stdio MCP is unchanged.
See `docs/specs/2026-08-18-argus-lab-gui-design.md`.
