# The stand-in human

[Back to the lab workflow](lab-workflow.md) |
[Calibration protocol](specs/2026-11-15-stand-in-calibration.md)

The objective's threat goal, bot kills on a person per minute at skill 1, is
measured only in human sessions, and those are the scarcest evidence the lab
has. The stand-in is a puppet client that plays a deathmatch the way a person
roughly does, so the lab can ask the same question without one. It is an
instrument with a calibration record, and **on the current record it may not
screen threat claims**: see [calibration](#calibration).

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

## What would fix it

Two things, either of which needs its own registered calibration
([#842](https://github.com/saworbit/argus/issues/842)):

- Navigation that keeps it in the game: the remaining stalls are on dm4's
  walkway steps and in corners the nav graph's nearest node cannot see.
- A measure that does not depend on how much it fought: bot kills per minute
  in sight of a bot, rather than per minute of match.

Until then `tools/lab_instruments.json` records it as failing dose response on
dm4, `argus_lab.py pyramid --through 5` does not plan it, and threat claims
still need a human session.
