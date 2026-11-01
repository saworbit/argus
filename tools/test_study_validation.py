"""Evidence gates and lab cleanup must survive optimized Python and failures."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_behaviour_equivalence as native
import verify_plan_progress as plan


class StudyValidationTests(unittest.TestCase):
    def test_optimized_interpreters_reject_failed_routes_and_incompatible_arms(self):
        code = '''
from verify_water_route import require_outcome
from run_map_intelligence import comparison_primary
protocol = dict(maps=['dm3'], seconds=60, skill=2, requested_ticrate=.0139,
                primary='stall_parity', cli_sha256='a')
checks = [lambda: require_outcome(dict(case=6, completed=False, handoffs=0, seconds=30), False),
          lambda: comparison_primary(protocol, dict(protocol, maps=['dm6']))]
for check in checks:
    try: check()
    except AssertionError: pass
    else: raise RuntimeError('invalid evidence accepted')
'''
        for flags, environment in [([], {}), (['-O'], {}), ([], {'PYTHONOPTIMIZE': '1'})]:
            result = subprocess.run([sys.executable, *flags, '-c', code],
                cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                env=dict(os.environ, **environment), timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_backups_root_is_refused_before_any_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(plan, 'ROOT', root), \
                 patch.object(sys, 'argv', ['verify_plan_progress.py', '--output', str(root/'backups')]), \
                 contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as stopped:
                    plan.main()
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn('new directory beneath backups', errors.getvalue())
            self.assertFalse((root/'backups').exists())

    def test_primary_failure_skips_another_request_and_always_closes(self):
        lab = Mock()
        failure = RuntimeError('original lab failure')
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                try: raise failure
                finally: native.finish_lab(lab)
            except RuntimeError as reported:
                self.assertIs(reported, failure)
        lab.call.assert_not_called()
        lab.close.assert_called_once()

    def test_failed_stop_is_logged_and_does_not_skip_close(self):
        lab = Mock()
        lab.call.side_effect = BrokenPipeError('stop pipe closed')
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            native.finish_lab(lab)
        lab.close.assert_called_once()
        self.assertIn('stop pipe closed', errors.getvalue())

    def test_close_handles_dead_stdin_and_escalates_an_unresponsive_child(self):
        lab = native.Lab.__new__(native.Lab)
        lab.p = Mock()
        lab.p.stdin.close.side_effect = BrokenPipeError('closed')
        lab.p.wait.side_effect = [subprocess.TimeoutExpired('lab', 5),
                                 subprocess.TimeoutExpired('lab', 5), 0]
        lab.close()
        lab.p.terminate.assert_called_once()
        lab.p.kill.assert_called_once()
        lab.p.stdout.close.assert_called_once()

    def test_a_crashed_real_child_keeps_the_original_failure(self):
        program = '''
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message['method'] == 'initialize':
        print(json.dumps(dict(jsonrpc='2.0', id=message['id'], result={})), flush=True)
    elif message['method'] == 'tools/call':
        sys.exit(3)
'''
        start = subprocess.Popen
        def launch(command, **kw):
            return start([sys.executable, '-u', '-c', program], **kw)
        with tempfile.TemporaryFile(mode='w+') as errors, patch.object(native.subprocess, 'Popen', side_effect=launch):
            lab = native.Lab(errors)
            with self.assertRaisesRegex(AssertionError, 'lab exited'):
                try:
                    lab.call('see', what='project')
                finally:
                    native.finish_lab(lab)
            self.assertEqual(lab.p.returncode, 3)
            self.assertTrue(lab.p.stdin.closed and lab.p.stdout.closed)
            self.assertFalse(errors.closed)

    def test_legacy_fixture_sources_keep_lf_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)/'legacy'
            plan.prepare(folder, legacy=True)
            for filename in ('argus.qc', 'defs.qc', 'progs.src', 'world.qc', 'plan_progress.qc'):
                self.assertNotIn(b'\r\n', (folder/'src'/filename).read_bytes(), filename)


if __name__ == '__main__':
    unittest.main()
