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
  `movement.deflection_causes` counts brink-deflection episodes by the steering
  cause that led into each one. The brief's `hazards` total is throttled to one
  a second per bot and mostly measures combat strafes on narrow walkways.
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
| [Route elbow](specs/2026-11-16-route-elbow-protocol.md), 5 x 120 s | steer at the axis-aligned elbow when the line to the node crosses a void | route-steer deflection episodes a tape | 87.4 | 90.6 | 49.2 | no effect; refuted |
| [Brink turn](specs/2026-11-16-brink-turn-protocol.md), 5 x 120 s | beside lethal liquid, turn the movement heading 3x faster and double friction while turning | the same | 114.8 | 89.0 | 56.1 | no detectable effect |
| Brink turn confirmation, 8 x 180 s | the same | episodes per 1000 route-steer samples | 56.9 | 45.8 | 12.1 | no detectable effect; parked |
| [Early turn](specs/2026-11-16-early-turn-protocol.md), 10 x 180 s | at a hazard corner, hand the steering to the next node 0.35 s of travel out | the same | 53.2 | 56.9 | 8.6 | the wrong way; refuted |

None of the three changes was run on a stock map, because none cleared the
lab bar, and all are reverted with their post-mortems beside the route
steering in `Argus_AI`. The claims are `route-elbow-void-corners` (refuted),
`brink-turn-lava-corners` (parked) and `early-turn-lava-corners` (refuted) in
`tools/lab_claims.json`, and every tape's map, size and SHA-256 is in the four
`runs/lab-voidcorner-*.results.json` files.

What the scenario established, which no stock tape had shown:

- The brief's `hazards` count is throttled and dominated by combat strafes:
  on this map route steering led into about one deflection episode in eight.
  `movement.deflection_causes` now separates them.
- 74 per cent of the deflections that follow route steering begin mid-turn,
  with the movement heading rotating at `AR_TURNRATE` (320 degrees a second)
  at about 200 u/s. Stock acceleration only adds along the wish, so offline NQ
  integration puts the overshoot of a 90 degree turn at that speed at 97u,
  more than a 64u walkway's half-width. A corner fix has to start the turn
  early or shed speed; running to the corner centre first (the elbow) adds
  overshoot.
- The instrument's own spread is large: the same control code read 49.8, 66.6,
  56.9 and 53.2 episodes per 1000 route-steer samples in four ladders. A change
  needs a bigger effect than the brink turn's 20 per cent, or more tapes than
  ten pairs, to clear it.
- Starting the turn earlier at the waypoint, sized by that integration to keep
  a centred bot on the floor, changed nothing. The integration models a clean
  corner entry; the turns that end on the lip start somewhere else
  (re-routing, a goal change, resuming after a fight, an off-centre entry),
  and the next corner change should find where before it is written.

## Limits

- Brushes are axis-aligned boxes: no slopes, curves or diagonal walls.
- No monsters and no arbitrary brush entities; doors and teleporters come only
  from connections.
- Lighting is a flat minimum light level; the maps are for bots, and for a
  person checking them in the engine.
- The generated graph is still navgen's. A lab map tests navigation and
  runtime behaviour on that graph, and it can expose a navgen limitation as
  readily as a runtime one.
