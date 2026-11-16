# Lab scenarios

[Back to the lab workflow](lab-workflow.md) |
[Operator guide](../tools/argus_mcp/README.md#lab-scenarios-lab_request)

A lab scenario is a purpose-built micro-map that isolates one bot behaviour:
a corner, a stair into a teleporter, a ledge over lava. An agent describes it
as a structured request; `lab_request` turns the request into a compiled BSP,
takes it down the same road a stock map travels (navgen, the mill,
registration through the reach and mill gate) and records it as an
instrument. A stock map mixes every mechanism at once, so a change that moves
one of them is often lost in the others. On a micro-map the mechanism runs
dozens of times a minute.

## The promotion rule

Lab maps are isolation instruments. A result measured on a lab map can
support an isolation-tier claim only. A claim about stock geometry needs a
separate run on real geometry (dm2, dm3, dm4, dm6 or another stock map), and
it cites the lab tapes and the stock tapes together.

The rule is enforced, not advisory. `tools/lab_instruments.json` lists every
scenario under `lab_scenarios`, with `claim_tier: isolation`, and
`python tools/argus_ci.py lab` fails when:

- a claim cites a tape recorded on a lab map without naming that map in its
  `maps`, so a lab result cannot hide inside a stock claim;
- a supported or fixed claim names a lab map and a stock map but cites no tape
  recorded on each of them. A tape's map is read from the engine's own
  `SpawnServer` line, not from its name. Evidence can also be a ladder's
  committed results file whose `tapes` list records each tape's map (read
  from that line), size and SHA-256, because full-rate diagnostic tapes are
  too large to commit and stay machine-local, like the frozen study tapes.

If a change does not transfer to real geometry, the claim names the lab map
only and stays at the isolation tier, with the stock tapes and the reason in
its statement.

## Install the map compiler

Generated maps are compiled with ericw-tools 0.18.1 (tag `v0.18.1`, commit
`b6e2431f29a1f5763d4aa5fa37cb06838580f41a`, the latest stable release). The
pinned assets, sizes and SHA-256 sums live in
[`tools/lab_mapgen_profile.json`](../tools/lab_mapgen_profile.json):

| Platform | Asset | SHA-256 |
|---|---|---|
| Windows | `ericw-tools-v0.18.1-win64.zip` | `a0f39c6f...6e9cd3` |
| Linux | `ericw-tools-v0.18.1-Linux.zip` | `986531ff...f040e2` |

From the repository root, this **terminal command** downloads the asset for
the platform from the GitHub release, refuses it unless the size and SHA-256
match, and unpacks it under `tools/external/ericw-tools/`, which Git ignores:

```text
python tools/lab_mapgen.py tools --install
```

`--from-zip PATH` installs from a copy you already have, under the same check.
`ARGUS_ERICW` points at another directory holding `qbsp`, `vis` and `light`.
The tools are GPL-3.0; the repository carries none of their files.

## The request

A request is JSON. Distances are Quake units, snapped to an 8u grid; x and y
are the floor plan and z is height.

```json
{
  "schema": 1,
  "name": "lab_voidcorner",
  "intent": "Isolate route handoffs at void-edged corners ...",
  "claim_tier": "isolation",
  "claims": ["e1m7-early-switch-runoffs", "dm4-walkway-corner"],
  "constraints": {"max_brushes": 60, "max_entities": 30, "liquids": ["lava"], "min_spawns": 4, "margin": 128},
  "base": {"floor_z": -192, "liquid": "lava", "liquid_depth": 48},
  "regions": [
    {"name": "south", "kind": "walkway", "min": [0, 0], "size": [768, 64], "floor_z": 0,
     "connections": [{"to": "east", "type": "open"}]},
    {"name": "column", "kind": "block", "min": [256, 256], "size": [256, 256], "floor_z": -192, "height": 384}
  ],
  "entities": [
    {"classname": "info_player_deathmatch", "region": "south", "at": [0.25, 0.5], "angle": 0},
    {"classname": "item_armor1", "region": "south", "at": "centre"}
  ]
}
```

[`labmaps/lab_voidcorner/request.json`](../labmaps/lab_voidcorner/request.json)
is the full example.

| Field | Meaning |
|---|---|
| `name` | `lab_[a-z0-9_]{1,28}`. The prefix keeps a generated map from ever shadowing a stock one |
| `intent` | One or two sentences: the mechanism the map isolates |
| `claim_tier` | `isolation`, the only tier a generated map can carry |
| `claims` | Claim ids in `tools/lab_claims.json` the scenario is built to test |
| `regions` | Named boxes (below) |
| `entities` | Point entities placed by region name (below) |
| `constraints` | Budgets and permissions (below) |
| `base` | The floor under everything: `floor_z` (default 64 below the lowest floor), optional `liquid` and `liquid_depth` |
| `headroom` | Open air above the highest standing surface, 128 to 1024, default 192 |
| `notes` | Free text, kept in the manifest |

