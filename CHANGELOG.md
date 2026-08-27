# Changelog

Every entry is a shipped `progs.dat` build, tuned and gated by A/B
botmatch telemetry before install. Dates are build dates. The full
paper trail (ladder tapes, metric boundaries, forensics) lives in the
machine-local project brief; this is the distilled record. Lab
tooling (the Rust MCP server) versions independently; its own table
is in `tools/argus_mcp/README.md`.

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
