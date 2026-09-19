# Regression analysis and recovery plan (2026-09-14)

Shane's question: the bots seem to be regressing rather than getting
smarter. This document answers it from the record (71 human session
tapes, 471 ladder tapes, the git history and the lab source) and then
lays out the plan. Every number here is reproducible with two scripts
added alongside it: `tools/argus_longi.py` (one scorecard row per tape,
human-facing metrics) and `tools/argus_tick.py` (the server tick rate a
tape actually ran at, recovered from its telemetry cadence).

## Summary

The bots are not getting smarter, and on dm2 they are getting worse in
exactly the way a player sees. The lab has been reporting "improved"
for a month because it cannot see what Shane sees. Four things are
true at once:

1. On dm2, the map Shane plays now, the stall rate under human play is
   the worst since the door and grate fixes of 19 August: 6 to 9 stalls
   a minute across nine sessions on 20 and 21 August, then 21.6 (28
   August), 32.5 (13 September) and 21.9 (14 September). Each jump sits
   on a nav regeneration that shipped on bot-only ladders. The last two
   sessions also carry the first visible unstick warps (three and two)
   and a 19.7 s freeze.
2. On dm4, the map with the longest record, bot movement improved all
   month (stalls per minute 6 to 12 in the v3.8 era, 0.5 to 3.7 by the
   end of August) but the bots stopped being dangerous. Bot kills on
   Shane fell from 4.2 a minute (v3.8 to v3.20, eight sessions) to 2.2 a
   minute (v3.71 to v4.05, nine sessions) while his own rate rose from
   1.8 to 2.6. There has been no human dm4 session since 29 August;
   twelve progs builds and a new dm4 graph have shipped since without a
   single human tape.
3. The lab's verdict cannot tell a change from nothing. Sixteen pairs
   of byte-identical builds run through `compare_runs` read 9
   "improved", 5 "regressed", 2 "mixed" and 0 "parity". "Improved,
   approved for release" is the most likely verdict for a null change.
   Same-code control tapes have a coefficient of variation of 52 per
   cent (dm4 stalls) and 77 per cent (dm2 stalls). Every ship decision
   in the CHANGELOG rests on this instrument.
4. The lab runs the wrong game. Every human session runs at about 71 Hz.
   Every lab tape runs dedicated at about 19 Hz, and roughly a quarter
   of them at 14 to 15 Hz depending on the Windows timer state that day.
   The "10 Hz" the brief records is `ftos` rounding a 0.05 to 0.07 s
   frame to one decimal. The aim spring behaves differently in each
   regime: at skill 2 it settles in 0.05 s at 19 Hz, rings for 0.28 s at
   14.5 Hz and takes 0.15 s in play; at skill 3 it never settles at
   14.5 Hz. One command-line flag puts the lab at the played rate.

