import unittest
from pathlib import Path
from check_muzzle_fixture import check,audit,LABELS

class MuzzleTests(unittest.TestCase):
    def test_strict_records(self):
        text='BHVRPL begin muzzle_fixture\nMFIX begin dm4 dt_ms 100\n'+''.join(f'MFIX check {label} 1\n' for label in LABELS)+'MFIX end checks 14 ok 1\n'
        self.assertEqual(check(text),[])
        for bad in [text.replace('MFIX check cleanup 1\n',''),text+text,text.replace('ok 1','ok 0'),text+'MFIX unknown\n']:
            with self.assertRaises(AssertionError):check(bad)
        self.assertEqual(check(text.replace('ordinary_wall 1','ordinary_wall 0').replace('ok 1','ok 0')),['ordinary_wall'])

    def test_production_callsite_and_mutations(self):
        source=(Path(__file__).resolve().parents[1]/'src/argus.qc').read_text()
        self.assertTrue(audit(source))
        for bad in [source.replace('if (!Argus_MuzzleClear (aimpt))','if (FALSE)'),
                    source.replace('if (targetdist < reach) reach = targetdist;','reach = 240;'),
                    source.replace('!self.ar_tactic && self.weapon != IT_ROCKET_LAUNCHER','!self.ar_tactic')]:
            with self.assertRaises(AssertionError):audit(bad)
        early='        self.v_angle_y = self.angles_y;\n        if (!Argus_MuzzleClear (aimpt))\n            return TRUE;'
        late='        if (!Argus_MuzzleClear (aimpt))\n            return TRUE;\n        self.v_angle_y = self.angles_y;'
        self.assertEqual(source.count(early),1)
        with self.assertRaises(AssertionError):audit(source.replace(early,late))

if __name__=='__main__':unittest.main()
