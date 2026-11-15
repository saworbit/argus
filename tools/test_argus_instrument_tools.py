#!/usr/bin/env python3
"""Tests for the instrument validation tools: argus_clock_validation.py and
argus_standin_calibration.py (their statistics and their tape reading)."""
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_clock_validation as clock  # noqa: E402
import argus_standin_calibration as cal  # noqa: E402


class Statistics(unittest.TestCase):
    def test_t_quantiles_match_the_tables(self):
        self.assertAlmostEqual(clock.t_quantile(0.95, 10), 1.8125, places=3)
        self.assertAlmostEqual(clock.t_quantile(0.975, 5), 2.5706, places=3)
        self.assertAlmostEqual(clock.t_quantile(0.975, 1000), 1.9623, places=3)

    def test_welch_interval_brackets_the_difference(self):
        d, lo, hi = clock.welch([1, 2, 3, 4], [3, 4, 5, 6], 0.95)
        self.assertEqual(d, 2.0)
        self.assertLess(lo, 2.0)
        self.assertGreater(hi, 2.0)
        self.assertEqual(clock.welch([5, 5], [5, 5], 0.9), (0.0, 0.0, 0.0))

    def test_the_criterion_reads_each_case(self):
        same = clock.judge([10, 11, 9, 10, 12, 8], [10, 10, 11, 9, 10, 11], 'engages')
        self.assertEqual(same['verdict'], 'equivalent')
        moved = clock.judge([1, 1, 2, 1, 1, 2], [6, 7, 6, 8, 7, 6], 'stalls')
        self.assertEqual(moved['verdict'], 'different')
        wide = clock.judge([0, 10, 0, 12], [2, 14, 1, 16], 'stalls')
        self.assertEqual(wide['verdict'], 'inconclusive')
        self.assertEqual(clock.judge([1, 2], [1, 2], 'freezes')['margin'], 1.0, 'one event at least')
        self.assertAlmostEqual(clock.judge([100, 100], [100, 100], 'avg_speed')['margin'], 30.0)

    def test_spearman_handles_ties(self):
        self.assertEqual(cal.ranks([3, 1, 2, 2]), [4.0, 1.0, 2.5, 2.5])
        self.assertAlmostEqual(cal.spearman([0, 1, 2, 3], [1, 2, 3, 4]), 1.0)
        self.assertAlmostEqual(cal.spearman([0, 1, 2, 3], [4, 3, 2, 1]), -1.0)
        self.assertEqual(cal.spearman([1, 1, 1], [1, 2, 3]), 0.0)


def tape(rows):
    return 'ARGUS init on dm4\nARGEVT Reap spawned\nARGEVT Omi spawned\n' + ''.join(rows)


def sample(name, t):
    return f"ARGLOG {name} t {t:.1f} pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n"


class StandInTapes(unittest.TestCase):
    def test_kills_come_from_death_events_and_only_bots_count(self):
        rows = [sample(n, 1.0 + i) for i in range(61) for n in ('Reap', 'Omi', 'standin')]
        rows += ["ARGEVT standin death Reap pos '0 0 24'\n",          # a bot kill
                 "ARGEVT standin death world pos '0 0 -400'\n",       # lava: nobody
                 "ARGEVT standin death standin pos '0 0 24'\n",       # its own rocket: nobody
                 "ARGEVT Omi death standin pos '0 0 24'\n"]           # its kill
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'standin_cal_dm4_k1_1.log'
            path.write_text(tape(rows))
            got = cal.tape_rates(path)
        self.assertEqual(got['human'], 'standin')
        self.assertEqual((got['bot_kills'], got['kills']), (1, 1))
        self.assertAlmostEqual(got['minutes'], 1.0)

    def test_a_tape_with_no_human_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'standin_cal_dm4_k0_1.log'
            path.write_text(tape([sample('Reap', 1.0), sample('Reap', 2.0)]))
            self.assertIsNone(cal.tape_rates(path))

    def test_dose_response_needs_a_rising_and_clear_difference(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / 'runs'
            runs.mkdir()
            for k in range(4):
                for s in range(4):
                    rows = [sample(n, 1.0 + i) for i in range(61) for n in ('Reap', 'Omi', 'standin')]
                    rows += ["ARGEVT standin death Reap pos '0 0 24'\n"] * (k * 2 + (s % 2))
                    (runs / f'cal_dm4_k{k}_{s + 1}.log').write_text(tape(rows))
            rep = cal.evaluate(td, 'cal_dm4_k*', person_mean=2.5, skill=1)
        self.assertTrue(rep['dose_response'], rep)
        self.assertGreater(rep['spearman'], 0.9)
        self.assertTrue(rep['level'])
        self.assertTrue(math.isclose(rep['per_skill'][3]['mean'], 6.5))


if __name__ == '__main__':
    unittest.main()
