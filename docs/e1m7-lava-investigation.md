# e1m7 lava deaths

e1m7 bots die in the central lava lake about four times a match. The
navigation repair of 2026-11-13 cut every graph route into the lake's lava
seats and left that count at parity (4 to 3), so the deaths were not routes
into lava. This note records what they are and the two runtime checks that
address them: one for running off a ledge, one for jumping.

## Two mechanisms

Six full-rate tapes of the unchanged build (progs MD5 `ccdb0f52`, the
repair ladder's control) were recorded with the existing per-frame motion
diagnostic (`developer 1`, `scratch1 697`, the `ARGMOT` rows). They hold 43
lava deaths. Each was traced back to the last grounded frame on a dry floor
before the bot's feet first entered lava.

| Entry | Deaths | What happens |
|---|---|---|
| Run-off from an upper floor | 28 | A grounded bot walks off a ledge at 300 to 450 u/s and lands in the lake |
| Jump from a low floor or the island | 15 | A jump launched at the lake edge carries the bot into it |

Neither is a knock-in: 39 of the 43 bots lost no health in the second
before. The 2 Hz control tapes of the repair ladder split the same way (12
from upper floors, 9 from low floors).

### Run-offs: the guard approved a drop it could not survive

`Argus_MoveHazard` probes 32 to 52 units ahead along the bot's velocity and
traces 280 units down. A lava or slime floor, or no floor at all, vetoes the
heading. A dry floor within the window approves it, and the walk branch
then completes the step off the lip (the `FL_PARTIALGROUND` retry). That is
right for a bot stepping off. A running bot keeps its horizontal speed
through the fall and lands `speed * sqrt (2 * drop / gravity)` further on.
Air control could shorten that only with a wish pointing back, and the
steering that ran the bot off the lip still points forward. (A first draft
of this note said air control can never shorten a flight. That is wrong:
`Argus_AirAccelerate` caps the gain along the wish, not a brake against it,
and the gap-jump tapes below show it braking a flight from 317 to 142 u/s.)

e1m7 puts a narrow dry target under its main lips, with lava beyond it:

| Lip | Dry floor under the probe | Drop | Run-off flight at 320 u/s | Deaths |
|---|---|---|---|---|
| East end of the west walkway | The island | 200 to 225 | 225 to 240 | 15 |
| The four z 280 spawn pads | The low floor, with a 56-unit walkway 64 units down | 224 | about 240 | 6 |
| East walkway's west lip, south walkway's east end | The deathmatch lava bridge (`func_door` deck at z -16, 126 units wide) | 168 to 208 | 210 to 230 | 3 |

The other four upper-floor deaths were a slow jump from the south walkway
and three bots that left a walkway even though the guard had vetoed the
heading. That is a different failure at the lip, not studied here.

Each departure was replayed offline: the departure position, the heading
and speed of the last frames, the guard's probe distance for that speed,
and the world hull plus the deathmatch pads and bridge deck as boxes. The
old guard approved 25 of the 28 departures. At the east lip the guard's own
verdicts were also logged with a scratch build: on every frame before each
departure its floor trace stopped on `door` at z -16 and it approved the
heading.

Two map facts make this a spawn problem as much as a walkway one. The four
z 280 pads are deathmatch-only `func_wall`s (spawnflags 1792), which navgen
does not see, so a bot spawned there is 150 units or more from any seat and
its first heading runs straight at a walkway seat over the pad's edge. All
six pad deaths left within 0.3 s of spawning. The west pad faces the west
walkway's open end, 140 units away, and 14 of the 15 west-end deaths left
within 3 s of spawning. Of the 28, 23 had no hazard event in the second
before: the guard was not overwhelmed, it was asked the wrong question.

What it was not: the steering cause at departure varied (route steering,
combat approach and strafe, noise investigation), so no one steering mode
drives it; no drop link lands in lava from its seat at run speed (offline,
0 of e1m7's one-way drops); and the probe distance is not short, since the
guard saw each lip in time and approved it.

### Jumps at the lake edge

The other 15 started on the low floors (z 56 and 24) or the island (z 8),
each launched with an upward velocity, and each fell 18 to 71 units into the
lava. Every one logged a `jump` event on the departure frame, at 164 to 405
u/s.

Three more full-rate tapes of the run-off build, with every jump site
tagged, held 10 lava entries:

| Jump site | Lava entries | Why it lands in lava |
|---|---|---|
| Reachability jump in `Argus_AI`, while fighting | 5 | It fires when the steering point is more than 24 units up and within 80. A walkway seat 160 units overhead qualifies, so a bot running along the low floor's lake edge under it jumps, at 164 to 442 u/s, toward a seat no jump can reach |
| Predictive gap jump (`Argus_GapJumpOK`) | 4 | Its arc is traced at chest height, so a "landing" can leave the feet 48 units lower: three of the seven gap jumps approved in these tapes put the feet into the island's bank. And nothing holds the launch line in the air, so steering bends or brakes the flight |
| None (an upper-floor run-off the first change misses) | 1 | |

No jump-up link (the climb branch) fired in these tapes. Of 104 untyped
jumps, 70 were the fighting reachability jump.

## The change

`Argus_DropLandHazard` runs at the end of `Argus_MoveHazard`, after the
floor under the probe has been judged dry. When that floor is more than a
step (18 units) below the feet, it projects the landing at the bot's current
horizontal speed, shortens it at the first wall, and traces down there with
the probe's own rules: lava or slime that the hull does not bridge, or no
floor within 280 units of the origin, is a hazard. The speed is the bot's
own, measured now, so a deliberate slow drop keeps today's verdict. Vanilla
QuakeC has no square root, so `Argus_Sqrt` starts from (1 + a) / 2 and takes
three Newton steps (within 0.2 per cent from 0.04 to 6).

Every caller of `Argus_MoveHazard` gets the new verdict: the per-frame
guard, the deflection fan, combat strafes and the recovery walk.

Replayed offline, it refuses 21 of the 25 departures the old guard approved:
14 of 15 at the west end, 4 of 6 off the pads and all 3 over the bridge.
Two of the four it misses are pad departures whose straight-line landing is
the dry east walkway, while the real flight curved: air control steered it
toward a route seat across the lake. So about half of all e1m7 lava entries
are in reach of this change, and the jumps are not.

Offline, against the shipped graphs, a bot running at 320 u/s from each
one-way drop link's seat is newly refused on 9 dm4 links (walkway into the
pit; the landing is over the deep lava), 3 e1m6, 2 e1m1 and 23 e1m8 links
(gravity 100, where a 112 unit drop flies 480 units), and on none of dm2,
dm3, dm6, e1m5, e1m7 or lqdm2. A bot approaching those links slowly is
unaffected.

## The jump change

`Argus_JumpLandHazard` traces the jump the bot would make right now (its own
horizontal velocity, `AR_JUMPVEL` up, map gravity) at the feet, in 0.1 s
segments over the gap jump's own window. Feet entering lava or slime, a
landing on either that the hull does not bridge, or no landing at all
(unless water breaks the fall) is a hazard. A face in the way drops the
body straight down beside it, so a jump onto a step or a ledge still passes.

- The `ar_jump` consumer in `Argus_Physics` (reachability, stall and escort
  jumps) drops a hazardous jump and lets the frame walk on under the brink
  guard, printing `ARGUS <name> jumpveto`.
- The gap jump needs `Argus_JumpLandHazard` to pass as well as
  `Argus_GapJumpOK`, and holds its launch line through the flight with the
  existing sprint flight latch (`ar_sprintstate` 3, cleared on landing).

Typed launches, hurdles and the climb branch are unchanged.

Emulated offline on the 104 untyped jumps in the three tagged tapes, the
check vetoes 5 of the 9 that started a lava entry (3 of 5 reachability, 2 of
4 gap) and 15 of the other 95, most of them reachability jumps at a seat no
jump can reach. The four it passes all had dry straight arcs and were
steered off them in the air. The held launch line covers the two gap jumps;
the reachability jump is left free to steer, since steering toward its
target is its purpose.

## Ladder

Registered before any ladder tape: primary lava deaths on e1m7, predicted
down. Candidate progs `4b758405`, control `ccdb0f52` (byte-identical to the
repair ladder's control and to this change's base). Skill 2, 185 s, played
rate, both arms interleaved in rounds of three engines on one machine, and
every tape in the listen tick class.

Two earlier rounds were rejected unjudged. The machine was shared with
another session, including a mutation-testing run at full CPU, and with
twelve and then four engines running every tape fell to `dedicated_fast` and
lost a third of its game clock. The kept rounds raised their own three
engines to AboveNormal priority. Their game clock still ran 153 to 181 s per
185 s match in both arms; the band compare scales by duration.

| Arm | Tapes | Lava deaths | Stalls | Engagements | Goals |
|---|---|---|---|---|---|
| Control | 5 | 2, 3, 0, 6, 3 | 3, 6, 1, 2, 4 | 82, 95, 92, 126, 83 | 14, 21, 27, 21, 17 |
| Candidate | 5 | 0, 2, 4, 1, 4 | 4, 0, 2, 1, 1 | 74, 93, 104, 86, 105 | 16, 22, 30, 26, 22 |

`argus-mcp compare` returns PARITY: lava median 3 to 2, IQM 2.7 to 2.3,
improvement 95% CI -2.0 to +3.3, P(improve) 0.56, SPRT continue. Adding the
repair ladder's five byte-identical controls (ten in all) gives median 3 to
2, IQM 3.3 to 2.3, CI -1.2 to +3.3, P(improve) 0.65, still parity. Stalls (3
to 1) and engagements (91 to 99) stay in band, with no freezes. The K/D
spread row flagged: candidate median 8 (1, 6, 8, 8, 13) against 6 over the
ten controls (2 to 10). e1m7's 105 listen-class tapes run 0 to 17 on that
metric, so this is recorded rather than read as an effect.

The mechanism was checked separately (not registered). Two full-rate
candidate tapes held 4 lava deaths, all jumps from the low floors or the
island, and no upper-floor run-off; the six control tapes averaged 4.7
run-offs a tape. Across the ten ladder tapes, at 2 Hz (any sample above z
100 in the 2 s before death), the candidate's lava deaths split 5 upper and
7 low against the control's 10 and 8.

What this establishes: the change removes the class it targets, judged by
mechanism. The lava count cannot yet show it. Control tapes alone run 0 to
7, and a cut of about half the entries needs more than five tapes a side to
resolve. The low-floor jumps are now most of what is left.

### dm4 regression check

`Argus_MoveHazard` is shared by every map, so six candidate dm4 tapes were
judged against the eight dm4 controls of the 2026-11-13 mesh ladder, which
ran the same control progs (`ccdb0f52`). Those controls were recorded
earlier the same day, not interleaved with these. Primary registered as
stall parity.

| Arm | Tapes | Stalls | Lava deaths | Engagements |
|---|---|---|---|---|
| Control | 8 | 2, 5, 9, 1, 20, 1, 23, 4 | 4, 3, 6, 5, 4, 4, 8, 2 | 82, 76, 81, 72, 66, 73, 70, 75 |
| Candidate | 6 | 9, 9, 1, 10, 1, 4 | 1, 1, 2, 5, 2, 1 | 70, 67, 72, 63, 78, 96 |

PARITY on stalls: median 4.5 to 6.5 inside a control band of 0 to 25, IQM 5
to 5.8, CI -6.2 to +11.0. None of the candidate's 19 stalls in its first
three tapes fell within 120 units of the pit lips whose run-speed drops the
check now refuses. Lava deaths fell as a secondary: IQM 4.2 to 1.5, CI +0.5
to +4.2, P(improve) 0.86, SPRT accept. That fits the offline finding that a
run-off from dm4's walkway seats beside the pit lands over the deep lava,
but it was not the registered metric and the arms were not run side by side,
so it is a lead for a registered dm4 ladder, not a result.

### Jump ladder

Registered before any tape: primary lava deaths on e1m7, predicted down.
Candidate progs `e9959a8f` (both changes), control `4b758405` (the run-off
change alone). Same rig, rounds of three engines at AboveNormal priority,
both arms interleaved; every tape in the listen tick class and at a full
185 s of game time.

| Arm | Tapes | Lava deaths | Stalls | Engagements | Goals |
|---|---|---|---|---|---|
| Control | 5 | 3, 2, 4, 4, 2 | 1, 4, 1, 2, 18 | 103, 109, 102, 87, 68 | 30, 23, 23, 21, 13 |
| Candidate | 5 | 0, 3, 1, 2, 1 | 3, 5, 3, 0, 2 | 104, 72, 102, 99, 93 | 18, 20, 28, 27, 26 |

At five a side `argus-mcp compare` returns PARITY: lava median 3 to 1, IQM 3
to 1.3, improvement 95% CI +0.0 to +3.0, P(improve) 0.86, SPRT continue.
Stalls (2 to 3) and engagements (102 to 99) stay in band. Goal pickups
warned on the gate card's representative pair, but the medians rose (23 to
26). The K/D spread row flagged again (medians 7 to 11, candidate range 2 to
12 against control 4 to 11).

