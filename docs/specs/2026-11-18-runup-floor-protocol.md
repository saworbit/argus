# Run-up floor veto: registered protocol

Registered 2026-11-18, before any tape of either arm was recorded.

## Why

On dm4, bots lining up the staged walkway jump from node 111 (849 -343 24) to
node 115 (945 -599 24) can leave the walkway during the run-up (#867). The
edge beside the run-up is a legal 128u drop, so the brink guard allows it; the
bot lands in the room below still on the hop and steers at the run-up point or
the landing, 128u overhead behind the walkway's side wall, sliding along that
wall until something else clears the route. Eight-pair dm4 control ladders
averaged 5.7 routed seconds a tape in that room
(`runs/dm4-overhead-target.results.json`). The overhead-target re-plan aimed
at the aftermath is refuted; this change aims at the cause.

## The change

In `Argus_MoveHazard`, while `ar_sprintstate` is -1 or 1 (armed at the launch
seat, then walking back to the run-up point), a floor more than a step (18u)
below the probe is a veto rather than a legal descent. Phase 2, the charge in
which the gap is crossed, is unchanged, and so is every other state.

| Arm | Source | Game directory |
|---|---|---|
| Control | main at 89b9852 (build 9387e1e77737) | `engine/argus_soak_ctlm` |
| Candidate | the control plus the veto above (build 7ddba72df21f) | `engine/argus_soak_runupm` |

Both arms carry the motion diagnostic (`scratch1 697`).

## Rung

dm4, skill 2, 185 s, wall clock at the played rate, eight pairs, control and
candidate launched together and interleaved. Tapes outside the listen tick
class are reported and left out. If dm4 supports the change, a dm2 guard rung
of five pairs runs before it reaches `src/argus.qc` on main.

## Registered readings

- Primary: routed seconds a tape inside the room box x 690 to 1060, y -700 to
  -390, z -160 to -90, from `tools/argus_guard_replica.py --overhead
  src/argus_nav_dm4.qc.json --region 690 1060 -700 -390 -160 -90`. Room
  overhead-target events are reported beside it.
- The candidate moves the primary when its mean falls by more than the
  detection limit, 2.8 x pooled sigma x sqrt(2/n).
- Guards, each against its limit from `argus_lab.py skeptic`: lava deaths,
  world deaths, stalls and freezes must not rise past their limits, and goals
  must not fall past theirs.
- Supported when the primary moves and no guard fails; not supported
  otherwise. Every tape is kept.

## Result (recorded 2026-11-18, after the eight pairs)

All sixteen dm4 tapes held the listen tick class.

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Routed seconds a tape in the room (primary) | 9.26 | 3.40 | -5.86 | 10.76 | does not move |
| Lava deaths | 1.6 | 2.4 | +0.8 | 2.1 | no regression |
| World deaths | 1.62 | 2.50 | +0.88 | 1.18 | no regression |
| Stalls | 6.6 | 6.2 | -0.4 | 8.0 | no regression |
| Freezes | 0 | 0 | 0 | 1.0 | no regression |
| Goals | 21.2 | 22.1 | +0.9 | 7.1 | no regression |

Reported: overhead-target events in the room 5.5 to 1.0 a tape, overhead-target
wall re-entries over the whole map 16.62 to 15.88. Per tape, routed seconds in
the room ran 0, 21.6, 0.5, 17.9, 1.2, 15.0, 9.1 and 8.8 on the control and 0,
0, 1.8, 0, 20.1, 0.3, 5.0 and 0 on the candidate.

**Verdict.** The primary fell by more than half, but not by the detection
limit, so the change is not supported and the dm2 rung is not run. The veto
is the change described above and is not merged: `src/argus.qc` on main is
unchanged.

**Why (post hoc, not registered).** The room is either empty or full on a
control tape: three of eight tapes put 15 s or more there and three put under
2 s. Eight pairs cannot size a mean that swings like that, and the candidate
still had one 20.1 s tape. Six of its eight tapes were near zero against three
of eight on the control, which is the shape a working fix would have, so a
rerun with more pairs, or a primary that counts tapes with a long stay, is the
next step rather than a new mechanism. World deaths rose by 0.88 a tape inside
their limit, and that has to be watched in any rerun.
