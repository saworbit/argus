# Behaviour diagnostics: step 0 results

Follow-up: [overhead investigation and controlled equivalence](behaviour-equivalence-results.md)
supersedes the unresolved pilot discussion below. The original evidence is
retained as the record of the first step-0 run.

Step 0 is implemented on `codex/behaviour-diagnostics`. The passive observer
passes source and immediate-state noninterference checks. Perception and
gameplay decision logic are unchanged. Ordinary-match equivalence is not
established by this pilot, and no gameplay improvement is claimed.

## What changed

- Opt-in BHVDBG snapshots describe existing perception stamps, intent,
  transitions and local progress. Existing tactical abort reasons are logged.
- BHVFIX wraps the existing independent tactical fixture with ordered IDs,
  deadlines, overlap refusal, state guards and cleanup acknowledgements.
- The source-built CLI adds `behaviour-suite --diagnostics on|off`.
- The tactical checker now scopes hidden-departure memory reads to TACFIX
  samples. Tests prove unrelated diagnostic memories are ignored while real
  hidden-tracking violations still fail.
- CI runs the new passive-source and fixture-contract tests.

See [the operator contract](behaviour-diagnostics.md) and
[machine-readable results](../runs/bhv0_step0.results.json).

## Direct noninterference evidence

All 54 baseline QC/build files match the pre-change snapshot
after removing the explicit diagnostic/fixture hooks. The passive module's
source allowlist permits only diagnostic-field writes and printing, formatting,
length and cvar reads. Mutation tests reject RNG, tracing, vector-global,
movement and gameplay-field writes.

The eight on/off suites cover dm2/dm4 at played cadence and 10 Hz:
120 trials, 26,311
guarded calls, and 1,715 enabled emissions.
Each call compares 77 gameplay fields plus self/other and trace/vector globals.
All state guards and cleanup checks passed. Every suite also passed the
independent tactical movement, full-body cover, angle, damage and interruption
checks. All 24 nominal trials demonstrated a damaging return shot.

Measured played cadence was approximately 64 Hz, with startup trials around
66 Hz; every slow trial measured 10 Hz. On/off measurements show no material
cadence shift at this instrument's resolution. Requested rate was not used
as a substitute for measured rate.

Two private engine mutations were rejected: changing health from the observer
failed the state guard, and omitting done timed out through the runner's
owned-engine cleanup. These mutations never entered the working QC tree.

## Ordinary-match pilot

Three 30-second tapes per mode and map enter these native comparisons.
The separate first dm4 off tape was retained but excluded because its native
tick class was dedicated_fast; a matching listen-class replacement was run.
No BHVFIX trial activated in ordinary play. Diagnostics appeared only in the
enabled arms. The primary metric was stall_parity.

| Map | Diagnostics | Median stalls | Goal pickups gl | Grabs | Engages | Lava deaths |
|---|---|---:|---:|---:|---:|---:|
| dm4 | off | 0 | 5 | 6 | 14 | 1 |
| dm4 | on | 0 | 3 | 10 | 14 | 0 |
| dm2 | off | 4 | 2 | 9 | 6 | 0 |
| dm2 | on | 6 | 0 | 10 | 6 | 0 |

Both native primary comparisons report parity within their control bands,
with statistical continuation rather than an equivalence finding. Goal-pickup
flags remain: dm4 5 to 3 and dm2 2 to 0. These are consumed-goal counters, not
goal selections. The small noisy sample does not establish causation, and
the flags are not discarded because the pre-registered primary passed.

The exact claims supported are source preservation and checked immediate
state preservation. This is not a proof that wall-clock logging overhead
can never affect a long stochastic match. Do not treat the lab's release
parity banner as proof of match-level equivalence.

## Verification and retained state

- 304 Rust tests passed, run serially outside the
  Windows sandbox so temporary Git and engine integration tests could execute.
- 140 Python tests passed; strict Clippy,
  formatting and repository invariants passed.
- Compiler output is vanilla id format with no new warnings.
- Original game and engine binaries are restored; compiler output matches
  shipped bytes. Candidate
  QC, binary, raw tapes, checks, private negative tests and reproducible drivers
  are retained under `backups/behaviour-step0/` and `runs/bhv0_*`.

The initial exploratory snapshot-entity bug and checker-prefix collision
were fixed before acceptance. Failed exploratory tapes are retained and
excluded from the 120-trial result. No perception changes were started.
