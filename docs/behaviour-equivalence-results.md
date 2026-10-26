# Step 0: diagnostic overhead and gameplay equivalence

2026-10-24. No perception changes were made.

**The larger pre-registered real-time cohort passes goal-rate equivalence on
both maps using the unchanged +/-2 goals/minute bounds.** Both intervals include
zero, supporting sampling noise as the explanation of the earlier goal deficit.
Enabled diagnostics add measurable CPU work, about 6 CPU ms per wall second,
without a meaningful goal-rate reduction under these test conditions.
Perception changes remain on hold as requested.

## Larger real-time cohort, 2026-10-24

The [frozen protocol](behaviour-goal-cohort-protocol.json) was written and hashed
before the first new launch. It specifies 128 adjacent, counterbalanced on/off
order-pairs on **each** of dm2 and dm4: 512 valid 60-second matches, skill 1.
The previous cohort supplied variance estimates for sample-size planning only;
it was not pooled into this independent confirmation. There were no interim
primary intervals, outcome-based exclusions, sample-size changes or stopping
when a result passed.

| Map | Off goals/min | On goals/min | On - off | Paired 90% interval | +/-2 result |
|---|---:|---:|---:|---|---|
| dm2 | 3.213 | 3.519 | +0.306 | -0.063 to +0.674 | Equivalent |
| dm4 | 7.608 | 7.390 | -0.219 | -0.724 to +0.287 | Equivalent |

Each map separately passes the registered two one-sided equivalence tests at
alpha .05: its paired Student-t interval lies strictly inside [-2,+2]. This is
a positive equivalence result within those bounds, not merely a failure to
detect a difference. It does not prove an exactly zero effect or equivalence of
every gameplay outcome. `gl` is the existing completed-goal counter, not an
independent record of actual item touches.

| Map | Extra CPU ms/wall second, on - off | Descriptive 90% interval | Mean frame difference | Frame 90% interval including rounding |
|---|---:|---|---:|---|
| dm2 | +5.998 | +5.184 to +6.812 | +0.004 ms | -0.127 to +0.135 ms |
| dm4 | +6.142 | +5.309 to +6.976 | +0.008 ms | -0.113 to +0.128 ms |

Mean frame cadence passes the unchanged +/-1 ms bounds on both maps, including
the conservative +/-0.1 ms format-rounding allowance. Recorded mean frames
were about 15.1 ms, roughly 66 Hz, with all native tick classes `listen`; the
study used real time without a fixed-frame or RNG override. CPU cost includes
observation, formatting and output. These ordinary matches do not isolate the
cost of each print call, or establish a batching speedup against the original
fragmented-output mode. Extra CPU work and noisy goal differences can coexist.

There were **513 launches: 512 valid matches and one exposure-invalid attempt**.
At dm4/on repeat 20, 60 requested wall seconds produced 56.9 native game
seconds, failing the registered 58-second validity floor. That tape recorded
22 frames above 50 ms, including clamped 100 ms frames. Execution stopped and
restored the shipped binary. The raw tape and its native brief were retained,
and the [technical amendment](behaviour-goal-cohort-amendment-001.json) recorded
the replacement before resuming the same fixed schedule. No acceptance bound,
source, binary, graph or primary analysis was changed.

The additional first-attempt sensitivity includes that original attempt in
place of its replacement. dm4's goal interval is **-0.743 to +0.264 goals/min**
and its mean-frame interval is **-0.109 to +0.137 ms**, including rounding.
Both pass; dm2 is unchanged. The replacement therefore does not determine the
equivalence conclusion. The disrupted attempt's cause remains unproven.

All complete timing windows, including startup and the rejected attempt, show:

| Map | Off >50 ms frames / recorded frames | On >50 ms frames / recorded frames |
|---|---:|---:|
| dm2 | 33 / 468,848 | 39 / 468,786 |
| dm4 | 27 / 468,276 | 60 / 471,346 |

The enabled point counts are higher. Descriptive paired tail-count intervals
include zero, including the first-attempt sensitivity. These sparse events are
clustered, so treating every frame as an independent trial would overstate
precision. No numerical tail-equivalence margin was registered; none is
invented after seeing the counts. The mean-frame pass does not establish
absence of occasional stutters, and the engine clamp does not reveal their
full wall-clock duration. First timing windows were excluded only from the
primary cadence calculation, as specified beforehand; final partial windows
remain unrecorded.

