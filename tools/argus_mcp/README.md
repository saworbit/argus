# Argus lab MCP server

Rust stdio MCP server for the Argus lab. It compiles QuakeC, ingests
maps, runs headless matches, and briefs the result the way this
project already judges A/B. Toolchain only: it does not change QuakeC
or the engine.

Current version: **0.18.0**. Operator guide (this file). Design
history: `docs/specs/2026-08-17-argus-mcp-design.md`.
Captured external spec and triage: `docs/mcp_quake_dev_spec.md`.

```
cargo test --manifest-path tools/argus_mcp/Cargo.toml
cargo build --release --manifest-path tools/argus_mcp/Cargo.toml
```

Binary: `tools/argus_mcp/target/release/argus-mcp` (`.exe` on
Windows). Point the client at the release binary so startup is not a
cargo build. Restart the client after every rebuild. The running
process locks the exe on Windows (`Access is denied` on
`argus-mcp.exe`). Do not commit `target/`.

## Human deploy wizard

Same binary, not MCP. Design:
`docs/specs/2026-08-18-argus-lab-gui-design.md`.

```
argus-mcp gui
argus-mcp gui --port 7420 --no-open
```

Binds `127.0.0.1` only (never a public interface) and opens a
browser. One page:

- path strip (repo root, Quake basedir, game dir) for this process
- map list from `list_maps` (bsp / pak / nav / dispatcher flags)
- drop a `.bsp` into `maps_local/` (BSP29 check; simple names only)
- **Generate nav** (`nav_generate` with `--register`)
- **Compile and install** (backup first, then `compile_qc`)
- **Backup only** / **Restore**

After generate it shows `runs/nav_<map>.png` and the 0.17
cartographer brief (islands, door cuts, corridor misses, edicts).
Id maps stay on this machine; the wizard will not pack them.

Compile always writes `$ARGUS_ROOT/backups/<YYYYMMDD-HHMMSS>/`:
`lq1/progs.dat`, each install `progs.dat` (lab basedir, `game/argus`,
and the rerelease Saved Games copy if that folder exists),
`src/progs.src`, `src/argus_nav_dispatch.qc`, every
`src/argus_nav_*.qc`, plus `manifest.json`. Restore copies those
files back. `backups/` is gitignored.

Agents keep using `see` / `experiment`. The GUI only buttons the
same functions.

## What it is for

An agent should not invent a shell pipeline from CLAUDE.md. The
repo file `AGENTS.md` is the session protocol. The loop is:

1. `see what=project` (or open `argus://project`) for the tree, maps,
   and the next call.
2. `see what=map name=dm4` to ingest the BSP as a brief.
3. Look deeper without grepping: `see what=item name=dm4:quad`,
   `see what=path name=dm4:quad->lg`, `see what=search name=CONTENT_LAVA`,
   `see what=fn name=Argus_HazardSteer` (source plus calls and callers),
   `see what=plan name=latest` for GOAP plan events.
4. After a QC edit: `experiment map=dm4 duration_sec=30 skill=2`
   (compile + match + duration-scaled lite compare). Several maps:
   `matrix_experiment`.
