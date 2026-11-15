#!/usr/bin/env python3
"""Apply the fixed-clock validation criterion to two arms of tapes.

docs/specs/2026-11-15-fixed-clock-validation.md registered the question, the
design and this criterion before any validation tape existed. For each
metric, d is the fixed arm's mean minus the played arm's mean and the margin
is the larger of 30 per cent of the played mean and one event (30 per cent
alone for average speed):

  Equivalent    the 90 per cent Welch interval for d lies inside the margin
  Different     the 95 per cent Welch interval for d excludes zero
  Inconclusive  neither

A map is accepted when no metric reads Different and engagements, coverage
and goals read Equivalent. Tapes that are not listen class are excluded and
named. Metrics come from argus-mcp corpus (the Rust parser is the gate
definition); lava deaths are recounted from hull-0 contents when the BSP is
on hand, as the skeptic does.

usage:
  argus_clock_validation.py --map dm4 --played RUN... --fixed RUN... [--json]
  argus_clock_validation.py --map dm4 --played-glob 'fxval_played_dm4_r*' --fixed-glob 'fxval_fixed_dm4_s*'
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_lab  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
METRICS = ('stalls', 'engages', 'lava_deaths', 'world_deaths', 'freezes', 'cover', 'goals', 'deaths',
           'routefails', 'avg_speed')
REQUIRED = ('engages', 'cover', 'goals')
RELATIVE_ONLY = ('avg_speed',)


def betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Numerical Recipes)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > 1e-30 else 1e-30
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-12:
            break
    return h


def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * betacf(a, b, x) / a
    return 1.0 - bt * betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    tail = 0.5 * betai(df / 2.0, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def t_quantile(p, df):
    """Student t quantile by bisection on the CDF."""
    lo, hi = -100.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def welch(a, b, level):
    """Interval for mean(b) - mean(a) at a two-sided level."""
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va = statistics.variance(a) if len(a) > 1 else 0.0
    vb = statistics.variance(b) if len(b) > 1 else 0.0
    se2 = va / len(a) + vb / len(b)
    d = mb - ma
    if se2 == 0:
        return d, d, d
    df = se2 ** 2 / ((va / len(a)) ** 2 / max(len(a) - 1, 1) + (vb / len(b)) ** 2 / max(len(b) - 1, 1))
    q = t_quantile(1 - (1 - level) / 2, df)
    half = q * math.sqrt(se2)
    return d, d - half, d + half


def judge(played, fixed, metric):
    mean_p = statistics.fmean(played)
    margin = 0.3 * mean_p if metric in RELATIVE_ONLY else max(0.3 * mean_p, 1.0)
    d, lo90, hi90 = welch(played, fixed, 0.90)
    _, lo95, hi95 = welch(played, fixed, 0.95)
    if lo95 > 0 or hi95 < 0:
        verdict = 'different'
    elif -margin <= lo90 and hi90 <= margin:
        verdict = 'equivalent'
    else:
        verdict = 'inconclusive'
    return dict(played=mean_p, fixed=statistics.fmean(fixed), d=d, ci90=[lo90, hi90], ci95=[lo95, hi95],
                margin=margin, verdict=verdict, n_played=len(played), n_fixed=len(fixed))


def evaluate(root, mapname, played, fixed):
    rows, _ = argus_lab.corpus_rows(root, played + fixed, mapname)
    missing = [n for n in played + fixed if n not in rows]
    not_listen = [n for n in played + fixed if n in rows and rows[n].get('tick_class') != 'listen']
    keep_p = [n for n in played if n in rows and n not in not_listen]
    keep_f = [n for n in fixed if n in rows and n not in not_listen]
    lava = {n: argus_lab.hull0_lava(root, n, mapname) for n in keep_p + keep_f}
    lava_ok = all(v is not None for v in lava.values())
    results = {}
    for metric in METRICS:
        def values(names):
            if metric == 'lava_deaths' and lava_ok:
                return [float(lava[n]) for n in names]
            return [argus_lab.num(rows[n].get(metric)) for n in names]
        if len(keep_p) < 2 or len(keep_f) < 2:
            results[metric] = dict(verdict='unmeasurable: fewer than two tapes an arm')
            continue
        vp, vf = values(keep_p), values(keep_f)
        if any(v is None for v in vp + vf):
            # a metric the corpus does not carry is not measured, never zero
            results[metric] = dict(verdict='not measured: the corpus does not carry it')
            continue
        results[metric] = judge(vp, vf, metric)
    different = [m for m, r in results.items() if r.get('verdict') == 'different']
    short = [m for m in REQUIRED if results.get(m, {}).get('verdict') != 'equivalent']
    accepted = not different and not short
    clocks = {}
    for n in keep_p + keep_f:
        clock = argus_lab.argus_tape.tape_identity(argus_lab.read_text(Path(root) / 'runs' / f'{n}.log'))['clock']
        clocks[n] = f'fixed {clock["frame_us"] / 1000:g} ms' if clock and clock['kind'] == 'fixed' else 'realtime'
    return dict(map=mapname, played=keep_p, fixed=keep_f, missing=missing, not_listen=not_listen,
                clocks=dict(played=sorted({clocks[n] for n in keep_p}), fixed=sorted({clocks[n] for n in keep_f})),
                lava_rule='hull-0 contents' if lava_ok else 'corpus z rule', metrics=results,
                accepted=accepted, different=different, required_not_equivalent=short,
                limits=[m for m, r in results.items() if r.get('verdict') == 'inconclusive'])


def expand(root, names, pattern):
    if pattern:
        names = names + sorted(p.stem for p in (Path(root) / 'runs').glob(pattern + '.log'))
    return names


def report(rep, out=None):
    out = out or sys.stdout
    print(f'{rep["map"]}: {len(rep["played"])} played ({", ".join(rep["clocks"]["played"])}), '
          f'{len(rep["fixed"])} fixed ({", ".join(rep["clocks"]["fixed"])}) tapes; lava by {rep["lava_rule"]}',
          file=out)
    for key, label in (('missing', 'not parsed'), ('not_listen', 'excluded, not listen class')):
        if rep[key]:
            print(f'  {label}: {", ".join(rep[key])}', file=out)
    print('| Metric | Played | Fixed | Change | 90% interval | Margin | Reading |', file=out)
    print('| --- | --- | --- | --- | --- | --- | --- |', file=out)
    for metric, r in rep['metrics'].items():
        if 'd' not in r:
            print(f'| {metric} | - | - | - | - | - | {r["verdict"]} |', file=out)
            continue
        print(f'| {metric} | {r["played"]:.1f} | {r["fixed"]:.1f} | {r["d"]:+.1f} | '
              f'{r["ci90"][0]:+.1f} to {r["ci90"][1]:+.1f} | {r["margin"]:.1f} | {r["verdict"]} |', file=out)
    verdict = 'ACCEPTED' if rep['accepted'] else 'NOT ACCEPTED'
    why = []
    if rep['different']:
        why.append('different: ' + ', '.join(rep['different']))
    if rep['required_not_equivalent']:
        why.append('not shown equivalent: ' + ', '.join(rep['required_not_equivalent']))
    print(f'{verdict}' + (f' ({"; ".join(why)})' if why else '')
          + (f'; limits: {", ".join(rep["limits"])}' if rep['limits'] else ''), file=out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--map', required=True)
    ap.add_argument('--played', nargs='*', default=[])
    ap.add_argument('--fixed', nargs='*', default=[])
    ap.add_argument('--played-glob')
    ap.add_argument('--fixed-glob')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    root = Path(args.root)
    played = expand(root, args.played, args.played_glob)
    fixed = expand(root, args.fixed, args.fixed_glob)
    rep = evaluate(root, args.map, played, fixed)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        report(rep)
    return 0 if rep['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
