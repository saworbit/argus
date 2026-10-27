import unittest
from pathlib import Path
from check_button_physical import check,audit


def tape(active=True):
    rows=['BHVRPL begin button_physical',"BPFIX begin case 1 start '-45.0 288.0 320.0'"]
    for i,x in enumerate((-45,-100,-170)):
        rows.append(f"BPFIX sample t {i*.2:.1f} pos '{x}.0 288.0 320.0' state {0 if active and i else 1} touches {int(active and i>0)} support {int(i==1)} grounded 1 hp 100 frames {i*14+1}")
    return '\n'.join(rows+[f'BPFIX end touched {int(active)} activated {int(active)} owner {int(active)} ctx 1 support 1','BPFIX cleanup owned_engine_pending_stop'])


class ButtonTests(unittest.TestCase):
    def test_current_and_mutated_motor_outcomes(self):
        self.assertTrue(check(tape(),1,True)['activated'])
        self.assertFalse(check(tape(False),1,False)['activated'])
        self.assertTrue(check(tape().replace('-170.0','-160.0'),1,True)['activated'])
        for bad in (tape()+tape(),tape().replace('ctx 1','ctx 0'),
                    tape().replace('cleanup owned_engine_pending_stop','cleanup missing'),
                    tape().replace('hp 100','hp 90'),tape().replace('frames 15','frames 1'),
                    tape().replace('-170.0','-100.0'),tape().replace('-100.0','-1000.0'),
                    tape().replace('ctx 1 support 1','ctx 1 support 0')):
            with self.assertRaises(AssertionError):check(bad,1,True)
        with self.assertRaises(AssertionError):check(tape(False),1,True)

    def test_printed_clock_boundary_keeps_decimal_rounding(self):
        text=tape().replace('t 0.2','t 0.8').replace('t 0.4','t 1.1')
        text=text.replace('t 0.8', 't 0.2')
        # Insert the intermediate stationary rows needed for the longer clock.
        anchor="BPFIX sample t 1.1"
        sample="BPFIX sample t {t} pos '-100.0 288.0 320.0' state 0 touches 1 support 1 grounded 1 hp 100 frames {frames}\n"
        text=text.replace(anchor,''.join(sample.format(t=t,frames=n) for t,n in ((.4,18),(.6,20),(.8,22)))+anchor)
        self.assertTrue(check(text,1,True)['activated'])
        with self.assertRaises(AssertionError):check(text.replace('t 1.1','t 1.2'),1,True)

    def test_support_guard_and_passive_observer(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'src/argus.qc').read_text()
        fixture=(root/'tools/fixtures/button_physical.qc').read_text()
        self.assertTrue(audit(source,fixture))
        for old in ('button = self.groundentity;','self = bot;','other = savedother;',
                    'activator = savedactivator;','button.state != STATE_BOTTOM'):
            with self.assertRaises(AssertionError):audit(source.replace(old,''),fixture)
        with self.assertRaises(AssertionError):
            audit(source,fixture.replace('    bp_frames = bp_frames + 1;',
                '    bp_frames = bp_frames + 1;\n    bp_actor.velocity = \'0 0 0\';'))


if __name__=='__main__':unittest.main()
