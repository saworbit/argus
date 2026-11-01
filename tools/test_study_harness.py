"""One executable and one compiled-source identity per study process."""
import contextlib
import hashlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_behaviour_equivalence as native
import run_map_intelligence as maps
from argus_source import source_identity
import argus_fixture_harness as fixtures


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


class SourceContract(unittest.TestCase):
    def test_attention_stage_receipt_tracks_tactics_changes(self):
        import verify_target_attention as attention
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, output = root / 'source', root / 'staged'
            shutil.copytree(native.ROOT / 'src', src)
            (src / 'argus_tactics.qc').write_text('first')
            attention.stage(native.ROOT, output, src)
            before = attention.source_receipt(output / 'src')
            (output / 'src/argus_tactics.qc').write_text('second')
            self.assertNotEqual(attention.source_receipt(output / 'src')['source_sha256'], before['source_sha256'])

    def test_missing_or_empty_source_is_not_a_valid_identity(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError): source_identity(Path(td) / 'missing')
            with self.assertRaises(ValueError): source_identity(td)
    def test_nonprimary_sources_and_names_change_the_identity_but_sidecars_do_not(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)
            (src / 'argus.qc').write_bytes(b'bot')
            path = src / 'argus_tactics.qc'
            path.write_bytes(b'first')
            before = source_identity(src)
            path.write_bytes(b'second')
            self.assertNotEqual(source_identity(src), before)
            before = source_identity(src)
            (src / 'graph.qc.json').write_text('{}')
            self.assertEqual(source_identity(src), before)
            path.rename(src / 'other.qc')
            self.assertNotEqual(source_identity(src), before)

    def test_current_tree_matches_the_recorded_path_prefixed_algorithm(self):
        digest = hashlib.sha256()
        src = native.ROOT / 'src'
        for path in sorted([*src.rglob('*.qc'), *src.rglob('*.src')]):
            digest.update(path.relative_to(native.ROOT).as_posix().encode())
            digest.update(b'\0')
            digest.update(path.read_bytes())
        self.assertEqual(source_identity(src), digest.hexdigest())


