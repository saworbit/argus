# Agent protocol

Argus has a lab MCP server. Use it. Do not invent a shell pipeline
from a local handoff.

This file contains tracked, portable rules. Correct durable rules here so
every checkout receives the fix. Keep machine paths, credentials, session
notes and current handoffs in ignored local files. `CLAUDE.md`, when
present, is an optional working handoff; it is not required by a fresh clone.

## First call, every session

```
see what=project
```

Same data: open `argus://project`. Then `see what=help` if you need
the vocabulary. Do not grep the tree for "how do I compile".

## The loop

| You want | Call |
|----------|------|
| Map brief (items, reach, recipe) | `see what=map name=dm4` |
| Route between items or nodes | `see what=path name=dm4:quad->lg` |
| One control item | `see what=item name=dm4:mega` |
| QC function + callers | `see what=fn name=Argus_HazardSteer` |
| Grep Argus QC | `see what=search name=CONTENT_LAVA` |
| After a QC edit | `experiment map=dm4 duration_sec=30 skill=2` |
| Several maps, one compile | `matrix_experiment` |
| Full-length A/B | `compare_runs log_b=latest` |
| Live skill / fraglimit | `tune command="skill 3"` (Windows console injection is supported) |
| Live log without spam | `see what=status` then `since_line=<next_line>` |
| Harvest a human session | `python tools/harvest_session.py --tag vNNN` (FIRST, before any new engine launch - launches truncate qconsole.log) |
| Read the session's demo | `see what=demo name=<stem>` (full-rate named tracks; PVS-culled to the recorder's view) |
| Directed reach of shipped graphs | `python tools/argus_reach.py [map]` |
| How human does a tape's movement look | `python tools/argus_humanness.py runs/<tape>.log --profile` (map-matched distance plus SIGNED per-feature gaps; the bare distance says a feature is wrong, never which way) |
| Was that stationary window a chosen pause | `python tools/argus_gait.py runs/<tape>.log` (attributes freezes to this bot's own `hesitate` marker; exits 1 on an attributable failure, and a window with no marker is the pre-existing wedge class) |
| What is under a vetoed void, how tight is a seat | `python tools/argus_voidprobe.py dm4 dm2 [--clearance]` (offline hull-0 read of the SHIPPED graph; needs maps_local/<map>.bsp - two gait changes were built on guesses this answers) |
| Why did it pick that goal | `tune command="scratch1 1"` then grep ARGDBG (scratch1 0 to silence) |
| Walk a link in the REAL engine | `argus-mcp probelinks <map> [limit<=80] [skip]` (refusals persist by endpoint in src/argus_nav_<map>.probe.json; teleport_failures need AABB triage on tele maps) |
| Puppet a live match | `argus-mcp client observe|walk|walkrel|impulse <n>` (impulse 101 = 4th bot, 100 = menu, headless 4-player) |
| Full-rotation sweep | chunk probelinks in a detached driver; stop file runs/soak.stop, position in runs/probe_soak_state.json; monitor the STATE FILE, never tail -f a PS-written log |
| Unattended match shift (only when Shane asks) | `argus-mcp soak --maps dm2 --matches N [--parallel 2]` / `argus-mcp cycle <map>` (hard caps; stop via runs/soak.stop) |
| Human attach / deploy | `argus-mcp gui` (you do not drive the browser) |
| Verify spectator-camera code | start a match, then `argus-mcp client impulse 210` - the puppet's ARGLOG stops at the impulse (FrameAll's `cam_active` skip), which proves the camera took the client without a human watching |
| Verify anything `bprint` (chat) | drive the puppet: `argus-mcp client observe <secs>` returns `last_prints`. `bprint` is invisible in a dedicated log, so this is the only headless way to see chat |

Trust `next_steps` on experiment / compare. Do not re-parse ARGLOG.
Lava deaths are hull-0 contents (z < -300 is the no-BSP fallback only).
`learn_hotspots` writes `src/argus_nav_<map>.costs.json`; the next
`nav_generate` inflates those cells. Do not hand-edit generated nav.

