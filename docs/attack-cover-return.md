# Attack, cover, return — first playable milestone

Romero can commit to an opening rocket, walk behind cover, and return along
a different leg before firing again. This first implementation is limited
to the two verified encounters on dm4 and dm2. It does not yet search every
map for new manoeuvres.

It runs in deathmatch at base skill 1, for roster slot 1, with a rocket
launcher, at least two rockets, adequate effective health and an ordinary
dry walking approach. Existing adaptive difficulty and aim error remain in
control of the shots. The bot must start within 48 units of the route's
opening node; geometry is checked against the opponent's observed position.

| Route | Opening | Via | Full-body cover | Return | Tested opponent |
|---|---|---|---|---|---|
| dm4 A | n79 `(465,-279,-104)` | — | n89 `(561,-183,-104)` | n81 `(465,-151,-104)` | n65 `(337,-247,-296)` |
| dm2 C | n94 `(2209,-279,24)` | n104 `(2241,-87,24)` | n92 `(2177,-23,24)` | n86 `(2145,-119,24)` | n130 `(2433,-183,24)` |

dm2 n104 is a transit point, not cover: the centre can be hidden while a
standing hull corner remains exposed. The implementation checks the centre
and all eight hull corners. It measures the return angle at first
reappearance, rather than crediting a later endpoint. The minimum is 30
degrees around the opponent.

## Behaviour and limits

The candidate must resolve to existing plain graph links and pass current
floor, body clearance, avoidance, teleport-exclusion, cover and rocket-lane
checks. No graph or sidecar was changed. Tactical state lives on the bot
and does not overwrite the item-route BFS.

The ordinary firing code must actually spend a rocket before movement
commits. Travel suppresses firing; the exit hands the shot to normal
reaction, turning and imperfect aim. A 240-unit trace checks the actual
shot direction, allowing for the 160-unit splash radius and movement during
rocket flight at the tested cadence. A closer wall delays the shot without
changing aim. Cover means visual occlusion at the sampled body points, not
immunity to splash damage. Lower frame rates still need verification.

The opening has a 1.2-second deadline, followed by at most 2.8 seconds for
the manoeuvre. Failure and success impose 10- and 14-second cooldowns.
Low health, retreat, missile dodge, visible crossfire, weapon changes,
observed opponent displacement, target loss, invalid walking geometry and
lack of progress cancel the move. Concealed movement uses remembered enemy
coordinates; a hidden departure does not update that memory.

## Reproducing controlled engine trials

Use an isolated lab match: the fixture resets the encounter and temporarily
changes other bots and pickups. Harvest any human session before launching
a new engine, which truncates its console log. Use the lab MCP to compile
and start a skill-1 match on the chosen map.
Arm `developer 1`, `scratch1 197`, and select the case with `scratch2` via
`tune`. Send `argus-mcp client impulse 217 9` to run a six-second trial.
For three stationary trials use `argus-mcp client impulse 217,217,217 9`.
The final run allowed one second after changing console values, but elapsed
wall time alone is not an acknowledgement. Check the incremental match log
for the expected `TACFIX begin <map> case <n>` and its `TACFIX end` before
changing case or firing another impulse. Run cases in the sequence
`0,0,0,1,2,3,4,5,6,7`, then stop and harvest the match. Reject a tape with
missing, overlapping, or unexpected cases. Start a fresh match for the
other map.

| Case | Setup |
|---|---|
| 0 | Stationary, damageable target; ordinary bot chooses the manoeuvre |
| 1 | Target rushes the return exit after concealment |
| 2 | Target leaves to a hidden position after concealment |
| 3 | Bot begins at 20 HP |
| 4 | Bot drops to 20 HP after concealment |
| 5 | Weapon changes after concealment |
| 6 | Bot enters with lateral velocity |
| 7 | A second visible opponent appears after concealment |

The explicit developer fixture resets the encounter, temporarily freezes
other bots and weapon pickups, and places a stationary 5000-HP target. It
does not force the tactical phases. Its independent observer records actual
movement, eight-corner/centre visibility, ammunition, damage, health and
frame cadence. These controlled tapes are not normal-match scorecards.

Check a harvested tape with:

```text
python -B tools/check_tactic_fixture.py runs/tactic_commit2_dm4.log --suite
python -B tools/check_tactic_fixture.py runs/tactic_commit2_dm2.log --suite
```

The checker requires all three complete manoeuvres and real return rockets,
with at least two damaging returns. Ordinary skill-1 aim can miss; hits are
reported separately. Interrupted encounters must cancel without claiming a
successful return shot.

