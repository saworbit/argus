# Brink turn ladder: registered protocol

Registered 2026-11-16, after the route elbow ladder
([its protocol and result](2026-11-16-route-elbow-protocol.md)) and before any
brink turn tape was recorded. No development probe of this candidate was run.

## The change

In `src/argus.qc`, gated on lethal liquid found by a hazard probe in the last
half second (`ar_brinkliquid`, the gate the cautious gait already uses), no
enemy and a route or goal mode:

- steering half (`Argus_AI`, the route steer): when grounded, the movement
  heading turns at `AR_BRINKTURN` = 3 times `AR_TURNRATE`; facing keeps the
  body rate;
- physics half (`Argus_Physics`): while the velocity lags the wish by more
  than 30 degrees at over 100 u/s, friction runs a second time, the doubling
  stock applies as edge friction.

Offline NQ integration: the overshoot of a 90 degree turn begun at 200 u/s
falls from 97u to 46u.

## Arms

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | as in the route elbow ladder | `90E5DEC08594EEE65A5C0F011129C49B` |
| Candidate | the control plus the brink turn | `34809FD9EE30F7EDDB31F3E21E837F5D` |

Private game directories `engine/argus_vcctld` and `engine/argus_vccand2d`,
both with the motion diagnostic (`scratch1 697`).

## Lab map rung

- `lab_voidcorner`, skill 2, 120 s, wall clock at the played rate, five fresh
  pairs, control and candidate launched together on separate ports.
- Tapes `labvc2_ctl_r1` to `r5`, `labvc2_cand_r1` to `r5`.
- Primary, predicted down: route-steer deflection episodes per tape
  (`brief.movement.deflection_causes.route_steer`).
- Guards: lava deaths, world deaths, stalls and freezes must not rise past
  their detection limits; goals must not fall past theirs.
- Detection limit 2.8 x pooled sigma x sqrt(2/n). Inside it reads "no
  detectable effect".

## Stock map rung

Only if the lab primary moves and no lab guard regresses: dm4, skill 2, 185 s,
five pairs, tapes `dm4bt_ctl_r1` to `r5` and `dm4bt_cand_r1` to `r5`. Primary
route-steer deflection episodes (predicted down or level); guards as above
plus engagements. dm4 is the stock map with the most lethal brinks.

## Decision

As in the route elbow protocol: the lab primary moving with no guard
regressing supports an isolation-tier claim; the stock rung decides whether
the claim may also name dm4 (the promotion rule in `docs/lab-scenarios.md`);
a stock guard regressing keeps it at the isolation tier. Every tape is kept.

## Result of the lab rung (recorded 2026-11-16, after the five pairs)

| Metric | Control | Candidate | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes (primary) | 94, 149, 136, 116, 79 (mean 114.8) | 61, 123, 124, 87, 50 (mean 89.0) | -25.8 | 56.1 | no detectable effect |
| Of those within 128u of a corner | mean 45.8 | mean 47.6 | +1.8 | 29.2 | no detectable effect |
| Lava deaths | 1, 0, 0, 0, 0 | 1, 0, 0, 0, 1 | +0.2 | 0.9 | no detectable effect |
| Stalls | mean 1.4 | mean 2.0 | +0.6 | 1.1 | no detectable effect |
| Goals | mean 10.8 | mean 12.4 | +1.6 | 5.5 | no detectable effect |

All ten tapes held the listen tick class. The primary did not move, so this
ladder does not support the claim and the stock rung was not run. Results:
`runs/lab-voidcorner-brink-turn.results.json`.

Exploratory, not registered: the same control code read 87.4 episodes a tape
in the route elbow ladder and 114.8 here, because the count scales with how
much of a match the bots spend routing rather than fighting. Per 1000
route-steer frames the reading is 66.6 against 45.6 (-21.0, detection limit
28.2), and the control read 49.8 in the earlier ladder. Five two-minute tapes
an arm cannot resolve an effect of that size; the confirmation below is
registered with the normalised rate as its primary and more data.

## Confirmation ladder (registered 2026-11-16, before its tapes)

- Same arms and game directories.
- Lab map rung: `lab_voidcorner`, skill 2, 180 s, eight fresh pairs, tapes
  `labvc3_ctl_r1` to `r8` and `labvc3_cand_r1` to `r8`.
- Primary, predicted down: route-steer deflection episodes per 1000
  route-steer motion samples, per tape.
- Guards as before: lava deaths, world deaths, stalls and freezes must not rise
  past their detection limits; goals must not fall past theirs.
- Stock rung, only if the lab primary moves with no guard regressing: dm4,
  skill 2, 185 s, five pairs, tapes `dm4bt_ctl_r1` to `r5` and
  `dm4bt_cand_r1` to `r5`, the same normalised primary (predicted down or
  level) and the same guards plus engagements.
