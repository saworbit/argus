"""Cover annotations cannot bypass a missing, typed or deliberate-drop hop."""
from pathlib import Path
import hashlib
import json
import unittest
from verify_cover_hop import LABELS, inspect_fixture


def receipt(ms=14):
    return ('ARGUS init on dm4\nBHVRPL begin cover_hop\n'
        f'CHFIX begin dt_ms {ms} layout 1\n' +
        ''.join(f'CHFIX check {name} 1\n' for name in LABELS) +
        f'CHFIX end checks {len(LABELS)} failures 0\n')


class CoverHop(unittest.TestCase):
    def test_retained_controls_and_rejected_cohort_are_not_relabelled(self):
        root=Path(__file__).resolve().parents[1]
        e=json.loads((root/'runs/cover-hop-v1.results.json').read_text(encoding='utf-8'))
        for row in e['cases']+e['negative_controls']+e['cost_cases']:
            self.assertEqual(hashlib.sha256((root/row['raw']).read_bytes()).hexdigest(),row['raw_sha256'])
        for row in e['cases']:
            self.assertEqual(inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'],row['map'])['checks'],15)
        self.assertEqual(e['cost_verdict'],'Rejected')
        failed=[r for r in e['cost_cases'] if r['arm']=='candidate' and r['repeat']==2][0]
        self.assertEqual(failed['totals']['freeze_underfire'],1)

    def test_both_cadences_and_every_predicate_control(self):
        for rate,ms in ((.0139,14),(.1,100)):
            self.assertEqual(inspect_fixture(receipt(ms),rate)['checks'],len(LABELS))

    def test_no_missing_failed_or_wrong_map_control(self):
        good=receipt()
        for bad in (good+good,good.replace('CHFIX check jump 1',''),
                good.replace('CHFIX check jump 1','CHFIX check jump 0'),
                good.replace('on dm4','on dm2'),good.replace('layout 1','layout 2')):
            with self.assertRaises(AssertionError):inspect_fixture(bad,.0139)

    def test_combat_checks_the_hint_before_reading_its_heading(self):
        source=(Path(__file__).resolve().parents[1]/'src/argus.qc').read_text(encoding='utf-8')
        guard=source.index('&& Argus_CoverHopOK (cnode, cnode.an_coverhop)')
        assignment=source.index('chop = cnode.an_coverhop;')
        self.assertLess(guard,assignment)


if __name__=='__main__':unittest.main()
