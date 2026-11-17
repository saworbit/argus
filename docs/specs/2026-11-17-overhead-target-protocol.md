# Grounded overhead-target re-plan: registered protocol

Registered 2026-11-17, before any tape of either arm was recorded.

## Why

dm4's wall re-entries cluster: one 128u cell holds 122 of 647
(`runs/lab-wallmix-mix.results.json`). Read frame by frame, a bot routing on
the walkway at z 24 turns back toward a waypoint behind it, its run carries it
off a legal 128u drop into the room below, and it keeps steering at the
walkway waypoint, now 128u overhead behind the walkway's side wall, sliding
and flickering along that wall for seconds. The displacement guard re-plans
only beyond 340u horizontally, and its vertical clause covers water alone.

A proxy over all of dm4's wall re-entries (eight control tapes) found 183 of
647 whose wish heading lies within 8 degrees of a waypoint 64u or more above
the bot, within 340u, with solid on the straight line to it: about 28 per cent
of wall re-entries and 13 per cent of all re-entries, in the room and on the
pit floor under the walkways.

## The change

`Argus_OverheadTarget` (candidate only): a grounded routed bot whose steering
point stands more than step plus jump reach above it (18 plus
`Argus_JumpApex`, 64u at gravity 800), with solid on the straight line to it,
for 0.3 s, re-plans exactly as the 340u guard does. Every typed hop is exempt
(lift, train, jump, rocket jump, swim exit, door, sprint, lift wait). It sits
in the displacement chain after the water clause. Nothing else changes.

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | the tree at 2f6c3f5 plus the `lab_dropwall` and `lab_dropwall2` graphs (shipped QC) | `819F9AB90BC77DF84A34491601430DF2` |
| Candidate | the control plus `Argus_OverheadTarget` and its clause | `457F046853D12C0A3702E434E8A399F6` |

Private game directories `engine/argus_ohctl` and `engine/argus_ohcand`, both
with the motion diagnostic (`scratch1 697`).

## Rungs

1. `lab_dropwall2` (scenario `lab_dropwall2-da26a88635`, graph MD5
   `321f634a`): a room split into three bays below a walkway 128u up whose edge
   is a legal drop. Tapes `labov_ctl_r1` to `r8` and `labov_cand_r1` to `r8`.
2. dm4. Tapes `dm4ov_ctl_r1` to `r8` and `dm4ov_cand_r1` to `r8`.

Each rung: skill 2, 180 s, wall clock at the played rate, eight pairs, control
and candidate launched together on ports 26111 and 26112. Tapes outside the
listen tick class are reported and left out.

## Registered readings

- Primary, per rung: overhead-target wall re-entries per tape. A re-entry (a
  route-led deflection start within two route frames of the bot's previous
  episode) counts when `tools/argus_guard_replica.py` calls it a wall veto and
  its wish heading lies within 8 degrees of a waypoint 64u or more above the
  bot, 24 to 340u away horizontally, with solid on the straight line to it.
- The candidate moves the primary when the mean falls by more than the
  detection limit, 2.8 x pooled sigma x sqrt(2/n).
- The lab rung is informative only if its control averages at least 3 such
  re-entries a tape. Below that it is void and says so; dm4 does not depend on
  it.
- Guards, per rung: lava deaths, world deaths, stalls and freezes must not rise
  past their detection limits; goals must not fall past theirs.
- Reported with no criterion: all wall re-entries, route-led starts, route
  events, routefails and trapped events (a re-plan from a pit with no exit
  ends in routefails and the trapped exit, which costs a frag).

## Verdicts

- A rung supports the change when the primary moves and no guard regresses.
- Supported on `lab_dropwall2` alone: an isolation-tier result.
- Supported on dm4: a dm4 result, recorded in `tools/lab_claims.json` with both
  rungs' tapes. Nothing is installed or shipped on this ladder; that, and any
  further stock map, is Shane's call.
- A guard regression on either rung is reported as such, whatever the primary
  does.

## Results of the first candidate (recorded 2026-11-17)

**`lab_dropwall2` rung: void.** All sixteen tapes held the listen tick class.
The control averaged 0.75 overhead-target re-entries a tape (registered floor
3), so the rung is void: the bays restored routing (route steering about 10 per
cent of motion samples) but the walls bots meet there are bay-wall ends at
their own level, not a waypoint overhead. No guard moved (lava 0.12 to 0.12,
world 0.12 to 0.12, stalls 0.5 to 0.5, goals 22.0 to 25.25 against a limit of
6.26).

