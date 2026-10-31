"""A transfer receipt must describe exactly one measured physical task."""
import unittest

from verify_mover_transfer import inspect_fixture


def receipt(frame_ms=14, completed=1):
    return (f'ARGUS init on e1m6\nMVFIX begin dt_ms {frame_ms}\n'
            f'MVFIX result completed {completed} seconds 4.1 boarded 1 route_retained 1 '
            "dry 1 alive 1 launches 1 bad_launch 0 pos '529 1393 344'\n")


class TransferReceipts(unittest.TestCase):
    def test_both_rates_preserve_physical_outcome(self):
        for rate, ms in ((.0139, 14), (.1, 100)):
            row = inspect_fixture(receipt(ms), 'e1m6', rate)
            self.assertTrue(row['completed'] and row['boarded'] and row['route_retained'])
            self.assertEqual(row['frame_ms'], ms)
            self.assertEqual(row['launches'], 1)

    def test_failed_control_is_a_measurement_not_a_missing_result(self):
        self.assertFalse(inspect_fixture(receipt(completed=0), 'e1m6', .0139)['completed'])

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
