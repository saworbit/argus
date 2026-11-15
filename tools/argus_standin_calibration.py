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

usage:
  argus_standin_calibration.py --glob 'standin_cal_dm4_k*' --person-mean 1.27 [--skill 1] [--json]
"""
import argparse
import json
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


def evaluate(root, pattern, person_mean, skill=1):
    rows = []
    for path in sorted((Path(root) / 'runs').glob(pattern + '.log')):
        m = NAME.search(path.stem)
        if not m:
            continue
        rates = tape_rates(path)
        if rates is None:
            continue
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
                level_band=[0.5 * person_mean, 1.5 * person_mean], level=level)


def report(rep, out=None):
    out = out or sys.stdout
    if 'error' in rep:
        print(rep['error'], file=out)
        return
    print('| Bot skill | Tapes | Bot kills on the stand-in a minute | SD |', file=out)
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
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    rep = evaluate(Path(args.root), args.glob, args.person_mean, args.skill)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        report(rep)
    return 0 if rep.get('dose_response') else 1


if __name__ == '__main__':
    sys.exit(main())
