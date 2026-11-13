# Navmesh from the clip hull

[Architecture](architecture.md) | [Lab workflow](lab-workflow.md)

EXPERIMENTAL, 2026-11-13. The mesh tools are not used by any build. What
the audit found IS fixed in source: `argus_navgen.py` gained a feet-level
liquid test, a zero-length beeline rule and `--repair-links`, and nine
shipped graphs were repaired with it (see [The fix](#the-fix)). Nothing is
installed; installed binaries keep MD5 `A3F7AA9428846DE7F7B327506F5F5D3D`.

## The idea

`argus_navgen.py` samples hull 1 on a 32u (or 16u) grid and keeps what the
grid happens to stand on. Hull 1 is already a navmesh in disguise: every
empty leaf of the player clip tree is a convex region where the player
ORIGIN fits, and qbsp has folded the 32x32x56 body into it. The
upward-facing faces of those leaves that rest on solid are the exact set of
origins a player can stand on. Nothing needs sampling, so a 20u corridor or
a 16u stair tread is found exactly as it is.

## Tools

`tools/argus_navmesh.py` extracts the mesh and audits a shipped graph
against it.

```bash
python tools/argus_navmesh.py maps_local/dm4.bsp --audit
```

```bash
python tools/argus_navmesh.py maps_local/dm4.bsp --png dm4_mesh.png --nav src/argus_nav_dm4.qc.json
```

- Extraction walks the clip tree, builds each empty leaf's floor faces by
  clipping a plane against the leaf's half-spaces, then walks each face back
  down the tree a fraction of a unit below itself and keeps the parts that
  land in solid. 1 to 3 seconds per map.
- Lava and slime are dropped by hull-0 contents at the feet and torso, since
  hull 1 collapses liquids to empty. Water floors are kept and marked wet.
- Walk portals join fragments whose edges are collinear in plan, lie on
  opposite sides of the shared line, and differ by at most one 18u step.
- Drops are found by stepping a body just past every ledge edge and letting
  it fall: open air at head height, no floor within a step, and a landing
  on a real fragment within DROPMAX. Pairing edges alone missed every ledge
  that overhangs the middle of a lower floor.

`tools/argus_navmesh_graph.py` derives a waypoint graph from the mesh.

```bash
python tools/argus_navmesh_graph.py dm4 OUTDIR [--max-seats N]
```

- Typed links (jump, rocket, sprint, teleporter, lift, swim, train) are
  inherited from the shipped graph WITH THEIR EXACT ENDPOINT SEATS, so every
  arc navgen verified survives and the experiment isolates one variable: how
  the walk graph is built.
- Control items get a seat. Coverage seats are placed roomiest first, so a
  seat stands in the middle of a space and a corridor only spends one where
  nothing covers it.
- A walk link is accepted only when a body following its straight line stays
  on the mesh, with world floor under its centre and no lava or slime at its
  feet. Each step may slide up to 16u sideways, as walkmove does along a
  wall. A link that starts in shallow lava may cross it (escape mode), so a
  knocked-in bot can still reach navgen's rocket-jump pad out of the pit.
- `--max-seats` builds dense and then removes the most crowded seat only when
  every in-neighbour still reaches every out-neighbour within three hops.
  Growing the radius instead (navgen's answer) left dm3 with 132 of 241
  seats on the mainland, because sparse seats cannot see each other round
  corners.
- navgen's own `--reanalyze-tactics` accepts the emitted pair and fills
  exposure and cover.

`tools/argus_pointfile.py --what mesh` draws the mesh outlines into a
listen game (`pointfile` at the console). It is a client command, so it has
not been checked by eye.

## What the audit found in the shipped graphs

| Map | Seats with feet in lava or slime | Vertical walk links | Plain links with no mesh path |
|---|---|---|---|
| dm2 | 1 | 0 | 10 |
| dm3 | 0 | 3 | 2 |
| dm4 | 7 | 3 | 1 |
| dm6 | 0 | 4 | 5 |
| lqdm2 | 0 | 0 | 2 |
| e1m1 | 6 | 0 | 21 |
| e1m2 | 0 | 0 | 7 |
| e1m5 | 0 | 2 | 6 |
| e1m6 | 3 | 1 | 21 |
| e1m7 | 41 | 2 | 2 |
| e1m8 | 12 | 0 | 3 |

Plain links with no mesh path include ballistic drops and mover-carried
hops, so that column is a reading list, not a defect count.

### Shallow liquid under seats

navgen's 4b drops lava and slime seats by testing hull 0 at origin+24,
which is 48u above the floor. WaterMove burns at waterlevel 1, so liquid
between the feet and that point is invisible to navgen and still lethal.

- e1m7: 41 of 204 seats stand in lava 39u deep. Across 113 e1m7 tapes, all
  208 lava deaths happened within 96u of one of those seats. THAT IS
  CORRELATION, NOT CAUSE, and it was read as cause until the ladder said
  otherwise: the seats sit in the lava lake, so any death in the lake is
  near one. The repaired ladder below shows e1m7's lava deaths come from
  routed bots running off the upper walkways (z 135 to 280) and landing in
  the lake, most with no damage taken first, which the repair does not
  touch.
- dm4: the seven pit-floor seats stand in 15u of lava. They are also
  navgen's 7g sink-escape seats, so removing them is not free.
- The lab's lava gate is NOT affected. Both parsers also probe 24u below
  the death origin, which catches all 192 pit deaths in 150 dm4 tapes.

### Vertical walks

`beeline_ok` returns True for any link shorter than 1u horizontally,
whatever the height difference, and 6b2's symmetric closure then adds the
reverse. Fifteen links across six maps are "walks" straight up 128 to 192u.

- dm3 n26 to n236 is the only walk entry to the north-west upper floor
  (SNG, rockets, nails). The mesh says that floor can be left on foot and
  never entered: three rocket-jump links are the honest way in. 16 of 758
  dm3 stall events in 157 tapes steer at n236.
- dm4's three pairs cost almost nothing in play (3 of 392 stall events).

## The fix

Both defects are fixed at the source for future generation, and in place
for the graphs that already ship, because a full regeneration would mix this
fix with every other change navgen has gained since each graph shipped.

- `hostile_at` tests lava and slime at the feet (origin minus 23) as well as
  the torso. Section 4b's seat filter and `beeline_ok` both use it.
- `beeline_ok` refuses a zero-length link that RISES past a step. A
  zero-length drop stays: the upper seat sits on hull 1's overhang strip and
  the runtime's lip tolerance carries a bot down it.
- `--repair-links` keeps every node and slot order, removes rising vertical
  walks, links from a dry seat into a liquid seat, and walks that wade liquid
  for 48u with no dry floor within 32u either side, then rebakes regions and
  tactics. Liquid seats keep their links out, so a knocked-in bot still
  routes to an escape. A cut liquid link comes back when it is a dry seat's
  only way to the mainland without a rocket or sprint: e1m8's spawn at
  (1000 -136 -712) stands on a ledge 40u above its lava floor, and half a
  second of wading beats the trapped exit. Liquid stays an exit, never a
  shortcut.
- The tactics pass rebuilt its block by adding a blank line to whatever was
  there, so every rerun grew the file by one empty line. It now restores
  navgen's own layout, which is what makes the repair idempotent.

```bash
python tools/argus_navgen.py maps_local/dm4.bsp dm4 src/argus_nav_dm4.qc unused.png --repair-links
```

| Map | Rising walks cut | Routes into liquid cut | Kept as only exit | Worst spawn reach before | After |
|---|---|---|---|---|---|
| dm2 | 0 | 1 | 0 | 96% | 96% |
| dm3 | 3 | 0 | 0 | 98% | 89% |
| dm4 | 3 | 15 | 0 | 98% | 93% |
| dm6 | 4 | 0 | 0 | 95% | 95% |
| e1m1 | 0 | 6 | 0 | 97% | 94% |
| e1m5 | 2 | 0 | 0 | 89% | 89% |
| e1m6 | 1 | 4 | 0 | 95% | 93% |
| e1m7 | 2 | 6 | 0 | 88% | 68% |
| e1m8 | 0 | 67 | 3 | 100% | 93% |

lqdm2 and e1m2 had nothing to repair and are untouched. Every reach drop is
seats that were only "reachable" through lava or an impossible climb: dm4's
seven pit seats, e1m7's 41 lava seats, e1m1's six slime seats. No dry seat
lost reach on any map except dm3, where 22 seats of the south upper area
(x -219 to 389, z 56 to 328) were entered only by the n44 to n47 and n214
to n212 climbs. That area holds dm3's RED ARMOUR at (256 -704 304). Across
157 dm3 tapes on the shipped graph, bots chose it as a goal 70 times and
never came within 96u of it: the climbs made the planner believe in a route
no bot could walk, so every one of those errands was doomed. After the
repair the area is a stranded region and the planner stops choosing it. The
mesh finds a real walking route into that area which the graph has never
had; seating it from the mesh would give bots dm3's red armour, and is the
obvious next piece of work. The reach gate's FAIL verdict is
unchanged: it was e1m8's two spawns over 200u from any waypoint before the
repair too.

`tools/test_navmesh_repair.py` builds a map with a 16u lava strip and checks
every rule, idempotence, the region rebake and the mesh audit.

### The repair ladder

Same rig as below: skill 2, 185 s, played tick rate, every tape in the listen
class, six engines at once. Control is the unrepaired build (ccdb0f52, the
dm4 mesh ladder's control, so its eight dm4 tapes carry over); the repaired
build is 42637d43, compiled from main with the nine repaired graphs. Main
moved during the session (#765 changed `argus.qc` comments only, which
compile to identical bytes; #760 bumped lab dependencies), so the arms still
differ only in navigation. Primaries were registered before any tape:
lava deaths on dm4, e1m7 and e1m8, stall parity on dm3. The staged lab had
to be rebuilt from the moved checkout before it would issue verdicts.

| Map | Tapes | Primary | Control median | Repaired median | Verdict | Mechanism |
|---|---|---|---|---|---|---|
| dm4 | 8 / 8 | lava deaths | 4 | 3 | parity, P(improve) 0.75 | lava entries 40 to 24; pit deaths 8 to 1 |
| e1m7 | 5 / 5 | lava deaths | 4 | 3 | parity, P(improve) 0.70 | rim falls unchanged (see below) |
| dm3 | 3 / 3 | stall parity | 18 | 16 | parity | red armour picks 7 to 0; goals 12 to 25; routefails 4 to 2 |
| e1m8 | 3 / 3 | lava deaths | 2 | 1 | parity, P(improve) 0.78 | lava entries 10 to 7, routed 7 to 4; stalls rose (see below) |

Secondaries, control to repaired medians: dm4 engagements 74 to 78.5, goals 19
to 24, stalls 4.5 to 4; e1m7 engagements 98 to 97, stalls 3 to 1; dm3
engagements 16 to 14. No freezes in any of the 38 tapes. dm2, dm6, e1m1,
e1m5 and e1m6 carry one to six cut links each and were not laddered.

dm4 is the clean case. Its repair cut every route into the pit, and lava
entries across eight tapes fell from 40 to 24, entries from routed mode from
30 to 17, and deaths within 96u of a pit seat from 8 to 1. The gate still
reads parity: lava median 4 to 3, interval -0.2 to +3.5, P(improve) 0.75.
The first four candidate tapes had looked stronger (median 1.5); the next
four pulled it back, which is the measurement-limits note again.

e1m8 carries a warning. Its lava numbers move the right way, but median
stalls rose 28 to 49 and engagements fell 22 to 10, both inside very wide
bands (control stalls ran 12 to 50 on one build). The stalls are not new:
both arms pile into the same cell, bots on the z 32 ledge near (860 64)
steering at n56 (833 -159 -368), 400u below them, whose only links in come
from its own floor. The control put 41 stall events on it, the repaired arm
78: with the lava-floor shortcuts gone, more routes run through a cell that
was already broken. That cell is the next e1m8 defect, and the repair can be
held back on e1m8 alone by restoring its two files.

e1m7 is the honest miss. Its lava deaths do not move, because they are not
the graph's doing: in the repaired arm routed bots still run off the upper
walkways at full speed and land in the lake, most with no damage taken
first. A drop-arc simulation clears navgen's drop links (only three of 42
land in lava at run speed, all starting from lava seats), so the falls come
from walking the upper floors, not from deliberate drops. That is a runtime
question and a separate piece of work.

## The mesh graph ladder

dm4, skill 2, 185 s, `+sys_ticrate 0.0139`, every tape in the listen tick
class. Both arms compiled from main at e0d5dc1 in scratch trees that differ
only in `argus_nav_dm4.qc`, and run from ignored mod dirs through
`ARGUS_GAME`. Control progs MD5 ccdb0f525b2892449c58c05804d891ef; mesh v1
15d8e2bc8a87aba9433d7a4ea5b88d33; mesh v2 14389db770f415a2a16aad1eecca62f0.
Primary metric pre-registered as stall parity.

| Arm | Tapes | Stalls | Engages | Goals | Lava | Freezes |
|---|---|---|---|---|---|---|
| Shipped graph (137 seats) | 8 | 2, 5, 9, 1, 20, 1, 23, 4 | 82, 76, 81, 72, 66, 73, 70, 75 | 16, 18, 34, 22, 19, 19, 16, 26 | 4, 3, 6, 5, 4, 4, 8, 2 | all 0 |
| Mesh v1 (127 seats) | 4 | 7, 4, 10, 11 | 70, 72, 72, 67 | 16, 20, 13, 23 | 6, 4, 4, 7 | all 0 |
| Mesh v2 (127 seats) | 4 | 9, 5, 1, 9 | 66, 66, 68, 80 | 18, 22, 34, 31 | 3, 8, 4, 4 | all 0 |

`argus-mcp compare` returns PARITY for both against the eight controls.
Every interval covers zero. Mesh v2 against control: stall median 4.5 to 7
(P(improve) 0.48), engagements 74 to 67 (95% CI -12.2 to +6.0), lava 4 to 4,
spatial coverage medians 363 to 358 cells, goal pickup median 19 to 26.5 on
four tapes. The gate card's own coverage row read 343 to 415, and that is one
representative tape pair (#757), not the band: read the medians.

After round one, with four controls, the engagement interval sat entirely on
the worse side. Four more controls moved it to cover zero. That is the
measurement-limits note doing its job, recorded so nobody reads a four-tape
dm4 interval as a verdict.

Mesh v2 differs from v1 in two places, both found by reading v1:

- Escape mode. v1 inherited dm4's seven pit-floor seats but refused every
  walk across their 15u of lava, so six seats had no walk out and two had no
  link out at all. A knocked-in bot standing nearest those could not route
  to the rocket-jump pad.
- Redundancy-aware eviction at the eight-slot cap. v1 dropped each node's
  longest links, which are exactly what a fewest-hop router leans on.

What the result says: on the map where navgen's graph is already nearly
exact, a graph derived from the clip hull in 4 seconds, with none of
navgen's link-repair passes, plays at parity. It has twice as many one-way
drops (126 against 66 descending past a step), routes in slightly fewer hops
(9.3 against 9.6 for pairs over 400u apart), and keeps no link the exact
walker refuses, against 65 of 700 in the shipped graph.

## Limits

- One map laddered. dm4 is the best-instrumented map in the lab and also the
  one whose shipped graph the mesh agrees with most (699 of 700 plain links
  pass), so it is the hardest place for a new graph to win.
- The graph inherits navgen's typed seats. A mesh-native jump, drop-arc and
  lift finder would remove that dependency and has not been written.
- The straight-fall drop model is stricter than play: dm4 n45 to n66 crosses
  about 40u of lava on momentum and killed nobody in 120 tapes.
- dm3 at its 244-seat budget covers 90 per cent of the mesh against the
  shipped graph's 95 per cent. Corner seats survive decimation at the
  expense of open-room coverage.
