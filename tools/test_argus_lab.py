"""Lab spine tests: validation, staleness, the skeptic, triage, sessions and the pyramid.

Every check runs on a fixture tree built here, so CI needs no machine-local
BSP, binary or tape. One test validates the committed objective and claims.
"""
import contextlib
import io
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_lab  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
INDEX_HEAD = ('run\tmap\tstarted\ttick_class\tkind\tduration_sec\tstalls\tengages\tlava_deaths\tworld_deaths\t'
              'freezes\tfreeze_underfire\tcover\tgoals\tfrags\tdeaths\troutefails\thazards\tgrabs\tweapons\tboards\t'
              'kd_spread\tavg_speed')
LIMITS = """# What the lab can measure

## The detection limit

### dm4

| metric | arms | tapes | mean | sigma | CV | MDE n=3 | n=5 | n=10 |
|---|---|---|---|---|---|---|---|---|
| stalls | 14 | 43 | 8.2 | 6.0 | 73% | 13.8 (168%) | 10.7 (130%) | 7.5 (92%) |
| engages | 14 | 43 | 82.4 | 10.1 | 12% | 23.1 (28%) | 17.9 (22%) | 12.7 (15%) |
| lava_deaths | 14 | 43 | 4.1 | 1.7 | 43% | 4.0 (98%) | 3.1 (76%) | 2.2 (53%) |
| cover | 14 | 43 | 343.5 | 22.4 | 7% | 51.2 (15%) | 39.7 (12%) | 28.0 (8%) |

## What four gates cost

| gate | convicts | of | rate |
|---|---|---|---|
| engagements | 2 | 16 | 12% |
"""


def index_row(run, stalls=8, engages=80, lava=4, cover=340, tick='listen', kind='bot', started='2026-10-01 10:00:00',
              dur=185.0, mapname='dm4'):
    return '\t'.join(str(v) for v in (run, mapname, started, tick, kind, f'{dur:.2f}', stalls, engages, lava, 2, 0, 0,
                                      cover, 15, 20, 18, 3, 90, 40, 12, 0, 3, 210.0))


def tape(nodes=137, base=1, started='10/01/2026', body=''):
    return (f'LOG started on: {started} 10:00:00 \nARGNAV {nodes} nodes, 700 links\nARGUS init on dm4\n'
            f'ARGUS difficulty Reap t   1.1 base {base} cognition 1 aim 1\n' + body)


class Fixture:
    """A miniature checkout: objective, claims, runs, a graph, a suite and a verdict file."""

    def __init__(self, td):
        self.root = Path(td)
        for d in ('tools', 'runs', 'src', 'benchmarks', 'docs/specs'):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        obj = json.loads((REPO / 'tools' / 'lab_objective.json').read_text(encoding='utf-8'))
        obj['limits_doc'] = 'docs/specs/2026-09-16-lab-measurement-limits.md'
        self.write('tools/lab_objective.json', json.dumps(obj))
        self.write('docs/specs/2026-09-16-lab-measurement-limits.md', LIMITS)
        self.write('tools/refuted_claims.json', json.dumps({'claims': [
            {'id': 'old-rule', 'claim': 'an old rule', 'correction': 'the truth', 'evidence': ['#1']}]}))
        self.claims([])
        nodes = [[0.0, 0.0, 24.0], [100.0, 0.0, 24.0], [200.0, 0.0, 24.0]] + [[1000.0 + i, 0.0, 24.0] for i in range(134)]
        self.write('src/argus_nav_dm4.qc.json', json.dumps({'nodes': nodes, 'links': [[0, 1], [1, 2]], 'jlinks': []}))
        self.write('runs/human_scorecard.tsv', 'file\tmap\tdur\tbot_world\tbot_world_unforced\tfz_fire\tfz_max\tunstick\t'
                   'bot_kills_human\thuman_kills_bot\n')
        self.index = []

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def claims(self, claims):
        self.write('tools/lab_claims.json', json.dumps({'claims': claims}))

    def add_run(self, run, text=None, **row):
        self.index.append(index_row(run, **row))
        self.write('runs/tape_index.tsv', INDEX_HEAD + '\n' + '\n'.join(self.index) + '\n')
        self.write(f'runs/{run}.log', text if text is not None else tape())


def claim(**over):
    base = dict(id='a-claim', title='A claim', status='open', kind='defect', tier=1, maps=['dm4'],
                statement='Something is wrong.', evidence=['#1'])
    base.update(over)
    return base


@contextlib.contextmanager
def no_lab_binary():
    with mock.patch.object(argus_lab, 'lab_binary', return_value=None):
        yield


