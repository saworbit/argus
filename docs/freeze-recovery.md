# Recovery under fire

[Architecture](architecture.md) | [Lab workflow](lab-workflow.md) |
[Evidence and input identities](../runs/freeze-recovery.results.json)

## Failure and response

Combat owns travel steering, while the ordinary stall counter deliberately
does not count fighting as a navigation stall. A bot can keep pressing a
blocked direction without earning ordinary stall recovery. The old
uncorroborated fight-pin rescue waits eight seconds.

The broader maps exposed two cases. A refused walk can leave a stationary
body on a floor without `FL_ONGROUND`. Other pins follow a jump or corner
collision and have no immediate support beneath the body's centre. e1m7,
e1m1 and lqdm2 supplied concrete examples. A ground-only fix misses the latter.

Failed walking now records position and time. After 1.4 seconds without
24 units of horizontal progress, the bot tries an escape heading, starting
back along the blocked line. Candidates retain the existing floor/liquid
veto and must clear six knee/chest traces across a 34-unit width. Actual
`walkmove` remains the collision referee. The direction lasts at most
0.8 seconds or 64 units and is rechecked against live bodies each frame.
Aim, the trigger and the current goal remain independent of travel.

An ungrounded body is eligible only when a floor trace proves immediate
support and vertical speed is negligible. The ground flag is restored only
if the engine's `checkbottom` also agrees. Swimming, typed links, mover waits,
tasks, authored tactics and chosen pauses retain movement ownership.

Hostile damage also becomes an urgency cue for the existing last-resort
rescue. It does not acquire or visually observe the attacker. Damage attributed
to the `world` entity, self, or a cooperative ally does not set the cue. Damage
attributed to another entity is an external danger cue. The rescue requires:

- More than three seconds in the existing stationary position window.
- Actual velocity below 20 units per second.
- At least 1.4 seconds to react after the first pinned hit, with hostile
  damage still recent within three seconds.
- No lift or train ride in progress.

Destination rules remain: a node at least 64 units away, the existing
point-footprint clearance check, a 64-unit player occupancy exclusion, and
the existing arrival handling. The soft destination fallback for an origin
embedded in solid is not opened to this new case. Unconfirmed fight pins
retain the old eight-second rule. Respawn clears recovery and damage history.
All durations use game time.

## Physical regressions

`tools/verify_freeze_recovery.py` stages private source and assets through the
native lab and measures engine timestamps after warmup. It exercises
production combat, physics, pain and unstick code while requesting the same
blocked travel heading. Other bots are inactive, leaving one fixed opponent.

The e1m7 quad pocket and a dm6 low obstruction test walking. Another e1m7
corner and the observed e1m1 seat test the fallback. Damage enters the normal
pain path without a knockback impulse that could free a control. A candidate
is measured until its first 64-unit exit; unchanged code must reproduce the
pin for seven seconds. Forcing the original bad heading after an exit would
test unrelated subsequent travel, so that is outside the measurement.

Receipts retain exit time, displacement, shots, visible-target time and rescue
count. Walking requires continuous movement and zero rescues. A fallback
permits at most one explicitly measured rescue; unexplained jumps still
fail. Clear firing opportunities must still produce shots. Guards cover
live blockers, mover waits, typed jumps, swimming, tasks, chosen pauses,
airborne motion and respawn cleanup. Both played and 100 ms cadences are tested.

The eight final candidate replays pass 128 checks; their eight unchanged-code
controls pass 48 checks while remaining pinned for seven seconds. e1m7's
ordinary pocket and dm6 walk out in 1.6–1.7 seconds without rescue. The
additional e1m7 corner uses one rescue at about 3.1 seconds at both rates.
e1m1 uses one rescue at about 3.0 seconds at the played cadence and walks
out in 1.6 seconds at 100 ms. The opponent is visible during these measured
exits and shooting continues.

Placing a bot at the single sampled lqdm2 coordinate did not reproduce its
historical internal state: it left almost immediately and later crossed a
teleporter. That failed replay is retained, not counted as a positive
control. Ordinary lqdm2 matches remain part of the broader validation.

## Match method and limits

The registered primary is `freezes`. The native severity gate rejects every
candidate tape with a freeze under fire, regardless of medians or the
primary. Pickups, engagements, stalls, lava deaths and coverage stay visible.

There are two 120-second matches per arm on dm3, dm6, lqdm2, e1m1, e1m2,
e1m5, e1m6 and e1m7, reversing order for the second repetition. e1m7 and
e1m1 also receive three 180-second matches per arm. Normal matches use
skill 2 and the played cadence. Each arm freezes source and private binaries;
maps and generated graphs are unchanged.

The final comparison contains 22 candidate and 22 control matches, a nominal
50 minutes per arm. All ten native band comparisons return parity under the
registered freeze primary. Descriptive totals for that matched map mix are:

| Measure | Unchanged control | Final candidate |
|---|---:|---:|
| Freezes under fire | 1 | 0 |
| All freezes | 4 | 2 |
| Existing unstick rescues | 9 | 6 |
| Navigation stalls | 329 | 297 |
| Engagements | 723 | 712 |
| Current-goal pickups | 206 | 190 |
| Lava/slime deaths | 34 | 28 |

These totals are not a pooled statistical improvement claim. The two
remaining candidate freezes last 6.7 and 7.1 seconds and remain in the
evidence. Per-map warnings also remain: dm3/e1m2 engagements and dm6/e1m6
pickups are lower in the short screen; dm6 stalls are higher. Long e1m1
stalls and lava deaths also increase. Freezes improving does not waive those
observations or establish readiness to ship other development changes.

The walk-only prototype remains separate. Its e1m1 and lqdm2 freezes under
fire reject it even where the median is zero. Unconditionally restoring the
ground flag also failed the additional corner replay and was dropped.
Neither variant is pooled into the final candidate. Native gate cards and
source/binary/tape hashes remain in the evidence file.

The production build matches the tested private candidate byte for byte and
compiles without new errors or warnings. Raw `freeze_*` and `broad_*` tapes
retain their original bytes through Git, so line-ending normalization cannot
silently break their recorded checksums. The playable installed binary is
unchanged.

These checks establish recovery under the measured conditions, not better
play against people. Mover waits, directed graph sinks and distant item
approaches remain separate problems. A zero-freeze match does not establish
good map control.

The broader runs also identify a concrete next problem: e1m6 still records
42 and 36 stalls in the two final candidate matches. Its leading native
stall clusters carry the `plat_column` cause, including a cluster with
95 per cent directed reach. That evidence points to local mover execution
rather than treating every such failure as an unreachable graph component.

The subsequent [mover investigation](mover-intelligence.md) reproduces a
continuing-route platform failure, preserves an unsuccessful runtime
prototype and expands validation to ten maps. It retains this recovery
source unchanged. Passing a short platform transfer did not establish actual
quad pickup or remove the wider-map warnings.