SPRT asked for more tapes, so the ladder ran on to its cap of ten a side,
still interleaved:

| Arm | Tapes | Lava deaths (all ten) | Total |
|---|---|---|---|
| Control | 10 | 3, 2, 4, 4, 2, 3, 3, 3, 1, 0 | 25 |
| Candidate | 10 | 0, 3, 1, 2, 1, 2, 2, 2, 1, 0 | 14 |

At ten a side the overall verdict is still PARITY. On the registered metric
the median falls 3 to 1.5 and the IQM 2.7 to 1.5, and the improvement's 95%
CI is +0.2 to +2.2, clear of zero, with P(improve) 0.77. The band gate cannot
call an improvement because the control band reaches zero, and SPRT stops
undecided at the cap, which it reads as an effect smaller than 2 a tape.
Stalls (median 2.5 both arms, SPRT rejecting an effect of 6.7 or more) and
engagements (99 to 94.5) are unchanged. The gate card's goal-pickup row
failed on its representative pair, but over all twenty tapes goal pickups
rose (mean 22.2 to 24.0).

One secondary is not explained. The frag gap between the best and worst bot
(`kd_spread`) widened, median 6 to 10.5 (mean 6.8 to 8.6), with both arms
ranging 2 to 12. Frag totals did not change (median 30 to 31), so it is not
a volume effect. The same control build read a median of 6 here and 8 in
the run-off ladder, so the metric is noisy. It is recorded for a registered
check, not read as an effect.

