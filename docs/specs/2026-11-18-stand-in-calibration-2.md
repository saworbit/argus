# Stand-in calibration 2: kills per minute in sight

Registered 2026-11-18, before any tape of this calibration was recorded. The
first calibration (`2026-11-15-stand-in-calibration.md`) is closed and is not
edited.

## Why a second one

The first failed dose response (Spearman 0.13) because how much fighting a
match gave the stand-in swamped the skill effect: its time in sight of a bot
ran from 0 to 2608 ticks between matches (#842). Read after that verdict, and
so not evidence for this protocol, the same 16 tapes divided by minutes in
sight instead of minutes of match gave Spearman 0.60. That is the reason for a
fresh, registered calibration on that measure, not a result.

## Design

- Build: main at 89b9852 (build 9387e1e77737, the identity every tape prints),
  installed in a private game directory.
- Map: dm4, three bots, deathmatch, 185 s, wall clock (the stand-in acts on
  wall time).
- Route: the human track of `runs/shane_dm4_2026-11-14_ed8926.log`, as before.
- Bot skill 0, 1, 2 and 3, four matches each, stand-in seeds 5 to 8 within
  each tier (fresh, not the first calibration's 1 to 4), so 16 tapes named
  `standin_cal2_dm4_k<skill>_<seed>`.
- At most two matches at once.

## Measure

Bot kills on the stand-in per minute in sight of a bot:
`tools/argus_standin_calibration.py --measure sight --map dm4`. A kill is an
`ARGEVT` death of the stand-in whose killer is a bot by name. Sight is rebuilt
from each 0.5 s sample: a living bot within 1800u with a clear hull-0 line
between the two eyes (origin + 22). A match with under 3 s in sight carries no
rate and is left out and reported.

## Criterion

- Dose response passes when the Spearman correlation between bot skill and the
  measure over every rated tape is at least 0.5 and the 95 per cent Welch
  interval for skill 3 minus skill 0 excludes zero, positive.
- Level matches when the stand-in's skill 1 mean lies within half to one and a
  half times the person's mean on the same measure. The person's mean is the
  mean over Shane's last four dm4 sessions read by the same rebuild
  (`shane_dm4_2026-11-14_ed8926`, `2026-11-01_bumpercars`, `2026-09-16b`,
  `2026-09-16`): 3.05, 3.21, 5.50 and 3.91, mean 3.92, band 1.96 to 5.88.
- Either way the result goes into `docs/stand-in.md` and
  `tools/lab_instruments.json`.