Read events for what they ARE. `ARGEVT "<bot> goal <class>"` is
emitted at goal SELECTION, not on pickup - "quad goalled 8 times"
can mean zero touches (on dm4 its quad sits on a rocket-jump ledge:
a 150 s probe recorded three selections and, when instrumented,
*no* artifact pickups at all). The brief's `gl`/goals TOTAL is the
consumed-pickup counter; the per-class map beside it is selections.
To answer "did a bot ever take this", instrument the touch or watch
a real client.

Brief fields to trust before reconstructing by hand: hotspot `cause`
(door / plat_column / lava_edge) and `reach_pct` (a routefail
cluster in a directed sink implicates the tested graph only with
build-attributed coverage), `nav_coverage` (provenance and dormant
typed-link families), `item_control` (per-prize clock
tightness), `totals.human` (human tracks are review data, never in
bot bands or gates), and the WRONG MAP flag (a refused spawn means
the whole tape describes the fallback map - judge nothing).

## Hard rules

- Vanilla QuakeC only. No engine extensions, no file I/O, protocol 15,
  max_edicts 600. The engine is a harness.
- Never hand-edit `src/argus_nav_<map>.qc`. Regen with
  `nav_generate` / `cartograph generate_nav=true` (registers by default).
  Exception class: a SCRIPTED splice of engine-proven links (json and
  QC in lockstep, ladder after) when a fresh regen measurably
  regresses the accumulated graph - the v3.96 islet entry precedent.
  The proper path is still the sidecar files (probe.json convictions,
  proven.json entries) consumed at the next real regen.
- One compiler at a time. Record the tree state on every A/B log.
- The lab runs at the played rate: every normal match passes
  `+sys_ticrate 0.0139`, about 70 frames a second. Express rates per
  second against `frametime`, sub-step stiff calculations, and measure
  cadence rather than assuming it. `sys_ticrate` gates the dedicated
  main loop. The old default recorded about 19 Hz, unlike played
  sessions at about 71 Hz. A guard like `if (frametime < 0.09)` fires
  on every normal lab frame. Deliberate slow studies set
  `sys_ticrate 0.1` as a separate arm. Never compare two tick classes.
- ONE TAPE SETTLES NOTHING on a movement question. A control tape of
  byte-identical shipped code ran dm2 stalls 31 and then 63, with one
  grate-room cell swinging 12 to 35; dm4 lava ranged 4 to 11 across a
  single session. Judge on two maps or against a control, and be
  aware that a change can survive its own single-tape bisect and
  still be convicted by the aggregate (that is exactly how #54 and
  #91 were caught).
- Base files have a scope rule: touch them when
  the BOT path needs it, or when the code contradicts its own intent
  and the fix is safe. Stock id behaviour that merely differs from a
  preference is out of scope - every baseline was measured under it.
- Metric boundaries are real: do not compare goal, engagement, raw
  death-event, distance or speed counts across incompatible counters
  or tape eras. Use the lab's gates and the tracked changelog history
  to establish compatibility. Human tracks are review data, never
  bot bands or gates.
- Use Australian English and sentence case headings. Do not introduce
  em dashes or en dashes in prose, comments, output or commits.

## Human wizard

```
argus-mcp gui
```

Localhost (`127.0.0.1:7420`) for attach / generate / compile /
install / restore. Shows the nav PNG and the cartograph brief.
Compile writes `backups/<stamp>/` first. Agents still use `see`
and `experiment`, not the browser.

## If the MCP server is not connected

Say so in the first reply. Use the tracked
[lab setup and workflow](docs/lab-workflow.md), not a guessed engine
command. A local handoff may add installation details. On Windows, qconsole.log lands
in the process working directory; launch needs `-condebug` and
`+developer 1` or the tape is empty.

## Where the rest lives

- CONTRIBUTING.md: portable engineering constraints and focused checks
- CLAUDE.md: optional ignored local handoff and machine-specific paper trail
- tools/argus_mcp/README.md: operator guide for every tool, with
  the lab-loop and mill flow charts
- README.md: the public face: features, quick start, map table,
  telemetry grammar
- CHANGELOG.md: current changes and links to tracked historical notes