Every region has `name`, `kind`, `min` [x, y], `size` [w, d] and `floor_z`.
Kinds:

| Kind | Builds |
|---|---|
| `floor` (or `room`, `platform`, `walkway`, `corridor`, `ledge`) | A 16u slab whose top is `floor_z`; `solid_below: true` fills it down to the base |
| `pit` | A floor at `floor_z` with optional `liquid` (`lava`, `slime`, `water`) `liquid_depth` deep |
| `block` | A solid column from `floor_z` up `height`; it may rise from the base |
| `stairs` | Treads from one riser above `floor_z` to `to_z`, running along `axis` (`+x`, `-x`, `+y`, `-y`), each riser at most 16u |
| `void` | Nothing; names open air for the adjacency report |

`ceiling` adds a ceiling slab that height above a region's floor, and
`walls` (`sides`, `height`, `thickness`) adds walls inside chosen edges.

Connections are declared on a region and checked against the geometry before
anything is written. A connection the layout cannot provide is refused with
the measurements:

| Type | Requires |
|---|---|
| `open` | A shared edge at least 32u long, standing heights within 18u |
| `drop` | A shared edge, falling more than 18u and at most 200u from `from` to `to` |
| `stairs` | A shared edge within 18u, with a stairs region at one end |
| `jump` | Facing footprints at most 160u apart, landing at most 40u up |
| `door` | A shared edge within 18u; builds a touch-opened `func_door` across it |
| `teleporter` | A floor at the far end; builds a `trigger_teleport` and its destination |

Entities take `classname` (spawns, items, weapons, `info_intermission` and
`info_teleport_destination`; monsters and arbitrary brush entities are
refused), `region`, `at` (`"centre"`, [fx, fy] fractions of the region, or
`{"offset": [dx, dy]}` from its corner), optional `z`, `angle`, `spawnflags`
and `keys`. Origins are set from the standing surface at that point, so an
item on a stair tread sits on that tread.

| Constraint | Default | Hard limit |
|---|---|---|
| `max_brushes` | 200 | 200 |
| `max_entities` (worldspawn included) | 60 | 60 |
| `sky` | false (a closed ceiling) | |
| `teleporters` | 0 | 8 |
| `doors` | 4 | 8 |
| `liquids` | all three | |
| `min_spawns` | 2 | |
| `margin` (open air between the outermost regions and the hull walls) | 0 | 512 |

The world stays inside +-4000 units, because protocol 15 sends coordinates as
shorts in eighths of a unit. Small maps keep the edict budget easy: a 60
entity map plus navgen's waypoints, the client slots and the 60-entity runtime
reserve stays far under 600.

## What lab_request does

`lab_request` (MCP) and `argus-mcp lab-request <request.json>` (CLI) run these
stages and return the manifest, a scenario id and `next_steps`:

1. **Build** (`python tools/lab_mapgen.py build`): validate the request, lay
   out axis-aligned brushes inside one sealed hull, write
   `labmaps/<map>/<map>.map` and a generated texture WAD, compile with `qbsp`,
   `vis` and `light` under the checked-in profile, refuse a leak or a BSP that
   is not version 29, and install the BSP into `ARGUS_MAPS` and the engine's
   game `maps/` directory.
2. **Navgen** through the lab's own `nav_generate`, exactly as for a stock
   map: `src/argus_nav_<map>.qc` and its `.qc.json` twin.
3. **The mill**: every walk link (and every jump link, when there are any) is
   walked by the puppet in the real engine. On a micro-map the three skill-0
   bots share the walkway being walked, so lab_request confirms: a link whose
   first attempt fails, or whose teleport never lands, is walked again at the
   end of the sweep and only a second failure convicts
   (`argus-mcp probelinks <map> --confirm` does the same by hand).
4. **Register** through the first-registration gate, for this map alone:
   every spawn must reach every pickup and the mill must pass the current
   graph. A map that fails stays experimental, and the stage says why.
5. **Record**: fold the navgen, mill and registration results into
   `labmaps/<map>/manifest.json` and register the scenario in
   `tools/lab_instruments.json`.

The textures are generated by `lab_mapgen.py` itself, so a lab BSP carries no
third-party art. The generator also places an `info_intermission` in clear air
when the request has none: qbsp fills the outside of the clipping hulls from
entity origins it finds in empty space, a spawn 24u above a floor sits exactly
on hull 1's expanded floor, and without an occupant the outside of hulls 1 and
2 stays open and navgen seats waypoints on the roof.

