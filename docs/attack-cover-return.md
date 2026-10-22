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

Run the acknowledgement-based driver from the repository root:

```text
argus-mcp tactic-suite dm4 tactic_ack_full_dm4
argus-mcp tactic-suite dm2 tactic_ack_full_dm2 --no-compile
argus-mcp tactic-suite dm4 tactic_ack_slow_dm4 --step 0.1 --no-compile
argus-mcp tactic-suite dm2 tactic_ack_slow_dm2 --step 0.1 --no-compile
```

The default sequence is `0,0,0,1,2,3,4,5,6,7,8,9,10,11,12`. The driver owns
an isolated match at skill 1. It waits for console-ready, matching trial ID
and case, end, and post-restoration cleanup records. Each trial has a
15-second deadline. Case 9 deliberately sends one overlapping start and
requires exactly one refusal. Missing, duplicate, wrong-case and incomplete
acknowledgements stop the match and fail the command. No fixed delay stands
in for an acknowledgement. Each run reports source, installed binary and
navigation hashes; changes during the suite fail it.

Use `--cases 0,0,0,10 --deathmatch 4` for the unlimited-ammo acceptance arm.
The observer counts newly seen bot-owned rocket entities every engine frame,
independently of ammunition and planner events. New tapes use this counter
for opening/return shots; old tapes retain their ammo-delta interpretation.
Damage still has the first-return 0.6-second window and later-shot exclusion.

The requested step is configuration, not measured cadence. Check complete
slow suites with both `--review-suite` and `--hz 10`. Do not mix tick classes
in ordinary A/B comparisons. The older `--suite` subset and `--slow-suite`
seven-case checker remain available for historical tapes.

```text
python tools/check_tactic_fixture.py runs/tactic_ack_full_dm4.log --review-suite
python tools/check_tactic_fixture.py runs/tactic_ack_slow_dm4.log --review-suite --hz 10
```

For a manual trial, use the existing developer/scratch1 197 gate, scratch2
for the case and scratch3 for a distinct integer trial ID before impulse 217.
Confirm the requested `TACFIX trial` and matching `TACFIX done`; an elapsed
client wait is not an acknowledgement. Prefer the driver for suites.

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
| 13 | Shared trigger-box boundary check; reports `TACFIX hull ok` before the encounter |

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
([#517](https://github.com/saworbit/argus/issues/517)). The historical 44-trial checkpoint used ordinary ammo and inferred rockets
from ammo loss. The current observer counts real owned projectiles; see the
acknowledged-suite checkpoint below for independent unlimited-ammo coverage
([#529](https://github.com/saworbit/argus/issues/529)).
Case 12 checks cancellation lifecycle and queue ownership. Dedicated coverage
of the failed-life veto after GOAP substitution is tracked in
[#530](https://github.com/saworbit/argus/issues/530).
Short normal matches establish smoke parity,
not improved win rate. The compare_band_primary_scaled note in review 3.3
requires no change: scaled correctly describes whether any arm changed scale.

## Acknowledged-suite checkpoint, 2026-10-22

The new driver passed every complete interruption suite at both cadences,
plus ordinary-ammo addition cases and eight unlimited-ammo trials. Both
installed binaries have MD5 `98C66862A34D1A2501F4C104CE02D8B3`.
Source, binary, nav and normalized tape identities, requested case order,
measured rates and every result are retained in
[runs/tactic_ack.state.json](../runs/tactic_ack.state.json).

| Suite | Trials | Measured cadence | Damaging stationary returns |
|---|---|---|---|
| full dm4 | 15 | 64.2-65.5 Hz | 3/3 |
| full dm2 | 15 | 64.0-66.2 Hz | 3/3 |
| slow dm4 | 15 | 10.0-10.0 Hz | 3/3 |
| slow dm2 | 15 | 10.0-10.0 Hz | 3/3 |
| unlimited dm4 | 4 | 64.3-66.3 Hz | 3/3 |
| unlimited dm2 | 4 | 64.3-66.5 Hz | 3/3 |

All 68 trials passed the unchanged walking, concealment, angle, cancellation,
first-return damage and self-damage checks that apply to their cases. Both
full suites include all interruption cases at measured 10.0 Hz. Case 9's
extra impulse was refused once per full suite. Cleanup was acknowledged
before the next trial. Unlimited ammo used deathmatch 4 and real owned-rocket
counts; all six stationary returns and both ammo-addition returns damaged
the target. This closes the coverage gaps in #515, #516 and #529. It does
not settle ordinary encounter frequency, human feel or adaptive aim.

The first driver diagnostic caught a stale case/ID write; a second found
joined back-to-back Windows console submissions. Both commands failed and
stopped their owned engines. Console-ready acknowledgement and one initial
setup submission resolved these transport failures. Diagnostic tapes are
retained locally in backups/soak-20261022/fixture-driver-diagnostics.zip.
