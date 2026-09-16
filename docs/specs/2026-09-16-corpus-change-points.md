# Every step in the record, found by a detector

A regression is a change in a series, not a difference between two
samples. Pairwise comparison throws away every other tape ever
recorded, and there are 752 of them in `runs/`, each stamped with the
date the engine wrote it, on a small set of maps, measuring the same
metrics.

Reproduce with:

```
argus-mcp corpus --rebuild --write        # the index, once
argus-mcp history                         # bot series, every map
argus-mcp history --kind human
argus-mcp history --map dm2 --tick listen # one rate class
```

Binary segmentation with a permutation-calibrated max-t statistic,
recursing into both segments, minimum segment five tapes, p below 0.01.
That is E-Divisive's structure with a cheaper statistic; the substitution
is argued in `history.rs`.

## The bot series, 2026-09-16

```
map   metric       date              run                    before -> after   p
dm2   stalls       2026-08-19 06:28  ab_dm2_doors            50.0    28.0    .002
dm2   stalls       2026-08-29 10:37  ab_dm2_v403_control     29.2    44.6    .001  *
dm2   goals        2026-08-27 00:00  ab_dm2_shove            19.2     6.3    .001
dm3   stalls       2026-08-27 19:11  ab_dm3_knit1            22.8    58.0    .001
dm3   stalls       2026-08-28 09:33  ab_dm3_verdictjump1     79.3    47.4    .001
dm3   goals        2026-08-19 21:24  ab_dm3_gndride          19.0    44.5    .002  *
dm3   goals        2026-08-27 19:11  ab_dm3_knit1            26.4     8.6    .001
dm3   goals        2026-08-28 10:42  ab_dm3_islet1            5.5    11.2    .002
dm4   stalls       2026-08-17 15:48  ab_dm4_routegen2        48.5    27.5    .002
dm4   stalls       2026-08-18 07:38  ab_dm4_liftdormant      24.7    45.2    .006
dm4   stalls       2026-08-18 08:13  ab_dm4_bisect3          35.3     8.0    .001
dm4   stalls       2026-08-19 11:02  ab_dm4_investigate2     15.9     6.4    .001
dm4   engages      2026-08-17 13:28  ab_dm4_button           52.0    63.4    .003
dm4   engages      2026-08-18 08:52  ab_dm4_v317c            61.3    78.9    .004
dm4   lava_deaths  2026-08-14 15:24  ab_dm4_B3               12.3     4.4    .001
dm4   cover        2026-08-19 11:02  ab_dm4_investigate2    366.4   340.1    .001
dm4   goals        2026-08-17 12:17  ab_dm4_deathanim        45.5    26.2    .001
dm4   goals        2026-08-20 21:38  ab_dm4_preposition1     26.7    16.7    .001
dm4   goals        2026-08-28 09:13  ab_dm4_labprobe         19.6    15.8    .009
e1m1  stalls       2026-09-13 16:58  ab_e1m1_mover1          66.9    34.8    .003
e1m1  engages      2026-09-13 11:19  probe_e1m1_stall         0.0     3.5    .005
e1m1  engages      2026-09-13 16:58  ab_e1m1_mover1           1.1    17.8    .001
e1m1  cover        2026-09-13 16:58  ab_e1m1_mover1         165.0   338.2    .001
e1m1  goals        2026-09-13 18:45  ab_e1m1_mover3           0.8     3.8    .001
e1m6  cover        2026-09-13 22:37  ab_e1m6_apexgate2       68.7   322.2    .002  *
```

`*` marks a step where the commonest tick class differs either side.
The tool prints those two columns on every row for exactly this reason:
the server frame rate is itself a step in most series, and reading one
as the other is the first mistake available.

The human series carries one step, found independently of the bot tapes:

```
dm4   stalls  2026-08-17 17:44  shane_dm4_2026-08-17_v311  32.2 -> 8.8  .001
```

## What it reproduces, which is how you know it works

Nearly every step is an event this project already wrote down, and the
detector names the tape that shipped it.

- **dm4 lava at `ab_dm4_B3`, 12.3 to 4.4.** The 2026-08-14 hazard
  avoidance. The changelog names the same tape as the shipped
  deflection.
- **dm4 stalls at `ab_dm4_bisect3`, 35.3 to 8.0.** The two-author
  forensics, where restoring the v3.16 deflection fan ended four
  consecutive off-band matches.
- **dm4 stalls at `ab_dm4_routegen2`, 48.5 to 27.5.** The wedge hunt:
  route generation stamps and the displacement guard.
- **dm4 engages at `ab_dm4_v317c`, 61.3 to 78.9.** v3.17 shipping.
- **e1m1 at `ab_e1m1_mover1`:** engages 1.1 to 17.8, coverage 165 to
  338, stalls 66.9 to 34.8, all on one tape. That is #281, the day
  e1m1 stopped being an empty map.
