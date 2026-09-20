# Changelog

Every entry is a shipped `progs.dat` build, tuned and gated by A/B
botmatch telemetry before install. Dates are build dates. The full
paper trail (ladder tapes, metric boundaries, forensics) lives in the
machine-local project brief; this is the distilled record. Lab
tooling (the Rust MCP server) versions independently; its own table
is in `tools/argus_mcp/README.md`.

## Unreleased

**CI NO LONGER MOVES TO A NEW UBUNTU IMAGE WITHOUT A DECISION** (#450). The
repository invariants, Rust lab, FTEQCC compile and headless LibreQuake smoke
now pin Ubuntu 24.04 instead of following `ubuntu-latest` onto Ubuntu 26 on
October 19, 2026. A regression test keeps all four blocking jobs explicit, and
the pin has a documented April 2027 review date.

**DIRECT BLOB WRITES CAN NO LONGER HIDE CRLF FROM THE REPOSITORY** (#448).
Text files declare an explicit LF policy, while Windows batch and command files
retain CRLF checkouts. The invariant battery reads Git's committed-blob EOL
metadata, so an API upload cannot look clean merely because checkout normalized
the worktree. Four blobs found by the new check were normalized without content
changes.

**STRICT CLIPPY IS NOW A REAL LAB PREFLIGHT** (#446). The existing Rust lint
backlog is clear, the repository pins Rust 1.95 with Clippy and rustfmt, and the
fast workflow rejects warnings across every library, binary and test target.
Intentional allowances stay local to match plumbing and serialized process
tests, with the reason beside each one. The full parallel preflight also found
and fixed graph-revision fixtures colliding under Windows' coarse clock.

**THE MILL NOW SPEAKS IN GRAPH REVISIONS AND PROBE VERDICTS** (#419). Nav
JSON revisions have stable content-hash ids, typed links, generator inputs and
Git provenance through MCP resources. The read-only `mill` tool compares two
revisions and reports only added, removed or type-changed links that exist in
at least one source graph, with matching probe evidence. Asking about a link
absent from both graphs fails closed. Git history supplies old bytes, so this
adds no graph or verdict format.

**OLD MCP CONFIGS CAN MOVE TO THE STABLE INSTALL SAFELY** (#437). A migration
command updates only an Argus entry with the retired Cargo release path,
verifies the installed binary and preserves the existing environment and
timeouts. It handles Codex and Grok TOML plus Claude-compatible JSON, then
states that the client must restart.

**COMPARE NOW REJECTS AN EMPTY CANDIDATE LIST** (#441). The CLI returns a
clear usage error instead of indexing an empty parsed list and panicking.

**SCALED VERDICTS KEEP THE SOURCE TAPE DURATION** (#440). Count metrics still
normalize to the candidate median, but coverage now reads every original tape
length and stays ungated if any source was short. Non-finite durations and
durations at or below one second return a clear Mixed verdict.

**BASELINE BANDS NOW COMPARE EQUAL-LENGTH COUNTS** (#435). Experiment and
explicit CLI band comparisons normalize both arms to the candidate median
duration before judging count metrics. Coverage remains unscaled and stays
ungated on short tapes.

**BOTS REMEMBER ONE WASTED CROSSING INTO THE NEXT LIFE** (#418). A death on a
long routed item run opens a short next-life refusal window. A nearby fight or
materially nearer live stack can keep the bot local, and `ARGEVT lifeveto`
records the decision once. Reaching the item, direct pickups, and expired
memories do not block later goals.

**CI NOW RUNS THE CURRENT MCP CLI TEST INSTEAD OF SKIPPING IT** (#433).
The lab job builds the checkout's `argus-mcp` binary before the Python CLI
suite, and that suite fails in CI if the source binary is missing. The stable
installed-binary smoke remains optional.

**THE PYTHON CLI TEST NO LONGER RUNS A STALE LAB INSTALL** (#431). Source CLI
coverage now uses only the current checkout build, while the stable install has
its own startup smoke test.

**CARGO CLEAN NO LONGER REMOVES THE CONFIGURED LAB SERVER** (#429). The client
example now uses Cargo's installed binary outside `target`, while locked Windows
updates keep using the existing staged swap.

**THE LAB CRATE IS BACK UNDER RUSTFMT** (#424). Existing Rust sources are
formatted consistently, and CI now rejects new formatting drift.

**THE LAB ADVERTISES ITS CARGO PACKAGE VERSION** (#426). Server metadata and
instructions now read the version set in `Cargo.toml`, and project docs point to
that single source instead of copying a current version number.

**THE HUMAN SCORECARD TEST NOW CLOSES ITS INPUT FILE** (#423).
Python development mode no longer reports a `ResourceWarning` after the
duplicate append check.

**NEW MAPS MUST PASS REACH AND THE ENGINE MILL BEFORE REGISTRATION** (#417).
The add-a-map path now checks every deathmatch spawn against every live pickup
and requires graph-specific walk/drop and jump probe evidence before it changes
`progs.src` or the dispatcher. Probe verdicts name the exact graph they walked,
community BSPs are staged into the engine only for the probe, and refused jump
links remain visible in the generated JSON and debug PNG. The CLI and GUI show
the same `playable` or `experimental` verdict.

**NAVGEN REFUSES OVER-BUDGET GRAPHS** (#420). Every generation now reports
waypoints, live BSP entities, world and client slots, the measured runtime
reserve, total use, slack, and an `ok`, `tight`, or `over-budget` verdict.
Over-budget output exits before `--register` can change the build. The MCP and
GUI surface the same verdict.

**LAB TICK CLASSIFICATION NOW TOLERATES PLAYED-RATE SAMPLING JITTER** (#412).
The listen-rate cutoff moved from 0.5105 to 0.5135 seconds, above repeated
same-runner measurements and below the calibrated 0.5145-second legacy
dedicated cluster. Matching Rust and Python regression tests cover values on
both sides of the old cutoff and retain the older 19 Hz classification.

**NAV GRAPHS NOW CARRY STATIC EXPOSURE AND COVER DATA** (#368).
Navgen traces every waypoint pair through the exact BSP world tree, counts the
other nodes visible from each point, and finds the nearest hidden node reachable
through ordinary walk links. The generated QC and JSON store the exposure rank,
hidden target, and first hop. Retreat steering tries that hop only after live
line-of-sight and hazard checks, then falls back to the established heading fan.
Cartograph map briefs and node inspection surface the new annotations. A
topology-preserving `--reanalyze-tactics` mode refreshed all eleven shipped
graphs without changing a node, link, movement type, region, or trace input.

The implementation follows the Source SDK navigation pattern of doing expensive
static visibility and hiding analysis offline while treating it as tactical
guidance, not a live player-visibility guarantee. Exact-length dm4 and dm2 tape
sets kept the preregistered engagement metric in band, with stalls, goals,
freezes, and coverage also at parity or better. The lab excluded faster-rate
tapes from the listen-rate verdict under its existing tick-class guard.

**BOTS SHARE SHORT-LIVED ROUTE WARNINGS FOR PLACES THAT JUST FAILED** (#366).
Two consecutive stalls, non-player deaths, stuck movers and timed-out doors add
one of four expiring avoid spots. Shopping floods, cached routes and active
walk paths reject segments that move closer to a live spot, while jump, drop,
teleport and mover links only reject unsafe destinations because they cannot
turn midway. A bot already inside a mark can always move away. Exact main-build
controls across three 30-second tapes per map put median dm2 stalls from 9 to 3
and dm4 stalls from 1 to 0; median goals held at 1 and 4 respectively, coverage
rose on both maps, and neither map produced a freeze. The chronic dm2 hold at
`(1424,-988,47)` fell from 16 stalls in its control tape to 3 in the matching
candidate tape.

**ITEM GOALS NOW USE THE GRAPH PATH THE BOT WILL WALK** (#355).
Before shopping, one frame-sliced, bot-specific flood visits the reachable
graph using the router's jump, rocket-jump, sprint and keyed-door gates.
`Argus_PickGoal` measures every item from that one route tree, including the
bot-to-start and goal-node-to-item offsets, and refuses unreachable items
before they enter the menu. The winning parent chain becomes the route, so
selection and execution cannot disagree and no second search is needed. The
existing 0.4x major-item circuit factor stays in place.

THE CACHE SHAPE IN #354 WAS TESTED AND REJECTED. A nearest-item field for
each broad item class gave one item a route distance while its sibling items
still used crow-flight distance. That made the score space inconsistent and
does not match Quake 3's per-item travel-time query. Against exact main-build
controls, the prototype reduced dm2 completed goals from 8/4 to 4/3 and
coverage from 347/367 to 296/311. The shipped design keeps one comparable
distance space for every item instead.

FINAL FULL-LENGTH TAPES USED EXACT MAIN-BUILD CONTROLS AT THE SAME LISTEN
RATE. On dm2, goals moved 8 to 10, engagements 25 to 32 and coverage 347 to
341; stalls 9 to 21 and lava deaths 0 to 2 remained inside the measured
control bands, with zero freezes and route failures down from 8 to 1. On dm3,
goals moved 0 to 3, engagements 17 to 18 and coverage 272 to 291; stalls 13
to 15 stayed in band, with zero lava deaths, freezes and route failures.
Three additional 30-second tapes on each map exercised the final
router-contention cleanup without a VM error, lava death or freeze. Modern
FTEQCC compiled with the six pre-existing warnings and installed matching
E77BCB3A4DC3C3E97F73DE2088BC60D9 binaries in all three locations.

**PROTECTIVE POWERUPS NOW OPEN ONLY THE STEP THEY ACTUALLY PROTECT** (#364).
A biosuit with more than three seconds left may admit a slime step; a live
Pentagram may admit slime or lava. The gate checks both the inventory bit and
the real expiry timer, keeps Quad carriers out of lava, and requires the
liquid-covered floor to be within one normal step of current support. Deep
pools stay refused because protection could expire before the bot finds an
exit. Only the final movement step can open. `Argus_SafeLine`, route planning
and speculative hazard steering remain strict. A throttled `hazardpass` event
records actual liquid entry.

DIRECTED ENGINE PROOF covered all six field cases: live suit returned
slime-only protection, live Pentagram returned both liquids, the exact
three-second boundary and each half-state returned neither, and Pentagram
plus Quad still refused lava. Three no-powerup dm4 tapes
`hazard364_verify_dm41` through `hazard364_verify_dm43` pre-registered lava
deaths as the only convicting metric and received release parity against four
matching-rate controls. The median was one lava death inside the zero-to-eight
control band, and no `hazardpass` marker fired. A no-powerup dm6 tape also
emitted no marker and recorded no lava death. The compiled binary is
FA4D050B8029B15A63B444A82B2EF60D in all three installs.

**COMBAT NOW READS THE FIGHT IT IS ACTUALLY IN** (#360, #361, #362,
#383). Reaper's effective-stack range signal returns as a bounded comfort
band: weak bots yield the splash preference and take a wider circle tangent,
stacked bots press, and Quad compresses the band. The signal never creates
radial backpedal, and the established Rocket Launcher self-damage and
Lightning Gun liquid gates remain hard boundaries. At cognition skill 0.5+
the last visibly held enemy weapon is classified as melee, direct fire,
splash, or beam and shapes circle angle, high-ground back-out and ordinary
retreat hysteresis. Quad/Pent opponents still use the established fixed 70/90
retreat bars regardless of weapon.

TARGET MOTION IS NOW PART OF HUMAN ERROR, NOT PERFECT INFORMATION. Observed
displacement is sampled on the existing 0.25-0.55 second saccade clock,
normalized to a fixed 0.05 second horizon, capped against teleports, scaled by
the aim-specific skill value, and held through the same 0.15 second glide.
Stationary targets add exactly zero and consume no extra random draw. Sight
loss glides the held offset to zero without sampling the hidden target, while
reacquisition clears both glide endpoints so a new target inherits nothing.
That keeps dedicated and played-rate sessions on the same magnitude scale
without turning movement into per-frame aim noise.

KILLZONE'S SECONDARY THREAT IS A SOFT POSITIONING PREFERENCE. The nearest
other visible player can win a tie between otherwise legal strafe/back-out
headings, or between primary-covered retreat headings. It never enters missile
dodge/body-clearance legality and never makes secondary cover mandatory. Plain
`ARGUS threatmove` and `ARGUS crossfire` markers expose the decision branches.
Bot death rows append `thirdparty` only when another player lands the kill
inside the active visible-fight window; the Rust tape parser carries that into
`third_party_deaths`, including compact CSV/headline output, while old rows
remain valid.

MATCHED EVIDENCE USED THE PRE-CHANGE BINARY FROM THE LAB BACKUP. These tapes
predate the final target-lifetime and telemetry fixes, so they establish the
candidate's safety envelope rather than final branch counts. On dm4,
185-second control/candidate tapes were release-gate parity: engagements
97 to 83 stayed in band, lava deaths improved 5 to 2, stalls were 10 to 12,
K/D spread stayed 10, and both arms recorded one freeze. Self-splash deaths
moved from 3 to 1. On dm2, matched 90-second tapes were parity: engagements
18 to 24, stalls 11 to 11, zero world/lava deaths and zero freezes in both
arms; self-splash moved from 0 to 2. The two-map aggregate stayed 3 to 3, so
the stack policy redistributed self-splash without increasing it.

THE EXACT SHIPPED BINARY THEN RAN CLEAN TWO-MAP SMOKES. On hash
BC538F4359114EE3C76CCDED7A4EB15B, 45-second dm4 and dm2 tapes had no VM,
edict, protocol or stray-client errors. dm4 recorded 20 range, 2 high-ground
and 6 retreat threat decisions, one world/lava death and 2 stalls; dm2
recorded 9 range and 3 retreat decisions, zero world/lava deaths and 10
stalls. Neither short tape happened to take a crossfire or third-party-death
branch; the matched candidate tapes had exercised both, while the final
purple review verified their fallback and attribution paths directly.

PLAYED-RATE CALIBRATION USED THE SAME BINARY AND THE OPT-IN `scratch1 362`
trace. A 35-second dedicated run produced 58 samples and a hidden local
listen-server run produced 96. Moving samples had mean normalized target
steps 10.08u versus 9.37u and mean held offsets 9.39u versus 8.13u; maximum
offset-to-step gain was 1.63 versus 1.72, inside the skill-2 bound in both.
All 62 stationary samples produced exact zero and neither run breached the
40u normalized-step cap. A loss-edge interpolation check at old-glide
fractions 0, 0.5 and 1 produced zero discontinuity in all three cases. Modern
FTEQCC compiled with the six pre-existing warnings, all 190 Rust unit tests
plus both integration tests passed, and all 52 Python project tests passed.

**ONE CONTINUOUS SKILL NOW BELONGS TO EACH BOT** (#358, #381, #359).
The stock `skill` cvar remains the roster baseline, but every bot now stores
its own effective 0..3 value. The four shipped integer rows are exact anchor
points and aim error, reaction time, tracking rate and spring gains interpolate
between them, so `skill 1.4` is no longer treated as skill 3. Live impulses
106 through 109 cycle a -1..+1 offset for roster slots 0 through 3, apply it
without a respawn, and the match card prints each effective value.

THE COMBAT GATES USE THAT SAME VALUE. Projectile lead, foot splash, combat
memory, item denial, hunches and speculative prefire form one ordered ladder
instead of reading the global cvar independently. Sprint-link eligibility is
per bot too. Discrete weapons now release the trigger between shots and add a
small skill-scaled delay beyond the stock refire clock; nailguns and lightning
use bounded bursts so releasing `button0` never aborts their damage frame
chains. This follows Quake 3's characteristic thresholds without changing the
capabilities present at the established integer skill-1 tier.

REAPER'S SKILL-1 EQUALISER RETURNS AS AN EXPLICIT OPT-IN. `impulse 110`
enables it only for deathmatches with a connected human and only at the
default global skill. A player kill raises the defeated bot; a bot kill lowers
that bot. Random steps anneal from 0.8 to 0.4 to 0.15 as results accumulate,
clamp the effective value to 0..3, and emit
`ARGUS <name> skilldrift <skill>`. Bot-only matches and co-op can never move
the dial, and disabling or re-enabling the option clears adaptive history.

LIVE PROOF USED THE FINAL BUILD. A real protocol-15 client drove impulse 106,
which logged Carmack at effective skill 1.5, then enabled adaptation and fought
the roster. Joe Rogan's human kill moved him independently to skill 0.7. The
same session forced Carmack from lightning to super shotgun and then recorded
his buckshot kill, followed later by a nailgun-to-rocket switch and rocket kill:
the former continuous-fire animation no longer blocks or impersonates the new
weapon. A remote client could not retune the roster, including after seven
attempts to raise the old `serverflags` bit through impulse 11; the same command
worked after the operator explicitly armed `scratch1 147`. Final-binary dm4 and
dm2 botmatches ran for 65 seconds without a VM or protocol error: dm4 recorded
1 stall, 11 deaths and 2 lava deaths; dm2 recorded 17 stalls, 5 deaths and no
lava deaths. These short two-map tapes are smoke evidence, not a formal
full-length A/B verdict.
Lab-only hygiene found by the verification pass: the MDE formula in
`stats.rs` is prose, not runnable Rust, so it is now inline code instead of a
doctest and the full Cargo suite can run through documentation tests.

**EACH PLAIN JUMP LINK NOW CARRIES THE SPEED OF ITS OWN APPROACH**
(#365). The graph already knew that one link crossed a short gap, one
needed a full arc, and another was only a climb, but runtime threw that
knowledge away and used the same 250 u/s launch floor for all of them.
Navgen now identifies the first physical unsupported span inside the
coarse link, resolves its actual standable takeoff and landing origins,
derives a target speed from that span and the descending jump root, and
adds a bounded cushion from the dry landing runway. Every whole-speed
point in the runtime's target-5 through target+15 launch window must
keep at least two units of arc margin and pass player-hull collision
sampling before navgen records the target, worst margin and runway.
Links it cannot certify keep the old direct gate. The original link's
collision verdict still belongs to the engine-proven graph. This does
not recreate the refused point-trace simulator from #356 in runtime.

The sprint run-up is now the typed-jump run-up. A positive-speed plain
link walks back to a validated point on the extended jump line, charges
through its launch seat with acceleration capped at the link target,
and fires inside a -5/+15 u/s window. A zero-speed climb or auto-hop
keeps the old direct 250 u/s gate. Launches expose the contract as
`ARGUS <name> jumpapproach <target> actual <speed>`; sprint links retain
their 316 u/s target and existing flight latch.

ALL ELEVEN SHIPPED GRAPHS WERE REPROFILED WITHOUT A REGEN: 183 jump
links, 37 certified staged gaps and 146 climb, auto-hop or fallback
links. The new
`--reprofile-jumps` mode refuses mismatched QC/JSON pairs, rewrites only
the existing jump calls and `jumpapproach` metadata, and exits before
full-map sampling. Nodes, links, link types, slots, regions, trace
inputs, camera nodes and teleporters compare unchanged against HEAD on
all eleven maps.

THE EVIDENCE BOUNDARY IS RECORDED. The first three 45 s control and
candidate tapes on both dm4 and dm2 stayed inside their control bands,
but two candidate tapes were classified at a different tick rate, so
the lab correctly voided a formal A/B verdict. Random goal play did not
reliably select and complete a positive-speed link. A developer-only
directed override then exercised the final state machine at 135 u/s:
dm4 launched at 142.1 and 138.0 u/s, and dm2 walked to a run-up,
charged, and launched at 137.9 u/s. The override is inactive unless
explicitly enabled through the developer and scratch cvars.
The remaining deterministic evidence is the topology-preserving
reprofile suite, positive-gap fixture, nav invariant suite, and a clean
vanilla-QC compile.

**A TYPED JUMP NOW LAUNCHES FROM ITS OWN SEAT, ON ITS OWN LINE, AND
STEERS THE FLIGHT** (#357, and the launch half of #365). The sprint
hop has had a launch discipline since v3.69: anchored within 48 units
of the seat the arc was verified from, aligned within 15 degrees of
the line, and above 310 u/s. A plain jump hop had none of it. It fired
on one condition, that a jump hop was armed and the ledge ran out one
step ahead at 250 or more, and it flew along whatever the velocity
happened to be doing.

MEASURED, ON dm4, 120 SECONDS: of 53 typed launches, **52 were nowhere
near the link's own seat**, and every one of those was 45 to 75 degrees
off the line to its own landing node. A bot crossing any lip at speed
with a jump hop armed fired a typed launch there. Now the launch needs
to be within 96 units of the source node, and it turns onto the line to
the landing, up to 60 degrees, before it goes. Reaper faces the ideal
yaw before it commits, for the same reason. Beyond either bar the bot
is not taking that link right now: the launch refuses, falls through to
the brink guard, deflects, and comes round again.

AND THE FLIGHT IS STEERED. Quake 3 hands every weapon jump and walk-off
to `BotAirControl`; Argus fired and then rode. While airborne on a plain
jump or a rocket jump the wish direction now points at the landing node,
so `Argus_AirAccelerate` spends its 30 u/s budget along the arc instead
of wherever ordinary steering happened to point. Two guards: a
correction that ends against a wall is refused, and the control is
released on grounding. The sprint flight latch is untouched, because an
arc with no margin wants its heading frozen and that is already the
right answer for it. Marker `ARGUS <name> aircontrol`, throttled.

LADDERED ON BOTH MAPS WITH JUMP TRAFFIC, parity on every gate. dm4
three tapes against four: stalls 6.5 to 5, engages 80.5 to 79, lava 3.5
to 3 with the sequential test rejecting any effect of 3 or more,
freezes 0 to 0, coverage 358 to 375. dm2 five a side: stalls 44 to 44,
engages 33 to 26, lava 0 to 0, freezes 1 to 1. **The anchor does not
starve the jump family**, which was the risk: jump events hold at a
median of 27 on dm4 and 94 on dm2, unchanged either side. Air control
fires 6 to 14 times a tape on dm4 and 1 to 4 on dm2.

CLOSED NOT PLANNED IN THE SAME PASS: the runtime arc check (#356). It
was built, found four defects in itself, and still refused 16 of 17
anchored and aimed launches on a map whose links the engine crossed 16
of 18 times. Quake 3 can ask the engine for a client bounding-box trace;
this vanilla QuakeC path has point traces. Another runtime fan would be
another approximation allowed to disable engine-proven links. Collision
truth therefore stays in the graph mill, while #365 carries the useful
approach data into runtime without a second collision referee.

**THE GROUND PATH LEARNS TO SLIDE ALONG A WALL** (#380). A masquerade
parity gap of the v3.6 family, and the last piece of the stock player
movement model the bots did not have. Stock `SV_FlyMove` clips the
velocity into every plane it hits and continues along the clipped
vector; the bot ground path had no equivalent, and a blocked walkmove
ungrounded so the engine's flymove would do the sliding instead. On a
blocked step the horizontal velocity is now projected into the
blocking plane and the move retried along it. Only then, if that
fails too, does the bot unground. Nothing that succeeds today
changes: the new step sits between the failure and the unground, and
runs after the `FL_PARTIALGROUND` retry so the grate-floor behaviour
is untouched.

THE PROBE IS THE WHOLE STORY. The first cut traced one line forward
from the origin and was measured before it was believed: on dm2, 120
seconds, three bots, it was reached on 4947 blocked steps and found a
wall on 137 of them. walkmove moves a 32-wide box and a wall that
stops the box is usually met by a corner, which a centre line misses.
A fan across the front of the bbox, three traces at waist height plus
a knee trace for the sliver between walkmove's 18 unit step-up and
the origin at floor plus 24, finds a wall in two thirds of blocked
steps and **slides 1489 times in the same 120 seconds**. The knee
trace only runs when the cheap three miss.

LADDERED ON BOTH CHRONIC-CELL MAPS, parity on every gate.
dm4 three tapes against a four-tape band: stalls 6.5 to 6, engages
80.5 to 88 (95 per cent CI +2 to +20, the only interval that clears
zero), lava 3.5 to 4 with the sequential test rejecting any effect of
3 or more, freezes 0 to 0. dm2 five tapes a side: stalls 44 to 57,
engages 33 to 33, lava 0 to 0, freezes 1 to 1, every interval
covering zero. The frame rate does not move. `tick_gap_mean` is
0.506 on every tape either side, which is the measurement that
settles the cost of up to four traces on a blocked step.

AND THE ISSUE'S OWN PREDICTIONS ARE REFUSED. It named the two chronic
cells and average speed as the judge. The cells do not move: dm4's
walkway corner runs 4, 6, 8, 8 deflections across the control tapes
and 8, 5, 4 across the candidates, and dm2's south-east grate room
runs 0 to 10 stalls on control tapes and 0 to 13 on candidates, which
is the same spread the control produces on byte-identical code.
Average speed moves on dm4 only, IQM 214.2 to 222.2 with all three
candidate tapes above the control median, and is flat on dm2, 182.8
to 185.6 inside a CV of 9 per cent. A bot spends very little of its
time pressed diagonally into a wall, so the speed bonus is real and
small rather than the 41 per cent the geometry allows. This ships as
what it is: a correctness restoration at parity, in the shape the
body block shipped in.

**RESPONSE SHAPING, AND A PRICE ON THE TOOL SURFACE** (#371). Lab
only: no QC, no nav data, no bot behaves differently. MCP 0.29.

CSV WHERE THE ANSWER IS A TABLE. `brief_run` and `compare_runs` take
`format=csv`. Every large part of a brief is rows - the per-bot table,
the hotspots, the kill matrix, the event counts - and a table as JSON
repeats every field name on every row. Measured on
`ab_dm4_deadlink1`: **1765 bytes as CSV against 3464 as compact JSON**,
and more again against the pretty JSON the server actually sends. The
test asserts the measurement rather than the slogan: the first cut
asserted "under half" and the real number is 51 per cent, so the bar
is 55 and the phrase everywhere is "about half". JSON stays the
default, because an agent that wants one field should not have to
parse a table.

THE LIVE TAIL PAGINATES ON SIZE. `since_line` is still the cursor and
the cut is now a 6 KB budget with a 120 line ceiling. Record count is
the wrong unit when records vary, and telemetry lines vary by five
times: `ARGEVT Reap jump` is sixteen characters and an ARGLOG sample
is over a hundred, so a flat eighty-line cut returned between 1.5 and
8 KB depending on what the match happened to be doing - and a busy
match, the one you are polling because something is happening,
returned the most. It always returns at least one line, because a
budget that can return nothing is a poll loop that never advances.

THE TOOL SURFACE NOW HAS A PRICE ON IT, and the suite holds a bound.
Every exposed tool is paid for on every request through its schema,
called or not. **39 tools, 18,816 bytes, about 4,700 tokens a
request.** The bound sits just above that on purpose; a bound three
times the actual is not a bound.

AND THE MEASUREMENT REFUSED THE THIRD PART OF THE ISSUE, which asked
to retire the parked extras. They cost `bot_simulate_match` 619 bytes,
`bot_capture_pov_frame` 334 and `rcon_exec` 253: 1,206 bytes, six per
cent, against breaking the table in `docs/mcp_quake_dev_spec.md` that
records all five as shipped. Two of the three work. The third answers
"no, and here is why, use these instead", which is worth 334 bytes
when the alternative is an agent inventing a screenshot pipeline.

Meanwhile **581 of those bytes were sitting in `corpus`**, the tool
added one version earlier to save tokens, which was the single most
expensive schema in the server because it explained each of its views
twice. Trimming it saved more than retiring `rcon_exec` and
`bot_capture_pov_frame` together. The cheaper saving was in the newest
code rather than the oldest, which is not where the issue pointed and
is why it is worth measuring before cutting. The refusal is recorded
on the spec document so its table stays honest.

188 tests.

**THE CORPUS BECOMES SOMETHING YOU CAN ASK A QUESTION OF** (#372, #378,
#386). Lab only: no QC, no nav data, no bot behaves differently. MCP
0.28.

Everything else in this lab is per run. Every cross-tape conclusion in
the record was produced by hand or by a one-off script and then pasted
into the brief as prose: the nine-session human band, the tick-rate
table, the five-arm phase 1 table, the sixteen null pairs, the ratio
ranges at one tape a side. Each of those is a query over a corpus that
has been sitting in `runs/` the whole time.

`corpus` is one tool with a `what` selector, in the shape `see`
already uses. `tapes` filters and aggregates an index of every
committed tape; `cells` does the same for hotspot cells; `changes`
runs change point detection over the dated series; `bisect` localises
one step with a noisy oracle. It answers in CSV, which is about half
the tokens of the same table as JSON.

SQLITE WAS CONSIDERED AND REFUSED. The issue suggested it and it is
the obvious store, but the corpus is a few hundred rows of a fixed
schema, a full scan is microseconds, and the part worth having was "a
query, not thirty parameters". A named filter-and-aggregate surface
gets that without asking an agent to discover a schema and then write
SQL against it, which costs more tokens than it saves at this size.

`runs/tape_index.tsv` is a CACHE, not a source of truth: a tape it
does not name is parsed on demand and appended. A full rebuild is
about forty seconds; a query off the cache is sixty milliseconds. The
time axis comes from `LOG started on:` inside each tape rather than
the file mtime, because a fresh clone stamps every file with the
checkout time and would flatten the axis the whole thing exists for.

THE DETECTOR REPRODUCES THE RECORD, which is how you know it works.
Twenty five steps across the bot corpus and nearly every one is an
event already written down, with the tape that shipped it named:

```
dm4  lava_deaths  ab_dm4_B3           12.3 -> 4.4    the 2026-08-14 hazard fix
dm4  stalls       ab_dm4_bisect3      35.3 -> 8.0    the two-author forensics
dm4  stalls       ab_dm4_routegen2    48.5 -> 27.5   the wedge hunt
dm4  engages      ab_dm4_v317c        61.3 -> 78.9   v3.17
e1m1 engages      ab_e1m1_mover1       1.1 -> 17.8   #281, e1m1 stopped being empty
e1m1 cover        ab_e1m1_mover1     165.0 -> 338.2  the same tape
dm4  stalls*      shane_dm4_..._v311  32.2 -> 8.8    v3.11, found in HUMAN tapes alone
```

AND IT DATES THE ONE THAT WAS NEVER BISECTED. This file records the
September dm2 stall rise as "the September dm2 ladder mean is 52
against late August's 36 with a 60 to 199 tail. Not bisected." The
step is at 2026-08-29 10:37, at `ab_dm2_v403_control`, 29.2 to 44.6,
p 0.001.

IT IS ALSO CONFOUNDED, AND THE TOOL SAYS SO ON THE ROW. Every step
carries the commonest tick class either side, and that one reads
`dedicated_fast` before and `listen` after. Restricted to either class
alone the step does not appear. That does not prove it is the rate,
and it does not prove it is code. It proves the question was never
clean, which is exactly what those two columns are for.

A DETECTOR OVER A CORPUS WITH EIGHT METRIC BOUNDARIES IN IT FINDS THE
BOUNDARIES. Three of the goal steps are counters changing meaning, not
bots changing behaviour: `ab_dm4_deathanim` is the GOAP boundary where
goal completions started counting the touch, and `ab_dm4_preposition1`
is where they stopped counting an arrival at a pending item. Both are
recorded in this file as boundaries. Useful when auditing the
instrument, a trap when hunting a regression, and the detector cannot
tell them apart.

BISECTION WITH A NOISY ORACLE. `git bisect` assumes an oracle: each
answer permanently discards half the range, so one unlucky tape sends
the search into the wrong half and it never comes back. Phase 1 came
three tapes from convicting the wrong arm. `what=bisect` keeps a
posterior over where the change is, updates it with each noisy answer
and samples at the posterior median, so a bad tape shifts the
posterior instead of cutting off the truth. Against the second dm4
lava step it lands within a couple of hours of the detector's date,
does NOT settle, and names where to spend the next tapes. On a 2.8 to
4.8 effect against a measured sigma of 1.7 that is the correct amount
of confidence.

TWO PARSER DEFECTS THE INDEX FOUND ON ITS WAY, both older than it.

**The lab puppet read as a human.** The netclient emits `ARGLOG` rows
and never spawns, and the human-track split reads any such track as a
person. So every tape the puppet connected to briefed as a human
session, `compare` flagged those review-only, and two committed
BASELINES said a human had played in them: `band_dm4_2` and
`band_dm2_3`. `Argus_CanSee` has refused the netname `labprobe` since
v3.85 for exactly this reason. The engine's own `unconnected`
placeholder goes with it.

IT HAD TO COME OUT OF BOTH SIDES, and the first cut only took it out
of one. Excluding the puppet from the human tracks put its deaths into
the bot world-death count and its standing still into the bot freeze
count, on eight tapes. An instrument is neither, at every site that
splits them.

**Half the human sessions read as botmatches.** Human `ARGLOG` tracks
only exist from v3.66, so 46 of the 73 harvested sessions are human
matches with no human in their telemetry, and they were sitting in the
bot series. Their bots were fighting a person, which moves every
metric they recorded. The index tags a session by the harvester's
naming as well as by the telemetry.

NO TAPE'S NUMBERS MOVE, verified rather than asserted: the whole index
was built before and after the parser change and diffed row by row.
Sixteen tapes change their `kind`, which is the fix, and zero change a
metric. 182 tests.

`docs/specs/2026-09-16-corpus-change-points.md` carries the full table
and the reading.

**THE VERDICT GETS AN INTERVAL, A STOPPING RULE AND A PRE-REGISTERED
PRIMARY** (#375, #376, #377). Lab only: no QC, no nav data, no bot
behaves differently. MCP 0.27.

WHAT THIS INSTRUMENT CAN SEE, MEASURED RATHER THAN ARGUED.
`argus-mcp measure` pools the within-arm standard deviation across
every committed same-build arm - one build, one map, so the spread is
the instrument and nothing else - and turns it into the smallest
effect detectable at 3, 5 and 10 tapes a side. 84 tapes in 27 arms.
The table is `docs/specs/2026-09-16-lab-measurement-limits.md`:

```
map   metric     CV     MDE at 3 a side
dm2   stalls     52%    56, which is 119 per cent of the mean
dm2   coverage    9%    79, which is 20 per cent
dm4   stalls     73%    14, which is 168 per cent
dm4   coverage    7%    51, which is 15 per cent
dm4   freezes   261%    not measurable as a rate at any n on this list
```

That is this file's own prose turned into numbers. dm2 stalls at three
tapes a side cannot detect anything short of a doubling, and a great
many historical stall verdicts were unearned in both directions. The
handoff's "coverage and goal pickups are the only metrics with enough
signal" is now a measurement with a figure beside it.

WHAT FOUR GATES COST. A verdict that convicts on any of four is not
one test. Over the sixteen null pairs each gate convicts a change that
does not exist 0 to 12 per cent of the time and the verdict as a whole
convicts 19 per cent of the time. The any-gate row is always the
largest in the table, and it is the rule that shipped sixty builds.

The fix is saying in advance which gate the change is expected to
move. `experiment` and `argus-mcp compare` take `primary`; only that
gate convicts and the rest are computed, printed and flagged. It drops
the false positive rate from 19 per cent to about 6, and it ends the
habit the corpus shows repeatedly of deciding which gate to believe
AFTER the tapes are in. `ab_dm2_apexgate1` against `2` is the worked
example: two byte-identical builds that the band calls improved on
engagements, and that read parity the moment anything else is
pre-registered.

EVERY COMPARE NOW CARRIES A `stats` BLOCK, one entry per gate, with
positive always meaning the candidate is better.

- Interquartile mean rather than median. Three or four tapes are too
  few to throw most of away, and the mean belongs to whichever tape
  had a bot fall in the pit.
- A 95 per cent stratified bootstrap interval on the improvement,
  stratified by map. An interval that clears zero is what an
  improvement actually is; the band could only ever say "outside what
  the same build does". It is ABSENT below two tapes a side, because
  resampling one observation returns that observation and the
  interval would be a point of width zero. Saying so beats printing
  it.
- Probability of improvement: the chance a candidate tape beats a
  control tape, 0.5 being a coin flip. A number with a direction.
- An SPRT call of accept, reject, continue or abandon, with its bound
  derived from the detection limit at five tapes a side, so the
  stopping rule and the instrument agree about what is visible.

CONTINUE IS THE ANSWER THE LAB COULD NEVER GIVE. The old rule had to
return improved, regressed or parity whatever the evidence was, and
looking after every tape to decide whether to run another is peeking,
which inflates a fixed-horizon test's error rate. A sequential test is
built to be peeked at. `abandon` fires at a ten tape cap so a marginal
change is dropped rather than ground out forever.

VALIDATED ON THE NULL CORPUS, which is the bar any estimator here has
to clear. Ten same-build arms of four or more tapes, each split in
half - two arms differing by nothing but the match - give 58
decisions: **zero accepts**, 20 rejects, 38 continues. The sixteen
null pairs still read thirteen parities, and at one tape a side the
sequential test says continue on every metric of every one of them,
which is correct: one tape cannot rule an effect in OR out.

Read back over #363's own ladder, eight dm4 tapes against four, the
new block says something the band could not: stalls IQM 5 to 4.5,
improvement interval -6.2 to +7.5, P(improve) 0.52, sprt REJECT at a
bound of 10.6 - no effect of shippable size and no reason to run more
tapes. "Parity" said less than that.

HOW MANY TAPES A NULL COSTS, fed one at a time the way a ladder is
actually run: 20 of those 58 reached a decision at a mean of 1.9
tapes a side and 38 did not. Read the ceiling before the mean. These
splits offer a median of two tapes a side, because most committed
arms are four or five tapes long, so the undecided rows are mostly
arms that ran out of tapes and the mean is conditional on deciding at
all. It says the ones that decided decided early, not that a null
costs two tapes. The report says so in those words.

DELIBERATELY NOT BUILT, so the next person does not look for them.
Performance profiles, which #376 lists alongside the rest: the whole
distribution of the ratio across runs is a plot, and the probability
of improvement is its single-number summary, which is what a text
brief can carry. And the verdict is still the band's. The new
estimators are reported beside it rather than replacing it, because
the band is fitted to the null corpus and load bearing, and an
estimator swap is a separate change that has to clear the same bar on
its own.

ALSO NOT DONE: `primary` is opt-in. Making it mandatory would break
every existing caller and every exploratory compare, so a compare
without one now says out loud that all four gates could convict and
what that costs. The residual is real: an agent that ignores the line
still gets the 19 per cent rule.

The corpus analysis takes a runs directory rather than a configured
lab, so its tests run on a bare checkout. A validation set that skips
itself on CI is not a validation set. The baked sigmas carry a drift
test: if the corpus moves more than a factor of two from them the
suite fails and says to rerun `measure`. 163 tests.

**e1m5 AND e1m6 DOOR CROSSINGS ARE TYPED, AND #324 IS PAID OFF** (#324).
`--retype-doors` against the shipped graphs, which is the mode that
reads a .qc and its json and rewrites one field in place. e1m5 gains a
single door verb, `n79 -279 2505 424 -> n93 -151 2537 344`. e1m6
changes 26: twelve links newly typed and fourteen that were typed
against the compiled box rather than the shut one and are now plain
walks, for 202 door verbs down to 200. Nodes, links, order and every
other typed list are untouched on both maps.

Fourteen e1m6 crossings stay untyped on purpose. All fourteen cross a
vertical DOOR_START_OPEN slab, which parks back in the hole it was
compiled in, and a retype can only untype those. Refusing to mint one
is 6b's job and only a regen runs 6b (#331).

BOTH MAPS WERE RE-BASELINED FIRST, because both pointed at 19 Hz tapes
and a ladder on either correctly read VOID. e1m5 now carries a
five-tape band and e1m6 a four-tape one, all at the played rate. That
is task 0.5 of the recovery plan for two of its seven maps.

```
                stalls  engages  cover  goals
e1m5 control (5)   15      22     254     6
e1m5 cand    (4)   37      15.5   315     6
e1m6 control (4)   65.5    22.5   238     4
e1m6 cand    (7)   55      24     238     3
```

In band on all four hard gates on both maps. e1m5's stall median is
the one figure that looks bad, and it is one tape: 40 of the arm's 41
stallnodes at `448 2240 256` come from `ab_e1m5_doorverb2`, no control
tape has any there, and the cell is 750 units from either end of the
only link that changed. Across the whole arm exactly ONE stallnode
lands within 200 units of the retyped link, against none in the
control. e1m5 is also bimodal on a cell at `-173 324`, where a bot
spends a third of the match: two of five control tapes and one of four
candidates.

METRIC BOUNDARY (2026-09-16, door events): `ARGEVT door` is throttled
to one a second per bot, like the hazard deflection, and door counts
are NOT comparable across this change. It was never once per door. An
open slab on the line is re-taken every frame by design - the aim
through the doorway is meant to last exactly as long as the
obstruction - so `ar_door` was cleared and set again at the frame rate
and the counter was counting frames. One newly typed link on a busy
e1m5 route took a tape from 23 door events to 2234 with the bots
moving at 270 units a second through the whole burst. Every door
figure quoted in this file before today is a frame count.

Recorded while working: one e1m5 tape came back classified
`dedicated_fast` on a gap of 0.5114 where every other tape this
session read 0.506. The verdict voided itself, correctly. It was
discarded rather than committed.

**THE ROCKET LEAD POINT IS TRACED BEFORE IT IS USED** (#363). Argus has
led rockets and nails since v3.19 and nothing ever asked whether the
led aim point was in the room. The lead sits ahead of the target along
its velocity, so a target strafing toward a pillar or a doorway edge
puts the aim point inside the geometry BEFORE the target reaches it,
and the rocket goes into the near wall. A near wall splashes the
firer, which dm2 has already priced: opening the point-blank RL band
took self-kills to 40 per cent of all deaths on that map.

Reaper's answer, and it is the right size. Halve the lead, test again,
halve again, and fire unled rather than into masonry. Rocket launcher
only: splash is where a wall hit is expensive, and the RL is the only
led weapon that flies straight, since the grenade is deliberately
lofted over geometry a few lines further down. Skill 1 and up, like
every cognition gate since v3.76, so a warmup bot keeps the honest
miss. A lead shorter than half a player hull is skipped, which keeps
the trace off the hot path against a standing target.

TWO TESTS, NOT ONE. `pointcontents` reads hull 0, so it sees world
brushes and is blind to a door or a plat. A traceline sees those and
is blind to a start inside solid, which returns fraction 1 and is
byte-identical to finding nothing - the trace-semantics rule this tree
has paid for twice, and an embedded bot is the exact state
`Argus_Unstick` exists for. `Argus_AimBlocked` takes both.

REACHABLE, AND THAT IS THE FIRST CLAIM. The marker fires 4 to 22 times
a tape on dm2 and 15 to 44 on dm4, throttled to one a bot every two
seconds, so those are floors rather than counts. All three bots fire
it. The parser counts it as pseudo-event `leadclip`.

LADDERED BOTH MAPS. dm2 five tapes against the committed five-tape
band, dm4 eight against eight - four from #388's candidate arm and
four fresh control tapes built from this branch's own base. Parity on
every gate:

```
            stalls   engages   lava   freezes   goals
dm2 control    44       33       0       1        7
dm2 cand       42       35       0       1        8
dm4 control     6       86       4       0       14.5
dm4 cand        4       87.5     3       0       16.5
```

RECORDED RATHER THAN BURIED: two of the eight dm4 candidate tapes
carry an under-fire freeze and none of the eight control tapes does.
All four candidate freezes and the one control freeze sit at z -296,
the pit floor, which is the documented class, and the v4.18 ship
ladder produced them on byte-identical code at one tape in four. There
is no mechanism: the clip moves an aim point, and facing is decoupled
from movement through `ar_moveyaw`. Not convicted, worth a look if it
repeats.

dm4's baseline band now points at `ab_dm4_deadlink1-4` instead of
`band_dm4_1-3`. The old band predates #388, which removed a dm4 nav
link, so every dm4 verdict since has been read against a graph the map
no longer has.

**dm2's THREE UNTYPED DOOR CROSSINGS ARE TYPED** (#324). A regen of dm2
on the current tree reproduces the shipped 215-node graph in every byte
except three walk links that become door links:

```
n0   1185 -919 152  ->  n1    1281 -983  32
n91  2177 -919 152  ->  n67   2049 -983  32
n116 2369 -567  56  ->  n140  2465 -503   8
```

Same nodes, same links, same order, same emission slots. #320 fixed how
navgen types a door link and #330 fixed the shut-box test, but neither
reaches a map that is not regenerated, so these three have crossed a
shut door and said nothing since they were minted. A bot routed over
one gets no `ar_hopdoor`, so the advance never knows a door is on the
line and the apex cornering will cut onto it. The v3.33 runtime trace
handler still catches the slab at 240 units, which is why it was never
fatal.

The `doorlinks` array in the json also drops `201 -> 183`. That pair is
a jump link, which the .qc never carried a doormask for, so nothing in
the runtime changes there. Count door typing from the .qc, not the json.

FIVE TAPES A SIDE, against a control arm built from the same QC and the
shipped graph, dm2 at the played rate. Parity on all eight gates:

```
              stalls  engages  lava  freezes  coverage  goals
control (5)     46      27       1      1       363      10
candidate (5)   44      33       0      1       414      16
```

Two of the three links end at nodes that lead dm2's stall board, and
the targeted cells moved the way the mechanism predicts: stall events
naming one of the six endpoints ran 49 across the control arm and 24
across the candidate, on 289 stallnodes against 195. That is a
direction, not a proof. This map splits its own six-tape band into two
halves of three and returns REJECTED on byte-identical code, which is
the reason the ladder ran five a side.

dm2's baseline band now points at the five candidate tapes.

Still open on #324: e1m5 carries one untyped crossing and e1m6 twelve,
and both maps point at 19 Hz baselines, so a ladder on either correctly
reads VOID until they are re-baselined at the played rate.

**A TELEFRAG NAMED THE WRONG KILLER ON THE DEATH LINE** (#337). The
attacker on a telefrag is a `teledeath` trigger, which carries no
netname, so `Argus_Die` and `ClientObituary` both fell through to
their nameless-killer fallback and wrote `death world`. The engine
obituary had the fragger the whole time, from `attacker.owner`, which
is why Shane's v4.05 tape read 18 obituary kills against 17 attributed
death lines. Both emitters now resolve the killer through a shared
`Argus_KillerName`, which follows `.owner` for all three teledeath
classes and leaves every other nameless killer as `world`.

Verified against a probe build that forces a telefrag every three
seconds. Same map, same probe, thirteen telefrags a side: the control
wrote `Romero death world` thirteen times, the fix wrote `Romero death
Joe Rogan`. Nothing else in the tape moved, and no gameplay path
changed, so no ladder was run.

METRIC BOUNDARY: a telefrag now appears in the kill matrix against the
player who caused it rather than against `world`. Tapes recorded
before this undercount the fragger and overcount world deaths by the
number of telefrags they contain, which is small (one in 302 s on the
v4.05 human tape, none in a 180 s dm6 botmatch).

## v4.19 (2026-09-16) - the link that was never crossed

Progs v4.19 MD5 4A691E3CFCADE7EF2CA476955B44CBA7 x4. Nav data and lab
tooling; no QC logic changed.

**dm4's n124 to n95 JUMP LINK WAS NEVER CROSSED IN THAT DIRECTION, AND
IT WAS THE MAP'S BIGGEST MEASURED COST** (#350). Across 30 tapes, 611
samples stand at n124 and NOT ONE reaches n95; the reverse crosses 25
times. Bots arriving at n124 were routed over a hop the runtime cannot
execute, dithered against the brink guard at a locked yaw, and fell
into the pit in 12 per cent of samples. The cell was the most frequent
confine on the map, ahead of the documented walkway corner.

THE PUPPET CONVICTED IT, WITH ITS OWN CONTROL. Jump links had NEVER
been swept: they live in their own `jlinks` array, never appear in
`links`, and `probe_links` filtered the class out, which is how this
survived every verification pass the project has run. `probelinks
--jumps` sweeps them now. On dm4, **16 of 18 pass and the two failures
are this pair**, so the hop works elsewhere and jams here. A jump
sweep deliberately does NOT write the verdict file, because navgen's
7g2c reads `failed` as "remint this WALK link as a jump", and these
are already jumps.

ONE DIRECTION REMOVED, the reverse kept because it demonstrably works
in play. Directed reachability is unchanged at 135 of 137 and n124
still reaches n95, in 9 hops rather than 1 - which is itself the
finding, since two nodes 181 units apart being 9 walk-hops apart means
there is real geometry between them.

Four tapes a side against v4.18 on the same nav, dm4 at the played
rate. Inside the cell:

```
                  stalls        hazards        longest hold
shipped nav    11, 0, 0, 15   104, 13, 1, 64  85.0s 12.1 0.5 65.7
link removed    0, 1, 0,  0     0,  2, 0,  1   0.5s  2.6 2.6  2.5
```

The control is bimodal: when routing happens to use the link a bot
loses up to 85 SECONDS, and when it does not the cell is quiet. That
is why the map's stall figure has always swung so hard. Map-wide,
stalls 12 to 6.5, freezes 0.5 to 0, under-fire freezes 0.5 to 0,
average speed 236 to 247, goals 110 to 126, engagements 72 to 80, all
four hard gates passed. Frag spread widened, 3.5 to 7.5, on more total
frags per tape (median 15.5 to 21) with every bot positive in every
tape: more combat to distribute, not a starved bot.

## v4.18 (2026-09-16) - the two changes a botmatch could not size

Progs v4.18 MD5 DE6E4B629B408F1EAE8E0274A1C1B66B x4 (lq1, game,
engine, rerelease).

**BOTH CHANGES WERE HELD BACK ON PURPOSE AND THEN INSTALLED ON SHANE'S
CALL.** Each is laddered green, and each changes how bots behave
against a HUMAN in a way no botmatch can size: one makes the aim
spring behave the same on every rig, the other makes a bot keep
shooting while it is shot at point blank. A botmatch can show that
neither breaks anything, which both did, and it cannot show whether
the game got harder. That is what the next human session is for.

Shipped against v4.17's 544D463AE34CD2EEE264B3BC3A92ADC3, which is
kept in `backups/` so a revert is byte exact rather than a recompile.
Smoke tested on dm4 at the played tick rate: clean, 332 telemetry
rows, no engine errors, and the body-block marker fired 5 times in
60 s, which reproduces the 8 in 120 s the instrumented ladder
measured.

**THE AIM SPRING BEHAVED DIFFERENTLY ON EVERY RIG, AND NOT SLIGHTLY.**
`turn = 1 - damping_c * frametime` goes negative at every tier above
skill 0 and was floored at 0.1, which does not damp the spring, it
replaces it: `aimvel` becomes almost entirely `k * dt * error`. At
skill 2 and 19 Hz that is 0.97 of the aim error in a single frame.
Settle time for a 30 degree flick to within 3 degrees:

```
tier       71 Hz (played)   19 Hz (lab)   14.5 Hz (lab)
skill 0        0.27 s          0.26 s        0.28 s
skill 1        0.20 s          0.10 s     ONE FRAME
skill 2        0.14 s       ONE FRAME        0.21 s
skill 3        0.11 s          0.05 s     NEVER SETTLES
```

Every lab tape since v3.27 was recorded in the middle column and every
session Shane played ran the left one. The fix is the integrator and
not the constants: sub-step at 0.02 s, which is ONE step whenever the
frame is at or under 20 ms (the lab's mean is 14.25 ms, counted with
`host_speeds`) and three steps at 19 Hz. Re-fitting the played
constants to match the lab, as the recovery plan asked, would
reproduce that snap-aim in play: a difficulty change dressed as a bug
fix, and it was declined.

Laddered both ways. At the played rate, parity on dm4 (three tapes)
and on dm2 (five). At about 14 Hz and skill 3, where the old
integrator provably sits in a limit cycle, two tapes a side are
DISJOINT on both metrics: engagements 61 and 68 against 85 and 115,
bot deaths 21 and 26 against 42 and 47.

THE dm2 ARM IS THE SESSION'S CLEAREST LESSON ABOUT THIS LAB. At three
candidate tapes it read 21, 22, 43 and the verdict was IMPROVED on two
gates against six controls. That could not be explained - the change
is arithmetically identical on a 14 ms frame - so more tapes were run
rather than shipping it. The fourth came back at 54, the fifth at 56,
and the verdict is parity.

**A BOT STOPPED SHOOTING WHEN SHOT AT POINT BLANK.**
`Argus_BodyBlockCheck` releases `button0` whenever any live player
within 48 horizontal units is airborne or firing. In co-op that is the
defect #177 was filed for, a companion shooting through its team
mate's back; in deathmatch the same line fires when an ENEMY shoots at
you. Gated to `coop > 0`; the sidestep and the anti-embed nudge stay
in both modes. Instrumented first (`ARGUS <name> bodyblock`, throttled
two seconds a bot): eight firings in a 120 s dm4 botmatch, about four
per cent of the windows, WHICH IS ALSO THE LIMIT OF WHAT A LADDER CAN
SAY. Three dm4 tapes read parity on all four gates. The human test
stands outstanding: stand on a bot while firing and see whether it
shoots back.


**THE LAB HAS BEEN RUNNING A DIFFERENT GAME FROM THE ONE ANYONE PLAYS,
and its verdict could not tell a change from nothing.** Phase 0 of the
regression recovery plan
(`docs/plans/2026-09-14-regression-analysis-and-recovery.md`). Lab
only: no QC, no nav data, no bot behaviour change.

`sys_ticrate` gates Quake's dedicated main loop. The engine default of
0.05 ran every tape in `runs/` at about 19 Hz while every human
session is a listen server at about 71 Hz, nearly a factor of four on
every per-frame constant in bot physics and on the aim spring's
integrator. Measured on dm4 with the telemetry-cadence estimator: the
default reads a mean ARGLOG gap of 0.5134, `+sys_ticrate 0.0139` reads
0.5074, and every human tape reads 0.506 to 0.509. This refutes the
v4.09 note that "sys_ticrate does nothing to the dedicated tick", and
the v4.07 "frametime 0.1", which was `ftos` printing a 0.05 s frame to
one decimal.

**THE TICK RATE DOES NOT MEASURABLY CHANGE dm2 BOT BEHAVIOUR**, and
this entry said otherwise twice before arriving here. The first
version claimed the played rate reproduced Shane's dm2 stall rate
where 19 Hz "read 11 to 16"; that was a selective reading of
historical tapes. The second claimed the rate moved engagement,
coverage and deflections; that rested on four tapes a side and the
fifth and sixth control tapes dissolved it.

Run as a controlled experiment, same progs and same graph:

```
dm2, shipped v4.17, 185 s tapes, 6 at the played rate against 3 at 19 Hz

rate-INDEPENDENT (counts of things that happened, not of frames)
  stalls         64 [31-86]      74 [17-79]     z +0.00   overlap
  engagements    24 [17-40]      31 [27-43]     z -1.29   overlap
  coverage      439 [348-560]   463 [454-505]   z -0.77   overlap
  goal pickups   96 [90-111]    101 [100-104]   z -0.77   overlap
  bot deaths     12 [4-19]       15 [11-16]     z -0.39   overlap
  average speed 208 [194-254]   210 [203-258]   z -0.52   overlap
  routed share   77 [75-81]      78 [71-78]     z +0.26   overlap
  routefails     15 [12-20]      14 [9-17]      z +0.65   overlap

INFLATED BY FRAME RATE BY CONSTRUCTION (throttled one a second per bot)
  hazard        244 [226-260]   203 [195-214]   z +2.32   disjoint
```

Every metric that counts something that HAPPENED overlaps, with
stalls at z 0.00 exactly. The one disjoint metric is the hazard
deflection count, and that event is throttled to one a second per
bot, so a 3.7x frame rate raises the chance of at least one
deflection landing inside any given second whether or not the bot
behaves differently. It is a measurement artifact and must not be
read as timidity.

**THE TICK PIN IS STILL RIGHT, FOR A REASON THAT IS ARITHMETIC AND NOT
STATISTICAL.** The aim spring's integrator genuinely behaves
differently at the two rates - 97 per cent of the aim error in one
frame at 19 Hz and skill 2, and no settling at all at 14.5 Hz and
skill 3 - and that is a derivation from the code rather than a
p-value. What these tapes add is that dm2's MOVEMENT numbers are
insensitive to the rate, which is worth knowing in its own right: the
old tapes' movement figures were not lies, they were just recorded on
a rig whose aim was a different bot.

dm2 runs about 21 to 24 stalls a minute at either rate, which is the
range Shane reports (21.6, 32.5, 21.9). The map's stall problem is
real, old, and was never being hidden by the rig.

**THE VERDICT RULE WAS A COIN FLIP.** Run over the sixteen pairs of
byte-identical builds in `runs/`, the old OR rule returned nine
"improved", five "regressed", two "mixed" and zero parity.
`compare_band` returns parity on thirteen of the sixteen, one
"improved" and two "regressed". Its band is
fitted to those pairs rather than guessed; one tape a side, on
identical code, this lab produces a stall ratio from 0.18x to 11.0x,
engages 0.45 to 2.82, world deaths 0 to 4x and freezes 0 to 3.
Coverage (0.70 to 1.19) and goal pickups (0.82 to 1.27) are the ONLY
metrics here with enough signal to read a change off a single pair.

At one tape a side the stall band's floor is zero, so an improvement
cannot be expressed at all, only a regression or parity. Every
"improved on all seven gates" in this file rests on an instrument that
could not have said anything else. The band narrows as the square root
of the tape count, so `experiment` now runs three candidate matches by
default and judges them against the map's whole baseline band.

Also: every brief carries `tick_gap_mean` and `tick_class`, and
compare voids a verdict across two classes; the human scorecard
(`tools/argus_longi.py`, `tools/argus_tick.py`) is a lab surface, with
unstick warps on the card because a bot vanishing is a visible failure
and not a fix; `argus-mcp match` drives a named match from the CLI;
dm2 and dm4 are re-baselined as three-tape bands at the played rate.

Filed while working: #337, a telefrag emits an engine obituary and no
ARGEVT death line, so it is invisible to every kill matrix.

Recorded: fteqcc IS byte-stable here. A recompile of the shipped v4.17
source differs in exactly one byte, the build date in its header
comment, which retires the v3.74 note that a rejected cycle must never
restore by recompile.


**A shootable door cannot be opened by walking into it, and fixing
that costs more than the defect (#325).** Recorded as a refusal with
its tapes, because the diagnosis is solid and all three cures failed.

`Argus_TakeDoor` treats a door with no targetname as touch-open. id's
own `LinkDoors` refuses a trigger_field to a door with health, a
targetname or items, and a `func_door_secret` never reaches LinkDoors
at all: `secret_touch` only centerprints, and `fd_secret` hands a
secret with no targetname health 10000, DAMAGE_YES and `th_pain`
`fd_secret_use`. So no targetname is exactly id's condition for "this
one opens when it is shot", and it is the condition Argus reads as
"walk in". Both classes set classname "door" at spawn, so health with
takedamage is the only runtime discriminator, and it is the right one.

Eight secrets in the rotation have no targetname; four carry
door-typed links, fourteen of them: e1m1 `*13` and `*14`, e1m2 `*48`,
e1m5 `*50`. No `func_door` in the rotation carries health, so the
other half of the class is inert here.

THE MEASUREMENT IS WHY IT DID NOT SHIP. Instrumented tapes on e1m1:
612 of 683 door traces in 120 seconds hit one of those secrets, and
every one of the 610 takes reported `ar_hopdoor` 0 while routed, so
the router never types these particular hops as door crossings. Three
cures, three answers:

- fire whenever the slab is taken: 610 firings, coverage 415 to 316,
  engages 25 to 20 (`ab_e1m1_shootsecret1`).
- gate on `ar_hopdoor`: zero firings in 305 seconds
  (`ab_e1m1_shootsecret2`).
- fire only after the same slab has blocked the bot for two seconds:
  zero firings in 185 seconds (`ab_e1m1_shootsecret3`), because
  `Argus_DoorPast` clears and re-takes the door constantly. The bots
  are crossing a sight line while walking past, not standing blocked.

So the slab is in front of bots 612 times a tape and never actually
stops one for two seconds. The defect is real in the code and costs
nothing in play on the maps that carry it.

CORRECTION TO METHOD, which cost four void probes: `experiment` with
`compile=false` runs whatever progs is already installed, so hand
compiling to `lq1/` and then probing proves nothing. Those four tapes
were deleted rather than committed. And e1m1's configured baseline is
from 2026-09-13: five tapes of the current build land at coverage 220
to 317 against its 415, so that gate has been measuring era drift, not
any candidate.

No QC ships. Instrument probes kept as `probe_e1m1_tracewhat` and
`probe_e1m5_tracewhat2`.

**A committed tape is evidence, and match_run stops writing over one
(#328).** `match_run` takes a `run_name` and writes
`runs/<name>.log`. A name that collided with a tape already in git
replaced it in place, with no warning, and the only sign was a
modified file in `git status`, which reads exactly like a tape you
just made. It happened twice in one week. `ab_e1m1_doorway1` was
caught and restored during #303. `ab_dm2_doortype2` was caught too
late, so the ladder tape it destroyed survives only in a session
transcript, and a refusal recorded without its tape is a refusal
nobody can re-read.

`MatchCtrl::start` now refuses such a name before the engine spawns,
in the same place as the un-harvested-session guard it mirrors, and
the message names both ways forward.

TRACKED BY GIT IS THE TEST, not whether the file is there. The matrix
probe writes `mx_<map>.log` on every run by design and five of those
tapes are committed, so refusing every collision would refuse the
lab's own loop. A rolling probe says so with
`refresh_committed_tape()`, which is one shot and cleared by the
`start` that uses it, so the exemption cannot leak into the next
match. `matrix_experiment` is the only caller.

AND IT FAILS OPEN. No git on PATH, or not a checkout, means nothing
is known about the tape and the match proceeds. A guard that cannot
answer must not wedge the lab.

`harvest_session.py` was checked and needed nothing: it already
auto-suffixes a colliding stem, so `match_run` really was the only
path in the tree that wrote over committed evidence.

Lab MCP 0.25.0.

**A vertical door that starts open parks in its own doorway, and
navgen now keeps links off it (#331).** 5b3's parked-slab veto only
modelled doors that slide sideways. A plain vertical door was left out
on the grounds that a slab going straight up or down leaves the
doorway rather than parking in it, which is true, and is the wrong way
round for a DOOR_START_OPEN one. doors.qc swaps pos1 and pos2 for that
flag, so the door sits a travel clear at spawn and the first thing
that triggers it puts the slab back in the box it was compiled in. For
a vertical door that box is the doorway.

Nine such doors are in the rotation: e1m1 five, e1m7 two, e1m5 and
e1m6 one each. Two of the nine stand where a graph reaches, and
between them they carry thirteen link pairs through the box they park
in - e1m6's `*40` ten, one a plain walk and nine typed as doors by the
bank of shut slabs sharing that volume, and e1m1's `*15` three, all
plain walks. The runtime steer from #303 catches every one of them
frame by frame, so this was never a freeze; it is a link the graph
should not mint.

The fix is one filter in `_door_travel_boxes`, which now answers for a
vertical START_OPEN door with the compiled box as its open half. 5b3
and 6b needed no changes at all. Two pieces of tidying came with it:
the vertical shut-box arithmetic, which used to be worked out twice
and was wrong the second time until #330, now lives in one place; and
the refusal that keeps a `func_door_secret` out of the travel model
moved there too, so no future caller can repeat #330's mistake.

MEASURED, because a mint-time change reaches a map only through a
regen and a regen has to be worth running. `--retype-doors` comes back
byte identical on all eleven maps, so the shut box did not move and
#330's guarantee holds. Regenerating e1m1 and e1m6 against the same
tool without the fix and with it: the same node count, the same worst
spawn reach (97 and 95 per cent), the same stranded pockets and the
same edict estimate, with six and fourteen more links vetoed. The
dishonest links go and nothing pays for them.

No nav data ships. Each map collects this at its next regen, e1m6
first, since it owns ten of the thirteen.

**navgen corrects door typing without regenerating the graph (#330).**
`--retype-doors` reads a shipped `argus_nav_<map>.qc` and its json,
recomputes which links a shut door blocks, and writes both back with
the typing corrected and nothing else touched. No sampling, no
decimation, no linking, no knitting, no plot. dm2 takes 0.2 seconds
against 37 for a regen, and its whole diff is three verbs.

The point is the unit of change, not the clock. #320's typing fixes
only reach a map through a regen, and a regen reseats, relinks,
re-decimates and re-knits everything, so a three link correction
arrived wrapped in a whole new graph and had to clear a ladder built
for whole new graphs. Three of the four maps carrying debt have their
regens refused for reasons that have nothing to do with doors.

WHICH FILE IS THE AUTHORITY ON WHAT. The `.qc` owns link order,
because emission order is what assigns runtime link slots: its lines
are rewritten in place, so a link keeps the slot it has and only its
verb changes. The json owns node position, because the `.qc` rounds to
whole units and the typing test measures floats. The two are checked
node for node before anything is written, so a mismatched pair refuses
rather than rewriting the wrong graph.

PROVEN AGAINST THE GENERATOR, which is the only claim worth making: a
full regen of dm2 and of e1m7, retyped, comes back byte identical in
both files, so the mode and the pipeline's own 7f2 agree. The refactor
it needed - the entity lump and the door geometry move ahead of
sampling, since nothing else in the file may run - leaves a dm2 regen
byte identical to the same regen before it, stdout included.

**Two defects in the shut-box test, both found by building that mode
(#330).** Both live in `_door_shut_box`, both arrived with #319, and
neither has reached nav data, because every regen since has been
refused for other reasons.

- A `func_door_secret` was read as a `func_door`. doors.qc builds a
  secret door at its closed position, always, and its bit 1 is
  SECRET_OPEN_ONCE, which means it stays open once opened, not that it
  starts open. Read as a func_door's DOOR_START_OPEN it swapped the
  box a travel away from the wall the door is actually in, and the two
  stage sidestep a secret really performs is not a travel this file
  models anyway. Six links on e1m1 and two on e1m2 lost a door type
  they had earned.
- The vertical branch had the two angles the wrong way round. subs.qc
  SetMovedir reads angle -1 as UP and -2 as DOWN; the code had it
  backwards, so every vertical START_OPEN door was tested against a
  slab reflected to the far side of its own doorway. e1m1 carries
  five, e1m7 two, e1m5 and e1m6 one each.

AND THE DEBT TABLE BELOW IS WRONG, because it was counted against both
of those and from the json rather than from the `.qc`. Those two
disagree on three maps - dm2 12 against 11, e1m1 59 against 58, e1m6
212 against 202 - because a pair 6c typed and a later pass reminted as
a jump emits as a jump link while 6c's list keeps the stale entry. The
runtime never had a doormask on any of them. 7f2 cannot produce one,
and a retype clears them. What the shipped graphs actually carry, what
a retype makes of them, and the whole of the real debt:

```
map     door verbs   after   newly typed   untyped
e1m6           202     200            12        14
dm2             11      14             3         0
e1m5            36      37             1         0
e1m1            58      58             0         0
e1m2            64      64             0         0
e1m7             0       0             0         0
e1m8            16      16             0         0
```

e1m7 was the headline item at 30 of 30 and needs nothing at all: every
one of the 30 was measured against the reflected slab. e1m1's seven
were six secret-door crossings and one reflected vertical. The real
debt is 26 links on e1m6, three on dm2 and one on e1m5. Collecting it
is still #324's job, one map at a time with its own tape, and e1m1,
e1m2 and e1m8 move in the json only, so their progs would not change
at all.

ONE MORE THING THE MODE FOUND AND CANNOT FIX, filed as #331: a
vertical door with DOOR_START_OPEN parks in the box it was compiled
in, which is the doorway, and 5b3's veto only models doors that slide
sideways. Fifteen links across e1m6 and e1m1 cross one. Untyping is
all a retype can do about that. Refusing to mint it is 6b's job, and
only a regen runs 6b.

The CLI fixtures for this are BUILT, not borrowed. A retype needs a
BSP only for its entity lump and its model boxes, so twelve lines of
struct is a whole map as far as it is concerned, and the seven new
tests run on any machine instead of skipping wherever `maps_local` is
absent - which is the lesson already recorded one method above them.

**The door-typing debt: the cheapest map in the queue was worked and
refused (#324).** #320 fixed three defects in how navgen types a door
link, and all three only reach a map through a regen, so every shipped
graph still carries links that cross a door and are typed as nothing.
Re-measured against the shut box rather than the compiled one, which
moves the numbers in the issue:

```
map     typed   crossings   untyped   wrongly typed
e1m7        0          30        30          0
e1m6      212         200        12         24
dm2        12          14         3          1
e1m1       59          53         1          7
e1m5       36          37         1          0
e1m2       64          62         0          2
e1m8       16          16         0          0
```

CORRECTED BY THE #330 ENTRY ABOVE: this table was counted from the
json and against a shut-box test carrying two defects. The real debt
is 26 links on e1m6, three on dm2 and one on e1m5, and e1m7 needs
nothing.

dm2 is the cheapest entry and the cleanest possible experiment: its
regen differs from the shipped graph in EXACTLY the door typing, one
link dropped and three added, every node and every other link
identical. Three tapes, and the tree's own gate rejects it: stalls 32
to 42, and an under-fire freeze in two of the three where the two
nearest controls had none.

THE REFUSAL IS HONEST BUT IT IS NOT CLEAN, and the reason is worth
keeping. Two of the three freezes sit at `'2003 -1104 344'` and
`'1992 -1108 344'`, which is #323's deck cell, 380 units from the
nearest door and nothing to do with this change. dm2's own history
runs 0 to 4 freezes a tape across every era, and the control that
happened to be picked ran zero twice. So the gate fails on its own
terms and the cause is probably elsewhere, which is exactly the
situation the two-tape rule exists to stop being argued away. No nav
data ships and the debt stays.

The real debt is e1m7 with 30 of 30 and e1m6 with 12, and neither map
has a regen that passes: e1m7 was refused this week on an under-fire
freeze at `'24 61 8'` in two tapes of three, and e1m6 has no baseline
at all.

  ONE TAPE OF THE THREE IS MISSING and it is the one that failed
  hardest. `ab_dm2_doortype2` collided with a committed tape of that
  name from the v3.35 era and overwrote it; restoring the committed
  one destroyed the candidate. Its numbers are in the refusal above.
  Second time this week, so it is filed as #328.

**navgen says which sidecars a run can see (#323).** The four sidecar
files - costs, probe, proven, mined - are read from the directory the
QC is written to. So a regen written to a scratch path silently builds
WITHOUT the map's convictions while one written into `src/` builds
with them, and the two graphs are then not comparable even though the
command looks identical. One line at the top of every run now names
the directory and lists what was found there.

It cost a wasted dm2 regen to notice, and worse, it means three of
this week's e1m2 candidates were judged against a shipped graph that
carried one puppet conviction they did not. One conviction against
198 nodes is unlikely to have flipped three ladders, but the method
was wrong and the number is on the record now rather than in nobody's
head.

**A bot pinned while fighting can be unstuck now (#322).**
`Argus_Unstick` has two signatures. Embedded fires on hull 0 reading
solid; pinned fires on four stalls and six seconds without moving,
which is how #271 caught a wedge that is not inside anything. The
second one keys on `ar_stalls`, and the only thing that feeds
`ar_stalls` is a detector gated on `!fighting`. So a bot with an enemy
stops counting stalls entirely and can never reach four, for any
length of time, and the two cancel exactly where it matters most.

Found in a human session, `shane_dm2_2026-09-14`: Carmack held
`'2372 16 72'` for 19.7 seconds at 26 health, turning on the spot
through yaw 158, 310, 224, 205, 230 and 324 while the position never
moved, with `engage player`, `retreat` and `pursue` in the window and
his stall count frozen at 6. Four were needed. The same tape holds
three more bot freezes over six seconds.

A third branch: a live enemy, no mover hop in progress, and eight
seconds without moving 32 units. The stall count was only ever a proxy
for "this is not a designed wait", because `Argus_AI` clears
`ar_liftwait` at the top of every frame and a hold flag read from in
there is always 0. Combat is not a designed wait either - every
pad-side hold has yielded to a live enemy since v3.64 - so the proxy
is not needed here, and the hop flags, which ARE readable on this
tick, are tested instead, because the aboard-a-mover holds
deliberately do not yield. Eight seconds rather than six because
nothing corroborates this one. The console marker splits three ways
now: `unstick embedded`, `unstick pinned`, `unstick fightpin`.

PROVED REACHABLE RATHER THAN ASSUMED. A probe build with the window at
one second fired it once in a 60 second dm2 match, `ARGUS Romero
unstick fightpin '2433 -183 24'`, which is both the proof the branch
runs and the measure of how rare it is: one firing in 180 bot-seconds
at a bar eight times lower than the shipped one. At eight seconds it
did not fire once across four full tapes.

That is also the shape of the ladder, and it is worth being plain
about. Four tapes, two maps, zero firings in all four, so every
difference in them is variance by construction rather than by
argument:

```
                      stalls   engages   coverage   goals
dm2 controls          41/97/17  48/17/48  435/367/422  9/9/6
dm2 fightpin1/2       41/28     36/31     482/423      11/5
dm4 baseline           6        84        345          18
dm4 fightpin1/2        6/20     78/47     348/321      19/10
```

Both maps inside their own bands, no gate failing twice. A guard that
only fires on a rare condition cannot be shown to help in a botmatch,
and the honest version of that is to show it costs nothing and to
prove separately that it runs.

**The seat budget, measured instead of assumed, and what it did not
fix.** e1m2 refuses 68 seat requests a run that found a sample and had
no budget left, and e1m5 refuses 42, while every other map in the
rotation refuses none. Two reasons, one of them simply wrong
arithmetic.

A MAKESTATIC ENTITY IS NOT AN EDICT. `light_globe`,
`light_torch_small_walltorch`, the three `light_flame_*` classes and
`func_illusionary` set a model and hand themselves to builtin 69,
which copies them into the static list and frees the edict, so a wall
torch costs a precache and nothing else. The budget counted all of
them. MEASURED, not reasoned: an `edicts` dump of a live e1m2 shows
`light_flame_small_yellow` at 16 in the lump and 0 in the world, in
deathmatch AND in co-op. e1m2 carries 24 of these, e1m5 22, lqdm2 22,
e1m6 16, dm6 15, e1m7 6.

AND THE BUDGET NOW SAYS WHAT IT IS MADE OF. It was a flat 500, which
is the 600 ceiling with a hundred held back for reasons nobody had
written down. Injecting `edictcount` into live matches says what the
hundred covers:

```
                             model      measured peak num_edicts
dm2   215 nodes,  88 ents      303      335
e1m2  198 nodes, 272 ents      470      447 deathmatch, 442 co-op
e1m2  253 nodes, 272 ents      525      502 deathmatch, 497 co-op
```

On dm2, where the entity count is honest, everything the model cannot
see - the world, eight client slots, three bots, and every rocket, gib
and backpack alive at once in a 31-engagement match - came to 32
edicts. Fifteen samples across two minutes never moved it, because the
engine reuses freed edicts and `num_edicts` IS the peak. So the budget
is `600 - 60 - 9`: the ceiling, a reserve of double what was measured,
and the world plus maxclients. Caps move: e1m2 200 to 259, e1m5 159 to
212, e1m6 203 to 260, everything else was already at the 260 density
ceiling.

MONSTERS AND `spawnflags 2048` ARE DELIBERATELY STILL COUNTED, though
every monster spawn in this tree removes itself in deathmatch and the
engine frees the 2048 entities there. e1m2 alone would gain 53 more
seats. It is played in co-op as well, where both are real, and the
budget has to hold in the worse mode.

THEN THE POINT OF THE EXERCISE FAILED, AND THAT IS THE RESULT. e1m2
regenerated under the corrected budget is a 253 node graph against
198, with zero bad seats, zero over-ceiling jump links, worst spawn
reach 97 per cent, its lift link, 37 door links and 48 door events a
tape against the shipped graph's 44. Three tapes against three
same-build controls:

```
                stalls   engages   coverage   goal pickups
control            35        23        540         11
control            67        10        359          8
control            32        23        479         16
budget             53        26        427          3
budget             59        25        412          5
budget             45        18        469         14
median control     35        23        479         11
median budget      53        25        427          5
```

Engagements hold and everything else is worse, goal pickups by half.
So the 68 refused seats were not a deficit: e1m2 plays better without
them. That is the fourth time this map has refused its regen, now with
the budget, the door typing, the plat pad and the jump ceiling all
fixed, and it is the strongest evidence yet that whatever is wrong
with an e1m2 regen is not in the list of things anyone has named.

No nav data ships. The budget change is verified for SAFETY by
measurement - the densest e1m2 anyone can now generate runs at 502 of
600 in deathmatch and 497 in co-op - and its effect on quality is a
question for each map's own ladder, which is where it belongs.

**Four navgen defects behind one refused regen (#319).** e1m2 had
refused its regen twice, in #308 and again in #318, and the tool was
blamed for two of it: a graph with half the door links and no lift.
Both were real. Neither was the reason the regen failed, and the
digging turned up two more.

THE PLAT PAD WAS NOT MISSING, THE BUDGET WAS. `PROMO_CAP` was 200,
decimation seated 196, and the item, stair and sprint passes took the
last four before the lift asked for its exit pad. `force_way` then
returned None and the pass printed "no usable pad", which reads as a
statement about the map. The sample that pad wanted was sitting 91
units away, well inside the 120 the search allows. This is the second
time the cap has eaten typed infrastructure: v3.69 records it killing
all four of dm2's rocket-jump pads the same way. Infrastructure now
has a reserve of eight seats past the cap, spends it out loud, and an
ordinary starved seat is counted rather than silent. e1m2's lift link
is back, `n198 -> n199`, 1201 33 92 up to 1361 33 320.

A DOOR THAT SLIDES UP INTO A CEILING IS NOT A PLATFORM. The #281
mover class takes any big vertical `func_door` with 48 units of
travel, and e1m2 has two 126x118 doors of that shape whose open top
face is in the ceiling. The pass seated pads there anyway, by snapping
47 units to the nearest sample or inventing a virtual one, then minted
a lift link each way into a hole - and after the fix above it was
spending the reserve to do it. A mover now needs real floor within a
step of BOTH faces. e1m1's *3 qualifies twice over, which is why it
was the found case: its closed top is the start area's floor and its
open position is the pit floor. e1m1 regenerates unchanged, e1m6's
*51 is correctly left as a door.

NINE SAMPLES CANNOT DECIDE WHETHER A SEGMENT MEETS A BOX. The door
test walked nine fixed points along each link, so its probe spacing
was the link's own length: a 300 unit link steps 37 units at a time
past a slab 30 wide. Replaced with an exact slab test, which has no
density to tune and is cheaper than the nine it replaces.

AND IT WAS TESTING AGAINST THE WRONG BOX, which is the one that
mattered. A `DOOR_START_OPEN` door is compiled where it stands when
OPEN, so on a map whose doors all carry that flag every door link
navgen drew was a link through the PARKED slab, which #309 vetoes
rather than types. e1m7 is that map. It ships 0 door links from 5 door
brushes today; with the compiled box it types 15, all of them wrong,
and with the shut box it types 30 honest ones.

```
door links          shipped   compiled box   shut box
e1m1                    59             59         53
e1m2                    64             33         31
e1m6                   212            181        167
e1m7                     0             15         30
```

Typing also moved to the end of the pipeline. 6c runs before knitting,
closure, jump-up links and the verdict remint, so links those passes
mint cross their doorways untyped; the retype runs over the final
graph and replaces rather than extends, so an evicted link cannot
leave a stale entry.

NO NAV DATA SHIPS WITH THIS. Both regens it enables were built and
laddered and both were refused. e1m2, on three tapes against a
same-build control, ran engages 6 / 12 / 6 against 23 / 10 / 23, which
fails that gate twice; its graph is honest in every static number
(zero bad seats against 39, zero over-ceiling jump links, worst spawn
reach 97 per cent against 95, and the lift back) and it still plays
worse. e1m7's regen differs from its shipped graph in exactly one
field, 0 door links becoming 30, and two of its three tapes flag an
under-fire freeze at '24 61 8' that no shipped-graph tape shows.

So the tool is fixed and its output is still refused, and those are
different statements. What the e1m7 pair does show is the wrong box
being expensive: routefails 11 and 28 with the compiled box, 1 and 4
with the shut box, on otherwise identical graphs.

AND THE COUNTER THE FIRST FIX ADDED POINTS AT THE NEXT THING. Over a
whole run e1m2 refuses 68 seat requests that found a sample, and e1m5
refuses 42. Every other map in the rotation refuses none. Those two
carry the biggest entity lumps, 296 and 341 live entities, and
`PROMO_CAP` is `500 - lump - 12`, so they are the maps where the
sampler cannot have the seats it asks for. That is worth knowing
before anyone tries e1m2 again: its regen is not competing with the
shipped graph on equal terms, it is building under a budget the
shipped graph was built under too but with more passes now asking.

CORRECTION TO THE ISSUE I FILED: the door link count itself was not a
defect. e1m2's shipped graph seats three nodes inside door brushes and
every link radiating from one counts as a crossing; the regen seats
one. Fewer typed links, same reachability. The defects were underneath
the count, not in it.

**The router refuses a climb a jump cannot make (#317).** #316 stopped
navgen minting a jump link that climbs further than a jump climbs, but
only a regen applies a mint-time rule, and the two maps carrying the
most of them had both refused their regen on their own tapes. So the
refusal moved to the router, where it costs nothing to apply and
covers every graph in the tree at once.

The bar is the apex rather than navgen's constant, and that difference
is the whole reason this works on both halves of the issue. navgen's
`JUMPUP` is deliberately not scaled with gravity (#282), because the
runtime cannot fly a 320 unit climb even where e1m8's physics allows
one. `AR_JUMPVEL^2 / 2g` is a different statement: not "this is hard"
but "this is impossible". At standard gravity it is 46, and e1m2's
seven links ask for 44 to 88. On e1m8, where gravity is 100, it is
364, and that map's one flagged link asks for 41.

```
map     jump links   over apex   apex   what the refusal costs
e1m2        13           6        46    7 nodes, worst spawn 95% -> 92%
e1m6        16           3        46    9 nodes, 95% -> 90%
e1m5        10           3        46    2 nodes, 92% -> 91%
dm3         22           1        46    nothing
e1m8        28           0       364    nothing
dm2         19           0        46    nothing
```

So e1m8's row of the issue was a false positive of the constant, and
the check that would have "fixed" it would have stranded a five node
pocket holding the rocket launcher approach and taken that map from
100 per cent reach to 96.

REFUSING AT THE SEARCH, NOT AT THE HOP. The climb branch in physics
already carries a comment saying navgen only mints these at rise 44 or
less, so the obvious place looks like the jump itself. It is the wrong
place: a bot that declines the jump is still standing at the lip with
a route that says climb, which is the dm2 pin #316 was about. Refused
at the search, BFS routes around it or returns nothing, and the goal
shelves through the path that already exists. The route cache carries
the same refusal, because an adopter must not walk a chain the
searcher could not have been given.

THE COST IS VISIBLE AND IS THE SAME TRADE #316 MADE: routefails on
e1m2 go from 0 to 18 and 19, because a route that used to end in a
bot walking at an impossible ledge now ends in a re-shop.

E1M6 IS WHERE THE DEFECT WAS CAUGHT IN THE ACT, on a map the issue did
not name. Its n59 at '-495 145 104' is entered by a link that climbs
80, and in the two control tapes bots stalled steering at it 1 and 7
times, 7 of that tape's 11 steering targets. Both candidate tapes
record zero. That is the first direct measurement of this class since
the dm2 session that started it.

Ladder. e1m2 three tapes against a same-build control (stalls 46,
engages 16, coverage 561): improved, regressed, improved, with stalls
35 / 67 / 32, engages 23 / 10 / 23 and goal pickups 11 / 8 / 16
against 5. No gate fails twice. e1m6 two controls and two candidates:
stalls 54 and 49 against 78 and 54, engages 33 and 49 against 19 and
43. dm2 and e1m8 carry no over-apex links and are inert by
construction; both were taped anyway and both are inside their own
spread, which on e1m8 means a control tape today that ran 0 engages
against the candidates' 12 and 9.

THE REGEN ROUTE WAS TRIED FIRST AND REFUSED AGAIN. e1m2 regenerated on
current navgen is a good looking graph: zero bad seats against 39,
zero over-ceiling links, worst spawn reach 96 per cent against 95. It
failed two tapes on coverage, routefails and stalls, piling into the
same two door-cause cells as the #308 refusal, with door events 44 to
8 and the map's only lift link lost to a pad the current pad placer
will not seat. The jump ceiling was not what made that regen bad. Its
tapes are committed beside the ladder.

**The seat campaign: nine graphs regenerated past the filter, two
refused (#308).** `SV_CheckBottom` is the test the engine itself
consults in `SV_movestep` before it accepts a walk, and a waypoint
that fails it is one a walking bot cannot arrive at the way the router
assumes. The #250 filter landed on 2026-09-05 and almost every graph
in the tree predates it, so between a fifth and a half of each one was
made of seats the engine refuses. The `FL_PARTIALGROUND` retry from
v3.42 rescues enough of them that this stayed invisible for a week.

One map at a time, each with its own ladder, as the issue asks. Six
shipped, two refused:

```
          bad seats        worst spawn reach        verdict
dm4       48 of 155 -> 0    98/95 -> 98/98          two tapes
dm6       58 of 213 -> 0    94    -> 95             three tapes
dm2       49 of 216 -> 0    99/93 -> 96/95          two tapes
dm3       58 of 259 -> 0    86    -> 98             two tapes
lqdm2     49 of 214 -> 0    -     -> 99             two tapes
e1m7      68 of 179 -> 0    92    -> 88             two + two controls
e1m1       0 of 238         99                      already done
e1m2      39 of 198         95/86                   REFUSED
e1m8      60 of 127         -                       REFUSED
```

dm3 is the largest structural gain in the tree's history on that map:
worst spawn reach 86 per cent to 98, stalls 51 to 28 and 15, engages
8 to 19 and 23, routefails 45 to 30 and 12. Worth reading against
v3.96, which measured a fresh dm3 regen at 78 per cent against the
accumulated graph's 85 and hand-spliced three entry links because of
it. Several campaigns of navgen work separate those two numbers.

THE TWO REFUSALS ARE THE POINT OF THE ISSUE'S WARNING, which is that a
regen has to be judged on a tape rather than assumed to be an
improvement. Both fresh graphs have a clean seat audit and one of them
has BETTER reach, and both play worse.

e1m2 fails four gates on both its tapes - stalls 31 to 71 and 42,
engages 30 to 4 and 18, coverage 563 to 343 and 411, goal pickups 13
to 3 and 5 - and both tapes pile into the same two cells, which the
brief tags `cause: door`: '1040 -500 172' and '1520 -575 170'. The
second of those is already on the watch list as a pre-existing
door-cause stall cell on that map, and reseating a doorway is exactly
the change that would make it worse.

e1m8 needs no second tape. The fresh graph reports 100 per cent reach
with SIXTEEN FEWER NODES, which is the tell rather than the result,
and its top hotspot is 121 hazard deflections at '956 -150 24' whose
nearest node is 398 units away. Routefails 29 to 108, engages 37 to 9,
frags 13 to -4, and a 19 second statue the control does not have.

METHOD NOTE worth keeping. e1m7 has no baseline and is not in the
rotation, so it got four tapes: two controls on the shipped graph as
well as two candidates. After the first pair the regen looked like it
had moved lava 3 to 4 and 8, which is the gate this tree treats most
seriously - and the second control came back at 9. The shipped band is
3 to 9 and the regen sits inside it. A map with no history needs a
control band before a candidate means anything.

**The mode is part of the verdict, and a shut door is not one
(#310).** `probelinks` started its server with `+deathmatch 1` and the
CLI had no way to ask for anything else. The engine strips every
entity with `spawnflags 2048` in deathmatch, doors included, and those
are the maps a co-op companion actually walks: every one of e1m8's
sixteen door links crosses a door that does not exist on the server
doing the verifying. So a link can be honest in the mode the verifier
ran and a lie in the mode the bot plays. The sweep takes `--coop` now,
threaded down to the argument `MatchCtrl::start` already had, and the
verdict file stamps which mode convicted what: `failed` stays the flat
union that navgen consumes, `modes` records each sweep, and a file
with no `modes` block is stamped deathmatch on first write, which is
true rather than a guess because nothing else could run.

The modes disagree, measured on the same 25 links of e1m8 twice:
co-op convicts `n5 -> n2` and deathmatch convicts `n7 -> n98`, and
each passes the other's. A regen now says which sweeps stand behind
its verdicts, so "no convictions" stops reading as "verified".

A SHUT DOOR IS A VERDICT ON THE DOOR, NOT ON THE LINK, and that one
was not in the issue. The puppet walks; it does not press buttons, so
it stops at any slab that happens to be closed and the link goes down
as unwalkable - while a bot standing in that doorway calls
`Argus_TakeDoor`, finds the actuator and presses it, which is the
whole point of typing the link. The first co-op sweep of that e1m8
window convicted seven links, four of them doors. dm2's committed
verdict file already carries the same error from the deathmatch mill:
its regen refuses five of them now rather than pruning or re-typing
five honest door links. The sweep skips the class in both modes and
reports the count, and navgen refuses any conviction that lands on a
door link, which covers the files already on disk.

Door links are therefore unverified in both modes, and stay that way
until the puppet can work a button.

**Do not draw a link through where the door will be standing (#309).**
A sliding door does not leave the world when it opens. It slides
beside the hole it was filling, keeping its own lip inside that hole
because `doors.qc` travels size minus lip, and it can come to rest on
the very line the graph draws through the doorway. e1m2's silver key
pair is the found case: shut across x 881 to 951, open across x 943 to
1013, and the n84 to n90 walk link crossing the frame at x 948, which
is inside both. The runtime learned to steer through the doorway
rather than at the node beyond it in #303, and that covers the
symptom, but it spends a frame of steering every time and it cannot
make a link honest.

NEITHER HULL CARRIES THE SLAB. Hull 1 has no `func_door` brushes at
all, so the sampler reads the doorway and the recess alike as clean
floor, and hull 0 only has the compiled position. It is geometry
nothing downstream can see unless it is handed over, which is the
same shape as the hull-0 liquid classification: navgen works the
parked box out once, before link building, and `beeline_ok`'s pass in
6b refuses to draw a line through it. A link that crosses where the
slab will stand is a lie exactly when a bot wants to use it, because
a door is open when you are walking through it.

DOOR_START_OPEN, which the report in #303 had backwards. `doors.qc`
sets `pos2 = pos1 + movedir * (|movedir . size| - lip)` and then SWAPS
them for a START_OPEN door, so such a door is compiled at its OPEN
position and its shut one is a travel away. Seven doors across the
rotation are built that way - dm2 three, e1m7 two, e1m1 and e1m2 one
each - and the report called the hole a parked slab for every one of
them. That maths lives in one function now, and both the veto and the
report read it.

Two things measured and not kept, recorded so nobody re-runs them. A
waypoint promoted at the centre of each opening, so Dijkstra would
stop there and cross the frame in the middle: it reaches zero parked
links on every door map, and so does the veto on its own at the same
worst-spawn reach, and on e1m1 it forced a seat onto the t15 doorway
at '1096 1024 -247' on the lip of the teleporter drop, where its
ladder came back with 83 hazard deflections and 17 stalls in that one
cell and coverage 391 down to 272 (that tape is not committed: the run
name collided with a tape from #303 and overwrote it, and the #303 one
was restored rather than the variant kept). And splitting the parked box into
the lip inside its own opening plus whatever part covers sampled
floor, on the grounds that a slab retracting fully into a 14 unit wall
blocks nothing: true, and worth nothing, because e1m6, e1m1, e1m2 and
e1m5 come out node for node identical either way.

The shipped graphs, measured against their own BSPs with the
START_OPEN correction applied, and what a regen on this navgen does to
them. Only e1m1 is regenerated here; the rest is the pre-flight for
the per-map campaign in #308, so those regens land on a known figure
rather than discovering this one at a time:

```
        parked links   after a regen      worst spawn reach
e1m6      38 of 212        0 of 174        95% -> 95%
e1m2      13 of  64        0 of  31        95% -> 97%
e1m7      67 of  69        0               92% -> (regen pending)
e1m5       6 of  36        0 of  30        92% -> 92%
dm2        4 of  28        0 of  12        99% -> 95%
e1m1       5 of  64        0 of  59        99% -> 99%
e1m8       0 of  16        0                 -
```

LADDER, e1m1 twice against the tape from the build before it, since
that is the only graph this changes and the QC is untouched. Improved
then parity, no gate failing either time: engages 17 to 25 and 17,
coverage 391 to 415 and 412, hazard deflections 171 to 135 and 147,
stalls 41 to 40 and 36, acquisitions 5 to 18 and 16, freezes 0 and 1
bounded, every bot positive both times.

**Some platforms are wearing door clothing (#281, #119).** e1m1 played
an empty match: zero engagements, zero weapon pickups and zero deaths
in over two minutes, with half the graph never visited. The map is a
chain, and the link nobody modelled is `func_door *3`, a 126 by 126
slab with `angle -2` that drops 230 units when either of its two
buttons is pressed. Its closed top face IS the start area's floor, and
riding it down is the only way out of that section. navgen models
`func_plat` and reads `func_door` only for door AABB typing, so the
slab was invisible to it and the crossing came out as ordinary walk
links over a hole no hull can see. The puppet convicted both of them,
stopping at the exact cells the bots pinned in, and dropping them
without replacing them takes that spawn's reach from 100 per cent to
5, because they are the section's only connection to the map.

navgen now treats a big vertical `func_door` as what it is: pads at
both faces and a lift link EACH WAY, because a mover carries you in
both directions and it is the actuator, not the graph, that decides
which way it is going. The size bar keeps bars, gates and rising
grates out of the class - a slab under 64 units on either axis is not
a floor a 32-wide body stands on, and travel under 48 is served by a
step or a jump-up already. At runtime the lift wait learned two
things. It fires for a hop that goes DOWN, which it never had to
before because every lift link navgen could emit ran bottom to top. And
it rides a door: board whenever the slab's own top face is within a
step of our feet, which is direction-agnostic and needs nobody to know
which way the slab travels, and anywhere else ask the door handler for
the button, which is the thing it has been finding and pressing since
v3.33. That is the runtime half of #119 - press that, then cross here.

A SLIDE IS NOT A TELEPORT, and that is the second half of why e1m1 lay
about its geometry. `beeline_ok` probes 32 units either side of a
link's line, because walkmove slides along walls and a line that clips
a corner is still walkable when floor continues just beside it. As a
grade for a link the fine graph already found, that is right, and
three attempts to narrow it are in the graveyard. As the ONLY referee
for a knit stitch, which by construction invents a link across ground
nothing walked, it is not: on e1m1 it reset its own bad-sample streak
by finding the ledge on the FAR SIDE of an eight unit wall. A knit
walk stitch now needs honest floor under every step of its own centre
line. The jump stitch below it still takes the short-void cases, on
the same 200 unit void envelope it has always had.

A LENGTH CAP ON THAT JUMP STITCH WAS TRIED AND REVERTED, and it is
worth recording because it nearly shipped. The first cut refused a
flat stitch longer than the jump model's flat range, on the grounds
that a level jump cannot outrun it. That bounds the wrong quantity:
the criterion beside it bounds the VOID, and a 250 unit stitch over a
48 unit gap is a walk with one hop in it, which is what a jump-typed
link means - the runtime fires at the lip, not at the far node. On
e1m1 it looked harmless, one dead-end node fewer. On e1m6 it cut the
load-bearing stitches and took worst spawn reach from 95 per cent to
43, on a map whose graph is otherwise reproducible from scratch.
Tightening the void envelope to the same figure was measured too, and
cost e1m6 47 points on its own, because several of those stitches sit
at a 192 unit void.

e1m1 regenerated: 238 nodes, worst spawn reach 99 per cent against a
graph whose reach only read 100 because of the two lies, one stranded
node stripped honestly, and zero seats that the engine's own bottom
test refuses (#308's audit reads 0 of 238 against 63 of 223).

LADDER. e1m1 improved on all seven gates three times: stalls 68 to 45,
32 and 41, engages 0 to 24, 16 and 17, kills 0 to 10, 8 and 9, frags
-2 to 7, 8 and 8 with every bot positive, coverage 178 to 376, 238 and
391, lava 2 to 3, 0 and 1, boards 4 to 7, 9 and 7. The third tape is
the shipped graph, after the length cap came back out. dm3, the other
lift map,
improved as well: stalls 51 to 25, engages 8 to 22, frags 1 to 5, no
freezes. dm2 read regressed and then mixed, and a control tape on
byte-identical shipped code reproduced every failing gate and was
worse on two of them - stalls 51, goal pickups 4, Romero on 0 frags,
lava 5 - so those gates belong to that map's documented variance and
its stale baseline, not to this change.
**A body in the air is not travelling in a straight line (#117).** The
projectile lead has always been linear - target velocity times time of
flight - and it is correct for a body standing on something. For one
in the air it is not, because that body is under constant downward
acceleration and lands 0.5*g*t*t short of where the straight line puts
it. At gravity 800 and a rocket at 400 units that is 64, which is more
than the whole 56 unit player hull: the shot sails clean over the head
of a jumping target, and over one that somebody else's rocket has just
put in the air, which is where most of dm4's air time comes from. The
term is now subtracted, with live gravity rather than an assumed 800,
because e1m8 runs 100 and the correction would be eight times too big
there. Swimmers and flyers are exempt: a body at waterlevel 2 or more
is held up by the water and a scrag is MOVETYPE_FLY, and neither is
falling.

The floor clamp underneath it - the one that stops a long lead on a
falling target dragging the aim point under the world - now tests
AIRBORNE rather than merely descending. It had to: a target rising at
100 with an 800 unit rocket flight is 176 units lower than the
straight line says, and the clamp is what turns that into a splash at
its feet when it lands rather than a shot into the ground. That is
the issue's second bullet, and it was already in the tree under a
condition that could not see the case.

LADDER, two maps and three tapes. dm4 twice: frags 14 to 34 and 28,
kills 31 to 36 and 36, engages 95 to 98 and 105, coverage at parity,
lava 1 and 6 against a band of 2 to 7, and no gate failed twice -
stalls read 14 and then 4, K/D spread 5 and then 9. dm2 came back at
parity with every bot positive and spread 2. Goal pickups read lower
on every tape and the reason is in the same briefs: deaths and
battle-grabs both rose, so the errand counter moved into the
mid-combat grab counter while total acquisitions held.

**The lightning wade test reads our depth now too (#18).** The
selector refuses the LG when the bot is deep enough that
`W_FireLightning` would discharge every cell into its own feet, and it
was mirroring that test against `self.waterlevel`. That field belongs
to the engine for a bot, and `Argus_SelectWeapon` runs on the AI tick,
which `FrameAll` calls before `Argus_Physics`: the number it read was
whatever `SV_CheckWaterTransition` left at the end of the previous
server frame, a flat 1 for any body in liquid and never a 2. The test
was answering yes in exactly the case it was written to refuse. It
reads `ar_wetlevel` now, which is the same honest 0 to 3 depth the
discharge test itself sees, because the weapon frame runs as a think
inside `SV_Physics` after `Argus_Physics` has written it. The
`watertype` half stays as the second condition: it is engine owned and
correct, and it covers the frame before a freshly spawned bot has run
any physics at all.

LADDER, and the useful half of it is one map. dm4 is the only map in
the rotation that exercises this branch: e1m2 has no lightning gun at
all, and dm3 and dm6 each carry one that no bot selected in any tape
on either arm. On dm4 the effect is visible and is the intended one -
lightning selections fall from 10 to 4 and 7 per tape while lightning
pickups stay at 10, so bots acquire it as before and stop choosing it
while submerged. First dm4 tape improved on all seven gates (stalls 5
to 1, frags 14 to 28); the second passed six with stalls at 11 against
a baseline 5, which is the top of that map's own 1 to 11 band this
session. dm3 and dm6 each wobbled on the same stall gate with the
branch provably never running, which is what those maps do.

**The rest of the pointfile overlays, and one of them found something
(#254).** Four audits join the drawing tool, all of them questions that
a top-down plot cannot answer and a number cannot either.

`--what badseats` runs the engine's own `SV_CheckBottom` against every
shipped seat, which is the test navgen gained in #250. It found that
every graph in the tree predates that filter: e1m2 carries 39 of them,
dm4 48, dm2 49, dm3 58, e1m1 63, between a quarter and a third of each
graph. A fresh regen of e1m2 through current navgen draws none, which
is both the instrument validating itself and the finding: those seats
are the class that put a waypoint 14 units past a lava lip on e1m6,
and they are still in every shipped graph until each map's next regen.

`--what surface` draws each swim exit with the water surface between
the submerged seat and the lip, and prints the climb in units, which
is the measurement that cost most of a session to get by hand.
`--what diff --against <other>.qc.json` draws the nodes a regen added
and removed, matched by position because indices shift every
generation. `--what probe` draws the links the puppet refused, read
from `argus_nav_<map>.probe.json`.

The colour trick works. `--pad --colour N` buries fifteen filler
points in solid geometry before each drawn point so every drawn point
lands on the same entry of the `(-index & 15)` cycle; the file is
checkable and every drawn point in a padded dm2 overlay lands on the
colour asked for. Whether that colour looks the way you expected still
needs a listen client, which is true of the whole tool.

THE PORTAL SPIKE, measured rather than argued, and the answer is no.
Portal space is three to ten times the size of the waypoint graph
(436 leaves on dm4 against 155 nodes, 1505 on e1m2 against 198), only
a third to a half of the open leaves have anywhere a player can
actually stand (33 per cent on dm2, 45 on dm4, 49 on e1m2, 57 on dm3),
and 56 to 75 per cent of the standable ones already hold a nav node.
The uncovered remainder is mostly leaf subdivision inside rooms the
graph already covers rather than rooms the sampler misses. So the
payoff is unproven while the cost is real: `.prt` is not in the
shipped BSP, so leaf adjacency would have to be rebuilt by clipping
each leaf's planes against its siblings, and a walkability filter
would then throw away half of what that produced.

**The guard that never fired, and the field it was reading (#256).**
The e1m2 co-op companion pins in water and swims in a circle for the
rest of the match, on every build measured including current main.
#248 shipped a guard for exactly this: a swimmer whose steering node
stands more than a water vault above it has been displaced, so re-plan.
The guard has never once fired.

It tests `self.waterlevel`, and for a bot that field belongs to the
engine. `SV_CheckWaterTransition` runs at the end of every
`MOVETYPE_STEP` entity's physics and leaves a flat 1 in it for a body
in liquid. `Argus_Physics` computes the honest 0 to 3 depth from three
`pointcontents` at feet, origin and eyes, but `FrameAll` calls
`Argus_AI` BEFORE it, so a test on the AI tick reads the engine's
number from the end of the previous server frame and never sees a 2.
A probe printing one line per second while wet returned 44 samples in
water with the feet correctly reading `CONTENT_WATER` and waterlevel
reading 1 in every one, while the steering node sat at
`'1041 257 308'` above a bot floating at z 171 - the same seat #248's
own commit message names. The cure is the one `ar_feettype` already
uses: QC keeps its own copy in `ar_wetlevel`, written where the depth
is computed, and the guard reads that.

Two conditions had to be added once the rule ran for real, and each
was paid for by a tape. Ground under the feet means the bot can walk,
so without that test the guard fires at every pool bank a route
crosses and e1m2 deathmatch came back at coverage 410 to 426 against a
control band of 494 to 563, with an abandon loop where bots used to
wade out. And the adrift clock resets on GROUND alone: two versions
keyed it on depth, one under waist height and one on dry feet, and the
swim bob defeated both by crossing the surface several times a second,
which is the same flicker the issue's swim event count is measuring.
Co-op tapes on those versions sat in the flooded court for the whole
match with 730 and 691 swim events.

LADDER. e1m2 co-op, six paired 185 s runs against current main: the
control pinned in four of six, the fix in none. Swim events 11735
against 736. Worst tape 26 cells against 95. That is the bimodality in
the issue closing: every tape on the fix works the map.

  dm3   improved, all seven gates: engages 8 to 17, routefails 45 to
        26, coverage 376 to 392, every bot positive
  dm4   improved, all seven gates: frags 14 to 27, spread 5 to 3, lava
        6 and in band
  e1m2  deathmatch, two tapes: one parity on all seven, one with
        coverage 440 against a control band of 494 to 563. Watch it.

RECORDED, NOT FIXED: the lightning selector's wade test (#18) reads
`self.waterlevel <= 1` in `Argus_SelectWeapon`, which also runs on the
AI tick, so it has been answering on the engine's number in exactly
the waist-deep case it was written to refuse. That is a combat change
and wants its own ladder.

**An open door is still a brush.** Hull 1 carries no `func_door`
brushes, so the sampler reads a whole doorway as clean floor and navgen
mints a beeline through it wherever the two waypoints happen to sit.
That line can run well off centre, and a sliding door does not leave the
world when it opens: it parks beside the hole it was filling. On e1m2
the silver key pair's east half is shut across x 881 to 951 and open
across x 943 to 1013, and the n84 to n90 walk link crosses the frame at
x 948, dead inside the slab's open position. Fifteen of e1m2's 64 door
links are drawn through an open slab, and so are four of dm2's 28, five
of e1m1's 48 and six of e1m5's 36.

The co-op companion pays for it on every e1m2 tape. On the four tapes on
file that doorway holds 21 to 42 per cent of every position sample of
the whole match, and a fresh probe on current main has the bot pressed
against the open slab's south face at '936 -1064 440' with `ar_door` set
and the door hop live. The lab puppet walked the same link clean and
reported it healthy, which is not a contradiction: both halves of that
pair carry spawnflags 2048, the engine strips those entities in
deathmatch, and `probelinks` runs a deathmatch server. The link is
honest in the mode it was verified in and a lie in the mode the
companion plays.

The cure is one aim point. A door hop steers through the DOORWAY now
rather than at the node beyond it. `absmin` and `absmax` follow the slab
wherever it has slid to and `pos1` is where it sits when shut, so the
difference walks the box back onto the hole it fills, and the thin axis
of that box is the wall it lives in. The steer lasts one frame by
design: the trace that takes the door runs again on every frame the slab
is still on the line, so the aim holds itself exactly as long as the
obstruction does, and `Argus_DoorPast` refuses it the moment the bot is
out the far side. A first cut held the aim across frames and kept
`ar_door` until the bot was through; e1m2 came back with coverage 563 to
335 and engagements 30 to 8, because holding a door drags a bot to every
frame it traces on a map with 26 of them. The one-frame version is the
shipped one.

Navgen reports the same geometry: it models each door's open position
from its angle, size and lip and names every door link drawn through it.
That is the gate that would have caught this, and it prints on every
regen.

LADDER, 185 s each against the shipped baselines. dm2 parity on all
seven gates. e1m1 improved, with engagements 0 to 4 and the first seven
item grabs that map has recorded. e1m2 parity on six, with stalls 31 to
40 against a control that runs 31 to 50 on identical code, so the stall
gate is reading that map's own noise. Co-op is harder to measure than it
should be, because the water pin of #256 eats roughly two thirds of
e1m2's co-op tapes before they reach the door at all: of six paired
runs, four pinned in water on both arms equally. The pair that got
through read the doorway at 37 per cent of samples on main and 27 on the
fix.

**A pinned bot is stuck too, and being embedded was only half of it
(#271).** `Argus_Unstick` shipped in #262 against one signature: origin
inside world solid. A dm2 tape has Joe Rogan at exactly
'2526.7 -40.9 -66.0' at spd 0 for 91 seconds of a 185 second match, not
inside solid at all, just pinned against geometry six units proud of a
node floor. Nothing could reach him: `pointcontents` reads hull 0 so it
cannot see a hull 1 wedge and cannot see bmodels in any hull, routefails
were 0 so the trapped rule could not fire, and stall recovery ran 73
times without freeing him. There are two signatures now and both require
that the bot has not moved, which was always the part doing the work:
embedded keeps its 3 seconds, pinned needs 6 seconds plus at least four
stalls inside the window. The stall count is the only honest
discriminator available here, because this runs on the AI tick and
`Argus_AI` clears `ar_liftwait` at the top of every frame for the ride
branch to re-earn, so a hold flag read from this function is always 0.
The stall detector runs later, with the flag back, and already skips
`ar_liftwait`, `ar_hoplift` and fighting, so every designed hold and
every duel is excluded for free. A throwaway probe build confirmed the
split: on dm2 a bot reached an 8.0 second window with zero stalls, which
is the bounded lift-wait give-up and is correctly ignored. The console
line now names which class fired, and a later dm2 tape caught the real
thing: `ARGUS Romero unstick pinned '2633.0 -143.0 120.0'`, at the NE
stair lip that this project has on record losing a bot 92 seconds. The
freeze was bounded at 11.3 seconds.

**Rescue destinations have to fit, and must not be occupied (#268).**
The same function sampled `pointcontents` at one point of a nav node and
warped. One point says nothing about a 32x32x56 hull and nothing about
bmodels, and nav nodes are the highest traffic points on a map by
construction, so the nearest free-looking node is a fair bet for where
somebody is standing. Landing on one leaves two players interpenetrating,
which is the bug the function exists to cure, and in co-op one of the two
is a human who cannot unstick themselves. Candidates now pass the eleven
point box test the catchup warp has always used and an occupancy check,
and the arrival telefrags like every other arrival in the tree. Not in
co-op: the occupancy check already keeps the spot clear and the only body
it could plausibly find there is the team mate. An embedded bot falls back
to the old looser geometry test if nothing passes, because it is in a
worse place than any waypoint, but the occupancy rule is never relaxed.

**The anti-embed nudge stops teleporting bots through walls and between
floors (#267).** `Argus_BodyBlockCheck` flattens the separation vector to
test horizontal distance, then built its destination as
`cl.origin + to`, which inherits the other player's height. A bot on the
dm4 walkway at z -232 directly above someone on the pit floor near z -380
read a horizontal distance near zero and warped 150 units down, and the
one underneath warped up into the walkway solid. It now keeps its own z
and verifies the spot before committing, because `setorigin` does not
collide and 36 units along the separation vector goes through the wall in
any corridor, which is the common case in co-op where the companion
escorts through doorways. If the spot does not fit the bot does not move
and the sidestep below resolves it against real collision.

Ladder: dm4 improved on all seven gates (lava 4 parity, stalls 6, engages
85, frags 25, spread 4, no freezes). dm2 needed a control on main to read,
because its shipped baseline is many builds old: two candidate tapes ran
stalls 47 and 23 against a control of 40, and lava 2 and 8 against 4, so
both bracket it. The stale baseline accounted for the rest.

**Two telemetry lines no parser could read (#269, #278).** The co-op
catchup warp announced itself with an `ARGEVT` prefix and the verb
`coop`, which was never in the parser's closed vocabulary, so the regex
found no match at any split point and the line was dropped in silence. A
`setorigin` that teleports a companion across the level is the single
most consequential thing a co-op bot does to itself, and it appeared in
no brief, no total and no gate. It is a plain `ARGUS` line now, the way
`shove`, `unstick`, `watch` and `sprintjump` already do it, and the
parser counts it. It counts `unstick` too, which had the same gap since
#262: both rescue teleports are now visible, which is what makes a build
that warps ten times a match instead of once look like the movement
regression it is rather than a coverage improvement.

Backpack goals emitted `ARGEVT <name> goal ` with nothing after the verb,
7 per cent of one dm2 tape's goal telemetry. `DropBackpack` never assigns
a classname, which is why `Argus_ItemValue` identifies packs by touch, and
the goal line never got the same treatment. It falls back to `backpack`
now, so the per-class goal map can show pack shopping for the first time:
a 90 second dm2 tape reports `backpack: 2`. The v3.45 fresh-pack bonus has
finally got an instrument that can see it being chosen.

A test now asserts that every `ARGEVT` verb the QC emits parses, across
both emission forms, and names the file when one does not. Reverting the
`coop` line makes it fail with exactly that verb. A sweep of the whole
tree found no others.

**A bot at a locked door it has no key for now gives up (#270).** The
keyed test sat above the give-up in the else-if chain, so a keyed door
could never reach the timeout: `ar_door` stayed set, the next frame
matched the same branch, and `ar_liftwait` went back on. That is the
physics level hold, friction only and no wish, with steering removed, so
the bot was a statue with no exit condition. `Argus_CoopCommitKey` does
not rescue it, because five of its six paths return without touching
`ar_door`, and the worst of those is the intended design: "team mate
already has the key, let them open it" was implemented as standing still
in front of the door forever, so in the normal co-op sequence, where the
human picks up the silver key, the companion froze at the door and could
not even follow the person carrying it. The give-up is tested first now,
and keyed doors get 25 seconds from `Argus_TakeDoor` rather than 8,
because fetching a key is a real errand. The give-up also shelves the
door for 20 seconds while it is still locked against that bot, or
clearing `ar_door` would simply let the detection traceline re-take the
same slab next frame and re-arm the whole deadline.

This path is co-op only in practice. A probe build instrumenting the
keyed branch recorded zero entries across a 120 second e1m2 botmatch,
because the router already refuses links a key door blocks, so nothing
steers a deathmatch bot into one. It is unverified in play and stays that
way until #259 lets co-op be driven headless.

**UseStandPoint says when it is guessing (#277).** Four of its five exits
return a validated floor position with line of sight to the brush. The
fifth returns the brush bounding box centre, which for a `func_door`,
`func_button` or `trigger_changelevel` is a point inside the brush, and
it returned it through the same bare vector as a success so no caller
could tell. `ar_standok` is set beside the result and read like
`trace_fraction`. The caller that pays for it is the solo campaign level
exit, which pushed a 60 second `GOAL_FETCH` at whatever came back: a
guess now gets 15 seconds instead, so the bot tries, fails and gets on
with the match rather than pushing at the inside of an arch for a minute.

Ladder: e1m1, the door-heavy map, at parity with its control (stalls 68
against 67, hazards 273 against 260, no freezes either side). Neither
change alters the non-keyed door path at all, which is why it is parity:
the reorder only moves a test that is false for an unkeyed door, and the
new shelf returns immediately for one.

**The lab stops asserting things it has not checked (#272, #273, #276,
#279).** Four ways the advice layer spoke with more confidence than its
evidence supported.

Zero engagements was diagnosed as a dead fire path, at priority 1,
naming three combat call sites, without ever asking whether the bots
were near each other. On the e1m1 tape that prompted this, no two bots
came within 1396 units all match: there was nothing to perceive and
nothing to shoot, and the answer was navigation. The brief already holds
every track, so closest approach is a few lines over data in hand. It is
reported unconditionally now, and the step it feeds points at nav when
the bots never met and at the fire path when they did. Both directions
are covered by tests against real tapes, because a longer e1m1 tape has
them passing within 79 units and still not fighting, which genuinely is
a combat question.

Stalls need low speed and freezes need low speed, so a bot can oscillate
inside a 220 unit box at 355 u/s and score zero on both while losing
seven per cent of its match. The only residue is hazard deflections,
which the lab deliberately reads as the guard working. `confine_max_sec`
ignores speed and asks the honest question instead: how long did the bot
fail to get anywhere. A 0 u/s freeze and a 355 u/s oscillation are the
same family and this reports both. Informational, not a gate, because a
fight or an item orbit looks the same.

dm4's rocket-jump pad node indices were printed on every map with a quad,
including dm2 and e1m5. Node numbers only mean something inside one graph
and the tree already records that they shift on every regen, which is why
probe verdicts are persisted by coordinate. They had also drifted from
the nav data they claimed to describe, because no test can compare a
prose string to a graph. The note is computed from the map's own rocket
link count now, and says the opposite when there are none rather than
advising something the graph cannot support.

Compare output names the run it resolved as the baseline. Every gate in a
report is a statement about that one tape, and a baseline many builds old
turns ordinary drift into a verdict: this session lost time to exactly
that on dm2, where the shipped baseline predates seventeen builds and a
control run on main was needed to tell a real regression from a stale
comparison. Baselines added for e1m1 and e1m2, the maps the co-op work
runs on.

One correction to #273: refusing a verdict when a map has no baseline was
already true in the tree. `resolve_baseline` errors for any map without a
row, and `matrix_experiment` turns that into `compare: null` with no
gates and no next steps. Verified live on e1m1 and e1m5. The issue was
filed against a stale running binary, which is its own recurring problem.

**The nav instruments can finally see a graph that does not cover its
map (#275, #280).** Every existing nav check measures connectivity, and
connectivity is exactly the property a too-small graph preserves
perfectly. Islands, strongly connected components, directed reach, sink
detection: all of them ask about the relationships between nodes that
exist, and none can notice the ones that do not. A graph of one room
scores 100 per cent. e1m5 ships 38 nodes covering one corner of the
level, with four of five deathmatch spawns outside the graph's bounding
box, and both `argus_reach` and cartograph called it healthy at 89 per
cent worst spawn.

Distance from a spawn to its nearest waypoint cannot be faked that way,
because it is a statement about the map rather than about the graph's
internal structure. `argus_reach` measures it now and fails the gate past
200 units, and it reports the give-away the old output already contained
without noticing: several spawns resolving to the same node. On e1m5 it
reads "7 of 10 spawns are over 200u from any waypoint, worst 1595u" and
exits 1 where it used to exit 0. It also caught two spawns on e1m8 at 606
and 488 units. dm4, dm2, dm6 and lqdm2 all still pass, so CI's own
lqdm2 gate is unaffected. Cartograph raises the same finding as an
implication, plus one for a map where most control items are off graph,
which reads identically today whether one item is off or eight.

The edict estimate counted the raw entity lump while navgen counted live
entities, so two tools in the same lab disagreed by most of the number on
every single player map. An untargeted `light` is removed by misc.qc's
`light()` the moment it spawns, and id's maps are full of them: 181 of
e1m1's 369, 195 of e1m5's 536, 308 of e1m8's 495. Cartograph reported
e1m1 at "592 of 600, keep a margin", eight edicts spare, when the live
figure is nearer 400. A reader acting on that would decline to
regenerate a graph that badly needed one, which is exactly what happened
when #274 was first diagnosed. Cartograph uses navgen's rule now, from a
single shared definition rather than two implementations that had already
drifted, and the note says how many entities free themselves and which
ceiling it is talking about: navgen budgets against 500, leaving 100 for
bodies, missiles and temp entities, while the engine's hard limit is 600.
Those were always two different questions presented as one metric.

**e1m5 gets a graph of its level (#274).** The shipped
`argus_nav_e1m5.qc` was an artifact of the collapsed-cap era that
`spawns_an_edict` fixed: 38 nodes in a 1056 by 1216 box on a full sized
map, zero door links on a map with 23 doors, and four of five deathmatch
spawns outside the graph's own bounding box. Every other e1m map was
regenerated after that fix and this one was missed. A regeneration today
produces 155 nodes spanning the whole level, and the item distances tell
the story better than the node count:

```
                          shipped   regen
weapon_rocketlauncher       516u      30u
item_artifact_super_damage 1005u      44u
item_health (mega)         1611u      34u
item_armor2                1213u      17u
weapon_supernailgun         922u      29u
weapon_grenadelauncher      794u      29u
item_armor1                 583u      42u
```

Those are the eight the issue listed as `off_graph`. Every spawn now
resolves to its own node, none further than 200 units, so the new
coverage gate passes it where it failed the old graph at 1595 units. The
graph gains 36 door links, 6 train links, 2 lift links and a swim link
where it had none of the first three. Edict estimate 496 of 600.

Ladder, one control on the shipped graph and two candidate tapes,
because the project's own rule is two tapes or a control:

```
                 control   regen1   regen2
engages                6        5       20
frags                 -1       -1       +6  (all positive only here)
stalls                30       36       17
acquisitions           3       17       20
coverage             218      301      328
routefails             7        0        0
freezes                9       12       10   (all bounded, ~7 s, same cell)
quad goal selections   0        4        4
```

Consumption, coverage and routefails improve decisively and in the same
direction on both candidate tapes. Engagement and frags swing hard, which
is this map's variance, but never below the control on aggregate. Freezes
are flat within noise and sit on a cell the control has too.

One new residual, and it is new only because the links did not exist
before: the second tape flags 4 lift/train waits with zero boards. That is
the v3.65 board accounting doing its job on infrastructure this graph has
only just acquired, and it wants its own look at the boarding gate rather
than a nav change. e1m5's baseline is now `ab_e1m5_regen2`.

**A tape that spans a level change is no longer briefed as one match
(#266).** The engine restarts `time` at a level change, so a co-op
session that plays 133 seconds of e1m2, exits, and records 3 more on
e1m3 was briefed as a 1.5 second match at 12,326 u/s. Three things broke
at once: duration came from the short trailing segment while distance was
summed over the whole file, counter fields like `st` and `gl` reset so
`totals.stalls` read 0 while `events.stall` counted 40, and every
geometry-joined field was computed against one level's graph for a tape
that held two. The existing wrong-map guard could not catch it, because
that one only fires on a refused spawn and both spawns here succeeded: it
was a deathmatch-only assumption, and reaching an exit is the normal end
of a co-op session.

The parser splits on level changes now and briefs the busiest segment,
saying so in a flag at the top. That tape reads 133.4 seconds of e1m2 at
117 u/s with `totals.stalls` 40 against `events.stall` 40, so the brief
no longer contradicts itself inside one object. A second, independent
guard flags any average speed over 400 u/s as a parsing defect rather
than printing it, because a Quake player caps near 320 and that is worth
catching however it happens.

**Ballistic predictions read the live gravity (#282).** `world.qc` sets
`sv_gravity` 100 on e1m8, Ziggurat Vertigo, exactly as stock id does,
and the engine applies it to bots for real because they are
`MOVETYPE_STEP`. Every prediction Argus made assumed 800, so a bot there
planned for a 45 unit jump it could actually make at 364: a factor of
eight, on the one map whose whole design is floating.

`Argus_Gravity` reads the cvar rather than caching it, because worldspawn
sets it after `Argus_Nav_Spawn` runs and anything latched at init would
hold the previous level's value. Five sites use it: the gap jump
simulation, which also scales its own time window because a 270 launch
is airborne for 5.4 seconds at gravity 100 and a fixed 1.25 second window
cut the flight off while still rising; the grenade loft, whose 800 was
hidden inside the constant 900; the rocket jump pitch bands, since
horizontal reach for a blast goes as vx/g so the same pad needs eight
times less push; and the water vault reach, where 320 up apexes at 64
under gravity 800 and 512 under 100. Every one reduces to its old
constant exactly at 800.

navgen is gravity aware the same way, and applies `world.qc`'s own rule
automatically rather than leaving it to a flag, because a regen that has
to remember a flag is a regen that will one day forget it. `--gravity`
overrides for experiments, and a regen now prints the gravity it modelled.
A fresh dm4 regen is byte identical to one from before this change, so no
shipped graph can move.

Ladder, two tapes a side. On e1m8 against a control on main: stalls 38 to
22 and 26, acquisitions 10 to 14 and 17, frags -1 to +4 and +2, lava 4 to
0 and 4. The mechanism is visible in the jump counts, 45 down to 29 and
33: the honest arc refuses gap jumps the 800 model approved, and the
stalls those failed jumps were costing go with them. dm4 is at parity or
better, lava 9 then 2 against a baseline of 4, which is this map's
documented swing and cannot be otherwise, since every formula is
arithmetically identical at 800.

**What this does not fix, measured rather than assumed.** The issue
predicted the seven off-graph control items on e1m8 would become
reachable. They do not, and gravity was never what refused them. navgen
seats 191 waypoints there spanning z -344 to +416, and the route-poison
prune strips 123 of them because the upper half of that map is a set of
mutually stranded pockets with no feasible escape by any modelled move.
The shipped graph, a fresh regen on main and a fresh regen with correct
gravity all span z -752 to -296 for that reason. Connecting e1m8's upper
level is a fragmentation campaign, not a constant.

The e1m8 regen is therefore **not shipped**. It laddered decisively worse
than the shipped graph: 1 engagement against 12, 65 routefails against 25,
coverage 198 against 248. The reason is recorded in navgen beside
`JUMPUP`, which is deliberately held at its tuned value instead of being
scaled: gravity 100 permits a 320 unit climb, but landing one means
arriving within 44 units of the apex after a 5.4 second flight, and the
regen that tried it fired 72 jumps and 58 stalls. Emitting links the
runtime cannot walk is the mistake the lift statue taught.

**Two physics-level holds with no way out (#257).** Both of the longest
freezes on record are a bot standing still with `ar_liftwait` set, which
suppresses the stall detector and removes steering, so the bot emits
nothing at all while it does it. 144 s of a 190 s match in one tape,
87 s in another.

The train ride hold treated standing on a car as progress
unconditionally, resetting its 15 second give-up every frame. A bot
aboard a car that is parked - docked at a corner, sitting out its wait,
or stopped at the end of its path - therefore held forever. The 87 s
freeze begins the instant `ARGEVT train` fires and a 322 unit rise puts
the bot on dm2's east deck, which is that mechanism exactly. Riding is
progress only while the car is moving now.

The lift give-up lived inside the positional gate that decides whether to
park, so a bot carrying `ar_hoplift` while it was not over the pad never
reached its own deadline. v3.56 hit this shape and treated it by widening
the gate from 56 to 200, which moved the boundary without removing it.
The clock is tested first now and the parking second.

That split matters more than it looks, and the first cut got it wrong.
`ar_liftstart` is stamped when the hop is planned, so it already includes
the walk to the pad: hoisting the 8 second bound gave up on bots still
legitimately walking there, cooled the pad behind them for 25 seconds and
shelved the goal. dm2 came back with `mover_waits` 0, `boards` 0 and
stalls 74 against 34, the lifts simply stopped being used. There are two
deadlines now, 8 seconds for waiting at the pad and 20 for carrying the
flag at all, and dm3 boards 3 of 3 lift waits against a baseline of none.

**The freeze gate weighs duration (#257).** A tape where one bot stood
still for three quarters of the match scored "1 freeze" and passed, next
to a tape with five short ones that would have failed. `freeze_total_sec`
is in the totals and in the gate, so losing 30 seconds more than the
baseline fails whatever the count says.

Honest limit on the ladder: neither hold can be reproduced on demand
headless, and dm2 is currently too noisy to judge movement on. A control
on main reads 66 stalls there against a baseline of 34, with one chronic
grate-room cell contributing 42 to 48 of them, and both candidate tapes
recorded `mover_waits` 0, meaning the changed code never executed in
either. dm3 is where lifts actually fire, and it came back at stall
parity with engagements up and every wait boarding.

**One link slot per pair (#249).** Every typed link builder calls
`Argus_NavLink` itself and then sets its own mask, and navgen emitted the
walk graph and then each typed list unconditionally. A pair appearing in
both was therefore emitted twice and consumed TWO of a node's eight link
slots for a single destination, with one slot masked walk and the other
masked train, swim or rocket, so which one the router picked came down to
slot order. dm3 ships 5 such pairs and e1m5 6. No node overflows today,
but both maps carry nodes sitting exactly on the 8 cap, where a wasted
slot means the clamp evicted a real link to make room for a duplicate.

The walk pass keeps its slots and the typed passes skip what it already
emitted, deliberately in that order: reordering would reshuffle slot
assignment on every map, and in each observed case the survivor is the
link Dijkstra verified and the cheaper one to execute, a jump any bot can
take rather than a rocket hop gated on RL, rockets and health. A regen
now reports how many it skipped, and a fresh dm4 regen stays byte
identical because dm4 has none.

The shipped graphs keep their duplicates until their next regen. An e1m5
regen carrying only this change differs by exactly the six lines and
nothing else, and it was laddered and not shipped: one tape came back
down on engagements and coverage, and e1m5's own baseline swung 5 to 20
engagements on identical code across the two #288 tapes, so a single tape
cannot settle it and six freed slots do not justify the noise.

**The rig's CI download fails on a 404 (#221).** `setup_rig.sh` had
already gained `python3-matplotlib`, `curl -fsSL` and its gitignore
entries; the CI workflow had not, so a missing release still wrote the
HTML error body into `lite.zip` and the cache key kept the poisoned file
afterwards. Both fetches use `-f` now. A failed compile in the rig script
also prints the last 40 lines of `compile.log` instead of one verdict
sentence with no evidence.

**The brief hot path stops re-reading everything (#228).** `cartograph`
called `read_bsp29` before it consulted `ATLAS_CACHE`, so the cache only
ever saved `atlas_from_bsp` and the planes, nodes, leaves and clipnodes
of a 1 to 2 MB file were re-parsed on every call. `brief_run` calls
`cartograph` twice and `hull0_for_map` parsed the same file a third
time. Separately, `look_at` rebuilt the whole 15 file QC index on every
call, and `brief_run` calls it once per next step.

The cache check now comes first, nothing there needing the parsed BSP;
a parsed BSP is shared by mtime behind an `Arc` so `hull0_for_map` costs
a pointer clone; and the QC index is built once per process and rebuilt
only when one of its files changes.

Measured on the same 185 s dm4 tape, three consecutive `brief_run` calls
in one process:

```
            first     second    third
before      189 ms    154 ms    150 ms
after       136 ms     52 ms     52 ms
```

which is the issue's own "time it with and without the cache warm; it
barely moves" turned into a warm path roughly three times faster.

**The rest of the engine's debug shelf (#255).** The headline adopt,
`edicts`, shipped in #261 and named both dm2 freezes in one command each.
The smaller items on that list are on the tune whitelist now:
`profile` and `serverprofile`, which print QC execution counts and are
read-only in the same way the edict dumps are, and the two server-side
toggles worth having on a lab child - `notarget`, so a co-op look
measures the bot rather than the bestiary, and `sv_freezenonclients`,
which holds everything but the clients still so a stuck bot can be walked
around and inspected. All four were confirmed present in the lab engine
binary before being whitelisted, and each has a knob entry saying what it
is for.

`viewpos` and `setpos` are deliberately left off. Both act on a local
player and every lab match is `-dedicated`, where there is none, so
injecting them through this channel would do nothing. They remain worth
typing on a listen server, which is a human's console rather than the
lab's.

**The lab puppet can pull the trigger (#259).** `clc_move` already
carried the button bits and `set_move` already took pitch and yaw, so the
protocol half was done; what was missing was a seat a bot will react to
and a verb to drive it.

`argus-mcp client attack [secs] [yaw] [pitch]` holds the attack button.
With no yaw given it tracks the nearest player each tick and closes the
range, because a stray shot exercises nothing and the first pass proved
it: 45 seconds and 787 tracked ticks standing still landed on nobody,
since the spawn weapon is a shotgun and its spread is a miss across dm4.

The visibility opt-in needed no QC change at all. `Argus_CanSee` refuses
the exact netname `labprobe`, so the link-probe puppet stays an
instrument, and connecting as `labfoe` is a valid target to every bot.
The name is the flag.

Proven end to end on a live dedicated server rather than asserted. Bots
acquire it (`ARGEVT Romero engage labfoe`), kill it, and - the half that
matters - it kills them: `Joe Rogan chewed on labfoe's boomstick`, with
`ARGEVT Joe Rogan death labfoe` in the server tape beside 5
`engage labfoe` and 22 pursue events. Everything that begins with "the
bot takes damage from a player" is now exercisable headless: `Argus_Pain`
retaliation, the vendetta ledger, retreat entry thresholds, the pain
flinch on aim, knockback response and the shove economy.

**Three more pointfile overlays (#254).** `argus_pointfile.py` gains the
items from that list that are computable offline:

- `--what jump|door|lift|train|rocket|sprint|tele` draws one typed link
  family at a time, which makes a map's movement vocabulary legible:
  which crossings are jumps, which are rides, which need a door open.
- `--what fails` draws the cells where routefail, abandon, hazard,
  trapped and stall events fired. ARGEVT carries no position for most
  verbs, so the position is the emitting bot's nearest ARGLOG sample in
  time, accurate to half a second. That is good enough to stand in the
  right room, which is the point of drawing these rather than counting
  them.
- `--what human` draws the human's own trail. Human tracks have been in
  the tape since v3.66 and nobody has ever seen one.

Verified both ways rather than by eye, since the drawing itself needs a
listen game: the human overlay returns 2270 points on a real co-op
session tape and zero on a botmatch, with a note saying why.

**Route against trajectory (#254 item 1).** The forensic that issue calls
"the one that would have shortened every wedge hunt in the project".
`--what route` draws what the router planned and `--what trail` draws
where the bot actually went, with `--bot NAME` to pick one track. They
are separate files by necessity: particle colour is `(-index & 15)` and
cannot be chosen, so intent and reality are flipped between rather than
overlaid.

Route events carry the hop count plus start and goal but not the hops,
so the path is rebuilt by BFS over the same link classes the router
walks. That rebuild is checked against the router's own hop count on
every route, which is what makes it trustworthy rather than decorative:
on e1m1 all 79 agree exactly.

The check earned its keep immediately. dm2 came back with 27 of 182
disagreeing, and the cause is that the router refuses rocket links to a
bot that cannot pay and sprint links below skill 3, while a naive
rebuild takes those shortcuts anyway. Excluding the gated classes is now
the default and lifts dm2 to 164 of 182; `--gated` includes them. The
residual is inherent, since the router's path depends on what the bot
was carrying and the tape does not record that, so the note says a few
disagreements are expected and that most of them disagreeing is the
signal worth acting on.

## v4.09 (2026-09-05) - the co-op session, and two freezes named by the engine's own dump

A day driven by three human co-op sessions on e1m2. Each one produced a
defect, each defect produced a fix, and two of the fixes were built on
instruments the engine has carried since 1996 and the lab had never used.

**Navigation: waypoints past a ledge lip (#250).** navgen samples hull 1,
the player clip hull, whose floor reaches half a player width past every
real ledge. On e1m6 it seated n93 fourteen units out over a 304 unit drop
with lava at -128. The engine never agreed: `SV_movestep` calls
`SV_CheckBottom`, which point traces the box corners against the world, so
`walkmove` refuses the step and the hazard guard refuses it too. A bot
routed there can neither arrive nor give up, and a co-op companion spent a
whole session at that lip: 213 stalls and 215 jumps in 175 s. Section 4c
now runs the engine's own test with the same constants and order. e1m6
regenerated: 536 lip overhang samples dropped, 198 nodes to 188, worst
spawn reach 85 to 95 per cent, seats over a 96 unit void 32 to 0. Other
graphs are not regenerated; dry runs confirm the rule does not fragment
them (dm4 98 per cent, dm6 95, e1m1 99).

**An unroutable co-op objective stops hammering the router (#251).** The
`GOAL_FETCH` branch re-adopts its subject the moment `ar_goal` is cleared,
and the routefail handler clears `ar_goal` on every failure, so the pair
retried at think rate: 400 routefails in 175 s against four goal pushes.
The item shelf could not cover it, because `ar_failtime` is only stamped
when the failure comes from a different area and a bot hammering one
objective never leaves its patch. A routefail on the current fetch subject
now rests that bot 20 s, per bot rather than on the global shelf, with
`ar_goal` left clear so `Argus_PickGoal` runs and the bot shops meanwhile.
e1m6 routefails 400 and 377 to 8 and 9, coverage 6 and 9 cells to 23 and
22, busiest cell 57 per cent to under 10.

**Door contact is an overlap, not a radius (#253).** The handler decided it
was touching its opener when the opener's centre was within 40 units,
flattened in z, and then stood still to be touched. An opener is a brush.
e1m2's t120 door is fired by a trigger 110 wide and 6 thick, so a bot 38
units from that centre still had its box stopping 18 units short of the
volume. It froze waiting for a touch, and the engine only fires touch on
movement, so the touch could never arrive: the v3.43 lift statue in a new
place, five times and 35 s of a 157 s session. `Argus_TouchingBox` compares
`absmin`/`absmax` against the opener's, the same boxes `SV_LinkEdict` uses,
with 2 units of slack so a solid button pressed against still counts. On
e1m1, the only map whose botmatch drives the door path hard, freezes 6 and
6 became 2 and 4 and the worst freeze 13.4 s and 16.9 s became 8.2 s and
8.8 s, which is the give-up cap finally bounding it.

**A companion stops killing its team mate (#260).** Two sessions, two
deaths, two mechanisms. `Argus_Pain` fights back against "any live player,
human or bot" with no co-op test, and in co-op that branch can only ever
fire on a team mate, because monsters do not carry classname "player": the
tape shows both parties taking exactly 24 damage within one second of each
other. Separately, a bot with a monster for an enemy fires at its last
known position during the sight loss hold, and a human crossing that line
takes it. Two guards, both gated on `coop`: no retaliation against a team
mate, and a trace along the shot with fire held when a team mate is what it
reaches. Splash is not covered. Verified in play: the human shot Carmack
dead and he never shot back, four engage events all `engage monster`.
`Argus_Perceive` already returned before its player scan whenever co-op was
on, so a guard written there first was removed as dead code.

**A bot embedded in the world gets out (#262).** A bot whose origin is
inside solid cannot `walkmove` in any direction, so it stands still until
the match ends with no hold flag to explain it. `pointcontents` reads
hull 0, which is the test that separated a frozen bot from five moving ones
in the same dumps. Recovery follows the catchup warp: fog, `setorigin` to
the nearest nav node (seated at hull 1 standable origins by construction,
so a node is somewhere a player fits), zero velocity, clear the route
state. Nearest by distance only, deliberately not `Argus_NearestNode`,
because a traceline starting in solid returns fraction 1 and from in there
every node on the map looks visible. The first cut keyed on contents plus a
low instantaneous speed and teleported a healthy bot 192 units into the dm4
pit while it ran at 320 u/s; being inside solid AND not having moved is the
real signature, so it now needs three seconds without displacing 32 units.
Verified recovering a real one on dm4: embedded at t 33.3, warped out at
t 36.3, running at 306 u/s by t 37.2.

**A stalling bot stops deferring its own thinking (#263).** Stall recovery
pushes `ar_nextai` out 1.5 s so the bot wanders before re-planning, and it
re-armed that deferral on every stall. A bot stalling more often than every
1.5 s therefore pushes its own AI tick permanently out of reach: it never
re-picks a goal, never routes, and the wander meant to free it is the thing
keeping it blind. Romero on dm2 sat motionless for 65 s with `ar_goalstart`
frozen at 13.9 across two dumps 28 s apart while `ar_stalls` went 15 to 53.
Only defer if not already waiting. dm2 goals 78, 86, 89 became 100, 96, 91,
with every fix tape beating every control tape, and the worst freeze 22.3 s
became 8.2 s.

**Swim node selection (#248), and its correction.** `Argus_NearestNode`
prefers a node at or below a query point that is in water. The supporting
ladder was later found invalid: the "before" tape carried a stationary
netclient puppet as a second client, and in co-op the companion escorts its
team mate, so it was parked by the puppet rather than by the water. Matched
configurations put the arms at 52 against 55 cells. The logic hole is real
and the change does no measured harm, but the headline improvement was a
configuration artifact. Recorded so nobody cites it.

**Instruments.** `tools/argus_pointfile.py` writes the engine's `.pts`
overlay so the nav graph, its swim exits, or a tape's freeze cells can be
drawn in the world and walked to. `tools/argus_edicts.py` reads an `edicts`
dump, which walks the progs field definitions and therefore carries
`ar_node`, `ar_goal`, `ar_liftwait` and the rest; `edicts`, `edict <n>` and
`edictcount` joined the lab's tune whitelist so they can be injected into a
running match. Both freezes above were named by that dump in one command
each, where every earlier forensics session added a dprint and recompiled.
Rejected with measurements: `host_timescale` runs 2.9x but drops
engagements per game minute from 23.4 to 7.0, `sys_ticrate` does nothing,
and savegames are refused outright in multiplayer.

## v4.08 (2026-09-03) - navigation caching, item chain, and roster control

A performance, navigation accuracy, and player-experience milestone addressing bot goal selection latency, lift/button stand-pad precision, friendly collision clearance, and runtime bot management.

**1-hop spatial neighbor caching in `Argus_NearestNode` (#146).** During continuous locomotion, a bot rarely teleports across the arena. `Argus_NearestNode` now probes `self.ar_node` and its 1-hop connected neighbors (`an_l0`..`an_l7`) first, exiting immediately when within 120u with line-of-sight. The global O(N) full-map waypoint sweep is bypassed in >95% of frames and runs only on fresh spawns, falls, or rocket knockbacks (>200u).

**Static control-item entity chain in QuakeC (#145).** Replaced the 500+ global edict iteration in `Argus_PickGoal` with a linked list `argus_itemchain` maintained via `Argus_ItemChain_Add` and `Argus_ItemChain_Remove` in `subs.qc`. `PlaceItem`, `DropQuad`, `DropRing`, and `DropBackpack` link items into the chain; touch handlers and `SUB_Remove` unlink them. Cuts interpreter loops by >90% per bot think tick.

**Stand-pad floor targeting & pickup claim mutex (#177).** Lifts, buttons, and doors are brush entities whose bounding-box midpoints often sit inside solid geometry or float in mid-air. `Argus_GoalPoint` now casts a downward floor traceline for non-point entities, directing bots to clear stand-pads (+24u waist) rather than brush geometric centers. Lifts on dm2 and buttons on dm6 cleared without edge stalls. High-value pickups (Megahealth, 100+ Armor, Quad, Pentagram) enforce a 3-second claim reservation mutex so two bots do not fight over the exact same pickup point. `Argus_BodyBlockCheck` clears 48u client collisions by sidestepping perpendicular and suppressing fire (`button0 = 0`).

**In-game bot roster menu & skill cycler (#147).** Runtime bot management wired to impulses: `impulse 100` displays an interactive on-screen `centerprint` menu; `impulse 101` adds a bot; `impulse 102` removes a bot; `impulse 103` cycles difficulty skill (0..3) with `localcmd` and instant centerprint feedback; `impulse 104` toggles ArgusCam AI Director; `impulse 105` displays match statistics and bot scorecards. Guarded by `Argus_ClientCanControlRoster` to protect dedicated multiplayer servers.

**Visual A/B quality gate cards & CLI wrappers (#148, #150).** High-contrast Unicode box-drawing gate cards with aligned status badges (`🟢 PASS`, `🟡 WARN`, `🔴 FAIL`) in CLI and localhost GUI. Unified developer CLI runner subcommands: `compile`, `nav`, `analyze`, `harvest`, `reach`.

**Engine process lifecycle and safety (#151-#155).** Engine child process termination on drop via Windows `TerminateProcess` and Unix `kill_on_drop`, match identity timer safeguards, 90s compiler timeout, and atomic binary swap.

## v4.07 (2026-08-29) - the lab runs at 10 Hz, and a correction

Following the v405 session review's own recommendation: audit bot
physics for per-frame constants that should be scaled by `frametime`.
The audit mostly VALIDATED the code, found one small defect, and
caught a mistake in the previous entry.

**Measured, not assumed.** A one-off `FTDBG` dprint of `frametime` in
a live lab match reports **0.1** in every sample, sustained, while the
server keeps real time (26.4 s of game time in a 25 s match). 0.1 is
not `sys_ticrate`, it is id's `host_frametime` clamp, so the headless
dedicated child runs at roughly ten frames a second. A listen server
runs near 72. That is a factor of **seven** between the rig every tape
is recorded on and the rig every session is played on.

**The correction.** v4.05's swim fix keyed on an assumed 0.05 and
claimed to be bit-identical to the lab. It was not: at 0.1 it changed
swim drag from 0.8 to 0.6 per frame. Re-derived against the measured
rate (`k = 2`, impulse `600 * frametime`) it now reproduces 0.8 and 60
exactly at 0.1, so the lab calibration is genuinely preserved and the
listen server matches it. The terminal 300 u/s was correct throughout.

**The new defect.** The aim tremor was injected once per frame with no
frametime scaling, so its noise power scaled with tick rate: about
2.7x the steady-state jitter on a listen server. It now runs on a
fixed clock, guarded so the branch cannot be entered at the lab rate.
The magnitude is small (0.3 degrees is about 2.6 units at 500u against
a 32-unit target); this is correctness, not difficulty.

**Audited and clean:** `Argus_Friction`, `Argus_Accelerate`,
`Argus_AirAccelerate` (faithful NQ replication, all frametime scaled),
the saccade glide and its re-roll clocks, the stall detector, drowning
escalation, and every turn-rate limiter.

**Found and deliberately NOT changed:** the damped-spring aim clamp.
`turn = 1 - damping_c * frametime` is floored at 0.1 so slow rigs do
not ring, and at frametime 0.1 that floor is hit at every skill tier
while at 72 Hz it is never hit. Per 0.1 s of wall time the spring
retains about 0.26 against 0.10 at skill 1, the default tier - so bot
aim is measurably less damped in a played session than in any tape.
That is a difficulty change to make deliberately with a human-play
ladder, not a bug to silently correct.

Ladder: dm4 IMPROVED on all seven gates, lava back to 4 at baseline
with frags 23 and stalls 4; dm3 movement improved (stalls -22%,
hazards -17%, goals +33%) with its chronic frag-board noise unchanged.
Progs `2CE5C1A999A4F8DF7B6CA382F5664955`.

## v4.06 (2026-08-29) - the quad line the session review caught

A 302 s human session on dm4 reviewed against v4.05. The build held:
zero engine errors, zero bot freezes, stalls 7 (about 4 per 185 s),
all frags positive, 137 engages, 151 acquisitions, 94% of nav nodes
visited, and bots killed the human ten times across all three slots.

One real defect, and it was in the previous entry's own work. The
powerup chat added in v4.01 fires from `powerup_touch`, the PEDESTAL
handler. Both bot quad acquisitions that match came through
`q_touch`, the DROPPED-quad handler - the human took the pedestal
quad, died, and the bots looted the drop - so the line never fired
once in five minutes. The same call now sits in `q_touch`, which is
the commoner case in a real match and the better moment for it:
taking the quad off somebody's corpse. Chat-only, no gameplay path
touched; `q_touch`'s previously unused `stemp` local is now used, so
the compile drops from 7 warnings to 6.

Two alarming-looking flags investigated and dismissed, recorded so
they are not re-chased. "rjlinks never fired" is a property of that
match, not a regression: rocket jumps fire 1 to 6 times in every
botmatch tape of the era including the shipped build, and five
routes in this tape had the quad node as their goal. And 139 swim
events against the 3 to 6 of any lab tape is a pre-existing
lab-versus-listen divergence (48 and 71 on listen tapes before any
of this work), clustering at the pit floor where knocked-in bots
land in water - it tracks how often the human shoves bots into the
pit, and bot time down there was 2.0% against 1.7% and 1.3% on the
two earlier listen tapes.

Progs `1A8436C946AF7D8DD6FB409A1A2D388B`.

## v4.05 (2026-08-29) - the tracker batches

Eighty issues arrived overnight in two waves and all eighty are
answered. Six shipped builds, each on its own ladder; seven changes
were implemented, laddered and reverted with post-mortems in the
code. Progs `16474B95C015A897872CE1494907EE36`.

**v3.98 base files.** `W_FireGrenade` was the sixth fire routine and
the only one still falling through to `aim()` - a bot aiming dead
level has `v_angle_x == 0` and took the autoaim branch, losing
`ar_aimerr`, the lead and the loft. The quad else-branch in
`CheckPowerups` stripped `EF_DIMLIGHT` every frame while a pentagram
was lit, so the invulnerable glow was lost for its whole duration
(the bot path had carried the guard since v3.6). Plus the
`trigger_hurt` frag penalty, entity identity in the rocket-jump
multiplier, the three miscopied `hadammo` pools, a zero-direction
knockback guard, and `> time` on the powerup timestamps.

**v3.99 camera.** The HUD computed the tracked bot's weapon and
affect state every frame and threw both away; `centerprint5`/`7`
are id's own declarations against builtin `#73`. POV froze on a
stale combat angle (every `v_angle` write sits in a firing path).
Smart Chase read `angles_x`, which is 0 on any upright player, so
its pitch was a constant. The viewmodel never got `weaponframe`.
Two bots stacked in a lift shaft collapsed the duel camera into
their bounding boxes. The teleporter cut-ahead tested a sphere
against a brush.

**v4.00 combat.** A traceline that *starts* in solid returns
fraction 1, so both `Argus_SafeLine` and the offensive shove read
solid ground as a void - the shove pulled aim 24u short of every
cornered target. Projectile lead dragged the aim point under the
floor chasing a falling enemy. The grenade loft ignored
`W_FireGrenade`'s own `v_up * 200`. Dodges sidestepped into walls,
because `MoveHazard` only asks whether there is floor and a wall has
excellent floor. Point-blank with only an RL, the selector fell
through to the axe - re-cut at 120u and 100 effective health after
the first version sent dm2 self-kills to 40% of deaths.

**v4.01 perception.** The FOV gate normalised in 3D and dotted
against a flat `v_forward`, charging enemies for vertical
separation. The ears traced to floor-level item origins. Any frag
vented a nemesis vendetta; the killer now learns who it got, from
`ClientObituary` as well, without which a vendetta against the human
could never vent. `Argus_Chat(4)` existed and was never called.

**v4.02 interpreter.** `Argus_PickGoal` walked the whole edict array
once per candidate item. The router re-derived a link slot it
already had, twice per expanded node. `Argus_NearestNode` traced
nodes that could not win. Plus: combat no longer burns the goal
clock, powerup expiry cues play for bots, a pentagram lets a bot
rocket-jump freely, the gun comes back after a navigation jump, and
trigger-operated doors have activators.

**v4.03 economy.** Backpack ammo is valued by what the bot can
absorb and an unowned heavy weapon in a pack is priced as a weapon.
Both spawn systems now apply the engine's own 84u crowding rule -
the post-kill watch had been betting on the pad `SelectSpawnPoint`
is *least* likely to choose, and bot spawns had marched a learnable
cycle through the entity lump.

**v4.04.** `ar_aimrate` was written at every skill tier and read
nowhere, so warmup bots turned corners as fast as skill 3. Armour
below the tier already worn scores zero (`armor_touch` replaces
rather than adds). Auditory glances are rate-limited instead of
snapping 180 degrees in a frame. Five camera modes assigned
`vectoangles()` straight to `client.angles`, framing every director
cut vertically backwards.

**v4.05.** Swim drag was a per-frame factor. Top speed was never
affected - `0.8v + 60` settles at 300 u/s at any tick rate - but the
time constant was frame-counted. See v4.07: the reference rate this
shipped against was assumed rather than measured, and was wrong.

**Lab.** The camera was unindexable in three layers at once (both
file lists, `keep_fn`'s `"Argus_"` prefix, and the call regex).
Cartograph called dm3's plats unboardable while dm3 rode them every
tape. Train, sprint and door hops briefed as plain walks. `lqdm2`
tapes answered `dm2` sweeps. `line_clear` sampled a 1200u trace in
20 steps. Respawns counted as travel. 92 tests.

## v3.97 (2026-08-28) - the fourth bot gets his own name, and the tracker empties

The night the last four issues closed without human eyes.

ROSTER FIX (the QC delta): Argus_RosterName had "Mr Elusive" at
index 2, misaligned with the Argus_Init literals - the impulse-100
fourth bot spawned as a SECOND "Joe Rogan" (merged telemetry,
duplicate TAB row), and taking the omicron costume off mis-renamed
slot 2. Table aligned; the fourth bot is Mr Elusive, whose chat
voice was already waiting. Found by the first headless 4-player
match in project history. dm4 sanity probe at parity.

Issue #2 closed by measurement: the netclient gained a
`client impulse` CLI verb; the puppet joined a live dm3 match and
fired impulse 100. Four players ran 38 engages/200 s against the
rock-stable 3-bot band of 8-9 - a 4.2x jump from ONE added
participant, with stalls FALLING to 36. dm3's thin engage economy
is population scarcity on a 4x map, not a combat defect
(ab_dm3_fourbot1).

Issue #11 closed by census: a four-match dm2 soak (~740 s) ran
ZERO freezes of any class anywhere. The *34 give-up freeze has
one recorded instance ever, three structural bounds around it,
and nothing stares at it - including the instruments.

Issue #15 closed by driving the KEX client itself: three
automated quake_gog.exe sessions with screenshot capture. The mod
loads (+game argus - KEX ignores classic -game), bots fight and
gib on screen, obituaries and \x01 bronze chat render, zero
errors. The skins mechanism is confirmed by the engine's own log:
"Missing skin for progs/player (skin# 1..4). MDL will be
enforced" - KEX falls back to the classic colour-baked MDL for
exactly the bot skins while humans keep the remaster model. The
one residual pixel (TAB rows in a lobby-hosted MP game) is a
30-second glance whenever KEX is next launched by hand.

## v3.96 (2026-08-28) - the puppet opens the islet's back door

Issue #26, resolved the mill's way. Candidate entry links into
dm3's entry-stranded pockets were spliced into the nav json and
walked by the puppet in the real engine: 86 candidates, 43 proven,
43 refused - every refusal honest (under-floor targets, a parapet
at x 1424, +64..96 final risers past the auto-hop envelope). Three
proven entries shipped, spliced surgically into the SHIPPED graph
(a fresh regen measured 78% reach vs the shipped 85% and was
abandoned - the accumulated graph is not reproducible from
scratch): n146->n135 (the RL islet's south-east back door),
n93/n101->n103 (region 4). Four nodes flip to mainland including
the RL seat n158 and the islet spawn n125; regions recomputed in
json and QC. navgen gains the 7g2d engine-proven ingest for the
next real regen (src/argus_nav_<map>.proven.json holds all 43).

Ladder with a CONTROL: the spliced tapes ran stalls 51/78/67
against a 47-stall v3.87-era baseline - but the control (pre-splice
graph, current QC) ran 74, so the elevation is EIGHT BUILDS of
inherited drift, not the splice; recorded as a dm3 play-quality
finding (Joe Rogan pinned 36-45 stalls per tape, quad-court and
n105 '1200 -112 -222' clusters). The splice's own axis is decisive:
the RL goaled 1x on the control, 12-14x spliced - the islet prize
is shopped for the first time in graph history. dm3 baseline ->
ab_dm3_isletentry1. The west-wing RED ARMOUR stays honestly
stranded: the mill refused every existing-node line into it, so
its entrance needs corridor-campaign seats on unsampled stairs.

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