5. `see what=last` for this process's last experiment. `tune
   command="skill 3"` then `see what=live` for a running child
   (Unix stdin; Windows console inject).

The long form (`compile_qc` → `match_run` → `compare_runs`) is still
there. Use it for a full-length, unscaled A/B (185 s vs the shipped
baseline). `experiment` is the one-call loop.

Read-only tools need only `ARGUS_ROOT`. Compile, navgen, and match
also need the compiler, engine, basedir, and Python.

## Config

No baked-in machine paths. Required for a full lab:

| Key | Meaning |
|-----|---------|
| `ARGUS_ROOT` | Repo root. Scripts live at `$ARGUS_ROOT/tools/`. |
| `ARGUS_FTEQCC` | Modern fteqcc executable. |
| `ARGUS_ENGINE` | Dedicated-capable Quake (QuakeSpasm in the lab). |
| `ARGUS_BASEDIR` | Engine `-basedir` (contains `id1/` and the game dir). |
| `ARGUS_PYTHON` | Python 3, used only for `argus_navgen.py` and `analyze_match.py`. |

Optional, with defaults under `ARGUS_ROOT`:

| Key | Default |
|-----|---------|
| `ARGUS_GAME` | `argus` |
| `ARGUS_SRC` | `$ARGUS_ROOT/src` |
| `ARGUS_RUNS` | `$ARGUS_ROOT/runs` |
| `ARGUS_PROGS` | `$ARGUS_ROOT/lq1/progs.dat` |
| `ARGUS_MAPS` | `$ARGUS_ROOT/maps_local` |

Load order: optional TOML, then env. Env wins. TOML path is
`$ARGUS_MCP_CONFIG`, else `$ARGUS_ROOT/tools/argus_mcp.toml`, else
`./tools/argus_mcp.toml`. If `ARGUS_ROOT` is still unset, the server
walks parents from the process cwd for `game/argus/autoexec.cfg` and
fills fteqcc / engine / basedir / python when those files exist in
the usual lab layout. Explicit env still wins.

`config_check` always returns the resolved table and never errors.
Other tools name the missing key and refuse.

Examples (fill real paths; do not commit secrets or this machine's
exe paths as if they were defaults): `tools/argus_mcp.toml.example`,
`.mcp.json.example`.

## Inspect (`see` and resources)

`see` is the one inspect call. Pass `what` and, when needed, `name`.
Omit `what` (or pass `start` / `orient`) for `project`. Aliases:
`qc`/`func` → `fn`, `atlas` → `map`, `session` → `last`,
`bots` → `live`, `route` → `path`, `grep`/`find` → `search`,
`pickup` → `item`, `events` → `timeline`, `near`/`pos` → `around`,
`goap`/`goalplan` → `plan`, `dem`/`replay` → `demo`.
`see what=help` prints the vocabulary.

Tool errors are JSON `{error, hint}` with a next call.

| `what` | `name` | Returns |
|--------|--------|---------|
| `project` | | Tree: QC files, maps, live vs compile, next call |
| `help` | | This vocabulary plus resource URIs |
| `lab` | | Dashboard: config, maps (bsp/nav/dispatcher), recent runs, recommend |
| `map` | `dm4` | Cartographer brief. `detail=full` for every entity |
| `recipe` | `dm4` | Just the match / compare line |
| `node` | `dm4:56` | Waypoint, out/in links (including rocket/lift/swim), nearby control |
| `path` | `dm4:56-72` or `dm4:quad->lg` | BFS on the inspect graph (walk/drop/jump/tele/rocket/lift/swim) |
| `item` | `dm4:quad` | Control item plus snapped node |
| `fn` | `Argus_HazardSteer` | Source, `calls`, `called_by` |
| `file` | `argus.qc:120-180` | A source slice |
| `search` | `CONTENT_LAVA` | Grep Argus QC (including items/combat/weapons) |
| `const` | `AR_JUMPVEL` | Matching `AR_*` constants |
| `live` | | Last ARGLOG sample per bot (running or last match) |
| `bot` | `Reap` or `latest:Reap` | Deep tape: events, deaths, nearest node/item, mode share |
| `timeline` | `Reap` or `ab_dm4_parity:Omi` | ARGEVT stream |
| `plan` | `latest` or `ab_dm4_goap4` | GOAP `ARGEVT plan <class> via <class>` |
| `around` | `dm4:200,-900,24` | Nearest node and control at a point |
| `status` | | Dedicated child: running, pid, elapsed. `since_line` for an incremental tail |
| `run` | `latest` or `ab_dm4_parity` | Lite brief of a harvested log |
| `demo` | `shane_dm4_2026-08-27_v373` | Parse a `.dem` from `runs/demos` or the game dir: duration, named roster, full-rate tracks, projectiles, kill feed |
| `last` | | Session memory: last map, function, run, experiment |
| `knobs` | | Live cvars vs compile-time constants |

Clients that speak MCP resources can open the same data without a
tool call:

| URI | Same as |
|-----|---------|
| `argus://project` | `see what=project` |
| `argus://lab` | `see what=lab` |
| `argus://knobs` | `see what=knobs` |
| `argus://last` | `see what=last` |
| `argus://quality` | `quality_bars` |
| `argus://help` | `see what=help` |
| `argus://map/{name}` | `see what=map name={name}` |
| `argus://fn/{name}` | `see what=fn name={name}` |
| `argus://run/{name}` | `see what=run name={name}` |
| `argus://const/{name}` | `see what=const name={name}` |
| `argus://path/{spec}` | `see what=path name={spec}` |
| `argus://search/{needle}` | `see what=search name={needle}` |

`see what=last` is in-process only. It resets when the MCP process
restarts.

## Deeper inspect

These stay on `see`. They do not add tools.

**Nav path.** `name` is `map:from-to` or `map:from->to`. Each end is a
node id or a control-item token. Link kinds the inspect BFS walks:
`walk`, `drop` (one-way), `jump`, `tele`, `rocket`, `lift`, `swim`.
Item tokens:

