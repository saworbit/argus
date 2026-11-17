# lab_drymix2 mix check: registered protocol

Registered 2026-11-17, after `lab_drymix2` (scenario `lab_drymix2-e81474c4ef`,
graph MD5 `5f60d525`) was built and registered through the `lab_request` MCP
tool, and before any tape on it was recorded.

## Why this map

`lab_drymix` missed the registered mix band by one point: 55 per cent of its
control re-entries had the wanted heading pointing at lava or a void, against
dm4's 39 and a band of 24 to 54
([protocol](2026-11-17-drymix-protocol.md)). Its non-lethal re-entries came
mostly from the west run-off ledge, a dry 96u ledge 80u down with lava beyond
it, while its plain 64u dry drop on the south contributed few. `lab_drymix2` is
`lab_drymix` with a second run-off ledge along the inner side of the north
walkway (`ledge_nw` and `ledge_ne`, joined by stairs back up), so that run-off
lips carry a larger share.

## What is measured

Only the mix. No candidate arm is run, and no claim moves on this check.

- Arm: the control, the tree at 2c019d4 plus the `lab_drymix2` graph (shipped
  QC), in the private game directory `engine/argus_dmx2ctl` with the motion
  diagnostic (`scratch1 697`).
- `lab_drymix2`, skill 2, 180 s, wall clock at the played rate, eight tapes,
  two engines at a time on separate ports.
- Tapes `labdm2_ctl_r1` to `r8`. Tapes outside the listen tick class are
  reported and left out.

## Registered reading

The method is the one the `lab_drymix` ladder used: re-entries probed 48u ahead
against the map's BSP with the guard's floor rules. The reading is the share of
re-entries whose wanted heading points at lava or a void. The map carries dm4's
mix if that share falls within 15 points of dm4's 39 per cent (24 to 54 per
cent); outside that band it does not, whichever side it falls.

## What follows

If the share lands in the band, `lab_drymix2` becomes eligible for a candidate
ladder of the mode-2 brink check, registered separately before its tapes. If it
does not, the guide records the reading, and the next step is a judgment about
whether hand-built run-off lips can reach dm4's mix at all.

## Results (recorded 2026-11-17, after the eight tapes)

All eight tapes held the listen tick class. Control arm `progs.dat` MD5
`53FF71E0A0D0E85A9038ABC4AD70C78D`.

**Registered reading.** 439 of 684 re-entries (64 per cent) have the wanted
heading pointing at lava or a void; 45 (7 per cent) are momentum and 200 (29
per cent) neither. Per tape the share ran 41 to 85 per cent. The band was 24 to
54 per cent, so by the registered rule `lab_drymix2` does not carry dm4's mix.
Adding a run-off ledge moved the share away from dm4, not towards it.

**Why (post hoc, not registered).** Two readings explain it, both taken from
tapes already recorded:

- A run-off ledge is a dry drop only from the walkway above it. Its own inner
  edge drops straight into lava, so a bot on the ledge meets a lethal lip: 109
  of the 141 re-entries on the two new north ledges point at lava.
- Splitting every map's re-entries by whether the bot stood within 128u of a
  waypoint: all 1369 of dm4's control re-entries are on the graph, 39 per cent
  lethal. On `lab_drymix` 58 per cent are off the graph, and on `lab_drymix2`
  36 per cent, every one of them on `ledge_s` (on `lab_drymix` also `ledge_n`),
  run-off ledges the generated graph seats no waypoint on. The stairs in both
  requests run across the ledge and cut it into a pocket a bot can fall into
  and leave by no link. On the graph, both maps read about 71 per cent lethal,
  nowhere near dm4. `lab_drymix`'s near miss of 55 per cent was an average of
  that and an off-graph artefact.

**What follows.** The guide records the reading. `lab_request` gained a
coverage gate: a standable floor with no waypoint now refuses registration
unless the request marks it `off_graph`, and the gate would have refused both
drymix maps. No candidate ladder runs on `lab_drymix2`. Results:
`runs/lab-drymix2-mix.results.json`.