Every descriptive secondary interval for grabs, acquisitions, engages, stalls,
frags, lava deaths and freezes includes zero. They remain unpowered secondary
comparisons, not separate equivalence proofs. Average speed was 195.30/194.89
off/on on dm2 and 215.56/214.78 on dm4. Native exposure among valid matches
ranged from 59.3 to 60.2 seconds. Conclusions concern these two maps, skill,
match length and measured cadence.

The [larger-cohort evidence](../runs/bhv2_equivalence.results.json) includes the
protocol, source/binary/nav/CLI identities, all 512 successful raw-tape hashes,
the retained failure and amendment, execution history, every reported interval
and independent SciPy checks. Full native receipts, original registered code
snapshots and the initial frozen analysis remain under
`backups/behaviour-equivalence-larger/`. The protocol SHA256 is
`e6962e0023da61acb2f24689aa5db1de8e8ab1b327643a7a3871331ea748a252`.

The cohort ran the saved final candidate
`f00eb2ca930ffa259d56ea717128a1c618c9e48d65c5a4658521ab8ddda3b10c`.
No QC, perception, navigation or gameplay code changed during this follow-up.
After completion, the restoration test was made self-contained by creating its
scratch parent directory on clean checkouts. The frozen test snapshot is
retained; an exact inverse-edit audit and unchanged-result comparison cover
this test-only portability fix. All 26 focused Python tests and all 10 runner
tests in an isolated clean checkout passed. Repository ship/EOL/tape/nav
invariants pass, and all 54 baseline source files still match after removing
the previously documented diagnostic/fixture hooks. All three workspace
shipped binaries are restored to MD5 `A3F7AA9428846DE7F7B327506F5F5D3D`;
no game engine remains running. Perception remains on hold.

## Earlier diagnostic investigation

The earlier controlled functional equivalence tests passed, but their smaller
real-time cohort was inconclusive. The results below retain that investigation
and its limitations; the larger cohort above supersedes its goal-rate decision.

The [machine-readable evidence](../runs/bhv1_equivalence.results.json) retains
the protocol, identities, intervals, replay hashes, state guards, negative
control and raw-tape hashes. Detailed native receipts and source/binary
snapshots are under `backups/behaviour-equivalence/`.

## Earlier real-time matches

Eight adjacent, counterbalanced on/off order-pairs ran on each map, 60 seconds
per match, skill 1: 32 fresh tapes. All used the same candidate, source and
graph; every native tick class was `listen`. No controlled encounter activated
in these matches. Native briefs supply the gameplay metrics.

The primary equivalence criterion was fixed before the cohort: each map's
90% paired Student-t interval must lie strictly inside ±2 completed goals per
match-minute. A non-significant difference does not pass that criterion.

| Map | Off goals/min | On goals/min | On − off | 90% interval | Result |
|---|---:|---:|---:|---|---|
| dm2 | 3.38 | 3.76 | +0.38 | −1.92 to +2.67 | Inconclusive |
| dm4 | 7.50 | 6.37 | −1.13 | −3.54 to +1.28 | Inconclusive |

The dm2 pilot deficit reversed. The dm4 point estimate is smaller than the
pilot deficit, but its interval still permits a meaningful reduction.
Secondary event rates also differ between arms; they are retained in the
JSON and are not reinterpreted as equivalence passes. `gl` is the existing
completed-goal counter. `goal` events are selections and `grab` events are
committed battle-item detours; those events are not proof of item touches.

The common `BHVTIME` probe measured roughly 15.6 ms mean frames after startup.
The on-minus-off intervals remain within approximately ±0.12 ms after widening
for the formatter's rounding uncertainty, comfortably inside the registered
±1 ms bound. No >50 ms frame occurred in the analysed steady-state windows.
Checking all 352 complete windows, including startup, found one 100 ms frame
in a **disabled** control and none above 50 ms in enabled runs. First windows
were excluded from the primary timing calculation as specified beforehand;
final partial windows were not recorded.

CPU measurements are noisier than frame timing. Disabled repeats with identical
gameplay varied substantially. The fixed-work measurements do not establish a
CPU speedup from batching. Batching demonstrably reduces snapshot console
calls from 31 to 12; the report does not convert that count into an invented
runtime improvement.

## Controlled-input equivalence

