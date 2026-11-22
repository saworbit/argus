# Broader map intelligence

[Architecture](architecture.md) | [Lab workflow](lab-workflow.md) |
[Machine-readable evidence](../runs/map-intelligence.results.json)

## What changed

The runtime router now chooses the shortest distance among routes with the
fewest links. Previously equal-link routes were decided by insertion order,
and the length of that first path supplied item scoring and respawn timing.
On dm6, one three-link route measured 465 units although another three-link
route measured 120. This affected every map without needing a broken graph.

The replacement keeps the existing frame budget of 48 node expansions. A
shorter distance updates the parent and schedules propagation to descendants.
An already queued node keeps its existing queue entry. Searches settle before
installing a route or scoring items.
Equal distances retain the first parent. Existing equipment, skill, jump
apex, keyed-door and shared avoidance gates still apply.

Route ordering uses geometric link lengths and favours fewer movement
steps. Pickup respawn clocks use a separate estimate for confirmed
teleporters. Lift and train legs still use geometric length for pickup timing.

## Timing pickups through teleporters

A successful warp through an always-active portal can confirm a link
already present in the map graph. Argus matches the live entry and exit to
the graph seats and records a cost while the search queue is idle. The
estimate allows for the full 0.7-second exit coast and the distances
between both seats and the portal. Triggered gates and unmatched links
retain their existing timing.

A search uses one coherent set of estimates. If two distinct gates are used
while it is busy, both observations wait until the next idle route frame.
Repeat use of the same pending gate adds no second observation. Fixtures
exercised both cases with the live triggers on dm3 and dm6.
[Portal queue fixtures](../runs/audio-adaptation.results.json)

The shopping flood carries this estimate along its chosen parent chain.
The respawn window uses it to judge how early a bot would arrive. Route
ordering, live pickup utility and failed-life avoidance continue to use
geometric distance.

Two stock-map fixtures exercised the live teleport touch and the
production shopping flood. On dm3 the estimated portal leg fell from
5.0 seconds to 1.1, and on dm6 from 3.0 seconds to 1.2. Both controls
committed too early to the pending rocket launcher. Both candidates passed
it over and still routed to due and live pickups.
Triggered gates and crossings during the search retained the older
estimate for the active flood in both fixtures.

The walk-plus-teleport cases carried the timing estimate across a
two-link route and kept the first walk hop when the pickup was due.
All 30 timing checks and 29 existing route-distance checks passed.

The short played-rate dm6 screen averaged 27 engagements per control
match and 20 per candidate match. In four fresh 120-second matches per
arm, the averages were 35.0 and 35.25. The played-rate candidates recorded
no freezes or rescue warps on dm4 or dm6.
[Fixtures and match results](../runs/teleport-pickup-timing.results.json)

## Pickup timing on lifts and trains

Private QuakeSpasm fixtures ran the stock e1m1 armour lift and dm2 grenade
launcher train at played cadence. Each scheduled the real item to respawn
six seconds after the test started. The fixture applied the current
geometric timing formula to the seeded route and measured when the bot
first boarded, dismounted and came within 48u of the item after dismount.

| Completed approach | Estimate (s) | Entry wait (s) | Ride (s) | Final approach (s) | Total (s) |
|---|---:|---:|---:|---:|---:|
| e1m1 lift at bottom | 2.0 | 0.4 | 2.8 | 1.0 | 4.2 |
| dm2 train, second phase in the first series | 2.4 | 4.1 | 3.3 | 0.4 | 7.8 |
| dm2 train near the dock | 2.4 | 0.2 | 3.5 | 7.7 | 11.4 |

