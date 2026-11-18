# e1m7 jump landing check, kd_spread: registered protocol

Registered 2026-11-18, before any tape of either arm was recorded.

## Why

In #773's ten-a-side e1m7 ladder of the jump landing check
(`Argus_JumpLandHazard`), `kd_spread`, the best bot's frags minus the worst
bot's, widened from a median of 6 to 10.5 (mean 6.8 to 8.6) while frag totals
held (median 30 to 31). The same control read a median of 6 in that set and 8
in the run-off ladder, so it may be noise, but it flagged in both #773 ladders
and nothing explains it (#785).

## Arms

| Arm | Source | Game directory |
|---|---|---|
| Control | main at 89b9852 with `Argus_JumpLandHazard` returning FALSE, so no reachability, stall or escort jump is refused (build 4e0cd0792e0f) | `engine/argus_soak_nojl` |
| Candidate | main at 89b9852, the shipped check (build 9387e1e77737) | `engine/argus_soak_ctl` |

## Rung

e1m7, skill 2, 185 s, wall clock at the played rate, ten pairs, launched
together and interleaved. Tapes outside the listen tick class are reported and
left out.

## Registered readings

- Primary: `kd_spread` per tape, from `argus_lab.py skeptic --metric
  kd_spread`. The check widens it when the candidate's mean exceeds the
  control's by more than the detection limit, 2.8 x pooled sigma x sqrt(2/n).
- If it widens: per bot, frags against that bot's `jumpveto` count, to name
  who gains. If it does not, that breakdown is not read.
- Reported beside it, with no criterion: frags, lava deaths and world deaths.

## Result (recorded 2026-11-18, after the ten pairs)

All twenty tapes held the listen tick class.

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| kd_spread (primary) | 5.1 | 6.6 | +1.5 | 2.9 | does not widen |

Reported, with no criterion: frags 29.1 to 30.5 a tape (median 28.5 to 29.5),
lava deaths 2.2 to 1.6, world deaths 2.2 to 1.6. Every other gate the
skeptic reads (stalls, engages, freezes, cover, goals) shows no detectable
effect.

**Verdict.** The check does not widen `kd_spread`. The candidate's mean sits
above the control's, as it did in #773, but by half the limit, and the frag
totals hold. By the protocol, the per-bot `jumpveto` breakdown is not read.
The shipped check stays as it is. Tapes: `runs/study_kd785_nojl_r1` to `r10`
and `runs/study_kd785_ctl_r1` to `r10` (machine-local).
