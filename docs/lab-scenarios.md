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
`off_graph: true` on a floor exempts it from the coverage gate (below), for a
pocket the map means to have; without it, a floor the generated graph seats no
waypoint on refuses registration.

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
4. **Coverage** (`python tools/lab_mapgen.py coverage`): every floor region at
   least 32u wide must seat a waypoint of the generated graph within 64u above
   its floor. A floor with none is a pocket that bots fall into and leave by
   no link, and their routed motion there measures that, not the behaviour
   the map isolates; `lab_drymix` and `lab_drymix2` registered with one
   before this gate existed. A region the request marks `off_graph` is exempt;
   stairs, blocks, pits and voids are not checked. An uncovered floor skips
   registration.
5. **Register** through the first-registration gate, for this map alone:
   every spawn must reach every pickup and the mill must pass the current
   graph. A map that fails stays experimental, and the stage says why.
6. **Record**: fold the navgen, mill, coverage and registration results into
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
mill passes, waypoints per floor region (`coverage`) and registration. The
scenario entry in `tools/lab_instruments.json` lists any uncovered floor as
`off_graph_regions`.

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
  metrics, and every tape's map, size and SHA-256) and cite it in the claim.
  When the tapes are too large to commit, name the ladder's runs
  `study_<stem>_...`, which one `.gitignore` rule keeps out of Git with their
  navigation receipts, and set the results file's `tape_storage` to
  `machine-local`; `argus_ci.py localtapes` fails while any tape it lists is
  trackable (#872).

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

## The second scenario: lab_drymix

`lab_drymix` keeps dm4's 96u walkway width and adds dm4's other lip types: a dry
ledge 80u down with lava beyond it on the west, and a plain 64u dry drop with
stairs back up on the south, beside lethal lava lips on the north and east. It
was the first scenario built through the `lab_request` MCP tool. That first
call found a defect in the tool itself: the client sent the nested request as a
JSON string, and the tool now reads a string that parses to an object as that
object. The first pass of the mill then convicted six links on both walks,
among them a stair-side crossing a riser too tall to walk and a corner diagonal
over lava, so the gate refused registration; the rerun regenerated the graph
with those convictions consumed and walked all 342 links clean. That is the
stock road working as it should.

Its registered ladder ([protocol](specs/2026-11-17-drymix-protocol.md)) asked
whether the map carries dm4's mix and whether it then predicts dm4's result for
the mode-2 brink check. It does not qualify: 55 per cent of its control
re-entries point at lava or a void, one point outside the 24 to 54 per cent band
around dm4's 39 (`lab_voidcorner` read 95), and its noisier control left the
change's reading (88.4 to 73.6, limit 24.7) unable to tell dm4's result from
`lab_voidcorner`'s. The mix check needed only the control arm, so run it first
on any new lab map meant to stand in for a stock map.

### lab_drymix2 and the coverage gate

`lab_drymix2` added a second run-off ledge along the north walkway to push the
share down. Its registered mix check
([protocol](specs/2026-11-17-drymix2-mix-protocol.md)) read 64 per cent, ten
points above the band, and two post-hoc readings of the recorded tapes say
why. First, a run-off ledge is a dry drop only from the walkway above it: its
own inner edge drops straight into lava, so a bot on the ledge meets a lethal
lip. Second, and worse for the instrument, splitting re-entries by whether the
bot stood within 128u of a waypoint showed that every one of dm4's control
re-entries happens on the graph, while 58 per cent of `lab_drymix`'s and 36 per
cent of `lab_drymix2`'s happen on `ledge_s`, a ledge the generated graph seats
no waypoint on. The stairs in both requests run across the ledge and cut it
into a pocket that bots fall into and leave by no link. On the graph, both maps
read about 71 per cent lethal against dm4's 39; `lab_drymix`'s near miss was an
average of that and an off-graph artefact
(`runs/lab-drymix2-mix.results.json`).

`lab_request` registered both maps anyway, because nothing checked that the
graph covers the layout. It now does: the `coverage` stage refuses
registration while a standable floor seats no waypoint, unless the request
marks that region `off_graph`. Both drymix maps were registered before the
gate. Their scenario entries carry `off_graph_regions`, and they are not fit
for a mix question. To give a ledge a way back up, put the stairs at the end of
the ledge, rising along it, not across it.

### What deflects routed bots: dm4 against the lab maps

The mix checks above probed 48u along the wish, which is not what the guard
does. `tools/argus_guard_replica.py` replays the physics guard itself: the
velocity heading after one frame of friction and acceleration, the
speed-scaled 32 to 52u probe, and every branch of `Argus_MoveHazard`, including
the run-off landing test. It validates itself on each tape against frames
whose verdict is known, and on eight dm4 control tapes it recalls 89.5 per cent
of route-led deflections with 1.9 per cent false vetoes
(`runs/dm4-reentry-guard.results.json`).

Of dm4's 1369 re-entries, 47 per cent are the guard's probe buried in a wall,
36 per cent lava under the probe, 6 per cent a void, and 2.5 per cent the run-off
landing test. The 48u wish probe's lethal share (39 per cent) matches the
replica's lava plus void (42), and its other class was mostly walls, not
run-off lips. So the mode-2 brink check, which acts on lethal lips, could
reach at most two in five of dm4's re-entries, and the run-off test is not
worth a change of its own.

On all three lab maps, 97 to 98 per cent of re-entries are lava vetoes and none
are walls. A generated floor or stair tread is a 16u slab over open air, and a
trace that starts inside solid and leaves it reports the next solid it meets,
so a probe buried in a slab finds the lava below. (The replica first treated
every start in solid as finding nothing, and missed a quarter of the drymix
vetoes. On the probes where the two rules disagree, the engine's rule
predicted 1250 of 1365 known outcomes and the other 518.) No lab map built so
far contains dm4's commonest re-entry. A map meant to stand in for dm4's
flicker needs walls that the guard reads as walls, which in a generated map
should mean `walls` on regions with `solid_below` (untested), and its mix
should be read with the replica.

### lab_wallmix: walls the guard reads as walls

`lab_wallmix` is a ring of 96u walkways over lava whose outer edges are the hull
walls (`margin: 0`, walkways `solid_below`), with pillars rising from the base
to fill two of the four inner corners. Before any tape the replica read a probe
into the hull wall or a pillar as a wall, which confirms the recipe: a wall
reads as a wall when the solid under it reaches the base. It registered on the
first call, and the coverage gate passed on its first live use.

Its registered mix check ([protocol](specs/2026-11-17-wallmix-mix-protocol.md))
read 20 per cent walls and 77 per cent lava over 357 re-entries, against bands
of 32 to 62 and 27 to 57, so it does not carry dm4's mix, though it is the first
lab map with any walls at all. Three in four of its re-entries are at the inner
lava lip of the straights. Its corners carry few, because a ring's corner
square leaves a walkway-wide space to turn in. dm4's wall re-entries cluster
instead: one 128u cell holds 122 of 647, the north-west corner of an open room
at the end of a wall column, where routes leave the room into a corridor that
turns around the wall end (`runs/lab-wallmix-mix.results.json`). That turn is
what the next map needs.

### The overhead target: lab_dropwall, lab_dropwall2 and lab_jumpgap

Read frame by frame, dm4's cell is not a corridor turn. Node 111 on the walkway
carries a staged jump to node 115 across the open top of the room below. A bot
lining up for it turns more slowly than it runs, its run-up carries it off the
walkway edge (a legal 128u drop the guard allows), and it lands in the room
still on the hop, steering at a point 128u overhead behind the walkway's side
wall. The displacement guard re-plans only beyond 340u horizontally, and its
vertical clause covers water alone, so the bot slides along that wall for
seconds until a stall.

Three lab maps tried to hold that. `lab_dropwall` copied the walkway and room
but left the room open, and its bots fought instead of routing: route steering
was 0.4 per cent of motion samples against dm4's 27, and its mix check failed on
13 re-entries (`runs/lab-dropwall-mix.results.json`). `lab_dropwall2` split the
room into bays and restored routing, but its walls are bay-wall ends at the
bots' own level, with no overhead target. `lab_jumpgap` cut the walkway with a
jump over the room, and the mill refused the jump at a 128u gap and at 96u, so
it was not registered.

A grounded re-plan for an overhead target behind solid was laddered under a
registered protocol ([protocol](specs/2026-11-17-overhead-target-protocol.md)).
Its lab rung was void (no mechanism on `lab_dropwall2`). Its first version
exempted jump hops and so could not reach the room case. The second, without
that exemption, cut dm4's overhead-target re-entries from 15.75 to 11.62 a
tape, inside the detection limit of 6.99. The room case survived it because
dm4's jump is staged and the staged run-up ran under a state the clause still
exempted, so a third version acted there too; it moved the re-entries from
12.12 to 12.75 (limit 7.94). Neither regressed a guard, and the hypothesis is
refuted by its own registered test. Post hoc, the third version did shorten
the room stays (the longest routed stay 3.8 s against the control's 8.6), but
the room holds only one to three of the twelve to sixteen overhead-target
events a dm4 tape carries, so fixing it cannot move that primary, and the same
control binary read 15.75 on one ladder and 12.12 on the next. Both patches
are recorded (`runs/dm4-overhead-target.results.json`), not shipped. The
lesson for the next ladder: size the primary to the mechanism it targets. The
room case itself stays open
([#867](https://github.com/saworbit/argus/issues/867)), and the scorer behind
this primary ran outside the repo
([#868](https://github.com/saworbit/argus/issues/868)).

The lab maps taught one more rule: a lab map has to keep dm4's balance of
routing and fighting, not just its geometry. An open room gives every bot a
line of sight to every other, and the routed travel the brink work measures
stops happening.

## Limits

- Brushes are axis-aligned boxes: no slopes, curves or diagonal walls.
- No monsters and no arbitrary brush entities; doors and teleporters come only
  from connections.
- Lighting is a flat minimum light level; the maps are for bots, and for a
  person checking them in the engine.
- The generated graph is still navgen's. A lab map tests navigation and
  runtime behaviour on that graph, and it can expose a navgen limitation as
  readily as a runtime one.
- A `jump` connection does not yet survive the mill: both of `lab_jumpgap`'s
  jump links were refused at a 128u gap and at 96u, the puppet falling into
  the gap each way, so a scenario that needs a jump cannot register
  ([#866](https://github.com/saworbit/argus/issues/866)).
