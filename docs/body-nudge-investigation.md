# Same-floor body nudges

[#747](https://github.com/saworbit/argus/issues/747) tracked two failures left
in the anti-embed nudge after the [body-height repair](body-height-investigation.md).
That repair stopped players on other floors from triggering it. On the same
floor, `Argus_BodyBlockCheck` still had two faults:

- It accepted a destination from eleven point samples and then called
  `setorigin`, which never collides. On dm3 a three-unit nudge passed the
  samples while the player hull clipped the wall by a fraction of a unit.
- It separated the two bodies by 36 units along the line between them. Player
  hulls are square, so a diagonal offset of 36 units still leaves them
  overlapping by about 6.5 units on each axis.

## The repair

The nudge now scales the offset so one axis clears 36 units, which separates
two 32-unit hulls in every direction. For a grounded bot it then asks the
engine: after `setorigin`, a zero-step `walkmove` fails on any hull overlap or
missing floor, and a refused spot puts the bot back where it stood. An airborne
bot keeps the old placement, because the engine refuses `walkmove` for anything
off the ground. A legal three-unit nudge is unchanged.

`ARGUS <name> bodynudge moved` or `refused` records each nudge that reaches the
engine check, throttled to once every 2 s per bot.

## Physical controls

`tools/verify_body_nudge.py` places a real bot and a stationary player hull on
dm3, calls the production function once per case and checks the result with an
engine zero-step walk. It then runs a continuing route from the original pin
seat. The observer writes no movement, route or goal after setup.

| Source | Played | 100 ms |
|---|---|---|
| Frozen main 8922727 | Fails wall refusal and diagonal overlap | Same two failures |
| Repair | All ten checks pass, route in 1.0 s | All ten checks pass, route in 0.9 s |
| Repair without the engine check | Fails wall refusal only | Not run |
| Repair without axis separation | Fails diagonal overlap only | Not run |

No case needed a rescue. The body-height fixture still passes all its dm3 and
e1m6 checks at both cadences, including its unchanged same-floor nudge.

## Matched ordinary matches

The rule was written before any tape ran: reject on a native band rejection, an
engagement median outside the control band, or any under-fire freeze. Three
120 s tapes per arm on dm3 and dm4, skill 2, played rate, against a frozen copy
of main.

| Map | Stalls | Engagements | Lava | Under-fire freezes | Native verdict |
|---|---|---|---|---|---|
| dm3 | 10 to 10 | 11 to 11 | 0 to 0 | 0 to 0 | Parity |
| dm4 | 2 to 3 | 47 to 47 | 2 to 2 | 0 to 0 | Parity |

Medians, control to candidate. One candidate dm3 tape records an under-fire
rescue for Romero. That tape has no `bodynudge` marker, so the changed path
moved nothing there.

## Limits

The changed path reached the engine check only twice across the six candidate
tapes, so the matches show the repair costs nothing measurable. They do not
measure a benefit. The fixture is the proof of the two cases. Airborne bots are
out of scope. No installed binary changed and no human play is claimed.

Receipt: [runs/body-nudge-v2.results.json](../runs/body-nudge-v2.results.json),
with every raw tape listed by hash.
