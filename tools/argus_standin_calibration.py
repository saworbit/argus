#!/usr/bin/env python3
"""Apply the stand-in calibration criterion to a set of stand-in tapes.

docs/specs/2026-11-15-stand-in-calibration.md registered the design and this
criterion before any calibration tape existed:

  Dose response  the Spearman rank correlation between bot skill and bot kills
                 on the stand-in per minute, over every tape, is at least 0.5,
                 and the 95 per cent Welch interval for (top skill mean minus
                 bottom skill mean) excludes zero.
  Level          the stand-in's mean at the calibration skill lies within half
                 to one and a half times the person's mean (--person-mean).

Tapes are named `<stem>_k<skill>_<seed>`. Kill counts come from the tape's
ARGEVT death lines: a kill on the stand-in is a death whose killer is a bot
by name, so its own suicides and world deaths credit nobody.

--measure sight (#842) divides the kills by the minutes the stand-in spent in
sight of a living bot instead of by the minutes of match. How much fighting a
match gave the stand-in swamped the skill effect in the first calibration
(0 to 2608 ticks in sight between matches). Sight is rebuilt from the tape:
at each sample the stand-in counts as in sight when a living bot stands within
1800u (the stand-in's own sight range) with a clear hull-0 line between their
eyes (origin + 22). It needs maps_local/<map>.bsp (ARGUS_MAPS names another
folder). A match with under 3 s in sight carries no rate and is left out.

usage:
  argus_standin_calibration.py --glob 'standin_cal_dm4_k*' --person-mean 1.27 [--skill 1] [--json]
  argus_standin_calibration.py --glob 'standin_cal2_dm4_k*' --measure sight --map dm4 --person-mean 1.27
"""
import argparse
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_clock_validation  # noqa: E402
import argus_tape  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'_k(\d)_(\d+)$')


