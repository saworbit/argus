"""Require physical hull witnesses and complete nudge/route outcomes."""
import hashlib
import json
from pathlib import Path
import re
import unittest
from verify_body_nudge import CASES,LABELS,inspect_fixture


def tape():
    return ('BHVRPL begin body_nudge\nBNFIX begin dt_ms 14 layout 1\n'+
        ''.join(f'BNCASE {n} initialfit {int(not n.startswith("overlap_"))} finalfit 1 distance {dict(clear_step=3,overlap_axis=16,overlap_diagonal=22.6).get(n,0)} dodge 0\n' for n in CASES)+
        ''.join(f'BNCHECK {n} 1\n' for n in LABELS)+
        'BNFIX end checks 10 failures 0 seconds   1.0 frames 70\n'
        "BNRESULT pos '632.8 182.8 -200' lost 0 discontinuous 0 hp 100 wet 0\n")


class BodyNudge(unittest.TestCase):
    def test_physical_outcome_and_both_tick_profiles(self):
        self.assertEqual(inspect_fixture(tape(),.0139)['failures'],[])
        slow=tape().replace('dt_ms 14','dt_ms 100').replace('frames 70','frames 11')
        self.assertEqual(inspect_fixture(slow,.1)['failures'],[])

    def test_invalid_placement_false_markers_and_missing_witnesses_rejected(self):
        good=tape()
        for bad in (good+good,good.replace('layout 1','layout 2'),
                good.replace('initialfit 1','initialfit 0'),good.replace('finalfit 1','finalfit 0'),
                good.replace('discontinuous 0','discontinuous 1'),good.replace('lost 0','lost 1'),
                good.replace('frames 70','frames 5'),good.replace('632.8','0'),
                good.replace('BNCHECK wall_refused 1\n','')):
            with self.assertRaises(AssertionError):inspect_fixture(bad,.0139)
        failed=good.replace('BNCASE wall_refused initialfit 1 finalfit 1 distance 0',
            'BNCASE wall_refused initialfit 1 finalfit 0 distance 3').replace('BNCHECK wall_refused 1','BNCHECK wall_refused 0').replace('failures 0','failures 1')
        self.assertEqual(inspect_fixture(failed,.0139)['failures'],['wall_refused'])

    def test_observer_has_no_movement_or_ownership_writes(self):
        text=Path(__file__).with_name('fixtures').joinpath('body_nudge.qc').read_text(encoding='utf-8')
        observer=text.split('void() BodyNudgeAfter =',1)[1].split('    if (completed ||',1)[0]
        self.assertIsNone(re.search(r'\b(?:setorigin|walkmove|droptofloor|Argus_\w+)\s*\(',observer))
        self.assertIsNone(re.search(r'\bbn_bot\.\w+\s*=(?!=)',observer))

    def test_committed_physical_and_ordinary_artifact_identities(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/body-nudge-v1.results.json').read_text(encoding='utf-8'))
        for row in proof['artifacts']:
            self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['sha256'])
        for row in proof['physical']:
            result=inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'])
            self.assertEqual(result['failures'],row['failures'])
            self.assertEqual(bool(result['failures']),row['failed_control'])
            if not row['failed_control']:self.assertEqual(row['rescues'],0)
        audit=proof['superseded']['physical_audit']
        self.assertEqual(inspect_fixture((root/audit['raw']).read_text(encoding='utf-8'),audit['ticrate'])['failures'],['overlap_diagonal'])
        protocol=proof['protocol']
        self.assertEqual(len(proof['ordinary']),len(protocol['schedule']))
        for map_name in protocol['maps']:
            for arm in ('control','candidate'):
                self.assertEqual(sorted(r['repeat'] for r in proof['ordinary']
                    if r['map']==map_name and r['arm']==arm),[1,2,3])
        for row in proof['ordinary']:
            for key in ('source_sha256','binary_sha256'):
                self.assertEqual(row[key],protocol['arms'][row['arm']][key])
            initial={}
            for m in re.finditer(r'^ARGUS difficulty (.+?) t\s+[\d.]+ base\s+([\d.]+) cognition\s+([\d.]+)',(root/row['raw']).read_text(encoding='utf-8'),re.M):
                initial.setdefault(m[1],(float(m[2]),float(m[3])))
            self.assertEqual(len(initial),3)
            self.assertEqual(set(initial.values()),{(2,2)})


if __name__=='__main__':unittest.main()
