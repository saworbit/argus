# Changelog

Every entry is a shipped `progs.dat` build, tuned and gated by A/B
botmatch telemetry before install. Dates are build dates. The full
paper trail (ladder tapes, metric boundaries, forensics) lives in the
machine-local project brief; this is the distilled record. Lab
tooling (the Rust MCP server) versions independently; its own table
is in `tools/argus_mcp/README.md`.

## v3.95 (2026-08-28) - the tracker sweep

Four tracker issues in one laddered batch, each a filed defect from
the morning's project review (#16, #17, #18, #23).

Teleporter exit coast (#23): teleport_touch stamps teleport_time =
time + 0.7 and launches the player at 300 u/s down the destination's
v_forward. Engine physics honours the window for real clients; bot
physics re-derived wishvel on the very next frame and overwrote the
launch, halting the bot on the exit pad. Bots now coast the window -
no friction, no wish - with one hard lesson from the first ladder:
an UNGUARDED coast ran dm4 lava 6 (a pit-floor teleporter exit
launches toward the south lava boundary and the brink guard was
skipped with everything else). The shipped coast rides the launch
only while its heading probes safe 48u out; the moment the guard
vetoes it, or the launch is spent, steered physics takes back over.
dm6, the teleporter map, improved on the change: stalls 9 to 6,
hazard deflections 109 to 81 (exits no longer fight the guard at
the pad).

Goal-node caching (#16): Argus_NearestNode is an O(N) sweep with eye
traces and ran TWICE per failed route adoption, every pending frame,
for every bot. The goal's node now stamps once per item entity (the
ar_itemregion pattern - deathmatch item positions never move):
ar_goalnode / ar_gnodeset, resolved lazily, with a world result left
unstamped so a transiently blocked eye trace retries instead of
poisoning the item forever.

Lightning gun waterlevel guard (#18): the selector's in-liquid test
read watertype - the ORIGIN contents - which can sit empty while the
bot wades waist-deep with waterlevel 2, exactly the state where
W_FireLightning discharges every cell into the firer. The selector
now also demands waterlevel <= 1, mirroring the discharge test
itself.

ArgusCam plain text (#17): the camera's sprint strings carried
Q3-style caret colour codes, which protocol 15 clients render
literally. All thirteen strings are plain text now.

Ladder: dm4 parity on all seven gates after the coast guard
(ab_dm4_issuebatch2; the unguarded first run is ab_dm4_issuebatch1,
kept as the lesson), dm6 improved (ab_dm6_issuebatch1), dm2 improved
- stalls 22 to 14, routefails 0, boards live (ab_dm2_issuebatch1),
lqdm2 parity, dm3 45 s probe noise on single-digit counts (its
engage economy is issue #2, untouched by this batch).

Same session, tooling (no progs delta): argus_review.py now counts
the plain ARGUS tactical markers (shove, routecache adopt, hunch,
watch, prefire, sprintjump) exactly like the Rust parser (#25);
pak_extract.py accepts the documented positional extraction form
(#24); argus_navgen.py prints usage instead of a traceback when
called bare or with --help (#21); the MCP test suite recovers from
a poisoned ENGINE_TEST_LOCK so one engine-test failure cannot
cascade (#19).

## v3.94 (2026-08-28) - the wrist learns to drift

Issue #5, humanisation. Every session demo has read bots at
126-192 deg/s mean angular rate against the human's 57-80, with
2-4x the flick count - and the mechanism was the saccade re-roll:
the held aim offset STEPPED to a new value every 0.25-0.55 s and
the spring chased the step, a measured 2-4 extra flicks a second.
The SACCADE GLIDE ramps the old offset into the new one over
~0.15 s instead. Same magnitude semantics (personality, distance,
track time - the issue's red line, untouched), same destinations,
no step input. A human wrist drifts between corrections; it does
not teleport.

Ladder: improved on all seven gates on BOTH maps - dm4 glide1
(lava 4 parity, stalls 5 parity, engages 96, frags 31 - steadier
tracking hits more, the v3.77 lesson repeating), dm2 glide1
(stalls down 21%, everything else parity). The deg/s and flick
verdict belongs to the next session demo's bot entity-angle
stats against the v393b datum (126-192 dps / 224-271 flicks).

Also this block: the Romero pit-edge positioning issue (#13) was
CLOSED REFUTED after its third grave - the softest possible
slice (brink-aware strafe-side selection at the existing re-roll)
failed its ladder twice (lava 5 then 9, engages 84 then 64, the
'700 -800' corner at 22 deflections). dm4's boundary death
economy is load-bearing; the reactive 48u flip is the calibrated
equilibrium. Post-mortem comment above the lava flip. And the
dm2 puppet sweep (#14) reached 120 of ~1000 links: 20 convictions
persisted, almost all one family - west-tower descents whose
targets sit under deck overhangs.

## v3.93 (2026-08-28) - the sprint jump finally flies

Issue #4, run-up discipline, and the forensics found THREE stacked
reasons no sprint link ever fired live:

1. No run-up: the fire gate demands 310+ u/s within 15 degrees of
   the line INSIDE 48u of the seat, and the seat sits at the lip -
   a bot that walks to the seat and pivots can never rebuild that.
   Now the hop stages: a validated run-up point 60-150u behind the
   seat on the extended jump line (clear chest line, dry floor),
   walk there, then charge through the seat at the landing.
2. The 340u displacement guard: during the charge the steering
   target is the landing, 342-406u out - the guard re-planned every
   sprint hop at phase-2 start (the runup1 zero-fire tape). Charging
   sprint hops are exempt to 480, the way train pads earned their
   exemption in v3.46.
3. The brink guard: the speed-scaled probe vetoes the gap from
   39-52u out while the 8u launch lookahead cannot fire until the
   lip - the guard always won. An ALIGNED charge inside the fire
   envelope now owns its last 48u, and CheckBottom refusing the
   step there fires the jump rather than letting the
   FL_PARTIALGROUND retry walk the bot off the edge.

Then the first live firing died mid-air to a battle-grab bending
the wish 105 degrees off the flight line (air-accelerate bled 359
to 50 u/s by the apex). The FLIGHT LATCH holds the launch line for
the whole arc, whatever combat wants that frame; any grounded frame
clears it. Overshooting the seat unfired or drifting 48u+ off the
line drops the hop back to the line-up phase - never a full-speed
unanchored lip approach.

Every launch prints "ARGUS <name> sprintjump" (pseudo-event
`sprintjump` in briefs). The router gate drops skill 3 -> 2 with
the discipline in place (default skill-1 sessions still route
around, exactly like a mid player who knows the jump exists).

Ladder: dm4 runup3 parity on all seven gates with the FIRST
COMPLETED SPRINT CROSSING in project history (Carmack, n145->n146,
386 u/s held through an engage and a grab mid-flight); runup4
improved on all seven with four launches, two clean completions,
the failures being mid-air rocket knockback landing survivably in
the pit. dm2 improved / dm6 parity (their tapes predate the latch;
zero sprint flights occurred, so the code path is identical).
dm2/dm6 sprint seats see almost no traffic - the links are
load-bearing shortcuts (dm2 saves up to 18 hops) that fire when
routes actually cross them. dm4 baseline -> ab_dm4_runup4.

## v3.92 (2026-08-28) - lqdm2 reborn: the last map joins the modern era

Issue #12: the LibreQuake stand-in was the one map still on its
vendored graph (87% reach, never saw seats / stitches / knit /
slot clamp). Full modern regen: 214 nodes, 22 jump-up links, 8
knit stitches, a 15-node poisoned pocket stripped, edicts 331 of
600 - and directed reach 97% from every spawn, gated AND ungated
(tools/argus_reach.py prints the table). Ladder ab_lqdm2_rebirth1
improved on all seven gates: routefails 33 to ZERO, stalls 19 to
5, zero world deaths, zero freezes, spread 3, coverage parity.
Every map in the rotation now runs a modern graph and the last
four ladders across the project all ended at zero routefails.
Progs delta is the nav data only. lqdm2 baseline ->
ab_lqdm2_rebirth1.

## v3.91 (2026-08-28) - the spawn watch, and the issue tracker learns to close

The first GitHub-issues sweep. QC side is issue #3, the post-kill
spawn watch (the ambush reflex mre and Omicron both converged on):
a bot that scores a kill bets the victim respawns at the nearest
deathmatch pad to the death spot and biases its shopping 1.5x
toward items within 500u of that pad for 8 s (6 s cooldown, one
bet per episode). Same shopping-bias shape as the hunch, different
trigger; a live hunch (1.7x) still outranks it. Skill 1+ so
default sessions see it. Pad choice refuses cross-level bets
(|dz| >= 96) and lava/slime seats, so a walkway kill never parks
the killer on the pit lip. Plain `ARGUS <name> watch spawn`
console line, counted as pseudo-event `watch` by the lab.

Ladder: dm4 improved on all seven gates (lava 3, stalls 8 at
parity, engages 88, frags 27, spread 11, zero freezes,
ab_dm4_spawnwatch6; spawnwatch5 missed only the stall gate inside
the noise band). dm2 ran three tapes: mixed (coverage dip, never
repeated), regressed (stall spike to 51, never repeated), then
improved on all seven gates with the era-best engages 43, frags
12, spread 2, coverage 438 (ab_dm2_spawnwatch1-3). No failing
gate appeared twice; movement bands held everywhere.

Lab side (0.23, its own table): brief `acquisitions` figure (#6),
the ARGUS_ROOT auto-swap fallback for client-copy binaries (#7),
cartograph implication strings refreshed with a no-era-counts
regression test (#8), and the dm4 map-brief timeout (#9) closed
as not reproducible - warm and cold atlas rebuilds both return in
under a second on the fixed binary.

## v3.90 (2026-08-28) - Romero's cell number comes up

Shane's dm2 session (309 s, his first on the reborn graph): every
movement system live under human play - trains ridden, boards,
doors, lifts, 221 jumps, a rocket jump - and Shane won 15-10 over
Carmack. But Romero finished 0-and-9 with 67 stalls, 54 of them in
ONE cell: '2304 -2176', the SE grate room, steering at a node 128u
west he could never reach.

The loop that killed the quad-court pinch ran again, start to
finish, inside an hour: the puppet walked the accused link and
jammed eight units from Romero's exact cell (convicted BOTH
directions - a 48u void sits dead on the centre line, snaked
around by the beeline offsets at mint time); the verdict pass
reminted both directions as jump links; the ladder came back with
the grate-room count at ZERO, total stalls 45 to 32, routefails
still zero, Romero at 5 frags. Third chronic cell down to the same
mill: engine testifies, navgen re-types, bots inherit.

Also on the session tape: consumption healthy (42 grabs), pursuit
and retreat firing under human play, world deaths 3 in five
minutes. The residual bounded freeze class (one 7.7 s give-up wait
at the *34 armour deck) stands as filed.

## v3.89 (2026-08-28) - the second audit answered: dm6 reborn, Grok armed

The auditor's follow-up found the last stale copy and set the
queue; all of it ran:

- **Grok armed**: its MCP config points at ~/.grok/bin, which the
  auto-swap could never see - the week-old binary renamed aside,
  0.22 copied to the path its config names. (Grok respawned its
  server mid-operation, so its next restart completes the arm.)
- **dm2 consumption: diagnosed, not chased**. The economy is
  healthy - all three bots acquired the RL during the rebirth tape
  (8 switch events) and 17 battle-grabs took armour and health.
  The gl counter counts only CURRENT-GOAL touches by design (the
  v3.17 metric boundary), so on a contested map the goalers get
  invalidated mid-route by whoever eats the prize first - the 17
  same-prize re-picks are honest competition, and the low number
  is the instrument, not the bot. No code change, per the review.
- **dm6 reborn**: same recipe as dm2 - 11 guaranteed item seats,
  five jump stitches, the slot clamp - and the 20-node pocket
  shattered to 11 nodes in slivers. Reach 86% -> 94%. The ladder
  (run through the documented no-MCP fallback: direct engine plus
  argus_review): ZERO routefails (the debut ran 10), stalls 19 ->
  14, all frags positive at spread 2, 24 goals consumed, no
  freezes, no world deaths. Every map in the rotation now routes
  clean or near-clean.
- Baselines now cover all four maps at modern tapes (dm6 ->
  ab_dm6_rebirth1 added).

## v3.88 (2026-08-28) - the audit answered: dm2 reborn, the lab unstuck

An external review (run from disk while the MCP sat hung) called it
straight: "the bot itself is in a good place; the lab around it is
not." Every finding addressed, in its order:

- **Lab unstuck**: both stale argus-mcp processes killed, the 0.22
  staged binary (netclient + probelinks + auto-hop) swapped live,
  version strings corrected everywhere (MCP README claimed 0.18,
  root README 0.20; both now 0.22 with a table row).
- **Baselines moved at last**: dm3 -> ab_dm3_islet1, dm4 ->
  ab_dm4_gapsclosed4, dm2 -> ab_dm2_rebirth1. Lab verdicts measure
  the healed era instead of calling every modern match "regressed"
  against suicide-economy tapes.
- **The ninth-link amputation**: the late graph passes added links
  past the runtime's 8-slot budget and Argus_NavLink silently
  dropped the overflow (three nodes on dm3, every tape). A final
  slot clamp now runs after every adder - typed hops own their
  slots, jump links kept preferentially, and eviction is
  REDUNDANCY-AWARE (a length-only policy cut the tower spawn's
  reach from 85% to 74% by evicting a bridge; preferring
  well-served targets restored it). The json now tells the
  runtime's truth.
- **dm2 REBORN**: the project's worst graph regenerated through the
  full modern pipeline - item seats, jump stitches (16), knitting,
  poison prune. Worst spawn 4% -> 99%, one stranded node on the
  whole map. The ladder made history: ZERO routefails in 190
  seconds on the map that never ran below 68, zero freezes, zero
  lava. The v3.70 tele-orphan debt is paid.
- **NE moat-mega looked at, not blind-fixed**: the mega's seat and
  links are healthy (n161, 25u); the 87 bank deflections are
  orbit-lap noise around a clocked prize - the documented
  informational class. Filed as watch.
- **Puppet auto-hop**: the walk controller taps jump when progress
  stagnates, so the verifier now clears steps, lips and jump-typed
  links the way a human holding +jump does.

## v3.87 (2026-08-28) - item seats, jump stitches, and the apex vault

Three session reports, three root causes, one ladder:

- **"A bot was stuck in the RL area"** - the dm3 RL platform is a
  fine-graph ISLET: a 32-64u moat severs it from every neighbour,
  so decimation never kept a seat there (nearest node 241u away)
  and a spawn point sits ON the platform. Two navgen answers, both
  general: GUARANTEED CONTROL-ITEM SEATS (every weapon, armour,
  powerup and mega promotes its closest sample - the oldest
  idea-bank entry finally forced into code) and JUMP STITCHES in
  the knitting pass (a pocket ringed by a short void joins by a
  jump link when the gap fits the proven envelope - the pattern
  the puppet's verdicts taught). The RL seat now sits 8u from the
  weapon; nineteen jump stitches joined pockets that had resisted
  every criterion; dm3 reach hit 85% on every spawn, 85% UNGATED,
  poison prune down to one node. Goal completions nearly tripled.
- **"They still don't know how to hop up out of the water"** - the
  vault's trigger tested clearance at EYE height, and the trench
  banks rise ~40u above the surface - above a swimmer's eyes - so
  it could never fire where it mattered. What decides a vault is
  whether the lip sits under the JUMP APEX, so the probe moved
  there, and the vault grew to match (290 up, ~65u lip with the
  step). Longest submersion fell from 73 seconds to 13; swim
  churn from 370 events to 18. Lava stays excluded by contents.
- **"Can they use the lightning gun in the water?"** - verified,
  and working as designed: zero discharges on the tape (the
  selector's in-liquid guard holds), and the water kills Shane saw
  were bots lawfully beaming swimmers FROM DRY LAND - in vanilla
  Quake only the firer's own submersion discharges, and shafting
  someone in the pool from the bank is exactly correct play.

## v3.86 (2026-08-28) - the puppet grades the graph, and the pinch falls

The link-verification loop closed the same evening the client was
born, and its first case solved the campaign's worst cell. The
harness (`argus-mcp probelinks <map> [limit] [skip]`): spawn the
lab engine, connect the puppet, teleport it to each link's start
(dev impulse 216 reads the scratch cvars, both driven through the
console-inject tune path), walk the line, record the verdict by
endpoint coordinates in `src/argus_nav_<map>.probe.json`.

First sweeps: 22 of 22 ordinary dm3 links walked and passed - and
the quad-court pit-mouth pair FAILED with the puppet jammed at
literally '552 240 56', the coordinate every ladder tape had been
reporting. Plus one conviction nothing had noticed (n68->n78,
jamming at '552 502').

Then the twist that made the fix right instead of merely honest:
deleting the convicted links stranded 123 nodes - they were
LOAD-BEARING, which is exactly why bots jammed on them - and the
measured voids (80u, 160u) sit squarely in running-jump range. The
links were not dishonest, they were MISTYPED. navgen's verdict
pass (7g2c, after every minting stage) now remints a refuted walk
link whose centre-line void fits the proven jump envelope (the
dm4 lava crossing clears 192u) as a JUMP link, and only truly
unjumpable refusals die. Ladder: the '552 240' stall cluster is
GONE from the hotspot board for the first time since the campaign
began, jump events doubled (51 to 123 - bots fly the crossing),
zero deaths to the world, all seven gates through except the
era-baseline coverage artifact. dm4 probed at parity for the QC
line (impulse 216, developer-gated).

## v3.85 + lab 0.22 (2026-08-28) - the lab joins the game

The fourth instrument: the lab now connects to a running server as a
REAL NetQuake client (`argus-mcp client`). A Rust implementation of
the 1996 datagram protocol - control handshake, reliable/unreliable
channels with acks, the full signon dance, the svc vocabulary the
demo reader already speaks - proven live against the lab engine: it
connects, spawns, reads the scoreboard, streams the entity world at
server rate, and WALKS under `clc_move` control (first live test:
the puppet spawned on dm4's chronic walkway, of all places, and
moved on command). One discovery paid for the evening: WinQuake
binds its UDP socket to the hostname-resolved address, not
loopback - the client now mirrors that lookup.

What this opens, in value order: empirical link verification (drive
the puppet along minted links and OBSERVE whether the walking works
- the ground truth three failed v3.84 beeline criteria were
approximating), live full-rate observation without demo files, the
say channel (a client legally reads chat, which vanilla QC never
can), and scoreboard verification from a real client's seat. The
puppet connects as "labprobe" and v3.85's one QC line makes bots
treat it as an instrument, not a target - the same courtesy as the
spectator camera. Engine-gated integration test included; the two
engine-spawning tests now share a lock (a port race flaked once).

## v3.84 (2026-08-28) - the dm3 musing delivered, with its graveyard

Five directions from the dm3 challenge musing shipped, and four
attempts died honestly on their own ladders - the fullest
red-team block in the project's history:

- **Human-trace link mining** (navgen): every harvested session
  demo now nominates graph links. Snap the 69 Hz track to the
  graph, collect transitions no edge covers, verify each with the
  same referees as any link (beeline for walks, arc clearance for
  jump-ups), mint what passes. Three dm3 sessions yielded 24 links
  from 128 sightings - corridors the linker's candidate windows
  had simply missed, several bidirectional. Every future session
  on any map feeds it.
- **Jump-up links** (navgen + runtime): one-way drop lips whose
  rise a standing jump clears (under ~45u) get their reverse
  minted as a jump link; the runtime fires beside the lip. Six on
  dm3 plus one the human trace proved.
- **Region-aware shopping** (navgen + QC): the reachability
  condensation is baked into the nav data - mainland zero, each
  entry-stranded pocket its own id - and the goal picker refuses
  items in regions the bot provably cannot reach BEFORE any
  router call. dm3 routefails fell to 17-33 per match, the best
  figures on record; the match-start poison menus are now
  impossible rather than merely survivable.
- **Virtual plat pads** (navgen): when no static floor serves a
  plat's seated face, a synthetic seat goes ON the slab rest-top -
  Omicron's 1998 answer, waiting since the lift lab. Dormant on
  dm3 (real pads found); loaded for dm2's *31.
- **The graveyard**, recorded in code where each died: a box-aware
  hazard-probe rescue (both depths - deep laterals approved a
  razor shelf, step laterals turned dm4's wall-pin into
  wall-pressing); a +-16 beeline offset cap and two streak
  criteria (each amputated half of dm3's west wing - steering
  slack makes walkability GRADED, and no binary line-level rule
  separates "slides past" from "deflects forever"); and a
  same-level arrival widening (dm4's walkway bots cut corners a
  body early, 92 deflections at the '700 -800' lip). The
  quad-court pit-mouth keeps its tax and its name: it wants APEX
  SEATS - seat the elbow so routes bend around small voids - the
  next slice, precisely spec'd by three failures.

Ship ladders: dm4 healthy (stalls 8, engages 90, lava 4); dm3
structurally strongest ever (routefails 17, all frags positive,
spread 3, zero lava, lifts boarding) with the pinch as the one
elevated cell; dm2 and dm6 probes improved. Docs: the specs and
plans moved from docs/superpowers/ to docs/specs and docs/plans.

## v3.83 (2026-08-28) - the trapped verdict demands evidence

The match-start suicide came back and the tape convicted a different
mechanism than the one v3.82 fixed: Carmack spawned at a healthy
85%-reach spawn and routefailed four DIFFERENT local goals inside
three seconds - his nearest pickups all sit in pockets the graph
cannot route into - and the four-fail trapped rule executed him
without him taking a single step. The rule was written for pit
floors; it now demands physical evidence. First verdict: probation -
drop the shopping list and wander four seconds, then shop from new
ground. Only a second verdict that has not displaced 150 units is a
real pit and takes the exit. One carve-out its own ladder forced:
a bot hemmed in by lava or void on two-plus compass headings skips
probation and exits immediately - on dm4's lava-edged pit floor the
original verdict was right all along, and the probation wander
walked bots into the lava instead (lava 12 on the interim ladder,
back to 6 in band with the carve-out).

dm3: one trapped exit in the whole ladder match (the corridor era
ran thirty-nine), match opening clean. dm4: improved on all seven
gates. The deeper cause - the west wing and its neighbours hide
behind one-way drop lips, so their items poison a spawn bot's
opening menu - is measured, commented in navgen, and belongs to the
corridor campaign.

## v3.82 (2026-08-27) - the vault, the moat, and honest eyes

The v3.81 session reproduced every report on tape, and each decoded
into a mechanism:

- **The splash on repeat** ("they don't know how to jump out of the
  water back to land" - exactly right): dm3's east moat is wade-deep
  water with a bank lip taller than a step. Its seats are not
  underwater, so no swim links exist there, and the waterjump vault
  only fired on routed swim hops - bots swam against the bank
  splashing forever (982 swim events in a two-minute tape). The
  vault now fires in ANY water when the waist is blocked and the eye
  is clear, carries forward so the arc actually lands on the bank,
  and rate-limits so a failed try is not a splash machine-gun. The
  contents gate keeps lava excluded - which is all the old hop gate
  was really for.
- **The bot that dies at match start**: Carmack spawned beside a
  pocket the knitting had reported unhealable, routefailed his whole
  goal menu, and took the trapped suicide seconds in. New navgen
  pass: nodes that still cannot reach the mainland after knitting
  are route poison and are pruned - a bot standing there routes from
  the nearest surviving node and simply walks, which beats dying.
- **Still seen through the ring**: the acquisition gate was honest
  but tracking aimed at the live origin - a glimpse or a close pass
  bought three seconds of perfect tracking of a nearly invisible
  model, and the tape shows the gib with 22 seconds of ring left.
  Against a ringed target the aim error now triples (a floating
  pair of eyes is hard to put a rocket on) and lost sight holds the
  last seen position instead of tracking through walls.
- One leak caught by its own ladder: the v3.81 air-emergency scan
  ran in lava too and redirected the only-prayer swim-up sideways
  (lava 9 on the first dm4 ladder) - contents-gated to water, lava
  back in band.

Ladders: dm3 improved on all seven gates with stalls at baseline
parity for the first time in the campaign and an engagement record;
dm4 in band with the one-tape spread spike filed under Romero's
boundary watch.

## v3.81 (2026-08-27) - the ring, the air, and respect for the quad

Three fixes from the first human session on the healed dm3, each a
direct answer to a report:

- **"They can see you through the ring?"** They effectively could:
  the 2% glimpse chance against an invisible enemy was rolled per
  visibility check, and checks run several times a second, so the
  odds compounded into near-continuous tracking. The glimpse is now
  a clock - one roll per second - so a ringed player is genuinely
  unseen beyond close range. (Stock monsters never honoured the
  ring at all; Argus's courtesy just became real.)
- **"Do they understand they can drown?"** They drowned in place:
  the drive-for-air pins under ceilings and overhangs, and Romero
  reached 1 hp submerged in the session tape. With air nearly out
  and solid overhead, a bot now scans eight headings for one with
  clear water above and swims hard for the hole - nothing on the
  shopping list outranks breathing.
- **"They don't understand the powerup."** Two consequences wired
  in: a bot holding the quad hunts - it investigates any gunfire at
  full earshot for the whole thirty seconds instead of going
  shopping - and a bot facing a live quad or pentagram carrier
  doubles its retreat bar, breaking line of sight at mid stack
  instead of feeding the run (denial targeting unchanged: the
  carrier still draws every gun).

Ladders: dm4 improved on all seven gates (engages 90, stalls 8,
spread 2); dm3 at the era's best engagement figure with the frag
board positive and zero drownings. The ring fix is human-eyes
verification - take the ring and watch them lose you.

## v3.80 (2026-08-27) - the dm3 campaign: knitting and the dive

The worst graph in the project is structurally healed. dm3's spawns
reached 2-21% of the map (bots spawned inside directed sinks and
suicided out at a frag each - the trapped economy); the modern regen
plus three new navgen passes take every spawn to 70-83%, ungated
66-78%, and the 7h reach gate passes on dm3 for the first time.

- **Symmetric closure** (navgen 6b2): the Dijkstra linker's
  neighbour candidacy was asymmetric - dm3 shipped 55 near-level
  one-way links, dz 16 steps linked downhill only. Every one-way
  walk link whose reverse beeline verifies now gets the reverse.
- **Reachability knitting** (navgen 7g2): the 7g sink stitcher only
  healed strict sinks; pockets that leak into other dying pockets
  passed the test and stayed stranded. The general criterion is
  reachability itself: iterate until every node reaches the largest
  strongly-connected component and is reached from it, stitching one
  link per round - walk joins first, then drops, rocket jumps last
  (they are equipment-gated and invisible to RL-less bots), with
  ungated connectivity healed before gated.
- **The dive** (navgen + QC): dm3's deep basin sits 368u below its
  deck, floored in water, with twenty swim exits and no entry the
  runtime could execute - the advance gate closed at 220 below and
  the hazard guard read past-280 as bottomless, so the first knitted
  graph left bots pinned on the lip above a dark deep level for a
  whole tape. Three water-gated QC touches: the hazard probe treats
  a submerged probe-end as a pool, not a void (water breaks any fall
  in Quake); the advance gate closes on an underwater target at any
  depth; and a routed bot with an underwater node below it swims
  DOWN (air-gated at five seconds of margin - the up-only bob had
  made every submerged goal unreachable). dm4 parity ladder for the
  QC diff: improved on all seven gates.
- **Wall-clearance seat shift** (navgen 5a2): a waypoint seated
  against a wall face makes every arriving bot bury its point probe
  and deflect-dither at its own steering target; decimation seats
  with walls inside 24u now shift to a roomier neighbouring sample.
- **Costs rejected, recorded**: folding the learned stall cells into
  nav costs inflated 1074 fine edges and amputated arteries (stalls
  114, engagements 4) - the dm4 learncost lesson repeating on a
  tighter map. dm3's pinches are load-bearing corridors, not
  detourable cells.

dm3 ladder headline: routefails 540 to 29, trapped suicides 39 to 2,
deaths 56 to 9, the frag board positive with spread 0. Honest
residuals: stalls run above the old baseline (bots now actually walk
routes instead of routefail-looping at spawn), goal completions are
low, and two geometry chokes are filed - the quad-court pinch at
'552 240 56' and the east ditch at '1830 -112 -208'. dm3 is
structurally sound but not yet human-ready.

Red team: scratch regens with the new navgen beat every shipped
graph's reach - dm4 100%, dm6 93%, dm2 91%, lqdm2 92% - each
awaiting its own ladder session before re-ship. Lab: an abandoned
match could orphan a hung engine on the port (observed live);
match_ctrl now kills the child on every error path.

## v3.79 (2026-08-27) - the mind at skill 1

The hunch and the corner pre-fire move from skill 2 down to skill 1,
after a session review caught them firing zero times at the default
difficulty: the flagship cognition was invisible to the human it was
built for. Aim stays gentle at skill 1; the thinking does not. Also
in the record: Romero's chronic bottom-board is now explained (his
armour appetite parks him at the pit-edge red armour, where the
knockback economy collects him - ten lava deaths in one tape), and a
lava-escape scramble was tried and reverted the same hour, defeated
by geometry: dm4's lava sits eighty units below its lips and a vault
rises thirty.

## v3.78 (2026-08-27) - the trigger finger

The ambush reflex: while chasing a vanished foe, a rocket armed bot
fires one speculative rocket at the corner they disappeared behind.
The shot arrives where they were, and sometimes where they still
are. Once per chase, skill 2 and up, never the last rocket. Its dm4
ladder is the strongest botmatch on record (104 engagements, 29
frags, spread 2, zero abandons). The saccade aim measurement was
also honestly closed out: entity angle statistics cannot isolate
aim smoothness (byte quantisation plus patrol turns), so that
verdict belongs to human eyes.

## v3.75-v3.77 (2026-08-27) - the theory-of-mind block

Three shipped slices and one honest graveyard entry, each on its own
ladder with red-team probes between:

- **v3.75, the hunch**: when a foe breaks line of sight for good,
  the bot scores the map AS THEM (the classic QuakeC self-swap makes
  the utility scorer read the foe's health, guns and ammo), bets on
  the item they are most likely running for, and biases its own
  shopping toward the interception point for eight seconds.
  Engagements jumped by a third; on dm4 the bots' favourite bet is
  "he is going for the quad", which is simply correct.
- **v3.76, cognition-gated difficulty**: skill now scales the
  THINKING, not just the trigger finger. A warmup partner (skill 0)
  genuinely forgets you when you break sight, holds no grudges,
  ignores gunfire, never denies items, never shoves, and aims centre
  mass instead of at your feet - which also halved its lava rate.
  Red-teaming this slice exposed a graph defect the hunch had
  amplified: the dm4 quad ledge was a two-node directed sink (reach
  2 of 145 since the graph shipped), fixed by teaching navgen's sink
  stitcher that downward sinks escape by beeline-verified DROP
  links, not rocket jumps. The ledge now reaches 153 of 155.
- **v3.77, saccade aim**: human mis-aim is a stable offset that
  re-anchors a few times a second, not white noise rolled every
  frame. The bots' aim spring now tracks a steady point between
  saccades; the twitch measurement (bots at 128-176 deg/s against
  the human's 71-80) awaits its verdict from the next real session
  demo.
- **Range fighting: reverted with a post-mortem.** Per-weapon
  distance bands failed three ladders two different ways on dm4,
  where fights live at the pit boundary - free back-offs re-ran the
  2026-08-18 dead-retreat lava numbers, floor-probed back-offs
  traded lava for boundary stalls. Radial displacement pressure
  fights this map; a real exchange layer needs positioning
  awareness. Recorded in the combat code beside the other two
  retreat graves.

## v3.74 (2026-08-27) - the decision tape

Console `scratch1 1` (the vanilla scratch-cvar float pipe, settable
live through `tune`) makes every goal pick dump its per-class
utility board as an `ARGDBG` line - "why did it choose that" becomes
a grep instead of an hour of inference. One cvar read per pick when
off. Alongside it, the lab grew its idle-hands capabilities:
`argus-mcp soak` (unattended match loop with gated verdicts and hard
caps - wall clock, match count, bytes written, stop file) and
`argus-mcp cycle <map>` (one guarded learning cycle: learn hotspots,
regen, compile, probe; adopts only on an improved verdict, restores
byte for byte otherwise - its dm4 trial correctly self-rejected,
reconfirming that dm4's lava is combat, not routing). Demo analysis
went from summaries to answers: view angles and POV aim extracted,
per-player aim statistics (the first measurement separating human
mouse feel from bot servo feel: mean 80 deg/s vs 128-176), a
highlight reel with playdemo timestamps (first blood, multikills,
sprees, quad runs), and full-track JSON export. CI grew the Rust
suite and a headless LibreQuake stability smoke with the
directed-reach gate.

## Lab 0.21 (2026-08-27, no QC change) - the operational gaps

- Staleness self-awareness: the server detects a newer staged build
  at startup, auto-swaps it in for the next restart, and stamps a
  `lab_stale` banner on every response until then - stale briefs can
  no longer pose as current ones.
- Harvest-first, enforced: every match starter refuses to launch
  over an un-harvested play session (the harvester now moves its
  inputs, so leftovers are the signal, and the engine can no longer
  silently truncate an unarchived tape).
- One-call review: a tape's brief automatically folds in its paired
  demo - aim statistics, the highlight reel, full-rate tracks.
- `ship` and `baseline_set` tools close the loop's last manual
  steps (install everywhere with recorded MD5s; safe baseline
  pointer updates).
- `soak --parallel 2` runs two engines on separate ports, halving
  unattended ladder time.
- Session memory survives restarts; `see what=project` stops
  reciting fifty pak-only maps; compares involving human tapes are
  flagged as review-only.

## Stack sweep (2026-08-27, no QC change)

- Windows live tune was broken since lab 0.15, not merely
  unverified: after `AttachConsole` the inject wrote to the MCP's
  own redirected pipe instead of the child console. Fixed by opening
  `CONIN$` explicitly; a live-engine integration test (spawn the
  hidden dedicated child, inject `status`, require the output in
  the log) guards it permanently. Live `skill` and `scratch1`
  tuning on Windows work for the first time.
- `argus-mcp demo <stem>[:export]` reads demos from the CLI, no MCP
  client required.
- The plain `ARGUS shove` and `routecache adopt` console lines
  count as pseudo-events in briefs (previously invisible to every
  parser).
- The highlight reel files stock self-kill obituaries as `suicide`,
  separate from environment deaths.
- First demo-driven forensics on the chronic walkway corner: the
  freeze is a wall-pin at the z -232 / z -184 walkway junction -
  and it happened entirely outside the recording client's PVS, the
  demo caveat's first real bite. Filed for an instrumented session
  rather than fixed blind.

## Lab pipeline (2026-08-26 to 2026-08-27, no QC change)

- Demo ingest: every play session now records a `.dem`
  (`+record session <map>` in the launch command),
  `tools/harvest_session.py` pairs tape and demo in `runs/`, and the
  lab reads demos natively (`see what=demo`): protocol 15 parser,
  full-rate tracks (25-70 Hz vs the 1 Hz tape), named roster via the
  skin byte, projectiles in flight, coalesced kill feed.
- Directed-reach audit: `tools/argus_reach.py` runs navgen's reach
  gate against the shipped graphs (found dm3 at 2-21% from every
  spawn - the measured cause of its trapped economy).
- Brief intelligence: hotspots carry a geometric `cause` (door /
  plat column / lava edge) and `reach_pct` (routefail clusters in
  directed sinks are named as such); briefs cross-examine atlas
  reach labels against routing evidence; graph coverage with
  dormant-typed-link detection; per-prize item-clock tightness;
  human tracks split out of bot quality bands; a refused map spawn
  makes the whole tape flag itself.

## v3.73 (2026-08-26) - offensive displacement

Rocket-armed bots aim the splash short when the floor behind their
grounded target is lava or void: the knockback shoves the victim
over the brink. The bot-side version of the human signature move.

## v3.72 (2026-08-26) - retreat toward supplies

A retreating bot may now bend its cover fan toward a reachable
health or armour item (the only self-serve exit from retreat is a
recovered stack, and healing was gated off - the design could not
escape itself), and a cornered exit takes a lockout so it means
fight, not re-scan. Real clients now emit the detailed death event,
so the lab sees the human die.

## v3.71 (2026-08-21) - the Omicron homage

A hidden console word dresses the roster as its 1997 ancestors, in
tribute; every line is original. Undocumented by design.

## v3.70 (2026-08-21) - nav pullback and the reach gate

The regressed dm2 graph was reverted to the proven build, and navgen
gained a directed-reach gate (BFS from every spawn, loud warning
under 60%) so a structurally broken graph can never ship quietly
again.

## v3.69 (2026-08-21) - high ground and the trick-move family

Bots refuse to fight from directly under an elevated enemy, backing
out until the angle is honest. Navgen gained sprint-jump links (a
full-run arc model for gaps the conservative model refuses),
skill-gated at runtime.

## v3.68 (2026-08-21) - pad cooldown

A lift or train give-up cools that pad for 25 s so a bot re-shops on
the move instead of chaining statues under a busy elevator.

## v3.67 (2026-08-20) - the lip drop

A routed bot whose next node sits far below steps firmly off the lip
instead of teetering at walking pace (a 92-second dwell class,
dissolved).

## v3.66 (2026-08-20) - pre-positioning and human tracks

Bots arrive early at a pending major and orbit its spawn point until
it pops ("be early, not on time"). Real clients emit ARGLOG tracks,
so every analysis tool sees the human as one more trajectory.

## v3.65 (2026-08-20) - the lab gets teeth

Statue freezes became a hard A/B gate (with an under-fire measure),
and lift/train boarding success is accounted, after a visible defect
rode three green verdicts.

## v3.64 (2026-08-20) - the west dock

The west train pad was geometrically unboardable (a 13-unit gap
outside the gate) and pad waits ignored combat; both fixed - the
first west-to-east bridge ride on record.

## v3.59-v3.63 (2026-08-20) - the Omicron delivery block

Five slices from the Omicron bot review, each on its own ladder:
battle get item (grab a scored item mid-fight, shooting throughout),
hearing item pickups, predictive gap jump (simulate the arc, jump
only if the landing is dry), the dm3 corridor campaign with stair
seats and island discipline, and a shared route cache (a completed
route is adopted free by the next bot wanting the same goal).

## v3.58 (2026-08-20) - control circuits

High-value items read distance at 0.4x, so majors pull map-wide and
bots run circuits like seasoned players instead of grazing their
spawn quarter.

## v3.57 (2026-08-20) - retreat by geometry

The third retreat attempt shipped: cover is a wall between us, never
distance. Low-stack bots break the enemy's eye line while shooting,
and cornered means fight.

## v3.55-v3.56 (2026-08-20) - brink probe and boarding pads

The hazard probe scales with speed (closing the dm4 lava-band
concern), and navgen places plat boarding pads outside the swept
column - the first completed ride on dm2's main lift.

## v3.51-v3.53 (2026-08-19/20) - lifts, ears, and camera ghosts

Swept-column lift waits (step clear of the descending slab, stall
suppression), weapon-sound classification (what you hear and what
you can afford sets the hunt range), spectators become invisible to
perception, docked train cars board, seated slabs summon themselves.

## v3.48-v3.50 (2026-08-19) - clocks, dodges, and the finder fix

Item respawn clocks read from the engine's own think timers; missile
dodging (perpendicular sidestep, both sides floor-probed); and the
discovery that func_plat renames itself "plat" at spawn - two
runtime systems had been silently blind-parking. Bonus: the engine
maintains groundentity for bots, so riding detection became exact.

## v3.42-v3.47 (2026-08-19) - the dm2 grind

Grate floors walk (opposed-support bridging over decorative lava
channels), steep stairs read as stairs rather than void, remote
door buttons no longer freeze the presser, the cold shelf died (the
first 20 seconds of every match had shelved every goal on the map
since the GOAP build), fresh kill-drop packs outrank stale ones,
train boarding steers at the slab centre, and lift waits went
plat-state aware.

## v3.38-v3.41 (2026-08-19) - the away-window block

Combat memory (a recent foe is exempt from the FOV gate), corridor
mode nav sampling (healed dm2's utility-bait pocket), trains
relanded and ridden, and gunfire investigation - an unengaged bot
walks toward fresh shots.

## v3.36-v3.37 (2026-08-19) - doors and the roster

Typed door links plus the classname-rename fix that made them fire;
personalities keyed to roster slot so renaming bots never changes
how they play; netnames may contain spaces.

## v3.27-v3.35 (2026-08-18/19) - the organic player model and dm2 slices

Damped-spring aim (flick, overshoot, settle, tremor), simulated
hearing with soft FOV, nemesis vendettas, item denial, corner
pre-aim, chat over the real talk channel, pack valuation by
contents, water-sound root cause (the engine's own transition check,
fed bad state every frame), dm2's lava graph, touch and shoot-button
door handling.

## v3.24-v3.26 (2026-08-18) - the honesty build

Engine autoaim removed for bots (five weapons had been pixel-perfect
at every skill tier, silently), the ring of shadows honoured,
timelimit honoured headless, sink components stitched with verified
rocket-jump escapes, trapped bots take the deathmatch exit, and the
lesson that with real knockback bots shove each other into lava -
the honest economy.

## v3.20-v3.22 (2026-08-18) - water, lifts, and five fixes

Hull-0 water classification with typed swim-exit links (the dm3
trench healed; first lift rides in project history), rocket-jump
pads gained walk-in links, the typed-link slot budget, and a
five-item correctness list from review.

## v3.16-v3.19 (2026-08-17/18) - the goal planner era

Utility scoring plus GOAP precondition chaining replaced
nearest-item picking (personality appetites, claim shelves, the
SafeLine gate on direct seeking), then projectile leading, prize-only
rocket-jump pads, and Argus_HazardSteer's held-heading brink
deflection.

## v3.9-v3.15 (2026-08-17) - becoming personalities

Skill tiers 0-3 with per-slot personalities, pursuit through sight
breaks, the drop-lip advance, chat, waterjump, roster impulses
(FrikBot's numbers), and baked player-model skins so bot colours
survive GL renderers.

## v3.2-v3.8 (2026-08-14/17) - the masquerade hardening

Weapon pickup and range-aware selection, stock death animations and
backpacks, the fire button (three weapons had never actually fired),
spawn telefrags, the six-gap masquerade parity audit (healing,
knockback, drowning, falling damage, powerup expiry, intermission),
and the wedge-hunt navigation fixes ending in the displacement
guard.

## v3.1 (2026-08-14) - first contact

The first human playtest found bots blind to humans, a hard-crash
scoreboard, and 32 lava deaths per match on dm4. All three fixed the
same day: human-aware perception, dynamic scoreboard slots, and the
brink hazard guard (lava deaths 32 to 2). Everything since is the
telemetry loop doing its work.
