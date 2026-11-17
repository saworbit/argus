# lab_dropwall mix check: registered protocol

Registered 2026-11-17, after `lab_dropwall` (scenario `lab_dropwall-be907f5db2`,
graph MD5 `179a846c`) was built and registered through the `lab_request` MCP
tool, and before any tape on it was recorded.

## Why this map

`lab_wallmix` gave the guard walls to see and read 20 per cent wall
re-entries against dm4's 47 (`runs/lab-wallmix-mix.results.json`). dm4's wall
re-entries cluster: one 128u cell holds 122 of 647. Read frame by frame, the
cell is not a corridor turn as first described. A bot routing on the walkway at
z 24 turns back toward a waypoint behind it, its run carries it off the
walkway edge, a legal 128u drop the guard allows, into the room below, and it
keeps steering at the walkway waypoint (node 114), now 128u overhead behind the
walkway's side wall. The displacement guard re-plans only beyond 340u
horizontally, and the vertical guard covers water alone, so the bot slides and
flickers along that wall for seconds. Of the 19 room visits behind the
cluster, 7 came off the walkway within 10 s and 14 came up the south stairs
while investigating a noise; in all of them route steering aimed at the
walkway overhead.

`lab_dropwall` copies that geometry: a north walkway 128u above a 640 by 576
room, its edge a legal drop into the room and its side face a wall solid to
the base, with the only way back up by stairs at the far east end. The
walkway's east half and the south and east walkways have lava lips. Margin 0
puts the hull walls on every outer edge. Spawns stand on the walkways: with two
in the room the mill's roster body-blocked the puppet and convicted a different
flat link on each of three passes.

## What is measured

Only the mix. No candidate arm is run, and no claim moves on this check.

- Arm: the control, the tree at 2f6c3f5 plus the `lab_dropwall` graph (shipped
  QC), in the private game directory `engine/argus_dwlctl` with the motion
  diagnostic (`scratch1 697`).
- `lab_dropwall`, skill 2, 180 s, wall clock at the played rate, eight tapes,
  two engines at a time on separate ports.
- Tapes `labdw_ctl_r1` to `r8`. Tapes outside the listen tick class are
  reported and left out.

## Registered reading

`tools/argus_guard_replica.py` over the listen tapes, under the rule used for
`lab_wallmix`.

- The reading counts only if the replica holds on this map: recall at least
  0.85 on route-led deflection starts and false vetoes at most 0.05 on steady
  routed frames.
- The map carries dm4's mix if both hold: the wall share of re-entries falls
  within 15 points of dm4's 47 per cent (32 to 62), and the lava plus void share
  within 15 points of dm4's 42 per cent (27 to 57).
- Reported beside it, with no criterion: re-entries by place (in the room
  within 64u of the walkway's side face, elsewhere in the room, on the
  walkways), the run-off share, lava deaths and stalls.

## What follows

If the map carries dm4's mix, it becomes the lab map for brink changes, and a
candidate aimed at the overhead-target wall flicker is registered separately
before its tapes, with a dm4 rung. If it does not, the guide records which
share missed and by how much.

## Results (recorded 2026-11-17, after the eight tapes)

All eight tapes held the listen tick class. Control arm `progs.dat` MD5
`C4EB81C5EB8FAFB1791009C31287F44C`. No lava deaths and no stalls in any tape.

**The replica held** (recall 1.0 on 46 route-led deflection starts, false
vetoes 0 on 107 steady frames), but on very little: the whole set held 13
re-entries, 3 walls (23 per cent) and 10 lava (77 per cent), and four tapes
held none. By the registered rule `lab_dropwall` does not carry dm4's mix.

**Why (post hoc, not registered).** Bots on this map fight rather than route.
Route steering was 0.4 per cent of motion samples, against 27 per cent on a
dm4 control tape and 10 on `lab_wallmix`; combat strafing alone was 52 per
cent. The open room gives every bot a line of sight to every other and to the
walkway above, so the routed travel that produces re-entries hardly happens.

**What follows.** `lab_dropwall2` splits the room into three bays with walls
rising from the base, and carries the ladder of the grounded overhead-target
re-plan (`2026-11-17-overhead-target-protocol.md`). Results:
`runs/lab-dropwall-mix.results.json`.