**dm4 rung: stopped after one completed pair, without a verdict.** Reading
the candidate's own first tape, the clause never fired where it was meant to:
a bot sat in the room under the walkway for seven seconds with no re-plan. The
bots there are on a jump hop. Node 111 on the walkway carries a level jump
link to node 115 across the open top of the room; a turn-rate-limited run-up
carries them off the edge, and they land in the room with `ar_hopjump` still
set and the hop's target overhead. The candidate exempted jump hops, so it
could not reach the case it was built for. The stop was decided from that
mechanism, not from the primary. Stopping the runners killed pairs 2 and 3
before either wrote a tape; pair 1 is kept as recorded.

## Revision: the second candidate (registered 2026-11-17, before its tapes)

The same clause without the jump exemption, and the re-plan clears the jump
hop it abandons (`ar_hopjump`, `ar_hopspeed`). Navgen lands a jump at most 40u
above its takeoff, below the clause's 64u reach, so a jump hop whose target
stands that far overhead has already failed. Lift, train, rocket jump, swim
exit, door, sprint and lift wait stay exempt.

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | as above | `819F9AB90BC77DF84A34491601430DF2` |
| Candidate 2 | the control plus the revised clause | `1FF4C96DCD4311E4ABE1D361ADAAD94F` |

Private game directories `engine/argus_ohctl` and `engine/argus_oh2cand`.

**Rung: dm4 only.** A lab map holding the mechanism was attempted and not
built: `lab_jumpgap` (`lab_dropwall2` with the walkway cut by a gap over the
room) had both of its jump links refused by the mill at a 128u gap and again
at 96u, where the puppet dropped into the gap each way, so it stays
unregistered. The second candidate is therefore judged on dm4 alone, which
can support a dm4 result and no isolation-tier one.

dm4, skill 2, 180 s, eight pairs, tapes `dm4ov2_ctl_r1` to `r8` and
`dm4ov2_cand_r1` to `r8`, the control and candidate launched together on ports
26111 and 26112. Primary, guards, reported counts and verdict rules are the
ones registered above.

## Addendum: a dm2 guard rung (registered 2026-11-17, before the dm4 verdict was read and before any dm2 tape)

The clause applies on every map, not only where dm4's walkway jump puts bots
under their node. If the dm4 rung supports the second candidate, a dm2 rung
checks that it does not cost anything on other geometry before it is added to
`src/argus.qc` on the branch.

- dm2, skill 2, 180 s, eight pairs, the same two arms, tapes `dm2ov2_ctl_r1`
  to `r8` and `dm2ov2_cand_r1` to `r8`, launched together on ports 26111 and
  26112. Tapes outside the listen tick class are reported and left out.
- Criterion: no guard regresses past its detection limit (lava deaths, world
  deaths, stalls and freezes must not rise; goals must not fall). dm2 has no
  primary on this ladder: its overhead-target count, wall re-entries, route
  events, routefails and trapped events are reported with no criterion.
- If dm4 supports and dm2 holds its guards, the change goes into
  `src/argus.qc` on `lab-scenarios`, committed locally and not installed. If
  dm2 regresses a guard, the change stays a recorded patch and the guide says
  which guard moved. If dm4 does not support, dm2 is not run.

## Results of the second candidate (recorded 2026-11-17)

All sixteen dm4 tapes held the listen tick class.

| Metric | Control mean | Candidate 2 mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Overhead-target wall re-entries a tape (primary) | 15.75 | 11.62 | -4.12 | 6.99 | level |
| Lava deaths | 1.50 | 2.25 | +0.75 | 1.65 | no regression |
| World deaths | 1.50 | 2.25 | +0.75 | 1.65 | no regression |
| Stalls | 6.00 | 5.38 | -0.62 | 3.96 | no regression |
| Freezes | 0 | 0 | 0 | 0 | no regression |
| Goals | 23.0 | 19.0 | -4.0 | 7.18 | no regression |

Reported: wall re-entries 61.4 to 60.8, all re-entries 137.3 to 132.5, route
events 244.6 to 240.6, routefails 1.1 to 0.9, trapped 0 to 0.

**Verdict.** The primary fell by a quarter and stayed inside its detection
limit, so the dm4 rung does not support the second candidate. By the
addendum, dm2 is not run, and the change stays a recorded patch:
`src/argus.qc` is unchanged.

**Why (post hoc, not registered).** Split by place, the overhead-target events
in the room under the walkway jump did not fall (0.88 to 3.38 a tape), and nor
did routed time there (5.7 to 7.0 s, limit 10.7). A candidate tape's longest
room stay (8.1 s) steered at the staged jump's run-up point behind node 111,
with node 115 as its stall node. dm4's jump 111 to 115 is staged, and the
staged run-up runs under `ar_sprintstate`, which the second candidate still
exempts. Where nothing exempts the clause, the events fell from 14.88 to 8.25
a tape. A third version would let the clause act during a staged run-up too,
whose landing navgen bounds the same way as a jump's; it needs its own
registration. Results: `runs/dm4-overhead-target.results.json`.