class TestValidation(unittest.TestCase):
    def test_the_committed_objective_and_claims_are_sound(self):
        self.assertEqual(argus_lab.validate(REPO), [])

    def test_validation_catches_each_rule(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.claims([
                claim(),
                claim(),  # duplicate id
                claim(id='bad-status', status='maybe'),
                claim(id='no-date', status='fixed'),
                claim(id='no-refute', kind='hypothesis'),
                claim(id='ghost-evidence', evidence=['runs/nowhere.log']),
                claim(id='wrong-cell', cells=[{'map': 'dm2', 'at': [0, 0, 0], 'radius': 64}]),
                claim(id='live-graveyard', kind='graveyard', status='open'),
                claim(id='old-rule'),
            ])
            errors = '\n'.join(argus_lab.validate(fx.root))
            for needle in ('a-claim: duplicate id', 'bad-status: status must be', 'no-date: a fixed claim says when',
                           'no-refute: an open hypothesis', 'ghost-evidence: evidence runs/nowhere.log',
                           'wrong-cell: cell map dm2', 'live-graveyard: a graveyard entry',
                           'old-rule: already in refuted_claims.json'):
                self.assertIn(needle, errors)

    def test_a_gate_column_must_exist_and_a_signed_objective_names_its_signer(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            obj = json.loads((fx.root / 'tools/lab_objective.json').read_text())
            obj['status'] = 'signed'
            obj['hard_gates'].append({'id': 'phantom', 'column': 'no_such_column', 'max': 0})
            fx.write('tools/lab_objective.json', json.dumps(obj))
            errors = '\n'.join(argus_lab.validate(fx.root))
            self.assertIn('names who signed it', errors)
            self.assertIn('column no_such_column is not in', errors)

    def test_evidence_can_be_an_issue_a_path_or_a_run(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_x1')
            self.assertTrue(argus_lab.evidence_resolves(fx.root, '#42'))
            self.assertTrue(argus_lab.evidence_resolves(fx.root, 'runs/ab_dm4_x1.log'))
            self.assertTrue(argus_lab.evidence_resolves(fx.root, 'ab_dm4_x1'))
            self.assertFalse(argus_lab.evidence_resolves(fx.root, 'ab_dm4_missing'))
            self.assertFalse(argus_lab.evidence_resolves(fx.root, '#forty'))


class TestLimits(unittest.TestCase):
    def test_limits_parse_per_map_and_ignore_other_tables(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            lim = argus_lab.limits(fx.root, argus_lab.objective(fx.root))
            self.assertEqual(set(lim), {'dm4'})
            self.assertEqual(lim['dm4']['stalls']['sigma'], 6.0)
            self.assertNotIn('engagements', lim['dm4'])

    def test_mde_reproduces_the_committed_limits_doc(self):
        lim = argus_lab.limits(REPO, argus_lab.objective(REPO))
        if 'dm4' not in lim:
            self.skipTest('limits doc has no dm4 table')
        # The doc prints dm4 stalls MDE 13.8 at n=3 and 10.7 at n=5 from sigma 6.0.
        self.assertAlmostEqual(argus_lab.mde(6.0, 3), 13.8, delta=0.15)
        self.assertAlmostEqual(argus_lab.mde(6.0, 5), 10.7, delta=0.15)
        self.assertEqual(argus_lab.mde(6.0, 0), math.inf)
        n = argus_lab.tapes_needed(6.0, 8.2 * 0.3)
        self.assertGreaterEqual(argus_lab.mde(6.0, 1) / math.sqrt(n / 1), 0)
        self.assertLessEqual(argus_lab.mde(6.0, n), 8.2 * 0.3 + 1e-9)
        self.assertGreater(argus_lab.mde(6.0, n - 1), 8.2 * 0.3)


class TestStale(unittest.TestCase):
    def findings(self, fx):
        with no_lab_binary():
            return argus_lab.stale_findings(fx.root, argus_lab.objective(fx.root))

    def test_baselines_benchmarks_verdicts_and_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_fast', tick='dedicated_fast')
            fx.add_run('ab_dm4_oldgraph', text=tape(nodes=120))
            fx.write('runs/baselines.json', json.dumps({'dm4': ['ab_dm4_fast', 'ab_dm4_oldgraph'], 'dm2': 'gone'}))
            fx.write('benchmarks/dm4.json', json.dumps({'map': 'dm4', 'graph_md5': '0' * 32, 'tasks': []}))
            fx.write('src/argus_nav_dm4.probe.json', json.dumps({'failed': [
                [[0.0, 0.0, 24.0], [100.0, 0.0, 24.0]],      # still shipped as a walk
                [[5000.0, 5000.0, 5.0], [6000.0, 6000.0, 6.0]]]}))   # endpoints gone
            fx.write('runs/shane_dm4_2026-10-02.log', tape())
            text = '\n'.join(f'{f["severity"]} {f["area"]} {f["item"]} {f["detail"]}' for f in self.findings(fx))
            self.assertIn('void baseline dm4 baseline recorded at dedicated_fast, not the played rate', text)
            self.assertIn('(ab_dm4_fast)', text)
            self.assertIn('stale baseline dm4 baseline ran 120 nodes, 700 links; the shipped graph prints 137 nodes', text)
            self.assertIn('void baseline dm2 baseline 1 tape missing: gone', text)
            self.assertIn('stale benchmark dm4.json pins graph 00000000', text)
            self.assertIn('1 link the puppet refused still shipped as plain walks, e.g. n0->n1', text)
            self.assertIn('1 of 2 convictions name endpoints no longer in the graph', text)
            self.assertIn('stale scorecard runs/human_scorecard.tsv 1 session tape not scored', text)
            self.assertIn('info objective', text)

    def test_verdict_modes_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('src/argus_nav_dm4.probe.json', json.dumps({'failed': [], 'modes': {
                'coop': {'failed': [[[0.0, 0.0, 24.0], [100.0, 0.0, 24.0]]]},
                'deathmatch': {'failed': [[[100.0, 0.0, 24.0], [200.0, 0.0, 24.0]]]}}}))
            items = [f['item'] for f in self.findings(fx) if f['area'] == 'verdicts']
            self.assertIn('argus_nav_dm4.probe.json (coop sweep)', items)
            self.assertIn('argus_nav_dm4.probe.json (deathmatch sweep)', items)

    def test_a_typed_link_is_not_reported_as_a_shipped_walk(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            doc = json.loads((fx.root / 'src/argus_nav_dm4.qc.json').read_text())
            doc['doorlinks'] = [[0, 1]]
            fx.write('src/argus_nav_dm4.qc.json', json.dumps(doc))
            fx.write('src/argus_nav_dm4.probe.json', json.dumps({'failed': [[[0.0, 0.0, 24.0], [100.0, 0.0, 24.0]]]}))
            self.assertFalse([f for f in self.findings(fx) if f['area'] == 'verdicts' and f['severity'] == 'stale'])

    def test_strict_exits_one_and_json_parses(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('benchmarks/dm4.json', json.dumps({'map': 'dm4', 'graph_md5': 'x', 'tasks': []}))
            out = io.StringIO()
            with no_lab_binary(), contextlib.redirect_stdout(out):
                self.assertEqual(argus_lab.main(['--root', str(fx.root), 'stale', '--json']), 0)
                self.assertTrue(json.loads(out.getvalue()))
                self.assertEqual(argus_lab.main(['--root', str(fx.root), 'stale', '--strict']), 1)


class TestSkeptic(unittest.TestCase):
    def run_skeptic(self, fx, a, b, **kw):
        with no_lab_binary():
            return argus_lab.skeptic(fx.root, a, b, **kw)

    def test_a_clean_comparison_classifies_effects_against_the_limit(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            for i, (s, e) in enumerate([(8, 80), (9, 82), (7, 81)]):
                fx.add_run(f'ab_dm4_ctl{i}', stalls=s, engages=e)
            for i, (s, e) in enumerate([(9, 120), (8, 118), (10, 121)]):
                fx.add_run(f'ab_dm4_new{i}', stalls=s, engages=e)
            rep = self.run_skeptic(fx, [f'ab_dm4_ctl{i}' for i in range(3)], [f'ab_dm4_new{i}' for i in range(3)])
            self.assertEqual(rep['verdict'], 'clean')
            self.assertEqual(rep['metrics']['stalls']['effect'], 'no detectable effect')
            self.assertEqual(rep['metrics']['engages']['effect'], 'moved')
            self.assertEqual(rep['metrics']['engages']['sigma_from'], 'limits doc')

    def test_void_reasons(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_a', tick='dedicated_slow')
            fx.add_run('ab_dm4_b')
            fx.add_run('shane_dm4_h', kind='human')
            rep = self.run_skeptic(fx, ['ab_dm4_a', 'ab_dm4_b'], ['ab_dm4_b', 'shane_dm4_h', 'ab_dm4_missing'])
            text = '\n'.join(rep['void'])
            self.assertEqual(rep['verdict'], 'void')
            self.assertIn('the same tape is in both arms: ab_dm4_b', text)
            self.assertIn('tick classes differ', text)
            self.assertIn('human and fixture tapes never enter', text)
            self.assertIn('ab_dm4_missing is not in runs/', text)

    def test_confounds_graph_skill_and_metric_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_a1', started='2026-08-19 10:00:00', text=tape(nodes=137, base=1))
            fx.add_run('ab_dm4_a2', started='2026-08-19 11:00:00', text=tape(nodes=137, base=1))
            fx.add_run('ab_dm4_b1', started='2026-08-21 10:00:00', text=tape(nodes=145, base=2))
            fx.add_run('ab_dm4_b2', started='2026-08-21 11:00:00', text=tape(nodes=145, base=2))
            rep = self.run_skeptic(fx, ['ab_dm4_a1', 'ab_dm4_a2'], ['ab_dm4_b1', 'ab_dm4_b2'],
                                   metrics=['stalls', 'goals', 'avg_speed'])
            text = '\n'.join(rep['confounds'])
            self.assertEqual(rep['verdict'], 'caveated')
            self.assertIn('different graphs (137 nodes, 700 links against 145 nodes, 700 links)', text)
            self.assertIn('skill tiers differ', text)
            self.assertIn('goals crosses a metric boundary: 2026-08-20', text)
            self.assertNotIn('avg_speed crosses', text)

    def test_a_tape_on_the_boundary_day_is_after_the_change(self):
        obj = argus_lab.objective(REPO)
        # world_deaths changed meaning on 2026-09-16 (telefrags credited to their cause): a tape that day is new.
        self.assertTrue(argus_lab.boundaries_crossed(obj, 'world_deaths', ['2026-09-15', '2026-09-16']))
        self.assertFalse(argus_lab.boundaries_crossed(obj, 'world_deaths', ['2026-09-16', '2026-09-17']))
        self.assertFalse(argus_lab.boundaries_crossed(obj, 'world_deaths', ['2026-09-14', '2026-09-15']))
        self.assertFalse(argus_lab.boundaries_crossed(obj, 'stalls', ['2026-08-01', '2026-10-01']))
        self.assertFalse(argus_lab.boundaries_crossed(obj, 'world_deaths', ['', '']))
        # A parser boundary is no confound: the corpus re-parses every tape with today's parser.
        self.assertFalse(argus_lab.boundaries_crossed(obj, 'avg_speed', ['2026-08-28', '2026-08-30']))

    def test_unequal_durations_compare_rates_and_zero_spread_is_not_a_move(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_a1', stalls=10, lava=0, dur=100.0)
            fx.add_run('ab_dm4_a2', stalls=12, lava=0, dur=100.0)
            fx.add_run('ab_dm4_b1', stalls=20, lava=0, dur=200.0)
            fx.add_run('ab_dm4_b2', stalls=24, lava=0, dur=200.0)
            rep = self.run_skeptic(fx, ['ab_dm4_a1', 'ab_dm4_a2'], ['ab_dm4_b1', 'ab_dm4_b2'])
            self.assertTrue(any('per-minute rates' in n for n in rep['notes']))
            self.assertAlmostEqual(rep['metrics']['stalls']['a'], rep['metrics']['stalls']['b'])
            self.assertEqual(rep['metrics']['stalls']['sigma_from'], 'these arms')
            self.assertEqual(rep['metrics']['lava_deaths']['effect'], 'no change')

    def test_one_tape_a_side_is_noted(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_a')
            fx.add_run('ab_dm4_b')
            rep = self.run_skeptic(fx, ['ab_dm4_a'], ['ab_dm4_b'])
            self.assertTrue(any('one tape a side' in n for n in rep['notes']))


def sample(name, t, x, y, z, spd=200, hp=100):
    return f"ARGLOG {name} t {t:.1f} pos '{x} {y} {z}' spd {spd} yaw 0 mode 2 st 0 gl 0 hp {hp} frg 0\n"


class TestTriage(unittest.TestCase):
    def stalls_at(self, x, y, z, n=5, started='10/01/2026'):
        body = 'ARGEVT Reap spawned\n'
        for i in range(n):
            body += sample('Reap', i * 1.0, x, y, z) + 'ARGEVT Reap stall\n'
        return tape(started=started, body=body)

    def test_known_new_regression_and_before_the_fix(self):
        claims = [dict(id='open-cell', status='open', cells=[{'map': 'dm4', 'at': [0, 0, 24], 'radius': 96}]),
                  dict(id='fixed-cell', status='fixed', fixed_on='2026-09-01',
                       cells=[{'map': 'dm4', 'at': [2000, 0, 24], 'radius': 96}])]
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            cases = [((10, 10, 24), '10/01/2026', 'known'),
                     ((2010, 0, 24), '10/01/2026', 'regression?'),
                     ((2010, 0, 24), '08/01/2026', 'before the fix'),
                     ((5000, 0, 24), '10/01/2026', 'new')]
            for (x, y, z), started, flag in cases:
                path = fx.write('runs/t.log', self.stalls_at(x, y, z, started=started))
                with mock.patch.object(argus_lab, 'bsp_path', return_value=None):
                    rep = argus_lab.triage(fx.root, path, claims=claims)
                self.assertEqual(rep['clusters'][0]['flag'], flag, (x, started))
                self.assertEqual(rep['clusters'][0]['kinds'], {'stall': 5})

    def test_a_light_recurrence_at_a_fixed_cell_is_not_a_regression(self):
        claims = [dict(id='fixed-cell', status='fixed', fixed_on='2026-09-01',
                       cells=[{'map': 'dm4', 'at': [0, 0, 24], 'radius': 96}])]
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            path = fx.write('runs/t.log', self.stalls_at(0, 0, 24, n=3))
            with mock.patch.object(argus_lab, 'bsp_path', return_value=None):
                rep = argus_lab.triage(fx.root, path, claims=claims)
            self.assertEqual(rep['clusters'][0]['flag'], 'known')

    def test_world_deaths_split_with_contents_and_stay_plain_without(self):
        body = 'ARGEVT Reap spawned\n'
        for t, z, hp in ((1.0, -296, 100), (1.5, -296, 100), (2.0, -384, 60), (2.5, -384, 20)):
            body += sample('Reap', t, 0, 0, z, hp=hp)
        body += "ARGEVT Reap death world pos '0 0 -384'\n"
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            path = fx.write('runs/d.log', tape(body=body))
            lava = lambda x, y, z: -5 if z < -350 else -1  # noqa: E731
            with mock.patch.object(argus_lab, 'bsp_path', return_value=Path('x.bsp')), \
                    mock.patch.object(argus_lab.argus_longi, '_classifier', return_value=lava):
                rep = argus_lab.triage(fx.root, path, claims=[])
            self.assertEqual(rep['clusters'][0]['kinds'], {'unforced death': 1})
            with mock.patch.object(argus_lab, 'bsp_path', return_value=None):
                rep = argus_lab.triage(fx.root, path, claims=[])
            self.assertEqual(rep['clusters'][0]['kinds'], {'world death': 1})
            self.assertFalse(rep['bsp'])


class TestSessions(unittest.TestCase):
    def test_gates_goal_measures_and_eligibility(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('runs/shane_dm4_2026-10-01.log', tape(base=1))
            fx.write('runs/shane_dm4_2026-10-02.log', tape(base=2, body='Host_Error: Program error\n'))
            fx.write('runs/shane_e1m2_2026-10-03.log', 'LOG started on: 10/03/2026 10:00:00 \n')
            rows = [dict(file='shane_dm4_2026-10-01.log', map='dm4', dur='240', bot_world='2', bot_world_unforced='0',
                         fz_fire='0', fz_max='0', unstick='0', bot_kills_human='10', human_kills_bot='15'),
                    dict(file='shane_dm4_2026-10-02.log', map='dm4', dur='240', bot_world='2', bot_world_unforced='2',
                         fz_fire='1', fz_max='12.5', unstick='1', bot_kills_human='4', human_kills_bot='16'),
                    dict(file='shane_e1m2_2026-10-03.log', map='e1m2', dur='60', bot_world='0', bot_world_unforced='',
                         fz_fire='0', fz_max='0', unstick='0', bot_kills_human='0', human_kills_bot='0')]
            obj = argus_lab.objective(fx.root)
            history = [dict(commit='b' * 40, date='2026-09-30', subject='install')]
            good, bad, coop = (argus_lab.evaluate_session(fx.root, r, obj, history, {}) for r in rows)
            self.assertEqual(good['failed'], [])
            self.assertEqual(good['bk_pm'], 2.5)
            self.assertEqual(good['ratio'], 1.5)
            self.assertTrue(good['eligible'])
            self.assertEqual(good['build'], 'bbbbbbb')
            self.assertEqual(good['date'], '2026-10-01')
            self.assertEqual(set(bad['failed']), {'engine-error', 'freeze-under-fire', 'statue-10s',
                                                  'unforced-world-death', 'rescue-warp'})
            self.assertIn('skill 2, not 1', bad['reasons'])
            self.assertFalse(coop['eligible'])
            self.assertIn('unforced-world-death', coop['unknown'])
            self.assertIn('the tape does not name its skill tier', coop['reasons'])

    def test_goal_verdict_needs_enough_sessions_on_the_installed_build(self):
        obj = argus_lab.objective(REPO)
        history = [dict(commit='c' * 40, date='2026-11-01', subject='new'), dict(commit='d' * 40, date='2026-10-01', subject='old')]
        mk = lambda d, b, bk: dict(map='dm4', eligible=True, build=b, date=d, bk_pm=bk, ratio=2.0, file=d)  # noqa: E731
        sessions = [mk('2026-10-05', 'ddddddd', 1.0), mk('2026-11-02', 'ccccccc', 2.5), mk('2026-11-03', 'ccccccc', 2.0)]
        v = argus_lab.goal_verdicts(sessions, obj, history)
        self.assertEqual((v['dm4']['status'], v['dm4']['have'], v['dm4']['eligible_any_build']), ('insufficient', 2, 3))
        sessions.append(mk('2026-11-04', 'ccccccc', 3.5))
        v = argus_lab.goal_verdicts(sessions, obj, history)
        self.assertEqual(v['dm4']['status'], 'measured')
        self.assertEqual(v['dm4']['bk_pm'], 2.5)
        self.assertEqual(v['dm4']['bk_band'], 'in target')
        self.assertEqual(v['dm2']['status'], 'insufficient')

    def test_build_on_and_tape_date(self):
        history = [dict(commit='new', date='2026-11-01'), dict(commit='old', date='2026-10-01')]
        self.assertEqual(argus_lab.build_on('2026-10-15', history)['commit'], 'old')
        self.assertEqual(argus_lab.build_on('2026-11-01', history)['commit'], 'new')
        self.assertIsNone(argus_lab.build_on('2026-09-01', history))
        self.assertIsNone(argus_lab.build_on(None, history))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'shane_dm4_2026-01-02.log'
            p.write_text('LOG started on: 11/14/2026 07:11:58 \n')
            self.assertEqual(argus_lab.tape_date(p), '2026-11-14')
            p.write_text('no header\n')
            self.assertEqual(argus_lab.tape_date(p), '2026-01-02')


class TestPyramid(unittest.TestCase):
    def test_plan_blocks_stale_suites_and_sizes_ladders(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('benchmarks/dm4.json', json.dumps({'map': 'dm4', 'graph_md5': 'x', 'tasks': []}))
            with mock.patch.object(argus_lab, 'bsp_path', return_value=None), no_lab_binary():
                steps = argus_lab.pyramid_plan(fx.root, ['dm4', 'nomap'], 4, argus_lab.objective(fx.root))
            by = {s['name']: s for s in steps}
            self.assertIn('no BSP', by['dm4 navmesh audit']['skip'])
            self.assertIn('no src/argus_nav_nomap', by['nomap graph']['skip'])
            self.assertTrue(by['benchmark dm4.json'].get('blocks'))
            self.assertIn('94 listen-class tapes a side', by['dm4 ladder for stalls']['plan'])
            self.assertEqual(max(s['tier'] for s in argus_lab.pyramid_plan(fx.root, ['dm4'], 1,
                                                                           argus_lab.objective(fx.root))), 1)

    def test_benchmark_ratchet_holds_the_bar_a_graph_has_reached(self):
        def report(*done, total=('a', 'b', 'c')):
            rows = [dict(name=n, split='train', completed=n in done, wall_sec=1.0) for n in total]
            return 'task a ...\n' + json.dumps(dict(suite='s', results=rows), indent=1)
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            step = dict(name='benchmark s.json', key='g1')
            ok, detail, done = argus_lab.judge_benchmark(fx.root, step, report('a', 'b'))
            self.assertTrue(ok)
            self.assertIn('2 of 3 tasks completed; the first run on this graph sets the bar', detail)
            (fx.root / 'runs' / 'lab').mkdir(parents=True)
            fx.write('runs/lab/pyramid-20260101T000000Z.json',
                     json.dumps(dict(steps=[dict(name='benchmark s.json', key='g1', completed=done)])))
            ok, detail, _ = argus_lab.judge_benchmark(fx.root, step, report('a'))
            self.assertFalse(ok)
            self.assertIn('no longer completes b', detail)
            ok, detail, _ = argus_lab.judge_benchmark(fx.root, step, report('a', 'b', 'c'))
            self.assertTrue(ok)
            self.assertIn('newly completes c', detail)
            # A new graph starts its own bar.
            ok, detail, _ = argus_lab.judge_benchmark(fx.root, dict(step, key='g2'), report('a'))
            self.assertTrue(ok)
            self.assertIn('sets the bar', detail)
            ok, detail, _ = argus_lab.judge_benchmark(fx.root, step, 'crashed before a report\n')
            self.assertFalse(ok)

    def test_a_failing_tier_stops_the_climb_and_leaves_a_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            steps = [dict(tier=1, name='passes', cmd=[sys.executable, '-c', 'pass']),
                     dict(tier=1, name='fails', cmd=[sys.executable, '-c', 'raise SystemExit(3)']),
                     dict(tier=2, name='never', cmd=[sys.executable, '-c', 'pass'])]
            out = io.StringIO()
            with mock.patch.object(argus_lab, 'pyramid_plan', return_value=steps), no_lab_binary():
                code = argus_lab.pyramid(fx.root, ['dm4'], 2, out=out)
            self.assertEqual(code, 1)
            text = out.getvalue()
            self.assertIn('tier 1 fails: FAIL', text)
            self.assertNotIn('never', text)
            receipt = json.loads(next((fx.root / 'runs' / 'lab').glob('pyramid-*.json')).read_text())
            self.assertEqual(receipt['stopped'], 1)
            self.assertEqual([s['status'] for s in receipt['steps']], ['pass', 'fail'])


class TestNight(unittest.TestCase):
    def sweep(self, fx, steps):
        out = io.StringIO()
        with mock.patch.object(argus_lab, 'pyramid_plan', return_value=steps), no_lab_binary(), \
                mock.patch.object(argus_lab, 'bsp_path', return_value=None):
            code = argus_lab.night(fx.root, maps=['dm4'], out=out)
        report = sorted((fx.root / 'runs' / 'lab').glob('night-*.md'))[-1].read_text()
        return code, report

    def test_the_sweep_alerts_on_what_got_worse_and_not_on_known_failures(self):
        ok = [sys.executable, '-c', 'pass']
        bad = [sys.executable, '-c', 'raise SystemExit(1)']
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            code, report = self.sweep(fx, [dict(tier=1, name='a', cmd=ok), dict(tier=1, name='b', cmd=bad)])
            self.assertEqual(code, 0)
            self.assertIn('First sweep', report)
            self.assertIn('Still failing, not an alert: b', report)
            code, report = self.sweep(fx, [dict(tier=1, name='a', cmd=bad), dict(tier=1, name='b', cmd=bad)])
            self.assertEqual(code, 1)
            self.assertIn('newly failing: a', report)
            self.assertNotIn('newly failing: b', report)
            code, report = self.sweep(fx, [dict(tier=1, name='a', cmd=ok), dict(tier=1, name='b', cmd=bad)])
            self.assertEqual(code, 0)
            self.assertIn('Nothing got worse.', report)

    def test_a_newly_void_artefact_alerts_once(self):
        ok = [sys.executable, '-c', 'pass']
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            self.assertEqual(self.sweep(fx, [dict(tier=1, name='a', cmd=ok)])[0], 0)
            fx.add_run('ab_dm4_fast', tick='dedicated_fast')
            fx.write('runs/baselines.json', json.dumps({'dm4': 'ab_dm4_fast'}))
            code, report = self.sweep(fx, [dict(tier=1, name='a', cmd=ok)])
            self.assertEqual(code, 1)
            self.assertIn('newly void: baseline: dm4 baseline', report)
            self.assertEqual(self.sweep(fx, [dict(tier=1, name='a', cmd=ok)])[0], 0)

    def test_registered_maps_come_from_progs_src(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('src/progs.src', '../lq1/progs.dat\ndefs.qc\nargus_nav_dm4.qc\n  argus_nav_e1m1.qc\nargus_nav_dispatch.qc\n')
            self.assertEqual(argus_lab.registered_maps(fx.root), ['dm4', 'e1m1'])


class TestReviewFindings(unittest.TestCase):
    """One test per defect the 2026-11-14 red-team rounds found, so none comes back."""

    def test_builds_are_attributed_by_time_of_day(self):
        history = [dict(commit='v418', when='2026-09-16 06:23:53', date='2026-09-16'),
                   dict(commit='v417', when='2026-09-14 09:56:07', date='2026-09-14')]
        self.assertEqual(argus_lab.build_on('2026-09-16 06:06:00', history)['commit'], 'v417')
        self.assertEqual(argus_lab.build_on('2026-09-16 06:26:00', history)['commit'], 'v418')
        self.assertEqual(argus_lab.build_on('2026-09-16', history)['commit'], 'v418')
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.log'
            p.write_text('LOG started on: 09/16/2026 06:06:12 \n')
            self.assertEqual(argus_lab.tape_when(p), '2026-09-16 06:06:12')

    def test_a_baseline_on_the_same_nodes_but_other_links_is_stale(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('src/argus_nav_dm4.qc', 'void() x = { dprint ("ARGNAV 137 nodes, 716 links\\n"); };\n')
            fx.add_run('ab_dm4_base', text=tape(nodes=137))  # the fixture tape prints 700 links
            fx.write('runs/baselines.json', json.dumps({'dm4': 'ab_dm4_base'}))
            with no_lab_binary():
                found = [f for f in argus_lab.stale_findings(fx.root, argus_lab.objective(fx.root))
                         if f['area'] == 'baseline']
            self.assertEqual(len(found), 1)
            self.assertIn('ran 137 nodes, 700 links; the shipped graph prints 137 nodes, 716 links', found[0]['detail'])

    def test_the_limits_age_uses_the_generated_date_and_tape_headers(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('docs/specs/2026-09-16-lab-measurement-limits.md',
                     'Generated by `argus-mcp measure` on 2026-11-01.\n' + LIMITS)
            for i in range(12):
                fx.write(f'runs/ab_dm4_new{i}.log', tape(started='11/05/2026', body=sample('Reap', 1.0, 0, 0, 24)))
            for i in range(12):
                fx.write(f'runs/ab_dm4_old{i}.log', tape(started='10/05/2026', body=sample('Reap', 1.0, 0, 0, 24)))
            fx.write('runs/shane_dm4_2026-11-06.log', tape(started='11/06/2026', body=sample('Reap', 1.0, 0, 0, 24)))
            with no_lab_binary():
                found = [f for f in argus_lab.stale_findings(fx.root, argus_lab.objective(fx.root))
                         if f['area'] == 'limits']
            self.assertEqual(len(found), 1)
            self.assertIn('generated 2026-11-01; 12 bot tapes recorded since', found[0]['detail'])

    def test_a_tape_twice_in_one_arm_is_void(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_a1', engages=60)
            fx.add_run('ab_dm4_b1', engages=90)
            with no_lab_binary():
                rep = argus_lab.skeptic(fx.root, ['ab_dm4_a1'] * 3, ['ab_dm4_b1'] * 3)
            self.assertEqual(rep['verdict'], 'void')
            self.assertTrue(any('more than once' in v for v in rep['void']))

    def test_a_zero_sigma_in_the_doc_falls_back_to_the_arms(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('docs/specs/2026-09-16-lab-measurement-limits.md',
                     LIMITS.replace('| lava_deaths | 14 | 43 | 4.1 | 1.7 |', '| lava_deaths | 14 | 43 | 0.0 | 0.0 |'))
            for i, v in enumerate((0, 1, 0)):
                fx.add_run(f'ab_dm4_a{i}', lava=v)
            for i, v in enumerate((3, 4, 3)):
                fx.add_run(f'ab_dm4_b{i}', lava=v)
            with no_lab_binary(), mock.patch.object(argus_lab, 'bsp_path', return_value=None):
                rep = argus_lab.skeptic(fx.root, [f'ab_dm4_a{i}' for i in range(3)], [f'ab_dm4_b{i}' for i in range(3)],
                                        metrics=['lava_deaths'])
            m = rep['metrics']['lava_deaths']
            self.assertEqual(m['sigma_from'], 'these arms')
            self.assertEqual(m['effect'], 'moved')

    def test_arms_noisier_than_the_doc_set_the_limit(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            for i, c in enumerate((300, 400, 330)):
                fx.add_run(f'ab_dm4_a{i}', cover=c)
            for i, c in enumerate((420, 330, 450)):
                fx.add_run(f'ab_dm4_b{i}', cover=c)
            with no_lab_binary():
                rep = argus_lab.skeptic(fx.root, [f'ab_dm4_a{i}' for i in range(3)], [f'ab_dm4_b{i}' for i in range(3)],
                                        metrics=['cover'])
            m = rep['metrics']['cover']
            self.assertEqual(m['sigma_from'], 'these arms')
            self.assertEqual(m['effect'], 'no detectable effect')

    def test_names_and_maps_are_read_from_any_spelling(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            self.assertEqual(argus_lab.run_name('runs/ab_dm4_x.log'), 'ab_dm4_x')
            self.assertEqual(argus_lab.run_name('ab_dm4_x'), 'ab_dm4_x')
            self.assertEqual(argus_lab.map_from_name(fx.root, 'nm_ctl_dm4_1'), 'dm4')
            self.assertEqual(argus_lab.map_from_name(fx.root, 'rep_cand_dm4_3.log'), 'dm4')
            self.assertIsNone(argus_lab.map_from_name(fx.root, 'nm_ctl_zz9_1'))
            fx.add_run('ab_dm4_a1')
            fx.add_run('ab_dm4_b1')
            with no_lab_binary():
                rep = argus_lab.skeptic(fx.root, ['runs/ab_dm4_a1.log'], ['ab_dm4_b1.log'])
            self.assertNotEqual(rep['verdict'], 'void', rep['void'])

    def test_stub_tapes_and_unknown_tick_classes_are_void(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.add_run('ab_dm4_a1', dur=0.0)
            fx.add_run('ab_dm4_b1', tick='')
            with no_lab_binary():
                rep = argus_lab.skeptic(fx.root, ['ab_dm4_a1'], ['ab_dm4_b1'])
            text = '\n'.join(rep['void'])
            self.assertIn('no duration, a stub tape: ab_dm4_a1', text)
            self.assertIn('no tick class', text)

    def test_lava_is_recounted_from_hull0_contents(self):
        body = 'ARGEVT Reap spawned\n' + sample('Reap', 1.0, 0, 0, -20) + "ARGEVT Reap death world pos '0 0 -30'\n"
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            for name in ('ab_dm4_a1', 'ab_dm4_a2'):
                fx.add_run(name, lava=0)
            for name in ('ab_dm4_b1', 'ab_dm4_b2'):
                fx.add_run(name, lava=0, text=tape(body=body))
            lava = lambda x, y, z: -5 if z < -40 else -1  # noqa: E731  shallow lava the z rule misses
            with no_lab_binary(), mock.patch.object(argus_lab, 'bsp_path', return_value=Path('x.bsp')), \
                    mock.patch.object(argus_lab.argus_longi, '_classifier', return_value=lava):
                rep = argus_lab.skeptic(fx.root, ['ab_dm4_a1', 'ab_dm4_a2'], ['ab_dm4_b1', 'ab_dm4_b2'],
                                        metrics=['lava_deaths'])
            self.assertEqual((rep['metrics']['lava_deaths']['a'], rep['metrics']['lava_deaths']['b']), (0.0, 1.0))
            self.assertTrue(any('hull-0' in n for n in rep['notes']))

    def test_known_failures_do_not_stop_the_pyramid_and_a_tier_finishes(self):
        ok = [sys.executable, '-c', 'pass']
        bad = [sys.executable, '-c', 'raise SystemExit(1)']
        steps = [dict(tier=1, name='known', cmd=bad), dict(tier=1, name='new', cmd=bad),
                 dict(tier=1, name='later in the tier', cmd=ok), dict(tier=2, name='next tier', cmd=ok)]
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            (fx.root / 'runs' / 'lab').mkdir(parents=True)
            fx.write('runs/lab/night-20261101T000000000000Z.json',
                     json.dumps(dict(date='2026-11-01', steps=[dict(name='known', status='fail')])))
            out = io.StringIO()
            with mock.patch.object(argus_lab, 'pyramid_plan', return_value=steps), no_lab_binary():
                code = argus_lab.pyramid(fx.root, ['dm4'], 2, out=out)
            text = out.getvalue()
            self.assertEqual(code, 1)
            self.assertIn('tier 1 known: known failure', text)
            self.assertIn('tier 1 later in the tier: pass', text)
            self.assertNotIn('next tier', text)
            out = io.StringIO()
            with mock.patch.object(argus_lab, 'pyramid_plan', return_value=[dict(tier=1, name='known', cmd=bad),
                                                                             dict(tier=2, name='b', skip='x', blocks=True)]), \
                    no_lab_binary():
                self.assertEqual(argus_lab.pyramid(fx.root, ['dm4'], 2, out=out), 3)

    def test_validation_rejects_values_that_would_crash_later(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            obj = json.loads((fx.root / 'tools/lab_objective.json').read_text())
            obj['hard_gates'][1]['max'] = '0'
            obj['goal_targets']['kill_ratio'] = 'high'
            del obj['calibration']['goal_maps']
            fx.write('tools/lab_objective.json', json.dumps(obj))
            fx.claims([claim(id='dot', evidence=['.']), claim(id='outside', evidence=['../outside.txt']),
                       claim(id='absolute', evidence=[str(Path(sys.executable).resolve())]),
                       claim(id='bool-radius', cells=[{'map': 'dm4', 'at': [0, 0, 0], 'radius': True}]),
                       claim(id='mixed', kind='graveyard', status='refuted', do_not_retry=True, next='retry it')])
            errors = '\n'.join(argus_lab.validate(fx.root))
            for needle in ("max must be a number, not '0'", 'goal target kill_ratio: needs numeric',
                           'goal_maps must be a non-empty list', 'claim dot: evidence . does not resolve',
                           'claim outside: evidence ../outside.txt', 'claim absolute: evidence',
                           'claim bool-radius: a cell is',
                           'claim mixed: do_not_retry contradicts'):
                self.assertIn(needle, errors)

    def test_a_bot_only_tape_never_counts_and_json_has_no_infinity(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.write('runs/b.log', tape(base=1))
            row = dict(file='b.log', map='dm4', dur='300', human='-', bot_world='0', bot_world_unforced='0',
                       fz_fire='0', fz_max='0', unstick='0', bot_kills_human='0', human_kills_bot='3')
            s = argus_lab.evaluate_session(fx.root, row, argus_lab.objective(fx.root), [], {})
            self.assertFalse(s['eligible'])
            self.assertIn('no human in the tape', s['reasons'])
            self.assertEqual(s['ratio'], math.inf)
            self.assertEqual(json.loads(json.dumps(argus_lab.jsonable(s)))['ratio'], 'inf')

    def test_a_refused_jump_link_still_shipped_is_stale(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            doc = json.loads((fx.root / 'src/argus_nav_dm4.qc.json').read_text())
            doc['jlinks'] = [[1, 2]]
            fx.write('src/argus_nav_dm4.qc.json', json.dumps(doc))
            fx.write('src/argus_nav_dm4.probe.json', json.dumps({'failed': [], 'typed_failed': [
                {'kind': 'jump', 'from': [101.0, 3.0, 24.0], 'to': [205.0, -4.0, 30.0]}]}))
            with no_lab_binary():
                found = [f for f in argus_lab.stale_findings(fx.root, argus_lab.objective(fx.root))
                         if f['area'] == 'verdicts']
            self.assertEqual(len(found), 1)
            self.assertIn('1 jump link the puppet refused still shipped, e.g. n1->n2', found[0]['detail'])

    def test_cells_bound_height_and_claims_set_their_tolerance(self):
        cell = {'map': 'dm4', 'at': [0, 0, -384], 'radius': 330, 'dz': 40}
        self.assertTrue(argus_lab.in_cell((300, 0, -380), cell))
        self.assertFalse(argus_lab.in_cell((194, -276, -73), cell))
        self.assertFalse(argus_lab.in_cell((100, 0, -300), cell))  # inside the radius, a storey up
        self.assertTrue(argus_lab.in_cell((100, 0, -350), cell))
        self.assertFalse(argus_lab.in_cell((340, 0, -384), cell))
        mk = lambda *pts: dict(points=[dict(kind=k, dur=d) for k, d in pts])  # noqa: E731
        self.assertFalse(argus_lab.regressed(mk(('freeze', 7.0)), {'freeze_sec': 8}))
        self.assertTrue(argus_lab.regressed(mk(('freeze', 9.0)), {'freeze_sec': 8}))
        self.assertTrue(argus_lab.regressed(mk(('unforced death', 0)), {'events': 99}))
        self.assertFalse(argus_lab.regressed(mk(*[('stall', 0)] * 10), {'events': 10}))
        self.assertTrue(argus_lab.regressed(mk(*[('stall', 0)] * 11), {'events': 10}))
        self.assertTrue(argus_lab.regressed(mk(*[('stall', 0)] * argus_lab.REGRESSION_COUNT), {}))


class TestCommandLine(unittest.TestCase):
    def test_every_command_runs_on_the_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            fx.claims([claim(cheapest_tier=2, next='do the thing')])
            fx.add_run('ab_dm4_a1')
            fx.add_run('ab_dm4_b1')
            fx.write('runs/t.log', tape(body='ARGEVT Reap spawned\n'))
            root = ['--root', str(fx.root)]
            for argv in (['claims'], ['claims', '--check'], ['claims', '--status', 'open'], ['state'], ['stale'],
                         ['session', '--last', '3'], ['skeptic', 'ab_dm4_a1', '--vs', 'ab_dm4_b1'],
                         ['skeptic', 'ab_dm4_a1', '--vs', 'ab_dm4_b1', '--json'], ['triage', 't'],
                         ['triage', 't', '--json'], ['review', 't'], ['ledger'],
                         ['pyramid', '--maps', 'dm4', '--dry-run']):
                out = io.StringIO()
                with no_lab_binary(), mock.patch.object(argus_lab, 'bsp_path', return_value=None), \
                        contextlib.redirect_stdout(out):
                    code = argus_lab.main(root + argv)
                self.assertEqual(code, 0, (argv, out.getvalue()[-500:]))
                self.assertTrue(out.getvalue().strip(), argv)
            out = io.StringIO()
            with no_lab_binary(), contextlib.redirect_stdout(out):
                argus_lab.main(root + ['state'])
            self.assertIn('## Next', out.getvalue())
            self.assertIn('a-claim (deterministic cases, #1): do the thing', out.getvalue())

    def test_state_and_ledger_write_files(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(td)
            target = fx.root / 'out' / 'state.md'
            target.parent.mkdir()
            with no_lab_binary(), contextlib.redirect_stdout(io.StringIO()):
                argus_lab.main(['--root', str(fx.root), 'state', '--write', str(target)])
                argus_lab.main(['--root', str(fx.root), 'ledger', '--write', str(fx.root / 'out' / 'ledger.json')])
            self.assertTrue(target.read_text().startswith('# Argus lab state'))
            ledger = json.loads((fx.root / 'out' / 'ledger.json').read_text())
            self.assertEqual(ledger['graphs']['dm4']['nodes'], 137)
            self.assertIn('stale', ledger)


if __name__ == '__main__':
    unittest.main()