Both other lift runs boarded but recorded no approach. Across the six
train runs, boarding took 0.2 to 14.9 seconds and only two runs recorded
an approach. The lift reached its item before the six-second window in
one phase. Both complete train approaches arrived after the window. The
variation after dismount leaves a phase-only correction unverified, so
the live timing formula and route ordering stay as they are.
[Phase measurements](https://github.com/saworbit/argus/issues/1006#issuecomment-7040229808)

## Graph evidence

`python tools/audit_route_distance.py` reads generated QC in actual link
insertion order, checks the eight-link capacity, and compares the work-queue
model with an independent priority-queue shortest-path oracle. It uses a
skill-2, no-rocket profile at ordinary gravity. Closed keyed doors and live
avoidance require engine evidence and are outside this offline model.

Across eight maps, all 326,031 reachable directed pairs match the oracle.
3,522 first-found paths were more than 25 per cent longer than an alternative
with the same number of links.

| Map | Worst first-found / minimum distance | Maximum queue expansions |
|---|---|---|
| dm3 | 1,967 / 847 | 243 |
| dm6 | 465 / 120 | 237 |
| lqdm2 | 1,277 / 441 | 214 |
| e1m1 | 576 / 206 | 233 |
| e1m2 | 1,065 / 572 | 175 |
| e1m5 | 2,907 / 1,937 | 147 |
| e1m6 | 954 / 455 | 176 |
| e1m7 | 1,378 / 761 | 204 |

The largest observed flood needs six slices at the unchanged budget. This
is an observed bound on these graphs, not a worst-case complexity guarantee.

## Engine contracts

The private `route_distance.qc` fixture calls production routing code with
one expansion per call. Its 29 checks cover fewest-link discipline, shorter
equal-link alternatives, queued updates, downstream propagation, positive cycles,
route ownership, frame slicing, unreachable targets, abort/new-root reuse,
rocket and sprint tolls, the jump-apex gate, shopping distances and cleanup.

The candidate passes all 29 checks at measured 14 ms and 100 ms engine-frame
intervals. The fixture measures successive game-time timestamps after map
warmup, before running its bounded search calls.
The frozen old router fails five checks as a negative control, including
shopping distance and route selection; unrelated ownership and equipment
checks pass.
These are engine contracts, not a claim about human play.

## Refused distance-only policy

The first candidate minimised geometric distance even when that added links.
It passed its synthetic routing contracts, but the eight-map screen exposed
movement trouble. On e1m6 one minute produced 36 stalls, 44 abandoned errands
and no consumed goals; the native brief attributed most of those stalls to
a platform column. Other maps also raised stall warnings. Those tapes remain
retained rather than being folded into the revised candidate's arm.

This is why the current rule preserves fewest-link routing before comparing
distance. A geometric graph length is not a complete traversal-cost model.

## Match results

All entries below are means of two skill-2, three-bot matches per arm. The
control is a frozen snapshot of the development source before this change,
not an older release. Every tape ran in the measured `listen` cadence class.
The primary statistical measure was stall parity.
The complete study retains 70 ordinary gameplay matches across controls,
two routing candidates and a small goal-calibration diagnostic. Smoke matches
and controlled contracts are separate from that count.

### Eight-map screen, 60 seconds per match

| Map | Stalls, control / revised | Consumed goals, control / revised | Engagements, control / revised |
|---|---|---|---|
| dm3 | 3.5 / 2 | 2.5 / 1.5 | 3.5 / 2 |
| dm6 | 7 / 5.5 | 5.5 / 7 | 17 / 18 |
| lqdm2 | 2 / 6.5 | 5 / 3.5 | 11 / 15.5 |
| e1m1 | 7.5 / 10.5 | 3 / 2.5 | 5.5 / 6 |
| e1m2 | 9.5 / 8 | 2 / 3 | 2.5 / 1 |
| e1m5 | 4.5 / 0 | 3.5 / 1 | 1.5 / 2 |
| e1m6 | 10.5 / 9 | 1 / 3 | 11.5 / 11.5 |
| e1m7 | 1 / 5.5 | 7 / 6.5 | 31 / 36 |

Six maps passed the primary screen. lqdm2 and e1m7 raised stall warnings,
which remain part of the evidence rather than being replaced by later tapes.

### Independent full-length matches, 185 seconds each

| Map | Stalls, control / revised | Consumed goals, control / revised | Engagements, control / revised |
|---|---|---|---|
| dm3 | 18.5 / 12.5 | 4 / 2 | 3.5 / 7.5 |
| dm6 | 21.5 / 17.5 | 19 / 12.5 | 46.5 / 41.5 |
| e1m7 | 4 / 4 | 23 / 17.5 | 95 / 99 |
| lqdm2 | 6.5 / 6.5 | 12 / 12 | 48.5 / 59 |

The full-length stall measure is at parity or better on all four maps.
Consumed-goal counts fall on three, so this is not evidence of universally
better item control. `gl` counts touches of the bot's current goal, not every
item it passes over; goal-selection events are a different counter again.
No human play-quality claim follows from these small match arms.

### Release limit of the routing-study build

The subsequent [recovery study](freeze-recovery.md) changes the pin-recovery
behaviour and has its own controls. The freezes below belong to the routing
study's frozen build; they are not a claim about every later development build.

e1m7 still produces freezes under fire on both builds: two such windows in
each full-length arm. The development source is not installed over the
playable mod. The freeze defect remains a release blocker even when stalls
are at parity.

The study also exposed and repaired a lab verdict defect: a band comparison could print a
failed severe-freeze row while its registered statistical primary allowed an
overall release approval. The repaired check inspects every candidate tape
and remains independent of the statistical primary. Regression tests cover
a bad nonrepresentative tape, total frozen time, existing control severity
and ordinary count gates. The corrected e1m7 verdict rejects release even
though its primary stall measure is at parity. A release veto on a defect
also present in the control does not establish that the change caused it.

A separate route-only diagnostic preserved the original goal-score distances
on lqdm2. Its mean stalls were 8 against 6.5 in the control, with more consumed
goals. It is retained as a diagnostic, not adopted or treated as a broader win.

## Broader learnings

- Directed graph reach is not physical execution. e1m6's largest rejected
  stall cluster had 95 per cent directed reach and a native `plat_column`
  cause. Mover availability and boarding reliability need their own evidence.
- e1m1 and e1m6 can select prizes the atlas labels off graph. A goal selection
  is not a pickup, and a successful route to its nearest node is not proof
  that the final approach works.
- Contact changes the workload. A route that creates more fights can also
  expose the existing fight-pin freeze class. Inspect severe stationary
  windows separately from travel stalls and aggregate counts.
- Geometric length is useful for resolving arbitrary route ties, but it is
  not an estimate of lift waits, jump setup or combat exposure. The refused
  distance-only arm is a counterexample to treating those as interchangeable.

## Bot adaptation verification

This earlier candidate evaluated four decision changes. The later
[merged adaptation series](classic-bot-comparisons.md#runtime-navigation-and-duel-decisions)
has separate build identities, controls and stock-match results.

- Preserve focus through a brief sight gap, then compare visible challengers
  with the remembered target. Track two recent sources of damage independently
  so a light hit leaves the stronger cue available.
- Check momentum and landing safety before pursuing a last sighting directly.
  A remembered failed crossing triggers a fight detour only with fresh sight.
- Plan supplies around any loaded fighting weapon. Release a health, ammo or
  armour errand after an incidental pickup fills the need and travel can safely
  be redirected. Skip owned weapons that stay in place under the match rules.
- Reconsider a nearby item after another bot's failed approach when it is
  safely reachable from the current waypoint.

The current lab reanalysed 120 archived played-rate tapes from 11 maps at
skills 0 to 3. Build `a577f46c1529` passed 19 of 20 comparisons. The
skill-3 lqdm2 stall comparison failed. The archived e1m1 follow-up passed
the current stationary freeze gate, which classifies the flagged window as
lift travel. Skill-2 dm4 recorded 9 control and 18 candidate lava deaths
across seven matches per build, below the detection limit.
[lqdm2 stalls](https://github.com/saworbit/argus/issues/1053) |
[e1m1 lift travel](https://github.com/saworbit/argus/issues/1051) |
[dm4 lava deaths](https://github.com/saworbit/argus/issues/1055)

The candidate rebased onto `9ebe2dc` (build `8d8f41ea7313`) passed 180
automated decision checks and four stock pursuit cases. The 22 fresh matches
used control build `cbbd30ece9ce` and returned parity on all three primary gates.

| Map | Skill | Matches per build | Primary | Median, control to candidate |
| --- | ---: | ---: | --- | ---: |
| e1m1 | 2 | 3 | Stalls | 30 to 32 |
| dm4 | 2 | 3 | Lava deaths | 2 to 2 |
| lqdm2 | 3 | 5 | Stalls | 3 to 5 |

The fresh lqdm2 improvement interval was -4.3 to +2.7 stalls. The earlier
rejection applied to this candidate. The calibrated skill-1 dm4 stand-in
estimated +0.92 bot kills per minute in sight, with a 95 per cent interval of
-2.00 to +3.85. That threat direction is inconclusive. These builds remain
historical study arms.

## Repeating the evaluation

Build the current native lab using the operator guide. The bounded runner
copies a source snapshot, compiles with `install=false`, and uses its own game
directory. Named raw tapes stay in `runs/`; source hashes, compile reports,
native briefs, comparisons and progress stay beneath the chosen output.
Existing output directories and tapes are refused.
The shared lookup prefers the staged release build. Use `--lab` to select
another current source-built binary. See the [lab workflow](lab-workflow.md)
for the search order.
An already connected older MCP process needs reconnection before it can
serve the repaired verdict. Require `lab_identity.authoritative: true`.

```text
python tools/run_map_intelligence.py --output backups/map-intelligence/control --prefix map_a
python tools/run_map_intelligence.py --output backups/map-intelligence/candidate --prefix map_b --baseline backups/map-intelligence/control
python tools/report_map_intelligence.py backups/map-intelligence/control backups/map-intelligence/candidate --output runs/map-intelligence.results.json
python tools/verify_route_distance.py --output backups/map-intelligence/contracts --prefix route_contract
```

The default rotation is dm3, dm6, lqdm2, e1m1, e1m2, e1m5, e1m6 and e1m7:
two 60-second matches per map and arm, skill 2, with the second rotation
reversed. `--port` uses the native CLI's separate-port match support;
`--ticrate 0.1` selects a separate slower arm. Comparisons require the same
measured cadence class. The source-built native lab must report matching
build and checkout identities before any verdict is accepted.

The statistical primary is stall parity. Two matches per arm and map are
an initial cross-map screen, not a tight estimate of every metric. Native
briefs supply all gameplay counts. Goal selections are never treated as
pickups, and a successful graph route is never treated as a physical pickup.
