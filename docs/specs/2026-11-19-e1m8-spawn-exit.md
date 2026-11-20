# E1m8 upper spawn exit

The spawn at (880 128 24) uses eight new seats to reach the lower graph.
The first drop makes the middle ledge at z -96. The second is a 272u
drop onto the shelf at z -368. This route uses world floor and e1m8's
gravity of 100.

The 312u probe applies on e1m8 to an aligned, grounded route to a seat
240u to 280u below. The floor and projected landing checks still reject
lava, slime and a deeper trace that misses the intended shelf height.
The coordinate sidecar reproduces the tested splice onto the shipped graph.
Full generation uses different waypoint coordinates from the splice and
has its own entries in the same sidecar. The
[regeneration trials](2026-11-20-e1m8-soak.md#full-regeneration) record the
comparison with the shipped graph.

QuakeSpasm took the real bot from the exact spawn into the connected
graph in 7.7 s and from the offset start in 8.2 s. Both reached the
lower waypoint at full health. The shipped guard with the first spawn-exit
graph failed to complete the shelf task within 24 s.
[Repeatable native tasks](../../benchmarks/e1m8_spawn_exit.json)

The first played cohort had four lava deaths on main and eight on the
spawn-exit build, all in the lower arena. Both arms showed slides down
the west face. The deathmatch puppet twice refused six outward links
from n38 and passed the uphill exit to n88. The new graph retires those
six links and preserves every other node and directed link from the
first spawn-exit graph. The confirmed west-face task completed in 5.7 s
on the new build. Main timed out. The candidate also entered lava on
the first placement attempt.

All seven settled spawns pass coverage. The worst reaches 119 of 135
waypoints, or 107 without gated links. The edict budget is 391 of 600
including the runtime reserve.

Three matched 185-second pairs ran at skill 2 and the played cadence.
Control `148d482e6ba7`. Candidate `e1cb6d0031f7`.
[Registration](https://github.com/saworbit/argus/issues/789#issuecomment-7004928494)

Native all-gate verdict is parity.
Median stalls went from 34 to 20.
Lava deaths fell from seven to three, or 2.33 to 1 per tape.
Median route failures rose from 7 to 14. This is outside the registered hard
gates and remains a follow-up signal.
The spawn stall cell had 15 entries in the control hotspot lists
and 0 in the candidate lists.
[Builds, tape hashes and gate results](../../runs/e1m8-spawn-exit-played.results.json)
