# The stand-in human

[Back to the lab workflow](lab-workflow.md) |
[Calibration protocol](specs/2026-11-15-stand-in-calibration.md)

The objective's threat goal, bot kills on a person per minute at skill 1, is
measured only in human sessions, and those are the scarcest evidence the lab
has. The stand-in is a puppet client that plays a deathmatch the way a person
roughly does, so the lab can ask the same question without one. It is an
calibrated instrument for screening the direction of threat changes on dm4.
Human sessions decide the threat verdict and measure how often bots kill the player.
See [calibration 3](#calibration-3-longer-exposure).

## Running it

```text
argus-mcp standin dm4 185 standin_dm4_a --skill 1
argus-mcp standin dm4 185 standin_dm4_b --route runs/shane_dm4_2026-11-14_ed8926.log --seed 2
```

It starts a wall-clock match, connects as `standin`, plays for the requested
seconds and prints what it did with the tape's human scorecard. The tape is an
ordinary human tape: the bots see and fight the stand-in like any player, and
its track, deaths and kills are in the log. It cannot use the fixed lab clock,
because it acts on the wall clock and would play at a sixth of the game's
speed.

## How it plays

- **Route.** It follows a route a human ran: the recording player's full-rate
  path from the session demo's track export (`runs/demos/<stem>.tracks.json`,
  about 70 samples a second), or the tape's 2 Hz human samples when there is
  no export. The default is the newest `runs/shane_<map>_*.log`. The 2 Hz
  route cut corners into dm4's pit lava in the first smoke test.
- **Getting back.** Knocked off the route, respawned or stuck, it rejoins at
  the nearest route point in clear sight, reaching it over the bots' own nav
  graph (walk and jump links). A straight line to the nearest point is not a
  way there: dm4 spawns a player in a walkway box whose nearest route points
  sit over a 48-unit step.
- **Sight and reaction.** It sees a bot only along a clear hull-0 line within
  1800 units, and fires once that bot has stayed in sight for 0.25 s.
- **Aim.** The view turns at most 540 degrees a second, closing 45 per cent
  of the error each 50 ms tick, plus a held offset (2.5 degrees deviation)
  re-rolled every 0.3 to 0.6 s. It fires inside 7 degrees.
