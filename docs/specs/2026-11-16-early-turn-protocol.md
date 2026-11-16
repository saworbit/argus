# Early turn ladder: registered protocol

Registered 2026-11-16, after the route elbow and brink turn ladders
([elbow](2026-11-16-route-elbow-protocol.md),
[brink turn](2026-11-16-brink-turn-protocol.md)) and before any early turn
tape was recorded. No development probe of this candidate was run.

## The change

`Argus_EarlyTurn` in `src/argus.qc`, called from the apex block of the routed
advance only where the existing apex cut refuses because the 48u probe along
the cut finds a hazard (lava, slime, a lethal void or a deadly run-off). It
hands the steering on to the next node when all of these hold:

- the bot is grounded and its distance to the current node is at most
  0.35 s of travel at its horizontal speed, bounded to 48 to 112u;
- the turn between the leg to the current node and the next leg is at least
  35 degrees, and the next leg is at least 32u;
- the 48u probe along the current velocity is clean (the momentum, not the
  chord, carries the bot on);
- the eye line to the next node is clear.

Offline NQ integration of a 90 degree, 64u walkway corner (stock friction and
acceleration, the 320 degree a second steering limit, the guard's 32u probe)
keeps body and probe on the floor with that switch distance at 200, 260 and
320 u/s, and puts the probe 6.5u over the lip with today's 48u switch at 200.

## Arms

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | the registered tree at 674de9b (shipped QC plus the lab_voidcorner graph) | `90E5DEC08594EEE65A5C0F011129C49B` |
| Candidate | the control plus `Argus_EarlyTurn` and its one call | `2E5262F19FCC802ADB2B8F5BDC9F5A6B` |

Private game directories `engine/argus_vcctld` and `engine/argus_vccand3d`,
both with the motion diagnostic (`scratch1 697`).

## Lab map rung

- `lab_voidcorner`, skill 2, 180 s, wall clock at the played rate, ten fresh
  pairs, control and candidate launched together on separate ports.
- Tapes `labvc4_ctl_r1` to `r10`, `labvc4_cand_r1` to `r10`.
- Primary, predicted down: route-steer deflection episodes per 1000
  route-steer motion samples, per tape (the brink turn confirmation's
  primary; the count a tape scales with routed time).
- Guards: lava deaths, world deaths, stalls and freezes must not rise past
  their detection limits; goals must not fall past theirs.
- Detection limit 2.8 x pooled sigma x sqrt(2/n). Inside it reads "no
  detectable effect".

## Stock map rung

Only if the lab primary moves and no lab guard regresses: dm4, skill 2, 185 s,
five pairs, tapes `dm4et_ctl_r1` to `r5` and `dm4et_cand_r1` to `r5`, the
same normalised primary (predicted down or level) and the same guards plus
engagements. dm4 is the stock map with the most lava corners.

## Decision

As in the earlier protocols: the lab primary moving with no guard regressing
supports an isolation-tier claim; the stock rung decides whether the claim may
also name dm4 (the promotion rule in `docs/lab-scenarios.md`); a stock guard
regressing keeps it at the isolation tier. Every tape is kept.

## Result of the lab rung (recorded 2026-11-16, after the ten pairs)

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes per 1000 route-steer samples (primary) | 53.2 | 56.9 | +3.7 | 8.6 | no detectable effect |
| Route-steer deflection episodes a tape | 151.1 | 167.9 | +16.8 | 25.9 | no detectable effect |
| Of those within 128u of a corner | 61.3 | 58.0 | -3.3 | 14.7 | no detectable effect |
| Lava deaths | 0.6 | 0.3 | -0.3 | 0.9 | no detectable effect |
| Stalls | 1.1 | 0.7 | -0.4 | 1.1 | no detectable effect |
| Goals | 18.0 | 17.8 | -0.2 | 5.2 | no detectable effect |
| Engagements | 134.1 | 132.1 | -2.0 | 10.0 | no detectable effect |

All twenty tapes held the listen tick class. The primary moved the wrong way
inside its limit and the corner episodes the change was built for did not
fall, so the claim is refuted and the stock rung was not run. The change is
reverted, with its post-mortem beside the route steering in `Argus_AI`.
Results: `runs/lab-voidcorner-early-turn.results.json`.

The offline integration modelled a bot entering the corner on the centre
line at a steady speed with nobody near it. Whatever starts the turns that
end on the lip in play (re-routing, a goal change, the resumption after a
fight, an off-centre entry), it is not the moment of the waypoint handoff
at the corner. The next corner change should first read where those turns
begin, from the motion rows and the route events together.
