# dm2 campaign design (Claustrophobopolis)

Date: 2026-08-18
Status: agreed; slice 1 SHIPPED 2026-08-18 night in v3.25 (plan
docs/superpowers/plans/2026-08-18-dm2-lava-graph.md, all gates
green: world deaths 3 to 1, stalls 73 to 46, engages 11 to 55).
Slice 2 SHIPPED 2026-08-18 late night in v3.33 as pure runtime
(trace-detect the slab, walk touch-openers, button detour with
liftwait hold, shelve on shoot-only) - no navgen or BFS change was
needed since hull 1 never contained the doors. Gates green vs
ab_dm2_lava (stalls 37/45 vs 46, abandons 0/2, weapons 12/9 vs 7,
t6 doorway cluster gone; residual stalls are the '2664 -22 -34'
nook). Slice 3 (the shoot button *30) is next.

Findings after slice 1 (human tape shane_dm2_2026-08-18_v325b.log,
487 s): 72 of 128 stalls are one cluster at the t6 doors - slice 2's
case, now measured under human play. Two sinks survive slice 1
untouched and route to the corridor-sampling campaign, not this one:
the item_rockets pocket at '2232 -112 -160' (utility bait, no
arc-feasible RJ escape; 7g policy amended so item sinks TRY to
stitch) and the east upper deck holding the GL at '2056 -936 320'
(a 9-node reachability pocket; the west deck the n10-n9 lift serves
does not connect east). The trapped exit fired 25 times covering
the pockets. The quad is contested, not unreachable; contested
pickups inflate bot completion counts (touch-counter attribution
limit, noted for gate reading). v3.26 fixed a swim-bob sound
artifact found in this session - the first with-sound playtest.
Scope: dm2 playability. Vanilla QC charter applies in full.
Baseline build: v3.24 (55AF5FC872795DA6806E60A19F1AC12A).
Baseline tapes: ab_dm2_first.log (botmatch), shane_dm2_2026-08-18.log
(human, 493 s, "predictable and stuck a lot").

This spec supersedes the dm2 ordering in the campaign queue as written
before 2026-08-18 night. It records Shane's counter-analysis of the dm2
folklore, the verification of that analysis against the BSP and nav
json, and the agreed slice order. Every slice is its own A/B. Nothing
here is bundled, because dm3 taught that one slice can hide whether the
next one works (water hid the lift rides).

## Corrections of record

Each of these was verified on 2026-08-18 against maps_local/dm2.bsp
(entity lump) and src/argus_nav_dm2.qc.json (current nav).

1. Doors do not shatter the nav graph. The graph is 182 nodes in 180+2
   weak components. Hull 1 never contains func_door brushes (doors are
   entities, not world geometry), so navgen already walks every
   doorway. The strongly-connected splits are one-way drops and typed
   hops, not locked rooms.
2. The liquid is lava, not water. Hull-0 classification of waypoint
   seats: 151 empty, 31 lava, 0 water. A 64u world grid found 214 lava
   cells and 4 water cells. The "pool" coordinates in ab_dm2_first.log
   are dry. The "swim then death world" lines are lava at z about -35
   beside the trains, which the dm4 z < -300 lava filter cannot see.
3. Bots route through closed doors and pin. Waypoint n171 sits at
   '2785 -55 -72', inside the closed t6 button-only door pair (*12 and
   *13, opened by button *15). The router sees the gap as empty floor
   (hull 1 again); walkmove hits the door entity at runtime. This is
   the t6 stall cluster.
4. Trains sit on the lava lip. Three func_train shuttles: *11 (first
   corner t4), *23 (t12), *28 (t16). The deaths at '1937 -1650 -34'
   are mover-adjacent lava, not a pool vault.
5. Node indices shift across regens. The chronic nook is the place
   '2664 -22 -34', not "node 164"; n164 in the current json is at
   [2689, -1911, 120]. Specs and telemetry notes name places by
   coordinate, never by node index.

## Entity inventory (verified)

Doors, 15 total. Button-operated: t1 (*1, *4, *5; buttons *3 and *8),
t3 (*7, *9; buttons *32 and *33), t6 (*12, *13; button *15), t9 (*20;
button *22), t10 (*16; button *17), t11 (*18; button *19), t18 (*29;
button *30). Untargeted (touch-open or start-open): *2, *21, *26.
t15 (*25) is opened by a trigger, not a button.

Buttons, 9 total, one shootable: *30 has health 1 and opens t18. All
others are touch buttons, which already fire for bots through the
classname "player" masquerade.

Trains: 3 (*11, *23, *28) over 6 path_corners.

Nav as shipped: 182 nodes, 6 rocket-jump links, 2 lift links, 0 swim
links (correctly: there is nothing to swim).

## Slice order

