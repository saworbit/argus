# lab_drymix ladder: registered protocol

Registered 2026-11-17, after `lab_drymix` (scenario `lab_drymix-288fc2055f`,
graph MD5 `b58fe7ee`) was built and registered through the `lab_request` MCP
tool, and before any tape on it was recorded.

## Why this map

The mode-2 brink check cut flicker on `lab_voidcorner` and not on dm4. The
reason, read from both rungs' tapes, was the mix of lips: on `lab_voidcorner`,
every lip of which drops into lava, 95 per cent of routed re-entries have the
wanted heading pointing at lava or a void; on dm4, 39 per cent
(`runs/lab-voidcorner-brink-flicker-gate.results.json`). `lab_drymix` keeps
dm4's 96u walkway width and adds dm4's other lip types: a dry ledge 80u down
with lava beyond it, and a plain 64u dry drop with stairs back up.

This ladder asks two questions. Does the new map reproduce dm4's mix? And does
it then predict dm4's result for the same change, which `lab_voidcorner` did
not?

## Arms

| Arm | Source | progs.dat MD5 |
|---|---|---|
| Control | the tree at 1526580 plus the lab_drymix graph (shipped QC) | `0E501B8C939213B3EE6DDD4C8630A79C` |
| Candidate | the control plus the mode-2 brink check, code identical to the one laddered in `2026-11-17-brink-flicker-protocol.md` | `82908EB76A14AB13A26A46A05A1AB2E3` |

Private game directories `engine/argus_dmxctl` and `engine/argus_dmxcand`,
both with the motion diagnostic (`scratch1 697`).

## Rung

- `lab_drymix`, skill 2, 180 s, wall clock at the played rate, eight pairs,
  control and candidate launched together on separate ports.
- Tapes `labdm_ctl_r1` to `r8`, `labdm_cand_r1` to `r8`.
- Tapes outside the listen tick class are reported and left out.

## Question 1: does the map carry dm4's mix?

Measured on the control arm alone, with the method of the gate results file
(re-entries probed 48u ahead against the map's BSP with the guard's floor
rules). Registered reading: the share of re-entries whose wanted heading points
at lava or a void. dm4 read 39 per cent and `lab_voidcorner` 95. The map
carries dm4's mix if its share falls within 15 points of dm4's (24 to 54 per
cent); outside that band it does not, whichever side it falls.

## Question 2: does it predict dm4's result?

- Primary: route-steer deflection episodes per 1000 route-steer motion
  samples. dm4 read level for this change (55.3 to 55.6, limit 12.2) and
  `lab_voidcorner` read a 20 per cent fall.
- The map predicts dm4 here if the primary reads level, inside its detection
  limit. A fall past the limit means it behaves like `lab_voidcorner` instead.
- Guards, as before: lava deaths, world deaths, stalls and freezes must not
  rise past their detection limits; goals must not fall past theirs.
- Detection limit 2.8 x pooled sigma x sqrt(2/n).

## What follows

If both questions read yes, `lab_drymix` becomes the lab map to use for brink
changes before a stock rung, and the guide says so. If either reads no, the
guide records which, and that a lab map's mix has to be checked against the
stock map before its result is trusted. No claim about the change itself moves
on this ladder: it is already recorded as isolation-tier (`mode2-brink-check`).

## Results (recorded 2026-11-17, after the eight pairs)

All sixteen tapes held the listen tick class.

**Question 1.** On the control arm, 470 of 852 re-entries (55 per cent) have the
wanted heading pointing at lava or a void; 96 (11 per cent) are momentum and
286 (34 per cent) neither. The band was 24 to 54 per cent, so by the registered
rule the map does not carry dm4's mix. It moved most of the way from
`lab_voidcorner`'s 95 per cent towards dm4's 39, and missed by one point.

**Question 2.**

| Metric | Control mean | Candidate mean | Change | Detection limit | Reading |
|---|---|---|---|---|---|
| Route-steer deflection episodes per 1000 route-steer samples (primary) | 88.4 | 73.6 | -14.8 | 24.7 | level |
| Brink encounters per 1000 route-steer samples | 19.7 | 17.0 | -2.7 | 3.5 | level |
| Lava deaths | 1.1 | 0.9 | -0.2 | 1.2 | no regression |
| Stalls | 4.8 | 3.5 | -1.2 | 4.0 | no regression |
| Goals | 17.1 | 18.5 | +1.4 | 4.8 | no regression |
| Engagements | 112.5 | 110.0 | -2.5 | 13.6 | no regression |

The primary reads level, so by the registered rule the map predicts dm4 here.
The reading carries no information, though: this map's control is much noisier
than either other map's (60 to 113 episodes per 1000 against dm4's 42 to 68),
its detection limit is 28 per cent of the control mean, wider than the 20 per
cent fall that separated `lab_voidcorner` from dm4, and the point estimate
(-17 per cent) sits nearer `lab_voidcorner`'s result than dm4's.

**What follows.** Question 1 read no, so `lab_drymix` does not become the lab
map for brink changes. The guide records why, and the lesson that held: the mix
check needs only the control arm and settles whether a lab map can stand in for
a stock map, so it belongs before any candidate ladder on a new map. Results:
`runs/lab-drymix-mode2.results.json`.
