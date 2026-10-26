"""Confirmatory dm2 lava holdout; native receipts only, no ARGLOG metrics."""
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

PAIRS = 256
HARM_MARGIN = .10
BLOCK = 4
BOOTSTRAPS = 50000
SEED = 20261026
MIN_EVENTS = 20


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schedule(prefix):
    return [(f'{prefix}_dm2_{mode}{i:03}', mode, i)
            for i in range(1, PAIRS + 1)
            for mode in (('control', 'candidate') if i % 2 else ('candidate', 'control'))]


def ci(values, confidence):
    x = np.asarray(values, dtype=float)
    assert x.shape == (PAIRS,) and np.isfinite(x).all()
    radius = float(stats.t.ppf((1 + confidence) / 2, PAIRS - 1)) * float(x.std(ddof=1)) / math.sqrt(PAIRS)
    return [float(x.mean()) - radius, float(x.mean()) + radius]


def block_intervals(differences):
    blocks = np.asarray(differences).reshape(-1, BLOCK).mean(axis=1)
    rng = np.random.default_rng(SEED)
    means = blocks[rng.integers(0, len(blocks), size=(BOOTSTRAPS, len(blocks)))].mean(axis=1)
    return dict(ci90=np.quantile(means, [.05, .95]).tolist(),
                ci95=np.quantile(means, [.025, .975]).tolist())


def exact_poisson_support(control, candidate, control_minutes, candidate_minutes):
    assert control >= 0 and candidate >= 0 and control_minutes > 0 and candidate_minutes > 0
    total = control + candidate
    if not total:
        return dict(rate_ratio=None, ci95=[0., None], pvalue=None,
                    assumption='Independent Poisson support check; no events, unbounded ratio')
    test = stats.binomtest(candidate, total, candidate_minutes / (candidate_minutes + control_minutes))
    bounds = test.proportion_ci(.95, method='exact')
    ratio = candidate / control * control_minutes / candidate_minutes if control else None
    convert = lambda p: p / (1 - p) * control_minutes / candidate_minutes if p < 1 else None
    return dict(rate_ratio=ratio, ci95=[convert(bounds.low), convert(bounds.high)],
        pvalue=float(test.pvalue), assumption='Exact conditional independent-Poisson check; ignores pair/block dependence, not the primary decision')


def evaluate(control_counts, candidate_counts, control_seconds, candidate_seconds):
    arrays = [np.asarray(x, dtype=float) for x in (control_counts, candidate_counts, control_seconds, candidate_seconds)]
    assert all(x.shape == (PAIRS,) and np.isfinite(x).all() for x in arrays)
    a, b, sa, sb = arrays
    assert (a >= 0).all() and (b >= 0).all() and np.equal(a, np.floor(a)).all() and np.equal(b, np.floor(b)).all()
    assert ((sa >= 58) & (sa <= 64) & (sb >= 58) & (sb <= 64)).all()
    control, candidate = a * 60 / sa, b * 60 / sb
    differences = candidate - control
    c90, c95 = ci(differences, .9), ci(differences, .95)
    blocks = block_intervals(differences)
    adequate = int(a.sum() + b.sum()) >= MIN_EVENTS
    regression = adequate and c95[0] > 0 and blocks['ci95'][0] > 0
    noninferior = adequate and c90[1] < HARM_MARGIN and blocks['ci90'][1] < HARM_MARGIN
    decrease = adequate and c95[1] < 0 and blocks['ci95'][1] < 0
    if not adequate:
        verdict = 'inconclusive: insufficient pooled events for paired inference'
    elif regression:
        verdict = 'confirmed lava-death rate regression'
    elif c95[0] > 0:
        verdict = 'paired-test increase; block sensitivity inconclusive'
    elif decrease:
        verdict = 'reproducible decrease; earlier increase not reproduced'
    elif noninferior:
        verdict = 'practical non-inferiority; earlier increase consistent with sampling noise'
    else:
        verdict = 'inconclusive'
    return dict(n=PAIRS, control_mean=float(control.mean()), candidate_mean=float(candidate.mean()),
        difference_mean=float(differences.mean()), paired_sd=float(differences.std(ddof=1)),
        ci90=c90, ci95=c95, block_bootstrap=blocks, harm_margin_per_minute=HARM_MARGIN,
        adequate_pooled_events=adequate, regression_confirmed=bool(regression),
        practical_noninferiority=bool(noninferior), verdict=verdict,
        totals=dict(control=int(a.sum()), candidate=int(b.sum())),
        affected_matches=dict(control=int(np.count_nonzero(a)), candidate=int(np.count_nonzero(b))),
        poisson_support=exact_poisson_support(int(a.sum()), int(b.sum()), float(sa.sum()/60), float(sb.sum()/60)))


def paired(rows, prefix):
    assert [(r['name'], r['mode'], r['repeat']) for r in rows] == schedule(prefix), 'incomplete, duplicate or reordered cohort'
    by_name = {r['name']: r for r in rows}
    return [(by_name[f'{prefix}_dm2_control{i:03}'], by_name[f'{prefix}_dm2_candidate{i:03}']) for i in range(1, PAIRS + 1)]


def rate(row, key):
    totals = row['brief']['totals']
    assert 58 <= totals['duration_sec'] <= 64
    return totals[key] * 60 / totals['duration_sec']


