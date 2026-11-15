# Stand-in human: calibration protocol

Registered 2026-11-15, before any calibration tape was recorded. Results are
reported in [the stand-in guide](../stand-in.md); this file is not edited
after the runs start, except to add the link to them.

## The question

`argus-mcp standin` seats a puppet client that follows a route a human ran,
reacts in 0.25 s, aims with a turn-rate cap and a held, re-rolled offset,
strafes at the human reversal rate and picks weapons from its inventory
(`tools/argus_mcp/src/standin.rs`). The objective's threat goal is "bot kills
on the human per minute at skill 1" (2.0 to 3.0, `tools/lab_objective.json`),
measured only in human sessions. The stand-in is worth something to the lab
only if its own "bot kills on the stand-in per minute" moves the way a
person's would when the bots get harder or softer.

Matching the stand-in to Shane build by build is not the test. His dm4 rate
ran from 0.5 to 3.2 a minute inside one week in August, one session per build
at about five to ten events each, so a build-by-build fit would mostly fit
noise. The test is dose response, plus a check on level.

## Design

- Build: the one this branch compiles (identity printed in every tape).
- Map: dm4, three bots, deathmatch, 185 s, wall clock (the stand-in acts on
  wall time, so its match cannot run on the fixed clock).
- Route: the human track of `runs/shane_dm4_2026-11-14_ed8926.log`, the
  latest dm4 session on the installed build.
- Bot skill 0, 1, 2 and 3, four matches each, stand-in seeds 1 to 4 within
  each tier, so 16 tapes named `standin_cal_dm4_k<skill>_<seed>`.
- At most two matches at once.

## Measures

From each tape's human scorecard: bot kills on the stand-in per minute, its
kills per minute, and the threat ratio.

## Criterion

- Dose response: the Spearman rank correlation between bot skill and bot
  kills on the stand-in per minute, over all 16 tapes, is at least 0.5, and
  the 95 per cent Welch interval for (skill 3 mean minus skill 0 mean)
  excludes zero.
- Level: the stand-in's skill 1 mean is compared with Shane's mean over his
  last four dm4 sessions at skill 1 (1.32, 1.59, 1.14 and 1.02 a minute,
  16 September to 14 November). It is level-calibrated if within half to
  one and a half times that mean (0.64 to 1.91).

When dose response passes, the stand-in may screen threat claims: a change
that should make bots more or less dangerous to a person can be checked
against it before a session is spent, and a claim it contradicts needs a
session to overturn it. When level calibration also passes, its absolute
numbers may be read beside Shane's, always labelled as a stand-in's. When
dose response fails, the stand-in is not used for threat claims, and the
failure is recorded.
