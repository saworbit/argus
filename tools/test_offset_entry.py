"""Fail-closed physical entry evidence and read-only observer checks."""
import unittest
from pathlib import Path
from verify_offset_entry import check,audit_fixture,record_case,expected_success
from tempfile import TemporaryDirectory
import contextlib
import io
import json


def tape():
    rows=['BHVRPL begin offset_entry',"OFFIX begin case 1 start '1361 33 320' solid 0"]
    for i in range(5):
        if i==4:rows.append("OFFIX contact t 0.8 pos '1361 -159 320' active 1")
        rows.append(f"OFFIX sample t {i*.2:.1f} pos '1361 {33-i*48} 320' active 1 from {int(i==0)} hp 100 frames {i*14+1}")
    return '\n'.join(rows+['OFFIX end ok 1','OFFIX cleanup owned_engine_pending_stop'])


class EntryTests(unittest.TestCase):
    def receipt(self, case, success):
        starts={1:(1361,33,320),2:(1348,32,320),3:(1348.9,32,358.7),4:(1361,33,358.7)}
        x,y,z=starts[case]
        rows=['BHVRPL begin offset_entry',f"OFFIX begin case {case} start '{x} {y} {z}' solid 0"]
        for i in range(5):
            pos=f'{x} {y-i*48} {320 if i else z}'
            if success and i==4:rows.append(f"OFFIX contact t 0.8 pos '{pos}' active 1")
            active=int(success or i<4)
            rows.append(f"OFFIX sample t {i*.2:.1f} pos '{pos}' active {active} from {int(i==0)} hp 100 frames {i*14+1}")
        return '\n'.join(rows+[f'OFFIX end ok {int(success)}','OFFIX cleanup owned_engine_pending_stop'])

    def test_runner_rejects_a_control_that_no_longer_distinguishes_the_fix(self):
        with TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            out=Path(td);rows=[]
            record_case(out,rows,'current',3,self.receipt(3,True))
            with self.assertRaisesRegex(AssertionError,'expected contact=False'):
                record_case(out,rows,'old_handoff',3,self.receipt(3,True))
            saved=json.loads((out/'results.json').read_text())
            self.assertEqual(len(saved),2)
            self.assertTrue(saved[0]['accepted'])
            self.assertFalse(saved[1]['accepted'])
            self.assertTrue(saved[1]['success'])

    def test_declared_current_and_control_outcomes(self):
        with TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            for variant in ('current','old_handoff'):
                for case in (1,2,3,4):
                    expected=expected_success(variant,case)
                    self.assertEqual(expected,not(variant=='old_handoff' and case==3))
                    self.assertTrue(record_case(Path(td),[],variant,case,self.receipt(case,expected))['accepted'])

    def test_invalid_control_failure_is_retained_and_rejected(self):
        with TemporaryDirectory() as td,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(AssertionError,'invalid physical receipt'):
                record_case(Path(td),[],'old_handoff',3,self.receipt(3,False).replace('hp 100','hp 90'))
            saved=json.loads((Path(td)/'results.json').read_text())[0]
            self.assertFalse(saved['accepted'])
            self.assertIn('invalid physical receipt',saved['rejection'])

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