def audit(path):
    p = json.loads(path.read_text()); out = ROOT / p['output']; sha = digest(path)
    assert p['pairs'] == PAIRS and p['seconds'] == 60 and p['skill'] == 1
    assert p['harm_margin_per_minute'] == HARM_MARGIN
    assert (out / 'protocol.sha256').read_text().strip() == sha
    execution = json.loads((out / 'execution.json').read_text())
    assert execution['status'] == 'complete' and execution['completed'] == 2 * PAIRS
    assert execution['restored_sha256'] == p['shipped_sha256'] and execution['protocol_sha256'] == sha
    for relative, expected in {**p['code_sha256'], **p['resources_sha256']}.items():
        assert digest(ROOT / relative) == expected
    rows = json.loads((out / 'receipts.json').read_text()); pairs = paired(rows, p['prefix'])
    for row in rows:
        assert row['protocol_sha256'] == sha
        assert row['identity'] == dict(p['identity'], binary_sha256=p['binaries'][row['mode']]['sha256'])
        assert row['executed_source_sha256'] == p['binaries'][row['mode']]['source_sha256']
        assert row['brief']['map'] == 'dm2' and row['brief']['totals']['tick_class'] == 'listen'
        assert row['brief']['totals']['lava_rule'] == 'contents'
        assert row['brief']['lab_identity']['authoritative'] and row['valid']
        raw = ROOT / f"runs/{row['name']}.log"; assert digest(raw) == row['raw_sha256']
        text = raw.read_text(errors='replace'); assert timing(text) == row['timing']
        assert not any(s in text for s in ('BHVFIX ', 'PERFIX ', 'TACFIX begin', 'BHVRPL ', 'BHVDBG ', 'Host_Error', 'Program error', 'runaway loop error'))
        assert not any('WRONG MAP' in f or 'CONTROLLED FIXTURE' in f for f in row['brief']['flags'])
        assert dt.datetime.fromisoformat(p['registered_utc']) < dt.datetime.fromisoformat(row['started_utc']) < dt.datetime.fromisoformat(row['stopped_utc'])
    for relative in p['protected_binaries']:
        assert digest(ROOT / relative) == p['shipped_sha256']
    counts = lambda mode: [r[0 if mode == 'control' else 1]['brief']['totals']['lava_deaths'] for r in pairs]
    seconds = lambda mode: [r[0 if mode == 'control' else 1]['brief']['totals']['duration_sec'] for r in pairs]
    result = evaluate(counts('control'), counts('candidate'), seconds('control'), seconds('candidate'))
    secondary = {}
    for key in ('engages', 'goals', 'frags', 'deaths', 'stalls', 'freezes', 'acquisitions', 'grabs'):
        differences = [rate(t, key) - rate(c, key) for c, t in pairs]
        secondary[key] = dict(control_mean=statistics.mean(rate(c, key) for c, _ in pairs),
            candidate_mean=statistics.mean(rate(t, key) for _, t in pairs),
            delta=statistics.mean(differences), descriptive_ci95=ci(differences, .95))
    order = {}
    for parity, label in ((1, 'control_first'), (0, 'candidate_first')):
        arm = [(c, t) for c, t in pairs if c['repeat'] % 2 == parity]
        order[label] = dict(n=len(arm), delta=statistics.mean(rate(t, 'lava_deaths') - rate(c, 'lava_deaths') for c, t in arm),
            control_events=sum(c['brief']['totals']['lava_deaths'] for c, _ in arm),
            candidate_events=sum(t['brief']['totals']['lava_deaths'] for _, t in arm))
    frame = lambda r: sum(w['mean_ms']*w['frames'] for w in r['timing']) / sum(w['frames'] for w in r['timing'])
    cadence = [frame(t)-frame(c) for c, t in pairs]
    cpu = [1000*(t['cpu_seconds']/t['wall_seconds']-c['cpu_seconds']/c['wall_seconds']) for c, t in pairs]
    tails = {}
    for mode in ('control', 'candidate'):
        arm = [r for r in rows if r['mode'] == mode]
        windows = [tuple(map(float,w)) for r in arm for w in TIMING.findall((ROOT/f"runs/{r['name']}.log").read_text(errors='replace'))]
        tails[mode] = dict(windows=len(windows), frames=sum(w[1] for w in windows),
            over20=sum(w[5] for w in windows), over50=sum(w[6] for w in windows), max_ms=max(w[4] for w in windows))
    result.update(protocol=p, protocol_sha256=sha, execution=execution,
        native_receipts_sha256=digest(out/'receipts.json'), secondary_per_minute=secondary,
        order_sensitivity=order, cadence=dict(delta_ms=statistics.mean(cadence),
            ci90_with_rounding=[ci(cadence,.9)[0]-.1,ci(cadence,.9)[1]+.1],
            cpu_delta_ms_per_wall_second=statistics.mean(cpu),cpu_descriptive_ci95=ci(cpu,.95)),
        all_complete_window_tails=tails,
        tapes={r['name']:dict(sha256=r['raw_sha256'],identity=r['identity'],totals=r['brief']['totals'],flags=r['brief']['flags']) for r in rows},
        limitations='Independent dm2 skill1 one-minute listen sessions only. Paired t inference uses 256 order blocks, not identical seeds; four-pair bootstrap guards short serial dependence, not arbitrary drift. Exact Poisson support assumes independent events and is not the decision rule. No pooling with exploratory data, optional stopping, deployment or gameplay changes.')
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__);ap.add_argument('protocol',type=Path);ap.add_argument('output',type=Path)
    args = ap.parse_args();result = audit(args.protocol);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('tapes','protocol')},indent=2))
