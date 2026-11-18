# The fixed lab clock

[Back to the lab workflow](lab-workflow.md) |
[Validation protocol](specs/2026-11-15-fixed-clock-validation.md)

The lab's ordinary matches run on the wall clock: a 185 s match takes 185 s.
The fixed clock runs the same game faster than real time and makes it repeat
exactly. It is a screening instrument, validated per map: read
[where it agrees](#where-it-agrees-with-the-wall-clock) before trusting a
fixed tape.

**Current standing:** accepted on dm4, dm2, dm3 and e1m7 at 14.25 ms. Limits:
routefails everywhere; lava and world deaths on dm4, dm2 and e1m7; stalls on
dm4, dm3 and e1m7; deaths on dm3. Not validated on any other map.
`tools/lab_instruments.json` holds the record the lab reads.

## What it does

Three stock engine settings, no engine change:

- `host_framerate` pins every frame's length, so the simulation takes the same
  step whatever the wall clock did. The default is 14.25 ms, the wall-clock
  lab's own measured frame; see [why not 13.9](#why-dm4-differs-and-what-was-done-about-it).
- `sys_ticrate 0.001` with `host_maxfps 1000` lets the dedicated loop run a
  frame every millisecond instead of waiting for the next tick.
- `timelimit` makes the bots end the match at the requested game time, so
  every fixed tape is exactly as long as asked.

Measured on this rig: about 6.3 times real speed per engine, and four engines
side by side recorded 16.6 game seconds per wall second. A 20-seed, 185 s
ladder takes about three minutes on four lanes.

## It repeats

QuakeSpasm draws QC `random()` from the C library stream and calls `rand()`
once per main-loop pass "to keep the random time dependent". On the wall clock
that makes every match different. With one loop pass per frame (the reason for
`sys_ticrate 0.001` rather than 0, which busy-loops and draws thousands of
times between frames) the stream is the same every run, so a given progs, map
and seed produce the same match: two runs matched line for line over 1,115
telemetry lines, a seed run alone and the same seed run inside a four-lane
ladder matched over 916.

The seed chooses which repeat. The lab passes it as `saved4`, and `Argus_Init`
burns that many draws before the roster spawns (`ARGUS clock ... seed <n>` in
the tape). On any ordinary server `saved4` is 0 and the burn does nothing.
`argus-mcp seeds` walks seeds spaced far apart (`seed_for`), because adjacent
seeds shift the stream by one draw and can pick the same spawn pads. Seeds run
1 to 2000, which keeps the burn far inside id's original runaway limit of
100,000 QC statements a call. (The validation tapes below used an earlier walk
over 1 to 9973; each tape names its seed, and the build they ran capped at
10000.)

So a freeze or a death that happened once can be made to happen again:

```text
argus-mcp match dm4 185 replay_dm4 --seed 1292 --skill 2
```

replays the tape of seed 1292 exactly, as long as the build is the same (the
tape's `ARGUS build` line names it).

## Commands

```text
argus-mcp seeds <map> <count> <stem> [--duration 185] [--skill N] [--lanes 4] [--first 1] [--seed-list a,b]
argus-mcp match <map> <secs> <run> --seed N
```

and through the MCP server:

```text
match_run map=dm4 duration_sec=185 run_name=replay_dm4 seeds=[1292]
match_run map=dm4 duration_sec=185 run_name=fx_dm4 seeds=[1292,584,1875]
```

`seeds` runs on lanes with ports 26060 upward and names tapes
`<stem>_s<seed>`. A run that dies at network start-up is retried once;
engines launched in the same instant have been seen to lose one on Windows,
so lanes start 1.5 s apart. The stand-in human cannot use the fixed clock: it
acts on the wall clock and would play at a sixth of the game's speed.

`match_run seeds` (#853) is the same clock for an agent, with two
differences. It is refused on any map where `tools/lab_instruments.json` does
not record the fixed clock as accepted, while the CLI stays open on every map
because a validation has to record fixed tapes on a map first. And it runs
its seeds one after another on one engine, at most ten, because the server
tracks a single live engine for `match_stop` and shutdown: one seed returns
the ordinary result under `run_name`, several return the `seeds` report with
tapes named `<run_name>_s<seed>`. Both carry `fixed_clock`, which names the
clock, its frame, the seeds and the map's limits. A ladder costs about half
a minute of wall time per 185 s tape. The seeds above are the first three
that `seeds` walks.

Fixed tapes read the listen tick class (their telemetry gap is 0.5004 s), so
the tick-class guard does not tell them from wall-clock tapes. The `ARGUS
clock` line does: the skeptic, and since #852 the Rust `compare`, band and
`experiment` verdicts, report arms on different clocks as a confound.

`ARGUS_FIXED_FRAME` overrides the frame for an experiment, the way
`ARGUS_TICRATE` does for the wall clock. Every tape records its frame. The
skeptic and the Rust verdicts report arms that ran different clocks or frames
as a confound; the skeptic voids an arm that holds the same seed and build
twice, and the Rust verdicts refuse it.

## Where it agrees with the wall clock

The [protocol](specs/2026-11-15-fixed-clock-validation.md) was registered
before any validation tape: one build (`cbc0176e8e8e`), skill 2, 185 s, 10
wall-clock tapes against 20 fixed tapes per map, and a criterion per metric
(Equivalent when the 90 per cent Welch interval for the difference lies inside
30 per cent of the wall-clock mean or one event, Different when the 95 per
cent interval excludes zero). A map is accepted when nothing reads Different
and engagements, coverage and goals read Equivalent. Average speed was
registered but the corpus did not carry it then
([#843](https://github.com/saworbit/argus/issues/843)), so it was read on the
confirmation tapes after both verdicts, once the corpus carried it (below).
`tools/argus_clock_validation.py` applies the rule.

### dm2 at 13.9 ms: accepted

| Metric | Wall clock | Fixed | Change | 90% interval | Reading |
| --- | --- | --- | --- | --- | --- |
| stalls | 31.3 | 32.6 | +1.3 | -4.0 to +6.7 | equivalent |
| engagements | 30.7 | 34.0 | +3.3 | -1.7 to +8.4 | equivalent |
| lava deaths | 1.3 | 1.0 | -0.3 | -1.0 to +0.4 | inconclusive |
| freezes | 0.2 | 0.1 | -0.2 | -0.4 to +0.1 | equivalent |
| coverage | 432.0 | 463.8 | +31.8 | -2.1 to +65.7 | equivalent |
| goals | 10.5 | 11.3 | +0.8 | -1.1 to +2.8 | equivalent |
| deaths | 12.7 | 13.3 | +0.7 | -1.7 to +3.0 | equivalent |
| routefails | 5.7 | 6.1 | +0.4 | -1.5 to +2.3 | inconclusive |

At 13.9 ms dm2 was accepted. Lava deaths and routefails stayed limits there:
a claim about them still needs wall-clock tapes.

### dm4 at 13.9 ms: not accepted

| Metric | Wall clock | Fixed | Change | 90% interval | Reading |
| --- | --- | --- | --- | --- | --- |
| stalls | 4.9 | 7.3 | +2.4 | -0.3 to +5.1 | inconclusive |
| engagements | 69.2 | 69.8 | +0.6 | -6.3 to +7.6 | equivalent |
| lava deaths | 1.6 | 2.5 | +0.9 | +0.3 to +1.6 | **different** |
| freezes | 0.0 | 0.0 | 0.0 | 0.0 to 0.0 | equivalent |
| coverage | 353.8 | 361.5 | +7.7 | -10.2 to +25.6 | equivalent |
| goals | 23.3 | 21.0 | -2.3 | -5.8 to +1.2 | equivalent |
| deaths | 27.0 | 26.8 | -0.2 | -3.0 to +2.6 | equivalent |
| routefails | 0.4 | 2.0 | +1.6 | +0.6 to +2.7 | **different** |

On dm4 the fixed clock at 13.9 ms put more bots in the lava and failed more
routes than the wall clock did. Ten metrics were tested without correction for
multiplicity, and lava deaths and world deaths are the same events counted
twice, but the rule was registered as it is and the rule stands: on dm4 the
fixed clock does not stand in for wall-clock tapes.

### Why dm4 differs, and what was done about it

QC reads none of the clock settings, so the difference is in the clock
itself. The wall-clock lab does not run 13.9 ms frames: the loop waits at
least 13.9 ms and the operating system's sleep rounds that up, so its frames
average 14.25 ms (70.2 Hz, measured with `host_speeds`) and jitter around
that. An exploratory third arm, 20 fixed tapes at 14.25 ms on the same seeds,
was not registered and decides nothing on its own:

| Metric | Wall clock | Fixed 13.9 ms | Fixed 14.25 ms |
| --- | --- | --- | --- |
| stalls | 4.9 | 7.3 | 5.7 |
| lava deaths | 1.6 | 2.5 | 2.0 |
| routefails | 0.4 | 2.0 | 1.6 |

Against the wall clock, the 14.25 ms arm reads nothing Different and would
pass the rule (stalls, lava and routefails inconclusive). Against the
13.9 ms arm it reads nothing Different either. Frame length moves dm4 in the
direction of the gap, but these tapes cannot say it explains all of it, and
routefails stay higher in both fixed arms.

The human plays at 13.9 ms (host_maxfps 72 on a listen server); the wall-clock
lab, which every committed band was recorded on, runs 14.25. The fixed clock
screens for the lab, so the question is whether a 14.25 ms fixed frame agrees
with the lab on both maps when the seeds are fresh. That is registered below
and was run after the stand-in calibration, so the two never shared the CPU.

### Confirmation run (registered after the first result)

Registered 2026-11-15, after the results above and before any tape of it:
the same build, skill and length; fixed frame 14.25 ms; 20 fresh seeds per
map (`seed_for(21..=40)`); the same ten wall-clock tapes per map as the
control; the same criterion. If both maps are accepted, the fixed clock's
default frame becomes 14.25 ms, the lab's own rate. If either is not, the
default stays 13.9 ms and the fixed clock screens only on dm2.

### Confirmation result

Both maps accepted at 14.25 ms on fresh seeds (the earlier walk's indices 21
to 40, seeds 273 to 9949), against the same ten wall-clock tapes a map:

| Metric | dm4 wall | dm4 fixed | dm4 reading | dm2 wall | dm2 fixed | dm2 reading |
| --- | --- | --- | --- | --- | --- | --- |
| stalls | 4.9 | 6.2 | inconclusive | 31.3 | 33.2 | equivalent |
| engagements | 69.2 | 69.3 | equivalent | 30.7 | 31.1 | equivalent |
| lava deaths | 1.6 | 2.0 | inconclusive | 1.3 | 0.8 | inconclusive |
| freezes | 0.0 | 0.0 | equivalent | 0.2 | 0.2 | equivalent |
| coverage | 353.8 | 359.6 | equivalent | 432.0 | 425.9 | equivalent |
| goals | 23.3 | 23.9 | equivalent | 10.5 | 11.2 | equivalent |
| deaths | 27.0 | 26.1 | equivalent | 12.7 | 11.8 | equivalent |
| routefails | 0.4 | 0.9 | inconclusive | 5.7 | 6.2 | inconclusive |

Average speed, registered with the rest but read on 2026-11-18 after both
verdicts ([#863](https://github.com/saworbit/argus/issues/863)), because the
corpus did not carry it when they were made. Its margin is 30 per cent of the
wall-clock mean. It reads equivalent on both maps, so neither verdict and no
limit changes:

| Map | Wall clock | Fixed | Change | 90% interval | Margin | Reading |
| --- | --- | --- | --- | --- | --- | --- |
| dm4 | 212.2 | 209.4 | -2.9 | -6.7 to +1.0 | 63.7 | equivalent |
| dm2 | 182.9 | 183.7 | +0.7 | -9.5 to +11.0 | 54.9 | equivalent |

As registered, the default frame is now 14.25 ms. On both maps a fixed ladder
may screen a change for engagements, coverage, goals, deaths and freezes (and
stalls on dm2). Lava and world deaths and routefails, and stalls on dm4, stay
limits: a fixed ladder cannot settle them, and a claim about them still needs
wall-clock tapes. dm4's lava reads higher on the fixed clock in all three
fixed arms (2.5, 2.0, 2.0 against 1.6); no arm convicts it at 14.25 ms, but
nobody should read a dm4 lava result off a fixed ladder.

A fixed tape models the lab's wall clock, not a person: the human plays
13.9 ms frames on a listen server.

### Amendment 1: dm3 and e1m7 at 14.25 ms

The [amendment](specs/2026-11-18-fixed-clock-validation-amendment.md) was
registered before any of its fixed tapes ([#854](https://github.com/saworbit/argus/issues/854)).
Same question and criterion; the build is main at 89b9852 (`9387e1e77737`)
and the wall-clock arm is the played-rate control tapes of that build from
other ladders the same day, all recorded before the amendment and some of
their totals already read. That is weaker than a control recorded for the
validation itself. The fixed arm is 20 fresh seeds a map, `seed_for(41..=60)`.

| Metric | dm3 wall | dm3 fixed | dm3 reading | e1m7 wall | e1m7 fixed | e1m7 reading |
| --- | --- | --- | --- | --- | --- | --- |
| stalls | 20.8 | 19.9 | inconclusive | 2.1 | 1.5 | inconclusive |
| engagements | 19.7 | 19.1 | equivalent | 95.3 | 95.0 | equivalent |
| lava deaths | 0.0 | 0.0 | equivalent | 1.3 | 0.9 | inconclusive |
| world deaths | 0.0 | 0.0 | equivalent | 1.3 | 0.9 | inconclusive |
| freezes | 0.0 | 0.0 | equivalent | 0.2 | 0.1 | equivalent |
| coverage | 515.1 | 502.8 | equivalent | 386.2 | 393.8 | equivalent |
| goals | 23.1 | 24.8 | equivalent | 22.8 | 23.1 | equivalent |
| deaths | 6.2 | 6.8 | inconclusive | 34.7 | 34.0 | equivalent |
| routefails | 3.4 | 2.6 | inconclusive | 3.3 | 2.8 | inconclusive |
| average speed | 196.0 | 195.9 | equivalent | 213.0 | 208.6 | equivalent |

Both maps are accepted: nothing reads different, and engagements, coverage
and goals read equivalent. dm3 had 11 wall-clock tapes and 20 fixed; e1m7 had
13 and 19. dm3's lava reads equivalent only because neither arm had a lava
death, so it says nothing about lava there; treat it as untested rather than
trusted.

One e1m7 fixed tape, seed 250, was excluded as outside the listen tick class.
The class is read from the mean gap between a bot's half-second samples, and
the listen boundary is 0.5135 s. At a 14.25 ms frame the telemetry fires
every 36 frames, 0.513 s, every time, and the one-decimal time stamps scatter
the measured mean around that: seed 250 read 0.5132 and seed 125 read 0.5135.
Fixed tapes can fall either side of the boundary by chance
([#901](https://github.com/saworbit/argus/issues/901)). The verdict does not
depend on that tape.

## Evidence

Played arm: `runs/fxval_played_dm4_r1` to `r10`, `runs/fxval_played_dm2_r1` to
`r10`. Fixed arms: `runs/fxval_fixed_<map>_s<seed>` (13.9 ms),
`runs/fxval_fixed1425_dm4_s<seed>` (exploratory 14.25 ms) and
`runs/fxconf_fixed1425_<map>_s<seed>` (the confirmation). Reproduce a reading
with `python tools/argus_clock_validation.py --map dm4 --played-glob
'fxval_played_dm4_r*' --fixed-glob 'fxconf_fixed1425_dm4_s*'`.

Amendment 1: `runs/fxval2_played_dm3_<ladder>_ctl_r<n>` and
`runs/fxval2_played_e1m7_<ladder>_ctl_r<n>` are the control tapes the
amendment names, copied under these names unchanged (`study_sw761d3_ctl_r1`
is `fxval2_played_dm3_sw761d3_ctl_r1`, and so on), and
`runs/fxval2_fixed_<map>_s<seed>` the fixed arm. Reproduce with
`python tools/argus_clock_validation.py --map dm3 --played-glob
'fxval2_played_dm3_*' --fixed-glob 'fxval2_fixed_dm3_s*'`.

## What it cannot say

- Anything a human does: the stand-in and every session run on the wall
  clock.
- A ship decision: a candidate that fails a fixed screen need not spend
  wall-clock tapes, but one that passes still owes them.
- A metric listed as a limit for its map, and any map not validated here.