The manifest carries the brush and entity counts against their budgets, the
region list, region adjacency (shared edges with their length and step,
overlaps and facing gaps), each declared connection as measured, the source
hash (the normalised request plus the generator version), the map, WAD and
BSP hashes, the compile profile hash, per-step compile results, navgen
readiness before navgen runs (spawns, pickups, standable area, room for
waypoints), and afterwards the graph counts, edict budget, playability verdict,
mill passes and registration.

Two compiles of the same request produce byte-identical BSPs, which the
integration test checks.

## Files

| Path | Tracked | Holds |
|---|---|---|
| `labmaps/<map>/request.json` | yes | The request |
| `labmaps/<map>/<map>.map` | yes | Generated source, for review and rebuilds |
| `labmaps/<map>/manifest.json` | yes | The manifest |
| `src/argus_nav_<map>.qc`, `.qc.json`, `.probe.json` | yes | The generated graph and mill verdicts, as for any map |
| `labmaps/<map>/*.bsp`, `*.wad`, `*.prt`, logs | no | Build outputs; `lab_request` rebuilds them |
| `tools/external/ericw-tools/` | no | The pinned compiler |

## Running a ladder

A lab map is judged like any other change, with the lab's own tools and the
same discipline: pre-register the primary metric before the tapes exist, use
five tapes an arm, interleave control and candidate, and keep every tape.

- Compile each arm with `compile_qc install=false` (or `argus-mcp compile`)
  with `ARGUS_SRC` and `ARGUS_PROGS` pointed at a private copy of `src/`, so a
  candidate never lands in `game/argus` or `engine/argus`.
- Copy `autoexec.cfg`, `progs/` and the lab map from `engine/argus/` into a
  scratch game directory, drop the arm's `progs.dat` in and select it with
  `ARGUS_GAME` for `argus-mcp match <map> <secs> <run> --port N`.
- For movement questions, add `scratch1 697` to that scratch `autoexec.cfg`.
  The tapes then carry the full-rate `ARGMOT` motion rows, and every brief's
  `movement.brink_encounters` counts brink encounters (deflections under 250 ms
  apart merged) by what started each one; `movement.deflection_causes` counts
  the raw episodes, which include flicker within one encounter. The brief's
  `hazards` total is throttled to one a second per bot and mostly measures
  combat strafes on narrow walkways. Parse motion rows with the lab's grammar:
  `ftos` pads fractional values, so `wish  66.8` carries two spaces.
- Run the same arms on a stock map before a claim names one (the promotion
  rule above).
- Write the ladder's results file into `runs/` (protocol, arm MD5s, per-tape
  metrics, and every tape's map, size and SHA-256) and cite it in the claim;
  the tapes themselves are listed in `.gitignore` when they are too large to
  commit.

## The first scenario: lab_voidcorner

`lab_voidcorner` is a 64u walkway ring over lava with four tight corners and
open air on both sides, a central column blocking sight across the ring, and
no splash weapons, so lava deaths mean movement rather than knock-ins. Navgen
spaced its waypoints 128u apart along each centre line, and three of the four
corner links run their centre line diagonally across the inside void. That
passes navgen's beeline test, which grades a link with the player hull's
wall-slide slack, and the brink guard then walks it as a run of deflections.
The fourth corner is seated, and there the early waypoint switch draws the
same diagonal.

It was registered through `lab-request` (scenario `lab_voidcorner-70ece72d72`,
graph MD5 `324e18b2`): the mill walked all 44 links, six of them only on the
confirming walk, and the gate passed. Four registered ladders ran on it, each
with control and candidate built from private source copies and run from
scratch game directories, every tape at the listen tick class:

| Ladder | Change | Primary | Control | Candidate | Detection limit | Reading |
|---|---|---|---|---|---|---|
| [Route elbow](specs/2026-11-16-route-elbow-protocol.md), 5 x 120 s | steer at the axis-aligned elbow when the line to the node crosses a void | route-steer deflection episodes a tape | 105.6 | 112.2 | 59.4 | no effect; refuted |
| [Brink turn](specs/2026-11-16-brink-turn-protocol.md), 5 x 120 s | beside lethal liquid, turn the movement heading 3x faster and double friction while turning | the same | 129.2 | 105.6 | 69.1 | no detectable effect |
| Brink turn confirmation, 8 x 180 s | the same | episodes per 1000 route-steer samples | 59.2 | 45.9 | 12.3 | moved |
| Brink turn stock rung, dm4, 5 x 185 s | the same | the same | 52.5 | 55.3 | 13.4 | level, no guard regressed: no harm, no benefit |
| [Mode-2 brink check](specs/2026-11-17-brink-flicker-protocol.md), 7 listen x 180 s | after a deflection, route a vetoed routed heading through the guard's HazardSteer | episodes per 1000 route-steer samples | 63.6 | 50.9 | 11.2 | moved |
| Mode-2 brink check stock rung, dm4, 8 x 185 s | the same | the same | 55.3 | 55.6 | 12.2 | level, no guard regressed: no harm, no benefit |
| [Early turn](specs/2026-11-16-early-turn-protocol.md), 10 x 180 s | at a hazard corner, hand the steering to the next node 0.35 s of travel out | the same | 56.1 | 58.8 | 7.9 | the wrong way; refuted |

