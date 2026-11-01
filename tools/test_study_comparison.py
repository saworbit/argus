"""Registered-primary comparison artifacts keep native decisions and frozen inputs."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_map_intelligence as runner


class RegisteredComparisons(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'runs').mkdir()
        self.exe = self.root / 'argus-mcp'
        self.exe.write_bytes(b'frozen native analysis executable')
        self.protocol = dict(maps=['dm3'], seconds=60, skill=2, requested_ticrate=.0139,
                             primary='freezes', cli_sha256=runner.digest(self.exe),
                             binary_sha256='candidate-binary', source_sha256='candidate-source')
        self.control = dict(self.protocol, binary_sha256='control-binary', source_sha256='control-source')
        self.row = self.tape('candidate', self.protocol)
        self.baseline = self.tape('control', self.control)
        self.addCleanup(patch.stopall)
        patch.object(runner, 'ROOT', self.root).start()

    def tape(self, name, protocol):
        path = self.root / 'runs' / (name + '.log')
        path.write_bytes(b'ARGUS init on dm3\r\nARGLOG retained sample\r\n')
        return dict(name=name, map='dm3', repeat=1, raw_sha256=runner.digest(path),
                    binary_sha256=protocol['binary_sha256'], source_sha256=protocol['source_sha256'],
                    brief=dict(totals=dict(tick_class='listen')))

    def compare(self, run):
        with patch.object(runner, 'lab_cli', return_value=run) as invoke:
            value = runner.compare_registered_tape(self.exe, self.control, self.protocol,
                                                   [self.baseline], self.row)
        return value, invoke

    def test_all_registered_primaries_reach_native_cli_and_artifact(self):
        card = 'REJECT: severe freeze in one tape\nOther statistical gates passed.\n'
        for primary in ('stall_parity', 'engagements', 'lava_deaths', 'freezes'):
            with self.subTest(primary=primary):
                self.protocol['primary'] = self.control['primary'] = primary
                value, invoke = self.compare(subprocess.CompletedProcess([], 0, card, ''))
                self.assertEqual(invoke.call_args.args,
                    (self.exe, 'compare', 'candidate', 'control', '--primary', primary))
                self.assertEqual(invoke.call_args.kwargs['environment']['ARGUS_ROOT'], str(self.root))
                self.assertEqual(value['effective_primary'], primary)
                self.assertEqual(value['native_gate_card'], card)
                self.assertEqual(value['analysis_lab_sha256'], runner.digest(self.exe))
                self.assertEqual(value['inputs']['control']['raw_sha256'], self.baseline['raw_sha256'])
                self.assertEqual(value['inputs']['candidate']['source_sha256'], 'candidate-source')
                self.assertEqual(json.loads(json.dumps(value))['comparison_protocol']['primary'], primary)

    def test_incompatible_or_missing_protocol_fields_refuse_before_native_call(self):
        alternatives = dict(maps=['dm6'], seconds=120, skill=3, requested_ticrate=.1,
                            primary='engagements', cli_sha256='different-cli')
        for key, value in alternatives.items():
            for missing in (False, True):
                with self.subTest(key=key, missing=missing):
                    control = copy.deepcopy(self.control)
                    if missing:
                        del control[key]
                    else:
                        control[key] = value
                    with patch.object(runner, 'lab_cli') as invoke:
                        with self.assertRaisesRegex(AssertionError, key):
                            runner.compare_registered_tape(self.exe, control, self.protocol,
                                                           [self.baseline], self.row)
                        invoke.assert_not_called()
        self.control['primary'] = self.protocol['primary'] = 'unregistered'
        with self.assertRaisesRegex(AssertionError, 'unsupported'):
            runner.comparison_primary(self.control, self.protocol)

    def test_baseline_mismatch_precedes_study_output_or_lab_start(self):
        baseline = self.root / 'baseline'; baseline.mkdir()
        (baseline / 'protocol.json').write_text(json.dumps(dict(self.control, primary='engagements')))
        (baseline / 'results.json').write_text(json.dumps([self.baseline]))
        output = self.root / 'backups' / 'new-study'
        argv = ['run_map_intelligence.py', '--maps', 'dm3', '--seconds', '60', '--skill', '2',
                '--output', str(output), '--prefix', 'new_study', '--lab', str(self.exe),
                '--baseline', str(baseline), '--primary', 'freezes']
        with patch.object(sys, 'argv', argv), patch.object(runner, 'Lab') as lab:
            with self.assertRaisesRegex(AssertionError, 'primary'):
                runner.main()
            lab.assert_not_called()
        self.assertFalse(output.exists())
        self.assertFalse((self.root / 'engine').exists())

    def test_empty_baseline_is_refused(self):
        folder = self.root / 'baseline'; folder.mkdir()
        (folder / 'protocol.json').write_text(json.dumps(self.control))
        (folder / 'results.json').write_text('[]')
        with self.assertRaisesRegex(AssertionError, 'empty baseline'):
            runner.load_comparison_baseline(folder, self.protocol)

    def test_changed_tape_or_frozen_program_identity_is_refused(self):
        for arm, original in [('candidate', self.row), ('control', self.baseline)]:
            for field in ('raw_sha256', 'binary_sha256', 'source_sha256'):
                with self.subTest(arm=arm, field=field):
                    row = dict(original, **{field: 'changed'})
                    candidate = row if arm == 'candidate' else self.row
                    baseline = row if arm == 'control' else self.baseline
                    with patch.object(runner, 'lab_cli') as invoke:
                        with self.assertRaises(AssertionError):
                            runner.compare_registered_tape(self.exe, self.control, self.protocol,
                                                           [baseline], candidate)
                        invoke.assert_not_called()
        self.exe.write_bytes(b'replaced executable')
        with self.assertRaisesRegex(AssertionError, 'executable changed'):
            runner.compare_registered_tape(self.exe, self.control, self.protocol,
                                           [self.baseline], self.row)

    def test_control_selection_and_all_same_map_cadences_are_checked(self):
        other = self.tape('control_two', self.control)
        self.row['repeat'] = 2
        response = subprocess.CompletedProcess([], 0, 'native card\n', '')
        with patch.object(runner, 'lab_cli', return_value=response) as invoke:
            result = runner.compare_registered_tape(self.exe, self.control, self.protocol,
                                                   [self.baseline, other], self.row)
            self.assertEqual(invoke.call_args.args[3], 'control_two')
            self.assertEqual(result['inputs']['control']['name'], 'control_two')
        self.row['repeat'] = 1
        other['brief']['totals']['tick_class'] = 'dedicated'
        with patch.object(runner, 'lab_cli') as invoke:
            with self.assertRaisesRegex(AssertionError, 'cross-cadence'):
                runner.compare_registered_tape(self.exe, self.control, self.protocol,
                                               [self.baseline, other], self.row)
            invoke.assert_not_called()

    def test_native_errors_and_empty_cards_are_not_artifacts(self):
        for response in (subprocess.CompletedProcess([], 1, '', 'native source mismatch'),
                         subprocess.CompletedProcess([], 0, '', '')):
            with self.subTest(response=response):
                with self.assertRaises(AssertionError):
                    self.compare(response)


if __name__ == '__main__':
    unittest.main()
