"""One executable and one compiled-source identity per study process."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_behaviour_equivalence as native
import run_map_intelligence as maps


class ExecutableContract(unittest.TestCase):
    def test_balance_comparisons_use_the_same_selected_lab(self):
        import run_health_balance as health
        import run_perception_balance as perception
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'runs').mkdir()
            exe = root / 'lab'
            rows = []
            for map_name in ('dm2', 'dm4'):
                for mode in ('control', 'candidate'):
                    for repeat in range(1, 9):
                        name = f'{map_name}_{mode}_{repeat}'
                        (root / 'runs' / (name + '.log')).write_bytes(b'retained tape')
                        rows.append(dict(map=map_name, mode=mode, repeat=repeat, name=name,
                                         raw_sha256=hashlib.sha256(b'retained tape').hexdigest()))
            with patch.dict(os.environ, ARGUS_LAB=str(exe)):
                for module in (health, perception):
                    selected = rows if module is health else [r for r in rows if r['repeat'] <= 3]
                    with patch.object(module, 'ROOT', root), patch.object(module, 'OUT', root), \
                         patch.object(module, 'lab_cli', return_value=subprocess.CompletedProcess([], 0, 'native card', '')) as cli:
                        module.write_comparisons(selected)
                    self.assertEqual(cli.call_count, 2)
                    self.assertTrue(all(call.args[0] == native.lab_executable() for call in cli.call_args_list))
    def test_default_and_override_are_shared_by_mcp_and_cli(self):
        with tempfile.TemporaryDirectory() as td:
            exe = Path(td) / 'chosen-lab'
            with patch.dict(os.environ, ARGUS_LAB=str(exe)):
                self.assertEqual(native.lab_executable(), maps.lab_executable())
                self.assertEqual(native.lab_executable(), exe)
                with patch.object(native.subprocess, 'run') as run:
                    native.lab_cli(exe, 'compare', 'a', 'b', timeout=3, runner=run)
                self.assertEqual(run.call_args.args[0][0], str(exe))
                self.assertEqual(run.call_args.kwargs['encoding'], 'utf-8')

    def test_one_lab_class_uses_the_selected_path_and_a_request_deadline(self):
        program = '''
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message['method'] == 'initialize':
        print(json.dumps(dict(jsonrpc='2.0', id=message['id'], result={})), flush=True)
'''
        start = subprocess.Popen
        selected = []
        def launch(command, **options):
            selected.append(command[0])
            return start([sys.executable, '-u', '-c', program], **options)
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryFile(mode='w+') as errors:
            exe = Path(td) / 'chosen-lab'
            with patch.object(native.subprocess, 'Popen', side_effect=launch):
                lab = native.Lab(errors, exe=exe, timeout=1)
                try:
                    with self.assertRaises(TimeoutError): lab.request('slow', {}, timeout=.02)
                    self.assertEqual(lab.executable, exe)
                    self.assertIs(maps.Lab, native.Lab)
                finally:
                    native.finish_lab(lab, active=False)
            self.assertEqual(selected, [str(exe)])
            self.assertEqual(lab.p.returncode, 0)
            self.assertFalse(errors.closed)

    def test_cli_exit_and_timeout_reap_the_owned_process(self):
        start, owned = subprocess.Popen, []
        def launch(*args, **options):
            process = start(*args, **options)
            owned.append(process)
            return process
        with patch.object(native.subprocess, 'Popen', side_effect=launch):
            result = native.lab_cli(Path(sys.executable), '-c', 'print("card");raise SystemExit(7)', timeout=3)
            self.assertEqual(result.returncode, 7)
            self.assertEqual(result.stdout.strip(), 'card')
            with self.assertRaises(subprocess.TimeoutExpired):
                native.lab_cli(Path(sys.executable), '-c', 'import time;time.sleep(30)', timeout=.1)
        self.assertTrue(all(p.poll() is not None for p in owned))

    def test_only_documented_stage_build_is_needed_for_preflight(self):
        import verify_private_fixtures as private
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            root = Path(td)
            binary = root / 'tools/argus_mcp/target-stage/release' / ('argus-mcp.exe' if os.name == 'nt' else 'argus-mcp')
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'lab')
            (root / 'src').mkdir()
            (root / 'src/progs.src').write_text('world.qc\n')
            with patch.object(native, 'ROOT', root):
                self.assertEqual(private.preflight(root, root / 'backups/new', 'new'), root / 'backups/new')


if __name__ == '__main__':
    unittest.main()