Two full-rate candidate tapes held 3 lava entries (1.5 a tape): one jump
and one walk-in from the low floor, and one east-lip departure of the
"vetoed but still fell" kind. The run-off build's full-rate tapes had 2 to
3 jump entries a tape. `jumpveto` fired 5 and 7 times in them.

On dm4 the jump check is nearly inert: three candidate tapes logged 1, 1
and 0 vetoes. Against the six run-off-build dm4 tapes, stalls hold parity
(median 6.5 to 7, in band, SPRT rejecting an effect of 10.6 or more) and
lava deaths read 2 to 3, inside noise.

## Follow-ups

- [#782](https://github.com/saworbit/argus/issues/782): stop the fighting
  reachability jump firing at a point no jump can reach (the high end of the
  test; #774 and #780 cover the low end and battle grabs).
- [#783](https://github.com/saworbit/argus/issues/783): seat deathmatch
  spawns that stand on brush entities, such as e1m7's pads.
- [#784](https://github.com/saworbit/argus/issues/784): ladder the run-off
  check on e1m8, e1m6 and e1m1, where it refuses run-speed drop links.
- [#785](https://github.com/saworbit/argus/issues/785): register a check of
  the frag gap the jump ladder widened.
- [#786](https://github.com/saworbit/argus/issues/786): keep ladder engines in
  the played tick class on a busy machine.
- [#775](https://github.com/saworbit/argus/issues/775) now carries the three
  run-offs that left a lip after the guard vetoed the heading.

## Reproduce

- Full-rate tapes: copy the control build to an ignored mod dir, add
  `scratch1 697` to its `autoexec.cfg`, select it with `ARGUS_GAME` and run
  `argus-mcp match e1m7 185 <name> --skill 2`.
- The guard's verdict at the east lip came from a scratch build that printed
  the probe's trace entity, floor and verdict every frame inside the east
  walkway box; it is not part of this change.
- Tapes, machine-local and not committed: `runs/lavadiag_e1m7_1..3` and
  `runs/lavadbg_e1m7_1..3` (full-rate control), `runs/lcd_e1m7_1..2`
  (full-rate candidate), `runs/lc2_e1m7_1..5` and `runs/lk2_e1m7_1..5` (the
  ladder), `runs/lc2_dm4_1..6` (dm4 candidate). The rejected slow rounds are
  `runs/landcand_*`, `runs/landctl_*`, `runs/lcand_*` and `runs/lctl_*`.
  For the jump change: `runs/jdbg_e1m7_1..3` (full-rate, every jump site
  tagged, scratch build `b3f04d67`), `runs/jcd_e1m7_1..2` (full-rate
  candidate), `runs/jc_e1m7_1..10` and `runs/jk_e1m7_1..10` (the ladder) and
  `runs/jc_dm4_1..3`.
