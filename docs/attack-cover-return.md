# Attack, cover, return - reviewed implementation

Romero can fire an opening rocket, walk through full-body cover and return
from a different angle on two verified routes. This repair branch restores
the feature preserved at c4c6716, which was closed as PR #528 after its dm4
damage acceptance failed. Historical passing tapes do not certify this build.

The feature is limited to deathmatch at base skill 1, roster slot 1, rockets,
at least two rounds, sufficient effective health and a dry walking approach.
Normal reaction, weapon selection and imperfect aim govern every shot.
The 0.35 adaptive aim share is retained. The separate 0.60 experiment, human
tapes and scorecards remain preserved under issue #527 and the verified
backups/pr-cleanup-20261022/ archive; they are outside this repair.

| Route | Opening | Via | Full-body cover | Return | Observed opponent |
|---|---|---|---|---|---|
| dm4 A | (465,-279,-104) | cover | (561,-183,-104) | (465,-151,-104) | (337,-247,-296) |
| dm2 C | (2209,-279,24) | (2241,-87,24) | (2177,-23,24) | (2145,-119,24) | (2433,-183,24) |

Candidates resolve existing plain graph links. No generated navigation is
modified. Runtime checks include floor and body clearance, avoidance,
teleport exclusion, all eight hull corners plus centre for concealment,
rocket lanes and at least 30 degrees around the observed opponent at first
reappearance. Hidden travel uses remembered coordinates only.

## Review changes

- Item-route state survives tactical ownership, but routed dives, jumps,
  climbs, drops, rocket jumps and incidental gap jumps cannot execute then.
- Completion and abort keep a 0.5-second braking handoff, holding item-route
  launches until ordinary movement takes over. Dodge and retreat can release
  the handoff immediately. Respawn and explicit navigation tasks clear it.
- Entry validates the incoming horizontal braking envelope, using the
  existing friction constants and an extra frame of travel. An unsafe
  moving approach is refused before a tactical state or cooldown is set.
- The return radius is 16 units. Actual angle and rocket-lane checks still
  gate the current seat; a blocked lane keeps walking under the 0.6-second
  progress watchdog. It does not park at the first failed lane probe.
- Begin runs after ordinary weapon selection. Active tactics skip ordinary
  circle, item-grab and threat-movement choices and their telemetry. An
  incompatible pre-existing item detour is released without a failure shelf.
- Hidden turns clear spring aim velocity. Exit sight loss aborts immediately.
  An obstructed actual muzzle direction allows 0.4 seconds for normal aim to
  settle; the exposed exit state is capped at 0.6 seconds before yielding.
- Successful W_Attack acknowledgement drives tactical shot transitions,
  independently of net ammunition changes or unlimited-ammo rules. Travel
  clears the fire button on the opening transition frame.
- Navigation cancellation releases the owner's shared flood and shopping
  latch together. Death, respawn, skill boundary changes, life veto, task
  reset, roster removal and fixture reset all use it. Cancelling another
  bot leaves the live owner's queue intact.
- The failed-life veto is applied after GOAP weapon substitution. A vetoed
  route also clears every typed-hop latch before re-planning.
- Overlapping fixtures are refused. Cleanup resets tactical state and bot
  references before removing target edicts, and restores saved solidity,
  camera flags and weapon touches. Setup clears avoid marks and item detours.
  Shop checks release a frozen packmate's pending flood and re-arm its errand.
  The fixed target clears knockback in its pain callback; otherwise normal
  aim would lead phantom velocity on a target whose position cannot move.

## Engine acceptance

Harvest a human session before any new launch. Compile and start an isolated
deathmatch on dm4 or dm2 through the lab MCP, with skill 1 and enough time
for the suite.

Use an isolated lab match. Arming this fixture lets a connected client
rewrite live bot/loadout/pickup state and freeze the other bots for six
seconds. Keep `scratch1 197` disarmed on shared servers.

Arm the fixture and select a case using separate calls:

```text
tune command="developer 1"
tune command="scratch1 197"
tune command="scratch2 0"
```

