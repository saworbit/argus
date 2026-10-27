import unittest
from pathlib import Path
from check_door_actuator import LABELS,DIRECT_ONLY_FAILURES,check,audit


def tape(failures=()):
    return 'BHVRPL begin door_actuator\nDAFIX begin dm2\n'+''.join(
        f'DAFIX check {label} {int(label not in failures)}\n' for label in LABELS)+f'DAFIX end checks {len(LABELS)} ok {int(not failures)}\n'


class DoorTests(unittest.TestCase):
    def test_current_and_direct_only_receipts(self):
        self.assertEqual(check(tape(),'dm2'),[])
        self.assertEqual(check(tape(DIRECT_ONLY_FAILURES),'dm2'),DIRECT_ONLY_FAILURES)
        for bad in (tape()+tape(),tape().replace('check cleanup 1\n',''),
                    tape().replace('ok 1','ok 0'),tape()+'DAFIX unknown\n',
                    tape().replace('cycle_is_bounded','direct_button')):
            with self.assertRaises(AssertionError):check(bad,'dm2')
        with self.assertRaises(AssertionError):check(tape(),'e1m2')

    def test_opener_search_has_no_gameplay_mutations_and_is_bounded(self):
        source=(Path(__file__).resolve().parents[1]/'src/argus.qc').read_text()
        self.assertTrue(audit(source))
        for old,new in [('depth > 4','FALSE'),
                        ('argus_door_search_budget <= 0','FALSE'),
                        ('bd = 1024;','bd = 999999;'),
                        ('b.state == STATE_BOTTOM','FALSE'),
                        ('best = world; bd = 1024;','self.ar_goal = world; best = world; bd = 1024;')]:
            with self.assertRaises(AssertionError):audit(source.replace(old,new))


if __name__=='__main__':unittest.main()
