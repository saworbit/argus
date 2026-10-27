"""Fail-closed physical entry evidence and read-only observer checks."""
import unittest
from pathlib import Path
from verify_offset_entry import check,audit_fixture


def tape():
    rows=['BHVRPL begin offset_entry',"OFFIX begin case 1 start '1361 33 320' solid 0"]
    for i in range(5):
        if i==4:rows.append("OFFIX contact t 0.8 pos '1361 -159 320' active 1")
        rows.append(f"OFFIX sample t {i*.2:.1f} pos '1361 {33-i*48} 320' active 1 from {int(i==0)} hp 100 frames {i*14+1}")
    return '\n'.join(rows+['OFFIX end ok 1','OFFIX cleanup owned_engine_pending_stop'])


class EntryTests(unittest.TestCase):
    def test_physical_contact_and_adversarial_receipts(self):
        self.assertTrue(check(tape(),1)['success'])
        for bad in ('BHVRPL begin offset_entry',tape().replace('contact','selection'),
                    tape().replace("'1361 -159 320'","'2000 -159 320'"),
                    tape().replace('hp 100','hp 90'),tape().replace('solid 0','solid 1'),
                    tape().replace('frames 15','frames 1'),
                    tape().replace('OFFIX cleanup owned_engine_pending_stop',''),
                    tape().replace('end ok 1','end ok 0')):
            with self.subTest(bad=bad[-80:]),self.assertRaises(AssertionError):check(bad,1)
        with self.assertRaises(AssertionError):check(tape(),2)

    def test_observer_cannot_drive_the_actor(self):
        source=Path(__file__).with_name('fixtures').joinpath('offset_entry.qc').read_text()
        audit_fixture(source)
        anchor='    oe_frames = oe_frames + 1;'
        for bad in ('walkmove (90,10);','oe_bot.ar_goal = oe_goal;',
                    'setorigin (self, oe_start);','Argus_PlanObserve (FALSE, oe_from);',
                    'oe_contact = time;','Argus_TacticReset ();'):
            with self.assertRaises(AssertionError):audit_fixture(source.replace(anchor,anchor+'\n'+bad))


if __name__=='__main__':unittest.main()
