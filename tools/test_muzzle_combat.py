import unittest
from pathlib import Path

from check_muzzle_combat import LABELS,check


def tape(failed=False):
    rows=['BHVRPL begin muzzle_combat','MCFIX begin dm4']
    for label in LABELS:
        if label.startswith('combat_'):
            n=int(label!='combat_blocked' or failed)
            rows.append(f'MCFIX outcome {label} gates 1 ammo {n} rockets {n} motor 80')
        if label=='embedded_contract':rows.append('MCFIX embedded fraction 1 startsolid 1 allsolid 1 allowed 1')
        rows.append(f'MCFIX check {label} {int(not(failed and label=="combat_blocked"))}')
    return '\n'.join(rows+[f'MCFIX end checks 6 ok {int(not failed)}'])


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


if __name__=='__main__':unittest.main()
