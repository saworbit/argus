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
    def test_retarget_is_distinct_from_starting_an_engagement(self):
        from collections import Counter
        from argus_tape import parse_tape
        tape = parse_tape('ARGEVT Joe Rogan spawned\n'
            'ARGEVT Joe Rogan engage Carmack\n'
            'ARGEVT Joe Rogan retarget Romero\n')
        counts = Counter(event[2] for event in tape.events)
        self.assertEqual(counts['engage'], 1)
        self.assertEqual(counts['retarget'], 1)
        self.assertEqual(tape.events[-1][1:], ('Joe Rogan', 'retarget', 'Romero'))

    def test_shared_role_fixture_matches_rust(self):
        from argus_tape import roles
        cases = json.loads((Path(__file__).parent / 'testdata/roles.json').read_text())
        for case in cases:
            actual = roles(case['text'])
            for role in ('bots', 'humans', 'instruments'):
                self.assertEqual(actual[role], case[role])

    def test_camera_is_absent_from_downstream_tracks(self):
        from tempfile import TemporaryDirectory
        import argus_humanness
        case = json.loads((Path(__file__).parent / 'testdata/roles.json').read_text())[0]
        with TemporaryDirectory() as td:
            path = Path(td) / 'camera.log'
            path.write_text(case['text'])
            tracks = argus_humanness.read_tape(path)
            self.assertEqual(set(tracks['bots']), {'Reap'})
            self.assertEqual(set(tracks['humans']), {'Ranger'})
            self.assertEqual(argus_longi.analyse(path)['human'], 'Ranger')
            path.write_text(case['text'].replace("ARGLOG Ranger", "ARGLOG labcamera"))
            self.assertEqual(argus_pointfile.human_points(path, 4), [])

    def test_shared_samples_maps_roles_and_whitespace(self):
        from argus_tape import samples, map_name, roles, event_fields
        text = FIXTURE.read_text()
        self.assertTrue(list(samples(text)))
        self.assertEqual(roles(text)['humans'], ['Shane Wall'])
        self.assertEqual(roles(text)['instruments'], ['labprobe', 'unconnected'])
        for gap in (' ', '  ', ' \t '):
            self.assertEqual(event_fields('ARGEVT Big Bob' + gap + 'goal  item_armor1', ['Big Bob']),
                             ('Big Bob', 'goal', 'item_armor1'))
        self.assertEqual(map_name('SpawnServer: DM4\n'), 'dm4')
        self.assertEqual(map_name('Spawning server maps/DM2\n'), 'dm2')
        self.assertEqual(map_name('maps/DM6.bsp\n'), 'dm6')
        self.assertEqual(map_name("SpawnServer: missing\nCouldn't spawn server maps/missing.bsp\nSpawnServer: start\n"), 'start')
        self.assertEqual(len(list(samples("ARGLOG Old Bot t 1.0 pos '0 0 24'\n"))), 1)
        self.assertEqual(map_name('SpawnServer: dm4\nARGUS init on dm2\n'), 'dm2')
        self.assertIsNone(map_name('ARGUS init on dm4\nARGUS init on dm2\n'))

    def test_event_vocabulary_matches_rust(self):
        import re
        from argus_tape import VERBS
        rust = (Path(__file__).parent / 'argus_mcp/src/parse_arglog.rs').read_text()
        words = re.search(r'const EVENT_VERBS: &str = "([^"]+)";', rust)[1]
        self.assertEqual(VERBS, frozenset(words.split('|')))

    def test_pointfile_preserves_spaced_names_and_excludes_legacy_humans(self):
        from tempfile import TemporaryDirectory
        row = "ARGLOG Big Bob t {} pos '{} 0 24' spd 0 yaw 0 mode 0 st 0 gl 0\n"
        with TemporaryDirectory() as td:
            path = Path(td) / 'tape.log'
            path.write_text(row.format(0, 0) + row.format(1, 16)
                            + "ARGEVT Big Bob death world pos '16 0 24'\n")
            self.assertEqual(argus_pointfile.event_points(path, {'death'}), [(16.0, 0.0, 24.0)])
            self.assertEqual(argus_pointfile.human_points(path, 4), [])
            path.write_text('ARGEVT Big Bob spawned\n' + row.format(0, 0)
                            + row.format(1, 16).replace('Big Bob', 'labprobe')
                            + row.format(2, 32).replace('Big Bob', 'labprobe'))
            self.assertEqual(argus_pointfile.human_points(path, 4), [])

    def test_event_words_in_names_do_not_change_identity_or_payload(self):
        from argus_tape import parse_tape, track_names
        from tempfile import TemporaryDirectory
        text = '''ARGEVT Reap spawned
ARGEVT Gap lift spawned
ARGEVT Last death spawned
ARGLOG Reap t 0.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0
ARGLOG Gap lift t 0.0 pos '10 0 24' spd 0 yaw 0 mode 0 st 0 gl 0
ARGLOG Last death t 0.0 pos '20 0 24' spd 0 yaw 0 mode 0 st 0 gl 0
ARGEVT Gap lift tactic abort weapon
ARGEVT Last death death Gap lift pos '20 0 24'
ARGEVT Gap lift goal spawned
'''
        tape = parse_tape(text)
        self.assertEqual(track_names(tape.samples, tape.events)[1], [])
        self.assertEqual([event[1:] for event in tape.events], [
            ('Reap', 'spawned', ''), ('Gap lift', 'spawned', ''), ('Last death', 'spawned', ''),
            ('Gap lift', 'tactic', 'abort weapon'), ('Last death', 'death', "Gap lift pos '20 0 24'"),
            ('Gap lift', 'goal', 'spawned'),
        ])
        overlap = "ARGLOG Gap t 0.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0\n" + text
        self.assertEqual(parse_tape(overlap).events[1][1], 'Gap lift')
        no_samples = parse_tape('ARGEVT Gap lift spawned\nARGEVT Gap lift tactic abort weapon\n')
        self.assertEqual(no_samples.events[1][1:], ('Gap lift', 'tactic', 'abort weapon'))
        with TemporaryDirectory() as td:
            path = Path(td) / 'names.log'
            path.write_text(text)
            _, events, deaths = argus_review.parse(path)
            self.assertEqual([event[1:] for event in events], [event[1:] for event in tape.events])
            self.assertEqual(deaths[0][1:3], ('Last death', 'Gap lift'))
            row = argus_longi.analyse(path)
            self.assertEqual(row['bots'], 3)
            self.assertEqual(row['human'], '-')
            self.assertEqual(row['bot_deaths'], 1)

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

    def test_unforced_world_deaths_split_walk_offs_from_knock_ins(self):
        from tempfile import TemporaryDirectory
        # Lava below z -350; every sample is (t, z, hp) for one bot.
        lava = lambda x, y, z: -5 if z < -350 else -1

        def count(rows, death_z=-384, contents=lava, extra=''):
            lines = ['ARGUS init on dm4', 'ARGEVT Reap spawned']
            lines += [f"ARGLOG Reap t {t:.1f} pos '0 0 {z}' spd 300 yaw 0 mode 2 st 0 gl 0 hp {hp} frg 0"
                      for t, z, hp in rows]
            lines += [extra] if extra else []
            lines.append(f"ARGEVT Reap death world pos '0 0 {death_z}'")
            with TemporaryDirectory() as td:
                path = Path(td) / 'deaths.log'
                path.write_text('\n'.join(lines) + '\n')
                return argus_longi.analyse(path, contents=contents)['bot_world_unforced']

        run_off = [(1.0, -296, 100), (1.5, -296, 100), (2.0, -296, 100), (2.5, -384, 60), (3.0, -384, 20)]
        self.assertEqual(count(run_off), 1)
        knock_in = [(1.0, -296, 100), (1.5, -296, 80), (2.0, -296, 80), (2.5, -384, 50), (3.0, -384, 20)]
        self.assertEqual(count(knock_in), 0)
        # Surfacing between samples is a bob: the burn before it is the lava, not a cause.
        bob = [(1.0, -296, 100), (1.5, -296, 100), (2.0, -384, 80), (2.5, -384, 60), (3.0, -320, 50), (3.5, -384, 20)]
        self.assertEqual(count(bob), 1)
        # Burning at the edge after the feet read dry: the death position ends the run.
        edge = [(1.0, -296, 100), (1.5, -384, 70), (2.0, -384, 40), (2.5, -320, 25), (3.0, -320, 10)]
        self.assertEqual(count(edge, death_z=-384), 1)
        self.assertEqual(count(edge, death_z=-320), 0)
        # Megahealth rot is not damage; a hit more than 3 s before the entry is not the cause.
        self.assertEqual(count([(1.0, -296, 110), (1.5, -296, 109), (2.0, -296, 108), (2.5, -384, 70)]), 1)
        old_hit = [(0.0, -296, 100), (0.5, -296, 50), (4.0, -296, 50), (4.5, -296, 50), (5.0, -296, 50), (5.5, -384, 20)]
        self.assertEqual(count(old_hit), 1)
        # Tapes before 2026-08-18 wrote a bare death line beside the detailed one.
        self.assertEqual(count(run_off, extra='ARGEVT Reap death'), 1)
        # A spawn kill has no samples to judge and is skipped, not blanked.
        self.assertEqual(count(run_off, extra="ARGEVT Reap death world pos '0 0 24'\nARGEVT Reap respawn"), 1)
        # No BSP: blank rather than a guess.
        self.assertEqual(count(run_off, contents=None), '')

    def test_unforced_is_zero_without_world_deaths_even_without_a_bsp(self):
        from tempfile import TemporaryDirectory
        text = ('ARGEVT Reap spawned\nARGEVT Omi spawned\n'
                "ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n"
                "ARGEVT Reap death Omi pos '0 0 24'\n")
        with TemporaryDirectory() as td:
            path = Path(td) / 'frag.log'
            path.write_text(text)
            self.assertEqual(argus_longi.analyse(path, contents=None)['bot_world_unforced'], 0)

    def test_the_first_session_on_ed8926_has_two_unforced_world_deaths(self):
        # Carmack ran off a ledge at 440 u/s and Joe Rogan's stall jump (#797)
        # flew him into lava; the third bot was knocked in after a 17 hp hit.
        tape = Path(__file__).resolve().parent.parent / 'runs/shane_dm4_2026-11-14_ed8926.log'
        if not tape.is_file() or argus_longi.bsp_for('dm4') is None:
            self.skipTest('needs the 11-14 tape and a machine-local dm4.bsp')
        row = argus_longi.analyse(tape)
        self.assertEqual((row['bot_world'], row['bot_world_unforced']), (3, 2))

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
