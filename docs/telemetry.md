# Recording and reading matches

[README](../README.md) | [Lab workflow](lab-workflow.md)

Use the lab's native briefs and comparisons for match metrics. The console
log records the whole map; a demo adds detailed observations within the
recording client's visible area.

Python review, scorecard, pointfile, humanness and tick tools share the sample,
map, event, death and role readers in `tools/argus_tape.py`. Known complete
names take precedence over words in the event vocabulary. Lab instruments
are excluded from human trails, and tapes without birth evidence do not
invent human tracks. Humanness scoring still requires birth evidence.

## Record and harvest a human session

With the mod installed, start a classic engine using these **engine arguments**:

```text
quakespasm -listen 8 -condebug -game argus +developer 1 +skill 1 +deathmatch 1 +record session dm4
```

Replace the executable as needed. `-condebug` saves console output,
`+developer 1` enables diagnostics, and `record session dm4` starts a demo
on dm4. `qconsole.log` is written in the process working directory; the demo
is written under the active game directory. This command starts a listen
game for human play, not a dedicated comparison arm.

Quit after playing. Before another engine launch, run from the repository
root:

```text
python tools/harvest_session.py --dry-run --tag my_session
python tools/harvest_session.py --tag my_session
```

The harvester looks for the freshest `qconsole.log` in the repository root
or `engine/`, and recent demos in `engine/argus/`. Playing elsewhere does not
change those search paths: preserve your external log/demo and put copies in
those input locations first. Inspect the dry run before moving anything.

The actual harvest moves inputs into `runs/<stem>.log` and
`runs/demos/<stem>.dem`, avoiding existing names, and updates the human
scorecard. Use the stem printed by the tool in subsequent calls.

For automated comparison matches, let `experiment` or `matrix_experiment`
launch the dedicated engine with the lab's rate/configuration controls.

## Read a saved session

**MCP calls**, using the harvested stem:

```text
brief_run log=my_run
see what=demo name=my_run
```

`my_run` is a placeholder for the actual run name, not necessarily the tag
passed to the harvester. For demo export use `see what=demo name=my_run:export`.
The terminal equivalent for a demo is `argus-mcp demo my_run`.

Demos contain positions, projectiles, view angles and kill messages at the
recording rate. They are PVS-culled: an off-screen bot is not a full-rate
track. Use the console tape for full-map event counts and quality gates.

## Log records and their meaning

Optional `BHVDBG` snapshots and isolated `BHVFIX` trials have a separate
[behaviour diagnostics contract](behaviour-diagnostics.md). They do not
change the ordinary ARGLOG/ARGEVT metric grammar. `BHVTIME` reports independent
cadence windows. Activated `BHVFIX begin`, `TACFIX begin`, `BHVRPL begin`,
`FRFIX begin` and `MVFIX begin` mark controlled fixtures: native briefs label them and ordinary quality
comparisons refuse them. Passive snapshots alone do not mark a fixture.

`PERFIX` and `HIFIX` report private observation and health/inventory checks.
`MFIX` reports the private muzzle-clearance fixture: three BSP premises,
ten firing/control scenarios and cleanup, followed by its checked total.
These tapes emit `BHVRPL begin` before ordinary play, so they remain excluded
from bot bands. `MFIX` has no production console switch or public impulse.
Parse it with `tools/check_muzzle_fixture.py` as a Python module; it is not
an ARGLOG metric and the module does not expose a command-line parser.

Private plan, entry, combat and mover fixtures add separate records:

| Record | Evidence |
|---|---|
| `PLANFIX` | Controlled decision contracts and alternative goal selection |
| `PEFIX` | Failed-goal release, alternative selection and continuous physical escape |
| `PMFIX` | Physical co-op rest/retry, route legs, travel, trigger contact and paired real-door movement samples |
| `OFFIX` | Seeded offset-entry trajectory, goal ownership and actual trigger contact |
| `OETRACE` | Private handoff positions and wall-slide diagnostics; not an outcome counter |
| `MCFIX` | Actual combat-trigger clearance, preserved movement, ammo/projectile outcomes and separate embedded-ray observation |
| `BPFIX` | Real bot/player floor-button crossing, support contact, activation and callback-context preservation |
| `DAFIX` | Bounded opener lookup and actual extracted door-controller ownership/timeout checks |

