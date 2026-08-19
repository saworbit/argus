# Quake MCP server spec (captured)

Provenance: pasted 2026-08-17 as "Architecture and engineering design
specification: Quake Model Context Protocol (MCP) server for autonomous
bot development" with the instruction to capture it and implement.
The project remains Argus. The spec was written for mvdsv / FTEQW /
UDP RCON / 100x tickrate and a vision client. That is not the Argus
charter. Triage first, then the document as received (formatting
cleaned, wording preserved).

## Triage against the Argus hard constraints

Charter: pure vanilla QuakeC, protocol 15, max_edicts 600, no engine
extensions, the engine is a harness. The MCP may use any language.

### Native loop (0.18, prefer this)

The lab an agent should use is in `tools/argus_mcp/README.md`:

1. `see what=project` then `see what=map name=dm4` (islands, door
   cuts, corridor misses, hull-0 lava rule in the brief).
2. Deeper inspect, still `see`: `path` (`dm4:quad->lg`, walks
   rocket/lift/swim as well as walk/drop/jump/tele), `item`,
   `search`, `fn` (source plus calls/callers), `bot` / `timeline` /
   `plan`.
3. `experiment` after a QC edit (compile + short match +
   duration-scaled lite A/B against `ab_dm4_water`; dm2 uses
   `ab_dm2_lava`). `matrix_experiment` for dm2/dm3/dm4/dm6/lqdm2
   after one compile.
4. `compare_runs log_b=latest` for a full-length unscaled verdict.
5. `tune` is live: Unix stdin, Windows `AttachConsole` inject. If
   inject fails, pass `skill` on start. The dedicated child still
   uses a hidden console that does not inherit the MCP pipe.
6. Live tails: `match_status since_line=N` (and `see what=status`)
   return only new lines plus `next_line`.
7. Humans attach a map with `argus-mcp gui` (localhost wizard).
   Agents do not drive the browser.

### Shipped extra tools (this capture)

These five names are **extra** MCP tools. They do not replace
`compile_qc`, `cartograph`, `match_run`, `tune`, or `analyze_match`.

| Extra name | Extra job | Native tool that stays |
|------------|-----------|------------------------|
| `quake_compile_qc` | Optional `source_directory`; no install unless that dir is the lab `src/`. | `compile_qc` |
| `bsp_inspect_entities` | Raw entity lump + `filter_classname`. | `cartograph` |
| `bot_simulate_match` | Batch K/D / pickup / nav-error report. Default 300 s. | `match_run` |
| `rcon_exec` | Whitelisted stdin plus log tail. | `tune` |
| `bot_capture_pov_frame` | Parked POV hook; PNG substitutes. | `analyze_match` |

Feedback tiers as implemented:

1. Static: `compile_qc` structured diagnostics (`quake_compile_qc` extra).
2. Macro: `experiment` / `brief_run` / `compare_runs` (lite by default).
3. Micro: `see what=live` / ARGLOG tape (not a new bprint JSON; bprint is
   invisible on an empty dedicated server).
4. Visual: nav PNG + trajectory plot. In-engine TE_LIGHTNING2 and POV
   screenshots are parked.

### Parked (charter or engine-track)

- mvdsv / FTEQW / UDP RCON.
- `sys_ticrate 0.001` + `host_framerate 0.01` as 100x dilation. That
  changes `frametime` and therefore Argus physics. A/B matches must
  stay on the same timestep as a human listen server.
- `bot_capture_pov_frame`, `cam_target_bot`, `screenshot_to_file`,
  `r_drawbotnav`.
- QC `Debug_DrawLine` via TE_LIGHTNING2 (needs a connected client).
- QC `Bot_DumpDecisionJSON` via `bprint` (invisible on dedicated;
  ARGLOG/ARGEVT via `dprint` already fills this role).

If the engine track is ever opened, those stay a second deliverable
beside this server. Vanilla `progs.dat` remains canonical.

---

## Captured specification (content preserved, formatting cleaned)

# Comprehensive engineering specification: Quake MCP server for autonomous bot development

## 1. System vision and problem statement

Developing competitive autonomous bot AI in vanilla Quake (id Tech 2)
using standard QuakeC (progs.dat) presents severe feedback bottlenecks:

- The manual verification loop: edit .qc, run an external compiler,
  launch the engine, spawn bots, spectate 10 to 20 minutes, note
  failures, repeat.
- Lack of direct agent observability: raw text logs or visual
  gameplay, no introspective API for compilation, trigger topology,
  engine state, or sightlines.