| Token | Classname |
|-------|-----------|
| `quad` | `item_artifact_super_damage` |
| `lg` / `lightning` | `weapon_lightning` |
| `rl` / `rocket` | `weapon_rocketlauncher` |
| `gl` / `grenade` | `weapon_grenadelauncher` |
| `ssg` | `weapon_supershotgun` |
| `sng` | `weapon_supernailgun` |
| `ng` | `weapon_nailgun` |
| `pent` | `item_artifact_invulnerability` |
| `ring` | `item_artifact_invisibility` |
| `mega` / `mh` | `item_health` with spawnflags 2 (id MegaHealth) |
| `ya` / `yellow` | `item_armor2` |
| `ra` / `red` | `item_armorInv` |

A classname substring also matches. Off-graph items (`reach` is
`off_graph` with no `nearest_node`) cannot be a path end.
`rocket_jump` items still resolve if they snapped to a pad node.

**QC.** `see what=fn` indexes `argus.qc`, `argus_nav.qc`,
`argus_nav_dispatch.qc`, and the masquerade-touched base files
(`defs.qc`, `items.qc`, `combat.qc`, `weapons.qc`, `world.qc`,
`client.qc`). Extra names kept: `weapon_touch`, `T_Damage`,
`W_FireLightning`, `W_Attack`, `PlayerDie`, `CheckPowerups`,
`WaterMove`, `PlayerPostThink`. `search` greps those files (needle
at least two characters, 24 hits). `file` is `name.qc` (first 80
lines) or `name.qc:120-180`.

**Tape.** `see what=bot name=Reap` uses the live or last match log.
`name=latest:Reap` or `name=ab_dm4_parity:Omi` reads a harvested
log. The deep bot view adds last events, deaths, nearest node/item,
height band, and mode share. `timeline` is the ARGEVT stream (40
events). `around` is `map:x,y,z` (commas or spaces).

## Map ingest (cartographer)

`cartograph` is the BSP ingest. Pass a path, a short name (`dm4`), or
`maps/dm4.bsp`.

Order, first hit wins:

1. The path as given, if that file exists.
2. `$ARGUS_ROOT/<path>`.
3. `$ARGUS_MAPS/<name>` or `$ARGUS_MAPS/<name>.bsp`.
4. Extract `maps/<name>.bsp` from `id1/pak0.pak` then `pak1.pak` under
   `ARGUS_BASEDIR` (also `engine/id1` and `$ARGUS_ROOT/id1`) and write
   it into `maps_local/`.

Default output is `detail=brief` (what an LLM should read). It is
not a raw entity dump:

- **control** items ranked (LG, RL, quad, pent, mega, red armour)
- each snapped to a nav node (nearest hull-1-clear eye line among
  the eight closest, else Euclidean): `reach` is `walk`, `jump`
  (normal 45u), `rocket_jump` (beyond a jump), `elevator` (near a
  plat pad), `blocked_by_door` (segment hits a door AABB), or
  `off_graph`; `island` is the weak-component id
- **graph_cuts**: weak/strong component counts, top islands with
  which control items sit on each
- **door_cuts**: walk/drop links that pierce a door AABB, plus the
  button and actuator that open it
- **corridor_misses**: 16u standable cells with no waypoint in 48u
  (the 32u sampler never sat there)
- **edict estimate**: waypoint count plus entity lump, against
  vanilla `max_edicts 600`
- **height bands** from the waypoint graph (on dm4: walkway / mid /
  pit / deep)
- **recipe**: the next `experiment` / `match_run` line
- dispatcher coverage and implications

`reach=rocket_jump` means the nearest walk node sits too far below
the item for a normal jump. On dm4 the runtime pad is node 142 at
about `209 -183 -296` onto node 56 (the quad ledge). That is a
typed `Argus_NavLinkRocket`, not a parked idea. The inspect BFS
walks rocket, lift and swim edges as well as walk/drop/jump/tele,
so `see what=path name=dm4:quad->lg` can use the pad hop.

`detail=full` adds every entity, every teleporter, and button-door
causality (including one relay hop and `func_door_secret`). Atlases
and nav graphs cache until the BSP or nav JSON mtime changes.

`lab_status` lists maps with bsp / nav / dispatcher flags and a
recipe string. It does not ingest every BSP (that was 0.11). Use
`see what=map` or `cartograph` for a real brief. `cartograph_all`
still atlases every on-disk BSP.

`list_maps` lists `*.bsp` already in `ARGUS_MAPS` plus map names that
still live only inside the PAKs.