- Detection limit 2.8 x pooled sigma x sqrt(2/n), as before.

## Result of the confirmation (recorded 2026-11-16, after the eight pairs)

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes per 1000 route-steer samples (primary) | 56.9 | 45.8 | -11.1 | 12.1 | no detectable effect |
| Route-steer deflection episodes a tape | 155.8 | 135.2 | -20.5 | 56.4 | no detectable effect |
| Of those within 128u of a corner | 51.6 | 68.2 | +16.6 | 28.8 | no detectable effect |
| Lava deaths | 0.1 | 0.2 | +0.1 | 0.6 | no detectable effect |
| Stalls | 1.0 | 1.6 | +0.6 | 1.6 | no detectable effect |
| Goals | 15.5 | 15.2 | -0.2 | 5.4 | no detectable effect |
| Engagements | 129.4 | 129.1 | -0.2 | 15.9 | no detectable effect |

All sixteen tapes held the listen tick class. The primary fell 19 per cent and
stayed inside its detection limit, and the corner episodes the change was
built for rose, so the claim is not supported and the stock rung was not run.
The change is reverted, with its post-mortem beside the route steering in
`Argus_AI`, and parked rather than refuted: it pointed the right way on the
normalised rate in both ladders. Results:
`runs/lab-voidcorner-brink-turn-confirmation.results.json`.

## Correction (2026-11-16, after the early turn ladder)

The first analysis read motion rows with a pattern that expected one space after `wish`; QuakeC's `ftos` pads fractional values (`wish  66.8`), so about 8 per cent of samples, every frame with a fractional wish, were dropped. The corrected pattern matches the lab's own parser (`tools/argus_mcp/src/motion.rs`) exactly. The results file now holds the corrected analysis, with the first recording kept as `original_analysis`. The numbers in both result sections above are superseded by these:

| Ladder | Metric | Control | Candidate | Change | Detection limit | Reading |
|---|---|---|---|---|---|---|
| First, 5 x 120 s | route-steer episodes a tape (primary) | 129.2 | 105.6 | -23.6 | 69.1 | no detectable effect |
| Confirmation, 8 x 180 s | route-steer episodes per 1000 route-steer samples (primary) | 59.2 | 45.9 | -13.4 | 12.3 | moved |
| Confirmation | of those within 128u of a corner, a tape | 58.8 | 72.4 | +13.6 | 33.3 | no detectable effect |
| Confirmation | lava deaths, stalls, goals, engagements (guards) | 0.1, 1.0, 15.5, 129.4 | 0.2, 1.6, 15.2, 129.1 | | 0.6, 1.6, 5.4, 15.9 | none regressed |

The confirmation's registered primary moved, by a thin margin, with no guard
regressing, so under this protocol the claim is supported at the isolation
tier and the dm4 stock rung is due. It has not been run. What moved is the
count of deflection episodes, which mostly measures flicker within one brink
encounter; brink encounters themselves (episodes under 250 ms apart merged,
not registered) read 14.4 against 12.7 with a detection limit of 2.7, no
detectable effect. So the brink turn reduced how often route steering and the
guard alternate at a brink, not how often bots reach one. The change stays
reverted until the stock rung has run.

## Result of the stock rung (recorded 2026-11-16, after the five dm4 pairs)

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes per 1000 route-steer samples (primary, predicted down or level) | 52.5 | 55.3 | +2.8 | 13.4 | level |
| Lava deaths | 1.6 | 2.0 | +0.4 | 1.7 | no regression |
| World deaths | 1.6 | 2.2 | +0.6 | 2.0 | no regression |
| Stalls | 6.2 | 6.0 | -0.2 | 5.0 | no regression |
| Freezes | 0 | 0 | 0 | | no regression |
| Goals | 25.0 | 21.0 | -4.0 | 7.4 | no regression |
| Engagements | 68.0 | 73.0 | +5.0 | 14.3 | no regression |
| Brink encounters per 1000 route-steer samples (not registered) | 14.7 | 14.5 | -0.2 | 1.2 | level |

All ten tapes held the listen tick class. By this protocol's decision rule the
stock rung holds: the primary is level and no guard regressed, so the change
does no measurable harm on dm4. It also shows no benefit there: the flicker
reduction measured on the lab map did not reproduce. The claim therefore stays
at the isolation tier (`brink-turn-lava-corners`, maps `lab_voidcorner`), with
the dm4 tapes cited as non-regression evidence, and the change stays reverted:
nothing here supports shipping it.

Why it did not transfer is not measured. Its gate is lethal liquid found by a
hazard probe in the last half second, and most of dm4's brinks drop to dry
floor; only the pit's lips and the lava floors trip it, so it may simply act
too rarely there to show. Results: `runs/lab-voidcorner-brink-turn-dm4.results.json`.
