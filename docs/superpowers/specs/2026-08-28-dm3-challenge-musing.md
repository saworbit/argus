# The dm3 challenge: research, analysis and directions

Status: musing, requested by Shane 2026-08-28 ("do some research,
analyse the map, and muse on solutions and innovative ways to solve
the dm3 challenge and make the bot better overall in the process").
Nothing here is shipped; each direction names its ladder and its
generalisation value. Evidence gathered this session with the
cartographer, the reach auditor, and a new demo-mining analysis.

## 1. What dm3 is

The Abandoned Base is the most-played competitive map in Quake
history - the map where "map control" was invented as a discipline.
Its control geography, confirmed against the entity lump:

- Red armour on a HIGH PERCH at '256 -704 304' (z 304, the map's
  crown; elevated flag from the cartographer).
- Pentagram at '1008 800 -296' beside the north water.
- Quad at '952 296 56' in the central court, behind the pinch.
- Lightning gun DEEP at '1544 -192 -416', in the flooded basement -
  the map's best close-range gun is guarded by water.
- THREE megahealths, one on an elevated west ledge ('-720 80 160').
- Two teleporters, three lifts, no doors.

The map rewards a player who runs a vertical circuit: armour high,
pent on time, quad through the pinch, LG via the water. Every prize
sits behind a vertical gate or a liquid one.

Historical calibration: Team Omicron hand-seated 236 waypoints on
dm3 in 1998 against 67-133 for every other id DM map - the original
author of bot navigation for this map already concluded it is the
densest seating problem in the set. Our current graph runs 255
seats, near their number but machine-placed.

## 2. Why it defeats Argus - the numbers

One weak island, NINETEEN strongly-connected components. Undirected,
the map is whole; directed, it is shattered. That single pair of
numbers is the whole dm3 story:

- 73 of 255 nodes are ENTRY-STRANDED: bots can route out of them
  but nothing routes in. The west wing, the RA platform, the SNG
  ledge and the NE tower all live in this set - the map's PRIZES
  are exactly its stranded real estate.
- The stranding mechanism is the one-way drop lip: walk-out
  beelines verify (a forward drop is legal), walk-in reverses fail
  (a climb past step height is not). The wings are moats-in-reverse.
- The legitimate return machinery is exactly what the graph cannot
  represent today:
  - All three func_plats are flagged by the cartographer: two have
    NO static floor within a step of the seated face (the navgen 5b
    virtual-pad gap, documented since the lift lab), and all three
    have only in-column static ledges (the *31 statue class).
    dm3's up-elevators are unboardable by graph construction.
  - The stairs that do exist are narrow or curved - the corridor
    class the 32u sampler misses and 5d only partly heals.
- Water: the LG basement and the pent approach are swim country.
  For a human the water is a highway (fast, safe, concealed); for
  the bot it has been a chore at best and a tar pit at worst. The
  dive + swim-down + general vault (v3.80-82) fixed survival;
  purposeful water ROUTING is still missing.
- The pinches: the quad-court gap between pillar corner and pit lip
  ('552 240 56') taxes every crossing with point-probe wall dither
  - the same class as dm4's '700 -800' corner, amplified because
  dm3 funnels its central traffic through one 60u throat.

## 3. The evidence experiment: the human is the cartographer

New analysis run this session, and it worked on the first try: take
Shane's 465 s recorded dm3 session, export the full-rate track
(69 Hz positions via the demo reader), snap every sample to the nav
graph, and report node transitions his feet made that the graph has
no edge for.

Results (repeat-count x, artifacts like respawn teleports filtered
by eye):

- Eight distinct walked ENTRANCES into "unreachable" pockets, most
  repeated: n138->n140 (x4, NE moat bank), n59->n65 (x3, south
  court), n234->n143 (x3, east wing), n16->n22 (x2, west wing).
- Twelve CLIMBS with no graph edge - including n73->n74 four times
  (z -264 to -104: the stacked plat ride) and n67->n69 four times
  (z 40 to 216: the upper tower stage). The human rode the exact
  plats the graph cannot board, four times each.
- The fast-rise map (sustained z gain over seconds) recovers the
  map's whole vertical machinery as actually used: the NE tower's
  three plat stages, the LG-pit exit ride at '192 -208'
  (z -416 to -175!), and the RA stair chain.

One 8-minute human session contains a near-complete correction set
for the graph's directed holes. This generalises to every map and
every future session: the demos are already recorded, harvested and
parseable - nothing new needs capturing.

## 4. Directions, ranked

### S1. Human-trace link mining (new, the innovative one)
A navgen input stage: read runs/demos/*.tracks.json for the map,
extract node-transition segments absent from the graph, verify each
candidate the same way any link is verified (beeline for walks, arc
for jumps, plat association for rides), and mint what passes. Seats
can also be PLACED from dense human traffic where no node exists
(the -224 east ditch shelf). Properties: offline, charter-clean,
self-improving with every session, and it captures exactly the
traversals a human considers natural. Risk: demo tracks include
deaths, knockback flights and teleports - candidates need the same
scepticism as any minted link (verify, never trust the trace alone).
Ladder: dm3 regen with mined links vs without.

### S2. Virtual plat pads (the 5b gap, now the critical path)
Omicron's 1998 answer, recorded in the capture review: seat the
plat's REST-TOP as a node (their PLATBOTTOM type) with the exit
typed above. Needs a runtime notion of a node with no static floor
- the bot stands ON the slab when seated, which the groundentity
work (v3.50) already detects. This is the single change that opens
dm3's designed circulation, and it retires the dm2 *31 residual in
the same stroke. Ladder: dm3 + dm2 + boards metric.

### S3. Jump-up links
Jump 270 apexes at ~45u. Mint the REVERSE of one-way drops whose
rise is jumpable (<= ~45 plus step), arc-verified like jump links.
Many west-wing lips qualify; it thins the one-way membrane without
any new runtime machinery (ar_hopjump exists).

### S4. Region-aware shopping (bake reachability into the graph)
navgen already computes the condensation; write a per-node REGION
CLASS into the nav data (a float field on existing waypoint
entities - zero extra edicts). PickGoal skips goals whose node the
bot's region provably cannot reach, before any router call. Kills
the poison-menu class outright on every map (the match-start
probation becomes a rarely-used backstop), and saves router frames.

### S5. Water as a highway
Cost water legs honestly in navgen (slow but safe), mint exits for
wade pools (the moat class), and let routes PREFER a swim when it
is the short way - the LG basement run and the pent approach are
where dm3 wants it. The survival layer (dive, swim-down, vault,
air emergency) shipped this week; this is the routing layer on top.

### S6. dm3 seat density
Omicron's 236 hand seats say dense; our edict estimate (466 of 600)
leaves ~80 nodes of headroom. A dm3-specific NODE_CAP raise plus
corridor mode would let decimation keep the stair seats it
currently trades away. Cheap experiment, measurable by reach.

### S7. Box-aware hazard probes (the pinch tax)
The guard probes points while the bot is a 32u box: at the
quad-court throat the probe buries in the pillar and vetoes a
walkable line. Probe the heading as a lateral PAIR (+-12u) and veto
only when both bury. Retires the chronic dither class on dm3 AND
dm4's '700 -800' corner - the oldest open item on the board.

### S8. The prize: dm3 as the control-play exam
None of the control machinery is wasted work - clocks, circuits,
pre-positioning, denial, the hunch - it is all built and waiting on
connectivity. When S1/S2 land, dm3 becomes the map where the bot's
whole economy finally plays the game the map was designed for. The
marvel test's true home was always going to be this map.

## 5. Suggested order

S2 (plat pads) and S1 (trace mining) attack the 19-SCC core and
carry the most generalisation; S4 is the cheap safety net that
makes every graph defect non-fatal; S3 and S7 are small and retire
old classes; S5 and S6 are tuning layers; S8 is the payoff session.
Each is one slice, one ladder, per the discipline.
