"""A transfer receipt must describe exactly one measured physical task."""
import unittest
from pathlib import Path

from verify_mover_transfer import audit_fixture, inspect_fixture


def receipt(frame_ms=14, completed=1):
    return (f'ARGUS init on e1m6\nBHVRPL begin mover_transfer\nMVFIX begin dt_ms {frame_ms}\n'
            f'MVFIX result completed {completed} seconds 4.1 boarded 1 route_retained 1 '
            "dry 1 alive 1 launches 1 bad_launch 0 landed 1 handoff 1 pos '529 1393 344'\n")


class TransferReceipts(unittest.TestCase):
    def test_both_rates_preserve_physical_outcome(self):
        for rate, ms in ((.0139, 14), (.1, 100)):
            row = inspect_fixture(receipt(ms), 'e1m6', rate)
            self.assertTrue(row['completed'] and row['boarded'] and row['route_retained'])
            self.assertEqual(row['frame_ms'], ms)
            self.assertEqual(row['launches'], 1)

    def test_failed_control_is_a_measurement_not_a_missing_result(self):
        self.assertFalse(inspect_fixture(receipt(completed=0), 'e1m6', .0139)['completed'])

    def test_landing_alone_cannot_claim_continuing_route_completion(self):
        for field in ('landed', 'handoff', 'route_retained'):
            with self.assertRaises(AssertionError):
                inspect_fixture(receipt().replace(field + ' 1', field + ' 0'), 'e1m6', .0139)

    def test_observer_refuses_actor_mutations_and_steering(self):
        source = (Path(__file__).parent / 'fixtures/mover_transfer.qc').read_text(encoding='utf-8')
        audit_fixture(source)
        for mutation in ('mv_bot.velocity_x = 320;', 'setorigin (mv_bot, mv_exit);',
                         'Argus_AI ();'):
            with self.assertRaises(AssertionError):
                audit_fixture(source.replace('    if (!mv_started || mv_done) return;', mutation))

    def test_duplicate_missing_wrong_map_and_engine_failure_refuse(self):
        good = receipt()
        for text in (good + good, good.replace('MVFIX result', 'missing'),
                     good.replace('begin dt_ms', 'missing'), good.replace('on e1m6', 'on dm3'),
                     good + 'Program error\n', receipt(100)):
            with self.subTest(text=text):
                with self.assertRaises(AssertionError):
                    inspect_fixture(text, 'e1m6', .0139)


if __name__ == '__main__':
    unittest.main()
