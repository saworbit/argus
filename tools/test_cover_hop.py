"""Cover annotations cannot bypass a missing, typed or deliberate-drop hop."""
from pathlib import Path
import hashlib
import json
import re
import unittest
from verify_cover_hop import LABELS, inspect_fixture


def receipt(ms=14):
    return ('ARGUS init on dm4\nBHVRPL begin cover_hop\n'
        f'CHFIX begin dt_ms {ms} layout 1\n' +
        ''.join(f'CHFIX check {name} 1\n' for name in LABELS) +
        f'CHFIX end checks {len(LABELS)} failures 0\n')


class CoverHop(unittest.TestCase):
    def test_committed_controls_and_cost_cohort_are_not_relabelled(self):
        root=Path(__file__).resolve().parents[1]
        e=json.loads((root/'runs/cover-hop-v2.results.json').read_text(encoding='utf-8'))
        for row in e['cases']+e['negative_controls']+e['cost_cases']:
            self.assertEqual(hashlib.sha256((root/row['raw']).read_bytes()).hexdigest(),row['raw_sha256'])
        for row in e['cases']:
            self.assertEqual(inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'],row['map'])['checks'],15)
        for row in e['negative_controls']:
            with self.assertRaises(AssertionError):
                inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'],row['map'])
        self.assertEqual(e['cost_verdict'],'Approved')
        self.assertEqual(sorted((r['arm'],r['repeat']) for r in e['cost_cases']),
            [(a,i) for a in ('candidate','control') for i in (1,2,3)])
        self.assertTrue(all(r['totals']['freeze_underfire']==0 for r in e['cost_cases']))

    def test_shipped_cover_hops_meet_the_runtime_contract(self):
        root=Path(__file__).resolve().parents[1]
        checked=0
        for path in sorted((root/'src').glob('argus_nav_*.qc')):
            text=path.read_text(encoding='utf-8')
            nodes={m[1]:float(m[2].split()[2]) for m in
                re.finditer(r"(n\d+) = Argus_NavNode \('([^']+)'\)",text)}
            kinds={}
            for m in re.finditer(r'Argus_NavLink(\w*) \((n\d+), (n\d+)',text):
                kinds.setdefault((m[2],m[3]),set()).add(m[1])
            for node,hop in re.findall(r'Argus_NavTactics \((n\d+), [\d.]+, n\d+, (n\d+)\)',text):
                checked+=1
                with self.subTest(graph=path.name,node=node,hop=hop):
                    self.assertEqual(kinds.get((node,hop)),{''})
                    self.assertLessEqual(nodes[node]-nodes[hop],18)
        self.assertGreater(checked,1000)

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