These tapes are quarantined with `BHVRPL begin`. Use the independent oracles
in `tools/check_plan_progress.py`, `tools/verify_offset_entry.py`,
`tools/check_muzzle_combat.py`, `tools/check_button_physical.py` and
`tools/check_door_actuator.py`; do not
pool their rows into match rates or count a selected goal as a pickup.
They add no shipped console control or change to ARGLOG/ARGEVT grammar.

The broader-map studies add these private records:

| Record | Evidence and reader |
|---|---|
| `RDFIX` | Route-distance and shopping contracts; `verify_route_distance.py`; emits `BHVRPL begin route_distance` |
| `FRFIX` | Measured cadence, pin recovery, fire/goal/footing/ownership guards and checked totals; `verify_freeze_recovery.py` |
| `MVFIX` | Measured cadence, boarding, uninterrupted task retention, world-floor landing, changed route node, launches and completion; `verify_mover_transfer.py` |
| `MTRACE` | Read-only transfer samples: elapsed time, position/node, mode, lift/wait flags, support/grounded state, platform phase/top height, velocity, action budget/best distance and current task retention |

Current mover fixtures emit `BHVRPL begin mover_transfer` and require
`landed` and `handoff` fields in the `MVFIX result` receipt. `landed` records
a supported, dry landing near the exit on world geometry; `handoff` records
a non-world route node whose position differs from the exit node. Completion
also requires the original task to remain continuously owned. A changed node
or a landing alone does not establish completion. The field does not independently prove the
node's order in the original route; [#647](https://github.com/saworbit/argus/issues/647)
tracks the stronger oracle. These are checkpoint observations, not proof
of reaching or touching the later goal.

The current receipt checker rejects older result layouts without the two
fields or the activation marker. Retain their original fixture versions and
outcomes rather than rewriting historical tapes. `MTRACE` alone does not
activate a fixture or add a new ARGLOG/ARGEVT metric.

