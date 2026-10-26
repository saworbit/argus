import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
from scipy import stats

from report_perception_cohort import evaluate, ci, paired, schedule, PAIRS
from run_perception_cohort import valid_tape
import report_perception_cohort as report


class CohortTests(unittest.TestCase):
    def test_zero_drop_and_equivalence_are_distinct(self):
        control = np.full(PAIRS, 12.)
        noise = np.tile([-1., 1.], PAIRS // 2)
        result = evaluate(control, control + noise)
        self.assertTrue(result['tost_equivalent'])
        self.assertIn('sampling noise', result['verdict'])
        self.assertFalse(result['regression_confirmed'])
        real = evaluate(control, control + noise - 4)
        self.assertTrue(real['regression_confirmed'])
        self.assertFalse(real['tost_equivalent'])
        small = evaluate(control, control + noise - .5)
        self.assertTrue(small['tost_equivalent'])
        self.assertTrue(small['regression_confirmed'])  # small but real is not called noise

    def test_inconclusive_and_positive(self):
        control = np.full(PAIRS, 30.)
        high_variance = np.tile([-20., 20.], PAIRS // 2)
        self.assertEqual(evaluate(control, control + high_variance)['verdict'], 'inconclusive')
        self.assertIn('increase', evaluate(control, control + 5)['verdict'])

    def test_paired_ci_matches_independent_scipy_api(self):
        rng = np.random.default_rng(12)
        a, b = rng.normal(15, 3, PAIRS), rng.normal(12, 3, PAIRS)
        for confidence in (.9, .95):
            expected = stats.ttest_rel(a, b).confidence_interval(confidence)
            np.testing.assert_allclose(ci(a - b, confidence), [expected.low, expected.high])

    def test_complete_schedule_and_floor(self):
        plan = schedule('test')
        rows = [dict(name=name, mode=mode, repeat=repeat) for name, mode, repeat in plan]
        self.assertEqual(len(paired(rows, 'test')), PAIRS)
        for bad in (rows[:-1], rows + rows[:1], rows[::-1]):
            with self.assertRaises(AssertionError): paired(bad, 'test')
        self.assertEqual([x[1] for x in plan[:4]], ['control', 'candidate', 'candidate', 'control'])
        self.assertTrue(evaluate(np.full(PAIRS, 10.), np.full(PAIRS, 8.))['existing_65pct_floor']['noninferior'])
        self.assertTrue(evaluate(np.full(PAIRS, 10.), np.full(PAIRS, 5.))['existing_65pct_floor']['collapse_confirmed'])
        self.assertIsNone(evaluate(np.zeros(PAIRS), np.zeros(PAIRS))['retention_ratio'])

    def test_correlated_blocks_do_not_get_ignored(self):
        control = np.full(PAIRS, 20.)
        correlated = np.repeat(np.tile([-7., 7.], PAIRS // 8), 4)
        result = evaluate(control, control + correlated)
        self.assertGreater(result['block_bootstrap']['ci95'][1], result['ci95'][1])
        with self.assertRaises(AssertionError): evaluate(control[:-1], control[:-1])
        with self.assertRaises(AssertionError): evaluate(control, np.full(PAIRS, np.nan))

    def test_validity_never_excludes_for_bad_gameplay(self):
        brief = dict(map='dm2', flags=['not every bot finished with a positive frag count'],
                     totals=dict(duration_sec=60., tick_class='listen', engages=0, frags=-10))
        text = '\n'.join(f'BHVTIME t {5*i} frames 350 seconds 5 mean_ms 14.3 max_ms 100 over20 4 over50 2' for i in range(1, 11))
        self.assertEqual(len(valid_tape(brief, text)), 9)
        for marker in ('BHVDBG ', 'PERFIX ', 'Host_Error'):
            with self.assertRaises(AssertionError): valid_tape(brief, text + '\n' + marker)
        brief['totals']['duration_sec'] = 57.9
        with self.assertRaises(AssertionError): valid_tape(brief, text)

    def test_full_native_receipt_audit_and_tamper_detection(self):
        scratch = Path(__file__).resolve().parents[1] / 'backups'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder); out = root / 'study'; out.mkdir(); (root / 'runs').mkdir()
            protocol = dict(output='study', prefix='unit', pairs=128, seconds=60, skill=1,
                engagement_margin_per_minute=2., registered_utc='2020-01-01T00:00:00+00:00',
                shipped_sha256='shipped', code_sha256={}, resources_sha256={}, identity={},
                protected_binaries=[], binaries={m:dict(sha256=m,source_sha256=m) for m in ('control','candidate')})
            path = root / 'protocol.json'; path.write_text(json.dumps(protocol)); sha = report.digest(path)
            (out / 'protocol.sha256').write_text(sha)
            (out / 'execution.json').write_text(json.dumps(dict(status='complete',restored_sha256='shipped',protocol_sha256=sha)))
            text = '\n'.join(f'BHVTIME t {5*i} frames 350 seconds 5 mean_ms 14.3 max_ms 100 over20 4 over50 2' for i in range(1, 11))
            rows = []
            for name, mode, repeat in schedule('unit'):
                raw = root / f'runs/{name}.log'; raw.write_text(text)
                totals = dict.fromkeys(('goals','frags','deaths','stalls','lava_deaths','freezes','acquisitions','grabs'),0)
                totals.update(duration_sec=60.,tick_class='listen',engages=12)
                rows.append(dict(name=name,mode=mode,repeat=repeat,protocol_sha256=sha,
                    identity=dict(binary_sha256=mode),executed_source_sha256=mode,
                    brief=dict(map='dm2',totals=totals,lab_identity=dict(authoritative=True),flags=[]),
                    raw_sha256=report.digest(raw),valid=True,started_utc='2021-01-01T00:00:00+00:00',
                    stopped_utc='2021-01-01T00:01:00+00:00',timing=valid_tape(dict(map='dm2',totals=totals,flags=[]),text),
                    cpu_seconds=1.,wall_seconds=60.,bytes=raw.stat().st_size))
            (out / 'receipts.json').write_text(json.dumps(rows))
            with patch.object(report,'ROOT',root):
                result = report.audit(path)
                self.assertIn('sampling noise',result['verdict'])
                self.assertEqual(result['all_complete_window_tails']['control']['over50'],2560)
                raw.write_text(text + '\nHost_Error')
                with self.assertRaises(AssertionError): report.audit(path)


if __name__ == '__main__':
    unittest.main()
