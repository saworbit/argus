"""Evaluate the pre-registered diagnostic cohort from authoritative native briefs.

This consumes JSON receipts, not ARGLOG. A confidence interval crossing a bound
is inconclusive, even when a difference test would be non-significant.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
# Student-t .95 quantile, df=7: two one-sided equivalence tests, alpha=.05.
T95_DF7 = 1.894578605061305
# scipy.stats.t.ppf(.95, 127), fixed before the independent larger cohort.
T95_DF127 = 1.6569403435420642


def interval(values, margin, pairs=8):
    assert pairs in (8, 128), 'unregistered sample size'
    assert len(values) == pairs and all(math.isfinite(v) for v in values), 'complete finite order-pairs required'
    mean = statistics.mean(values)
    critical = T95_DF7 if pairs == 8 else T95_DF127
    radius = critical * statistics.stdev(values) / math.sqrt(pairs)
    low, high = mean - radius, mean + radius
    return dict(n=pairs, mean=mean, ci90=[low, high], margin=margin,
                equivalent=low > -margin and high < margin)


def rate(row, key):
    totals = row['brief']['totals']
    seconds = totals['duration_sec']
    assert 58 <= seconds <= 64, 'different match exposure'
    return totals[key] * 60 / seconds


def frame_mean(row):
    windows = row['timing']
    assert len(windows) >= 9, 'incomplete timing exposure'
    return sum(w['mean_ms'] * w['frames'] for w in windows) / sum(w['frames'] for w in windows)


def frame_interval(differences, pairs=8):
    result = interval(differences, 1, pairs)
    result['rounded_value_ci90'] = result['ci90']
    # Each printed mean has up to .05 ms rounding error; an arm difference
    # has up to .1 ms. Do not report sub-format precision as physical precision.
    result['rounding_allowance_ms'] = .1
    low, high = result['ci90']
    result['ci90'] = [low - .1, high + .1]
    result['equivalent'] = result['ci90'][0] > -1 and result['ci90'][1] < 1
    return result


def evaluate(rows, pairs=8):
    assert pairs in (8, 128), 'unregistered sample size'
    assert len(rows) == pairs * 4, 'complete fixed cohort required'
    assert len({r['name'] for r in rows}) == pairs * 4, 'duplicate run'
    assert {r['mode'] for r in rows} == {'off', 'on'}
    for key in ('source_sha256', 'binary_sha256', 'cli_sha256'):
        assert len({r['identity'][key] for r in rows}) == 1, 'mixed ' + key
    result = {}
    for map_name in ('dm2', 'dm4'):
        selected = [r for r in rows if r['map'] == map_name]
        assert len(selected) == pairs * 2
        assert len({r['identity']['nav_sha256'] for r in selected}) == 1, 'mixed graph'
        paired_rows = []
        for repeat in range(1, pairs + 1):
            by_mode = {r['mode']: r for r in selected if r['repeat'] == repeat}
            assert len(by_mode) == 2, 'missing order-pair'
            paired_rows.append((by_mode['off'], by_mode['on']))
        goals = interval([rate(on, 'goals') - rate(off, 'goals') for off, on in paired_rows], 2, pairs)
        cadence = frame_interval([frame_mean(on) - frame_mean(off) for off, on in paired_rows], pairs)
        secondary = {}
        for key in ('grabs', 'acquisitions', 'engages', 'stalls', 'frags', 'lava_deaths', 'freezes'):
            diffs = [rate(on, key) - rate(off, key) for off, on in paired_rows]
            ci = interval(diffs, float('inf'), pairs)
            ci.pop('margin'); ci.pop('equivalent')
            secondary[key] = dict(off_mean=statistics.mean(rate(off, key) for off, _ in paired_rows),
                                  on_mean=statistics.mean(rate(on, key) for _, on in paired_rows), **ci)
        cpu = interval([1000 * (on['cpu_seconds'] / on['wall_seconds'] - off['cpu_seconds'] / off['wall_seconds'])
                        for off, on in paired_rows], float('inf'), pairs)
        cpu.pop('margin'); cpu.pop('equivalent')
        result[map_name] = dict(goals_per_minute=goals, frame_ms=cadence,
            secondary_per_minute=secondary, cpu_difference_ms_per_wall_second=cpu, modes={})
        for mode in ('off', 'on'):
            arm = [r for r in selected if r['mode'] == mode]
            windows = [w for r in arm for w in r['timing']]
            result[map_name]['modes'][mode] = dict(
                goals_per_minute=statistics.mean(rate(r, 'goals') for r in arm),
                goal_counts=[r['brief']['totals']['goals'] for r in arm],
                frame_ms=statistics.mean(frame_mean(r) for r in arm),
                over50_frames=sum(w['over50'] for w in windows),
                frames=sum(w['frames'] for w in windows),
                cpu_ms_per_wall_second=statistics.mean(r['cpu_seconds'] / r['wall_seconds'] * 1000 for r in arm),
                bytes_mean=statistics.mean(r['bytes'] for r in arm),
                native_tick_classes=sorted({r['brief']['totals']['tick_class'] for r in arm}))
    return dict(maps=result, primary_equivalent=all(r['goals_per_minute']['equivalent'] for r in result.values()),
                cadence_equivalent=all(r['frame_ms']['equivalent'] for r in result.values()),
                limitations=f'{pairs} independent launches per mode/map, paired by adjacent counterbalanced order, not identical random seeds. Student-t CI assumes approximately normal independent pair differences. Bounds concern completed-goal rate and mean frame time; secondary metrics and process CPU remain descriptive, not separately powered equivalence claims.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('receipts', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--pairs', type=int, choices=(8, 128), default=8)
    args = ap.parse_args()
    rows = json.loads(args.receipts.read_text())
    result = evaluate(rows, args.pairs)
    result['tapes'] = {r['name']: hashlib.sha256((ROOT / f"runs/{r['name']}.log").read_bytes()).hexdigest() for r in rows}
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'tapes'}, indent=2))


if __name__ == '__main__':
    main()
