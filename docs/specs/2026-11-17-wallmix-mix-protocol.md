# lab_wallmix mix check: registered protocol

Registered 2026-11-17, after `lab_wallmix` (scenario `lab_wallmix-58ab73b5ac`,
graph MD5 `f5e024fa`) was built and registered through the `lab_request` MCP
tool, and before any tape on it was recorded.

## Why this map

`tools/argus_guard_replica.py` replays the physics brink guard offline. On
eight dm4 control tapes it read the routed re-entries as 47 per cent walls (the
guard's probe buried in solid), 36 per cent lava, 6 per cent voids and 2.5 per
cent the run-off landing test. Every earlier lab map read 97 to 98 per cent
lava and no walls, because a generated floor is a 16u slab over open air and a
buried probe finds the lava below (`runs/dm4-reentry-guard.results.json`).

`lab_wallmix` makes walls the guard reads as walls. It is a ring of 96u
walkways over lava whose outer edges are the hull walls (margin 0, walkways
`solid_below`), with solid pillars rising from the base to fill the inner
corner at the south-west and the north-east, so bots turn two corners around a
wall and two around a lava lip. Before any tape, the replica reads a probe into
the hull wall or a pillar as `wall` and a probe off the inner lip as `lava`.

Navgen seated a waypoint on each pillar top and minted a rocket-jump link up to
it. The map has no rocket launcher, so neither link can fire.

## What is measured

Only the mix. No candidate arm is run, and no claim moves on this check.

- Arm: the control, the tree at 555c139 plus the `lab_wallmix` graph (shipped
  QC), in the private game directory `engine/argus_wmxctl` with the motion
  diagnostic (`scratch1 697`).
- `lab_wallmix`, skill 2, 180 s, wall clock at the played rate, eight tapes,
  two engines at a time on separate ports.
- Tapes `labwm_ctl_r1` to `r8`. Tapes outside the listen tick class are
  reported and left out.

## Registered reading

`tools/argus_guard_replica.py` over the listen tapes.

- The reading counts only if the replica holds on this map: recall at least
  0.85 on route-led deflection starts and false vetoes at most 0.05 on steady
  routed frames. Otherwise the check is void and says so.
- The map carries dm4's mix if both hold: the wall share of re-entries falls
  within 15 points of dm4's 47 per cent (32 to 62), and the lava plus void share
  within 15 points of dm4's 42 per cent (27 to 57).
- Reported beside it, with no criterion: the run-off share (dm4 2.5 per cent),
  route-led starts by branch, lava deaths and stalls.

## What follows

If the map carries dm4's mix, it becomes the lab map for brink changes aimed at
wall re-entries, and any candidate ladder on it is registered separately before
its tapes. If it does not, the guide records which share missed and by how
much.

## Results (recorded 2026-11-17, after the eight tapes)

All eight tapes held the listen tick class. Control arm `progs.dat` MD5
`364BC8500BD43CCDF9D36DAB8327F25E`. No lava deaths in any tape, stalls 0 to 3.

**The replica held.** Recall 0.947 on 916 route-led deflection starts, false
vetoes 0.007 on 3350 steady frames, so the reading counts.

**Registered reading.** Of 357 re-entries, 72 (20 per cent) are walls, 275 (77
per cent) lava, none are voids or run-offs, and 10 (3 per cent) the replica
does not explain. Per tape the wall share ran 10 to 32 per cent. The wall band
was 32 to 62 and the lava plus void band 27 to 57, so by the registered rule
`lab_wallmix` does not carry dm4's mix. It is the first lab map on which the
guard sees walls at all: every earlier one read none.

**Where (post hoc, not registered).** Three in four re-entries (268) are at the
inner lava lip of the straight walkways. The corners carry few: the pillars
give 38 of the 72 wall re-entries, and the lava corners almost none, because
the corner square leaves a walkway-wide space to turn in. On dm4, by contrast,
the wall re-entries cluster: one 128u cell holds 122 of 647 and twelve cells
hold 64 per cent. The top cell is the north-west corner of an open room at the
end of a wall column, where routes leave the room west into a corridor that
turns north, so route steering aims around the wall end while the run carries
the bot into the corner.

**What follows.** The guide records the reading. A map that carries dm4's mix
needs that turn, an open room left through a corridor around a wall end, with
walls solid to the base. Results: `runs/lab-wallmix-mix.results.json`.