Native parsing treats `FRFIX begin` and `MVFIX begin` as controlled-fixture
activation, including retained historical tapes without a `BHVRPL` marker.
Briefs label them, ordinary comparisons refuse them and default bot-corpus
queries exclude them. Passive check/result records alone do not activate a
fixture. The corpus context schema invalidates older cached classifications;
rebuild the index rather than editing raw tapes or their stored hashes (#626).
Use the verifier receipts for outcomes. Transfer completion is not proof of
the later prize pickup; check the stock item-touch/powerup state separately.
The ordinary recovery diagnostic `ARGUS <bot> unstick underfire <position>`
is counted in existing unstick totals, not as a new pickup or death event.

`ARGEVT <bot> retarget <opponent>` records a change of opponent during an
ongoing fight. It is separate from initial `engage` events. `ATFIX` records
the private [target-decision contracts](combat-attention.md), including
measured cadence, ordered checks and a final failure count. Those tapes emit
`BHVRPL begin target_attention` and stay outside ordinary match bands.

Blind-review ratings are subjective evidence, separate from native match
metrics. Keep build identity in a separate key until scoring is complete.
The `labcamera` recorder is an instrument, excluded from both bot and human
aggregates. Its raw rows remain available for inspection. Actual human tracks
belong under `totals.human` and stay outside bot comparison bands.

```text
ARGLOG <name> t <time> pos '<x y z>' spd <speed> yaw <degrees> mode <mode>
       st <stalls> gl <goals> hp <health> frg <frags>
ARGEVT <name> goal <class>
ARGEVT <name> death <killer> pos '<x y z>' [thirdparty]
ARGEVT <name> tactic <phase-or-abort-reason>
ARGDBG <name> pick <class> u <utility> ...
TACTICCHECK <name> t <time> stage <stage>
ARGUS difficulty <name> t <time> base <skill> cognition <tier> aim <tier>
       offset <offset> drift <drift> adaptive <0-or-1> aimshare_pct <percent>
ARGUS <name> hesitate <heard|junction|settle>
ARGUS <name> actionfail <route-seat-vector>
ARGUS <name> hurdle speed <horizontal-speed> up <vertical-speed>
```

This is a reading guide, not the complete closed event vocabulary. The Rust
parser and its QC-emitter audit define the accepted events; the
[operator guide](../tools/argus_mcp/README.md#tape-review-and-event-counts)
documents event counting and shared Python/Rust contracts.

| Record or field | What it establishes |
|---|---|
| `goal <class>` | A goal was selected, not that the item was taken |
| Sample `gl` | The consumed goal-pickup counter |
| `grab <class>` | A recorded pickup; separate from goal selections |
| Tactical `prepare` | The manoeuvre started, not that it completed |
| Tactical `returnshot` | A shot was acknowledged, not that it hit |
| `TACTICCHECK` | A throttled tactical entry check, not an independent encounter |
| `ARGUS difficulty` | Applied base skill, cognition/aim tiers and adaptive settings, not a performance score |
| `ARGUS <name> hesitate` | A pause the bot chose, and the reason it chose it, not a stall or a wedge |
| `ARGUS <name> actionfail` | A route action failed its approach clock and requested replanning; not a failed shot or an engagement |
| `ARGUS <name> hurdle` | A planned obstacle jump launched; not proof of landing |
| `ARGDBG` | Optional decision scores; enabled by server `scratch1 1`, excluded from ordinary brief counts |

Names may contain spaces and event words. Parsers resolve full known track
names before interpreting verbs; older ambiguous rows without sample/spawn
context retain the legacy interpretation. Do not split names on whitespace.

A chosen pause and a wedge look identical in a 0.5 Hz sample row, and they
want opposite reactions, so `hesitate` carries the cause that produced it.
`tools/argus_gait.py` reads the markers against the shared freeze windows and
attributes each stationary window to a hesitation only when that bot's own
marker precedes it; it exits non-zero when an attributed window lost health or
outlived the hold. Use it rather than a freeze count alone when judging a
change to the gait: dm4 and dm2 both produce long, pre-existing fight-pin
freezes on unchanged code.

Human and instrument tracks stay outside bot bands and freeze totals.
Freezes use speed under 20 u/s within a strict 32-unit XY circle for at least
six seconds, including the first sample. Multi-level tapes use the busiest
segment, with the last segment winning a tie. Lava deaths use BSP hull-0
contents; the `z < -300` rule is only a fallback when the BSP is absent.

## Plot or inspect a run

These **terminal commands** use a locally installed BSP and saved log:

```text
python tools/analyze_match.py maps_local/dm4.bsp runs/my_run.log runs/my_run.png src/argus_nav_dm4.qc.json
python tools/argus_pointfile.py dm4 --what swim
```

The plotter needs its Python plotting dependencies. Pointfile overlays are
viewed from a listen game with the engine's `pointfile` command. For live bot
fields, mover analysis, death regions and paired comparisons, follow the
[operator guide](../tools/argus_mcp/README.md#deeper-inspect).

For the bounded attack-cover-return behaviour, ordinary briefs report its
phases. The separate [fixture checker](attack-cover-return.md#engine-acceptance)
establishes controlled movement and first-return damage acceptance.

With `developer 1`, review entry checks and applied difficulty using:

```text
python tools/tactic_review.py runs/my_run.log
```

The JSON keeps evaluation ticks separate from phase counts and reports
ordinary-session `return_hits` as `null`. `evaluated`, `visible`, `loaded`,
`eligible` and `at_start` are nested milestones; other stages give refusal
reasons. Missing diagnostics in older tapes mean unknown opportunities.
Applied tiers use one-decimal console formatting and aim share is a whole
percent. The retained adaptive aim share is 35 percent; the declined 60-percent
proposal is not evidence of improved play.

For actual images, use [rendered POV capture](../tools/argus_mcp/README.md#rendered-pov-evidence).
Demo replay preserves the recorded viewpoint and visibility, while the source
tape establishes event counts and physics cadence.

Export a clip from the harvested demo with the **terminal command**:

```text
argus-mcp capture-video my_run 0.5 2.4 0.5
```

This samples 2.4 source seconds starting at 0.5 seconds and writes a 4.8-second
half-speed `clip.webm` with `video_manifest.json` under a fresh ignored
`backups/render_capture/` directory. FFmpeg with `libvpx-vp9` on PATH is required
for video; PNG capture needs no encoder. The exporter verifies decoded frame
hashes, order, count and playback timing. It preserves the recorded viewpoint
and cannot recover visibility missing from the original demo.
Capture manifests also identify staged PAK and loose assets by relative path,
size and MD5. Video manifests include the FFmpeg executable digest, build
output and encoding settings. VP9 preflight runs before rendering; input
changes detected during capture fail the call. PNG input requirements and
preflight deadlines are in the
[operator guide](../tools/argus_mcp/README.md#rendered-pov-evidence).
