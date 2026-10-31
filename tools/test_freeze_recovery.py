"""The physical-regression receipt must not silently lose a guard or cadence."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_freeze_recovery import CORE_LABELS, GUARD_LABELS, inspect_fixture


def receipt(candidate=True, frame_ms=14):
    labels = list(CORE_LABELS) + (list(GUARD_LABELS) if candidate else [])
    if not candidate:
        labels[0] = 'control_reproduces_pin'
    return (f'FRFIX begin dt_ms {frame_ms}\nFRFIX result maxmove 70 exit_sec 1.8 shots 6\n'
            + ''.join(f'FRFIX check {label} 1\n' for label in labels)
            + f'FRFIX end checks {len(labels)} failures 0\n')


class RecoveryReceipts(unittest.TestCase):
    def test_both_arms_and_cadences(self):
        for candidate in (False, True):
            for ticrate, ms in ((.0139, 14), (.1, 100)):
                result = inspect_fixture(receipt(candidate, ms), candidate, ticrate)
                self.assertFalse(result['failures'])
                self.assertEqual(result['frame_ms'], ms)

    def test_missing_or_duplicated_guard_cannot_pass(self):
        text = receipt()
        for broken in (text.replace('FRFIX check live_body_cancels_exit 1\n', ''),
                       text.replace('live_body_cancels_exit', 'mover_wait_held'),
                       text.replace('FRFIX end checks 16 failures 0', ''),
                       text + text, text.replace('FRFIX result', 'no result')):
            with self.assertRaises(AssertionError):
                inspect_fixture(broken, True, .0139)

    def test_wrong_rate_and_engine_failure_cannot_pass(self):
        for text in (receipt(frame_ms=100), receipt() + 'Program error\n'):
            with self.assertRaises(AssertionError):
                inspect_fixture(text, True, .0139)

    def test_failure_is_retained(self):
        text = receipt().replace('still_shoots 1', 'still_shoots 0').replace('failures 0', 'failures 1')
        self.assertEqual(inspect_fixture(text, True, .0139)['failures'], ['still_shoots'])

    def test_rescue_contract_retains_measured_warp_and_visibility_checks(self):
        text = receipt().replace('walks_out_before_freeze', 'rescues_pin_before_freeze')
        text = text.replace('continuous_motion', 'bounded_rescue_count').replace('still_shoots', 'fire_when_visible')
        self.assertFalse(inspect_fixture(text, True, .0139, rescue=True)['failures'])
        with self.assertRaises(AssertionError):
            inspect_fixture(text, True, .0139)

    def test_underfire_rescues_remain_visible_in_existing_scorecard(self):
        from argus_longi import analyse
        with TemporaryDirectory() as folder:
            log = Path(folder) / 'recovery.log'
            log.write_text("ARGUS init on e1m1\nARGEVT Joe Rogan spawned\n"
                "ARGLOG Joe Rogan t 1 pos '0 0 24' spd 0 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
                "ARGUS Joe Rogan unstick underfire '64 0 24'\n"
                "ARGLOG Joe Rogan t 2 pos '64 0 24' spd 100 yaw 0 mode 2 st 0 gl 0 hp 80 frg 0\n")
            self.assertEqual(analyse(log)['unstick'], 1)


if __name__ == '__main__':
    unittest.main()