One slice, one A/B, judged against ab_dm2_first.log with dm2 gates,
never against the dm4 parity tape. 120 s skill 2 probes while
iterating; a 190 s match for any ship decision.

1. Lava graph (planned, see the slice 1 plan). Navgen classifies every
   waypoint seat against hull 0 at torso height and drops lava and
   slime seats; walk-link verification refuses paths that step through
   lava; the analyzer classifies deaths by actual contents instead of
   the dm4 z threshold. Argus_MoveHazard stays as the runtime
   backstop. Success: world deaths fall and classify as lava at their
   true height, the 31 lava seats are gone, and the graph does not
   shatter (weak components stay near 180+2).
2. Typed door links (LANDED 2026-08-19 as v3.35). The lift pattern: navgen intersects each walk
   link with door AABBs and emits a door-typed link. Mode-2 advance:
   door open, walk; touch-open, walk in (the masquerade fires it);
   button-only, detour to the recorded button, wait for STATE_TOP,
   then cross. BFS treats door links as legal. Design notes: the typed
   masks are bits only, so a door hop needs per-slot door and button
   references (an_door0..7 entity fields in the an_l0..l7 pattern, or
   runtime resolution by tracing the blocked gap); record
   button-to-door distance at navgen time and split the cases, an
   adjacent button is a local advance detour, a remote button is a
   planner errand (fold into Argus_PickGoal only if the local detour
   proves insufficient). Success: the t6 stall cluster disappears,
   routefails drop, bots appear on both sides of t1, t3 and t6.
3. The shootable button. *30 (health 1) opens t18. When the current
   hop is door-typed for t18 and the button is visible within 600u,
   arm a hitscan weapon and put one shot into it. Success: t18
   crossings happen without the stall signature.
4. Trains. Typed ride with the lift shape: park on the boarding pad,
   friction-only hold, let the func_train move, advance at the far
   path_corner. Deliberately after slice 1 so a missed ride is a
   reroute, not a death. Success: ride events appear, mover-adjacent
   lava deaths do not rise.
5. Swim and waterjump. Expected nil (4 water cells on the whole map).
   Only touched if slices 1-4 leave a liquid gap.
6. The nook at '2664 -22 -34'. Re-examine after slice 1, since
   hull-0-aware seating may reshape it. Candidate fixes are a jump
   link back up the ledge or a general seating rule. Never a
   map-hardcoded exclusion.
7. Plat *34 approach steering at '2544 -992'. The raised slab leaves
   the shaft reading as void, so the brink guard fights the boarding
   approach. Candidate: physics brink-guard exemption while ar_hoplift
   is set and the bot is within about 120u of the boarding pad. Must
   be A/B'd on dm3 as well, since dm3 is the proven lift map and this
   touches its runtime.

Regen note: any dm2 regen from now on picks up pad walk-ins (7a3),
the link budget (7e), escape stitches (7f) and sink escapes (7g), so
the six dm2 RJ links become approachable for the first time. Expect
nav-shape drift in the first slice-1 A/B for that reason alone.

## Rejected approaches

- Compile-time solid doors. Faking door brushes into the clip hull
  would manufacture islands and hide the real defect, which is
  runtime collision with an entity the router cannot see.
- A dm2 swim regen as the first slice. The classifier already ran;
  swimlinks is correctly empty; the liquid is lava.
- Reusing the dm4 lava z filter. dm2's killing lava is at z about
  -35. Classification must come from contents, not a height.
- Map-hardcoded sample exclusions in navgen. The tool stays
  map-agnostic; dm2 must not grow special cases inside it.
- A default fourth bot in Argus_Init for dm2. impulse 100 already
  adds one at will, and a roster change silently shifts every
  engagement and frag baseline. If big maps want a four-bot default,
  that is its own measured change.
- Door approach A (recover after the stall). It waits for the failure
  it is meant to prevent and leaks stalls by design.
- Door approach C first (full GOAP door atoms). Right long-term, but
  it needs the router to report which doors a path uses, and it is
  more than one A/B. Approach B ships first; C only if B's local
  button detour proves too weak for remote buttons.

## Measurement

- Compare slices against ab_dm2_first.log and, for feel, the human
  tape shane_dm2_2026-08-18.log. The dm4 parity tape is the wrong
  ruler for this map.
- Death classification: python analyze_match.py gains contents-based
  lava classification in slice 1. The MCP's Rust bars keep the old
  behaviour until Shane's next rebuild; slice verdicts come from the
  python side until then.
- Campaign-end targets (directional, from the tapes): stalls under 25
  per 190 s botmatch (ab_dm2_first ran 73), routefails under 30 (was
  112), weapon pickups above 25 per 8 minutes (human match saw 11).
  Per-slice gates are listed with each slice above.
