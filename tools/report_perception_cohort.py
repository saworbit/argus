"""Fixed dm2 engagement holdout: native receipts only, never ARGLOG metrics."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics

import numpy as np
from scipy import stats

from run_behaviour_equivalence import ROOT, TIMING, timing

PAIRS = 128
MARGIN = 2.0
BLOCK = 4
BOOTSTRAPS = 50000
SEED = 20261025


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schedule(prefix):
    return [(f'{prefix}_dm2_{mode}{repeat:03}', mode, repeat)
            for repeat in range(1, PAIRS + 1)
            for mode in (('control', 'candidate') if repeat % 2 else ('candidate', 'control'))]


def ci(values, confidence):
    values = np.asarray(values, dtype=float)
    assert values.shape == (PAIRS,) and np.isfinite(values).all()
    mean = float(values.mean())
    se = float(values.std(ddof=1) / math.sqrt(PAIRS))
    radius = float(stats.t.ppf((1 + confidence) / 2, PAIRS - 1)) * se
    return [mean - radius, mean + radius]


def block_intervals(differences):
    # Resample consecutive, non-overlapping four-pair blocks. Resampling the
    # block mean preserves the mean of all 128 pairs, including both orders.
    blocks = np.asarray(differences).reshape(-1, BLOCK).mean(axis=1)
    rng = np.random.default_rng(SEED)
    means = blocks[rng.integers(0, len(blocks), size=(BOOTSTRAPS, len(blocks)))].mean(axis=1)
    return dict(ci90=np.quantile(means, [.05, .95]).tolist(),
                ci95=np.quantile(means, [.025, .975]).tolist())


def evaluate(control, candidate):
    control, candidate = np.asarray(control, dtype=float), np.asarray(candidate, dtype=float)
    assert control.shape == candidate.shape == (PAIRS,)
    assert np.isfinite(control).all() and np.isfinite(candidate).all()
    differences = candidate - control
    c90, c95 = ci(differences, .9), ci(differences, .95)
    blocks = block_intervals(differences)
    regression = c95[1] < 0 and blocks['ci95'][1] < 0
    equivalent = c90[0] > -MARGIN and c90[1] < MARGIN
    robust_equivalent = blocks['ci90'][0] > -MARGIN and blocks['ci90'][1] < MARGIN
    improvement = c95[0] > 0 and blocks['ci95'][0] > 0
    if regression:
        verdict = 'reproducible engagement-rate reduction'
    elif c95[1] < 0:
        verdict = 'paired-test reduction; block sensitivity inconclusive'
    elif equivalent and robust_equivalent:
        verdict = 'practically equivalent; earlier drop consistent with sampling noise'
    elif improvement:
        verdict = 'reproducible increase; earlier drop not reproduced'
    else:
        verdict = 'inconclusive'
    ratio = float(candidate.mean() / control.mean()) if control.mean() > 0 else None
    contrast = candidate - .65 * control
    # A one-sided 95% non-inferiority interval has the same endpoint as
    # the two-sided 90% interval. This preserves the existing dm2 65% floor.
    floor_ci = ci(contrast, .9)
    return dict(n=PAIRS, control_mean=float(control.mean()), candidate_mean=float(candidate.mean()),
        difference_mean=float(differences.mean()), paired_sd=float(differences.std(ddof=1)),
        ci90=c90, ci95=c95, block_bootstrap=blocks,
        tost_equivalent=equivalent, block_equivalent=robust_equivalent,
        regression_confirmed=regression, verdict=verdict,
        retention_ratio=ratio, existing_65pct_floor=dict(contrast_ci90=floor_ci,
            noninferior=floor_ci[0] > 0, collapse_confirmed=floor_ci[1] < 0))


def paired(rows, prefix):
    assert [(r['name'], r['mode'], r['repeat']) for r in rows] == schedule(prefix), 'incomplete, duplicate or reordered cohort'
    by_name = {r['name']: r for r in rows}
    return [(by_name[f'{prefix}_dm2_control{i:03}'], by_name[f'{prefix}_dm2_candidate{i:03}'])
            for i in range(1, PAIRS + 1)]


def rate(row, key):
    totals = row['brief']['totals']
    assert 58 <= totals['duration_sec'] <= 64
    return totals[key] * 60 / totals['duration_sec']


def audit(protocol_path):
    p = json.loads(protocol_path.read_text())
    assert p['pairs'] == PAIRS and p['seconds'] == 60 and p['skill'] == 1
    assert p['engagement_margin_per_minute'] == MARGIN
    out = ROOT / p['output']
    protocol_sha = digest(protocol_path)
    assert (out / 'protocol.sha256').read_text().strip() == protocol_sha
    execution = json.loads((out / 'execution.json').read_text())
    assert execution['status'] == 'complete' and execution['restored_sha256'] == p['shipped_sha256']
    assert execution['protocol_sha256'] == protocol_sha
    for path, expected in p['code_sha256'].items():
        assert digest(ROOT / path) == expected
    for path, expected in p['resources_sha256'].items():
        assert digest(ROOT / path) == expected
    rows = json.loads((out / 'receipts.json').read_text())
    pairs = paired(rows, p['prefix'])
    for row in rows:
        assert row['protocol_sha256'] == protocol_sha
        assert row['identity'] == dict(p['identity'], binary_sha256=p['binaries'][row['mode']]['sha256'])
        assert row['executed_source_sha256'] == p['binaries'][row['mode']]['source_sha256']
        assert row['brief']['map'] == 'dm2' and row['brief']['totals']['tick_class'] == 'listen'
        assert row['brief']['lab_identity']['authoritative']
        raw = ROOT / f"runs/{row['name']}.log"
        assert digest(raw) == row['raw_sha256']
        text = raw.read_text(errors='replace')
        assert not any(s in text for s in ('BHVFIX ', 'PERFIX ', 'TACFIX begin', 'BHVRPL ', 'BHVDBG ', 'Host_Error', 'Program error', 'runaway loop error'))
        assert timing(text) == row['timing']
        assert not any('WRONG MAP' in f or 'CONTROLLED FIXTURE' in f for f in row['brief']['flags'])
        assert dt.datetime.fromisoformat(p['registered_utc']) < dt.datetime.fromisoformat(row['started_utc']) < dt.datetime.fromisoformat(row['stopped_utc'])
        assert row['valid']
    for path in p['protected_binaries']:
        assert digest(ROOT / path) == p['shipped_sha256']
    control = [rate(c, 'engages') for c, _ in pairs]
    candidate = [rate(t, 'engages') for _, t in pairs]
    result = evaluate(control, candidate)
    secondary = {}
    for key in ('goals', 'frags', 'deaths', 'stalls', 'lava_deaths', 'freezes', 'acquisitions', 'grabs'):
        differences = [rate(t, key) - rate(c, key) for c, t in pairs]
        secondary[key] = dict(control_mean=statistics.mean(rate(c, key) for c, _ in pairs),
            candidate_mean=statistics.mean(rate(t, key) for _, t in pairs),
            delta=statistics.mean(differences), descriptive_ci95=ci(differences, .95))
    order = {}
    for parity, label in ((1, 'control_first'), (0, 'candidate_first')):
        selected = [(c, t) for c, t in pairs if c['repeat'] % 2 == parity]
        order[label] = dict(n=len(selected), delta=statistics.mean(rate(t, 'engages') - rate(c, 'engages') for c, t in selected))
    def frame(row):
        windows = row['timing']
        return sum(w['mean_ms'] * w['frames'] for w in windows) / sum(w['frames'] for w in windows)
    cadence = [frame(t) - frame(c) for c, t in pairs]
    cadence_info = dict(delta_ms=statistics.mean(cadence), ci90_with_rounding=[ci(cadence, .9)[0] - .1, ci(cadence, .9)[1] + .1])
    cpu = [1000 * (t['cpu_seconds'] / t['wall_seconds'] - c['cpu_seconds'] / c['wall_seconds']) for c, t in pairs]
    cadence_info['cpu_delta_ms_per_wall_second'] = statistics.mean(cpu)
    cadence_info['cpu_descriptive_ci95'] = ci(cpu, .95)
    tails = {}
    for mode in ('control', 'candidate'):
        selected = [r for r in rows if r['mode'] == mode]
        windows = [tuple(map(float, w)) for r in selected
                   for w in TIMING.findall((ROOT / f"runs/{r['name']}.log").read_text(errors='replace'))]
        tails[mode] = dict(complete_windows=len(windows), frames=sum(w[1] for w in windows),
            over20=sum(w[5] for w in windows), over50=sum(w[6] for w in windows),
            max_ms=max(w[4] for w in windows), tape_bytes=sum(r['bytes'] for r in selected))
    result.update(protocol=p, protocol_sha256=protocol_sha, execution=execution,
        native_receipts_sha256=digest(out / 'receipts.json'), secondary_per_minute=secondary,
        order_sensitivity=order, cadence=cadence_info, all_complete_window_tails=tails,
        tapes={r['name']: dict(sha256=r['raw_sha256'], identity=r['identity'],
            totals=r['brief']['totals'], flags=r['brief']['flags']) for r in rows},
        limitations='Engage events mark acquisition, not shots, damage or human skill. Adjacent independent launches share order blocks, not identical random seeds. Paired t assumptions and four-pair block bootstrap are both reported. Only dm2 skill1 one-minute listen-server sessions tested. No pooling with pilot or optional stopping. No deployment or further perception changes.')
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('protocol', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    result = audit(args.protocol)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('tapes', 'protocol')}, indent=2))