class FixtureContract(unittest.TestCase):
    def test_every_runner_refuses_the_absent_backups_root_itself(self):
        import verify_freeze_recovery, verify_mover_transfer, verify_target_attention
        import verify_water_route, verify_route_distance
        modules = (verify_freeze_recovery, verify_mover_transfer, verify_target_attention,
                   verify_water_route, verify_route_distance, maps)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for module in modules:
                args = [module.__file__, '--output', str(root / 'backups'), '--prefix', 'unit']
                with patch.object(module, 'ROOT', root), patch.object(sys, 'argv', args), \
                     patch.object(module, 'Lab') as lab:
                    with self.assertRaisesRegex(ValueError, 'strict child'): module.main()
                lab.assert_not_called()
                self.assertFalse((root / 'backups').exists())

    def test_shared_stage_writes_lf_and_rolls_back_a_failed_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source'; source.mkdir()
            (source / 'progs.src').write_bytes(b'argus.qc\r\nworld.qc\r\n')
            (source / 'world.qc').write_bytes(b'Argus_FrameAll ();\r\n')
            (source / 'argus.qc').write_text('bot')
            output = fixtures.new_output(root / 'backups/staged', root=root, create=False)
            fixtures.stage_fixture(root, output, source, fixtures={'fixture.qc': '// witness\n'},
                                   frame_wrap='Fixture ();\n    Argus_FrameAll ();')
            for name in ('progs.src', 'world.qc', 'fixture.qc'):
                self.assertNotIn(b'\r\n', (output / 'src' / name).read_bytes())
            self.assertEqual((output / 'src/progs.src').read_text().count('fixture.qc'), 1)
            failed = root / 'backups/failed'
            def partial_copy(src, dest):
                dest.mkdir(); (dest / 'partial.qc').write_text('partial')
                raise OSError('injected copy failure')
            with patch.object(fixtures.shutil, 'copytree', side_effect=partial_copy):
                with self.assertRaisesRegex(OSError, 'injected'):
                    fixtures.stage_fixture(root, failed, source)
            self.assertFalse(failed.exists())
            self.assertEqual((source / 'argus.qc').read_text(), 'bot')

    def test_named_tape_reader_never_uses_another_log(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'runs').mkdir()
            (root / 'runs/other.log').write_text('ARGUS init on dm4\n')
            with self.assertRaises(FileNotFoundError): fixtures.read_tape(root, 'chosen', 'dm4')
            path = root / 'runs/chosen.log'
            for text in ('ARGUS init on dm4\nARGUS init on dm4\n',
                         'ARGUS init on dm2\n', 'ARGUS init on dm4\nHost_Error broken\n'):
                path.write_text(text)
                with self.assertRaises(AssertionError): fixtures.read_tape(root, 'chosen', 'dm4')
            path.write_bytes(b'ARGUS init on dm4\r\nretained\xff\r\n')
            self.assertEqual(fixtures.read_tape(root, 'chosen', 'DM4')[0], path)

    def test_cadence_checks_are_shared_at_both_played_profiles(self):
        for marker in ('FRFIX', 'MVFIX', 'ATFIX', 'WRFIX', 'RDFIX'):
            for rate, ms in ((.0139, 14), (.1, 100)):
                text = f'{marker} begin dt_ms {ms}\n'
                self.assertEqual(fixtures.frame_ms(text, marker, rate), ms)
                with self.assertRaises(AssertionError): fixtures.frame_ms(text + text, marker, rate)
            with self.assertRaises(AssertionError): fixtures.frame_ms(f'{marker} begin dt_ms 100\n', marker, .0139)

    def test_private_game_checks_installs_on_success_and_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for folder in ('game/argus', 'engine/argus', 'lq1'):
                (root / folder).mkdir(parents=True)
                (root / folder / 'progs.dat').write_bytes(b'shipped')
            (root / 'game/argus/autoexec.cfg').write_text('max_edicts 600\n')
            before = fixtures.installed_identity(root)
            failure = RuntimeError('compile failed')
            with self.assertRaises(RuntimeError) as reported:
                with fixtures.private_game(root, 'failure', 'check'):
                    raise failure
            self.assertIs(reported.exception, failure)
            self.assertEqual(fixtures.installed_identity(root), before)
            with self.assertRaisesRegex(AssertionError, 'installed progs.dat changed'):
                with fixtures.private_game(root, 'changed', 'check'):
                    (root / 'engine/argus/progs.dat').write_bytes(b'external edit')
            self.assertEqual((root / 'engine/argus/progs.dat').read_bytes(), b'external edit')
            failure = RuntimeError('original failure')
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(RuntimeError) as reported:
                    with fixtures.private_game(root, 'both', 'check'):
                        (root / 'engine/argus/progs.dat').write_bytes(b'second external edit')
                        raise failure
            self.assertIs(reported.exception, failure)
            self.assertTrue(any('installed progs.dat' in note for note in failure.__notes__))

    def test_dangling_private_game_alias_is_refused_before_creation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'engine').mkdir()
            link, target = root / 'engine/check_alias', root / 'engine/argus'
            if os.name == 'nt':
                result = subprocess.run(['cmd', '/C', 'mklink', '/J', str(link), str(target)],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError):
                with fixtures.private_game(root, 'alias', 'check'): self.fail('alias entered')
            self.assertFalse(target.exists())

    def test_mover_main_uses_one_native_session_and_named_private_tapes(self):
        import verify_mover_transfer as mover
        from test_mover_transfer import receipt
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for folder in ('src', 'tools/fixtures', 'game/argus', 'engine/argus', 'lq1'):
                (root / folder).mkdir(parents=True)
            for folder in ('game/argus', 'engine/argus', 'lq1'):
                (root / folder / 'progs.dat').write_bytes(b'shipped')
            (root / 'game/argus/autoexec.cfg').write_text('max_edicts 600\n')
            (root / 'src/progs.src').write_text('argus.qc\nworld.qc\n')
            (root / 'src/argus.qc').write_text('bot')
            (root / 'src/world.qc').write_text('Argus_FrameAll ();\n')
            for name in ('e1m6', 'dm3'):
                (root / f'src/argus_nav_{name}.qc.json').write_text('{}')
            shutil.copy2(native.ROOT / 'tools/fixtures/mover_transfer.qc', root / 'tools/fixtures/mover_transfer.qc')
            exe = root / 'lab'; exe.write_bytes(b'lab')
            sessions, commands = [], []
            class FakeLab:
                def __init__(self, err, environment, **options):
                    self.executable, self.environment = options['exe'], environment
                    self.closed = False; sessions.append(self)
                def call(self, tool, **args):
                    if tool == 'compile_qc':
                        require_install = args['install']
                        if require_install: raise AssertionError('fixture installed')
                        Path(self.environment['ARGUS_PROGS']).write_bytes(b'private build')
                        return dict(ok=True)
                    if tool == 'brief_run': return dict(events={})
                    return {}
                def close(self): self.closed = True
            def cli(executable, command, map_name, seconds, name, *rest, **options):
                commands.append((executable, map_name, name, rest))
                runs = Path(options['environment']['ARGUS_RUNS'])
                (runs / (name + '.log')).write_text(receipt().replace('on e1m6', 'on ' + map_name))
                return subprocess.CompletedProcess([], 0, '{"ok":true}', '')
            before = fixtures.installed_identity(root)
            output = root / 'backups/job'
            args = ['verify_mover_transfer.py', '--output', str(output), '--prefix', 'unit']
            with patch.object(mover, 'ROOT', root), patch.object(mover, 'Lab', FakeLab), \
                 patch.object(fixtures, 'lab_cli', side_effect=cli), \
                 patch.dict(os.environ, ARGUS_LAB=str(exe)), patch.object(sys, 'argv', args), \
                 contextlib.redirect_stdout(io.StringIO()):
                mover.main()
            rows = json.loads((output / 'receipt.json').read_text())
            self.assertEqual(len(rows), 2)
            self.assertTrue(sessions[0].closed)
            self.assertTrue(all(c[0] == sessions[0].executable == exe for c in commands))
            self.assertEqual({c[2] for c in commands}, {'unit_e1m6', 'unit_dm3'})
            self.assertEqual(fixtures.installed_identity(root), before)
    def test_route_output_refusal_precedes_staging_or_lab_start(self):
        import verify_route_distance as route
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for folder in ('src', 'tools/fixtures', 'game/argus', 'engine'):
                (root / folder).mkdir(parents=True)
            (root / 'src/progs.src').write_text('argus.qc\nworld.qc\n')
            (root / 'src/world.qc').write_text('Argus_FrameAll ();\n')
            (root / 'src/argus.qc').write_text('bot')
            (root / 'tools/fixtures/route_distance.qc').write_text('fixture')
            (root / 'game/argus/autoexec.cfg').write_text('max_edicts 600\n')
            output = root / 'outside-backups'
            args = ['verify_route_distance.py', '--output', str(output), '--prefix', 'private', '--compile-only']
            with patch.object(route, 'ROOT', root), patch.object(sys, 'argv', args), \
                 patch.object(route, 'Lab', side_effect=RuntimeError('must not start')) as lab:
                with self.assertRaises(ValueError): route.main()
            lab.assert_not_called()
            self.assertFalse(output.exists())

    def test_freeze_parser_refuses_a_second_map_init(self):
        from verify_freeze_recovery import inspect_fixture
        from test_freeze_recovery import receipt
        tape = 'ARGUS init on dm4\nARGUS init on dm4\n' + receipt()
        with self.assertRaisesRegex(AssertionError, 'map'):
            inspect_fixture(tape, True, .0139)


if __name__ == '__main__':
    unittest.main()
