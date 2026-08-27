# Changelog

Every entry is a shipped `progs.dat` build, tuned and gated by A/B
botmatch telemetry before install. Dates are build dates. The full
paper trail (ladder tapes, metric boundaries, forensics) lives in the
machine-local project brief; this is the distilled record. Lab
tooling (the Rust MCP server) versions independently; its own table
is in `tools/argus_mcp/README.md`.

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
