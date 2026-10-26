"""Adversarial tests for behaviour evidence and observer purity."""
import unittest
from pathlib import Path

from check_behaviour_fixture import audit_observer, audit_timing, audit_diagnostic_ownership, check, guard_source


def tape(diagnostics=True, case=0):
    debug = 'BHVDBG Romero t 1 source remembered intent combat reason sample\n' if diagnostics else ''
    return (f'BHVFIX begin dm4 case {case}\nBHVFIX trial 1 case {case}\n'
            + debug + ('BHVFIX busy id 1 requested 1\n' if case == 9 else '')
            + "BHVFIX sample 0.1 pos '465 -279 -104' visible 1 launches 0 targethp 5000 hp 100 invariant 1\n"
            + f'BHVFIX guard checks 1 emits {1 if diagnostics else 0}\n'
            + "BHVFIX sample 5.8 pos '465 -151 -104' visible 1 launches 2 targethp 4900 hp 100 invariant 1\n"
            + f'BHVFIX guard checks 60 emits {30 if diagnostics else 0}\n'
            + 'BHVFIX end frames 60 seconds 6\nBHVFIX cleanup 1 restored 1 invariant 1\nBHVFIX done 1\n')


class BehaviourTests(unittest.TestCase):
    def test_rounded_timestamp_ties_require_distinct_frame_guards(self):
        first = "BHVFIX sample 0.1 pos '465 -279 -104' visible 1 launches 0 targethp 5000 hp 100 invariant 1\n"
        source = tape().replace('BHVFIX guard checks 1 emits 1\n',
            'BHVFIX guard checks 1 emits 1\n' + first + 'BHVFIX guard checks 2 emits 1\n')
        check(source, diagnostics=True)
        with self.assertRaises(AssertionError):
            check(source.replace('checks 2', 'checks 1'), diagnostics=True)
        with self.assertRaises(AssertionError):
            check(source.replace('BHVFIX guard checks 2 emits 1\n', ''), diagnostics=True)
    def test_valid_on_off_and_measured_cadence(self):
        for on in (False, True):
            self.assertEqual(check(tape(on), diagnostics=on, expected=[0], hz=10)[0]['fps'], 10)

    def test_missing_duplicate_wrong_and_reordered_acknowledgements(self):
        source = tape()
        mutations = [source.replace('BHVFIX done 1', ''),
                     source.replace('BHVFIX done 1', 'BHVFIX done 2'),
                     source.replace('BHVFIX trial 1 case 0', 'BHVFIX trial 1 case 0\nBHVFIX trial 1 case 0'),
                     source.replace('BHVFIX end frames 60 seconds 6', ''),
                     source.replace('BHVFIX begin dm4 case 0', 'BHVFIX begin wrong case 0'),
                     source.replace('BHVFIX cleanup 1 restored 1 invariant 1', ''),
                     source.replace('BHVFIX done 1', 'BHVFIX done 1\nBHVFIX done 1')]
        for text in mutations:
            with self.subTest(text=text), self.assertRaises(AssertionError):
                check(text, diagnostics=True)

    def test_failing_cleanup_or_invariant_cannot_pass(self):
        for old, new in [('restored 1', 'restored 0'), ('invariant 1', 'invariant 0'),
                         ('pos \'465 -151 -104\'', 'pos \'nan -151 -104\''),
                         ('frames 60', 'frames 0')]:
            with self.subTest(new=new), self.assertRaises(AssertionError):
                check(tape().replace(old, new), diagnostics=True)

    def test_wrong_diagnostics_or_cadence_fails(self):
        with self.assertRaises(AssertionError):
            check(tape(False), diagnostics=True)
        with self.assertRaises(AssertionError):
            check(tape(), diagnostics=True, hz=72)

    def test_overlap_must_be_refused_once(self):
        self.assertTrue(check(tape(case=9), diagnostics=True))
        for text in [tape(case=9).replace('BHVFIX busy id 1 requested 1\n', ''),
                     tape(case=9).replace('BHVFIX busy id 1 requested 1', 'BHVFIX busy id 1 requested 1\nBHVFIX busy id 1 requested 1')]:
            with self.assertRaises(AssertionError):
                check(text, diagnostics=True)

    def test_real_observer_is_pure(self):
        source = (Path(__file__).resolve().parents[1] / 'src/argus_behaviour.qc').read_text()
        audit_observer(source)
        for change in ['self.health = 100;', 'self.ar_goals = self.ar_goals + 1;', 'random ();', 'traceline ();',
                       'makevectors ();', 'setorigin ();', 'trace_fraction = 0;',
                       'Argus_Perceive ();']:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                audit_observer(source.replace('    local string source, intent, reason;',
                                              '    local string source, intent, reason;\n    ' + change))

    def test_generated_engine_guard_is_current(self):
        source = (Path(__file__).resolve().parents[1] / 'src/argus_behaviour_fixture.qc').read_text()
        self.assertIn('// BEGIN observer guard\n' + guard_source() + '// END observer guard', source)

    def test_cadence_probe_cannot_write_gameplay_or_consume_rng(self):
        source = (Path(__file__).resolve().parents[1] / 'src/argus_behaviour_fixture.qc').read_text()
        audit_timing(source)
        for mutation in ('self.health = 0;', 'random ();', 'traceline ();', 'v_forward = \'0 0 0\';'):
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_timing(source.replace('    ar_bt_frames = ar_bt_frames + 1;', mutation))

    def test_prints_use_vanilla_builtin_without_shared_temp_aliasing(self):
        import re
        source = (Path(__file__).resolve().parents[1] / 'src/argus_behaviour.qc').read_text()
        with self.assertRaises(AssertionError):
            audit_observer(source.replace('= #25;', '= #7;'))
        calls = re.findall(r'Argus_BehaviourPrint\s*\((.*?)\);', source, re.S)
        self.assertTrue(calls)
        self.assertTrue(all(len(re.findall(r'\b(?:ftos|vtos)\s*\(', call)) <= 1 for call in calls))
        batched = source.split('else if (mode == 590)', 1)[1]
        self.assertGreater(batched.count('Argus_BehaviourPrint ('), 0)
        self.assertLessEqual(batched.count('Argus_BehaviourPrint ('), 12)

    def test_gameplay_cannot_depend_on_diagnostic_history(self):
        root = Path(__file__).resolve().parents[1] / 'src'
        sources = {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob('*.qc')}
        audit_diagnostic_ownership(sources)
        for dependency in ('self.ar_bd_valid', 'ar_bt_frames'):
            with self.subTest(dependency=dependency), self.assertRaises(AssertionError):
                audit_diagnostic_ownership(dict(sources, **{'argus.qc': sources['argus.qc'] + '\n' + dependency}))

    def test_snapshot_never_acquires_engine_fields(self):
        import re
        fields = re.findall(r'^    (ar_bgs_\w+)\s*=', guard_source(), re.M)
        self.assertTrue(fields)
        self.assertTrue(all(field.startswith('ar_bgs_') for field in fields))
        self.assertNotIn('spawn (', guard_source())
        self.assertNotIn('ar_bf_guard.', guard_source())

    def test_diagnostics_are_outside_the_existing_metric_grammar(self):
        from argus_tape import event_fields, sample_row
        for line in tape().splitlines():
            self.assertIsNone(event_fields(line))
            self.assertIsNone(sample_row(line, 1))
        timing = 'BHVTIME t 5 frames 320 seconds 5 mean_ms 15.6 max_ms 17 over20 0 over50 0'
        self.assertIsNone(event_fields(timing))
        self.assertIsNone(sample_row(timing, 1))


if __name__ == '__main__':
    unittest.main()
