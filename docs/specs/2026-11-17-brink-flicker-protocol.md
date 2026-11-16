# Brink flicker ladder: registered protocol

Registered 2026-11-17, after the diagnosis in
`runs/lab-voidcorner-turn-diagnosis.results.json` and before any tape of this
candidate was recorded. No development probe of it was run.

## The change

In `Argus_AI`, routed steering (mode 2) is exempt from the steering-side
hazard check that unrouted seeking applies. For a quarter second after the
physics guard actually deflected the bot (`ar_brink`), and never during a typed
hop or a sprint, a routed wanted heading that the 48u probe vetoes is passed
through `Argus_HazardSteer`, held yaw included. The result is used only when it
is within 110 degrees of the wanted heading and its own probe is clean.
Otherwise the heading is left as it was. The route, its node and arrival are
untouched.

The diagnosis it targets: on lab_voidcorner (28 control tapes) and dm4 (two
control tapes) alike, 77 per cent of mid-turn route deflections began straight
after a previous deflection, route steering having turned back at the node a
frame or two after the guard swung the velocity off the lip.

## Arms

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | the registered tree (shipped QC plus the lab_voidcorner graph) | `90E5DEC08594EEE65A5C0F011129C49B` |
| Candidate | the control plus the mode-2 brink check | `130704CAE4256D04B4949B4AF20FF792` |

Private game directories `engine/argus_vcctld` and `engine/argus_vccand4d`,
both with the motion diagnostic (`scratch1 697`). Motion rows are read with the
lab's own grammar (`ftos` pads fractional values).

## Lab map rung

- `lab_voidcorner`, skill 2, 180 s, wall clock at the played rate, eight fresh
  pairs, control and candidate launched together on separate ports.
- Tapes `labvc5_ctl_r1` to `r8`, `labvc5_cand_r1` to `r8`.
- Primary, predicted down: route-steer deflection episodes per 1000 route-steer
  motion samples, per tape (the flicker the change targets).
- Flagged, not convicting: brink encounters per 1000 route-steer samples
  (`movement.brink_encounters`), predicted level.
- Guards: lava deaths, world deaths, stalls and freezes must not rise past
  their detection limits; goals must not fall past theirs.
- Detection limit 2.8 x pooled sigma x sqrt(2/n).

## Stock map rung

Only if the lab primary moves with no lab guard regressing: dm4, skill 2,
185 s, eight pairs, tapes `dm4fl_ctl_r1` to `r8` and `dm4fl_cand_r1` to `r8`.
Primary the same, predicted down: the diagnosis found the same re-entry share
on dm4, so this change is expected to transfer. Guards as above plus
engagements.

## Decision

- Lab primary moves, no lab guard regresses: supported at the isolation tier.
- dm4 primary moves the same way and no dm4 guard regresses: the claim may
  name dm4, citing both sets of tapes, as a reduction in brink flicker.
- dm4 primary level and no guard regresses: isolation tier, with dm4 recorded
  as non-regression only.
- Any dm4 guard regresses: isolation tier, and this file records it.
- Every tape is kept.

## Result of the lab rung (recorded 2026-11-17, after the eight pairs)

Round 4 left the listen tick class on both arms (`dedicated_fast`) and is
reported and left out of the means, so the readings are seven pairs.

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes per 1000 route-steer samples (primary) | 63.6 | 50.9 | -12.6 | 11.2 | moved |
| Brink encounters per 1000 route-steer samples (flagged, predicted level) | 15.1 | 14.4 | -0.7 | 3.1 | level |
| Lava deaths | 0.0 | 0.6 | +0.6 | 0.8 | no regression |
| Stalls | 1.7 | 1.1 | -0.6 | 1.4 | no regression |
| Goals | 18.0 | 17.1 | -0.9 | 3.9 | no regression |
| Engagements | 135.1 | 133.1 | -2.0 | 13.9 | no regression |

The primary moved as predicted and no guard regressed, so the claim is
supported at the isolation tier and the dm4 rung ran. A warning, recorded
rather than convicting: the candidate's tapes held five lava deaths (one in the
excluded round) against none in the control's. Two followed heavy damage, one
came under combat steering, which the change does not touch, and two left a lip
airborne with no damage while route steering. Results:
`runs/lab-voidcorner-brink-flicker.results.json`.

## Result of the stock rung (recorded 2026-11-17, after the eight dm4 pairs)

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes per 1000 route-steer samples (primary, predicted down) | 55.3 | 55.6 | +0.2 | 12.2 | level |
| Brink encounters per 1000 route-steer samples (flagged) | 14.9 | 15.4 | +0.5 | 3.1 | level |
| Lava deaths | 2.0 | 1.4 | -0.6 | 1.8 | no regression |
| Stalls | 6.1 | 3.4 | -2.8 | 4.1 | no regression |
| Freezes | 0 | 0 | 0 | | no regression |
| Goals | 22.4 | 22.4 | 0.0 | 6.5 | no regression |
| Engagements | 66.9 | 76.2 | +9.4 | 9.1 | rose, flagged |

All sixteen tapes held the listen tick class. The primary is level, so the
change did not cut flicker on dm4 although the diagnosis found the same
re-entry share there; no guard regressed and the lab map's lava warning did not
reproduce (lava fell). Engagements rose past their limit, which is not a
regression and is not explained: raw route episodes fell (597 to 511 a tape)
only because bots spent less time route steering. By the decision rule the
claim stays at the isolation tier, with dm4 recorded as non-regression only,
and the change is reverted. Results: `runs/lab-voidcorner-brink-flicker-dm4.results.json`.

## Why it did not transfer (read 2026-11-17 from the same tapes)

The check did act on dm4. After a routed deflection, the share of episodes whose
wish turned towards the guard's held heading over the next three frames rose
from 12 to 36 per cent on the lab map and from 34 to 45 per cent on dm4.

What differs is what the re-entries are. Probing each re-entry's wish and
velocity headings 48u ahead against the map's BSP with the guard's floor rules
(lava or slime, or no floor within 280u):

| Re-entry kind | Lab control | Lab candidate | dm4 control | dm4 candidate |
|---|---|---|---|---|
| Wish points into lava or a void | 354 (95%) | 224 (88%) | 540 (39%) | 317 (29%) |
| Momentum: safe wish, hazardous velocity | 8 | 14 | 38 | 52 |
| Neither probe sees lava or a void | 9 | 16 | 791 (58%) | 720 (66%) |

Where the wanted heading itself points at lava or a void, the check works the
same on both maps: those re-entries fell 37 per cent on the lab map and 41 per
cent on dm4. On the lab map, every lip of which is lethal, they are 95 per cent
of re-entries; on dm4 they are 39 per cent. Most dm4 re-entries happen where
neither heading sees lava or a void within the guard's floor reach, which
points at its speed-dependent run-off landing test (the scan leaves it out; not
measured). The lab map over-represented the one lip type this check can act
on. Results: `runs/lab-voidcorner-brink-flicker-gate.results.json`.