`generate_nav=true` on `cartograph` also runs `argus_navgen.py`
(`--no-dispatcher`, and `--register` by default so `progs.src` and
`argus_nav_dispatch.qc` are wired). Pass `register=false` to skip.

A match brief attaches `goal_reach`: each goaled classname gets the
cartographer's `reach`.

## Demo ingest

The 1 Hz ARGLOG tape is the ruler and the gates; a `.dem` is the
microscope. A listen session records one with the map-taking form of
`record` in the launch command (`+record session dm4` - the bare
`+record name` form before a map connects records nothing), then
`python tools/harvest_session.py --tag vNNN` stamps the tape and
demo into `runs/` under one paired stem, map sniffed from the last
confirmed SpawnServer.

`see what=demo name=<stem>` parses it: protocol-15 block stream,
fast-update deltas against baselines, obituary fragments coalesced
into whole lines. Identity is structural: a real client is entity
1..maxclients (scoreboard row = entity - 1); a bot's skin byte is
its roster slot + 1 and its scoreboard row counts down from the
top, so every player-model track comes back named. Body-queue
corpses are tagged `body`; missile/grenade tracks are tagged
`projectile` (note: entity SLOTS recycle, so a projectile track is
a slot history - split on time gaps for true per-rocket arcs).

Caveats: demos are PVS-culled to the recording client's view (an
out-of-sight bot drops to a trickle - the first walkway-corner
forensics found its freeze happened entirely off-camera), and the
engine truncates `qconsole.log` in its working directory on launch -
HARVEST BEFORE STARTING ANYTHING NEW.

`argus-mcp demo <stem>[:export]` is the CLI face of the same reader,
for sessions without an MCP client.

The brief carries analysis, not just inventory: per-player `aim`
statistics (mean and p95 angular rate, flick count - the recording
client measured from full-precision POV angles, bots from their
entity angles), and a `highlights` reel (first blood, multikills,
sprees, quad pickups and carrier deaths, environment deaths) each
with a timestamp to jump to under `playdemo`. `see what=demo
name=<stem>:export` also writes `<stem>.tracks.json` (full t / pos /
pitch / yaw vectors plus the POV series) for offline studies - the
sprint run-up forensics input format.

## Idle hands (soak and cycle)

Two CLI modes for the unattended lab. Neither is scheduled by
anything; they exist for the night the operator feels like it.

`argus-mcp soak` loops matches and gates every tape against the
shipped baseline, writing `runs/soak_<stamp>.md` as it goes. Hard
caps, not suggestions: `--hours` (default 4, max 12), `--matches`
(default 60), `--max-mb` bytes written (default 200; a real night of
tapes is under 10 MB), and a stop file - create `runs/soak.stop` and
the loop ends after the current match. `--learn` folds hotspots into
`costs.json` at the end (write-only; nothing regens automatically).

`argus-mcp cycle <map>` closes the offline learning loop ONCE, with
a guard: learn hotspots -> regen the nav (reach gate printed) ->
compile and install the candidate -> 185 s probe -> judge. An
improved verdict keeps the learned costs and graph in src/ (record
the new install MD5 in the handoff); anything else restores nav,
costs and every installed progs.dat byte for byte from the snapshot
(never by recompiling - fteqcc is not byte-stable). Its first dm4
trial self-rejected on the lava gate, exactly as the 2026-08-20
forensics predicted.

## The decision tape (ARGDBG)

