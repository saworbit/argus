"""Shared freeze predicate, identity and tactical event regression tests."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_longi
import argus_pointfile
import argus_review

FIXTURE = Path(__file__).parent / "testdata/freeze_parity.log"
EXPECTED = json.loads(FIXTURE.with_suffix(".json").read_text())


class TestTapeConsumers(unittest.TestCase):
    def test_committed_engine_events_match_the_review_and_scorecard(self):
        from argus_tape import tactic_counts
        path = FIXTURE.with_name('tactic_events.log')
        expected = json.loads(path.with_suffix('.json').read_text())
        _, events, _ = argus_review.parse(path)
        self.assertEqual(len(events), 70)
        self.assertEqual(dict(tactic_counts(events)), expected)
        self.assertTrue(all(event[1] == 'Romero' for event in events))
        row = argus_longi.analyse(path)
        for phase in ('prepare', 'opening', 'covered', 'reappear', 'returnshot', 'abort'):
            self.assertEqual(row['tactic_' + phase], expected['tactic_' + phase])
        self.assertEqual(row['tactic_abort_reasons'],
                         'blocked=2;crossfire=2;moved=2;route=1;survival=2;weapon=2')

    def test_legacy_tracks_are_bots_but_instruments_never_are(self):
        from argus_tape import parse_tape, track_names
        text = '\n'.join(line for line in FIXTURE.read_text().splitlines()
                         if not line.startswith('ARGEVT '))
        tape = parse_tape(text)
        bots, humans, instruments = track_names(tape.samples, tape.events)
        self.assertIn('Shane Wall', bots)
        self.assertEqual(humans, [])
        self.assertEqual(instruments, ['labprobe', 'unconnected'])

    def test_level_changes_use_the_busiest_segment_and_last_tie(self):
        from argus_tape import parse_tape
        a = "ARGLOG Reap t 0.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0"
        b = a.replace('t 0.0', 't 6.0')
        tape = parse_tape(f'SpawnServer: dm4\n{a}\n{b}\nSpawnServer: dm2\n{a}\n')
        self.assertEqual(len(tape.samples['Reap']), 2)
        tape = parse_tape(f'SpawnServer: dm4\n{a}\n{b}\nSpawnServer: dm2\n{a}\n{a}\n')
        self.assertEqual([s['t'] for s in tape.samples['Reap']], [0.0, 0.0])

    def test_review_reports_the_rust_bot_windows(self):
        samples, events, _ = argus_review.parse(FIXTURE)
        # Exclude review-only tracks just as the lab brief does.
        samples = {name: rows for name, rows in samples.items()
                   if name not in ('Shane Wall', 'labprobe', 'unconnected')}
        windows = argus_review.freezes(samples)
        actual = sorted((row[0], row[1], row[3]) for row in windows)
        self.assertEqual(actual, sorted((row['bot'], row['t_start'], row['dur']) for row in EXPECTED))

    def test_longi_and_pointfile_use_the_same_bot_windows(self):
        row = argus_longi.analyse(FIXTURE)
        self.assertEqual(row['freezes'], len(EXPECTED))
        self.assertEqual(row['fz_max'], 8.0)
        self.assertEqual(row['fz_fire'], 2)
        self.assertEqual(row['bots'], 7)
        self.assertEqual(row['human'], 'Shane Wall')
        points = argus_pointfile.tape_points(FIXTURE)
        self.assertEqual(sorted(points), sorted((r['x'], r['y'], r['z']) for r in EXPECTED))

    def test_tactical_events_keep_spaced_names_and_reasons(self):
        for module in (argus_review, argus_longi):
            event = module.EVT.search('ARGEVT Joe Rogan tactic abort target')
            self.assertIsNotNone(event)
            self.assertEqual(event.groups(), ('Joe Rogan', 'tactic', 'abort target'))

    def test_summary_reports_tactical_phases_without_claiming_hits(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            argus_review.cmd_summary(FIXTURE)
        text = out.getvalue()
        self.assertEqual(text.count('FROZEN '), len(EXPECTED))
        for field in ('tactic_prepare', 'tactic_opening', 'tactic_covered', 'tactic_reappear', 'tactic_returnshot', 'tactic_abort_target'):
            self.assertIn(field, text)
        row = argus_longi.analyse(FIXTURE)
        self.assertEqual(row['tactic_prepare'], 2)
        self.assertEqual(row['tactic_returnshot'], 1)
        self.assertEqual(row['tactic_abort'], 1)
        self.assertNotIn('tactic_hit', row)


if __name__ == '__main__':
    unittest.main()
