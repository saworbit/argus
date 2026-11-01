"""Fail closed on incomplete ownership evidence and preserve failed controls."""
import hashlib
import json
from pathlib import Path
import unittest

from verify_stall_ownership import LABELS,inspect_fixture


def receipt(ms=14):
    return ('BHVRPL begin stall_ownership\n'+f'SWCHECK begin dt_ms {ms} layout 1\n'+
        ''.join(f'SWCHECK {name} 1\n' for name in LABELS)+f'SWCHECK end checks {len(LABELS)} failures 0\n')


class StallOwnership(unittest.TestCase):
    def test_both_cadences_require_every_case(self):
        for rate,ms in ((.0139,14),(.1,100)):
            self.assertEqual(inspect_fixture(receipt(ms),rate)['failures'],[])

    def test_failed_control_is_retained_without_acceptance(self):
        text=receipt().replace('stationary_jump_released 1','stationary_jump_released 0').replace('failures 0','failures 1')
        self.assertEqual(inspect_fixture(text,.0139)['failures'],['stationary_jump_released'])

    def test_missing_repeated_wrong_layout_and_wrong_totals_are_rejected(self):
        good=receipt()
        for text in (good+good,good.replace('layout 1','layout 2'),
                good.replace('SWCHECK gait_tail 1\n',''),good.replace('failures 0','failures 1'),
                good.replace('dt_ms 14','dt_ms 100')):
            with self.assertRaises(AssertionError):inspect_fixture(text,.0139)

    def test_committed_decision_controls_and_ordinary_band_identities(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/stall-ownership-v1.results.json').read_text(encoding='utf-8'))
        for artifact in proof['artifacts']:
            self.assertEqual(hashlib.sha256((root/artifact['path']).read_bytes()).hexdigest(),artifact['sha256'])
        for row in proof['decisions']:
            result=inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'])
            self.assertEqual(bool(result['failures']),row['failed_control'])
        self.assertEqual(len(proof['ordinary']),12)
        for map_name in ('dm3','e1m6'):
            for arm in ('control','candidate'):
                self.assertEqual(sorted(r['repeat'] for r in proof['ordinary'] if r['map']==map_name and r['arm']==arm),[1,2,3])


if __name__=='__main__':unittest.main()
