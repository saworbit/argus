"""Observer truth requires all identity and liquid clauses, not just markers."""
import hashlib
import json
from pathlib import Path
import unittest
from verify_mover_predicates import CASES,LIQUID,inspect_fixture
from verify_mover_transfer import inspect_fixture as inspect_transfer
from verify_mover_forecast import inspect_fixture as inspect_forecast


def tape(variant='current'):
    text='BHVRPL begin mover_predicates\nMPP begin dt_ms 14 layout 1\n'
    for family,label in CASES:
        owned=label not in ('missing_task','missing_goal','neither','missing_node')
        dry=label not in LIQUID
        if variant=='legacy_retention' and label in ('missing_task','missing_node'):owned=True
        if variant=='legacy_dry' and label in LIQUID[:3]:dry=True
        text+=f'MVPRED {family} {label} retained {int(owned)} dry {int(dry)} lost {int(not owned)}\n'
        if family=='forecast':text+=f'MPLATCH {label} dry {int(dry)} lost {int(not owned)}\n'
    return text+'MPP end rows 17 cleanup 1\n'


class MoverPredicates(unittest.TestCase):
    def test_independent_retention_and_dryness_controls(self):
        self.assertEqual(inspect_fixture(tape(),.0139)['failures'],[])
        self.assertEqual(inspect_fixture(tape('legacy_retention'),.0139)['failures'],
            ['transfer:missing_task','forecast:missing_task','forecast:missing_node'])
        self.assertEqual(len(inspect_fixture(tape('legacy_dry'),.0139)['failures']),6)
        self.assertEqual(inspect_fixture(tape().replace('dt_ms 14','dt_ms 100'),.1)['failures'],[])

    def test_missing_duplicate_corrupt_latches_and_cleanup_rejected(self):
        good=tape()
        for bad in (good+good,good.replace('layout 1','layout 2'),
                good.replace('cleanup 1','cleanup 0'),good.replace('rows 17','rows 16'),
                good.replace('MPLATCH owned dry 1 lost 0','MPLATCH owned dry 0 lost 0'),
                good+'MVPRED unknown\n',good+'MPLATCH unknown\n',good+'MPP unknown\n',
                good.replace('MVPRED transfer owned retained 1 dry 1 lost 0\n','')):
            with self.assertRaises(AssertionError):inspect_fixture(bad,.0139)

    def test_committed_observer_and_qualified_historical_hashes(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/mover-predicates-v1.results.json').read_text(encoding='utf-8'))
        for row in proof['artifacts']:
            self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['sha256'])
        for row in proof['native']:
            result=inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'])
            self.assertEqual(result['failures'],row['failures'])
        self.assertEqual(len(proof['transfers']),4)
        self.assertEqual(len(proof['forecasts']),10)
        for row in proof['transfers']:
            result=inspect_transfer((root/row['raw']).read_text(encoding='utf-8'),row['map'],row['ticrate'],require_current=True)
            self.assertTrue(result['completed'] and result['forward_proven'] and result['observer_predicates_verified'])
            self.assertEqual(row['unstick_warps'],0)
        for row in proof['forecasts']:
            result=inspect_forecast((root/row['raw']).read_text(encoding='utf-8'),row['case'],row['ticrate'])
            self.assertTrue(result['observer_predicates_verified'])
        audit=json.loads((root/proof['historical_audit']).read_text(encoding='utf-8'))
        for row in audit['tapes']:
            self.assertFalse(row['corrected_predicate_layout'])
            self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['git_sha256'])


if __name__=='__main__':unittest.main()