Private test copies used two fixed random-input streams, seeds 113 and 50917,
on dm2 and dm4, with vanilla `host_framerate` fixed at 0.015625. Production
random-number generation was untouched; the test input provider was never
included in the production manifest.
An inverse-edit audit verified every QC/build/nav JSON source after removing
only the explicit private harness edits.

Each case ran six ways: disabled, repeated disabled, compute-only, original
fragmented snapshot output, batched output, and the saved original source.
All **24 runs** completed 3,842 frames. Every case had byte-identical exported
gameplay records and entity dumps across its six arms, excluding only
`ar_bd_*` diagnostic metadata. Final RNG state/call count, goal counters,
inventory, item state and other exported entity fields were included.

| Map | Seed | Goals in every arm | Controlled RNG draws |
|---|---:|---:|---:|
| dm2 | 113 | 4 | 6,385 |
| dm2 | 50917 | 4 | 6,880 |
| dm4 | 113 | 10 | 7,922 |
| dm4 | 50917 | 7 | 7,264 |

This is direct functional noninterference evidence under equal inputs.
Exported floats are rounded, so it is not a comparison of every internal
floating-point bit. The separate scheduled-call guards compare their listed
77 gameplay fields and trace/vector/self/other globals exactly.

Across the new guard matrix and corrected lifecycle fixtures, **64 trials,
14,133 guarded calls and 904 enabled emissions** passed state and cleanup
checks. All 24 ordinary nominal fixture trials demonstrated damaging return
shots. A private engine mutation that incremented `ar_goals` was rejected by
both source purity checking and the independent replay oracle; the poisoned
tape reported 893 goals. The mutation never entered production source.

## Issues fixed

- [Passive output](../src/argus_behaviour.qc): batch snapshot strings using
  vanilla builtin 25, with at most one temporary-string conversion per call;
  report `dt_ms` instead of rounding played-rate frame time to zero. Compute-only
  and original-output controls make output cost separable from state work.
- [Cadence and guards](../src/argus_behaviour_fixture.qc),
  [checker](../tools/check_behaviour_fixture.py): add a common cadence probe,
  enforce diagnostic-state ownership, and allow rounded timestamp ties only
  with strictly increasing exact frame-check serials and one guard per sample.
- [Lifecycle fixture](../src/argus_tactic_fixture.qc): its synthetic world death
  created a shared avoidance mark after initial cleanup, blocking its own
  nominal route. It also dropped a backpack that could refill the loadout.
  The untouched shipped binary reproduced the route failure. Clear those
  test-created effects before reseating. All eight fresh corrected lifecycle
  tests passed across maps, rates and diagnostic modes. Earlier failures remain
  in the evidence; they were not silently waived.
- [Analysis context](../tools/argus_mcp/src/intel.rs) and
  [corpus](../tools/argus_mcp/src/corpus.rs): activated TACFIX/BHVFIX/replay
  tapes are `fixture`, excluded from default bot queries and ordinary quality
  comparisons, including scaled comparisons. Old cache labels are invalidated.
  Numeric ARGLOG/ARGEVT definitions remain unchanged.
- [QC lookup](../tools/argus_mcp/src/qc_index.rs): index the diagnostic and
  tactical modules and use the same file list for search, making the new
  functions available through `see what=fn`.

The final fixture correction changes only `Argus_TacticFixture` bytecode.
The other **2,316 function bodies**, initialized globals, field layout, strings
and function signatures match the candidate used in the real-time and replay
tests. Source comparison likewise preserves all baseline gameplay code after
removing the explicit diagnostic hooks and fixture-only cleanup.

## Verification and retained state

The complete Rust suite passed 309 tests. After the final scaled-comparison
guard correction, all 45 affected analysis tests passed again. All 153 Python
tests and strict Clippy passed. Formatting and repository invariant results
are recorded with the final evidence.

All three workspace shipped/compiler binaries are restored to MD5
`A3F7AA9428846DE7F7B327506F5F5D3D`. The final candidate is retained separately;
no external game install or installed MCP configuration was changed. The
source-built lab CLI was used because the connected installed MCP is stale.

At that earlier checkpoint, the conclusion was **no observed diagnostic state
corruption and no material cadence regression**, with strong controlled-input
equivalence and an unresolved real-time goal-rate criterion. The larger
registered cohort above now passes that criterion. Perception remains on hold
as requested; a parity banner is not the evidence for this conclusion.