def ranks(values):
    """Average ranks, ties sharing the mean of their positions (1-based)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def tape_rates(path):
    """Bot kills on the human track and its kills on bots, per minute of tape.

    Counted from the ARGEVT death lines, not obituaries: a dedicated server
    sends obituaries to clients and never writes them to its own console, so
    an obituary count reads zero on every stand-in tape. A kill is a death
    whose killer is a bot by name, so the stand-in's own rocket suicides and
    world deaths credit nobody. Minutes are the span of the tape's samples.
    """
    tape = argus_tape.parse_tape(Path(path).read_text(encoding='utf-8', errors='replace'))
    bots, humans, _ = argus_tape.track_names(tape.samples, tape.events)
    if not humans:
        return None
    human = max(humans, key=lambda n: len(tape.samples.get(n, [])))
    times = [s['t'] for rows in tape.samples.values() for s in rows]
    minutes = (max(times) - min(times)) / 60 if times else 0.0
    if minutes <= 0:
        return None
    bot_set = set(bots)
    deaths = list(argus_tape.deaths(tape.events))
    bot_kills = sum(1 for d in deaths if d[1] == human and d[2] in bot_set)
    kills = sum(1 for d in deaths if d[1] in bot_set and d[2] == human)
    return dict(minutes=minutes, bot_kills_pm=bot_kills / minutes, kills_pm=kills / minutes, human=human,
                bot_kills=bot_kills, kills=kills)


SIGHT_RANGE = 1800.0
SIGHT_MIN_MINUTES = 0.05


def _clear(contents, a, b):
    d = math.dist(a, b)
    n = max(1, int(d // 16))
    for i in range(1, n):
        f = i / n
        if contents(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f) == -2:
            return False
    return True


def sight_minutes(tape, human, contents):
    """Minutes the human track spent alive with a living bot in clear sight."""
    snaps = {}
    for name, rows in tape.samples.items():
        for s in rows:
            snaps.setdefault(round(s['t'] * 2) / 2, {})[name] = ((s['x'], s['y'], s['z'] + 22), s['hp'])
    times = sorted(snaps)
    if len(times) < 2:
        return 0.0
    step = statistics.median(b - a for a, b in zip(times, times[1:]))
    seen = 0.0
    for t in times:
        snap = snaps[t]
        if human not in snap or snap[human][1] <= 0:
            continue
        me = snap[human][0]
        if any(n != human and hp > 0 and math.dist(p, me) <= SIGHT_RANGE and _clear(contents, p, me)
               for n, (p, hp) in snap.items()):
            seen += step
    return seen / 60


def evaluate(root, pattern, person_mean, skill=1, measure='match', contents=None):
    rows = []
    for path in sorted((Path(root) / 'runs').glob(pattern + '.log')):
        m = NAME.search(path.stem)
        if not m:
            continue
        rates = tape_rates(path)
        if rates is None:
            continue
        if measure == 'sight':
            tape = argus_tape.parse_tape(Path(path).read_text(encoding='utf-8', errors='replace'))
            rates['sight_minutes'] = sight_minutes(tape, rates['human'], contents)
            if rates['sight_minutes'] < SIGHT_MIN_MINUTES:
                continue
            rates['bot_kills_pm'] = rates['bot_kills'] / rates['sight_minutes']
        rows.append(dict(run=path.stem, skill=int(m[1]), seed=int(m[2]), **rates))
    if len(rows) < 4:
        return dict(rows=rows, error='fewer than four tapes')
    skills = sorted({r['skill'] for r in rows})
    by = {k: [r['bot_kills_pm'] for r in rows if r['skill'] == k] for k in skills}
    rho = spearman([r['skill'] for r in rows], [r['bot_kills_pm'] for r in rows])
    lo_k, hi_k = skills[0], skills[-1]
    d, lo95, hi95 = argus_clock_validation.welch(by[lo_k], by[hi_k], 0.95)
    dose = rho >= 0.5 and (lo95 > 0 or hi95 < 0) and d > 0
    level_mean = statistics.fmean(by[skill]) if by.get(skill) else None
    level = None if level_mean is None else 0.5 * person_mean <= level_mean <= 1.5 * person_mean
    return dict(rows=rows, per_skill={k: dict(n=len(v), mean=statistics.fmean(v),
                                              sd=statistics.stdev(v) if len(v) > 1 else 0.0) for k, v in by.items()},
                spearman=rho, top_minus_bottom=dict(d=d, ci95=[lo95, hi95], skills=[lo_k, hi_k]),
                dose_response=dose, level_skill=skill, level_mean=level_mean, person_mean=person_mean,
                level_band=[0.5 * person_mean, 1.5 * person_mean], level=level, measure=measure)


def report(rep, out=None):
    out = out or sys.stdout
    if 'error' in rep:
        print(rep['error'], file=out)
        return
    unit = 'minute in sight' if rep.get('measure') == 'sight' else 'minute'
    print(f'| Bot skill | Tapes | Bot kills on the stand-in a {unit} | SD |', file=out)
    print('| --- | --- | --- | --- |', file=out)
    for k, v in rep['per_skill'].items():
        print(f'| {k} | {v["n"]} | {v["mean"]:.2f} | {v["sd"]:.2f} |', file=out)
    t = rep['top_minus_bottom']
    print(f'Spearman {rep["spearman"]:.2f}; skill {t["skills"][1]} minus skill {t["skills"][0]}: '
          f'{t["d"]:+.2f} a minute (95% {t["ci95"][0]:+.2f} to {t["ci95"][1]:+.2f})', file=out)
    print(f'Dose response: {"PASSES" if rep["dose_response"] else "FAILS"}', file=out)
    if rep['level_mean'] is not None:
        print(f'Level at skill {rep["level_skill"]}: {rep["level_mean"]:.2f} a minute against the person\'s '
              f'{rep["person_mean"]:.2f} (band {rep["level_band"][0]:.2f} to {rep["level_band"][1]:.2f}): '
              f'{"matches" if rep["level"] else "does not match"}', file=out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--glob', required=True, help='run-name pattern under runs/, e.g. standin_cal_dm4_k*')
    ap.add_argument('--person-mean', type=float, required=True,
                    help="the person's bot kills a minute at the calibration skill")
    ap.add_argument('--skill', type=int, default=1)
    ap.add_argument('--measure', choices=('match', 'sight'), default='match',
                    help='divide kills by minutes of match (the first protocol) or minutes in sight of a bot')
    ap.add_argument('--map', default='dm4', help='the map whose BSP rebuilds sight (--measure sight)')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    contents = None
    if args.measure == 'sight':
        from argus_bsp import load_classifier
        maps = Path(os.environ.get('ARGUS_MAPS', Path(args.root) / 'maps_local'))
        bsp = maps / f'{args.map}.bsp'
        if not bsp.is_file():
            print(f'missing {bsp}: --measure sight rebuilds line of sight from the map', file=sys.stderr)
            return 2
        contents = load_classifier(bsp)
    rep = evaluate(Path(args.root), args.glob, args.person_mean, args.skill, args.measure, contents)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        report(rep)
    return 0 if rep.get('dose_response') else 1


if __name__ == '__main__':
    sys.exit(main())
