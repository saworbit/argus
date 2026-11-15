# Fixed lab clock: validation protocol

Registered 2026-11-15, before any validation tape was recorded. The results
are reported in [the fixed clock guide](../fixed-clock.md); this file is
not edited after the runs start, except to add the link to them.

## The question

The fixed lab clock (`argus-mcp seeds`, `argus-mcp match --seed`) runs the
played 72 Hz frame with `host_framerate 0.0139`, lets the dedicated loop run a
frame per millisecond instead of waiting for the wall clock, and ends each
match at its length through `timelimit`. It repeats exactly for one seed and
build, which has already been checked line for line. What it has not shown is
that a fixed tape is the same game as a played one. A difference could come
from anything that reads the wall clock rather than game time, or from the
real-time server's frame jitter mattering to bot behaviour.

## Design

- Build: one progs, identity `cbc0176e8e8e`, compiled from the branch that
  adds the clock, run from a scratch mod folder (`ARGUS_GAME=argus_idm`).
- Maps: dm4 and dm2, the two goal maps in `tools/lab_objective.json`.
- Skill 2, 185 s, three bots, deathmatch: the conditions of every committed
  band (`band_dm4_r*`, `band_dm2_r*`).
- Played arm: 10 tapes per map on the wall clock, `sys_ticrate 0.0139`, at
  most four engines at once (the measured listen-class limit on this rig).
- Fixed arm: 20 tapes per map, seeds from the standard walk
  (`seed_for(1..=20)`), four lanes, run only after the played arm finishes so
  the two never compete for the CPU.
- Tapes: `fxval_played_<map>_r<n>` and `fxval_fixed_<map>_s<seed>`.

## Metrics

From each tape's brief: stalls, engagements, lava deaths, world deaths,
freezes, coverage cells, consumed goals, bot deaths, routefails and average
speed. Every tape must also read the listen tick class; one that does not is
reported and excluded.

## Criterion

For each metric, d is the fixed arm's mean minus the played arm's mean, and
the margin is the larger of 30 per cent of the played mean and one event
(one unit for average speed is replaced by 30 per cent alone).

- Equivalent: the 90 per cent Welch interval for d lies inside the margin.
- Different: the 95 per cent Welch interval for d excludes zero.
- Inconclusive: neither.

A map is accepted for the fixed clock when no metric reads Different and
engagements, coverage and goals all read Equivalent. Accepted means the fixed
clock may screen a change on that map: a candidate that fails there need not
spend played tapes, and one that passes still owes the played-rate tapes any
ship decision needs. A metric that reads Inconclusive is listed as a limit,
and claims about it keep needing played tapes.

A map that is not accepted keeps the played clock for every purpose, and the
difference is recorded as a finding.