- **Movement.** While fighting it circles the target, reversing every 1.6 to
  3.4 s (about 24 reversals a moving minute, inside the 18 to 26 measured for
  the human in six dm4 demos, #697), backs off inside rocket splash and
  closes from far away. It will not step where the floor 32 or 64 units ahead
  is lava or slime.
- **Weapons.** From its real inventory (svc_clientdata): rockets beyond
  180 units, the lightning gun inside 600, then the nailguns and shotguns.
- **Respawn.** It presses fire, as a player does.

The profile values are settings, not measurements of a person; `--reaction`
overrides the reaction time.

## Calibration

The [protocol](specs/2026-11-15-stand-in-calibration.md) was registered before
any calibration tape: dm4, build `cbc0176e8e8e`, bot skill 0 to 3, four
185 s matches each, the stand-in following the route of the latest dm4
session. Dose response passes when the Spearman correlation between bot skill
and bot kills on the stand-in per minute is at least 0.5 and the skill 3 minus
skill 0 difference has a 95 per cent interval clear of zero. Level matches
when its skill 1 mean lies within half to one and a half times Shane's mean
over his last four dm4 sessions (1.27 a minute). `tools/argus_standin_calibration.py`
applies the rule.

| Bot skill | Tapes | Bot kills on the stand-in a minute | SD |
| --- | --- | --- | --- |
| 0 | 4 | 0.95 | 0.68 |
| 1 | 4 | 1.19 | 1.23 |
| 2 | 4 | 1.43 | 1.23 |
| 3 | 4 | 1.11 | 0.84 |

Spearman 0.13; skill 3 minus skill 0 is +0.16 a minute (95 per cent interval
-1.18 to +1.50). **Dose response fails.** Level at skill 1 is 1.19 against
1.27, inside the band, but a level without a dose response means nothing: an
instrument that does not move when the bots get harder cannot say whether a
change made them more dangerous.

Why: how much fighting the stand-in gets into swamps the effect of bot skill.
Its ticks with a bot in sight ran from 0 to 2608 across the sixteen matches;
the skill 1 match with none spent the game stuck (121 detours over the graph
and no contact at all), and three more matches made over 100 detours. Its own
deaths to bots ran from 0 to 10 in one tier. Of its 77 deaths, 59 were to
bots, 17 to the world (lava, mostly knock-ins) and 1 its own rocket.

Counting note, found while analysing: a dedicated server sends obituaries to
clients and never writes them to its console, so an obituary-based count reads
zero on every stand-in tape. The calibration counts `ARGEVT ... death` lines,
taking a kill as a death whose killer is a bot by name. The brief's human
scorecard now counts the same way; it used to subtract only world deaths, which
credited the stand-in's own rocket suicides to the bots
([#844](https://github.com/saworbit/argus/issues/844)).

## Calibration 2: kills per minute in sight

The [second protocol](specs/2026-11-18-stand-in-calibration-2.md) was
registered before its tapes: the same dm4 design on build `9387e1e77737`,
stand-in seeds 5 to 8, and bot kills on the stand-in per minute in sight of a
bot (`argus_standin_calibration.py --measure sight`), sight rebuilt from each
0.5 s sample as a living bot within 1800u on a clear hull-0 line between the
eyes. The person's level on the same measure is 3.92 (his last four dm4
sessions, 3.05 to 5.50).

| Bot skill | Tapes | Bot kills on the stand-in a minute in sight | SD |
| --- | --- | --- | --- |
| 0 | 4 | 4.33 | 0.63 |
| 1 | 4 | 3.99 | 3.07 |
| 2 | 4 | 9.26 | 3.21 |
| 3 | 4 | 10.77 | 7.30 |

Spearman 0.58, past the 0.5 bar, but skill 3 minus skill 0 is +6.44 a minute
with a 95 per cent interval of -5.12 to +18.01, which spans zero. **Dose
response fails**, narrowly. Level at skill 1 is 3.99 against 3.92, inside the
band. The interval is wide because exposure is still thin: the matches spent
0.13 to 1.06 minutes in sight, and one skill 3 match recorded no kill in its
0.22 minutes. Read after the first calibration's verdict, its 16 tapes on the
same measure gave Spearman 0.60 and an interval clear of zero; that reading
was not registered and is not a pass.

## Calibration 3: longer exposure

The [third calibration](https://github.com/saworbit/argus/issues/842#issuecomment-7023289389)
kept the same replay, movement and aim profile, and sight measure. It used
build `1129a18536ba`, eight 360-second dm4 matches per skill, and fresh
stand-in seeds 9 to 16. The skill order rotated by seed. All 32 wall-clock
tapes passed map, build and cadence checks and met the three-second minimum
in sight.

| Bot skill | Tapes | Bot kills on the stand-in a minute in sight | SD |
| --- | --- | --- | --- |
| 0 | 8 | 4.33 | 2.34 |
| 1 | 8 | 7.33 | 3.74 |
| 2 | 8 | 10.05 | 4.23 |
| 3 | 8 | 9.57 | 2.62 |

Spearman was 0.58. Skill 3 minus skill 0 was +5.24 kills per minute in
sight, with a 95 per cent Welch interval of +2.57 to +7.90. **Dose response
passes** the registered rule. The skill 1 mean was 7.33 against the human
reference of 3.92, above its 1.96 to 5.88 band.

`argus_lab.py pyramid --through 5` may now plan a directional screen on dm4.
Use the same replay and sight measure for that screen. Human sessions
remain the evidence for the absolute rate of bot kills on the player and the
threat verdict.
[Per-tape readings and identities](../runs/standin-calibration-3.results.json).
