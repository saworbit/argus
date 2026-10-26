# Behaviour diagnostics and controlled fixtures

Step 0 alone adds observation and test controls. Perception, aiming, movement,
goal selection and tactical eligibility keep their existing logic.

## Current development status

Step 1a visual observation caching and the separate ordinary rocket-clearance
fix are retained in development. Health/inventory step 1b is parked, including
its exact-health/inventory leak fixes; incoming-projectile perception stays
on hold. Shipped binaries are unchanged. Earlier sections' test totals and
cohort conclusions belong to their recorded builds, not every later change.

Current muzzle verification comprises 14 native controlled checks and two
negative controls, plus 41 focused Python tests. It is not a demonstration
of improved gameplay. No new cohorts or deployment are authorised. See the
[focused verification runbook](lab-workflow.md#focused-checks-without-deployment).

Follow-ups: [parked step 1b warning](https://github.com/saworbit/argus/issues/583),
[full combat-trigger coverage](https://github.com/saworbit/argus/issues/584),
[muzzle tests in fast CI](https://github.com/saworbit/argus/issues/585),
[repeatable native verification](https://github.com/saworbit/argus/issues/586)
and [local review-media hygiene](https://github.com/saworbit/argus/issues/587).
These tickets do not authorise further engine runs or deployment.

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
observer call. It compares 77 gameplay fields and the trace/vector/self/other
globals exactly before and after that call. Saved values are local variables,
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
are unchanged. Step 1a remains active in development; step 1b remains parked.

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
uses real BSP rays, the shared gate and stock firing; full `Argus_Combat`
integration remains a follow-up. No incoming-projectile logic was changed.

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

**Current status: parked.** A bounded follow-up ran three 30-second dm4
matches per arm: control, full candidate, targeting only, retreat only and
hunch only. Median stalls were respectively 1, 0, 0, 0 and 1. The full arm
recorded 0, 0 and 7 stalls. This did not reproduce the earlier warning or
identify a component; it does not establish that the warning was noise.
The run stopped at its 15-match cap.

All three step 1b production functions were restored to their exact saved
step 1a definitions. This also restores their previous private-health and
inventory lookups; the information-boundary fixes below are currently
inactive. The observation cache from step 1a remains. The unused helper and
dormant fixtures are retained. A portable restoration patch and source hashes
live in `tools/fixtures/health-inventory-step1b.patch` and its JSON manifest.
The 21 perception tests check active step 1a behaviour, the declared parked
state, and the reconstructed candidate's static boundary. Historical engine
checks below apply to the candidate, not the parked source. No large cohort
was added. See [bounded results](../runs/hi2_dm4_isolation.results.json).

The remaining text records the now-parked candidate and its original checks.

The muzzle amendment is allowlisted in the parked-state manifest through
`tools/fixtures/rocket-muzzle-clearance-reverse.patch`. Static tests reverse
that exact amendment in memory before checking the original parked function
hashes and reconstructing the historical candidate. This neither reactivates
step 1b nor establishes its information boundary in current ordinary play.

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
