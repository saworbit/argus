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
| Movement | Ground/air acceleration, friction, wall sliding, corner lookahead, chosen pauses and separate move/aim headings |
| Hazards | Braking-aware floor probes, dry landings, liquid checks and knockback-aware ledge avoidance |
| Navigation | Sliced search, cached routes, typed walks/drops/jumps, doors, lifts, trains, teleports and water transitions |
| Combat | Weapon/range choice, projectile lead, splash clearance, movement under threat and crossfire responses |
| Perception | Soft field of view, weapon/item hearing, cached visual combat inputs and limited invisible-player glimpses |
| Aim and skill | Damped spring tracking, blended aim offsets, reaction delay and continuous per-bot skill |
| Goals | Utility scoring, personality appetites, pickup claims, item timing, prerequisite errands and shared failed-plan evidence |
| Presentation | Fake scoreboard rows, stock player models/deaths/backpacks, chat and spectator camera |

Development navigation preserves fewest-link routing, then minimises geometric
distance among equal-link alternatives. A better parent propagates its distance
to descendants, so shopping and installed routes use the same settled distance
space. See the [cross-map audit and engine contracts](map-intelligence.md).

Development movement reacts to failed walking while combat owns steering.
It tries a short checked exit while retaining aim and fire. Recent hostile
damage corroborates an immobile body's need for the existing last-resort
rescue; lift/train rides and destination checks remain protected. See the
[recovery rules and physical regressions](freeze-recovery.md).

Development combat also reassesses its target using recent hostile damage,
observed powerups and a commitment margin. It can answer a visible third-party
attacker or prefer a vulnerable opponent while preserving reaction delay,
goal ownership and fair observation. See the [decision policy and controls](combat-attention.md).

The tactical attack-cover-return state machine owns movement temporarily on
two authored routes. It preserves item-route state but suppresses incompatible
launches, validates incoming momentum and brakes during handoff. See its
[implementation and acceptance limits](attack-cover-return.md).

