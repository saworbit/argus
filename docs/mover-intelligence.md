# Mover execution and wider-map investigation

[Broader routing study](map-intelligence.md) | [Recovery study](freeze-recovery.md) |
[Machine-readable evidence](../runs/mover-intelligence.results.json) |
[Diagnostic fixtures and attempts](../runs/mover-intelligence.diagnostics.json)

This is the historical investigation and rejected prototype. The narrower
[e1m6 dock-exit repair](e1m6-decisions.md) has its own frozen controls,
stronger route-handoff checks and broader-map validation.

## Retained changes

Navigation generation now reserves infrastructure seats inside the physical
edict allowance. Previously the reserve was added beyond that allowance,
and synthetic platform pads bypassed it entirely. A map with 351 live BSP
entities could produce 182 waypoints: 602 edicts including the world, client
slots and the existing 60-entity runtime reserve. The corrected allocator
admits at most 180 waypoints on that map, including infrastructure. A map
with no navigation headroom fails before decimation or registration.

On maps constrained below the normal 200-seat decimation target, the
generator also refines the final coarse radius step. It keeps the densest
legal sample found in eight iterations. It does not assume greedy sampling
is perfectly monotone. Roomier maps retain their existing sampling and
promotion limits. Existing registered graphs were not regenerated.

Reports now check both the frozen compilation list and navigation dispatcher.
An experimental graph on disk can supply spatial coverage to a native brief
even when bots never loaded that graph. Such coverage is now reported as
unavailable for runtime navigation, rather than as a positive score.

The accepted combat recovery and equal-link route-distance improvements
remain byte-identical to their previously validated development source.
The mover prototype below was removed. Installed gameplay binaries were
not changed.

## New map readiness

Both maps were generated through the native lab with registration disabled.
They remain experimental; neither is included in the compilation list or
dispatcher. Normal matches on these two maps therefore test fallback
behaviour, not the experimental navigation.

