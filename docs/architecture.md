# Bot architecture and source map

[README](../README.md) | [Controls](controls.md) |
[Lab workflow](lab-workflow.md) | [Change history](../CHANGELOG.md)

Argus is a vanilla QuakeC bot inspired by the Reaper and Omicron lineage.
The engine runs the game; offline tools build navigation and analyse saved
evidence. Playing the shipped mod needs neither the lab nor a network service.

## Runtime and lab

```mermaid
flowchart TD
    Frame[world.qc StartFrame] --> Driver[Argus_FrameAll]
    Driver --> Nav[Frame-sliced navigation search]
    Driver --> Think[Per-bot decisions]
    Driver --> Physics[Per-bot movement]
    Think --> Sense[Perception and remembered observations]
    Think --> Goal[Utility goals and prerequisite planning]
    Think --> Fight[Weapon selection and imperfect aim]
    Physics --> Move[Friction, acceleration and hazard checks]
    BSP[Local BSP] --> Generate[Offline navigation generation]
    Generate --> Graph[Generated QC and JSON]
    Graph --> Build[Lab compile and install]
    Build --> Game[Quake engine]
    Game --> Tape[Console tape and optional demo]
    Tape --> Brief[Native briefs and comparisons]
    Game --> Probe[Protocol-15 puppet link checks]
    Probe --> Sidecars[Probe convictions and proven links]
    Sidecars --> Generate
```

## Behaviour by component

| Component | Responsibilities |
|---|---|
| Movement | Ground/air acceleration, friction, wall sliding, corner lookahead and separate move/aim headings |
| Hazards | Braking-aware floor probes, dry landings, liquid checks and knockback-aware ledge avoidance |
| Navigation | Sliced search, cached routes, typed walks/drops/jumps, doors, lifts, trains, teleports and water transitions |
| Combat | Weapon/range choice, projectile lead, splash clearance, movement under threat and crossfire responses |
| Perception | Soft field of view, weapon/item hearing, remembered sightings and limited invisible-player glimpses |
| Aim and skill | Damped spring tracking, blended aim offsets, reaction delay and continuous per-bot skill |
| Goals | Utility scoring, personality appetites, pickup claims, item timing and prerequisite weapon errands |
| Presentation | Fake scoreboard rows, stock player models/deaths/backpacks, chat and spectator camera |

The tactical attack-cover-return state machine owns movement temporarily on
two authored routes. It preserves item-route state but suppresses incompatible
launches, validates incoming momentum and brakes during handoff. See its
[implementation and acceptance limits](attack-cover-return.md).

### Navigation is generated, not loaded at runtime

QuakeC has no file I/O. A BSP is sampled offline into generated
`argus_nav_<map>.qc`, compiled into `progs.dat`, and registered in both the
dispatcher and build manifest. Its `.qc.json` twin is for tooling.

Generation accounts for player-hull support, movement arcs, doors and mover
geometry, spawn reach and the edict budget. Real-engine probes record refused
links by endpoint; proven candidates and learned hotspot costs feed the next
generation. A generated graph and a well-connected graph are different claims.
New maps need current reach and mill evidence before registration.

Do not hand-edit generated navigation. Use the
[lab generation and validation workflow](lab-workflow.md#add-or-regenerate-navigation).

### Aim and difficulty

The four integer skill rows anchor a continuous 0-3 scale. Reaction time,
error, tracking and spring gains interpolate, while tactical abilities unlock
in an ordered ladder. Console baseline changes apply on respawn; roster
impulses can retune immediately. Per-slot offsets and optional human-only
adaptation are described in the [control reference](controls.md).

Physics rates use `frametime`, and the aim spring is sub-stepped for stable
integration. The lab requests the played rate, but records actual cadence.
Compare matched tick classes and retain the source identity for every arm.

## Source and evidence locations

| Path | Purpose |
|---|---|
| `game/argus/` | Playable `progs.dat` and protocol/edict configuration |
| `src/argus.qc` | Decisions, physics, combat, perception, skills and roster |
| `src/argus_tactics.qc` | Bounded tactical state machine |
| `src/argus_tactic_fixture.qc` | Explicit developer-only engine fixture |
| `src/argus_nav.qc` | Runtime sliced search and route handling |
| `src/argus_nav_dispatch.qc` | Hand-maintained map dispatcher |
| `src/argus_nav_<map>.qc` | Generated graph compiled into the game |
| `src/argus_nav_<map>.qc.json` | Machine-readable graph twin |
| `src/argus_nav_<map>.probe.json` / `.proven.json` | Engine refusals / proven candidates |
| `src/argus_cam.qc` | Spectator camera and HUD |
| `src/defs.qc` / `src/progs.src` | Definitions, client-message shims and compile order |
| `tools/argus_mcp/` | Lab server, wizard, CLI, puppet and native reports |
| `tools/argus_navgen.py` | BSP navigation generation |
| `tools/harvest_session.py` | Preserve console logs and demos from human play |
| `runs/` | Saved tapes, outcomes and build provenance |

Engine installs, licensed maps/models, local configuration, demos and dated
backups are machine-local where specified by `.gitignore`.

## Engine constraints that affect changes

- **Vanilla only:** NetQuake protocol 15, maximum 600 edicts, no engine
  extensions and no QuakeC file I/O. The engine is the measurement harness.
- **Bots are spawned entities:** They use `classname = "player"` for stock
  pickups, damage and triggers, but are not network clients. Client-only
  message shims must reject them. Extra skins provide colours in GL renderers.
- **Trace semantics:** A trace beginning in solid can report fraction 1 with
  `trace_allsolid`; support checks must distinguish that from clear space.
- **View pitch:** `vectoangles()` and view angles use opposite pitch signs.
  Camera and firing code must convert deliberately.
- **Console versus chat:** Diagnostics use `dprint` with `developer 1`.
  Dedicated logs do not prove client-visible `bprint` chat; observe through
  the puppet's `last_prints` to verify it.
- **Evidence:** A goal selection is not a pickup, a shot is not a hit and a
  passing short tape is not proof of improved player experience. Use the
  [recording and report contracts](telemetry.md).