- **dm3 stalls at `ab_dm3_knit1`, 22.8 to 58.0**, and back down at
  `ab_dm3_verdictjump1`. The knit era and the verdict remint, in order.
- **dm4 human stalls at `shane_dm4_2026-08-17_v311`, 32.2 to 8.8.**
  v3.11's drop-lip advance, recorded at the time as the all-time low.

## Three things it found that were not written down

**1. The September dm2 stall rise has a date.** `CLAUDE.md` records it
as "the September dm2 ladder mean is 52 against late August's 36 with a
60 to 199 tail. Not bisected." The detector puts the step at
2026-08-29 10:37, at `ab_dm2_v403_control`, 29.2 to 44.6, p 0.001.

**AND IT IS CONFOUNDED, WHICH THE TOOL SAYS ON THE ROW.** The commonest
tick class before that step is `dedicated_fast` and after it is
`listen`. Restricting the series to either class alone, the step does
not appear. That does not prove it is the rate - phase 0 measured six
played-rate tapes against three at 19 Hz and found dm2 stalls
overlapping at z 0.00 - and it does not prove it is code. It proves the
question was never clean, and it is the reason the tick columns exist.
Anyone re-opening this should run one class.

**2. Some steps are metric boundaries, not behaviour.** The detector
cannot tell them apart and must not be read as though it could. Three
of the goal steps are changes in what the counter counts, each one
already recorded in this repo as a boundary:

- `ab_dm4_deathanim` 2026-08-17, goals 45.5 to 26.2: the GOAP boundary
  where goal completions started counting the touch rather than the
  32 unit arrival.
- `ab_dm4_preposition1` 2026-08-20, goals 26.7 to 16.7: pre-positioning
  stopped counting an arrival at a still-pending item.
- `ab_dm2_shove` and `ab_dm3_knit1`, the same week, same metric.

A detector run over a corpus with eight recorded metric boundaries in
it will find the boundaries. That is a feature when you are auditing
the instrument and a trap when you are hunting a regression.

**3. `ab_dm4_labprobe` is a step in dm4 goals.** Small, p 0.009, and it
is the day the puppet client started connecting to matches. Which is
how the next finding turned up.

## Two defects the index found on its way

Neither is in this analysis; both are in the parser underneath it.

**The puppet read as a human.** The lab netclient emits `ARGLOG` rows
and never spawns, and the human-track split reads any such track as a
person. So every tape the puppet connected to briefed as a human
session, `compare` flagged it review-only, and two committed BASELINES
said a human had played in them (`band_dm4_2`, `band_dm2_3`).
`Argus_CanSee` has refused the netname `labprobe` since v3.85 for
exactly this reason; the parser owes it the same courtesy, and now does.
The engine's own `unconnected` placeholder is excluded with it.

**Half the human sessions read as botmatches.** Human `ARGLOG` tracks
only exist from v3.66, so 46 of the 73 harvested sessions are human
matches with no human in their telemetry. Their bots were fighting a
person, which moves every metric they recorded, and they were sitting
in the bot series. The index tags a session by the harvester's naming
as well as by the telemetry.

Both corrections are in the tables above.

## Bisection, when the oracle is a handful of noisy tapes

`git bisect` assumes an oracle: each answer permanently discards half
the range, so one unlucky tape sends the search into the wrong half and
it never comes back. Phase 1 came three tapes from convicting the wrong
arm. Probabilistic bisection keeps a posterior over where the change
is, updates it with each noisy answer, and samples at the posterior
median.

```
argus-mcp history --bisect lava_deaths --map dm4 --tick dedicated_fast \
                  --since 2026-08-15 --until 2026-08-22
```

Against the second dm4 lava step, which the detector dates to
2026-08-18 07:38, the posterior median lands at 2026-08-18 09:31 - the
right neighbourhood, a couple of hours out - and **does not settle**:
the 90 per cent interval still spans 35 tapes, so the run names the
date to spend the next tapes at rather than claiming an answer. On a
2.8 to 4.8 effect against a measured dm4 lava sigma of 1.7, that is the
correct amount of confidence.

Two limits worth stating, both from the issues that asked for this:

- **It assumes one change point.** Pointed at the whole dm2 stall
  series, which has three, it wanders and says so. Run the detector
  first and bisect one segment between two of its steps.
- **A position is queried at most once.** Horstein re-queries the
  median; doing that here would feed the same tapes in twice and
  manufacture confidence out of nothing, because the corpus holds
  exactly one answer per position. Re-querying means running fresh
  tapes, and the report names where.