These are the corrected readings. The first analysis read motion rows with a
pattern that expected one space after `wish`, and QuakeC's `ftos` pads
fractional values, so about 8 per cent of samples were dropped. Each protocol
keeps its first-recorded numbers and a correction section, and each results
file keeps `original_analysis`. The correction changed one verdict: the brink
turn confirmation's registered primary moved (it had read no detectable
effect).

All three changes are reverted, with their post-mortems beside the route
steering in `Argus_AI`. The route elbow and the early turn are refuted. The
brink turn is supported at the isolation tier only (`brink-turn-lava-corners`):
it cut flicker on the lab map by a thin margin, and its registered dm4 stock
rung held without transferring, every guard inside its limit and the primary
level. That is evidence it does no harm on dm4, not that it helps there, so
the claim names the lab map alone and the change stays out of the build. Why
it did not transfer is not measured; its lethal-liquid gate may simply trip
too rarely on dm4, whose brinks mostly drop to dry floor. Every tape's map, size and SHA-256 is in the `runs/lab-voidcorner-*.results.json`
files.

### What the scenario established

- The brief's `hazards` count is throttled and dominated by combat strafes;
  route steering leads into about one deflection episode in eight on this map.
- Deflection episodes mostly count flicker. Over the 28 control tapes, 71 per
  cent of route-steer episodes begin mid-turn, and 77 per cent of those begin
  straight after a previous deflection: routed mode 2 is exempt from the
  steering-side hazard check, so route steering turns the heading back at the
  node for a frame or two and the guard fires again. Two dm4 control tapes
  show the same 77 per cent. Episodes run about four times brink encounters
  (episodes under 250 ms apart merged), and the encounter rate is much
  steadier between ladders (13.2 to 14.4 per 1000 route-steer samples on the
  same control code, against 53.3 to 67.8 for episodes). Briefs now carry
  `movement.brink_encounters` beside `movement.deflection_causes`; judge a
  brink change on encounters.
- Waypoint handoffs start under 1 per cent of mid-turn route deflections on
  the lab map and 4.5 per cent on dm4, which is why the elbow and the early
  turn, both handoff changes, moved nothing. Encounters start most often from
  steady routed running (30 per cent on the lab map, 44 on dm4), then from
  resuming after combat (lab) or after a noise (dm4).
- Stock acceleration only adds along the wish, so offline NQ integration puts
  the overshoot of a 90 degree turn begun at 200 u/s at 97u, more than a 64u
  walkway's half-width; that integration models a clean, centred entry, which
  is not where these encounters start.
- None of the four ladders moved brink encounters (not registered; each
  results file carries them). The brink turn cut flicker within encounters,
  not visits to the brink.

The open defect is `route-steer-brink-flicker`. The candidate built
straight from the diagnosis, a hazard check for routed steering in the quarter
second after a real deflection (`mode2-brink-check`), cut the flicker a fifth
on the lab map, with a lava warning there, and changed nothing on dm4 while
harming nothing, so it too is an isolation-tier result and reverted. The
diagnosis found the same re-entry share on dm4, so the next question is
whether that check's gate opens on dm4's dry-drop lips at all. It does: the
check acted on both maps and cut the re-entries whose wanted heading points at
lava or a void by about 40 per cent on each. But those are 95 per cent of the
lab map's re-entries and 39 per cent of dm4's, where most re-entries happen at
lips no floor probe calls lethal, which points at the guard's run-off landing
test (`runs/lab-voidcorner-brink-flicker-gate.results.json`). The diagnosis is
in `runs/lab-voidcorner-turn-diagnosis.results.json`.

### A lesson for building lab maps

A micro-map isolates a mechanism by stripping everything else out, and it can
strip out the case that matters on the stock map. Every lip of lab_voidcorner
drops into lava, so it measured a change that acts on lethal lips at full
strength and said nothing about dm4's dry-drop lips, where most of dm4's
flicker happens. Before trusting a lab map for a stock-map question, compare
the mechanism's mix on both (the diagnosis files show how) and give the lab map
the stock map's mix: for brink work, lethal lips beside dry drops.

## Limits

- Brushes are axis-aligned boxes: no slopes, curves or diagonal walls.
- No monsters and no arbitrary brush entities; doors and teleporters come only
  from connections.
- Lighting is a flat minimum light level; the maps are for bots, and for a
  person checking them in the engine.
- The generated graph is still navgen's. A lab map tests navigation and
  runtime behaviour on that graph, and it can expose a navgen limitation as
  readily as a runtime one.
