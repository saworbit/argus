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

## Tracked follow-ups

The documentation audit searched open and closed issues before filing these
distinct items. The issue bodies identify the uncommitted study inputs and
retain the difference between observations and proven causes.

| Issue | Work / status |
|---|---|
| [#622](https://github.com/saworbit/argus/issues/622) | Completed by [#645](https://github.com/saworbit/argus/pull/645): narrower dock-exit repair with separate frozen validation; later prize touch remains a separate outcome |
| [#623](https://github.com/saworbit/argus/issues/623) | Close e1m3 pickup reach gaps within the legal budget before registration |
| [#624](https://github.com/saworbit/argus/issues/624) | Cover e1m4 deathmatch spawns and pickups before registration |
| [#625](https://github.com/saworbit/argus/issues/625) | Give native graph inventory and coverage explicit compilation provenance |
| [#626](https://github.com/saworbit/argus/issues/626) | Completed: native parsing quarantines recovery/transfer fixtures and invalidates older cached labels |
| [#627](https://github.com/saworbit/argus/issues/627) | Completed: all four engine-free budget/report/receipt suites block fast CI |
| [#628](https://github.com/saworbit/argus/issues/628) | Diagnose the e1m5 six-second window without assuming a chosen pause or a new mover regression |
| [#629](https://github.com/saworbit/argus/issues/629) | Completed: per-tape native cards retain the registered primary and refuse incompatible protocols |

The existing [human-play check #610](https://github.com/saworbit/argus/issues/610)
and [step 1b warning #583](https://github.com/saworbit/argus/issues/583) remain
open; these match sets do not replace or resolve them.
