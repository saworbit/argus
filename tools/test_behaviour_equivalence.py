import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from check_behaviour_equivalence import evaluate, frame_interval, interval, rate, T95_DF127
from run_behaviour_equivalence import timing, validate_protocol
import run_behaviour_registered


class EquivalenceTests(unittest.TestCase):
    def test_no_difference_is_not_equivalence_when_uncertain(self):
        self.assertFalse(interval([-10, 10] * 4, 2)['equivalent'])
        self.assertTrue(interval([-.1, .1] * 4, 2)['equivalent'])

    def test_detects_large_shift_and_rejects_partial_cohort(self):
        self.assertFalse(interval([-4] * 8, 2)['equivalent'])
        with self.assertRaises(AssertionError):
            interval([0] * 7, 2)

    def test_bounds_are_strict(self):
        self.assertFalse(interval([2] * 8, 2)['equivalent'])

    def test_larger_cohort_keeps_bounds_and_requires_complete_pairs(self):
        self.assertTrue(interval([-.1, .1] * 64, 2, 128)['equivalent'])
        self.assertFalse(interval([2] * 128, 2, 128)['equivalent'])
        self.assertFalse(frame_interval([.95] * 128, 128)['equivalent'])
        self.assertAlmostEqual(T95_DF127, 1.6569403435420642)
        for size in (8, 127, 129):
            with self.assertRaises(AssertionError):
                interval([0] * size, 2, 128)
        with self.assertRaises(AssertionError):
            interval([0] * 64, 2, 64)

    def test_larger_evaluation_rejects_duplicate_missing_or_mixed_pairs(self):
        rows = []
        for map_name in ('dm2', 'dm4'):
            for repeat in range(1, 129):
                for mode in ('off', 'on'):
                    totals = dict.fromkeys(('goals', 'grabs', 'acquisitions', 'engages', 'stalls',
                                             'frags', 'lava_deaths', 'freezes'), 2)
                    totals.update(duration_sec=60, tick_class='listen')
                    rows.append(dict(name=f'{map_name}_{repeat}_{mode}', map=map_name, repeat=repeat,
                        mode=mode, brief=dict(totals=totals), cpu_seconds=1, wall_seconds=60, bytes=100,
                        identity=dict.fromkeys(('source_sha256', 'binary_sha256', 'cli_sha256', 'nav_sha256'), 'x'),
                        timing=[dict(mean_ms=15.6, frames=320, over50=0)] * 10))
        self.assertTrue(evaluate(rows, 128)['primary_equivalent'])
        self.assertTrue(evaluate(rows, 128)['cadence_equivalent'])
        for changed in (rows[:-1], rows[:-1] + [rows[0]]):
            with self.assertRaises(AssertionError):
                evaluate(changed, 128)
        changed = copy.deepcopy(rows)
        changed[0]['identity']['binary_sha256'] = 'changed'
        with self.assertRaises(AssertionError):
            evaluate(changed, 128)

    def test_registration_rejects_bound_sample_and_identity_changes(self):
        protocol = dict(maps=['dm2', 'dm4'], pairs_per_map=128, seconds=60, prefix='bhv2',
            goal_margin_per_minute=2, confidence=.90, frame_margin_ms=1, rounding_allowance_ms=.1,
            identities=dict(dm2={'same': True}, dm4={'same': True}), analysis_code_sha256={})
        with patch('run_behaviour_equivalence.identity', return_value={'same': True}):
            validate_protocol(protocol, ['dm2', 'dm4'], list(range(1, 129)), 60, 'bhv2', 'confirm')
            for key, value in [('goal_margin_per_minute', 3), ('pairs_per_map', 64), ('confidence', .8),
                               ('frame_margin_ms', 2), ('rounding_allowance_ms', 0)]:
                changed = dict(protocol, **{key: value})
                with self.assertRaises(AssertionError):
                    validate_protocol(changed, ['dm2', 'dm4'], list(range(1, 129)), 60, 'bhv2', 'confirm')
        with patch('run_behaviour_equivalence.identity', return_value={'same': False}):
            with self.assertRaises(AssertionError):
                validate_protocol(protocol, ['dm2', 'dm4'], list(range(1, 129)), 60, 'bhv2', 'confirm')

    def test_registered_runner_restores_lab_binary_after_failure(self):
        scratch_root = Path(__file__).resolve().parents[1] / 'backups'
        scratch_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch_root) as directory:
            root = Path(directory)
            binary = root / 'engine/argus/progs.dat'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'shipped')
            candidate = root / 'candidate.dat'
            candidate.write_bytes(b'candidate')
            protocol = root / 'protocol.json'
            protocol.write_text(json.dumps(dict(output='results', candidate='candidate.dat',
                identities=dict(dm2=dict(binary_sha256=hashlib.sha256(b'candidate').hexdigest())),
                shipped_sha256=hashlib.sha256(b'shipped').hexdigest(),
                maps=['dm2', 'dm4'], pairs_per_map=128, seconds=60, prefix='bhv2')))
            def fail():
                self.assertEqual(binary.read_bytes(), b'candidate')
                raise RuntimeError('test interruption')
            with patch.object(run_behaviour_registered, 'ROOT', root), \
                    patch.object(run_behaviour_registered, 'run', side_effect=fail), \
                    patch.object(sys, 'argv', ['test', str(protocol)]):
                with self.assertRaisesRegex(RuntimeError, 'test interruption'):
                    run_behaviour_registered.main()
            self.assertEqual(binary.read_bytes(), b'shipped')
            self.assertEqual(json.loads((root / 'results/execution.json').read_text())['status'], 'interrupted')

    def test_cadence_equivalence_accounts_for_format_rounding(self):
        self.assertFalse(frame_interval([.95] * 8)['equivalent'])
        self.assertTrue(frame_interval([0] * 8)['equivalent'])

    def test_rates_use_native_exposure(self):
        self.assertEqual(rate(dict(brief=dict(totals=dict(duration_sec=60, goals=3))), 'goals'), 3)
        with self.assertRaises(AssertionError):
            rate(dict(brief=dict(totals=dict(duration_sec=30, goals=3))), 'goals')

    def test_cadence_rejects_malformed_missing_and_empty_windows(self):
        line = 'BHVTIME t 5 frames 320 seconds 5 mean_ms 15.6 max_ms 17 over20 0 over50 0\n'
        self.assertEqual(len(timing(line * 6)), 5)
        for text in (line * 4, (line * 6).replace('frames 320', 'frames 0'), line * 6 + 'BHVTIME bad\n'):
            with self.assertRaises(AssertionError):
                timing(text)


if __name__ == '__main__':
    unittest.main()
