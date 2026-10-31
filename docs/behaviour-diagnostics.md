# Behaviour diagnostics and controlled fixtures

The original step 0 added observation and test controls without changing
gameplay. The current development changes are listed below.

## Current development status

Step 1a visual observation caching, ordinary rocket clearance, shared
failed-plan recognition and the [human gait work](#human-gait-hesitation-and-cautious-liquid-approach)
are retained in development. Health/inventory step 1b
is active again in development at the user's request; incoming-projectile perception stays
on hold. Shipped binaries are unchanged. Earlier sections' test totals and
cohort conclusions belong to their recorded builds, not every later change.

Later work adds [equal-link route distances](map-intelligence.md) and
[under-fire recovery](freeze-recovery.md). A [ten-map mover investigation](mover-intelligence.md)
retains the recovery source, fixes offline navigation budgeting and rejects
its runtime mover prototype. e1m3/e1m4 remain experimental and unregistered.
Those studies have their own controls, cadence and stopping rules; the
historical cohorts below are not retested by those later match sets.

The subsequent [combat target policy](combat-attention.md) reconsiders an
opponent using observed cues and recent hostile damage, while retaining
reaction delay, retreat intent and the item goal. Its active-source boundary
and frozen historical health definitions are checked separately.

The earlier muzzle verification comprises 14 native controlled checks and two
negative controls, plus its recorded 41 focused Python tests. It is not a demonstration
of improved gameplay. That muzzle verification ran no new cohorts; its changes remain in
development without installation. See the
[focused verification runbook](lab-workflow.md#focused-checks-without-deployment).

The actual combat-trigger checks (#584), repeatable private verification
(#586, #595), enforced offset control (#594), and supported-speed physical
deadline gate (#589) are completed. Floor-button and opening-door fixes have
native controls (#600, #602). The normal e1m2 route passes; #593's remaining
unsupported motor-override requirement was retired without claiming it passed.
See [opening-door evidence](#opening-door-ownership-and-physical-deadline) and
the [maintained private commands](lab-workflow.md#focused-checks-without-deployment).

Open follow-ups remain the [step 1b gameplay warning](https://github.com/saworbit/argus/issues/583)
and [upstream artifact-download warning](https://github.com/saworbit/argus/issues/452).
They do not authorise more cohorts or deployment. The original warning has not
been labelled noise; historical test totals and tapes remain attached to their
recorded inputs and stopping rules.

## Human gait: hesitation and cautious liquid approach

Movement difference against the human reference corpus, measured with
`tools/argus_humanness.py`. The tool's distance is unsigned, so a new
`--profile` mode reports both populations' medians and quartile bands with the
signed gap in each feature's own scale; nothing below could have been aimed at
without it.

**What the measurement said, before any change.** On dm4 the reference human
pauses 21.9 times per 185 s for 26.5 s in total, a mean of 1.20 s per pause.
Bots pause 18 to 24 times for 14 to 17 s, a mean of 0.64. The *count* was never
wrong: each pause ends too early. The human's pause lengths are also graded and
heavy-tailed - 51 per cent at the 0.5 s tape floor, 23 per cent near 1 s,
14 per cent at 1.5 to 2 s, 9 per cent longer - where the bot's were a spike,
83 per cent at the floor. Separately, the bot's median gait on dm4 was 320 u/s
against the human's 221, while on dm2 both sat at the 320 cap.

**Hesitation.** `Argus_Hesitate` runs on the existing 0.2 s maintenance tick
and `Argus_GaitHold` releases the gait in `Argus_Physics`, so stock friction
does the stopping. Three causes, each legible on screen: `heard` (gunfire or a
pickup beyond 500 units, and the bot faces it), `junction` (the hop after the
one being walked turns more than 65 degrees, and the bot looks round the
corner), `settle` (a stop the bot was already making, held a beat longer).
Length is drawn from a four-way mixture that reproduces the reference shape
rather than one window, and is capped at 3 s of stillness plus the brake.
Personality scales the rate on the same axis the aim spring splits on: the
flick slot hesitates least, the smooth operator most.

**Refusals, each one measured rather than assumed.** No hesitation while an
enemy is live, pursuing, retreating, dodging, in any typed hop, on a mover, at
a door, in liquid, airborne, carrying quad or pentagram, in co-op, inside the
fixed-task fixture, below skill 1, with a stall run open, within 0.6 s of a
brink deflection, or where the resume heading fails the hazard probe. One
hesitation per 200 units of travel. Damage clears the window outright.

**Cautious gait.** Beside lava or slime found by a hazard probe in the last
half second - not beside a drop - and out of combat, the ground wish drops to
62 per cent of the cap. The first cut keyed on "the guard deflected me" and was
convicted by the tapes: it improved dm4 and took dm2's median speed to 237 for
a measured -2.60 against a control at +0.08, because dm2's brinks are mostly
honest drops. `Argus_MoveHazard` now stamps the one branch that knows the
hazard is lethal, changing no verdict and no control flow.

**Two accounting repairs this needed.** The stall detector skips a hesitation
one detector period past the last held frame, keyed on that frame rather than
on the window: `ar_lastpos` is stamped every 0.7 s whether a bot is held or
not, and damage clears the window, so reading the window counted a stall while
the bot still stood where the pause had left it. Without the tail, raising the
rate took dm4 stalls from 5 to 24 across six nodes - an artifact, not a place a
bot could not leave. `ar_hazhold` turned out to be unusable as a live brink
test: `Argus_HazardSteer` is only entered after the heading has already failed,
so its clearing branch is unreachable and the flag stays up for a bot's life
([#607](https://github.com/saworbit/argus/issues/607)).

### Evidence

Ladder at the played listen rate, skill 2, 185 s, same-session control built
from the same tree: dm4 three tapes a side, dm2 four. Receipt:
[`runs/human_gait.results.json`](../runs/human_gait.results.json).

| Arm | Humanness distance (median, range) |
|---|---|
| dm4 control | 1.321 (1.082 to 1.370) |
| dm4 candidate | 1.022 (1.017 to 1.089) |
| dm2 control | 1.278 (1.113 to 1.386) |
| dm2 candidate | 1.008 (0.960 to 1.058) |

The dm2 arms are fully disjoint. The dm4 arms overlap by 0.007.

Per feature, scaled gap, control to candidate. dm4: median speed +3.078 to
+2.406, pause fraction -1.809 to -1.267, pause length -1.107 to -0.580,
direction changes +2.501 to +1.793, active speed +0.688 to +0.409; gyration
-0.868 to -1.080 and local dwell +0.594 to +0.870 move the wrong way. dm2:
pause length -0.789 to -0.037, direction changes +2.691 to +1.848, local dwell
+3.019 to +2.549, cells -0.438 to +0.020, gyration -0.947 to -0.660, pause
fraction -0.530 to +0.423; median speed holds at the cap, +0.000 to -0.104.

Four further changes aimed at what is left were refused. Three were built,
laddered and reverted, each with its post-mortem beside the code it would have
gone in: a gentler
[deflection rung](#refused-a-gentler-first-rung-in-the-deflection-fan) for
heading churn, a [lethal-void stamp](#refused-stamping-the-lethal-void) for
dm4's residual gait, and a [flatter distance
curve](#refused-a-flatter-distance-curve-for-an-unhurried-bot) for local dwell.
The fourth, [re-seating waypoints off
walls](#refuted-without-a-tape-re-seating-waypoints-off-walls), was refuted by
measurement before any code was written.

Hard gates are at parity or better. Medians, control to candidate: dm4 stalls
9 to 8, engagements 74 to 83, world/lava deaths 3 to 5 (inside the 2 to 7 band
this map has always run), route failures 1 to 1, freezes 0 to 0; dm2 stalls
34 to 36.5, engagements 34.5 to 37, world deaths 0.5 to 1, route failures
3.5 to 3, freezes 1.5 to 0.5. Every bot finished positive on every dm4 tape
and on two of four dm2 tapes in each arm.

**Under-fire freezes are pre-existing and equal across the arms**, two in each.
`tools/argus_gait.py` attributes none of the candidate's to a hesitation, and
the control arm produced them on unchanged code. Every one of them is the
documented fight-pin class ([#322](https://github.com/saworbit/argus/issues/322)):
a bot pinned against geometry while fighting, freed by the eight-second
`unstick fightpin` branch. Whether such a pin counts as "under fire" depends on
whether an opponent happened to be shooting at it.

### Refused: a gentler first rung in the deflection fan

Tried after the above and reverted, with its post-mortem beside the code in
`Argus_HazardSteer`. Attributing every counted path-heading swing in two tapes
to the nearest preceding marker put 37 to 49 per cent of them beside a hazard
event, and the fan opens at 50 degrees against a 45 degree counting threshold,
so a 30 degree rung tried ahead of the existing four should have moved a third
of them under the threshold for nothing.

Three dm4 tapes against three said otherwise. The metric it was built for went
the wrong way, pooled +1.793 to +2.259, and stalls rose from a median of 8 to
21. The attribution shows why: hazard-attributed swings did fall, 262 to 235,
while wall-slide-attributed swings rose 78 to 126 and wall-slide firings rose
107 to 145. A gentler deflection keeps the bot nearer the geometry it was
avoiding, so it meets the adjacent wall instead, and the slide clips velocity
into that plane - a bigger heading change than the jink it replaced.

The lesson generalises past this fan, and it matches the 2026-08-28 note on the
step-lateral probe rescue turning the '700 -800' wall-pin into wall-pressing:
the churn is not the deflection step size, it is that the bot is pressed
against geometry at all. Apex or corridor seats keeping routes off the walls
would move this metric. Steering changes will not.

### Refused: stamping the lethal void

Also tried and reverted, with its post-mortem in `Argus_MoveHazard`'s void
branch. The floor trace stops at 280 units because that is the survivable-drop
line, so lava further down reads as plain emptiness and the cautious gait never
fires at the dm4 walkway edges that most want it. Two extra point samples
reached the lava, and on dm4 it worked: median gait gap +2.406 to +1.752 and
distance 1.022 to 0.973 over three tapes, stalls and lava unchanged.

It lost the same trade on dm2 that the first cautious-gait trigger lost: median
gait -0.104 to -1.258 against a human pinned at the 320 cap, with heading churn
+1.848 to +2.213 and distance 1.008 to 1.099 over two tapes.

`tools/argus_voidprobe.py` says why, and it is the reusable part. Sampling
eight headings at the guard's own 48-unit reach from every waypoint in a
shipped graph:

| Map | Probe directions | Floor with lava on it | Void | Under the void |
|---|---|---|---|---|
| dm4 | 1096 | 0 | 18 | lava, 284 to 380 down |
| dm2 | 1720 | 0 | 24 | lava, 284 to 572 down |
| dm3 | 1952 | 0 | 49 | stone 41, water 8 |
| dm6 | 1904 | 0 | 31 | stone 31 |

Two things follow. Every void the guard vetoes on dm4 *and* dm2 bottoms out in
lava, so void-depth lava cannot tell a catwalk from a deck edge - the signal
stops discriminating, which is exactly the failure mode. And **no probe
direction from any waypoint on any surveyed map finds lava underfoot**, because
navgen seats waypoints off hazards by construction: the kept stamp therefore
acts almost entirely from off-graph positions, which in practice means the dm4
pit. That is the mechanism behind its self-targeting, and it is narrower than
"beside lava" suggests.

### Refused: a flatter distance curve for an unhurried bot

The third attempt and the third reversal, post-mortem at the distance curve in
`Argus_PickGoal`. Local dwell is the largest gap left (dm2 +2.549), two thirds
of routed errands are shorter than the 1024-unit radius it measures, and the
majors already read distance at 0.4x - so letting minor items read it at 0.5x
while a bot is armed, stocked and healthy looked like the same proven lever
applied to the same symptom.

It did the opposite. Errands got **shorter**, median 521 units against 547 with
80 per cent under 1024 against 68; local dwell went to +4.121 against a kept arm
of +1.829 to +3.714; and the match economy fell with it, engagements 28-45 down
to 17 and pickups 26-57 down to 19. Flattening the curve compresses the scores,
so the winning candidate flips between ticks and the bot dithers rather than
commits - and a commuting bot picks nothing up, so it drops out of the atoms
that qualified it and spends the rest of the match on the tight curve, poorer.

One dm2 tape, which is normally not enough on this map. It is enough here
because the candidate falls outside the kept arm's range on the metric it
targeted *and* on engagements *and* on pickups, and because the errand-length
check says it failed by design rather than by luck. **The distance curve is not
the cause of local dwell.**

### Refuted without a tape: re-seating waypoints off walls

The deflection post-mortem above concluded that the heading churn is the bot
being pressed against geometry, and pointed at seats. navgen's 5a2 pass already
shifts a decimation seat when walls sit inside 24 units of it, so the obvious
next move was to audit the shipped graphs for seats it missed. Measuring first
cost nothing and settled it:

| Map | Waypoints | Solid cardinal sample at 24u | Air-only cardinal count |
|---|---|---|---|
| dm4 | 137 | 10 (7%) | 2 of 4 open, one seat |
| dm2 | 215 | 16 (7%) | 3 of 4 open |
| dm3 | 244 | 7 (3%) | 25 underwater seats have zero empty samples |
| dm6 | 238 | 17 (7%) | 3 of 4 open |

And the correlation that matters: of 340 located wall slides on dm4 and 680 on
dm2, **6 and 15 per cent respectively fall within 96 units of a wall-adjacent
seat, against 95 to 100 per cent within 96 units of any seat at all.** Wall
scraping is diffuse across everywhere a bot walks; it is not concentrated at
tight seats, so re-seating would not reach it. No ladder was run.

The original air-only tally counted 32 dm3 seats with a nonempty cardinal
sample and described 25 as boxed in. Offline contents classification resolves
that outlier: all 25 centres and all 100 cardinal samples are water
(`CONTENTS_WATER = -3`), with no solid samples. Only seven dm3 seats have a
solid cardinal sample. The other maps' nonempty counts equal their solid counts.

`tools/argus_voidprobe.py --clearance` reproduces navgen's empty-space bar,
which counts water as nonempty; its zero score is not proof of a wall or an
impassable player hull. The graph sidecar does not retain promotion provenance,
so this check does not label seats as ordinary or promoted. The water result
removes the reported reason to re-seat them regardless of provenance. No graph,
navgen, runtime rule or gameplay measurement changed, and no engine ran.
See [#608](https://github.com/saworbit/argus/issues/608). Local input hashes and
per-seat contents are retained in `backups/dm3-cardinal-water/evidence.json`.

### What the reference corpus is, and what that costs

Every human track in the corpus was recorded while a human hunted bots, and the
candidate tapes are bot-versus-bot. That difference is worth quantifying rather
than waving at, because two of the scored features are about roaming. Comparing
the same feature three ways - the human, the bots in those same human sessions,
and the bots in the botmatch arms:

| Map | Feature | Human | Bots with a human | Bots alone |
|---|---|---|---|---|
| dm2 | local dwell | 0.262 | 0.464 | 0.517 |
| dm2 | gyration | 811.3 | 725.9 | 726.8 |
| dm4 | local dwell | 0.879 | 0.951 | 0.966 |
| dm4 | gyration | 527.6 | 437.3 | 389.4 |

Bounded and small. On dm2 local dwell roughly a fifth of the gap is match
configuration and four fifths is the bot; gyration is unchanged by the human's
presence on both maps. So the gaps this section acts on are mostly real bot
properties, and a botmatch is a fair place to measure them - but a fifth of the
dwell gap is not something any bot change can reach.

### Limits

This is a movement-distribution result on two maps at skill 2, in development
and not installed. It is not a demonstration of better human play, better
spectating, or a difficulty change in either direction; no human session has
been played against it. dm4's median gait remains the largest single gap at
+2.406, because its walkway edges read as void rather than lava - the lava
surface sits further than the 280-unit floor probe below them - so the cautious
gait does not fire there. Closing that was [tried and
refused](#refused-stamping-the-lethal-void): it works on dm4 and costs dm2 the
same trade the first trigger did. Gyration and local dwell went the wrong way
on dm4 and are unexplained. dm2 single tapes swing widely on identical code;
the four-a-side arms are what the disjointness rests on, not any one tape.
The session that would settle the feel question is filed as
[#610](https://github.com/saworbit/argus/issues/610).

## Shared failed-plan recognition

`Argus_PlanObserve` keeps current goal identity, closest useful objective
distance, last reached waypoint and a visit epoch. Existing waypoints hold
one epoch mark per bot slot. Useful distance reduction (12 units, accumulated)
or a waypoint not previously reached during this attempt clears failure
history and renews the ordinary 20-second progress deadline. Detours cannot
increase the best-distance reference. Goal changes and new lives start fresh. Rebuilding a
route or moving sideways does not erase a failed attempt. Combat, tactical
ownership and existing door/mover/typed-link handling reset or pause this
navigation evidence. Waiting without failed recovery attempts remains valid.

Two failed attempts still use the existing bailout and per-bot goal shelf;
the ordinary utility selector chooses the alternative. There is no authored
escape path, map/item-class rule or nearby-item radius in the helper. This is
navigation-plan evidence. Revisiting a two-node or longer waypoint cycle no
longer renews the deadline. A failed co-op FETCH rests for 20 seconds after
route failure, repeated stalls or expiry, retaining its stack request. The
rest belongs to that bot and subject; a different request and another bot
remain eligible. Retrying starts a fresh deadline. Combat and the external
fixed-task tool retain their existing deadline ownership. This development
change has not been installed.

`tools/verify_plan_progress.py` builds owned source/asset copies and runs only
through the source-authoritative native lab. Its fixed default schedule covers
18 decision contracts on each of dm2/dm4, two physical dm2 cases, and a
legacy-reset negative control. The private `plan_progress.qc`, `plan_escape.qc`,
`plan_edges.qc` and `plan_physical_edges.qc` fixtures are excluded from production. `PLANFIX`, `PEFIX` and `PMFIX`
records are checked independently; the whole tape is quarantined with
`BHVRPL begin`. These tests do not reconstruct ARGLOG metrics.

The development checks passed all 36 decision contracts. In the live-item
physical case the bot released its failed goal by 4.3 seconds and moved beyond
220 units by 5.7 seconds; the respawn-camp case released by 3.7 seconds and
escaped by 5.5 seconds. Both selected valid alternatives and retained 100
health. The legacy-reset control released at 11.4 seconds but had not escaped
when its 12.2-second observation ended. This is controlled evidence, not a
population regression or equivalence result. Tapes and hashes are retained in
`backups/plan-development-20261027/`; the first physical attempt was rejected
for contradictory fixture flags and retained separately. Its oracle was not
relaxed. See [#589](https://github.com/saworbit/argus/issues/589) and the
[repeatable command](lab-workflow.md#focused-checks-without-deployment).

The edge follow-up reproduced nine failing checks on each of dm2/e1m2 before
fixes. The final expanded suite passed 39 checks per map, including co-op
retry/rest/subject isolation, combat and fixed-task deadlines, 24 distinct
detour waypoints, two-/three-node cycles, per-bot visit marks and epoch
rollover. `--mode edges` selects this pair of ten-second fixtures. These
inject controller state and waypoint arrivals, including co-op globals;
they do not demonstrate a physical long-detour route or a full co-op match.

The original 36 decision checks passed again. Physical live-item/camped-item
cases escaped beyond 220 units by 2.9/4.3 seconds, both at 100 health. The
legacy-reset control remained within 92.4 units at 12.2 seconds. Timings vary
with engine startup and are controlled-case evidence, not a speed comparison
against the earlier run. The enabled tactical trial passed 415 guards over
97 fields, with a damaging 41-degree return shot. All 78 focused Python tests
passed. One private diagnostic startup was rejected before trial start;
pinning protocol 15/max_edicts 600 allowed the same production source to pass.
Evidence: `runs/plan_progress_edges.results.json` and local
`backups/plan-edges-20261027/`. All rejected attempts are retained.

The earlier separate physical follow-up passed a real co-op retry on dm2: the bot
rested from 2.1 to 22.1 seconds with its FETCH request intact, retried with a
fresh deadline, then touched the goal at 22.8 seconds at 100 health. A cage
opens when that first rest expires; the fixture never moves the actor or
assigns another goal after setup. This is an isolated co-op engine fixture,
without a human teammate or monsters, rather than a complete campaign test.

Longer physical detour completion **failed**. The clean normal-pace e1m2
fixture travelled 1,269 units but released its goal near n130 at 7.8 seconds
without contact. A separate native player-sized walking probe passed the
canonical n130→n133 link. Approach/handoff or motor behaviour needs further
isolation; this does not convict the progress deadline, which had not expired.
The earlier half-pace attempt also failed, under different initial state.
The deadline-control build was not run because the successful-detour
precondition was missing. Track the movement reproduction in
[#593](https://github.com/saworbit/argus/issues/593). No production changes or
deployment followed that investigation; step 1b was still parked then.

`--mode physical-edges --physical-part coop` reproduces the passing co-op
case. `--physical-part normal` selects the original e1m2 route, while
`--physical-part detour` includes normal pace, the slower real door and both controls,
stopping on failure. All are private native builds. The physical oracle requires continuous samples and actual
trigger contact, and a source audit rejects scripted movement/progress or
observer writes to the actor. All 13 plan evidence tests pass. Evidence:
`runs/plan_progress_physical_edges.results.json` and local
`backups/plan-physical-20261027/`, including rejected setup attempts.

The health/inventory manifest verifies the active function hashes and reverses
allowlisted amendments only in memory before reconstructing its historical
parked/candidate sources. Their frozen hashes remain unchanged.

## Physical offset entry (#593)

### Solid floor buttons and relayed doors

An isolated real-button comparison identified a separate contact gap. A bot's
`walkmove` stepped across e1m2's floor button with `groundentity` naming that
button and `FL_ONGROUND` set, but did not receive its solid impact callback.
A real protocol-15 player crossing the same button did activate it.
`Argus_SupportButton` now dispatches the existing stock `button_touch` only
for a live bot's engine-confirmed support, an unpressed touch button and the
expected callback. It preserves `self`, `other` and `activator`; it does not
write movement or add traces, entities or RNG calls. Human movement is unchanged.

The door path also resolves physical buttons behind target relays. A projected
floor point is rejected for a touch trigger if the player's hull cannot reach
its brush. Lookup is capped at four target levels and 32 work units. Direct
buttons, reachable triggers and shoot buttons retain their paths. A solid
button must acknowledge activation before the bot waits for its door; bounding
box slack alone is not evidence of a press.

Run `python tools/verify_private_fixtures.py button --output backups/<new-directory> --prefix <new_prefix>`
for a physical bot crossing, a real-player control using the same binary and a
private mutant disabling only the support callback. The corrected bot and player
activate the button; the mutant crosses it without activation. Passive guards
check callback context, continuous movement and retained health. `door` selects
the bounded lookup/state contracts on dm2/e1m2 with independent traversal and
premature-hold controls. These are private native builds with unchanged installed
binary hashes, not gameplay cohorts or deployment.

Before the opening-wait follow-up, the original normal-pace route reached real goal contact at 19.4 seconds,
after 4,715.2 horizontal units and 21 distinct legs, at health 100. The historical
half-speed diagnostic remains failed: it drops into a lower room before the door
and expires after 20 seconds without useful progress. It changes the motor's
speed constant and is not used as the positive deadline witness.
`half` and `deadline-control` retain individual historical-case reproduction.
All existing distance, away-from-goal, waypoint, health and contact bounds remain
in force. Two alternate normal-speed long routes were rejected by those bounds:
one lacked the required movement away from the goal, and the other credited a
waypoint while too far away. Neither establishes deadline renewal. Failed
fixtures and rejected candidates remain retained locally. The following
opening-door witness supplies the missing supported-pace deadline evidence.

### Opening-door ownership and physical deadline

A nearby opening slab still blocks the body. Releasing door ownership at
`STATE_UP` made the bot walk into it, stall twice and drop its reachable goal.
`Argus_DoorOpeningWait` now retains ownership for a near-side bot within 320
units of the closed doorway until opening finishes. The button acknowledgement
starts one eight-second opening phase; it clears the opener so later frames
cannot extend that deadline. Timeout still takes the existing failed-door path.
Remote buttons, already-passed doors and finished/closing handling retain their
walking paths. The change adds no traces, fields, entities or movement constants.

Physical case 6 uses the original e1m2 route at shipped pace 320, with real door
`*27`'s mapper-supported speed set to 20 only at setup. Thereafter the bot owns
movement/routing and the engine owns the door. Paired passive samples require a
closed start, actual opening displacement and the declared mover speed. Existing
distance, away-from-goal, waypoint, continuous movement, health and contact
bounds remain unchanged; contact must occur after 20.5 seconds and before 40.

The original code released the goal at 19.0 seconds against the moving door.
The corrected route reaches contact at 25.2 seconds, after 4,809.9 horizontal
units and 21 distinct legs, at health 100. Disabling only deadline renewal
releases the goal at 20.2 seconds without contact. These are controlled
counterfactuals, not population performance or deployment evidence.
Disabling only the opening wait instead reproduces premature release at 19.1
seconds. The original unmodified-speed door route also passes, at 21.1 seconds
with 21 distinct legs and health 100.

Select `--mode physical-edges --physical-part mover` for the positive case,
`mover-control` for the deadline-disabled case, or `mover-release` for premature
door release. Each uses a new `--output backups/<new-directory>` and one bounded
45-second native experiment. `verify_private_fixtures.py door` also executes
the actual extracted door decision block on dm2/e1m2 to check acknowledgement,
non-renewal, timeout, remote/past handling and preserved goal ownership.
The historical half-speed diagnostic and rejected long witnesses remain
retained; this witness does not establish half-speed navigation or resolve #583.
The 160 motor override is excluded from the default gate. It does not scale the
graph's 280-speed arc model, fixed 250/310 launch thresholds or typed-hop speeds;
changing ordinary movement to satisfy that input would test a different navigation
model. `half` and `deadline-control` remain explicit diagnostic selectors. The
original supported-speed #593 defect is fixed; its remaining half-speed acceptance
is retired as unsupported test work rather than reported as passed.

`tools/verify_offset_entry.py` seeds one existing route leg at n130 on e1m2,
then leaves the normal scheduled bot code to move and hand off. The four
cases distinguish centred/offset and grounded/airborne entry. They require
actual trigger contact within six seconds, full health and continuous sampled
movement. Excluded actors are marked as cameras as well as non-solid, so
they cannot contaminate the navigation test through perception. A source
audit rejects observer movement, actor writes and manufactured progress.

The old policy reproduces the airborne offset failure at 2.1 seconds while
the centred airborne control passes. Tightening only normal arrival is
insufficient: the separate apex shortcut bypasses that gate. A landing-only
candidate fixed the first entry but regressed recovery; its receipts are
retained. The final shared guard checks landing and, for off-centre approaches, two lateral rays into
the next corridor, while preserving typed links, height changes, final arrival
and the 48-unit radius. It applies to both handoff paths. The wall-slide
cutoff remains 20; lowering it was an exploratory control, not the adopted fix.

All four final entry cases pass, at 0.6/0.8/1.1/0.9 seconds respectively, with
full health. The full normal-speed approach now passes this corridor and gets
farther into the map, but complete long-detour success remains a separate
integration check. Validated apex transitions now provide plan progress;
revisits still use the existing per-goal epoch rule.

Run `python tools/verify_offset_entry.py --output backups/<new-directory>`.
The default includes current cases and an old-handoff policy control; use
`--variants current --cases 3` for just the fixed airborne offset. The plan
declares every selected outcome before launch. All cases must contact except
old-handoff case 3, which must fail with valid physical evidence. Unexpected
contact, missing contact in a required passing case, and invalid control
receipts return nonzero after retaining the complete result and rejection.
The offset evidence tests run in fast CI (#594).
Raw accepted/rejected builds are local under `backups/offset-entry-20261027/`.
No cohorts or installation accompany these controlled checks.

## Passive snapshots

Set `developer 1` and `scratch4 590` through the lab's `tune` tool to
enable `BHVDBG`. Set `scratch4 0` to stop. This is independent of the
existing `scratch1 1` decision tape. Snapshots run at most once per 0.2
game seconds per bot; they are separate from ARGLOG/ARGEVT metrics.

Each snapshot reports the existing perception stamp, descriptive intent,
state transition, position, remembered enemy position, goal class, route
node, distance, best-distance improvement, displacement, nav/tactic mode
and actual frame time. `reported_visible` means `ar_seen == time`, not
an independent visibility check. `intent` describes state and is not a
new steering arbiter or a claim about which subsystem last wrote yaw.
`gain` compares distance to the best observed distance for the same node
and goal. Negative gain is permitted. Node/goal changes reset that yardstick.
There is no failure detector, recovery, belief estimate or new commitment.
Tactical aborts also emit their existing reason on the BHVDBG channel.
Scalar output uses stock Quake's one-decimal formatting. Frame time is emitted
as `dt_ms` so played-rate values remain measurable. Snapshots batch strings
through vanilla builtin 25: 12 console calls instead of the original 31. Each
call contains at most one `ftos`/`vtos`; original Quake shares their temporary
buffer, so combining two conversions would corrupt values on that engine.
Both behaviours are visible in [id's builtin implementation](https://github.com/id-Software/Quake/blob/master/WinQuake/pr_cmds.c).

The passive module may write only `self.ar_bd_*` fields. Its allowed
builtins are `cvar`, `dprint`, `ftos`, `vtos` and `vlen`. It cannot use RNG,
traces, makevectors, movement, weapon calls or gameplay setters. Death,
respawn, roster removal and fixture cleanup reset diagnostic history;
target transitions are identified from the next snapshot's current state.

## Isolated engine fixture

Run this only in a disposable lab match. It intentionally reuses TACFIX's
six-second loadout/position setup, temporary weapon-touch suppression and
other-bot freeze. It does not promise to restore pre-trial match history,
removed backpacks or projectiles, the subject's previous life/loadout, or
the elapsed world clock. The owned engine is stopped after the suite.
Cleanup restores the temporary touches and frozen bots, removes targets,
clears references and resets diagnostic history before acknowledging done.

The server must arm `developer 1` plus `scratch1 590`. Real-client impulse
218 starts the wrapper; `scratch2` selects the existing TACFIX case 0..14,
`scratch3` is a positive integer trial ID, and `scratch4 590` enables
diagnostics. The existing tactical and behaviour fixtures mutually refuse
overlap. Developer mode alone cannot arm it.

The runner uses the existing lab engine/client APIs and console-ready
acknowledgements. Every trial requires ordered begin, trial, end, successful
cleanup and done records. Case 9 deliberately sends a second impulse and
requires one busy refusal. Bad IDs, duplicates, missing records, disconnects
and timeouts fail; the runner stops its owned engine on failure.

Use the CLI built from this checkout. On Windows its development path is
`tools/argus_mcp/target/debug/argus-mcp.exe`; an older installed MCP/CLI does
not acquire the new command until rebuilt. The examples assume matching QC
has been staged in the disposable lab.

```text
argus-mcp behaviour-suite dm4 bhv_dm4_off --diagnostics off --no-compile
argus-mcp behaviour-suite dm4 bhv_dm4_on --diagnostics on --no-compile
argus-mcp behaviour-suite dm2 bhv_dm2_slow --step 0.1 --no-compile
python tools/check_behaviour_fixture.py runs/bhv_dm4_on.log
python tools/check_behaviour_fixture.py runs/bhv_dm4_off.log --diagnostics off
python tools/check_behaviour_fixture.py runs/bhv_dm2_slow.log --hz 10
```

Compile via the lab first. Without `--no-compile` the CLI uses the normal
lab compiler/installer, including configured external game installs.
Harvest any human session before launching. The default suite is three
case-0 trials followed by cases 1..12, retaining the existing tactical cases.

BHVFIX independently records actual position, a centre visibility trace,
real owned rocket count, target health and subject health. Centre visibility
is not full-body concealment. The separate TACFIX observer/checker remains
the full-body, first-return-angle and damage-window oracle.

During a behaviour fixture, a guard surrounds the subject's actual scheduled
observer call. It compares 97 gameplay fields and the trace/vector/self/other
globals exactly before and after that call, including plan and fetch-rest
fields. The latest six-second enabled native trial passed 415 guards and retained a
damaging changed-angle tactical return. Saved values are local variables,
never live engine fields on a snapshot entity. The tape records guard calls
and enabled emissions, so a throttled/no-op observer cannot masquerade as
tested enabled diagnostics. This proves the checked immediate state only;
it does not by itself prove match-level equivalence or timing overhead.

## Verification limits

- `tools/test_behaviour_fixture.py` adversarially tests acknowledgements,
  restoration, cadence, diagnostic arms and the passive source allowlist.
- `python tools/check_behaviour_fixture.py` without a log audits the observer
  and checks the generated guard. `--write-guard` regenerates only that guard
  from its explicit field list and current QC field types.
- Rust acknowledgement tests exercise the driver separately from the tape
  checker. A TACFIX acknowledgement cannot complete a BHVFIX trial.
- Use repeated ordinary matches on dm2/dm4 and measured matching tick classes
  for regression checks. Short parity does not establish equivalence.
- Record source, engine-binary and graph hashes for every arm. The original
  goal/pickup, shot/hit and human/bot metric boundaries are unchanged.

No perception changes are included in this step.

## Ordinary-match equivalence and overhead investigation

The diagnostic measurement modes are `scratch4 0` (off), `590` (batched
snapshots), `591` (the same state computation without formatting/output), and
`592` (the original fragmented snapshot output as a reference). The latter
two are lab controls. Tactical-event output is suppressed in compute-only
mode. Diagnostic history updates still occur there; gameplay fields do not.

Set `developer 1; scratch1 591` through separate `tune` calls for a common
cadence probe. It emits `BHVTIME` every five game seconds with actual frame
count, accumulated seconds, mean/max milliseconds and counts above 20/50 ms.
It performs no fixture setup and writes only its own diagnostic accumulators.
Disable it with `scratch1 0`. `BHVTIME` is outside established match metrics.

`tools/run_behaviour_equivalence.py` uses native lab MCP match/tune/brief tools,
owns each disposable match, pins QC/CLI/binary/graph hashes and records process
CPU, output bytes and authoritative gameplay metrics. It never launches an
engine directly. `tools/check_behaviour_equivalence.py` evaluates the fixed
32-tape cohort, or the independently registered 512-tape cohort with
`--pairs 128`, using pre-registered 90% paired Student-t confidence intervals.
An interval crossing an equivalence bound is inconclusive. A non-significant
difference alone cannot pass. The retained protocol specifies the bounds and
keeps exploratory mechanism runs separate from confirmation.

The larger cohort uses `tools/run_behaviour_registered.py` to stage only the
workspace engine candidate and restore shipped bytes on exit. Its immutable
[protocol](behaviour-goal-cohort-protocol.json) pins the schedule, identities,
code hashes and unchanged acceptance bounds. A technical failure stops the
schedule and retains its tape; replacement requires a recorded investigation
and amendment. No outcome-based exclusions or stopping on a pass.
`tools/report_behaviour_cohort.py` refuses partial execution, audits the frozen
code snapshots and raw hashes, and retains the exposure failure and additional
first-attempt sensitivity. Full receipts and registered code remain in
`backups/behaviour-equivalence-larger/`; the public evidence is
`runs/bhv2_equivalence.results.json`. A future cohort needs a fresh registration
and run prefix; do not mutate the completed study's protocol.

`gl` is the existing completed-goal counter: nearby invalidated-item and
arrival paths increment it. Preserve that definition across comparisons.
`ARGEVT goal` is goal selection, and `ARGEVT grab` is a committed battle-item
detour; neither proves an item touch. Do not describe their totals as actual
items collected. A question about a particular pickup still needs its touch
or a real client's observation.

`tools/run_behaviour_replay.py` supplies an additional controlled-input test.
It copies source into `backups/`, substitutes a deterministic QC random-input
provider and uses the vanilla `host_framerate` cvar. No production RNG or
manifest changes. Two disabled repeats must match before comparing compute,
fragmented-output and batched-output modes. Original-source copies use the
same inputs as a separate control. An independent inverse-edit audit checks
every QC/build/nav JSON source against its original after removing only the
explicit harness edits.

Each replay ends after 3,842 frames and exports ordinary gameplay records and
the stock engine's entity dump, including RNG end state and goal counters.
Only `ar_bd_*` diagnostic fields are excluded from the state comparison.
Every other exported field must match, and the engine's high-water edict count
must remain at or below 600. Positive goal coverage is required on both maps.
The checker rejects changed goal counts, changed RNG state, altered gameplay,
incomplete frames and missing state. Entity dumps round floating values, so
byte-identical exports do not mean every internal float was independently
compared. The scheduled observer guard supplies exact checks for its listed
77 fields. Controlled-input equality and real-time statistical equivalence
are distinct findings; keep any inconclusive real-time interval visible.

## Perception step 1a

After the larger diagnostic cohort passed, the user resumed the implementation
plan. Step 1a introduces cached visual inputs for the current combat target.
`Argus_ObserveEnemy` is the normal producer of the sight timestamp, observed
position, velocity, powerup cues and movement flags. Its callers commit only
after a successful visibility check. The secondary-threat scan records its
proven position at the shared scan boundary, including the tactical path.

`Argus_EnemyPosition`, `Argus_EnemyVelocity` and `Argus_EnemyPowerThreat` read
those observations. Hidden ordinary-combat prediction is bounded to 0.4 seconds
and 128 units; the existing pursuit and speculative corner shot keep their
original remembered vanish point. Unseen damage records the existing flinch,
but cannot manufacture a visual sighting. The new visibility check in the
damage callback preserves all nine incoming trace globals for the weapon
caller. Occlusion is checked before the ring glimpse so concealed powerup
changes cannot consume extra random draws.

Observation identity is invalidated on target loss/change, death, respawn,
roster removal and human client reuse/disconnect. Alive/dead validity checks
remain separate from tactical knowledge. Exact enemy-health decisions,
hidden-inventory hunch valuation and projectile-recognition gates are the
separate planned steps 1b/1c and remain unchanged here.

The `PERFIX` engine fixture is developer-gated by scratch1 593 and real-client
impulse 219, and additionally refuses production builds: its controlled-input
flag is zero in normal play. `tools/run_perception_fixture.py` creates private
source copies with a constant random-input provider and draw counter. Production
`random()` remains vanilla builtin 7. The private world emits `BHVRPL begin`
and activation emits `BHVFIX begin perception`, so existing native analysis
quarantines the whole tape from ordinary bot bands, even if a trial fails.

Both observers genuinely see the same target before an actual 0.2-second
sight-loss interval. The harness independently proves two world-occluded
positions, changes the hidden actor's position, velocity, movement flags,
weapon and powerups, then compares actual combat aim/steering/fire decisions
and random-draw counts across six weapon/stack cases. Further checks require
visible reacquisition, bounded prediction, unseen/visible damage and preserved
caller traces, secondary observations, target death/switch, respawn and roster
cleanup. There are 20 required checks per trial. The checker rejects incomplete,
reordered, wrong-ID, refused and failed trials; cached diagnostic claims alone
cannot supply acceptance.

The matrix covers dm2/dm4, observed ring off/on, measured played/10 Hz cadence,
and repeated trials. A private positive control restores the exact saved old
combat and pain function bodies; it must fail. Source inverse-edit audits
allow only the declared private input-provider changes and those exact legacy
bodies. The passive observer guard now also compares the new observation and
threat state, for 87 gameplay fields in total. Older 77-field results retain
their original scope.

Ordinary control/candidate matches use the saved pre-perception candidate and
the new production build, common timing probes and diagnostics disabled. They
are a small regression screen, not another powered equivalence study. Results
and full source/binary/nav/CLI identities are retained under
`backups/perception-step1/`.

### Step 1a results (2026-10-24)

The final callback-safe candidate passes all 320 directed checks in 16 trials:
dm2/dm4, played/10 Hz, ring off/on, two repeats. Measured played frames were
14-15 ms; slow frames were 100 ms. All four old-code positive controls fail
the hidden-input invariant as required. Production randomness remains builtin
7; the controlled provider is confined to private copies.

The full tactical matrix before the callback safeguard passed 68 trials and
15,915 passive guard comparisons, including 12 damaging nominal returns.
The final candidate passed 24 callback/lifecycle follow-up trials and another
5,646 guard comparisons, including 12 damaging nominal returns. These are
different build versions, not 92 trials of the final binary. The 48 focused
Python tests pass. The final native compile is id format, with no new errors
or warnings; six pre-existing stock Q302 warnings remain in its raw output.

The fixed ordinary screen completed all 12 matches, with native durations
59.7-60.1 seconds. Native comparison used engagements as its registered primary
metric and returned parity on both maps. Results are mixed, with lower dm2
engagements and higher dm4 engagements; both candidate medians are inside the
control bands (dm2 5-17; dm4 9-24), and both native 95% intervals include zero.
The following are medians of three native briefs per arm:

| Map | Arm | Engagements | Consumed goals | Frags | Stalls |
|---|---|---:|---:|---:|---:|
| dm2 | Control | 11 | 4 | 4 | 7 |
| dm2 | Candidate | 6 | 2 | 3 | 13 |
| dm4 | Control | 16 | 8 | 2 | 1 |
| dm4 | Candidate | 21 | 11 | 7 | 2 |

This screen does not establish gameplay equivalence, better skill or greater
human likeness. The dm2 direction remains visible rather than being erased by
the native parity label. A larger registered evaluation and human review are
still needed before a release claim. Step 0's 512-match diagnostic equivalence
result applies to its frozen diagnostic build, not this gameplay change.

One initial fixture launch failed because console injection preceded engine
health readiness; the driver now waits. A tactical case-13 reader defect was
fixed to require the trial's own successful hull proof, then the same completed
tape was rechecked. Finally, all 12 ordinary tapes completed before the export
failed: native CLI comparison emits UTF-8 text, not JSON. The exporter now
retains that text and can recover comparisons without relaunching engines.
All earlier tapes and failed attempts remain retained.

The machine-readable [evidence bundle](../runs/perc1_perception.results.json)
contains native briefs/comparisons, raw hashes, private inverse-edit audits,
build identities and source scope. Final candidate SHA256:
`56a4ee159959532c36108d53c49ecf579b1e72164e804ff7561ef06b7dae454a`.
The source changes are uncommitted; all three shipped/compiler binaries are
restored to their original MD5 `A3F7AA9428846DE7F7B327506F5F5D3D`.

### Larger dm2 engagement holdout (2026-10-25, complete)

The user requested a larger independent cohort to investigate the lower dm2
engagement rate. The [frozen protocol](perception-engagement-cohort-protocol.json)
registers 128 adjacent control/candidate pairs, 256 fresh one-minute dm2
matches at skill1. Order alternates by pair. Both saved binaries are unchanged;
the pilot is excluded from inference. No QC or further perception work and no
deployment are authorised by this experiment.

The primary outcome is the native engagement-acquisition rate per match-minute.
It is not a count of shots or damage. A paired 95% interval and fixed four-pair
block-bootstrap sensitivity assess a reproducible reduction. A separate paired
90% interval strictly inside +/-2 engagements/minute, supported by the same
block sensitivity, tests practical equivalence. A detected reduction takes
precedence even if small; a non-significant difference alone is inconclusive.
The existing dm2 65% retention floor is reported separately, not substituted
for this decision rule. The step0 goal-rate margins remain unchanged.

Runner, analysis, tests, dependencies, QC source, saved binaries, map resources,
engine and CLI are pinned. The seven cohort tests include end-to-end receipt
auditing, tamper detection, incomplete cohorts, exact inference directions,
independent SciPy interval agreement and correlated-block sensitivity. The
planning model uses paired SD6 and estimates 96.5% equivalence power at zero
effect; it does not guarantee power under serial dependence or at a bound.

No interim primary intervals, optional stopping, outcome-based exclusions or
sample expansion. Every attempt is retained. Technical invalidity stops the
runner for investigation before any logged replacement. The lab binary is
restored after each attempt; the two other binary locations stay untouched.
Full attempts and progress are in `backups/perception-engagement-cohort/`.
Health/inventory and projectile-perception changes remain on hold.

All 128 pairs completed: 256 valid matches, no exclusions, replacements,
technical amendments or interim statistical decisions. Native exposure was
59.6-60.1 seconds, all listen class. Execution ran from 07:09 to 11:31 Sydney
time on 25 October. The saved candidate/control and all frozen inputs matched
throughout. The registered analysis concludes **practical equivalence: the
earlier sharp engagement drop is consistent with sampling noise**.

| Engagement rate, per match-minute | Result |
|---|---:|
| Control mean | 11.2900 |
| Candidate mean | 10.7921 |
| Candidate minus control | -0.4979 |
| Paired 95% interval | [-1.3319, +0.3361] |
| Paired 90% equivalence interval | [-1.1963, +0.2004] |
| Four-pair block-bootstrap 90% interval | [-1.1067, +0.1500] |
| Four-pair block-bootstrap 95% interval | [-1.2179, +0.2780] |

Both 90% intervals are strictly inside the pre-registered +/-2 bound; neither
95% interval confirms a decrease. This is an equivalence result under that
practical margin, not proof of exactly zero effect. The candidate's mean is
95.59% of control. The separate existing 65% retention floor passes its
one-sided non-inferiority check. Both run-order strata have small negative
point estimates (-0.6284 and -0.3674), rather than a reversal between orders.
An independent SciPy API check reproduces the intervals; paired difference
p=0.2396, equivalence TOST p=0.000258. Equivalence, not non-significance, supports
the noise interpretation. See the
[paired-test implementation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html)
and [paired equivalence method](https://www.statsmodels.org/stable/generated/statsmodels.stats.weightstats.ttost_paired.html).

Cadence was comparable: mean difference -0.0010 ms, rounded-value 90% interval
[-0.1280, +0.1260] ms, inside the descriptive +/-1 ms reference. Complete-window
>50 ms frames totalled 10 control versus 9 candidate. CPU difference was
-0.0366 ms per wall second, descriptive 95% interval [-0.8074, +0.7342]. These
measurements do not show a timing or CPU slowdown explaining an engagement
loss. The final partial timing window is still unobserved.

There is a separate **exploratory lava warning**. Native lava deaths were
20 control versus 45 candidate, across 18 versus 38 matches; no single tape
contributes more than three. The increase appears in both run orders. Mean
rates were 0.1564 versus 0.3520 per minute, difference +0.1956, descriptive
95% interval [+0.0636, +0.3276]. These secondary intervals were not adjusted
for eight comparisons and do not constitute a pre-registered confirmatory
lava test. The signal warrants separate validation before deployment; the
engagement result does not clear overall gameplay. Goals, frags, deaths,
stalls, freezes, acquisitions and grabs have descriptive intervals including
zero. Native band comparison reports parity, with median lava zero in both
arms; its release wording does not override this unresolved secondary signal
or the user's deployment hold.

The [registered statistical result](../runs/perc2_engagement.results.json) and
[audit bundle](../runs/perc2_engagement.audit.json) retain all raw tape hashes,
native metrics/flags, comparison text, independent verification and final
checks. Seven cohort tests and the combined 11-test perception suite pass.
No QC, health/inventory or projectile-perception changes were made. All three
binary locations are restored to their original shipped bytes; no engine
remains running. Nothing is deployed, and both requested holds remain active.

### Separate dm2 lava holdout (2026-10-25, complete)

The user requested an independent confirmatory experiment for the exploratory
lava increase. The [frozen lava protocol](perception-lava-cohort-protocol.json)
registers 256 adjacent counterbalanced pairs, 512 fresh one-minute dm2 matches
at skill1, using the same saved binaries. All earlier tapes are excluded from
inference. Lava deaths from native BSP-contents classification are the sole
primary outcome, normalized by native exposure.

Regression requires positive lower endpoints in both paired and four-pair
block-bootstrap 95% intervals. A paired-only increase is inconclusive under
the sensitivity check. To support noise, the paired and block one-sided 95%
upper limits must both rule out +0.10 deaths/minute. This is directional
practical non-inferiority, not symmetric equivalence or proof of zero effect.
Any confirmed increase takes precedence, including a small one. Fewer than
20 pooled events produces an inconclusive inference, retaining all matches.
An exact conditional Poisson rate-ratio check is supplementary; its independent
event assumption does not replace the pair/block analysis.

The sample-size model estimates 95.6% paired-test power at the earlier effect,
with SD0.85 versus the observed0.7546. Zero-increase non-inferiority power is
84.4% at SD0.60. Block agreement, drift and true effects near the harm bound
can reduce these estimates; the sample will not expand based on outcomes.
Five lava-specific tests cover inference direction, small real harm, sparse
events, exposure, independent SciPy interval agreement, exact ratio symmetry,
complete-cohort auditing and tamper rejection. The combined perception suite
also passed before registration.

The frozen code/resources are checked on every attempt. Technical invalidity
stops execution for investigation and a logged amendment before replacement;
no exclusions for any gameplay outcome. No interim primary statistical looks.
The workspace engine binary is restored after each attempt; no compilation,
QC edits or deployment. Health/inventory and projectile perception remain on
hold. Attempts and progress: `backups/perception-lava-cohort/`.

After 138 valid matches, candidate070 failed the pre-registered timing
validity: 56.6 native seconds and a non-listen native cadence class, with
58 frames over 50 ms. The map was correct and no engine error was reported;
the cause of the timing disruption is unproven. The raw tape, working-directory
qconsole and full attempt receipt were retained under
`perc3_invalid_dm2_candidate070_a1`.
[Amendment001](perception-lava-cohort-amendment-001.json) was recorded before
replacing that missing cell under the same frozen parameters. The final report
must include a first-attempt sensitivity and all-attempt timing tails. No
interim primary analysis or gameplay-based exclusion was used.

The replacement also failed exposure (44.1 seconds, eight complete timing
windows). It is retained as `perc3_invalid_dm2_candidate070_a2`.
[Amendment002](perception-lava-cohort-amendment-002.json) records CPU99-100%
and processor queue10-31 while no Quake process was running. Execution waited
for three host-readiness samples below50% CPU and queue<=4 before resuming the
same missing cell. No process or system setting was changed. This supports a
current host-load explanation without proving the cause of the first failure.
Both rejected attempts receive separate substitution sensitivities; all their
timing tails remain in the final audit. The primary bounds and sample stay fixed.

All 256 pairs completed: **512 valid matches plus two retained timing-invalid
attempts**. There was no pooling with the exploratory cohort, interim primary
analysis, changed acceptance bound or outcome-driven extension. Native valid
exposure was 59.0-60.2 seconds, all listen class and BSP-contents classification.
The study ran from 12:20 to 21:19 Sydney time on 25 October, including the
recorded interruption. All frozen inputs matched.

The registered decision supports **practical non-inferiority: the earlier
lava-death increase is consistent with sampling noise**.

| Lava outcome | Control | Candidate |
|---|---:|---:|
| Matches | 256 | 256 |
| Total lava deaths | 48 | 50 |
| Matches with a lava death | 35 | 42 |
| Mean deaths per match-minute | 0.1879 | 0.1956 |
| Maximum deaths in one match | 3 | 3 |

The paired mean difference is +0.00769 deaths/minute. Its 95% interval is
[-0.07543, +0.09080]; the four-pair bootstrap 95% interval is
[-0.07063, +0.08979]. Neither confirms an increase. The registered one-sided
95% upper limits are +0.07736 (paired) and +0.07433 (block), both strictly
below +0.10. This positive non-inferiority result, rather than non-significance
alone, supports the noise interpretation. It does not prove exactly zero
effect or parity on other maps, skills, session lengths or timing tails.

Independent SciPy interval calculations agree. The non-inferiority p-value is
0.01482. The supplementary exact conditional Poisson rate ratio is 1.0418,
95% interval [0.6869, 1.5816], p=0.8408; its independent-event assumption does
not replace the registered pair/block rule. The protocol links the
[paired method](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html)
and [conditional count method](https://www.statsmodels.org/stable/generated/statsmodels.stats.rates.test_poisson_2indep.html).

Both rejected attempts contained zero native lava events. Substituting either
for the valid replacement produces a difference of +0.00379, paired 95%
interval [-0.07898, +0.08655], with paired/block upper limits +0.07317/+0.07396.
Both still pass the same +0.10 rule. The replacement does not drive the
conclusion. All rejected attempts remain outside the primary 512 matches.

Order-stratum point estimates are opposite: -0.0784 for control-first and
+0.0938 for candidate-first pairs. The registered decision concerns their
counterbalanced average, not a guarantee within each stratum. The descriptive
phase deltas before the interruption and after readiness are +0.0146 and
+0.0051. Temporal block counts are retained in the audit without selecting
favourable subsets.

Mean cadence difference is -0.0028 ms, rounded 90% interval
[-0.1166, +0.1110] ms. Valid-match >50 ms frames totalled 125 control versus
155 candidate; including both rejected attempts gives 125 versus 259. These
tails are retained, with no numerical tail-equivalence claim. Mean CPU delta
is +0.0366 ms per wall second, descriptive 95% interval [-0.4820, +0.5552].
Secondary gameplay intervals are descriptive and unadjusted. The lower freeze
count is not confirmatory improvement evidence. Native median-band comparison
reports parity, but its release wording grants no deployment authorisation.

The [registered result](../runs/perc3_lava.results.json) and
[complete audit](../runs/perc3_lava.audit.json) contain all native metrics,
raw hashes, amendments, both substitution sensitivities, timing tails,
verification and restoration checks. The 16-test perception suite passes.
No QC, health/inventory or projectile-perception changes were made. All three
binary locations are restored to their original shipped bytes; no engine is
running. Nothing is deployed and both requested perception holds remain active.

## Ordinary rocket muzzle clearance

The ordinary combat trigger now uses the existing tactical muzzle-clearance
gate after final imperfect aim. Its world trace stops at the nearer of 240u
and the muzzle-to-aim-point distance; a wall behind a close target does not
veto the shot. Tactical shots retain their full 240u probe and existing
settle/abort behaviour. Holding the trigger leaves computed movement intact.
Ordinary shotgun/grenade behaviour and the existing exact-line prefire branch
were unchanged at that review. Step 1a remained active in development and step
1b was parked then.

Fourteen controlled checks use independently proven dm4 BSP wall, clear and
overhang rays. A small harness calls the shared production gate followed by
real `W_Attack`, checking ammo, projectile emission, movement requests,
tactical behaviour and cleanup. It does not exercise the full combat AI.
The legacy gate fails the ordinary wall/overhang cases; an uncapped mutant
fails the wall-behind-target case. One 10-second production smoke and three
private fixture runs were used; no cohorts or deployment. Private hooks are
excluded from production. See [results](../runs/muzzle1_clearance.results.json).

The two negative controls reject the legacy gate on ordinary wall/overhang
shots and reject a missing distance cap on the target-backdrop case. Python
coverage was 2 muzzle, 21 perception and 18 tactical tests. The fast workflow
now includes the muzzle module and three local review-output contracts.

`tools/verify_muzzle_clearance.py` is the retained one-shot session driver,
not a reusable clean-checkout CLI. It expects ignored before-source/binary
snapshots under `backups/muzzle-clearance/`, fixed output names and empty
per-variant directories. It has no `--help` or output-prefix flags. Do not
delete its evidence or rerun it as a quick-start command. The private fixture
uses real BSP rays, the shared gate and stock firing. No incoming-projectile
logic was changed.

For repeatable current-source checks, use
`python tools/verify_private_fixtures.py muzzle --output backups/<new-directory> --prefix <new_prefix>`.
`--help` is side-effect free. The maintained runner snapshots current inputs,
requires the matching source-built lab, and compiles with `install=false`.
One private production smoke and the candidate, legacy and uncapped fixtures
run serially against copied assets. Their expected outcomes are declared in
`plan.json`; sources, binaries and tapes have SHA256 receipts. Installed
files are never overwritten, and before/after checks run on failure too.
Existing output directories and concurrent runner ownership are refused.
Historical session drivers and receipts remain intact (#586).

The separate actual-trigger check (#584) runs with
`python tools/verify_private_fixtures.py combat --output backups/<new-directory> --prefix <new_prefix>`.
It finds a real BSP obstruction along an imperfect firing direction while the
target remains visible eight degrees beside it. Disposable actors have fixed
initial aim state, reaction clocks and loadout; the actual `Argus_Combat`
perception, steering, clearance and stock trigger paths then run unchanged.
A passive counter immediately before the clearance call proves that branch
was reached and records its existing movement request. Blocked shots consume
no ammo and emit no rocket while preserving that request and velocity.
Aligning aim clears the shot for the same visible-target geometry. A separate
close-target backdrop case also fires. Disabling the ordinary rocket guard
privately makes only the blocked-shot check fail, with real ammo/projectile
evidence checked independently by the Python oracle.

The embedded-muzzle observation is deliberately separate and does not fire.
On the measured QuakeSpasm harness a ray wholly inside solid returns
`trace_startsolid=1`, `trace_allsolid=1`, `trace_fraction=1`. The current helper
therefore permits it. This records the existing contract; it does not establish
embedded-shot safety or change ordinary/tactical gameplay. The existing
240-unit tactical reach, settle and abort checks remain in the muzzle suite.
Both accepted and rejected private attempts stay local under
`backups/soak-combat-20261027-1/` and `backups/soak-combat-20261027-2/`.
Installed binaries remain unchanged. No gameplay cohorts or deployment.

## Blind comparison of step 1a and shipped matches

Four fixed 35-second recordings on dm2/dm4 at skill 1 supplied two consecutive
12-second windows per view, 96 seconds total. The review used identical
silent 640x480, 10 fps rendering and independently shuffled A/B labels.
Scoring was complete before the separate key was revealed: A was shipped
and B was step 1a on both maps. Human-like decisions / skill scores were:

| Map | Shipped A | Step 1a B | Preference | Confidence |
|---|---|---|---|---|
| dm2 | 4 / 3 | 4 / 3 | Tie | Low |
| dm4 | 1 / 1 | 2 / 1 | Not enough evidence | Low |

Step 1a is retained for fair information use and the earlier engagement/lava
checks. This small subjective review establishes neither a skill improvement
nor a perceptual win. Silent sampled footage cannot establish sound reactions
or aim smoothness. See the [review receipt](../runs/blind_perception_v1.review.json)
and [unblinded decision](../runs/blind_perception_v1.decision.json).

The HTML source is `tools/blind_perception_review.html`; generated anonymous
clips/page live under ignored `reviews/blind-perception-v1/`, and key/audit data under
ignored `backups/blind-perception-v1/`. Keep rendered licensed assets local and
uncommitted. The optional loopback preview is a session process, not an
installed service or deployment; its URL is not a durable published result.
Do not overwrite this review or reuse its already-unblinded ratings as a new
blind trial. The preparation script is also a fixed, one-shot session driver.

## Health/inventory perception step 1b

**Current status: active again in development, 27 October.** The user requested
reactivation. The acquisition, retreat and hunch boundary changes were reapplied
with the later ordinary rocket-clearance guard preserved; fresh native trials pass all
22 health/inventory checks on dm2 and dm4 (44 total), plus their observation
checks. The earlier dm4 warning is still unresolved. This is no claim of
gameplay non-regression, and no deployment or cohort was run.

Reproduce the current-source boundary checks with
`python tools/verify_private_fixtures.py health --output backups/<new-directory> --prefix <new_prefix>`.
This runs one declared ring-0 trial on each of dm2/dm4 with the existing
PERFIX and 22-check HIFIX oracles. Only the private fixture replaces RNG with
controlled inputs; production sources and installed binaries stay unchanged.
The private engine uses protocol 15 and max_edicts 600. The runner retains
input snapshots, source/binary/tape hashes, compilation reports, per-case
outcomes and before/after protection checks, including failure exits.
It needs configured local assets and a matching native lab build, with no
ignored historical snapshot dependency. The earlier `run_health_fixture.py`
remains historical; these checks do not resolve #583's gameplay warning (#595).

The manifest now verifies actual active function bodies. Inverse amendments
recover the original parked/candidate hashes without altering live source;
projectile recognition and own-item valuation remain unchanged.

**Earlier parking decision.** A bounded follow-up ran three 30-second dm4
matches per arm: control, full candidate, targeting only, retreat only and
hunch only. Median stalls were respectively 1, 0, 0, 0 and 1. The full arm
recorded 0, 0 and 7 stalls. This did not reproduce the earlier warning or
identify a component; it does not establish that the warning was noise.
The run stopped at its 15-match cap.

At that point all three step 1b production functions were restored to their
saved step 1a definitions, including their private-health and inventory
lookups. The observation cache, helper and fixtures remained. A restoration patch and source hashes
live in `tools/fixtures/health-inventory-step1b.patch` and its JSON manifest.
The 21 perception tests now check live active bodies as well as the frozen
historical sources. Historical engine
checks below belong to their recorded builds. No large cohort
was added. See [bounded results](../runs/hi2_dm4_isolation.results.json).

The remaining text records the candidate's original implementation and checks.

The manifest reverses allowlisted recovery, opening-door, button/door, offset-entry,
active-health, plan and muzzle
amendments in memory before checking the original parked hashes and
reconstructing the historical candidate. Live-source audits and fresh native
trials check the current information boundary separately. The original patch
and frozen historical hashes have not been rewritten.

The user authorised step 1b on 26 October. Exact opponent health no longer
contributes to target utility or bypasses ordinary retreat hysteresis. The
co-op shared-target fire delay also no longer consults the opponent's exact
HP. Own stack and own quad remain legitimate inputs. Alive/dead validity
checks remain separate from estimates of an opponent's condition; no numeric
health estimate is fabricated when the bot has no evidence.

`Argus_Perceive` scores visible powerups only after visibility succeeds.
`Argus_Hunch` no longer temporarily becomes the foe to call `Argus_ItemValue`.
The new `Argus_HunchValue` uses fixed item priors for unknown needs, plus the
last observed weapon family for compatible-ammo interest. A hidden active-gun
change cannot update that family; genuine visible reacquisition can. Health,
armour, owned weapons, reserve ammo and pack payload do not feed this hunch.
The existing pursuit trigger, cooldown, short detour curve and minimum-score
threshold are preserved. Own-item valuation and existing teammate coordination
remain unchanged. Projectile perception remains on hold.

`HIFIX` extends the private controlled-input `PERFIX` run when scratch4 is 594.
It inherits the real-client activation, production-build refusal, independent
BSP visibility premises, actual sight-loss interval and whole-tape quarantine.
No new normal-play frame hook is introduced. Disposable observers and targets
exercise actual combat, acquisition and hunch functions. Co-op's shared-fire
branch is tested with temporary QC globals that are restored synchronously.
All temporary items and map-item flags are restored before the enclosing
fixture completes.

The final matrix requires 22 health/inventory checks and the existing 20
perception checks per trial, over dm2/dm4, played/10Hz, ring off/on, twice.
It covers hidden and visible private-state mutations, retreat entry and
hysteresis, observed powerups, own-stack sensitivity, co-op hold-fire, target
health swaps, five isolated hunch input groups, cached and refreshed weapon
family, cooldown, identity and RNG draw counts. Exact old Combat/Perceive/Hunch
bodies are restored only in private positive controls and must be rejected.
Production randomness stays builtin 7; inverse-edit audits verify private
changes. The fixed RNG 0.5 fixture is not an exhaustive random-stream test.

An initial 21-check hunch fixture also changed health inside its weapon/ammo
cases. All original tapes are retained. The stricter revision holds unrelated
private inputs fixed and adds an engine-side input-isolation oracle. Its
production `argus.qc` is byte-identical to the earlier candidate; only fixture
code changed. See `backups/perception-step1b/validation-amendment-001.json`.
The final matrix passes all 672 checks, and the corrected old-code controls
fail the intended health, acquisition and inventory cases while passing input
isolation. The declared ordinary check is eight counterbalanced pairs per map,
32 one-minute matches, against saved step1a control. This is a regression
screen, not powered gameplay equivalence or a claim of better skill.

The final production build also passes the existing 68-trial tactical suite
across both maps and both frame rates. It records 15,992 passive guard
comparisons and all 12 nominal damaging returns. The focused Python suites
pass 64 tests: 26 behaviour, 20 perception and 18 tactical. The native compile
reports no new errors or warnings and emits id-format QuakeC bytecode.

All 32 ordinary matches completed with no retries or exclusions. Native
exposure was 59.7-60.1 seconds, all at the played listen-server rate. Values
below are control to candidate, from all eight native briefs per arm:

| Metric | dm2 | dm4 |
|---|---|---|
| Lava deaths, total | 2 to 2 | 12 to 12 |
| Stalls, total (median) | 78 to 97 (9.5 to 12.5) | 13 to 70 (2 to 5) |
| Frags, total (median) | 26 to 22 (3 to 2.5) | 42 to 27 (5 to 2.5) |
| Engagements, median | 10.5 to 10 | 21 to 21.5 |
| Consumed pickups, total | 22 to 23 | 72 to 66 |

The registered primary, lava deaths, falls inside the native control band on
both maps. This does not make the screen a clean regression pass: dm4 stalls
and lower frags remain concerns. Six dm4 candidate tapes have more stalls
than their paired controls, one ties and one has fewer. The native exploratory
stall IQM interval is entirely worse; it is secondary and not adjusted for
multiple comparisons. The stall rise is not confined to the worst tape.
Do not declare it noise or a confirmed causal regression from this screen.
The comparison's release wording is a primary-gate label, not deployment
permission. Representative-tape gate-card rows must not replace aggregate
values above. Preserve the fixed cohort; investigate and independently
confirm dm4 stalls before advancing perception work.

Mean sampled frame times stayed near 14.48 ms in all four arms. CPU use
changed from 16.34 to 18.39 ms per wall second on dm2 and 18.49 to 17.58 on
dm4. These are descriptive measurements, not performance-equivalence tests.
The dm4 warning has no corresponding sampled frame-time slowdown, but this
does not identify which behaviour change caused it.

The implementation passes the controlled information boundary, but ordinary
gameplay equivalence and improved skill are not established. Projectile
perception remains on hold. All three original binary locations are restored;
no deployment occurred. Full receipts and hashes are in
[`hi1_health_inventory.results.json`](../runs/hi1_health_inventory.results.json).