- The vanilla constraint: state-of-the-art behaviour without modifying
  engine C means pushing the QuakeC VM to its limits.

The proposed server is a JSON-RPC stdio control plane between an LLM
and the Quake execution environment.

Proposed layout (as captured):

```
LLM agent
  stdio MCP
    compilation hub (fteqcc)
    spatial / map entity inspector
    headless fast-forward sim (100x)
    live UDP RCON
    tick-state JSON stream
    multi-modal vision (POV)
      -> mvdsv / FTEQW runtime
```

Argus ships the first two hubs and a physics-accurate dedicated match
runner. The last four hubs are parked as above.

## 2. Core architectural rationale

### 2.1 Distinct tools, not one stdout scraper

An LLM solving a navigation deadlock needs trigger connectivity. An
LLM tuning combat needs aggregate match metrics. Separate tools, same
as the Argus server already does.

### 2.2 Four feedback tiers

1. Static code diagnostics (fteqcc JSON).
2. High-level macro analytics (frags, stalls, item clocks).
3. Microscopic tick dumps (entity position, goal state).
4. Multi-modal visual streams (debug rays, POV).

### 2.3 Headless fast-forward

The capture wants uncapped tickrates (`sys_ticrate 0.001`,
`host_framerate 0.01`) so 20 minutes of match time finish in 3 to 5
seconds. Parked for Argus A/B: that timestep is not the listen-server
timestep the charter tests against.

## 3. Tool schemas (as captured)

### 3.1 quake_compile_qc

Compiles progs.src via fteqcc. Inputs: `source_directory` (required),
`optimization_level` (`-O0` / `-O2` / `-O3`, default `-O3`).

Argus: directory is `ARGUS_SRC`. Optimisation flags are ignored so
the id-format `progs.dat` stays protocol-15 safe.

### 3.2 bsp_inspect_entities

Reads BSP lump 0. Inputs: `map_name` (required, no extension),
`filter_classname` (optional).

### 3.3 bot_simulate_match

Headless accelerated match. Inputs: `map_name` (default dm6),
`duration_seconds` (default 300), `bot_count` (default 2),
`time_dilation` (default 100).

Argus: three bots (Reap, Omi, Zeus) are compiled in. `bot_count` and
`time_dilation` are accepted and documented; dilation does not change
physics.

### 3.4 rcon_exec

UDP RCON. Input: `command`.

Argus: dedicated stdin whitelist (`tune`).

### 3.5 bot_capture_pov_frame

Client screenshot from a bot eye. Inputs: `bot_client_id`,
`render_debug_overlays`.

Argus: parked. Tool returns why, plus paths to nav/trajectory PNGs if
present.

## 4. Component sketches (as captured)

The capture included a stdio JSON-RPC loop, an fteqcc diagnostic
regex (`file:line: severity: message`), an mvdsv runner that scraped
"was fragged by" / "picked up" / `NAV_STUCK` / `[TACTIC_AMBUSH_SPRING]`,
and an RCON screenshot pipeline.

Argus already parses ARGLOG/ARGEVT instead of English obituaries, and
already parses fteqcc with that regex family. The ambush token is a
future QC event, not a parser we invent.

## 5. In-game debug sketches (as captured)

`Debug_DrawLine` via TE_LIGHTNING2, ambush perimeter boxes, and
`Bot_DumpDecisionJSON` via sequential `bprint`. Parked: dedicated
servers have no viewer, and `bprint` does not appear on an empty
dedicated. ARGLOG remains the tick dump.

## 6. End-to-end workflow (as captured)

1. Propose a QC change.
2. `quake_compile_qc`.
3. `bot_simulate_match`.
4. `bsp_inspect_entities` if a spatial failure shows up.
5. `bot_capture_pov_frame` (parked; use `analyze_match` PNG).
6. Adjust and repeat.

Argus workflow: `see what=project` then `see what=map name=dm4` then
`experiment` (or `matrix_experiment`). Full-length: `compile_qc` then
`match_run` then `compare_runs log_b=latest`. Extra names stay for
clients that ask for them; they do not replace the native loop.

## 7. Performance matrix (as captured)

The capture listed sub-150 ms compile, sub-10 ms entity parse,
2.5 s per 5-minute match, sub-20 ms RCON, sub-100 ms POV. Compile and
entity parse are in that band on this machine. Match time is wall-clock
of QuakeSpasm dedicated, not 100x.
