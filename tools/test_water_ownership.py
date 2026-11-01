"""Reject false private-observer ownership and preserve historical evidence."""
import hashlib
import json
from pathlib import Path
import unittest
from verify_water_ownership import CASES,inspect_fixture
from verify_water_route import inspect_fixture as inspect_route,require_outcome


def tape(legacy=False):
    s='BHVRPL begin water_ownership\nWRID begin dt_ms 14 layout 1\n'
    for i,name in enumerate(CASES,1):
        active=int(name=='owned' or (legacy and name=='task_only'))
        s+=f'WRID case {name}\nWRFIX sample t 0 pos \'0 0 0\' node \'0 0 0\' grounded 0 wet 0 feet 0 handoffs 0 active {active} hp 100 frames {i}\n'
    return s+'WRID end cases 4 cleanup 1\n'


class WaterOwnership(unittest.TestCase):
    def test_all_identity_combinations_and_real_failed_control(self):
        self.assertEqual(inspect_fixture(tape(),.0139)['failures'],[])
        self.assertEqual(inspect_fixture(tape(True),.0139)['failures'],['task_only'])
        self.assertEqual(inspect_fixture(tape().replace('dt_ms 14','dt_ms 100'),.1)['failures'],[])

    def test_missing_duplicate_reordered_or_dirty_observations_rejected(self):
        good=tape()
        for bad in (good+good,good.replace('layout 1','layout 2'),
                good.replace('cleanup 1','cleanup 0'),good.replace('frames 3','frames 4'),
                good.replace('WRID case task_only\n',''),good+'WRID extra\n'):
            with self.assertRaises(AssertionError):inspect_fixture(bad,.0139)

    def test_committed_observer_and_historical_hashes(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/water-ownership-v1.results.json').read_text(encoding='utf-8'))
        for row in proof['artifacts']:
            self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['sha256'])
        for row in proof['native']:
            result=inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'])
            self.assertEqual(result['failures'],['task_only'] if row['legacy'] else [])
        for row in proof['compatibility']:
            result=inspect_route((root/row['raw']).read_text(encoding='utf-8'),row['map'],.0139,row['case'])
            self.assertTrue(result['goal_identity_verified'])
            self.assertTrue(result['active'])
            require_outcome(result,False)
        audit=json.loads((root/proof['historical_audit']).read_text(encoding='utf-8'))
        self.assertEqual(len(audit['tapes']),47)
        for row in audit['tapes']:
            self.assertFalse(row['corrected_layout'])
            self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['git_sha256'])


if __name__=='__main__':unittest.main()