`ARGEVT <name> tactic` records `prepare`, `opening`, `covered`, `reappear`,
`returnshot`, or `abort <reason>`. The integrated Rust and Python parsers
report phases and abort reasons, retaining complete track names (#514,
#520). Compact lab briefs expose `tactics`; full briefs and Python
scorecards expose `tactic_*` counts. Use the dedicated checker for fixture
outcomes, which additionally require movement, concealment, and damage.
A `returnshot` event establishes a shot, not a hit or completed manoeuvre.

The unchanged-bot baseline `runs/tactic_red_dm4b.log` fired but failed the
independent concealment check before the feature was added. Earlier fixture
iterations and rejected trials remain in `runs/tactic_*` for diagnosis.

## Verified build, 2026-10-21

Both final suites passed: 20 trials, comprising six stationary manoeuvres
and fourteen interruption/motion cases. All six manoeuvres walked the
route, reached body concealment, returned at a useful angle and fired a
second rocket without return-shot self-damage. Four return rockets damaged
the target; one rocket on each map missed with ordinary aim error.

| Map | Completed manoeuvres | First reappearance angle | Concealed at | First visible again | Damaging returns |
|---|---|---|---|---|---|
| dm4 | 3/3 | 42.8–42.9° | 0.5 s | 1.2 s | 2/3 |
| dm2 | 3/3 | 49.9° | 1.3 s | 1.7 s | 2/3 |

Times are from fixture start, not from the first shot. Frame cadence was
measured in each six-second trial and is recorded in the results JSON; this
run measured 63.8–69.5 frames per second. It does not establish
low-frame-rate or latency robustness. Steering uses the existing
frametime-scaled physics, including on the frame of the opening shot.

The final 30-second normal matches on both maps received the lab's parity
verdict, with zero lava deaths and freezes. They recorded zero dm4 stalls
and five dm2 stalls, with no corrective next steps from the lab.
Two earlier pairs of normal-match smoke tests also returned parity. These
short tapes are regression checks, not evidence of improved win rate.
The final normal-match tapes contain no raw `tactic prepare` events.

A commit-verification regression tape, `runs/tactic_commit_dm2.log`,
recorded 23 HP of self-splash with the earlier 120-unit muzzle check. Its
build is recorded in `runs/tactic_commit.state.json`. Extending the check to
240 units allows a margin beyond the 160-unit splash radius for normal
forward movement during rocket flight. The final suites above passed
without return-shot self-damage at their measured cadence; this is not yet
verified at lower frame rates.

Evidence:

- `runs/tactic_commit2_dm4.log` and `runs/tactic_commit2_dm2.log`: final controlled encounters.
- `runs/tactic_commit2.results.json`: independent observer results and measured frame rates.
- `runs/tactic_commit2_normal_dm4.log` and `runs/tactic_commit2_normal_dm2.log`: normal matches.
- `runs/tactic_commit2_normal.brief.json`: unmodified native lab analysis.
- `runs/tactic_commit2.state.json`: branch, HEAD and tested source/binary/nav hashes.

Compilation succeeded, 71 Python tests passed (one optional test skipped),
and read-only review findings were addressed. Generated nav QC,
graph JSON and the existing dm2 probe sidecar are byte-identical to their
pre-task state. Commit `21ce7b7` excludes the checkout's prior adaptive-aim
edits. Its binaries match the feature-only source used by the recorded
commit verification runs.

The original feature snapshot failed the Rust emitter audit because its
parsers omitted `tactic`. Current code integrates the parser fixes from
main, along with the navigation benchmark. The fixture's explicit
`scratch1 197` gate takes precedence over the shared impulse 217; ordinary
navigation tasks still select their bot slot and take steering priority.

Human playtesting remains necessary to judge whether the move reads as
deliberate, whether it occurs often enough, and whether it creates the
desired surprise. That judgement should precede broadening the candidate
search, adding maps, or spreading the behaviour to more bots.

## Tracked follow-ups

Integration verification on 2026-10-22 passed 271 Rust and 101 Python tests,
including the emitter audit, and compiled both shipped binaries. The
20-case engine rerun preserved walking, concealment, return angles, and
interruption handling. However, dm4 damaged the target on only one of its
three return shots, so its `--suite` acceptance check failed the required
two-hit minimum. The original build's passing results above do not override
this failure. The integration is preserved for follow-up rather than merged.
Evidence: `runs/tactic_merge3_dm4.log`, `runs/tactic_merge3_dm2.log`, and
`runs/tactic_merge3.state.json`.

- [#527: resolve the integration acceptance failure](https://github.com/saworbit/argus/issues/527) and the separately preserved adaptive-aim tuning.
- [#514: tactical parser integration](https://github.com/saworbit/argus/issues/514), included with the main integration.
- [#515: verify lower frame rates](https://github.com/saworbit/argus/issues/515), including movement and return-shot splash clearance.
- [#516: synchronize fixture trials with engine acknowledgements](https://github.com/saworbit/argus/issues/516), replacing timing-only sequencing.
- [#517: measure natural frequency and player readability](https://github.com/saworbit/argus/issues/517) before expanding candidates.