## Revision: the third candidate (registered 2026-11-17, before its tapes)

The second candidate without the sprint exemption, and the re-plan clears the
staged run-up it abandons (`ar_sprintstate`) along with the jump hop. A staged
run-up steers at a point behind the launch seat whose floor `Argus_JumpRunup`
accepts only between 40u below and 16u above the seat, then charges at a
landing navgen puts at most 40u above the seat. Neither stands 64u over a bot
that is still on the walkway, so a grounded bot whose run-up point or landing
does is already off the line. Phase 3 (sprint flight) is airborne, and the
clause demands ground. Lift, train, rocket jump, swim exit, door and lift wait
stay exempt.

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | as above | `819F9AB90BC77DF84A34491601430DF2` |
| Candidate 3 | the control plus the clause without the jump or sprint exemptions | `5CA1A55855C65977ADEE4BD7B60C7667` |

The tree at the second candidate's commit (c0a41da) still compiles byte-exact
to the control MD5, so the control arm is the one the earlier rungs ran.

Private game directories `engine/argus_ohctl` and `engine/argus_oh3cand`.

**Rung: dm4 only**, for the reason given for the second candidate. dm4, skill
2, 180 s, eight pairs, tapes `dm4ov3_ctl_r1` to `r8` and `dm4ov3_cand_r1` to
`r8`, the control and candidate launched together on ports 26111 and 26112.
Fresh control tapes, not the second candidate's: the pair design compares arms
run side by side. Primary, guards, reported counts and verdict rules are the
ones registered above.

Added for this version, reported with no criterion: the room split the second
candidate's post hoc reading used (overhead-target events and routed seconds
inside the room under the walkway jump, the box x 690 to 1060, y -700 to -390,
z -160 to -90 that reading used), so the mechanism can be read beside the
verdict rather than after it.

**dm2.** The addendum above applies to this candidate unchanged: if dm4
supports it, the dm2 guard rung runs with this candidate in place of the
second (tapes `dm2ov3_ctl_r1` to `r8` and `dm2ov3_cand_r1` to `r8`), and the
change reaches `src/argus.qc` only if dm2 holds its guards. If dm4 does not
support it, dm2 is not run.

## Results of the third candidate (recorded 2026-11-17)

All sixteen dm4 tapes held the listen tick class.

| Metric | Control mean | Candidate 3 mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Overhead-target wall re-entries a tape (primary) | 12.12 | 12.75 | +0.62 | 7.94 | level |
| Lava deaths | 2.25 | 2.25 | 0 | 1.94 | no regression |
| World deaths | 2.25 | 2.38 | +0.12 | 1.96 | no regression |
| Stalls | 6.75 | 9.25 | +2.50 | 5.22 | no regression |
| Freezes | 0 | 0 | 0 | 0 | no regression |
| Goals | 23.5 | 20.88 | -2.62 | 7.44 | no regression |

Reported: wall re-entries 54.2 to 62.6, all re-entries 143.6 to 151.6, route
events 240.1 to 240.4, routefails 1.6 to 1.2, trapped 0 to 0. The registered
room split: overhead-target events in the room 2.62 to 1.00 a tape, elsewhere
9.50 to 11.75, routed seconds in the room 5.7 to 5.3 (limit 8.7).

**Verdict.** The primary did not move, so the dm4 rung does not support the
third candidate. By the addendum, dm2 is not run, and the change stays a
recorded patch: `src/argus.qc` is unchanged. This is the outcome the claim
`overhead-target-replan` registered as its refutation, and it is recorded as
refuted.

**Why (post hoc, not registered).** The third version did shorten the stays it
was built for: the candidate's longest routed stay in the room was 3.8 s, at
match end and routing normally, against the control's 8.6 and 6.2 s, and stays
over 3 s fell from 4 to 2. The room is too small a share of the primary for
that to show. It holds about one to three of the twelve to sixteen
overhead-target events a control tape carries, so a complete fix there cannot
clear a limit near 8, and the rest moved 9.50 to 11.75 here against 14.88 to
8.25 on the second candidate's ladder, which reads as noise. The same control
binary read 15.75 on one ladder and 12.12 on the next. A fix aimed at the room
would need a primary sized to it, such as routed seconds in the room,
registered before its tapes. Results: `runs/dm4-overhead-target.results.json`.
