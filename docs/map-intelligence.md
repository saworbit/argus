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

Distances retain the existing geometric link-length model and preference for
fewer movement steps. They do not
estimate lift waiting time, teleport transit time or combat risk. Improving
that cost model is a separate question from computing it correctly.

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

## Repeating the evaluation

Build the current native lab using the operator guide. The bounded runner
copies a source snapshot, compiles with `install=false`, and uses its own game
directory. Named raw tapes stay in `runs/`; source hashes, compile reports,
native briefs, comparisons and progress stay beneath the chosen output.
Existing output directories and tapes are refused.
The default lab path is `tools/argus_mcp/target-stage/release/argus-mcp`
(`.exe` on Windows); `--lab` accepts another current source-built binary.
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
