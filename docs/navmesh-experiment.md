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
python tools/argus_navmesh_graph.py dm4 OUTDIR [--max-seats N] [--native-typed]
```

- Typed links (jump, rocket, sprint, teleporter, lift, swim, train) are
  inherited from the shipped graph WITH THEIR EXACT ENDPOINT SEATS, so every
  arc navgen verified survives and the experiment isolates one variable: how
  the walk graph is built. `--native-typed` inherits none of them and finds
  its own (see [Mesh-native typed links](#mesh-native-typed-links)).
- Control items get a seat. Coverage seats are placed roomiest first, so a
  seat stands in the middle of a space and a corridor only spends one where
  nothing covers it.
- A walk link is accepted only when a body following its straight line stays
  on the mesh, with world floor under its centre and no lava or slime at its
  feet. Each step may slide up to 16u sideways, as walkmove does along a
  wall. A link that starts in shallow lava may cross it (escape mode), so a
  knocked-in bot can still reach navgen's rocket-jump pad out of the pit.
- `--max-seats` builds dense and then removes a seat only when every
  in-neighbour still reaches every out-neighbour within three hops. Growing
  the radius instead (navgen's answer) left dm3 with 132 of 241 seats on the
  mainland, because sparse seats cannot see each other round corners. Since
  #790 the seats that cost no coverage go first (every candidate point they
  cover is covered by another seat), then the cheapest in uncovered points,
  with crowding breaking ties; crowding alone left dm3 at 249 seats covering
  77 per cent of the mesh.
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
  bots running off the upper walkways (z 135 to 280) and landing in the
  lake, most with no damage taken first, which the repair does not touch.
  They are in route mode, but `ar_mode` is 2 whenever a bot has a next
  waypoint, fighting included, so that does not mean they were following a
  route.
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
had; it is now seated (see [Seating dm3's south upper
area](#seating-dm3s-south-upper-area)). The reach gate's FAIL verdict is
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
| e1m8 | 3 / 3 | lava deaths | 2 | 1 | parity, P(improve) 0.78 | lava entries 10 to 7, from route mode 7 to 4; stalls rose (see below) |

Secondaries, control to repaired medians: dm4 engagements 74 to 78.5, goals 19
to 24, stalls 4.5 to 4; e1m7 engagements 98 to 97, stalls 3 to 1; dm3
engagements 16 to 14. No freezes in any of the 38 tapes. dm2, dm6, e1m1,
e1m5 and e1m6 carry one to six cut links each and were not laddered.

dm4 is the clean case. Its repair cut every route into the pit, and lava
entries across eight tapes fell from 40 to 24, entries from route mode (which
includes fighting with a route set) from 30 to 17, and deaths within 96u of a pit seat from 8 to 1. The gate still
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
the graph's doing: in the repaired arm bots still run off the upper walkways
at full speed and land in the lake, most with no damage taken
first. A drop-arc simulation clears navgen's drop links (only three of 42
land in lava at run speed, all starting from lava seats), so the falls come
from walking the upper floors, not from deliberate drops. That is a runtime
question and a separate piece of work.

## The air layer

The floor mesh says where a player can stand. A player who leaves a floor
keeps moving: at 320 u/s a 190u fall carries about 220u sideways. The air
layer flies a player origin through hull 1 off every ledge and records
where it lands.

```bash
python tools/argus_navmesh.py maps_local/e1m7.bsp --air --tapes runs/*e1m7*.log --air-png e1m7_air.png
```

- Ledge points sit 16u apart on every fragment edge with open air past it
  and no floor within a step. Each is flown off five ways: a 240 u/s walk,
  a 320 u/s run straight out and turned 30 degrees either side, and a
  running jump (velocity_z 270). A body still on a floor keeps running
  until the floor ends; a wall stops the motion into it axis by axis; the
  fall ends when the feet enter lava, slime or water, or at a floor.
- Gravity follows stock `world.qc`: 100 on e1m8, 800 everywhere else.
- Solid brush entities count: walls, doors, secret doors and plats, as
  bounding boxes at their deathmatch spawn positions (a DOOR_START_OPEN door
  one travel along its move direction, an untargeted plat one travel below
  its top, the rules `doors.qc` and `plats.qc` follow). The first version
  used the world hull alone and flew straight through e1m7's spawn pads and
  lava bridge deck, which the e1m7 investigation found under 9 of its 28
  run-offs. `--no-brushes` keeps the world-only answer for comparison.
  Trains move and are left out.
- Verdicts: danger (a straight run lands in lava or slime), risky (only a
  walk, a turned run or a jump does), momentum (lethal straight down, dry
  every way at speed, which is dm4's n45 class) and safe.

### Checked against tapes, with a base rate

A proximity count proved nothing on e1m7 once already, so the test runs on
two populations: lava and slime ENTRIES (the last second before the feet
go in) and every ordinary dry one-second window. Each counts as crossing a
ledge when one of its 0.5 s sample segments passes within 32u of a danger
point at a height within 48u.

| Map | Tapes | Entries | Entries crossing a danger ledge | Ordinary windows | Lift | Run-offs / jumps |
|---|---|---|---|---|---|---|
| e1m7 | 153 | 339 | 94.4% | 8.3% | 11.3x | 259 / 61 |
| dm4 | 866 | 2232 | 74.7% | 15.5% | 4.8x | 1367 / 300 |
| e1m8 | 16 | 51 | 49.0% | 12.5% | 3.9x | 24 / 1 |

Brushes sharpen e1m7 from 9.1x to 11.3x, mostly by removing false danger
points beside the pads and the bridge (dm4 has none; e1m8's six change no
tape figure). So nearly every e1m7 lava death is a bot leaving one of the
danger ledges ringing the lake. Almost all entries are falls (only 13 of
223 e1m7 entries in one sample were level walk-ins), and a one-segment test
explains only 41 per cent of them: at 160u between samples the bot has
usually left the ledge before the last dry sample.

The last column splits the danger-ledge entries into two classes the
ledge test alone cannot tell apart: run-offs, where a grounded bot walks
off at speed, and deliberate jumps, flagged by a `jump` or `rjump` event
in the same second (events carry no time of their own, so each takes the
time of the latest sample before it). Run-offs dominate on every map. The
e1m7 investigation reconstructed six tapes at the full frame rate and
found 28 run-offs and 15 jumps of 43 entries; the 2 Hz split here finds
19 per cent jumps, a different sample at a coarser resolution, and both
say run-offs are most of it. That investigation also found why: the
runtime hazard guard traces 280u down from 32 to 52u ahead, finds a dry
floor under those edges and approves the step, without allowing for the
run-off carrying the bot 200 to 240u past that floor. Runtime checks for
both classes, one judging a run-off's landing and one tracing a jump at the
feet, are in [#773](https://github.com/saworbit/argus/pull/773)
([e1m7 lava investigation](e1m7-lava-investigation.md)).

### What it does not support

The link-run check flies each descending plain link off its lip along the
link's line. On dm4 it calls n90 to n79 lethal at both 240 and 320 u/s, and
five more lethal at 320 only. The tapes disagree: lava entries pass n90's
lip in 0.23 per cent of cases against 0.81 per cent of ordinary windows,
and the five lips 0.7 against 2.2 per cent. Bots die leaving lethal ledges
OFF their links (fighting, deflecting, wandering), not by following a drop
link in, so the ledge verdicts are evidence and the link verdicts are not.

Limits: air control is not modelled (bots steer in flight only on typed
jump hops); real bots leave a ledge at any angle, not only straight out or
at 30 degrees; brushes are bounding boxes, which over-claim floor for an
irregular brush, and the verdicts above take doors and plats where they
spawn (the [time layer](#the-time-layer) grades the ledges beside each one
at every position); ledge points come from the world mesh, so the edges of a pad
or deck are not sampled as ledges themselves; the 32u and 48u crossing tolerances are judgement calls; a
faller's own pre-entry windows count as ordinary moves, which inflates the
base rate and makes every lift above conservative. e1m8 rests on 16 tapes.
`tools/test_navmesh_air.py` builds a platform beside a lava strip where a
straight drop lands dry, a walk and a run land in the lava and a running
jump clears it.

## The water layer

The floor mesh flags water floors wet and stops there, but a swimmer moves
through a volume, and dm3, e1m1, e1m2 and e1m4 all route through water.
`--audit` now ends with the swim volumes and a cross-check of the shipped
swim links (`swimlinks` in `src/argus_nav_<map>.qc.json`); `--no-water`
leaves them out.

```bash
python tools/argus_navmesh.py maps_local/e1m2.bsp --audit
```

- The volume is every player origin that hull 1 admits and hull 0 puts in
  water: waterlevel 2, where `Argus_Waterlevel` starts the swim block. Each
  hull-1 empty leaf inside a water area is split down the hull-0 tree at
  the origin and again 22 units above it, so every cell is exact and either
  breathable (the eyes clear the water, and `Argus_WaterMove` restores the
  air) or submerged. Slime and lava are not swum, as in navgen.
- Cells that share a face join into pools. An exit is a floor fragment
  that passes navgen 7d's lip rules: an origin 12 units below to 44 above
  the water surface, within the 48 units 7d leaves to the vault, and a
  hull-1 path that rises from the water, crosses the lip under the vault's
  apex (290 u/s, about 52 units at gravity 800) and steps down. A floor is
  dry by navgen's rule, water no higher than 8 units over the origin, so a
  wading floor with the waist just under is an exit too.
- The air budget assumes the bot's swim terminal speed, 300 u/s, against
  `air_finished = time + 12`: 3600 units with the eyes under. The dive is
  the farthest submerged point from air (a straight leg inside its own
  cell, portal centre to portal centre after that). The crossing is the
  longest swim with the eyes under that getting between two separate
  surfaces cannot avoid, which is the longest edge of a spanning tree over
  the pool's air regions, because a swimmer may surface in any of them on
  the way. A face onto dry player space counts as air for the dive.
- Pools that hull 1 closes on every side, and films or puddles with no
  exit whose every point is within 32 units of air, are counted on one
  line each rather than listed.
- A shipped swim link is confirmed when its seat lies in a pool and its exit
  seat on one of that pool's exits, and "walk from an exit" when the exit
  seat is reached on foot over the mesh's walk and drop portals from one,
  within navgen's 320 units.

| Map | Swim volumes listed | Cells | Exits | Longest dive | Longest crossing | Shipped swim links |
|---|---|---|---|---|---|---|
| dm3 | 1 | 252 | 15 | 351u, 1.2 s | 760u, 2.5 s | 1 confirmed, 3 walk from an exit |
| e1m2 | 3, and 1 sealed pocket | 545 | 52 | 108u, 0.4 s | 416u, 1.4 s | 8 of 8 confirmed |
| e1m1 | 1 | 140 | 15 | 43u, 0.1 s | none | 15 of 15 confirmed |
| e1m4 | 2, and 1 puddle | 1252 | 52 | 475u, 1.6 s | 676u, 2.3 s | 10 confirmed, 1 walk from an exit |

No pool on a map with a shipped graph asks for much more than a quarter of
the air: the longest, e1m4's deepest dive of 475 units, is 3.2 s there and
back. What the cross-check found:

- dm3's three walk-from-exit links (n111 to n99, n112 and n115 to n100)
  leave the trench for seats on the floor at z -184 behind a wall along the
  trench's west side. The way out to them is a gap in that wall whose sill
  (fragment f577, 40 units over the surface) the vault lands on; the seats
  are 255 to 317 units on foot from it. Each link's
  straight line crosses the wall beside the gap: navgen 7d samples the swim
  path every 24 units and steps over the wall's 16. The routes are real; the
  links point through the wall.
- e1m2's eight are all real, and two rules were needed to see it. n85 and
  n106 to n80 leave through the end of a channel under the court wall, which
  the nearest point of the water alone missed because it sat on the wall's
  corner, so every 8 units of the water's edge is tried. n168 and n183 to
  n175 land on a shore floor 4 units under the surface, which the mesh's
  wet flag refuses and navgen's dry rule accepts.

`tools/test_navmesh_layers.py` builds a pit pool (exact volume, the eye
split at 22 units, both banks as exits, a 130 unit dive) and the same pit
with a wall hanging into the water, whose two surfaces join only under it.

## The time layer

A plat or a door is a floor or a wall depending on when a body arrives:
e1m1's `*3` and dm2's `*31` and `*34` are floors only while parked. `--air`
now ends with a mover report; `--no-movers` leaves it out, and so does
`--no-brushes`.

- Every func_plat, func_door and func_train gets the positions stock QC
  moves it between, how long it holds each and when in one cycle it is
  there: `plats.qc` (speed 150, a plat untargeted rests at the bottom and
  holds its top 3 s), `doors.qc` (speed 100, `wait` 3 by default and never
  back for -1 or a key, a toggle door holding both ends, DOOR_START_OPEN
  spawning a travel away and closing when triggered), func_train (speed
  100, the min corner on each path_corner, each corner held for its `wait`
  or the 0.1 s think) and `SUB_CalcMove` (no move under 0.1 s). Each
  position carries its box, a wall while present, and its deck, the top
  face in origin space, a floor while present. func_door_secret stays where
  it was built: its two-stage move is not modelled.
- Each world-mesh ledge point within 64 units of a mover's travel in plan,
  and no more than a jump below it, is graded once per position, with every
  other mover at its spawn position (trains at their first corner): walled
  (the mover fills the step or the spot), bridged (its deck is a floor
  within a step past the edge), or the air layer's verdict. The deck's own
  free edges are graded at each position too.

```text
e1m1  *3 func_door, targeted: shut (spawn, rest); open (5.0 s of each 9.6 s cycle); 2.3 s each way at 100 u/s
        14 ledge points beside it: shut: bridged 6, safe 8 | open: safe 14
      *8 func_door, targeted: open (spawn, rest); shut (from 0.4 s on); 0.4 s each way at 600 u/s
        101 ledge points beside it: open: danger 91, risky 5, safe 5 | shut: bridged 30, danger 25, ...
dm2   *1 func_door, targeted: shut (spawn, rest); open (3.0 s of each 8.9 s cycle); 2.9 s each way at 100 u/s
        134 ledge points beside it: shut: bridged 16, safe 118 | open: bridged 11, danger 55, ...
      *31 func_plat, touch: bottom (spawn, rest); top (3.0 s of each 5.0 s cycle); 1.0 s each way at 150 u/s
        7 ledge points beside it: bottom: safe 7 | top: bridged 7
```

dm2 has 20 movers, 14 of which change a ledge verdict with their position;
e1m1 has 13 and 8, e1m2 25 and 3. The floor panels `*1` and `*2` slide apart
over dm2's lava: 55 and 38 danger ledges while open, none while shut, which
the spawn-position air layer cannot see. `tools/test_navmesh_layers.py`
builds a plat whose top stands level with a platform and whose bottom rests
in a lava strip: a ledge in front of it is bridged at the top, and at the
bottom a walk lands on the deck while a run overshoots it into the lava.

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

## Seating dm3's south upper area

The area is a spiral of 64u walkways around a pit whose floor, at z -42, is
the mainland. From the lower east walkway (n232, z 56) a corridor turns west
to n72; stairs climb to the z 152 walkway (n60, n46), which turns south down
a west strip (n36, n35) and east along a south strip (n47); stairs climb to
the z 264 walkways (n213, n64, n66, n230) and on to the top, a U at z 328
whose south arm runs onto the red armour's platform (n228, n52, n183). Every
leg after n72 was already in the graph. Two were missing and one was a lie:

| Corner | Shipped graph | Why |
|---|---|---|
| n232 to n72, z 56 | no link | the straight line clips the inside corner; beeline_ok and the mesh walker both refuse it |
| n46 to n36, z 152 | a jump n36 to n46 only | the same, and nothing walked back |
| n45 to n40, z 328 | a walk both ways | the origin crosses 119u of open air over a 346u drop; the mesh walker refuses it and the v3.96 mill refused its predecessor in the engine |

navgen gains `--seat-links`, which reads `src/argus_nav_dm3.seats.json`:
seats and walks by coordinates, appended after n243 and after the last link
call so no existing index or slot moves, plus cuts that remove a plain walk
only when its far end stays reachable without it. Each walk must pass
beeline_ok; each one here also passes the mesh walker, with SV_CheckBottom
holding at every 4u sample, which matters because bots move with walkmove.
Rerunning it, `--reanalyze-tactics` or `--repair-links` leaves the bytes
unchanged.

The first cut (v1) put one seat in the middle of each corner. A probe showed
it was not enough: bots switch to their next waypoint 48u early, and
`Argus_WalkArrivalReady` refuses that switch only for a wall, never for open
air. On a 64u walkway, a bot switching 48u short of the top elbow heads for
n40 on a line 8u inside the void. Three skill-1 tapes (sprints refused, so
the walk is the only way up) put a bot on the top walkway four times, and all
four fell off at that corner. v2 places each elbow toward the outer corner
and gives the top U three seats, chosen by simulating the early switch with
12u of lateral error so that the origin stays over floor in both directions:

| Seat | Origin | Role |
|---|---|---|
| n244 | 492 -528 56 | z 56 elbow, n232 to n72 |
| n245 | -236 -532 152 | z 152 elbow, n46 to n36 |
| n246 | -172 -532 328 | top north-west elbow, from n45 |
| n247 | -176 -660 328 | top west arm |
| n248 | -140 -720 328 | top south arm, to n228 |

Sixteen walks join them (each leg both ways) and the cut retires n45 to n40
in both directions. n40 keeps its links to n228; linking it to the new seats
would bring back the corner-cutting route through the router's
fewest-hop search.

Offline, the 22 seats rejoin the mainland, leaving only the pre-existing
three-seat pocket at n15, n16 and n24. Directed reach from the worst spawn
rises from 89 to 98 per cent over all edges and from 83 to 92 per cent
without rockets or sprints. The mesh audit is unchanged; its one finding,
n165 to n169, is a 224u ballistic drop. In the engine, `probelinks` walked
all 16 new legs twice each with no failure. An earlier sweep of all 52 plain
links in the area passed 35 and failed none, with 17 teleport failures while
ladder matches ran beside it.

### What the tapes show

Ladder: the repaired graph (be0d4f4, progs 42637d43) against v2 (progs
452bcd33), dm3, skill 2, 185 s, played rate. The primary, stall parity, was
registered before any tape. A second rule was fixed after the first two
waves and before any later tape: only listen-class tapes count. Those waves
ran six engines at once beside another session's ladder and an unrelated
Rust build, and 9 of their 12 tapes fell into the dedicated classes. Every
later tape ran as one matched pair at a time, and all held the listen class.

| Comparison | Tapes | Stalls median | IQM | Improvement 95% interval | P(improve) | Verdict |
|---|---|---|---|---|---|---|
| v2 against its paired controls | 5 / 5 | 13 to 18 | 14.3 to 19 | -26.0 to +6.3 | 0.34 | parity, sequential test says stop |
| v2 against all listen controls | 11 / 5 | 15 to 18 | 14.9 to 19 | -24.8 to +7.7 | 0.39 | parity, sequential test says stop |
| v1 (progs 5af60557) | 6 / 5 | 15.5 to 17 | 16 to 17 | -13.9 to +7.2 | 0.40 | parity, sequential test says stop |

The v2 point estimate leans worse. 39 of the 49 stalls in its worst tape sit
in the pre-existing cell at (-635 225 -16), which also leads the controls'
worst tapes and is far from the change. Paired medians: engagements 17 to
22, goals 25 to 25. No tape in either arm froze or lost a bot to lava.

Mechanism, ARGLOG samples, skill 2, 185 s:

| Arm | Tapes | Red armour chosen | Tapes with a bot in the area | Within 96u | On the platform |
|---|---|---|---|---|---|
| repaired graph (control) | 15 | 0 | 0 | 0 | 0 |
| v1 | 10 | 14 | 3 | 1 tape, 10 samples | 0 |
| v2 | 5 | 14 | 3 | 2 tapes, 28 samples | 0 |

"Within 96u" is the measure the 157-tape history used. It overcounts: the
z 264 walkway passes 90u from the item, 64u below it, and every bot it
counted here was on that walkway, jumping at the item from below. "On the platform" is an origin at z 316 or above,
within 96u horizontally.

Skill-1 diagnostics, 300 s, three tapes each: v1 put a bot on the top
walkway in four episodes and lost all four at the north-west corner. v2 put
a bot on the top in four episodes; one ran across the platform past the item
(its samples either side of it lie on a line 11u away), and three fell off
the top.

Why trips still fall short:

- The errand is long: 30 to 37 hops from the middle of the map, about 4300u,
  through dm3's central low area, where one bot spent its 20 s walking
  budget re-routing before it reached the new entry.
- Bots reach the top airborne. Routed steering jumps whenever the next seat
  is more than 24u up and within 80u, and the stairs from n55 to n229 rise
  48u, so every bot hops there and lands on the 64u walkway at 360 to 440
  u/s, where it cannot turn. A seat on every tread would not stop it: with a
  48u arrival radius the next seat is always two treads up. This is a
  runtime rule, not a graph defect.
- At skill 2 the router prefers the existing sprint from n241 to n52 across
  the top gap, three hops from n229 against seven on foot. In the one v1
  tape where a bot got there it never fired the sprint; it dithered on the
  stairs, then steered at the visible armour from the walkway below.
- The fixed navigation benchmark, `benchmarks/dm3_red_armour.json` (four
  tasks between the mainland and the armour seat), could not run. The harness
  placed the task bot but lost the console commands that remove the other
  bots and assign the goal, at both skills and with the engine alone. Its
  150 ms waits are shorter than this rig's command latency; `probelinks`
  retries for 1.8 s and works.

## Mesh-native typed links

[#790](https://github.com/saworbit/argus/issues/790), 2026-11-18. Offline
work only: nothing here is installed or laddered yet.

```bash
python tools/argus_navmesh_graph.py dm4 OUTDIR --native-typed
```

`--native-typed` inherits no typed link and needs no shipped graph (one is
read, when present, for its camera nodes and for the comparison figures).
`tools/argus_navmesh_typed.py` finds the links from the map, judged by the
rules the runtime executes them under:

- Jumps. A plain jump hop fires where a hull-0 point trace 32u ahead, from 4u
  above the origin to 40u below, finds no floor; only within 96u of the seat
  it was minted from (#665); only 48u or more short of the landing seat; and
  it leaves at 270 u/s on the line to the landing. A link stands when that
  launch, flown through hull 1 and the solid brush entities at spawn (the air
  layer's `fly`, at the map's gravity), touches no wall or ceiling, passes at
  least 2u over the far edge and lands dry on world floor from which the
  landing seat is a mesh walk. The approach speed follows navgen: the lowest
  staged speed whose whole -5 to +15 firing window passes, else the 250 to
  320 fallback window, else no link.
- Climbs. A jump hop to a seat more than a step up fires a standing jump within
  72u of it. A link stands when the rise is under the jump apex (navgen's 44u
  at gravity 800), the take-off has headroom, and the upper floor begins
  before any void and within those 72u.
- Drop arcs. A run off the line at the routed drop commit's 240 u/s and at
  320 must both land clean where the target is a walk, and the physics
  guard's straight-down probes past the lip must find floor, not a void or a
  liquid, or the bot never takes the step. Going down, an arc is tried before
  a jump. A straight-fall drop the walker accepts is refused when its 240 u/s
  run-off lands in lava or slime.
- Lifts, by navgen's 5b rules: travel is the `height` key or size_z - 8; the
  boarding pad is the nearest seat outside the swept column, at most 96u out,
  standing within 20u of the slab's seated top; the exit pad is the nearest
  seat to the top centre within 120u, height counted double.
- Teleporters: a seat on the floor inside each trigger (arriving sends the
  body away, so a link to it may cross its own trigger at any depth) and one
  where stock `teleport_touch` drops the body, the destination's origin + 27.
- Falls stop at DROPMAX 200 at gravity 800. Elsewhere the limit scales by
  800/g, because the fall-damage rule keys on landing speed (`velocity_z`
  below -650), and never passes the 280u the guard traces down for a floor.
- Before seating, every ledge point is flown off (a jump at 280 u/s, drops at
  240 and 320) and an arc that saves more than 1.5x its length plus 128u of
  mesh walking asks for a seat behind its launch and one past its landing.
  After the walk links, a jump or arc is kept only where the graph, with the
  teleporters and lifts in it, has no route within 1.5x the hop plus 128u.
  Hops are taken greedily, largest saving first, each joining the graph
  before the next is judged, and two per source at most.

Not found: rocket jumps, sprints, swims and trains, vertical func_door
platforms (navgen's 5b2) and virtual plat pads.

### Offline figures

Reach is `argus_reach.py`'s worst spawn over all edges and over ungated ones
(no rocket jumps or sprints), as a share of each graph's own nodes. Coverage
is the share of the mesh's candidate points within 112u of a seat, in a 36u
height band and in sight; reachable coverage counts only seats the worst spawn
reaches, so a graph that seats lava is not flattered or penalised for it. The
earlier "90 against 95 per cent" dm3 figures used a measure that was not
recorded; under this one the crowding-only decimation read 77 against 89.
Edicts follow navgen's budget: waypoints, live entities, nine world and
client slots and a reserve of 60, against 600.

Plain links exclude teleporters; the bracket counts those that descend past
an 18u step.

| Graph | Seats | Plain links (descending) | Typed by family | Worst reach, all / ungated | Coverage | Reachable coverage | Edicts |
|---|---|---|---|---|---|---|---|
| dm4 shipped | 137 | 697 (70) | jump 6, sprint 2, rocket 6, teleporter 5 | 128 (93%) / 128 (93%) | 99.9% | 99.0% | 263 |
| dm4 mesh, inherited typed | 124 | 658 (127) | as shipped, all 19 kept | 118 (95%) / 118 (95%) | 100% | 100% | 250 |
| dm4 mesh, native typed | 126 | 684 (127) | jump 3, teleporter 5 | 126 (100%) / 126 (100%) | 100% | 100% | 252 |
| dm3 shipped | 249 | 794 (112) | jump 22, sprint 10, rocket 5, lift 3, swim 4, teleporter 2 | 246 (98%) / 230 (92%) | 89.2% | 87.8% | 427 |
| dm3 mesh, inherited typed, 249 seats | 249 | 1151 (311) | as shipped | 249 (100%) / 229 (91%) | 95.5% | 95.5% | 427 |
| dm3 mesh, native typed (diagnostic) | 249 | 1137 (318), 4 of them arcs | jump 23, climb 2, lift 3, teleporter 2 | 164 (65%) / 164 (65%) | 93.6% | 64.3% | 427 |

dm4 needs no inherited link to match: the native graph reaches every seat from
every spawn, where the shipped graph's 93 per cent is its seven pit-floor
seats, which stand in lava, and two walkway seats at z -104 (n45, n50) it
cannot route to. Its three jumps cross the lava pit, where nothing walks or
drops: two from the big room's z -104 walkway to the z -296 floor, one from
the z -72 ledge to the walkway. navgen's own `--audit-jump-anchors` profiles
all three as gap jumps with no anchor violation. The finder does not mint the shipped east-walkway jumps: every
speed of each clips a wall in flight, the clean-arc rule refuses them, and the
native graph walks those areas instead. Of the walker's straight-fall drops,
three land in lava at the drop commit's 240 u/s and are refused; fifteen more
do so only at 320 and are kept, because the guard re-judges a run-off at the
bot's own speed (#773).

The dm3 ladder candidate is the inherited-typed graph at the shipped graph's
249 seats, so the arms differ in how the walk graph is built and seated, not
in size or edict cost. Coverage-first decimation closes the coverage gap
(77.1 per cent under crowding alone, 95.5 now, shipped 89.2). It inherits the
shipped graph's one anchor violation (n73 to n86, launch 100u from its seat).

The native dm3 graph is a diagnostic, not a candidate. Its six lift pads
stand 15 to 39u from navgen's on all three plats, at the same heights, as
expected when the same rules choose from the mesh's 16u candidate lattice
instead of navgen's samples. It cannot reach 85 seats:
25 on the west upper floor, which every graph enters only by rocket jump, and
60 in the east basement, which is entered by drops of more than 200u into the
pool (water breaks the fall) and left by swim exits, neither of which the
finder models. That is [#791](https://github.com/saworbit/argus/issues/791).

### Building a candidate arm

The candidate pairs, tactics baked by navgen's `--reanalyze-tactics`, are
outside the repository. To compile one, from the main checkout (Git Bash),
with `CAND` the candidate folder and `MAP` dm4 or dm3:

```bash
T=$TEMP/arm_$MAP; rm -rf "$T"; mkdir -p "$T/lq1"; cp -r src "$T/src"
cp "$CAND/argus_nav_$MAP.qc" "$T/src/argus_nav_$MAP.qc"
python tools/argus_build_stamp.py --src "$T/src" --write
(cd "$T/src" && /c/argus/tools/win/fteqcc/fteqw-2026-07-13/fteqcc64.exe)
mkdir -p engine/argus_m790$MAP
cp -r engine/argus/autoexec.cfg engine/argus/maps engine/argus/progs engine/argus_m790$MAP/
cp "$T/lq1/progs.dat" engine/argus_m790$MAP/progs.dat
```

Trust the "Compile finished" line, not fteqcc's exit code, and run the arm
with `ARGUS_GAME=argus_m790$MAP`. The control arm is the same steps without
the copy of the candidate QC. Compiled from this branch's `src/`, the dm4
native arm's progs MD5 was 64b9ac067dc203ea358646533cc85c4d and the dm3 arm's
ac7e48a00f6ec92c3df6821f65f9e28b.

### Ladder verdicts

Recorded 2026-11-18. dm4 and dm3, skill 2, 185 s, wall clock at the played
rate (`+sys_ticrate 0.0139`), five pairs a map launched together, every tape
in the listen tick class. The control is main at 89b9852 (build
9387e1e77737) with the shipped graphs; each candidate is the same source with
only `argus_nav_<map>.qc` swapped, built as above. Primary: stall parity, as
in the first mesh ladder. Gates and limits from `argus_lab.py skeptic`.

| Map | Arm | Tapes | Primary | Control median | Candidate median | Verdict |
|---|---|---|---|---|---|---|
| dm3 | mesh, inherited typed, 249 seats | 5 + 5 | stalls | 16 | 9 | parity on stalls; goals fell past their limit; not adopted |
| dm4 | mesh, native typed | 5 + 5 | stalls | 8 | 4 | parity on every gate |

Per tape, stalls ran 15, 21, 16, 11, 26 (dm3 control) against 4, 9, 13, 24, 9,
and 8, 8, 3, 4, 11 (dm4 control) against 12, 3, 4, 2, 4.

| Map | Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|---|
| dm3 | stalls | 17.8 | 11.8 | -6.0 | 24.6 | no detectable effect |
| dm3 | engages | 18.4 | 28.6 | +10.2 | 12.0 | no detectable effect |
| dm3 | goals | 23.2 | 12.2 | -11.0 | 10.1 | moved |
| dm3 | lava, freezes | 0, 0 | 0, 0 | 0 | | no change |
| dm4 | stalls | 6.8 | 5.0 | -1.8 | 10.1 | no detectable effect |
| dm4 | engages | 70.2 | 70.8 | +0.6 | 28.9 | no detectable effect |
| dm4 | lava | 3.0 | 1.0 | -2.0 | 2.7 | no detectable effect |
| dm4 | goals | 20.4 | 16.6 | -3.8 | 8.9 | no detectable effect |
| dm4 | freezes | 0 | 0 | 0 | 1.2 | no detectable effect |

**dm4.** The native-typed graph stands alone: it carries no inherited typed
link, reaches 100 per cent from its worst spawn against the shipped graph's
93, and holds parity on every gate. That meets the bar #790 set for it. It
is not proposed for shipping: parity is not a gain, and the shipped graph's
rocket and sprint links are prize routes the native finder does not mint.

**dm3.** The inherited-typed mesh graph holds stall parity but routed goal
completions fell by more than their limit, so it is not adopted. Post hoc,
not registered: battle-scan grabs rose from 21 to 43 over the five tapes and
engagements rose by 10 a tape, so part of the fall may be pickups taken in
fights rather than as planned goals. Telling those apart needs a pickup
count that does not care how the bot came to the item, registered before
any rerun.

Tapes: `runs/study_g790d3_{ctl,m790dm3}_r1` to `r5` and
`runs/study_g790d4_{ctl,m790dm4}_r1` to `r5` (machine-local).

## Limits

- Two maps laddered, five pairs each. dm4 is the best-instrumented map in the
  lab and also the one whose shipped graph the mesh agrees with most (699 of
  700 plain links pass), so it is the hardest place for a new graph to win.
- By default the graph inherits navgen's typed seats. `--native-typed` finds
  jumps, climbs, drop arcs, lifts and teleporters itself, but not rocket
  jumps, sprints, swims or trains, so it stands alone only on a map that
  needs none of them: dm4 does, dm3 does not
  ([#790](https://github.com/saworbit/argus/issues/790)).
- The mesh leaves out faces too steep to stand on (normal z at most 0.7,
  the FL_ONGROUND rule), and 36 shipped seats with dry feet stand on one:
  e1m8 25 (faces of 49 degrees), e1m3 5, e1m7 3, e1m2 2, lqdm2 1.
  [#788](https://github.com/saworbit/argus/issues/788) took them for floors
  the extractor lost; with the cut lowered the extractor finds a face under
  every one within 0.1u, so its clipping and walk-back are sound. The
  audit now splits its "seats on no mesh fragment" line into liquid seats
  the repair keeps, steep faces (with the distance to the nearest
  fragment), no world floor within 30u, seats inside the world, and dry
  seats with no fragment and no reason, which is 0 on every shipped graph.
  Whether a bot can hold a steep seat is a runtime question. dm4 has none,
  so the ladder above is unaffected.
- The water and time layers ([#791](https://github.com/saworbit/argus/issues/791))
  report; nothing reads them yet. The swim distances run portal centre to
  portal centre, and the swim speed is the assumed horizontal terminal
  speed: the swim block drives a bot up for air, or down to a submerged
  seat, at 120 u/s, so a vertical leg takes longer than its figure says.
  Movers are bounding boxes
  graded at the ends of their travel, never between, one mover at a time
  with the rest at spawn; func_door_secret is not moved. The main air layer
  verdicts still take movers at their spawn positions and leave trains out.
- `tools/test_navmesh_repair.py`, `tools/test_navmesh_air.py`,
  `tools/test_navmesh_layers.py` and `tools/test_navmesh_typed.py` run in
  fast CI.
- The straight-fall drop model is stricter than play: dm4 n45 to n66 crosses
  about 40u of lava on momentum and killed nobody in 120 tapes.
- dm3 at its 244-seat budget covered 90 per cent of the mesh against the
  shipped graph's 95 per cent, because crowding-only decimation kept corner
  seats at the expense of open-room coverage. Coverage-first decimation
  (#790) puts dm3 at 249 seats ahead of the shipped graph; see
  [Offline figures](#offline-figures).
