import unittest
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from check_muzzle_combat import LABELS,check
from verify_muzzle_predicates import CASES,inspect_fixture


def tape(failed=False):
    rows=['BHVRPL begin muzzle_combat','MCFIX begin dm4']
    for label in LABELS:
        if label.startswith('combat_'):
            n=int(label!='combat_blocked' or failed)
            rows.append(f'MCFIX outcome {label} gates 1 ammo {n} rockets {n} motor 80')
        if label=='embedded_contract':rows.append('MCFIX embedded fraction 1 startsolid 1 allsolid 1 allowed 1')
        rows.append(f'MCFIX check {label} {int(not(failed and label=="combat_blocked"))}')
    return '\n'.join(rows+[f'MCFIX end checks 6 ok {int(not failed)}'])


def predicate_tape(legacy=False):
    rows=[tape(),'MPP begin dt_ms 14 layout 1']
    for index,label in enumerate(CASES):
        rows.append('MPSTATE '+label+' '+' '.join('0' if j==index else '1' for j in range(10)))
        rows.append(f'MPOUTCOME {label} gates {int(label!="gates")} ammo 1 rockets 1 motor 176')
        rows.append(f'MPCHECK {label} {int(legacy and index>0)}')
    return '\n'.join(rows+['MPP end rows 10'])


class CombatTests(unittest.TestCase):
    def test_current_and_negative_control_receipts(self):
        self.assertEqual(check(tape())['failures'],[])
        self.assertEqual(check(tape(True))['failures'],['combat_blocked'])
        self.assertEqual(check(tape())['embedded'],('1','1','1','1'))
        for bad in (tape()+tape(),tape().replace('gates 1','gates 0'),
                    tape().replace('combat_blocked gates 1 ammo 0 rockets 0','combat_blocked gates 1 ammo 1 rockets 1'),
                    tape().replace('startsolid 1','startsolid 0'),tape().replace('ok 1','ok 0'),
                    tape().replace('MCFIX check cleanup 1',''),tape()+'\nMCFIX unknown'):
            with self.assertRaises(AssertionError):check(bad)

    def test_fixture_reaches_real_combat_and_keeps_embedded_fire_separate(self):
        text=Path(__file__).with_name('fixtures').joinpath('muzzle_combat.qc').read_text()
        self.assertIn('owned = Argus_Combat ();',text)
        self.assertIn('self.ar_moveyaw == mc_motor',text)
        self.assertNotIn('W_Attack (',text)
        self.assertIn('self.ar_seen == time',text)
        self.assertIn('pointcontents (mc_embed) == CONTENT_SOLID',text)

    def test_each_negative_has_one_false_independent_premise(self):
        good=predicate_tape()
        self.assertEqual(inspect_fixture(good,.0139)['failures'],[])
        self.assertEqual(inspect_fixture(predicate_tape(True),.0139)['failures'],list(CASES[1:]))
        for bad in (good+good,good.replace('layout 1','layout 2'),
                good.replace('MPSTATE seen 1 1 0','MPSTATE seen 1 1 1'),
                good.replace('MPCHECK seen 0\n',''),good+'\nMPP unknown',
                good.replace('MPOUTCOME enemy gates 1 ammo 1','MPOUTCOME enemy gates 1 ammo 0'),
                good.replace('rows 10','rows 9'),good.replace('dt_ms 14','dt_ms 0')):
            with self.assertRaises(AssertionError):inspect_fixture(bad,.0139)

    def test_optimized_child_rejects_inconsistent_ammo_receipt(self):
        child=subprocess.run([sys.executable,'-O','-c',
            'import sys; from check_muzzle_combat import check; check(sys.stdin.read())'],
            input=tape().replace('combat_blocked gates 1 ammo 0','combat_blocked gates 1 ammo 1'),
            text=True,capture_output=True,cwd=Path(__file__).parent,timeout=10)
        self.assertNotEqual(child.returncode,0,child.stdout)
        self.assertIn('AssertionError',child.stderr)

    def test_retained_native_predicates_and_artifact_hashes(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/muzzle-predicates-v1.results.json').read_text(encoding='utf-8'))
        for artifact in proof['artifacts']:
            self.assertEqual(hashlib.sha256((root/artifact['path']).read_bytes()).hexdigest(),artifact['sha256'])
        self.assertEqual(len(proof['native']),4)
        for row in proof['native']:
            result=inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'])
            self.assertEqual(result['failures'],list(CASES[1:]) if row['variant']=='legacy' else [])
        with self.assertRaisesRegex(AssertionError,'wrong measured cadence'):
            inspect_fixture((root/proof['rejected_setup']['raw']).read_text(encoding='utf-8'),.0139)


if __name__=='__main__':unittest.main()