The development perception code gives ordinary combat an observation cache
for its target's position, velocity, movement flags and powerup cues. Hidden
prediction lasts at most 0.4 seconds and travels at most 128 units. Damage
alone cannot create a visual observation, and entity lifecycle changes clear
cached identity. Step 1b health/inventory perception is active again in
development: acquisition, retreat and hunch use observed cues and fixed priors
rather than exact opponent health/inventory. Its earlier dm4 stall warning
remains unresolved; controlled boundary checks do not establish gameplay
regression safety. Projectile
recognition remains a separate follow-up on hold. See the
[observation boundary and engine checks](behaviour-diagnostics.md#perception-step-1a).

`Argus_MuzzleClear` gates the ordinary final-aim rocket trigger after movement
has been computed. It traces the actual firing direction for the nearer of
240 units and muzzle-to-aim-point distance. Blocked shots release the trigger
without cancelling movement. Authored tactics retain their full 240-unit
probe and existing settle/abort rule. Ordinary grenade/hitscan fire and the
separate exact-line speculative prefire remain unchanged. This is outgoing
shot clearance, not incoming-projectile perception. Its controlled checks
cover the shared gate and stock firing, rather than the entire combat AI.

The development goal executor tracks goal identity, best objective distance
and per-goal waypoint visits, using one epoch mark per bot slot on existing
nodes. Useful progress clears failed recovery history and renews the goal
deadline; repeated waypoint cycles, movement or route-cache adoption alone
do not. Detours retain a monotonic best-distance reference. Failed co-op fetches
rest per bot/subject before retrying. Existing bailout
and utility selection choose another goal after repeated failed attempts.
The stall window uses a shared pause predicate for plan evidence and detection.
Explicit waits and moving typed actions keep ownership. Moving pending-item
orbits clear isolated failures; stationary typed flags and camps can reach
the bailout. The bailout cancels its old search, action state and item claim.
There is no map-specific escape sequence. See the
[controlled proof and limits](behaviour-diagnostics.md#shared-failed-plan-recognition).

Flat ordinary walking handoffs require support. Submerged seats can use water
support; dry airborne entries still wait for landing. Off-centre approaches use two
lateral rays into the next corridor; positions within eight units of the
canonical node trust that seat. Both normal arrival and the apex shortcut use this check;
A following jump waits for its actual launch seat and ground support. A
swim exit waits for a grounded bank at the right height, allowing shallow
wading. Endpoint action resolution chooses a feasible link when several
typed actions join the same pair; a swim route cannot become an unaffordable
rocket jump simply because that slot comes first.
The wall-slide cutoff and arrival radius stay unchanged. Visible-item
shortcuts preserve any remaining typed transition or substantial height
change. Routed diving follows submerged seat depth within eight units.
Planned water vaults retain upward momentum and compensate discrete gravity;
near-level hurdle jumps check body-width lookahead and apex clearance.

Route execution also tracks the best distance to its current seat. Twelve
units of improvement renew a three-second unpaused action clock; speed and repeated
bobbing alone do not. Combat, doors, train patrols, charged jump setup, authored tactics and chosen
pauses retain ownership. A supported static pad may wait for a lift, but a
lift ride must keep approaching the landing; crush/reverse cycles cannot
renew the action clock merely by carrying the bot. Optional sound pursuit
yields to committed route actions. Gait anticipation checks two nearby
seats, avoiding a fresh or continuing hesitation just before a typed action. A failed action temporarily avoids the seat and
replans, preserving an explicit navigation task.
 A validated apex
transition also supplies the shared progress observer, so detours do not lose
their deadline solely because they used corner cuts.

Grounded support on an actually moving platform retains the lift hold through
docking, even when the exit is already near the bot's height. At the top,
`Argus_MoverGapJumpOK` can validate an exit jump at current speed using the
existing gravity-aware arc check and the routed floor's height. Launch hands
ownership from the lift action to airborne route control without replacing
the goal. The forecast rejects lava/slime but does not independently require
a dry landing; the private transfer fixture checks that stronger outcome on
world geometry. See the [dock-exit decision study](e1m6-decisions.md).

Walking bots dispatch stock button contact for an engine-confirmed supporting,
unpressed touch button, preserving callback context. Door opener lookup follows
target chains with bounded depth/work and rejects unreachable touch triggers.
A solid button must acknowledge activation before waiting. Near-side bots keep
nearby opening-door ownership until the slab finishes, with one eight-second
opening phase and the existing timeout path. Remote buttons and already-passed
doors retain their walking paths. See the
[physical contracts and controls](behaviour-diagnostics.md#opening-door-ownership-and-physical-deadline).

Development source also gives ordinary patrol a human gait. Outside combat a
bot may choose a short stop with one of three recorded causes - a sound it
heard, a junction it reached, or settling after it slowed - and it approaches
lava or slime below full speed. Every disqualifying condition is re-tested
each frame, so an enemy, pain, a typed hop, a mover, a door errand or an
unstick ends a pause on the frame it arrives. The stall detector suppresses
only the frames the hold actually held, plus a short tail, because a chosen
stop is not a movement failure. Pauses are gated to skill 1 and above, never
run in co-op, and scale with each personality's deliberation appetite. See the
[measurement, refusals and limits](behaviour-diagnostics.md#human-gait-hesitation-and-cautious-liquid-approach).

### Navigation is generated, not loaded at runtime

QuakeC has no file I/O. A BSP is sampled offline into generated
`argus_nav_<map>.qc`, compiled into `progs.dat`, and registered in both the
dispatcher and build manifest. Its `.qc.json` twin is for tooling.

Generation accounts for player-hull support, movement arcs, doors and mover
geometry, spawn reach and the edict budget. Real-engine probes record refused
links by endpoint; proven candidates and learned hotspot costs feed the next
generation. A generated graph and a well-connected graph are different claims.
New maps need current reach and mill evidence before registration.
Infrastructure and synthetic platform pads share the hard waypoint allowance
with ordinary seats, after world/client slots and the 60-entity runtime
reserve. Hard-limited maps refine sampling within that allowance. A legal
budget is necessary but does not prove spawn or item reach. The experimental
e1m3/e1m4 files remain unregistered; see the [wider-map findings](mover-intelligence.md).

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
| `src/argus_nav_<map>.qc` | Generated graph; active only with compilation-list and dispatcher entries |
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
