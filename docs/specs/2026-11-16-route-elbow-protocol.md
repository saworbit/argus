# Route elbow ladder: registered protocol

Registered 2026-11-16, before any ladder tape was recorded. The smoke and
diagnostic tapes named below were recorded first to check that the candidate
compiles, runs and fires. They are development probes and are excluded from
the verdict.

## The change

`Argus_RouteElbow` in `src/argus.qc`. When the straight walk from a routed
bot to its steering node crosses a void or a lava floor (16u centre-line
samples, floor within 64u of the feet, the brink guard's hull-bridge rule for
liquids), steer at the axis-aligned elbow whose two legs both keep floor
underfoot and clear waist-height geometry. Typed hops, airborne bots, height
changes over 18u and lines that are under 32u, over 320u or already
axis-aligned keep the direct target. Arrival, the apex cut and the route are
untouched.

## Arms

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | `src/` at 073be51 plus the lab_voidcorner graph registered in a private copy | `90E5DEC08594EEE65A5C0F011129C49B` |
| Candidate | the control plus `Argus_RouteElbow` and its one call | `A7804FF31CD1A7F3A2A027E6F3901719` |

Both arms run from private game directories (`engine/argus_vcctld`,
`engine/argus_vccandd`) with the motion diagnostic on (`scratch1 697` in
their autoexec). The diagnostic only prints; no steering reads it.

## Instrument

Deflection episodes by preceding cause: a run of motion samples whose cause
is `hazard_*` counts once, credited to the last non-hazard cause before it.
`brief.movement.deflection_causes` reports it (tools/argus_mcp/src/motion.rs).
The brief's `hazards` total is not used: it is throttled to one per bot per
second and dominated by combat strafes on narrow walkways.

## Lab map rung

- Map `lab_voidcorner` (scenario `lab_voidcorner-70ece72d72`), skill 2,
  120 s, wall clock at the played rate, five tapes per arm, control and
  candidate launched together on separate ports in each round.
- Tapes: `labvc_ctl_r1` to `r5`, `labvc_cand_r1` to `r5`.
- Primary, predicted down: `route_steer` deflection episodes per tape.
- Guards, must not rise past their detection limit: lava deaths, world
  deaths, stalls, freezes. Goals must not fall past theirs.
- Detection limit: 2.8 x pooled sigma x sqrt(2/n), the skeptic's rule.
  A change inside it reads "no detectable effect", never "improved".

## Stock map rung

- Map dm4, skill 2, 185 s, five tapes per arm, same pairing.
- Tapes: `dm4elbow_ctl_r1` to `r5`, `dm4elbow_cand_r1` to `r5`.
- Primary, predicted down or level: `route_steer` deflection episodes per
  tape. Guards as above, plus engagements.
- dm4's lava and world deaths are noisy (4 to 11 a tape on one build); they
  are guards here, not the claim.

## Decision

- Lab primary moves and no guard regresses: the claim is supported at the
  isolation tier.
- Stock primary moves or holds and no stock guard regresses: the claim may
  name dm4, citing the lab and the stock tapes together (the promotion rule in
  `docs/lab-scenarios.md`).
- A stock guard regresses: the claim stays at the isolation tier and this file
  records why.
- Every tape is kept, including any that fail the listen tick class; a tape
  outside the listen class is reported and left out of the means.

## Development probes (excluded)

`labvc_ctl_probe1`, `labvc_cand_smoke1`, `labvc_diag_ctl1`,
`labvc_diag_cand1`. In the diagnostic pair, route-steer deflection episodes
read 120 (47 within 128u of a corner) against 68 (16).

## Result of the lab rung (recorded 2026-11-16, after the five pairs)

| Metric | Control | Candidate | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes (primary) | 84, 52, 79, 127, 95 (mean 87.4) | 111, 74, 65, 73, 130 (mean 90.6) | +3.2 | 49.2 | no detectable effect |
| Of those within 128u of a corner | mean 33.0 | mean 33.6 | +0.6 | 14.3 | no detectable effect |
| Lava deaths | 1, 0, 1, 0, 0 | 0, 0, 0, 0, 0 | -0.4 | 0.7 | no detectable effect |
| Stalls | 2, 0, 0, 0, 1 | 2, 2, 1, 1, 0 | +0.6 | 1.5 | no detectable effect |
| Goals | mean 13.0 | mean 11.6 | -1.4 | 4.7 | no detectable effect |

All twenty tapes held the listen tick class. Total and combat deflection
episodes fell past their limits (823.8 to 706.2, 642.4 to 516.6); neither was
registered and the change has no path to combat steering, so they are
flagged, not claimed.

The primary did not move, so the claim is not supported. The elbow did fire:
mode-2 route frames within 128u of a corner held an axis-aligned wish 27 per
cent of the time in the control and 60 per cent in the candidate. Reading the
frames before each deflection showed why it could not help: 74 per cent of
route-steer deflections began mid-turn, with the movement heading rotating
at AR_TURNRATE (320 degrees a second), at a median 201 u/s. Stock acceleration
only adds along the wish, so the old heading bleeds off through friction
alone, and offline integration of the NQ rules puts the overshoot of a 90
degree turn at 200 u/s at 97u. The elbow made bots run to the corner centre
before turning, which adds overshoot.

The stock rung was cancelled once the lab primary had failed, because an
unsupported isolation result has nothing to promote. Two dm4 pairs had
already run (`dm4elbow_ctl_r1`, `r2`, `dm4elbow_cand_r1`, `r2`); they are
kept and not read. The change is reverted, with its post-mortem beside the
route steering in `Argus_AI`.

## Correction (2026-11-16, after the brink turn and early turn ladders)

The first analysis read motion rows with a pattern that expected one space after `wish`; QuakeC's `ftos` pads fractional values (`wish  66.8`), so about 8 per cent of samples, every frame with a fractional wish, were dropped. The corrected pattern matches the lab's own parser (`tools/argus_mcp/src/motion.rs`) exactly. The results file now holds the corrected analysis, with the first recording kept as `original_analysis`. The verdict is unchanged; the numbers in the result section above
are superseded by these:

| Metric | Control | Candidate | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes a tape (primary) | 105.6 | 112.2 | +6.6 | 59.4 | no detectable effect |
| Of those within 128u of a corner | 38.8 | 41.2 | +2.4 | 17.5 | no detectable effect |

Mode-2 route frames within 128u of a corner held an axis-aligned wish 27 per
cent of the time in the control and 58 per cent in the candidate. Over the 28
control tapes of all four lab_voidcorner ladders, 71 per cent of route-steer
deflection episodes begin mid-turn, and 77 per cent of those begin straight
after a previous deflection: route steering re-asserts its heading for a frame
or two and the guard fires again. Under 1 per cent begin at a waypoint
handoff, which is why a handoff change could not move this metric
(`runs/lab-voidcorner-turn-diagnosis.results.json`).