Then run `argus-mcp client impulse 217 8` from the repository root. The
developer/scratch1 gate gives the fixture precedence over impulse 217's
normal navigation-task dispatch. Each trial lasts six seconds and samples
position, visibility, ammunition, health, tactical state and frame count.
Poll `see what=status` using its `next_line` cursor. Confirm the requested
case in `TACFIX begin`, then its `TACFIX end` before changing scratch2.
Bound the wait (the reviewed driver used 15 seconds); a missing or wrong
acknowledgement fails the trial. The client's eight-second wait alone is
not an acknowledgement. A reusable suite driver remains tracked in
[#516](https://github.com/saworbit/argus/issues/516).

Run both maps with these case sequences:

| Checker flag | Cases | Rate and extra requirements |
|---|---|---|
| `--suite` | `0,0,0,1,2,3,4,5,6,7` | Original subset; does not cover the review regressions |
| `--review-suite` | `0,0,0,1,2,3,4,5,6,7,8,9,10,11,12` | Default played-rate launch; require shop lifecycle checks |
| `--slow-suite` | `0,0,0,6,8,12,9` | Measured 9-11 Hz; require routed setup, shop checks and refused overlap |

For the slow suite, send `match_command command="sys_ticrate 0.1"` before
the first trial. This command uses the match console, since sys_ticrate is
outside tune's whitelist. Alternatively set `ARGUS_TICRATE=0.1` in the lab
process environment before launching that isolated job. Verify the actual
rate from the fixture frame counts; the requested cvar is not evidence.
For the final case 9, use `argus-mcp client impulse 217,217 1`, then observe
until the matching end. Require one `TACFIX busy` and one completed case 9,
without a second begin. Stop the slow match before launching a normal one;
remove any job-local environment override. Do not compare tick classes.

| Case | Setup |
|---|---|
| 0 | Stationary damageable target; run three times |
| 1 | Target rushes the exit after concealment |
| 2 | Target leaves behind cover |
| 3 | Initial low health |
| 4 | Low health during cover |
| 5 | Weapon change during cover |
| 6 | Moving entry toward the opening walkway's brink |
| 7 | New visible attacker during cover |
| 8 | Moving at 70 u/s with an exact preserved route node (dm4 pit floor) |
| 9 | Lightning owned with cells; selector must prevent entry |
| 10 | Ammo added after prepare, before the opening shot |
| 11 | Sight breaks at reappearance, before the return shot |
| 12 | Shop cancellation on death, respawn and skill change, plus ownership isolation |

The checker includes at least 0.5 seconds after an active moving-entry abort
or a completed return when checking the floor. A refused entry is reported
as a refusal, without a positive tactical-safety claim. Ordinary dry drops
after refusal are recorded separately. Any prepare event counts as ownership,
including a prepare and abort between observer samples; an unsampled
transition cannot become a refusal. It credits damage only within 0.6 seconds
of the first post-return rocket and before any subsequent rocket. Later ordinary combat
cannot rescue a missed return. The three stationary cases must still yield
at least two damaging returns; this threshold and ordinary aim are unchanged.

    python -B tools/check_tactic_fixture.py runs/tactic_review7_full_dm4.log --review-suite
    python -B tools/check_tactic_fixture.py runs/tactic_review7_slow_dm2.log --slow-suite

Tactical ARGEVT phases and reasons are already supported by main's Rust and
Python readers, including track names containing event words. A returnshot
is a shot acknowledgement, not proof of a hit. Use the independent fixture
checker for acceptance outcomes, and native lab briefs for normal matches.

## Validation record

The final build passed 44 controlled trials: two 15-case suites at the
played cadence and two seven-case suites at 10 Hz. The latter also require
refusal of an overlapping impulse and the moving, routed regression setup.
Completed manoeuvres and active moving-entry cases are checked through the
post-ownership window; refused entries carry a separate ordinary-drop observation.

| Suite | Cases | Measured cadence | Damaging stationary returns |
|---|---|---|---|
| full dm4 | 15 | 64.2-64.5 Hz | 3/3 |
| full dm2 | 15 | 63.3-64.5 Hz | 3/3 |
| slow dm4 | 7 | 10.0-10.0 Hz | 3/3 |
| slow dm2 | 7 | 10.0-10.0 Hz | 3/3 |

All 114 Python tests and 271 Rust tests passed. The final QuakeC emitter
audit also passed after the physics handoff change. Source and both binary
hashes are in runs/tactic_review7.state.json; the matching binary MD5 is
1B17C38CE8053E713112CCF2D1EA4F7C. Per-trial results, tape hashes and recovery-archive identity
are in runs/tactic_review7.results.json.

These manifests describe implementation checkpoint `bf170a9`, before the
subsequent documentation cleanup. Documentation edits do not replace its
source, binary or tape identities.

The final 30-second native matrix returned parity on dm4 and dm2. A prior
dm2 tape recorded 15 stalls; all attempts were retained. Three repeat tapes
returned duration-normalised parity, with median six stalls against a control
median of eight. The current lab CLI's report is
runs/tactic_review6_repeat.compare.txt. The connected experiment surface's
unscaled aggregate is not evidence of improvement. This matches the
stale-server failure already tracked and fixed in source by
[#499](https://github.com/saworbit/argus/issues/499); install the current lab
and restart the connected process before trusting its quality verdicts.
Short matches are smoke checks, and no win-rate improvement is claimed.

Intermediate trials exposed an overly eager lane abort, phantom knockback
velocity on the fixed dummy, shared-queue contention in the shop fixture,
and full-gait acceleration immediately after tactical reset. Those diagnostic
tapes and manifests were archived with SHA-256 verification in
backups/tactic-review-intermediate-20261022.zip. The source/binary recovery
snapshot for the earlier controlled build is
backups/tactic-review-build5-20261022.zip. Final acceptance uses only build 7.

Human playtesting remains necessary to judge encounter frequency and whether
the move reads as deliberate
([#517](https://github.com/saworbit/argus/issues/517)). The production firing
acknowledgement handles unlimited ammo, but the fixture and checker still
infer rockets from ammo loss; the recorded suites use ordinary ammo rules.
Independent unlimited-ammo shot coverage is tracked in
[#529](https://github.com/saworbit/argus/issues/529).
Case 12 checks cancellation lifecycle and queue ownership. Dedicated coverage
of the failed-life veto after GOAP substitution is tracked in
[#530](https://github.com/saworbit/argus/issues/530).
Short normal matches establish smoke parity,
not improved win rate. The compare_band_primary_scaled note in review 3.3
requires no change: scaled correctly describes whether any arm changed scale.