Against that instrument, 3 September landed 1,415 lines of AI and router
changes in one day (PRs #186 to #199) verified by 30 second probes with
no ladder tapes committed, the next fortnight was spent patching pinned
bots (#241, #262, #263, #271, #292, #322), and on 13 September six
graphs were regenerated in a day. None of that was bisected; the dm2
stall distribution in the lab moved from a mean of 36 (late August) to
52 (September) with a fat tail of 60 to 199 stall tapes, and the human
tapes went where they went.

The plan is in three parts: make the instrument honest first (one week
of lab work, no bot behaviour change), then bisect September's changes
and the dm2 graph on the honest instrument, then restore the threat
with Shane as the referee. Only after that does new capability work
make sense.

## Part 1: what the record says

### 1.1 Human sessions on dm4

27 sessions of 60 s or more, 14 to 29 August. Rates are per minute of
tape; kills and deaths come from the engine obituaries, which reconcile
with the frag counters (18 kills and one world death read 17 frags on
the v374 tape).

| Era | Sessions | Bot kills on Shane per min | Shane kills per min | Stalls per min | Bot deaths to the world per session |
|---|---|---|---|---|---|
| v3.1 to v3.7 (14 to 17 Aug) | 10 | 2.2 (0 to 4.2) | 2.4 | 5 to 25 | 0 to 11 |
| v3.8 to v3.20 (17 to 18 Aug) | 8 | 4.2 (2.6 to 6.8) | 1.8 | 3 to 12 | 0 to 4 |
| v3.71 to v4.05 (26 to 29 Aug) | 9 | 2.2 (0.5 to 3.2) | 2.6 | 0.5 to 3.7 | 1 to 12 |
| since 29 Aug | 0 | | | | |

What moved and why, as far as the record allows:

- Movement got genuinely better. The wedge hunt, the lip drop, the
  hazard steer and the rest are visible in play: stalls per minute fell
  ten-fold and freezes vanished.
- Lethality against the human halved and stayed halved. Three things
  changed between the eras and the lab cannot separate them: v3.24
  removed the engine's `aim()` autoaim from five weapons (bots were
  pixel-perfect before it, the CHANGELOG says so and says the tiers were
  deliberately not retuned, with "Shane's next playtest is the
  calibration data point"); the aim became a spring model (v3.27) with a
  saccade (v3.77) and a glide (v3.94), each tuned on the lab's tick
  rate; and Shane got better. The v373 session (1 and 7 at skill 1) was
  dismissed after v374 (17 and 3) as "the variable was the human". The
  calibration ladder that v3.24 promised was never run.
- Bots die to the world more, not less: 1 to 12 per session in the
  latest era against 0 to 4 in the v3.8 era. Knockback became real when
  autoaim left (v3.24 notes it), and Shane's signature move is the
  shove. This is the bots looking dumb in the pit, and it is a combat
  positioning problem, not a routing one (the v3.53 lab session
  established that, and three pit-fear attempts are in the graveyard).
- Engagement rate has been flat at 27 to 33 a minute since v3.7. The
  hunch, prefire, spawn watch, investigation and hearing slices did not
  move it under human play; the lab's bot-only engagement count rose 50
  per cent over the same builds.

### 1.2 Human sessions on dm2

29 sessions of 60 s or more.

| Era | Sessions | Stalls per min | Freezes (longest) | Routefails per min | Unstick warps |
|---|---|---|---|---|---|
| 18 Aug (v3.25 to v3.34) | 6 | 13 to 20 | 0 | 27 to 47 | none |
| 19 Aug (v3.36 to v3.47) | 10 | 4 to 18, 7 to 10 after the grate and door fixes | 0 to 2 (7 s) | 7 to 63 | none |
| 20 to 21 Aug (v3.52 to v3.69) | 9 | 6.3 to 8.9 | 1 to 7 (8 to 19 s) | 13 to 22 | none |
| 28 Aug (v3.89, the rebirth graph) | 1 | 21.6 | 0 | 0 | none |
| 13 Sep (v4.13, the seat regen graph) | 1 | 32.5 | 1 (9.6 s) | 0 | 3 |
| 14 Sep (v4.14 with #316) | 1 | 21.9 | 4 (19.7 s) | 6.7 | 2 |

The 20 to 21 August band is the best dm2 has played. Both later rises
sit on a new graph: the 28 August rebirth (54 stalls in one cell, fixed
the same day by the grate jump remint, but no human has played that
graph since) and the 13 September seat regeneration (165 stalls in one
cell at n0's knit-stitched jump, #316; then the deck cell and door
cluster on 14 September, #323 refused). Bot kills on Shane on dm2 have
run 0.2 to 1.9 a minute all month with no trend; the map is big and he
wins it.

The unstick warps are new and visible: a bot standing still for six
seconds is teleported to a node. The lab counts them as a fix. A player
sees a bot vanish.

### 1.3 The lab's own tapes

dm2 ladder tapes of 150 s or more, stalls per tape:

| Period | Tapes | Mean | Median | SD | Tapes over 60 stalls |
|---|---|---|---|---|---|
| 27 to 29 Aug (v3.7x to v4.07) | 25 | 36 | 33 | 13 | 2 |
| September (v4.08 to v4.17) | 31 | 52 | 41 | 33 | 7 |

Mann-Whitney z 2.5 between the two. The tail is the story: 199, 100, 97,
77, 74, 67 and 66 stall tapes all belong to September builds. The two
longest freezes on the lab record since the lift statue era are both on
the 3 September build's own control tapes: 63.5 s (`ab_dm2_unstick_ctl`)
and 22.3 s (`ab_dm2_aitick_ctl`).

dm4 ladder tapes of 150 s or more, mean (SD):

| Period | Tapes | Stalls | Engages | Bot deaths | World deaths | Goals | Cells |
|---|---|---|---|---|---|---|---|
| 27 to 29 Aug | 53 | 8.0 (5.2) | 86 (12) | 37 (4.5) | 6.0 (2.3) | 147 (16) | 448 (25) |
| 4 to 5 Sep | 7 | 11.1 (7.5) | 84 (13) | 35 (5.0) | 5.7 (2.2) | 137 (13) | 445 (17) |
| 13 Sep before the regen | 8 | 5.4 (2.9) | 90 (10) | 38 (4.5) | 4.2 (2.3) | 139 (10) | 435 (23) |
| 13 to 14 Sep after the regen | 7 | 11.1 (6.3) | 84 (19) | 36 (6.6) | 3.7 (1.6) | 127 (20) | 428 (33) |

dm4 combat is flat in the lab across the month. Stalls doubled on the
regenerated graph within the same day and goals fell 10 per cent; with
seven tapes a side and these spreads that is suggestive, not proven.

Same-code variance (control tapes, byte-identical builds):

| Metric | dm4 CV | dm2 CV |
|---|---|---|
| stalls | 52 per cent | 77 per cent |
| engages | 23 per cent | 32 per cent |
| world deaths | 45 per cent | 77 per cent |

### 1.4 The verdict is noise

`compare_briefs` in `tools/argus_mcp/src/intel.rs` declares "improved"
when no hard gate fails and ANY of these holds: fewer lava deaths, stalls
under 0.85 of the baseline, engages over 1.15 of the baseline, or more
frags with every bot positive. With the variance above, a null change
satisfies one of four such conditions most of the time. Sixteen pairs of
tapes from the same build on the same map, run through the lab's own
`compare_runs`:

| Pair | Verdict |
|---|---|
| dm4 tremorclock1 vs 2 | improved |
| dm4 tremorclock2 vs 3 | improved |
| dm4 fightpin1 vs 2 | improved |
| dm4 seatregen1 vs 2 | improved |
| dm4 airlead1 vs 2 | regressed |
| dm4 gravity1 vs 2 | improved |
| dm4 lgwade1 vs 2 | regressed (stalls 1 to 11, "up 1000%") |
| dm4 ctl_shelfsplit1 vs 2 | improved |
| dm2 apexgate1 vs 2 | improved (stalls 97 to 17) |
| dm2 fightpin1 vs 2 | mixed |
| dm2 jumpceiling1 vs 2 | regressed |
| dm2 decklink1 vs 2 | regressed |
| dm2 seatregen1 vs 2 | improved |
| dm2 mover1 vs 2 | mixed |
| dm2 holds1 vs 2 | regressed (stalls 74 to 100) |
| dm2 unstick1 vs 2 | regressed |

Nine improved, five regressed, two mixed, zero parity. The rule that
shipped sixty builds reads a coin flip as a release. This also explains
the graveyard: seven reverts whose "conviction" rests on the same
instrument, and the e1m2 regen refused four times on tapes that swing
26 to 119 cells on identical code.

### 1.5 The lab runs the wrong game, and a different wrong game on different days

Measured today with the engine's own `host_speeds` frame counter,
launched exactly as the lab launches it (hidden new console, same
flags), 30 s each on dm4:

| Launch | Frames per second | Frame period |
|---|---|---|
| lab default (`sys_ticrate` 0.05) | 19.3 | 51 ms |
| lab default plus `+sys_ticrate 0.0139` | 69.4 | 14 ms |
| Shane's listen sessions (demo POV rate, v373) | about 69 | 14 ms |

The rate a tape ran at can be recovered after the fact from its telemetry
cadence: `Argus_Telemetry` fires on the first frame after `time + 0.5`,
so the mean gap between a bot's ARGLOG rows is 0.5 s plus a frame.
Calibrated on the two probes (0.5154 at 19.3 Hz, 0.5053 at 69.4 Hz) and
run over every tape in `runs/`:

- All 71 human tapes: 0.506 to 0.509. About 71 Hz, every session.
- Lab tapes fall in two clusters: 0.5145 to 0.5155 (about 19 Hz) and
  0.535 to 0.555 (about 14 to 15 Hz: four 15.6 ms timer sleeps plus the
  frame's own work, the Windows coarse-timer regime). No tape reads 0.6,
  which is what a true 0.1 s frame would produce.
- The mix changes by day: 19 August 139 fast against 33 slow; 29 August
  19 against 29; 4 September 3 against 10; 13 September 113 against 3.
  The 29 August `probe_ftdbg` tape, the one the "10 Hz" finding rests
  on, sits in the slow cluster at about 15 Hz; its four FTDBG prints all
  read "0.1" because `ftos` prints one decimal.

So v4.07's swim drag "calibrated to frametime 0.1" was calibrated to a
rate the lab never ran at, and the tremor guard's comment ("at 20 Hz
this branch is never entered") is wrong the other way. Those two are
small. The aim spring is not. `argus.qc` line 4118 floors
`1 - damping_c * frametime` at 0.1, which at 19 Hz is hit at every tier;
the same constants integrate very differently at each rate. A 30 degree
flick, time to settle within 3 degrees, explicit Euler as in the code:

| Tier | Lab at 19 Hz | Lab at 14.5 Hz | Played at 71 Hz |
|---|---|---|---|
| skill 0 | 0.31 s | 0.21 s | 0.28 s |
| skill 1 | 0.15 s | 0.07 s | 0.21 s |
| skill 2 | 0.05 s | 0.28 s, rings 9 degrees | 0.15 s |
| skill 3 | 0.10 s | never, 28 degree limit cycle | 0.13 s |

Every aim constant since v3.27 was chosen on the left two columns and is
played on the right one. In play, bots settle their aim 1.4 to 3 times
slower than the 19 Hz lab believes at skills 1 and 2, and skill 3 is a
different bot in the slow lab regime. This is one mechanism by which the
lab's kill counts can rise while Shane's opponents get easier, and it is
a mechanism by which two "identical" lab tapes differ: the lab flips
regime between days.

### 1.6 What changed in September

- 3 September, v4.08: PRs #186 (link bit resolver), #189 (static item
  chain replaces the edict walk in `Argus_PickGoal`), #190 (stand-pad
  targeting through `UseStandPoint` for plats, trains and door buttons in
  four places in `Argus_AI`, `Argus_BodyBlockCheck`, a 3 s claim mutex on
  every item), #191 (`Argus_NearestNode` fast path: returns the current
  steering node if within 120 units and visible, else the first visible
  neighbour under 120 in link order, else the nearest visible neighbour
  under 200, before any global scan), #192 (roster menu), #196 to #198
  (co-op stack, fairness, keyed doors). 1,415 insertions and 191
  deletions across nine QC files between 1707c4d and c8afa00. Each PR
  body cites a "30s deathmatch lab experiment on dm4" as its
  verification. No tape was committed. The `CHANGELOG` v4.08 entry
  narrates them as done; `CLAUDE.md` has no state section for them.
- 4 September, #241: the batch's mutex had every pick shelve its own
  goal. Split.
- 5 September, v4.09: #262 unstick (teleport an embedded bot), #263 the
  AI tick livelock (a bot pinned hard stops thinking), both found on dm2
  with the v4.08 build: 63.5 s and 22.3 s statues on the control tapes.
- 13 September: eleven QC PRs (#283 wider stuck signature, #285, #291,
  #292 bounded holds, #303, #304, #307, #117, #281, #317 router refuses
  a climb) and six graph regenerations (#308) in one day, 43 commits.
  That night's human session found the n0 pin.
- 14 September: #322 fightpin (a third unstick branch), #323 refused.

Every QC change since 3 September except the co-op work and #117 is a
guard, a hold bound or an unstick: ways to get a bot out of a pin. None
asks why pins became common on 3 September. Under the systematic
debugging rule, three symptom fixes in a row mean the architecture
question is due, and here the question is the batch.

Specific mechanisms in the batch that run in deathmatch and were never
laddered at full length:

- #190 replaced the slab-centre steering that the August lift and train
  ladders tuned (`trainboard1` to `3`, `platwait1` and `2`, `waitnode1`
  to `3`, `camwait`, `westdock1`, `padcool1`) with a floor trace from the
  brush centre, on dm4 probes, where there are no movers.
- `Argus_BodyBlockCheck` holds `button0` at 0 for the whole AI tick
  whenever another player within 48 horizontal units is airborne or
  firing, and warps the bot 36 units sideways with `setorigin` when the
  boxes overlap. A human who jumps into a bot at point blank makes it
  stop shooting and pop sideways.
- #191's fast path is not a nearest-node function any more. A route can
  start from a node up to 120 units away in the link order's favour
  while a nearer node exists.

Nothing above is a conviction. It is the list of what to bisect.

## Part 2: diagnosis

Ranked by how much of the record each one explains.

1. The instrument. Bot-only tapes at 14 to 19 Hz judged by a rule that
   reads noise as improvement. Explains: sixty "improved" ships with
   flat human-facing numbers; the graveyard's contradictory verdicts;
   the e1m2 refusals; the confidence with which the 13 September regens
   shipped. Does not explain by itself why dm2 got worse in September.
2. The 3 September batch and the patch cascade after it. Explains: the
   September dm2 stall distribution, the long statues on its control
   tapes, the need for three unstick branches. Not yet bisected.
3. Graph regenerations judged on that instrument. Explains: the two
   dm2 human sessions (both pins were new links), and the dm4 post-regen
   stall doubling in the lab. The old graphs carried a month of
   convictions and human trace mining; a regen reproduces the
   convictions but not the human sessions.
4. Combat calibration never revisited since v3.24. Explains: the
   halving of lethality against Shane and the flat engagement rate.
   Confounded with Shane's own improvement; only a human ladder can
   separate them.
5. A month of guards. Each hold, veto and shelf is a hesitation a
   player can see, and none of them was measured under human play.

## Part 3: what this analysis did not establish

- Which change in the 3 September batch, if any, caused the dm2 stall
  and freeze shift. That needs the bisect in task 1.1.
- Whether the lethality decline on dm4 is the bots or Shane. The record
  has both changing at once.
- Why the lab's tick rate flips between 19 and 14.5 Hz on different
  days. The two clusters match the 1 ms and 15.6 ms Windows timer
  regimes exactly, which is a hypothesis, not a measurement.
- Whether 30 seconds at 69 Hz play differently from 30 seconds at
  19 Hz. The two probes differ (average speed 250 against 194, weapon
  pickups 14 against 4) but one 30 s tape each proves nothing.

## Part 4: the recovery plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> superpowers:subagent-driven-development or superpowers:executing-plans
> to work this plan task by task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** give the project an instrument that sees what Shane sees, then
use it to remove September's regressions and restore the bots' threat.

**Architecture:** phase 0 changes the lab only (tick rate, verdict
rule, scorecard, baselines); phase 1 bisects with that lab; phase 2 tunes
combat with Shane as the referee; phase 3 is process. No bot behaviour
changes before phase 1's evidence is in.

**Tech stack:** QuakeSpasm 0.96.3 dedicated (Windows, `engine/`), the
Rust lab in `tools/argus_mcp`, Python tools in `tools/`, fteqcc.

### Global constraints

- Pure vanilla QuakeC. No engine extensions. Protocol 15, max_edicts 600.
- Editorial: sentence case headings, Australian English, no em or en
  dashes anywhere, spaced hyphen instead.
- No Claude attribution on commits, issues or PRs. GitHub as saworbit
  only.
- One QC change per PR, each with its own ladder tapes committed.
- Every ladder in this plan runs at the played rate (task 0.1 first).

---

### Phase 0 as built (2026-09-15)

Tasks 0.1 to 0.4 are done and merged; what follows is what the work
found, including where it contradicted this document.

**0.1 confirmed, and it settles an old contradiction.** `sys_ticrate`
does gate the dedicated main loop. Measured on dm4 through the lab's
own launcher: the default reads a mean ARGLOG gap of 0.5134 (about
19 Hz), `+sys_ticrate 0.0139` reads 0.5074 to 0.5080 (about 70 Hz),
and every human tape reads 0.506 to 0.509. The v4.09 note that
"sys_ticrate does nothing to the dedicated tick" is wrong. Game time
tracks wall clock at the new rate (60.1 s of game time in a 60 s
match), so tape lengths stay comparable. Two engines at once on this
box both hold the listen class, so a ladder can run two ports.

**The estimator needed a correction before it could be trusted.** The
true telemetry gap is `n * dt` with `n` chosen to cross 0.5, so it can
never be below 0.5; `ab_dm3_fourbot1` read 0.4877 because 566
`ar_nextlog` resets on respawn dragged the mean under the arithmetic
floor and into the wrong class. The window is now 0.45 to 0.75. The
mechanism is also not quite what the script's header said: `t` prints
to one decimal, so the gaps on a tape are a two-point mixture of 0.5
and 0.6 and it is the *fraction of 0.6s* that carries the rate (7 per
cent at 70 Hz, 15 at 19 Hz, 32 at 14.5 Hz). The mean is therefore the
right statistic and the median is useless here: it reads 0.5 at all
three rates.

**0.3's band was fitted, not assumed.** The plan proposed encoding
"dm2 stalls 77 per cent CV, dm4 52 per cent". Measured directly from
the sixteen null pairs instead, one tape a side, on identical code:

| metric | null ratio range | usable on one pair? |
|---|---|---|
| stalls | 0.18x to 11.0x | no |
| engages | 0.45 to 2.82 | no |
| world deaths | 0 to 4x | no |
| freezes | 0 to 3 | no |
| coverage | 0.70 to 1.19 | yes |
| goal pickups | 0.82 to 1.27 | yes |

Coverage and goal pickups are the only two metrics in the lab with
enough signal to judge a change on a single pair. That is worth
remembering every time a tape is read. The fitted band half-widths are
stalls 1.00 + 4, engages 0.55 + 4, lava 1.50 + 3, freezes 1.00 + 2,
and they return parity on 15 of the 16 null pairs against the target
of 13. The one that still convicts is `ab_dm4_lgwade1 vs 2`, one stall
becoming eleven.

**A consequence the plan did not anticipate.** At one tape a side the
stall band's floor is zero, so an improvement cannot be *expressed*,
only a regression or parity. This is correct rather than broken - a
metric whose same-build ratio runs 0.18 to 11.0 has not improved
because one match came back lower - but it means every "improved on
all seven gates" in `CLAUDE.md` rests on an instrument that could not
have said anything else. `compare_band` now says so in its findings
and names the cure: the band narrows as `sqrt`, so three tapes a side
carry 0.58 of the one-tape spread and an improvement becomes
expressible again. `experiment` runs three by default.

**Filed while working:** #337, a telefrag emits an engine obituary and
no ARGEVT death line, so it is invisible to every kill matrix and to
the threat ratio phase 2 turns on. One kill in 302 s on the v405 tape.

*Corrected 2026-09-16:* the death line is emitted. It reads `death
world`, because the attacker on a telefrag is a `teledeath` trigger with
no netname. Fixed by resolving the killer through the trigger owner,
which is what the engine obituary always did.

### fteqcc is byte-stable, and the record says it is not

Recompiling the shipped v4.17 source with the lab's own fteqcc
produces a progs.dat that differs from the installed one in **exactly
one byte**: the build date fteqcc stamps into its header comment
("2026/09/15" against "2026/09/14"). The compiled code is identical.

This matters twice. It means a freshly built control is a valid
control, so a ladder does not need to re-run the shipped binary's
tapes to compare against them. And it retires the v3.74 note that a
rejected cycle must restore installed progs "never by recompile -
fteqcc is not byte-stable", which cost that machinery a snapshot
directory it did not need.

### The aim spring, measured before phase 2 touches it

Task 2.1 asked for the 71 Hz constants to be re-fitted so the settle
times match what the 19 Hz lab was tuned for. **That instruction
should not be followed as written**, and the simulation says why.
Settle time for a 30 degree flick to within 3 degrees, integrating
exactly as the QC does:

| tier | omega | zeta | 71 Hz (played) | 19 Hz (lab) | 14.5 Hz (lab) |
|---|---|---|---|---|---|
| skill 0 | 10.5 | 0.80 | 0.27 s | 0.26 s | 0.28 s |
| skill 1 | 14.1 | 0.80 | 0.20 s | 0.10 s | **one frame** |
| skill 2 | 19.0 | 0.80 | 0.14 s | **one frame** | 0.21 s |
| skill 3 | 23.7 | 0.80 | 0.11 s | 0.05 s | **never settles** |

The 19 Hz column is not a tuning, it is a broken integrator. `turn = 1
- damping_c * frametime` goes negative at every tier above skill 0 and
is floored at 0.1, which leaves `aimvel` almost entirely replaced by
`k * dt * error` each frame; at skill 2 and 19 Hz, `k * dt^2` is 0.97,
so the bot moves 97 per cent of its aim error in a single frame. That
is a snap-aim, which is precisely what the spring was introduced to
replace. Re-fitting the played constants to match it would reproduce
a snap-aim in play: a large difficulty change dressed as a bug fix.

What the numbers do establish is the mechanism behind the plan's own
paradox. **The lab has always measured a deadlier bot than Shane
fights** - the default tier settles in half the time on a lab tape
that it takes in a played session, and skill 3 in the slow lab regime
never settles at all. Lab kill counts rising while his opponents got
easier is exactly what that predicts.

So phase 2.1 as delivered fixes the integrator rather than the
constants: sub-step the spring so no sub-step exceeds 0.02 s. At 71 Hz
that is one step and bit-identical to the current build, so the game
Shane plays does not move; at 19 Hz it is three and at 10 Hz six, so
every rig runs the same bot and the damping floor becomes unreachable.
The design intent (omega 10.5 to 23.7, zeta 0.80) is realised at last
instead of being overwritten by the integrator.

Whether skill 1 should settle in 0.20 s at all is a difficulty
question, not a correctness one. That is task 2.2, and it needs Shane.

### Phase 0: make the instrument honest (lab only, one week)

#### Task 0.1: pin the lab tick at the played rate

**Files:**
- Modify: `tools/argus_mcp/src/engine.rs` (`apply_args`, around line
  204, and the `args` format string in `spawn_windows`, around line 327)
- Modify: `tools/setup_rig.sh` (the headless match command)
- Modify: `.github/workflows` smoke job (the quakespasm command line)
- Test: `tools/argus_mcp/src/engine.rs` unit tests

**Interfaces:**
- Produces: every engine launch carries `+sys_ticrate 0.0139`.

- [ ] **Step 1: write the failing test**

```rust
#[test]
fn every_launch_pins_the_played_tick_rate() {
    let cfg = Config::for_test();
    let mut cmd = Command::new("x");
    apply_args(&mut cmd, &cfg, "dm4", 8, None, None, false);
    let args: Vec<String> = cmd.as_std().get_args().map(|a| a.to_string_lossy().into()).collect();
    let joined = args.join(" ");
    assert!(joined.contains("+sys_ticrate 0.0139"), "{joined}");
}
```

On Windows add the same assertion against the `args` string that
`spawn_windows` builds (factor the format into a `fn windows_args(...) -> String`
so the test can call it without spawning).

- [ ] **Step 2: run it and watch it fail**

Run: `cd tools/argus_mcp && cargo test every_launch_pins`
Expected: FAIL, the string is absent.

- [ ] **Step 3: add the flag to both launch paths**

In `apply_args`, after `+developer 1`:

```rust
cmd.arg("+sys_ticrate").arg("0.0139");
```

In the Windows format string, after `+developer 1`:

```
+sys_ticrate 0.0139
```

Add the same two tokens to the `setup_rig.sh` match line and the CI
smoke command.

- [ ] **Step 4: run the tests, then prove it live**

Run: `cargo test` (expect green), then `experiment map=dm4
duration_sec=30 compile=false` and
`python tools/argus_tick.py runs/<that tape>.log`.
Expected: the tape reads "about 70 Hz".

- [ ] **Step 5: commit**

```bash
git add tools/argus_mcp/src/engine.rs tools/setup_rig.sh .github/workflows
git commit -m "Run every lab match at the played tick rate"
```

#### Task 0.2: every brief states the tick rate, and compare refuses to judge across rates

**Files:**
- Modify: `tools/argus_mcp/src/parse_arglog.rs` (totals)
- Modify: `tools/argus_mcp/src/intel.rs` (`compare_briefs`)
- Test: `tools/argus_mcp/src/parse_arglog.rs` tests

**Interfaces:**
- Produces: `totals.tick_gap_mean: f64` and `totals.tick_class: String`
  ("listen", "dedicated_fast", "dedicated_slow"), the same estimator as
  `tools/argus_tick.py`.

- [ ] **Step 1: write the failing test on two committed tapes**

```rust
#[test]
fn tick_class_separates_a_human_tape_from_a_lab_tape() {
    let human = parse_file("runs/shane_dm4_2026-08-29_v405.log");
    let lab = parse_file("runs/ab_dm4_tremorclock1.log");
    assert_eq!(human.totals.tick_class, "listen");
    assert_eq!(lab.totals.tick_class, "dedicated_fast");
    assert!(human.totals.tick_gap_mean < 0.5135);
    assert!(lab.totals.tick_gap_mean > 0.5135 && lab.totals.tick_gap_mean < 0.522);
}
```

- [ ] **Step 2: run it and watch it fail**

Run: `cargo test tick_class_separates`
Expected: FAIL, fields missing.

- [ ] **Step 3: implement the estimator**

Per bot, collect consecutive ARGLOG `t` gaps in (0.3, 1.0), take the
mean. Class thresholds: under 0.5135 listen, under 0.522 dedicated_fast,
otherwise dedicated_slow. In `compare_briefs`, when the two classes
differ, push a finding "tapes ran at different tick rates (a vs b); the
verdict is not valid" and set the verdict to `Mixed`.

- [ ] **Step 4: run the tests**

Run: `cargo test`
Expected: green, including the existing compare tests.

- [ ] **Step 5: commit**

```bash
git add tools/argus_mcp/src/parse_arglog.rs tools/argus_mcp/src/intel.rs
git commit -m "State the tick rate on every brief and refuse cross-rate verdicts"
```

#### Task 0.3: replace the one-tape verdict with a paired, banded one

**Files:**
- Modify: `tools/argus_mcp/src/intel.rs` (`compare_briefs`, the verdict block around lines 1113 to 1135)
- Modify: `tools/argus_mcp/src/server.rs` (`experiment` gains `repeats`, default 3)
- Modify: `runs/baselines.json` (a map points at a band, a list of tape names)
- Test: `tools/argus_mcp/src/intel.rs` tests

**Interfaces:**
- Produces: `compare_band(candidates: &[MatchBrief], controls: &[MatchBrief]) -> CompareReport`.
  Verdict rules: regressed if the candidate median is worse than the
  worst control on any hard gate (stalls, freezes, lava, engages);
  improved only if the candidate median beats the best control on at
  least one gate and is not worse than the control median on any hard
  gate; otherwise parity. The old OR rule is removed.

- [ ] **Step 1: write the failing test, sixteen null pairs must read parity**

```rust
#[test]
fn same_build_pairs_read_parity() {
    let pairs = [
        ("ab_dm4_tremorclock1", "ab_dm4_tremorclock2"), ("ab_dm4_tremorclock2", "ab_dm4_tremorclock3"),
        ("ab_dm4_fightpin1", "ab_dm4_fightpin2"), ("ab_dm4_seatregen1", "ab_dm4_seatregen2"),
        ("ab_dm4_airlead1", "ab_dm4_airlead2"), ("ab_dm4_gravity1", "ab_dm4_gravity2"),
        ("ab_dm4_lgwade1", "ab_dm4_lgwade2"), ("ctl_dm4_shelfsplit1", "ctl_dm4_shelfsplit2"),
        ("ab_dm2_apexgate1", "ab_dm2_apexgate2"), ("ab_dm2_fightpin1", "ab_dm2_fightpin2"),
        ("ab_dm2_jumpceiling1", "ab_dm2_jumpceiling2"), ("ab_dm2_decklink1", "ab_dm2_decklink2"),
        ("ab_dm2_seatregen1", "ab_dm2_seatregen2"), ("ab_dm2_mover1", "ab_dm2_mover2"),
        ("ab_dm2_holds1", "ab_dm2_holds2"), ("ab_dm2_unstick1", "ab_dm2_unstick2"),
    ];
    let mut parity = 0;
    for (a, b) in pairs {
        let r = compare_band(&[brief(b)], &[brief(a)]);
        if r.verdict == Verdict::Parity { parity += 1; }
    }
    assert!(parity >= 13, "only {parity} of 16 null pairs read parity");
}
```

With one tape a side the band collapses to a point, so this test also
needs the band rule to widen by the map's known control spread
(dm2 stalls 77 per cent CV, dm4 52 per cent) when fewer than three
controls are given. Encode those two numbers as a constant with a
comment naming this document.

- [ ] **Step 2: run it and watch it fail**

Run: `cargo test same_build_pairs_read_parity`
Expected: FAIL, `compare_band` undefined.

- [ ] **Step 3: implement `compare_band` and route `compare_runs` through it**

`compare_runs(log_a, log_b)` becomes `compare_band(&[b], &[a])`.
`experiment` runs `repeats` candidate matches (default 3) and, when the
map's baseline band is missing or its progs MD5 is not the shipped one,
runs three control matches on the shipped progs first. Verdict text
names the medians and the band.

- [ ] **Step 4: run the tests**

Run: `cargo test`
Expected: green; adjust the two existing compare tests that assert the
old OR rule.

- [ ] **Step 5: commit**

```bash
git add tools/argus_mcp/src/intel.rs tools/argus_mcp/src/server.rs runs/baselines.json
git commit -m "Judge candidates as bands against controls, never one tape against one tape"
```

#### Task 0.4: the human scorecard becomes a lab surface

**Files:**
- Keep: `tools/argus_longi.py` (added with this document)
- Modify: `tools/harvest_session.py` (append the session's row to `runs/human_scorecard.tsv`)
- Modify: `tools/argus_mcp/src/intel.rs` (`brief_run` on a human tape carries the same fields)
- Modify: `CLAUDE.md` (the handoff template records the scorecard row, not "improved on all seven gates")
- Test: `tools/test_tools_cli.py`

- [ ] **Step 1: write the failing test**

```python
def test_longi_reproduces_the_v405_row():
    out = run(["python", "tools/argus_longi.py", "runs/shane_dm4_2026-08-29_v405.log"])
    row = dict(zip(*[l.split("\t") for l in out.splitlines()[:2]]))
    assert row["bot_kills_human"] == "10" and row["human_kills_bot"] == "18"
    assert row["stalls"] == "7" and row["freezes"] == "0"
```

- [ ] **Step 2: run it**

Run: `python tools/test_tools_cli.py`
Expected: PASS already for the script, FAIL for the harvest append once
that assertion is added (`runs/human_scorecard.tsv` gains one row per
harvest).

- [ ] **Step 3: wire the harvest append and the brief fields**

`harvest_session.py` calls `argus_longi.analyse` on the harvested tape
and appends the row. `brief_run` on a tape with human tracks adds a
`human_scorecard` object with `bot_kills_human_pm`, `human_kills_pm`,
`stall_pm`, `freezes`, `fz_max`, `unstick`, `rf_pm`.

- [ ] **Step 4: run the tests**

Run: `python tools/test_tools_cli.py && cd tools/argus_mcp && cargo test`
Expected: green.

- [ ] **Step 5: commit**

```bash
git add tools/argus_longi.py tools/argus_tick.py tools/harvest_session.py tools/argus_mcp/src/intel.rs CLAUDE.md
git commit -m "Score every human session on what the player sees"
```

#### Task 0.5: re-baseline every map as a three-tape band at the played rate

**Files:**
- Modify: `runs/baselines.json`
- Create: `runs/band_<map>_v417_{1,2,3}.log` for dm2, dm3, dm4, dm6, e1m2, e1m5, e1m7, lqdm2

- [ ] **Step 1: run the bands on the shipped v4.17 progs**

For each map: `experiment map=<map> duration_sec=185 compile=false repeats=3`
with task 0.1 in place. Confirm with `python tools/argus_tick.py` that
every tape reads "about 70 Hz".

- [ ] **Step 2: point `baselines.json` at the bands and commit the tapes**

```bash
git add runs/baselines.json runs/band_*.log
git commit -m "Baseline every map as a band at the played rate"
```

---

### Phase 1 as built (2026-09-15): there is no September regression to remove

The bisect and the graph comparison both came back **parity**, and the
thing they found instead is more useful than a culprit.

Every arm below ran at the played tick rate, 185 s, on the same
engine, judged with `compare_band` against the tape counts shown.

```
arm                              n     stalls        engages     vs v4.07
v4.07 QC + 216-node old graph    4   54 [46-82]    24 [19-33]    control
v4.08 QC + 216-node old graph    4   52 [25-55]    34 [29-45]    parity
v4.09 QC + 216-node old graph    4   65 [43-129]   38 [19-41]    parity
v4.17 QC + 216-node old graph    4   46 [27-95]    26 [19-36]    parity
v4.17 QC + 215-node new graph    6   64 [31-86]    24 [17-40]    (graph arm)
```

The graph arm is judged against the old-graph arm on the same QC, six
tapes against four: **parity**, a candidate median of 64 inside a
control band of 23 to 97.

**Task 1.1, the QC bisect: not convicted.** The whole span from v4.07
to v4.17 on one graph moves the stall median from 54 to 46 and the
engagement median from 24 to 26. The 3 September batch does not raise
dm2 stalls, so task 1.2 does not run. The plan's decision rule (an arm
whose median exceeds v4.07's maximum, or a 20 s freeze v4.07 lacks)
fires on nothing.

**Task 1.3, the graph: not convicted either.** New graph against old
on identical QC reads **Parity**: the candidate median of 77 sits
inside the control band of 19 to 97. The old graph's own four tapes
ran 27, 47, 95 and one more, which is the width that makes the verdict
what it is.

That verdict is worth dwelling on, because after two tapes the old
graph was reading 27 and 47 against the new graph's 65 to 86 and the
obvious conclusion was "the regen did it". The third old-graph tape
came back at 95, and the fifth and sixth new-graph tapes came back at
31 and 37. **The band is the only reason that conclusion was not
shipped**, which is the whole argument for phase 0 in one experiment.

The v4.09 arm made the same point from the other side: at three tapes
it read REGRESSED (stalls 43, 129, 86) and its fourth tape returned it
to parity.

Five times in one session a conclusion looked decisive and the next
tape withdrew it:

| arm | looked like | the next tape said |
|---|---|---|
| dm2 old graph, 2 tapes | 27, 47: "the regen did it" | third: 95 |
| v4.09, 3 tapes | 43, 129, 86: regressed | fourth: parity |
| new-graph band, 4 tapes | 64 to 86: a stable control | fifth and sixth: 31, 37 |
| aim spring dm2, 3 tapes | 21, 22, 43: improved against six controls | fourth: 54, inside the band |
| the tick estimator | inverted to 39.5 Hz | `host_speeds`: 70.2 Hz |

**Three tapes is not enough on this map and four is barely.** The last
row is the same error in a different medium: an arithmetic identity
with more than one root, read as a measurement. When a result looks
decisive here, the correct next action is another tape, not a commit.

### What the tapes found instead

**dm2 has always been this bad, on both graphs and at both rates.** At
the played rate the shipped build runs about 21 stalls a minute on
dm2, and 25 a minute on the PREVIOUS graph. Shane's last three dm2
sessions read 21.6, 32.5 and 21.9. There was no September cliff in the
game.

I wrote two wrong things here before arriving at that. First, that the
19 Hz lab "read 11 to 16 for the same builds", which was a selective
reading of historical tapes. Then, having run a controlled experiment
at four tapes a side, that the rate moved engagement, coverage and
deflections. The fifth and sixth control tapes dissolved the second
claim as thoroughly as the controlled run dissolved the first.

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

**Every metric that counts something that happened overlaps**, stalls
at z 0.00 exactly. The one disjoint metric is the hazard deflection
count, and that event is throttled to one a second per bot, so a 3.7x
frame rate raises the chance of at least one deflection landing inside
any given second whether or not the bot behaves differently. It is a
measurement artifact, and reading it as timidity was the same mistake
in a new coat.

**The tick pin is still right, for a reason that is arithmetic rather
than statistical.** The aim spring's integrator genuinely behaves
differently at the two rates, and that is a derivation from the code.
What these tapes add is that dm2's MOVEMENT numbers are insensitive to
it: the old tapes' movement figures were not lies, they were recorded
on a rig whose AIM was a different bot.

dm4's played-rate band (5, 8, 11 stalls) sits on its 19 Hz history of
mean 8.0 over 53 tapes, so nothing here says dm4's month of clean
tapes was a lie either.

**The new graph did not add stalls, it concentrated them.** Total load
is in band, but the composition is not:

```
graph                 stalls/tape   top cell                     share
new (shipped, 215n)        76       2048 -1152  (west deck)       32%
old (216n), v4.17 QC       56       2176 -2176  (SE grate room)   40%
old (216n), v4.07 QC       59       2304 -2176  (SE grate room)   17%
```

The west deck cell does not appear in either old-graph arm's top four.
It arrived with #308, and 71 of its stall events name node
`2049 -1207 152` exactly: #323, reproduced without a human in the
game. The old graph's deck node drops 176 units over 96 to reach the
level below; the new one drops 192 over 101, with a sideways component
the old line did not have.

A single cell holding a third of a map's stalls is what a player
notices, even when the total is in band. **So the action is to fix the
cell, not to revert the graph**, and #323 already names the cure:
n65 to n66, 144 down over 32 horizontal, additive rather than the
deletion that cost three gates last time.

### What this changes about the plan

Part 2 of this document ranked "the 3 September batch and the patch
cascade after it" second among the explanations. On this evidence it
explains nothing about dm2 stalls, and the ranking should read:

1. The instrument. It was measuring a different game at a rate nobody
   plays, with a verdict rule that read noise as improvement.
2. dm2's own geometry, unchanged for weeks and never measured where it
   hurts: the west deck (#323), the door cluster (#324) and the SE
   grate room.
3. Combat calibration, still untested against a human since 29 August.

The September guards (#262, #263, #271, #292, #322) are not convicted
by this, but neither are they vindicated: they were laddered on the
old instrument. They cost nothing measurable here.

### Phase 1: find and remove the September regressions

#### Task 1.1: bisect the dm2 shift across v4.07, v4.08 and v4.09 on one graph

**Files:**
- Worktrees: `git worktree add ../argus-v407 cd45e00`, `../argus-v408 c8afa00`, `../argus-v409 7f8c929`
- Nav: in each worktree overwrite `src/argus_nav_dm2.qc` and `.json` with
  `git show 29f0bd1^:src/argus_nav_dm2.qc` (the graph that shipped from
  28 August to 13 September), so only QC differs
- Tapes: `runs/bisect_dm2_v407_{1..4}.log`, `_v408_`, `_v409_`

- [ ] **Step 1: compile each worktree with the Windows fteqcc and install to `engine/argus/progs.dat` one arm at a time**

Record the progs MD5 of each arm in the tape name's sidecar note.

- [ ] **Step 2: run four 185 s dm2 tapes per arm at the played rate**

`match_run map=dm2 duration_sec=185 run_name=bisect_dm2_v407_1` and so
on. Twelve tapes, about forty minutes of engine time.

- [ ] **Step 3: judge with the scorecard, not the old verdict**

```bash
python tools/argus_longi.py runs/bisect_dm2_v40*_*.log
```

Compare per arm: median stalls, count of freezes of 10 s or more, median
engages, median bot deaths. Decision rule: an arm whose median stalls
exceed the v4.07 arm's maximum, or which shows any freeze of 20 s or
more that the v4.07 arm does not, is convicted.

- [ ] **Step 4: record the result in `CLAUDE.md` and this document, tapes committed**

```bash
git add runs/bisect_dm2_*.log
git commit -m "Bisect the September dm2 stall shift across v4.07 to v4.09"
```

#### Task 1.2: if v4.08 convicts, bisect inside the batch

**Files:**
- Worktree on c8afa00 with `git revert -n e639ff6` (#190), then
  separately `-n f34086a` (#191), `-n 7705e2d` (#189), `-n 277268e` (#186)
- Tapes: `runs/bisect_dm2_no190_{1..4}.log` and so on

- [ ] **Step 1: revert one PR at a time on top of c8afa00, resolve conflicts, compile, install**

Order: #190 first (movers, body block, mutex), then #191, #189, #186.

- [ ] **Step 2: four tapes per arm, same judge as task 1.1**

The first revert that returns the arm to the v4.07 band names the
regression. Ship that revert (or a targeted fix of the mechanism) on its
own PR with the tapes.

- [ ] **Step 3: commit tapes and the revert**

```bash
git add runs/bisect_dm2_no*.log src/argus.qc src/argus_nav.qc src/items.qc src/subs.qc src/defs.qc
git commit -m "Revert the batch change that pinned dm2 bots, with its bisect tapes"
```

#### Task 1.3: the dm2 graph, judged by the player

**Files:**
- `src/argus_nav_dm2.qc` and `.json`: the shipped (#308) graph against `git show 29f0bd1^:...`
- Tapes: `runs/graph_dm2_old_{1..4}.log`, `runs/graph_dm2_new_{1..4}.log`
- Human tapes: one Shane session on each graph, harvested with
  `tools/harvest_session.py`

- [ ] **Step 1: four tapes per graph on the same QC (the task 1.1 winner) at the played rate**

- [ ] **Step 2: Shane plays one dm2 session on each graph, same launch command**

```
cd C:\argus\engine ; .\quakespasm.exe -listen 8 -condebug -game argus +developer 1 +deathmatch 1 +record session dm2
```

- [ ] **Step 3: the human scorecard decides**

Lower stalls per minute and no unstick warps wins. If the old graph
wins, it ships and the seat filter's output waits for the corridor and
door work named in #323 and #324.

- [ ] **Step 4: repeat for dm4 before Shane's next dm4 session**

The dm4 graph also changed on 13 September and no human has played it.

#### Task 1.4: the two named dm2 pins

- [ ] **Step 1: `'2065 -1136 380'` (#323)**: splice the n66 link the
  issue names through the proven-link ingest (navgen 7g2d, the path
  that shipped dm3's islet entries in v3.96), regenerate, confirm with
  `argus_pointfile.py` in a listen game, and take a human session.
- [ ] **Step 2: `'2231 -1968 120'` door cluster**: the retype tool
  (`argus_navgen.py --retype-doors`) plus the #303 doorway steer; judge
  on the scorecard.
- [ ] **Step 3: count unstick warps on every human tape**; the target is
  zero. A warp is a visible failure the scorecard must show, never a fix.

---

### Phase 2: restore the threat, with Shane as the referee

#### Task 2.1: re-derive the aim spring at the played rate

**Files:**
- Modify: `src/argus.qc` (`Argus_SetSkill` constants around line 2431, the spring block at line 4118)
- Tapes: dm4 band ladder at 71 Hz, then human sessions

- [ ] **Step 1: keep the design intent (omega 9 to 20 rad/s, zeta 0.8) and re-fit k and c so the 71 Hz settle times match what the 19 Hz lab was tuned for** (skill 1 about 0.15 s, skill 2 about 0.05 to 0.10 s), leaving the 0.1 floor in place for slow rigs but irrelevant at 71 Hz.
- [ ] **Step 2: ladder on the phase 0 lab** (bands, played rate), then two human sessions at skill 1 and one at skill 2.
- [ ] **Step 3: record the human scorecard rows in the handoff.**

#### Task 2.2: the skill-1 calibration ladder v3.24 promised

- [ ] **Step 1: define the target on the scorecard**: at skill 1 the bots' kills on Shane per minute should sit at 60 to 80 per cent of his own rate (he wins, narrowly); at skill 2 about parity.
- [ ] **Step 2: three sessions per candidate**, the dial is `ar_aimerr` and `ar_reactbase` per tier; one tier per PR.
- [ ] **Step 3: the CHANGELOG entry names the human rows, not lab gates.**

#### Task 2.3: `Argus_BodyBlockCheck` in deathmatch

- [ ] **Step 1: human test first**: stand on a bot while firing; note whether it shoots back and whether it pops sideways.
- [ ] **Step 2: gate the fire suppression and the `setorigin` nudge to `coop > 0`** unless the test shows they help in deathmatch; ladder at the played rate.

#### Task 2.4: capability, only now

Cover-based positioning, missile dodge retuned at 71 Hz, the parked
ambush and item-clock work. Each on the phase 0 instrument, each with
a human session before it is called an improvement.

---

### Phase 3: guardrails

- No QC merge without committed ladder tapes at the played rate and the
  band verdict in the PR body. `ship` refuses when the map's band is
  older than the shipped progs.
- One change per PR. A batch of "perf" and "opt" rewrites needs a ladder
  per PR, not a probe per batch.
- A regenerated graph ships beside the previous one
  (`argus_nav_<map>_prev.qc`, dispatcher-selectable by `scratch2`) until
  a human session on the new graph clears it on the scorecard.
- The handoff section in `CLAUDE.md` carries the human scorecard row for
  every session and the band verdict for every ship, and never the
  phrase "improved on all seven gates" for a single tape.
- Every new hold, veto, shelf or unstick must show, on a human tape,
  that it fires and that the scorecard moved.

## Part 5: what Shane can do today

1. Say yes to task 0.1 and it can go in as a one-line PR this session.
2. Play one dm4 session on v4.17 (no human dm4 tape since 29 August):

```
cd C:\argus\engine ; .\quakespasm.exe -listen 8 -condebug -game argus +developer 1 +deathmatch 1 +record session dm4
```

   then `python tools/harvest_session.py` and
   `python tools/argus_longi.py runs/shane_dm4_<date>.log`.
3. Decide whether task 1.1's forty minutes of engine time runs now or
   after phase 0. Phase 0 first is the recommendation: the bisect is
   only as good as the instrument that judges it.