Console `scratch1 1` (live via `tune command="scratch1 1"`; the
scratch cvars are vanilla's QC float pipe) makes every goal pick
print `ARGDBG <name> pick <class> u <utility> | w <> a <> h <> r <>
p <> o <> ws <atoms> streak <n>` - the full per-class utility board
behind the choice. `scratch1 0` silences it. Plain ARGDBG lines,
outside the closed ARGEVT vocabulary; grep them, they never touch
briefs or gates.

## Lite vs full

Default returns from `experiment`, `compare_runs`, `brief_run`,
`see what=run`, and `probe` are **lite**: headline, totals, flags,
gates (when comparing), hotspots (first five), bot frag lines, and
`next_steps`. That is what you act on.

Pass `detail=full` for the whole `MatchBrief` pair (events, weapons,
every hotspot). Prompts (`orient`, `review_run`, `review_ab`,
`review_map`) also embed the lite JSON.

`compare_runs` is unscaled: it expects two tapes of similar length.
`experiment` duration-scales the baseline counts to the candidate
duration so a 30 s probe is not judged as an engagement collapse
against the 185 s shipped tape (`ab_dm4_water`, falling back to
`ab_dm4_parity`). The lite compare
carries `scaled` and `scale_note` when that happens.

## Tools

### Maps

| Tool | Needs | Does |
|------|-------|------|
| `lab_status` | `ARGUS_ROOT` | Dashboard: config, map flags, recent runs, recommend. No per-map ingest. |
| `cartograph` | `ARGUS_ROOT` | Ingest a BSP. Default **brief**. `detail=full` for every entity. `generate_nav=true` also compiles nav and registers it. |
| `cartograph_all` | `ARGUS_ROOT` | Atlas every on-disk BSP in `ARGUS_MAPS` |
| `list_maps` | `ARGUS_ROOT` | Maps on disk and in id1 PAKs |
| `nav_generate` | full lab | Compile a per-map waypoint QC + PNG (PNG also returned as an image block) |
| `nav_sync_dispatch` | `ARGUS_ROOT` | Register new `argus_nav_<map>.qc` in the dispatcher and `progs.src` |

### Lab loop

| Tool | Needs | Does |
|------|-------|------|
| `config_check` | nothing | Resolved paths, exists or not |
| `compile_qc` | full lab | fteqcc from `src/`. Success is the `Compile finished` / `id format` line, not the exit code. Copies `progs.dat` to `game/argus` and the basedir game dir. Splits known LibreQuake warning noise from new errors. |
| `match_run` | full lab | Timed dedicated match, harvest `runs/<name>.log`, return a full brief |
| `match_start` / `match_command` / `match_status` / `match_stop` | full lab | Same single child, interactive. Status includes a live headline once ARGLOG appears. `match_status since_line=N` returns only new lines plus `next_line`. |
| `analyze_match` | full lab | Existing plotter plus brief and, if two logs, a compare |
| `list_runs` | `ARGUS_ROOT` | Top-level `runs/*.log`, newest first, known baselines annotated |

### Intelligence

| Tool | Needs | Does |
|------|-------|------|
| `see` | `ARGUS_ROOT` | One inspect. See the table above. |
| `experiment` | full lab | Compile + short match + **duration-scaled lite** A/B. `detail=full` dumps both tapes. Duration 10-185 s, default 30. |
| `matrix_experiment` | full lab | One compile, then a short probe on each of dm2/dm3/dm4/dm6/lqdm2 (default 20 s). |
| `brief_run` | `ARGUS_ROOT` | Lite brief of one log. `detail=full` for the whole tape. |
| `compare_runs` | `ARGUS_ROOT` | Unscaled lite A/B. `detail=full` for both briefs. Default `log_a` is `baseline`. |
| `suggest_next` | `ARGUS_ROOT` | Just the QC places to open |
| `qc_find` | `ARGUS_ROOT` | Argus functions by name, role (`hazard`, `combat`, `nav`), or comment |
| `qc_index` | `ARGUS_ROOT` | Full function + `AR_*` constant index |
| `qc_read` | `ARGUS_ROOT` | Full source of one Argus function, with line numbers |
| `learn_hotspots` | `ARGUS_ROOT` | Fold stall/lava/hazard cells across logs. Writes `src/argus_nav_<map>.costs.json` for the next navgen; does not write QC. |
| `knobs` | nothing | Live cvars vs compile-time constants |
| `tune` | live match | Whitelisted console: skill, fraglimit, map. Unix stdin; Windows AttachConsole inject. |
| `live_snapshot` | live or last match | Last ARGLOG row per bot. `since_line` for incremental. |
| `match_status` | live match | Running, pid, elapsed, log lines. `since_line` returns only new lines plus `next_line`. |
| `probe` | full lab | Prefer `experiment`. Compile + short match + lite brief, no A/B. Duration 10-120 s. |
| `quality_bars` | nothing | The bars used by compare |

Log arguments accept a path, a run name (`ab_dm4_parity`), `baseline`
/ `shipped` (dm4 → `ab_dm4_water`), or `latest` (newest
`runs/*.log`).

## Extra spec tools (do not replace the native set)

`docs/mcp_quake_dev_spec.md` asked for five more tools. They sit
**beside** `compile_qc`, `cartograph`, `match_run`, `tune`, and
`analyze_match`. Native tools keep their jobs. Descriptions start
with "Prefer …" so a client ranks the native call first.

| Extra tool | Extra job | Prefer instead |
|------------|-----------|----------------|
| `quake_compile_qc` | Compile an optional `source_directory`. Installs only if that dir is `ARGUS_SRC`. Records requested `-O*` and still emits id-format. | `compile_qc` |
| `bsp_inspect_entities` | Raw lump-0 dump + causality, `filter_classname`. | `see what=map` / `cartograph` |
| `bot_simulate_match` | Batch report: kills, deaths, pickups, nav_errors. Default 300 s. `time_dilation` recorded, not applied. | `experiment` |
| `rcon_exec` | Whitelisted stdin line plus the following log tail. | `tune` |
| `bot_capture_pov_frame` | Parked POV hook; substitute PNG paths. | `analyze_match` |

## Can an LLM see into Quake and change things live?

Yes, with a hard line.

**Live (no recompile):**

- `tune` / `see what=knobs`: `skill 0-3` (takes effect at the **next
  bot respawn**, `Argus_SetSkill`), `fraglimit`, `timelimit`,
  `map <name>`, `developer`, `status`. Unix writes the child stdin.
  Windows injects via `AttachConsole` + `WriteConsoleInputW`.
- `live_snapshot` / `see what=live`: last ARGLOG sample per bot from
  the running child (or the last harvested match).
- `see what=bot name=Reap`: deep tape (events, deaths, nearest
  node/item). `name=latest:Reap` reads a harvested log.
- `match_command` is still there for a single console line; `tune` is
  the safe whitelist.

Vanilla NetQuake has no QuakeWorld RCON. There is no VM memory
inspector. The engine stays a harness.

**Windows dedicated spawn:** QuakeSpasm `Host_Error`s if stdin is a
pipe (`GetNumberOfConsoleInputEvents`). 0.12 still inherited the MCP
stdio pipe under `CREATE_NEW_CONSOLE`, so matches could die at
"Server spawned." 0.13 uses `CreateProcess` with
`bInheritHandles=FALSE`, a new hidden console, and no
`STARTF_USESTDHANDLES`. Harvest is still `-condebug` `qconsole.log`.
`tune` / `match_command` inject via `AttachConsole` +
`WriteConsoleInputW` (stdio pipes are saved and restored so MCP JSON-RPC
is not stolen). If inject fails, pass `skill` on `experiment` /
`match_start`. `match_stop` sends `quit` the same way, then kills.

A match that produces no `ARGLOG` / `ARGEVT` is an error with a
diagnosis and log tail, not `ok: true` on a spawn-crash log. The
runner fails fast if the child dies before the first tape line.
`start` reaps a dead child so a zombie slot does not block the next
run. `experiment` stops a leftover live match first.

**Not live (edit QC, then test):**

- `AR_JUMPVEL`, `AR_AIMRATE`, personality offsets, hazard math, nav.
  Vanilla QuakeC cannot load files, so those only change when
  `progs.dat` is rebuilt.
- Workflow: `see what=search name=AR_AIMRATE` or
  `see what=fn name=Argus_SetSkill` → edit →
  `experiment map=dm4 duration_sec=30 skill=2`.

## Quality bars

Encoded from the project charter, not invented per call:

- Lava/slime deaths are hull-0 contents at the death origin (and 24u
  below), same rule as `analyze_match.py`. `z < -300` is the no-BSP
  fallback only. dm4 band is about 2-7 per 185 s. dm2 lava sits at
  z about -35 and now counts. Per-map stall/engage bars: dm4 25%/70%,
  dm2 30%/65%, dm3 35%/50%.
- Stalls stay within about 25% of the baseline.
- Engagements must not fall below 70% of the baseline.
- Every bot should finish with a positive frag count.
- K/D spread across equal bots should stay tight.
- Coverage and average speed should not crater.
- Routed mode-2 links are walk-verified; hazard deflections belong
  in mode 0/1.
- Freezes are a HARD gate: the parser runs the statue scan natively
  (6 s+ under 20 u/s in a 32u circle) with an under-fire measure
  (hp lost while frozen). Any under-fire freeze, a 10 s+ statue the
  baseline lacks, or a clearly growing count makes the verdict
  regressed on its own.
- Hop success is measured, not assumed: `mover_waits` (lift + train
  events) versus `boards` (`ARGEVT board`, fired when the bot
  actually gets aboard). A wait storm with zero boards is flagged
  as broken, not slow.
- A/B baselines are config-driven: `runs/baselines.json` maps a map
  to its baseline run; era defaults are the fallback and a missing
  named run errors loudly. Refresh the file after each clean ship.

`next_steps` maps failures to code:

| Signal | Look at |
|--------|---------|
| Lava spike | `src/argus.qc` `Argus_MoveHazard` / `Argus_HazardSteer` |
| Known walkway cells | `Argus_HazardSteer` hold at `200 -900 24` / `700 -800 -200` |
| Engagements gone | `button0` / perception / `W_FireLightning` |
| No weapon events | `src/items.qc` `weapon_touch` |
| Elevated quad + routefail | `Argus_BotCanRJ` / `ARGEVT rjump` / dm4 pad 142→56 |
| Quad goaled, zero `rjump` | bot never paid the toll (no RL, dry, hp < 70, or quad) |
| Almost no routed time | `argus_nav_dispatch.qc` and `argus_nav_<map>.qc` |
| Freezes / under-fire statue | pad waits in `argus.qc` (`ar_liftwait` holds), the wait give-up clocks |
| Waits with zero boards | pad geometry vs the board gate (car edge distance), navgen pad placement |

## Prompts

`orient`, `review_run`, `review_ab`, `review_map` embed the computed
lite JSON so the model does not re-parse ARGLOG or the BSP by hand.

## Client wiring

Grok (`.grok/config.toml`):

```toml
[mcp_servers.argus]
command = "C:/path/to/argus-mcp.exe"
startup_timeout_sec = 15
tool_timeout_sec = 700
tool_timeouts = { match_run = 700, compile_qc = 120, nav_generate = 180, cartograph = 60, experiment = 400, probe = 180, bot_simulate_match = 400 }
```

Set the five `ARGUS_*` keys in the env block or in
`tools/argus_mcp.toml`. `match_run` at 600 s plus harvest needs a
client tool timeout above that (700 s). `experiment` at 185 s plus
compile wants about 400 s. Restart the MCP client after rebuilding
the binary.

Claude-compatible (`.mcp.json`) uses the same command and an `env`
block. See `.mcp.json.example`.

## Recipes

Open a session:

```
see  what=project
```

New map (agent):

```
list_maps
see  what=map  name=dm4
# if nav is missing:
cartograph  bsp=dm4  generate_nav=true
see  what=item  name=dm4:quad
see  what=path  name=dm4:quad->lg
see  what=around  name=dm4:200,-900,24
see  what=node  name=dm4:142
```

New map (human): `argus-mcp gui`, drop the `.bsp`, Generate nav,
check the PNG, Compile and install.

A/B after a QC change:

```
experiment  map=dm4  duration_sec=30  skill=2
see  what=last
# full-length unscaled A/B:
compile_qc
match_run   map=dm4  duration_sec=185
compare_runs  log_b=latest
suggest_next  log_b=latest
```

Read an old tape, or learn across them:

```
see  what=run  name=ab_dm4_parity
compare_runs  log_a=ab_dm4_A  log_b=ab_dm4_parity
learn_hotspots  map=dm4  max_logs=8
see  what=search  name=CONTENT_LAVA
see  what=fn  name=Argus_MoveHazard
see  what=file  name=argus.qc:1-40
see  what=bot  name=latest:Reap
see  what=timeline  name=ab_dm4_parity:Omi
see  what=plan  name=latest
```

Live (Unix stdin; Windows console inject):

```
match_start  map=dm4  duration_sec=120  skill=2
see  what=live
tune  command=skill 3
match_stop
```

Several maps after one compile:

```
matrix_experiment  duration_sec=20
```

## Tests

`cargo test --manifest-path tools/argus_mcp/Cargo.toml`

Parser, config, cartographer, nav-graph BFS, QC search/calls, session,
resources, project view, and A/B tests do not need Quake. A mini BSP29
is synthesised in-process.
If `maps_local/dm4.bsp` and `runs/ab_dm4_parity.log` are present they
are ingested as extra checks. Compile integration runs only when the
full lab env is set. A live `match_run` is a manual lab check.

## Shutdown

When the MCP client drops stdio the server sends `quit` to any live
dedicated child (Unix stdin), waits two seconds, then kills it. At
most one match process. No RCON, no protocol overrides, no free-form
shell.

## Versions

| Ver | What landed |
|-----|-------------|
| 0.10 | Extra spec tools beside the native set. Cartographer briefs. `see` / `probe` / `tune`. |
| 0.11 | `see what=project`, `experiment`, session last-seen, MCP resources, `orient` prompt. |
| 0.12 | Lite defaults. `lab_status` no longer cartographs every map. Atlas cache. Windows `CREATE_NEW_CONSOLE`. Honest no-ARGLOG error. Extra tools defer to native names. |
| 0.13 | Windows `CreateProcess` does not inherit the MCP pipe (hidden console). Fail-fast if the child dies before ARGLOG. Diagnose crash logs. Reap dead children. `see` aliases (`qc`→`fn`, empty→`project`). Structured `{error,hint}` tool errors. Compile 90 s timeout. |
| 0.14 | Deeper `see`: nav path/item/around, QC calls/callers/search/file, bot tape + timeline. Resources `argus://path/{spec}` and `argus://search/{needle}`. |
| 0.15 | MegaHealth spawnflags. Safer QC slice. Death event dedup. Windows console inject for tune. PNG image blocks. `nav_sync_dispatch`, `matrix_experiment`, `see what=plan`. Config discovery from `game/argus/autoexec.cfg`. Edict estimate on cartograph. Alongside this release the QC tree shipped prize-only rocket-jump pads, `Argus_HazardSteer`, and GL/RL loft (see CLAUDE.md). |
| 0.16 | Cursor `since_line` on `match_status` / `live_snapshot`. mtime cache invalidation. Hull-1 snap + door/plat reach labels. Causal relay hops and secret doors. Inspect BFS walks rocket/lift/swim. Cartograph `generate_nav` registers by default. Experiment baseline is `ab_dm4_water`. |
| 0.17 | Hull-0 lava in Rust briefs (same as analyze_match.py). Per-map A/B bars. dm2 baseline `ab_dm2_lava`. Cartograph islands, door cuts, corridor misses. `learn_hotspots` writes `argus_nav_<map>.costs.json`; navgen inflates those cells. |
| 0.18 | `argus-mcp gui`: localhost deploy wizard (attach BSP, nav PNG, compile, install, dated backups + restore). |
| 0.19 | Spaced netnames parse whole (closed verb vocabulary). Freeze detection as a HARD gate with the under-fire measure. `mover_waits` vs `boards` hop-success accounting. Config-driven baselines (`runs/baselines.json`). Kind-aware `learn_hotspots` (lava cells small and heavy, deflection cells reported but never written). Cartograph `PlatBrief` boardability probes. New verbs: `retreat`, `grab`, `board`; human clients emit ARGLOG tracks. The escaped v363 west-pad tape is a permanent regression test. |
| 0.20 | The tape and the map argue with each other. Reach classifier fixed (floor-seated item origins traced 2u inside the hull-1 floor: eleven of twelve dm4 control items read off_graph). Human tracks split out of bot bands (`totals.human`); a refused map spawn flags the whole tape (every historical mx_lqdm2 probe had silently run on the start map). Hotspots carry `cause` (door / plat_column / lava_edge) and `reach_pct` (routefail clusters in directed sinks are named). Briefs cross-examine atlas labels against routing evidence, report `nav_coverage` (visited nodes, dormant typed-link families) and `item_control` (per-prize clock tightness). `see what=demo`: protocol-15 .dem parser with named full-rate tracks. Companions: `tools/argus_reach.py`, `tools/harvest_session.py`. Then the analysis layer: demo view angles + POV aim, per-player aim statistics, the highlight reel, `:export` track dumps; `argus-mcp soak` (capped unattended match loop) and `argus-mcp cycle` (guarded learn->regen->probe->adopt/restore); `scratch1-4` on the tune whitelist for the ARGDBG decision tape; CI runs the Rust suite plus a headless LibreQuake stability smoke with the reach gate. Stack sweep: Windows live tune FIXED (after AttachConsole the console input buffer must be opened as CONIN$ - GetStdHandle returns the MCP's own pipe; the inject had been broken since 0.15 and a live-engine integration test now guards it), `argus-mcp demo` CLI verb, and the plain `ARGUS shove` / `routecache adopt` console lines count as pseudo-events (`shove`, `routecache_adopt`) in briefs. |
| 0.21 | The operational gaps. STALENESS SELF-AWARENESS: at startup the server detects a newer staged build, auto-swaps it into place for the next restart (Windows allows renaming a running exe), and stamps `lab_stale` on every JSON response for the rest of the session - a stale server can never again hand out an unmarked opinion. HARVEST GUARD: every match starter (MCP tools, soak, cycle) refuses to launch over an un-harvested play session (the harvester now MOVES its inputs, so leftovers are the signal). PAIRED DEMO JOIN: brief_run folds the same-stem .dem into the brief (aim stats, highlight reel, tracks) - the whole "played, review" ritual is one call. `ship` (compile + install everywhere + MD5s) and `baseline_set` (rewrite runs/baselines.json safely) close the loop's last manual steps. `soak --parallel 2` runs two engines on separate ports, halving ladder wall clock. Last-seen session memory persists to runs/.lab_session.json across restarts; `see what=project` stops listing fifty pak-only maps; compare flags any human tape as review-only material. |