| Map / generation | Nodes | Budget including runtime reserve | Worst spawn reach, all / ungated | Readiness |
|---|---:|---:|---|---|
| e1m3, original allocator | 182 | 602 / 600 | 92% / 90% | Over budget |
| e1m3, bounded coarse sample | 143 | 563 / 600 | 63% / 18% | 196 playability reasons |
| e1m3, bounded refined sample | 175 | 595 / 600 | 96% / 94% | 26 playability reasons |
| e1m4 | 106 | 496 / 600 | Spawn coverage fails | 117 playability reasons |
| e1m3, knit stitches (#623) | 177 | 597 / 600 | 96% / 94% | 17 playability reasons |
| e1m4, knit stitches (#624) | 186 | 576 / 600 | 94% / 94% | 49 playability reasons |

The refined e1m3 graph has five spare edicts after the existing runtime
reserve. That is a tight budget, not a new runtime peak measurement.
Its super nailgun remains about 209 units from a seat and item pockets
remain disconnected. On e1m4, six of nine spawns are more than 200 units
from navigation; the worst is about 860 units away. Passing a broad
reach percentage does not establish that every live pickup is reachable.
No link mill was used to bypass these failures and no support was promoted.

The knit stitch rows come from navgen's swim, bank and deep-drop stitches,
which leave every registered graph byte-identical; their reason counts
include the missing mill verdict. All nine e1m4 spawns are now within 142
units and 50 of its 58 pickups are within reach of every spawn, and e1m3's
super nailgun is back on the graph through a 216 unit fall from its ledge.
e1m3's super shotgun and rockets stand on a shelf climbed by 24 to 32 unit
risers on 16 unit treads, which SV_CheckBottom refuses as seats, so only a
rocket jump reaches them. e1m4's other eight pickups are behind a two-button
secret door (invisibility, grenade launcher, health), in a walled room
behind a trigger-lowered door (spikes, two health), on a trigger-started
train (armour) and in an air pocket under the lake (rockets). Nine of
e1m4's eleven teleporter links, and both of its train links, name movers
that stock QuakeC runs only after a trigger, and the triggers here are
one-shot, a button or never fired; without those links its gate would
report 125 reasons, not 49. Registered e1m2, e1m5, e1m6 and e1m7 graphs
carry links through targetnamed teleporters too, and whether their triggers
keep them usable has not been checked.

Source hashes retain the original native output bytes. Git normalises the
experimental QC sources to LF; graph JSON and raw tape identities are
preserved unchanged. A source line-ending change is not a new engine trial.

### Stock-map follow-up

The [e1m3 tread fixture](../tools/verify_shelf_treads.py) places one bot on
the first tread and gives it four ordinary jump impulses along the shelf
route. QuakeSpasm controls flight and landing. Each jump after the first
starts at the previous landing, even where the narrow tread fails
`CheckBottom`. The last impulse crosses west onto the shelf. The fixture
proves the physical climb at played and 100 ms cadence. The route still
needs a graph entry and execution by the ordinary controller.

```text
python tools/verify_shelf_treads.py --output backups/shelf-treads --prefix shelf_treads
```

The benchmark suites for [dm6](../benchmarks/dm6_rocket_approach.json),
[e1m1](../benchmarks/e1m1_lower_stair.json) and
[lqdm2](../benchmarks/lqdm2_health_approach.json) keep the observed starts and
nearby easier approaches on the current registered graphs. Run a suite
with `argus-mcp benchmark`. Inspect the raw tape for `unstick` before
calling a dry landing a physical escape. The health and rocket destinations
in these suites are positional tasks. Actual item collection needs a stock
pickup receipt.

On lqdm2, the rounded observation `(-272 208 216)` is inside the player
hull's solid boundary. The fixed start uses `(-272 207.75 216)`, which has
world support on the lower floor. From there the first route seat is 32u
above the bot. Keep that entry long enough to start the climb before
turning straight towards the health. The stock fixture checks real
pickups from the lower floor and a direct approach from the upper floor.
`python tools/verify_health_approach.py --output backups/health-approach --prefix health_approach`
runs the fixture at played cadence.
Three 185-second skill-3 matches per arm reduced stalls in the lower corner
from four to one. Whole-map median stalls went from six to eight, inside the
native band. The dm4 cross-check kept median stalls at seven. Both maps
passed the hard gates.

On dm6, the upper ledge links to the rocket shelf pass through a solid wall.
The replacement takes the south hall around the wall through an elbow at
`(449 -1543 256)` and enters the t2 portal before steering for its exit.
The splice keeps the existing graph outside this route. Full regeneration
also changed other links and timed out from the recorded wall position.
The final build reached the shelf dry from that position in 7.8 seconds.
In three 185-second matches per arm, stalls at the wall fell from nine to
zero. Whole-map median stalls went from twelve to seven. The native gates
returned parity. Those comparisons used matched controls. The default dm6
band still needs a refresh on this graph.
[Baseline follow-up](https://github.com/saworbit/argus/issues/1076)

On e1m3, the current graph still lacks an ungated route from each of the
eight spawns to the super shotgun and rockets on the shelf. A private
native-typed generation stayed within 597 of 600 edicts and raised the
strict gate count from 17 to 223. In a separate private trial, ordinary
routing selected the four-tread climb and reached dry shelf support in
3.0 seconds from the exact stair entrance. With two added approach seats
(599 of 600 edicts), the entrance run took 26.1 seconds against a
25-second budget and both farther starts timed out. Keep both maps
experimental until their spawn, pickup and engine link checks pass.
[E1m3 route trial](https://github.com/saworbit/argus/issues/623#issuecomment-7061860314)

On e1m4, a private split swim from `(521 793 344)` towards
`(305 721 728)` reached dry world support in all three 100 ms trials
after compensating for the engine's larger gravity step during submerged
ascent. Each run took 4.8 seconds. All three slow controls timed out. At
played cadence both arms finished in 5.2 to 5.4 seconds. The exact private
graph still had 45 directed pickup gaps, three distance failures and no
mill verdict. The armour train starts after both buttons (*71 and *72)
fire their two-count relay. The t101 teleporter's only activator is a
scrag removed in deathmatch. Route coverage through those movers still
needs live activation evidence or an alternate path.
[E1m4 swim trial](https://github.com/saworbit/argus/issues/624#issuecomment-7051560958) and
[stock activator audit](https://github.com/saworbit/argus/issues/624#issuecomment-7061860364).

## A real platform fault, an insufficient runtime fix

On e1m6, the high-reach hotspot at platform `*72` is a local execution
problem. A bot can board and rise toward the upper exit, then oscillate at
the gap and abandon its continuing route. A task ending at the nearby exit
already succeeds in the control, so that easy task alone would conceal the
fault. The maintained fixture uses a goal beyond the exit and measures a dry
landing on static upper floor with the original task and route retained.
Historical individual retention/dryness fields have the
[predicate qualification](../runs/mover-predicates-v1.results.json); they do not
alone prove every clause. Independent physical and final handoff checks remain
separate evidence.

The prototype waits for the actual contacted platform to finish moving,
steers toward a safe exit, and permits an ordinary-speed jump only from a
docked platform when the existing arc checker predicts a landing on the
exit's floor. It adds no horizontal impulse or teleport. The
[preserved source patch](mover-exit-prototype.patch) is experimental evidence,
not development behaviour.

| Physical task | Control, played cadence | Prototype, played cadence | Both at 100 ms |
|---|---|---|---|
| e1m6 continuing route | Fails at 18 s; loses route | Lands at 4.1 s; one checked jump | Land at 2.2 s; no jump |
| dm3 platform route | Lands at 1.3 s | Lands at 1.6 s; no jump | Land at 1.1 s; no jump |

All eight formal physical tapes remain dry and alive and record zero rescue
warps. Measured played frames are around 14 ms. The slow-profile control
already succeeds: there is no claim that this fixes a 100 ms failure.

The actual later quad pickup was separately checked using the stock
powerup state. It did **not** occur during the 45-second probe. Leaving a
platform, selecting a prize and touching a prize are different outcomes.
This prototype does not establish improved prize control.

## Normal-match decision

The registered primary is stall parity, skill 2, measured played cadence.
Initial focal matches use three 120-second repeats per arm on e1m6 and dm3.
The e1m6 band is parity. The dm3 band rejects: median stalls rise from 4 to
21, with an improvement interval entirely below zero. That rejected card
remains in the evidence.

No lift or boarding event occurs in any of those six dm3 tapes. That is
counterevidence to a platform-geometry explanation, not permission to waive
the rejection. A fixed-source replication adds three repeats per arm on
both maps, retaining the original set and primary. Separate holdouts use
two 60-second repeats per arm on e1m3, e1m4, dm6, lqdm2, e1m1, e1m2,
e1m5 and e1m7. All arms use private game assets and retain their raw tapes.

The completed six-repeat focal bands and all eight holdout bands return
parity. On dm3 the combined median is 6.5 control versus 14 candidate, inside
the widened control band of 1 to 16; means are 7 versus 15. This does not
erase the initial rejection or demonstrate a general gain: the pooled IQM
improvement interval remains entirely worse, at -14.0 to -2.8 stalls.
The candidate is conservatively rejected and removed from development source. Full band
cards, counts, identities and the additional six-second e1m5 stationary
window are retained in the machine-readable evidence. None of the 56 normal
matches records a freeze under fire. Repeating until a favourable card
appears is not an acceptance rule.

## Reproduction and next constraints

`tools/run_map_intelligence.py` freezes source, compiles once through the
native lab and retains named raw tapes and briefs. Use a new output and
prefix for every attempt. Native band comparisons use the registered
primary; severe freezes remain hard vetoes.

`tools/verify_mover_transfer.py` stages the production AI/physics with the
private task fixture. The `--control` flag retains an incomplete baseline
as a measured outcome. Without it, completion, retained route, dry landing,
survival, safe launch and zero rescue warps are required. Use `--ticrate .1`
for the slow profile. The `mover` and `freeze` fixture families are included
in the serial private compile gate and CI.

The next mover change must explain a match-level failure and preserve the
continuing task, not just demonstrate a convenient short transfer. New map
promotion still needs current spawn/item reach checks and engine-proven
links. The preserved platform fixture provides a reproducible failure for
that work without adding map-specific runtime branches.

## Displaced train waits on dm2

The normal train hop can wait 15 seconds at the boarding seat or on a
stationary car. A bot that has never boarded, is nearly still on dry world
floor and is over 160u from its boarding seat now uses the same replan
path after eight seconds. A moving rider still renews the original clock.

The two logged wait origins sit against a clip-hull boundary, so the
private fixture uses nearby supported seats at `(1375 -714 344)` and
`(1375 -729.7 344)`. It verifies support before handing each case to
production AI. Each seat is exercised in three live shuttle phases,
alongside three trials from the actual boarding seat. The candidate must
release and acquire an alternate route in under ten seconds with full
health. At least one control must board the car and reach the far deck.

The six stock cases released at 15.0 seconds and installed an alternate
route at 15.1 to 16.4 seconds. The six candidate cases released at 8.0
seconds and replanned at 8.2 to 8.8 seconds. The stock recorded one far
deck crossing and the candidate recorded two. Two ordinary 120-second
matches per arm had zero freezes and no train hops, so the fixtures
carry the evidence for the changed branch.

Run `python tools/verify_train_wait.py --output backups/train_wait_candidate --prefix train_wait_candidate`.
Use `--source` with a clean copy of the old `src` and `--control` for the
15-second arm. The fixture retains the raw tape, private program and
source hashes. [Missed boarding evidence](https://github.com/saworbit/argus/issues/1003)

### Near-seat waits

On dm2, the eight-second replan also covers a bot on the same dry deck
when it is outside the 120u boarding range and within 16u of the boarding
height. The 160u rule still applies at other heights and on other maps.

The `--near-seats` fixture uses the two origins from #1054 and samples
both train directions. The waits ended at 8.0 seconds, down from 15.0,
and alternate routes installed at 8.1 and 8.2 seconds. The on-pad control
boarded and stepped onto the far deck at full health in both builds.
Six paired 185-second dm2 matches at skills 1 and 3 passed the
registered freeze gate. Neither arm reproduced the reported local waits
in those matches.
[Train recovery evidence](https://github.com/saworbit/argus/issues/1054)

Run the targeted fixture from the checkout root.

```text
python tools/verify_train_wait.py --output backups/train_wait_near --prefix train_wait_near --near-seats
```

For the near-seat control, use a fresh output and prefix with
`--near-seats --control --source <pre-1054-src>`. The source copy must
already include the far-displacement fix from #1003. Keep the dry
dismount receipt with the timing and route receipts. The separate e1m5
detour passed all three 100 ms cases. Two of three played-rate starts
missed the eight-second budget.
[E1m5 trial and dm2 fix](https://github.com/saworbit/argus/issues/1054#issuecomment-7061860204)

## Tracked follow-ups

The documentation audit searched open and closed issues before filing these
distinct items. The issue bodies identify the uncommitted study inputs and
retain the difference between observations and proven causes.

| Issue | Work / status |
|---|---|
| [#622](https://github.com/saworbit/argus/issues/622) | Completed by [#645](https://github.com/saworbit/argus/pull/645): narrower dock-exit repair with separate frozen validation; later prize touch remains a separate outcome |
| [#623](https://github.com/saworbit/argus/issues/623) | Close e1m3 pickup reach gaps within the legal budget before registration |
| [#624](https://github.com/saworbit/argus/issues/624) | Cover e1m4 deathmatch spawns and pickups before registration |
| [#625](https://github.com/saworbit/argus/issues/625) | Completed by [#717](https://github.com/saworbit/argus/pull/717): separate on-disk graphs from compiled navigation and record provenance |
| [#626](https://github.com/saworbit/argus/issues/626) | Completed: native parsing quarantines recovery/transfer fixtures and invalidates older cached labels |
| [#627](https://github.com/saworbit/argus/issues/627) | Completed: all four engine-free budget/report/receipt suites block fast CI |
| [#628](https://github.com/saworbit/argus/issues/628) | Completed by [#896](https://github.com/saworbit/argus/pull/896): release the lift wait when a raised platform still needs its button |
| [#629](https://github.com/saworbit/argus/issues/629) | Completed: per-tape native cards retain the registered primary and refuse incompatible protocols |

The human-play check and the step 1b deployment warning were tracked
separately. The gait review is complete, and the step 1b warning did not
recur in the deployment checks.
[Human-play check #610](https://github.com/saworbit/argus/issues/610) and
[step 1b warning #583](https://github.com/saworbit/argus/issues/583).
