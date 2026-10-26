import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import stats

import report_perception_lava as report
from run_perception_lava import valid_tape


class LavaTests(unittest.TestCase):
    def test_direction_noninferiority_and_small_real_increase(self):
        n = report.PAIRS; seconds = np.full(n,60.); control = np.tile([1,0,0,0],n//4)
        result = report.evaluate(control,control,seconds,seconds)
        self.assertIn('sampling noise',result['verdict'])
        candidate = control + (np.arange(n)%16==0)
        result = report.evaluate(control,candidate,seconds,seconds)
        self.assertTrue(result['regression_confirmed'])
        self.assertTrue(result['practical_noninferiority'])  # small real harm is still a regression
        result = report.evaluate(control+2,control,seconds,seconds)
        self.assertIn('decrease',result['verdict'])

    def test_nonsignificance_and_t_only_increase_are_not_noise(self):
        n=report.PAIRS; seconds=np.full(n,60.)
        result=report.evaluate(np.full(n,10),np.tile([0,20],n//2),seconds,seconds)
        self.assertEqual(result['verdict'],'inconclusive')
        control=np.tile([1,0,0,0],n//4); candidate=control+(np.arange(n)<8)
        result=report.evaluate(control,candidate,seconds,seconds)
        self.assertGreater(result['ci95'][0],0)
        self.assertEqual(result['verdict'],'paired-test increase; block sensitivity inconclusive')

    def test_rare_event_zero_and_invalid_inputs(self):
        n=report.PAIRS; seconds=np.full(n,60.); zeros=np.zeros(n)
        self.assertIn('insufficient',report.evaluate(zeros,zeros,seconds,seconds)['verdict'])
        self.assertIsNone(report.exact_poisson_support(0,0,256,256)['pvalue'])
        for counts in (np.full(n,-1),np.full(n,.5),np.full(n,np.nan),zeros[:-1]):
            with self.assertRaises(AssertionError):report.evaluate(zeros,counts,seconds,seconds)
        with self.assertRaises(AssertionError):report.evaluate(zeros,zeros,seconds,np.full(n,57.9))

    def test_independent_scipy_intervals_exposure_and_poisson_support(self):
        n=report.PAIRS;rng=np.random.default_rng(34)
        a=rng.poisson(.3,n);b=rng.poisson(.5,n);sa=rng.uniform(58.5,61,n);sb=rng.uniform(58.5,61,n)
        result=report.evaluate(a,b,sa,sb);t=stats.ttest_rel(b*60/sb,a*60/sa)
        for level,key in ((.9,'ci90'),(.95,'ci95')):
            expected=t.confidence_interval(level);np.testing.assert_allclose(result[key],[expected.low,expected.high])
        first=report.exact_poisson_support(20,45,128,128);second=report.exact_poisson_support(45,20,128,128)
        self.assertAlmostEqual(first['rate_ratio'],2.25);self.assertGreater(first['ci95'][0],1)
        np.testing.assert_allclose(first['ci95'],[1/second['ci95'][1],1/second['ci95'][0]])

    def test_complete_audit_and_tamper_detection(self):
        scratch=Path(__file__).resolve().parents[1]/'backups';scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root=Path(folder);out=root/'study';out.mkdir();(root/'runs').mkdir()
            p=dict(output='study',prefix='unit',pairs=256,seconds=60,skill=1,harm_margin_per_minute=.1,
                registered_utc='2020-01-01T00:00:00+00:00',shipped_sha256='shipped',code_sha256={},
                resources_sha256={},identity={},protected_binaries=[],binaries={m:dict(sha256=m,source_sha256=m) for m in ('control','candidate')})
            path=root/'protocol.json';path.write_text(json.dumps(p));sha=report.digest(path)
            (out/'protocol.sha256').write_text(sha)
            (out/'execution.json').write_text(json.dumps(dict(status='complete',completed=512,restored_sha256='shipped',protocol_sha256=sha)))
            text='\n'.join(f'BHVTIME t {i*5} frames 350 seconds 5 mean_ms 14.3 max_ms 100 over20 4 over50 2' for i in range(1,11))
            rows=[]
            for name,mode,repeat in report.schedule('unit'):
                raw=root/f'runs/{name}.log';raw.write_text(text)
                totals=dict.fromkeys(('engages','goals','frags','deaths','stalls','freezes','acquisitions','grabs'),1)
                totals.update(duration_sec=60.,tick_class='listen',lava_rule='contents',lava_deaths=int(repeat%4==0))
                rows.append(dict(name=name,mode=mode,repeat=repeat,protocol_sha256=sha,
                    identity=dict(binary_sha256=mode),executed_source_sha256=mode,
                    brief=dict(map='dm2',totals=totals,lab_identity=dict(authoritative=True),flags=[]),
                    raw_sha256=report.digest(raw),valid=True,started_utc='2021-01-01T00:00:00+00:00',
                    stopped_utc='2021-01-01T00:01:00+00:00',timing=valid_tape(dict(map='dm2',totals=totals,flags=[]),text),
                    cpu_seconds=1.,wall_seconds=60.))
            receipt=out/'receipts.json';receipt.write_text(json.dumps(rows))
            with patch.object(report,'ROOT',root):
                result=report.audit(path);self.assertIn('sampling noise',result['verdict'])
                self.assertEqual(result['all_complete_window_tails']['candidate']['over50'],5120)
                receipt.write_text(json.dumps(rows[:-1]))
                with self.assertRaises(AssertionError):report.audit(path)
                receipt.write_text(json.dumps(rows));raw.write_text(text+'\nHost_Error')
                with self.assertRaises(AssertionError):report.audit(path)


if __name__=='__main__':unittest.main()
