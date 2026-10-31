# e1m5 encounter investigation

[Architecture](architecture.md) | [Native checks](../tools/argus_mcp/README.md#water-route-decision-checks) |
[Receipts and raw identities](../runs/e1m5-encounters.results.json)

The original zero-engagement tapes do not establish a perception regression.
Fresh unchanged-source controls also record zero starts. The moat is a
rocket-free directed sink: normal spawns can reach most of the map while a
bot that falls into this pocket cannot leave it. Goal selections are not
pickups. No opponent score or engagement band was changed to force contact.
The original tapes do not establish which nearby opponents were visible.

## Execute the plan that search chose

Water supports an underwater walking handoff without a ground flag. Routed
diving now reaches seat depth closely enough to clear submerged ceilings.
A visible item cannot discard required transitions in an installed plan.
When a pair has swim and rocket slots, execution chooses an affordable
action, matching search. Planned swim vaults retain their upward momentum
rather than losing the bank-crossing arc on the next frame.

A jump's launch seat must be reached with support. Low obstacles between
near-level seats need a hurdle action: the face probe includes the player's
half-width and checks apex clearance. Failed route actions track improvement
toward the current seat, rather than rewarding sliding or bobbing. Optional
sound investigation yields to committed route actions; perceived opponents
still use combat normally. There are no map-specific steering rules.

Private witnesses assign initial placement and a task, then leave production
AI and physics in control. The original water-entry control makes zero
handoffs for eighteen seconds on both e1m5 and dm3. Rejected alternatives
include a direct bank edge and a corner inside the player hull. Point
visibility and a nominal arc were insufficient.

The accepted ramp witness completes in 4.0 seconds at played cadence and
3.3 seconds at 100 ms, landing dry without forced relocation. Exact seats
and directed jumps survive through a validated proof sidecar. Generated QC
was not edited by hand. Regeneration reports 583 of 600 edicts including
the runtime reserve, leaving 17 slots. This is a tight allowance, not a new
runtime peak measurement. Graph coverage uses a different node denominator
from the old 155-node graph and is not a direct gameplay improvement score.

## Broader play exposed a second decision failure

An e1m1 lift repeatedly reverses while carrying a bot vertically. Its
horizontal position stays fixed. The decisive read-only trace records real
platform contact, no combat, a best landing distance that stops improving,
and a suspended action clock that follows elapsed time. Support establishes
boarding; it does not establish successful travel toward the exit.

Earlier candidates checked floating waits and stale contact. Those checks
alone did not resolve the ordinary match. The final policy lets supported
static pads wait, but requires a lift ride to keep approaching its landing.
Brief intentional pauses suspend the remaining budget instead of renewing
it. Train patrols retain their longer ownership because an initial leg can
legitimately travel away from the requested pad. Charged jump setup,
doors, combat and authored tactics retain ownership.

In the raised-platform physical case, the previous policy takes 8.8 seconds
to move 64 units out of the pin. The final policy takes 4.2 seconds at played
cadence and 3.9 seconds at 100 ms, retaining the task and full health without
forced relocation.
A cold successful ride still completes in 4.1 seconds at played cadence and 4.2 seconds at 100 ms.
Fifty-six native component checks cover route actions, deadlines, support,
transient contacts, successful approach, task retention and sound priority.
Anticipation covers two nearby route seats: a junction hesitation cannot
run immediately before a lift or jump action and extend its waiting window.
A distant action does not suppress ordinary gait, and an existing pause
releases when a nearby typed transition becomes imminent.

## Retained failures and limits

Earlier raised-platform 100 ms candidates take one point of crush damage
and fail their full-health requirement. The final policy passes it. A quick
escape alone was never accepted as a pass while injury remained.
Cold case 11 is a positive ride check, not a negative pin reproduction.
An earlier observer used an invalid vector expression; its completion claim
was rejected by the independent trajectory check and is not physical proof.

A thirty-second moat-to-rocket-launcher task failed in the west wing in
several earlier candidates; another identical-source repeat reached the
main-map target in 16.7 seconds. That route remains variable. The regenerated
graph also fails an eighteen-second return-to-mega task despite making
handoffs. Escaping the moat is not proof that every item route works.

The final comparison uses sixteen unchanged-source controls and sixteen
fresh candidate matches: two sixty-second skill-2 repeats on dm3, dm6,
lqdm2, e1m1, e1m2, e1m5, e1m6 and e1m7. Earlier candidates and their warnings
are retained separately, including zero-contact e1m5 runs and e1m1 freezes.
Native gates keep their severe-freeze veto. Two repeats do not establish a
general win-rate improvement or good play against people.

## Final matched comparison

Each cell is the mean per sixty-second match, two repeats per arm.

| Map | Engagements, control / final | Consumed goals, control / final | Freezes, control / final |
|---|---:|---:|---:|
| dm3 | 3.5 / 6.5 | 1.5 / 6.5 | 0 / 0 |
| dm6 | 15.5 / 17 | 7 / 5 | 0 / 0 |
| lqdm2 | 20.5 / 15.5 | 5 / 4 | 0 / 0 |
| e1m1 | 4 / 4 | 1.5 / 4.5 | 0 / 0 |
| e1m2 | 6 / 4 | 2 / 3.5 | 0 / 0 |
| e1m5 | 0 / 5 | 2.5 / 9 | 0 / 0.5 |
| e1m6 | 14 / 4 | 2 / 2 | 0 / 0 |
| e1m7 | 30.5 / 35.5 | 5.5 / 8.5 | 0 / 0 |

Both final e1m5 tapes have contact: 8 and 2 engagement starts, compared with
zero in each fresh control. All eight native cards pass the registered
engagement primary and unchanged severe-freeze checks. No final tape has an
under-fire freeze. One final e1m5 wait lasts 7.1 seconds with no health loss;
it remains evidence for #628, not a claim that all stationary behaviour is fixed.

The result is mixed outside the focal map. e1m6 engagement activity falls
from 14 to 4 per match, stalls rise from 11 to 26.5, and forced recovery
warps rise from zero to two. Its continuing-platform-route problem (#622)
remains open. lqdm2 engagement activity also falls. The bands are wide at
two repeats, so passing them does not establish broad improvement.

A rejected intermediate candidate has an 11.2-second lqdm2 pursuit pin at
`(-15.1,-69,216)` without health loss. The read-only repeat does not reproduce
it, and neither final repeat freezes. Its cause remains uncertain; the raw
failure is retained for a focused regression rather than attributed to the
final gait change.

The ordinary cohort uses a single frozen program per arm. Afterwards, the
passive observer guard was extended to snapshot the four new action fields.
That dormant developer-only guard does not change the tested decision
functions; its separate two-map smoke and compile identities are recorded.
The artifact distinguishes runtime program identities from the published
source manifest.

Follow-ups are tracked in [the mega-route repair](https://github.com/saworbit/argus/issues/636),
[the lqdm2 pin reproduction](https://github.com/saworbit/argus/issues/637) and
[preview freshness after skipped plotting](https://github.com/saworbit/argus/issues/638).
The existing [e1m6 route](https://github.com/saworbit/argus/issues/622) and
[e1m5 wait](https://github.com/saworbit/argus/issues/628) investigations remain open.

No gameplay binary is installed by these checks. The health/inventory and
human-play release gates remain separate outstanding work.
