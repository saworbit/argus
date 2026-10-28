"""Compile-gate rejection and owned-output contracts; no engine or assets."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import compile_private_fixtures as gate


class CompileGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'private/candidate'
        (self.folder/'src').mkdir(parents=True)
        (self.folder/'src/progs.src').write_text('../lq1/progs.dat')
        (self.folder/'lq1').mkdir()
        self.compiler = self.root/'compiler'
        self.compiler.write_bytes(b'compiler')

    def compiler_run(self, text='Compile finished (id format)', binary=True, code=0, version=6):
        def run(*args, **kwargs):
            self.assertEqual(kwargs['cwd'], self.folder/'src')
            if binary:
                (self.folder/'lq1/progs.dat').write_bytes(version.to_bytes(4, 'little')+bytes(56))
            return SimpleNamespace(returncode=code, stdout=text, stderr='')
        return run

    def test_real_completion_contract_and_receipt(self):
        result = gate.compile_one(self.compiler, self.folder, self.compiler_run())
        self.assertTrue(result['ok'])
        self.assertEqual(result['compiler_sha256'], gate.digest(self.compiler))
        self.assertEqual(result['binary_sha256'], gate.digest(self.folder/'lq1/progs.dat'))
        self.assertTrue((self.folder/'compile.log').is_file())

    def test_zero_exit_alone_never_passes(self):
        for text, binary, code, version in [
                ('Unknown value "diff"', False, 0, 6),
                ('Compile finished (id format)', False, 0, 6),
                ('Compile finished (id format)', True, 0, 7),
                ('Compile finished (id format)', True, 1, 6)]:
            with self.subTest(text=text, binary=binary, code=code, version=version):
                path = self.folder/'lq1/progs.dat'
                path.unlink(missing_ok=True)
                with self.assertRaises(RuntimeError):
                    gate.compile_one(self.compiler, self.folder, self.compiler_run(text, binary, code, version))
                self.assertFalse(json.loads((self.folder/'compile.json').read_text())['ok'])

    def test_preexisting_binary_cannot_mask_a_failed_compile(self):
        (self.folder/'lq1/progs.dat').write_bytes(b'old')
        with self.assertRaises(ValueError):
            gate.compile_one(self.compiler, self.folder, lambda *a, **k: self.fail('compiler started'))

    def test_timeout_retains_failure_receipt(self):
        def timeout(*a, **k):
            raise subprocess.TimeoutExpired('compiler', 90)
        with self.assertRaises(subprocess.TimeoutExpired):
            gate.compile_one(self.compiler, self.folder, timeout)
        self.assertIn('timed out', json.loads((self.folder/'compile.json').read_text())['error'])

    def test_missing_compiler_collision_protected_path_and_invalid_family_refuse(self):
        for compiler, output, families in [
                (self.root/'missing', self.root/'new', ['muzzle']),
                (self.compiler, self.folder, ['muzzle']),
                (self.compiler, self.root/'src/new', ['muzzle']),
                (self.compiler, self.root/'tools/new', ['muzzle']),
                (self.compiler, self.root/'new', ['unknown']),
                (self.compiler, self.root/'new', [])]:
            with self.subTest(output=output, families=families):
                with self.assertRaises(ValueError):
                    gate.compile_families(compiler, output, families, self.root)
        self.assertFalse((self.root/'new').exists())

    def test_native_verifier_lock_is_respected_without_removal(self):
        lock = self.root/'backups/.private-fixture.lock'
        lock.parent.mkdir()
        lock.write_text('owned elsewhere')
        with self.assertRaises(FileExistsError):
            gate.compile_families(self.compiler, self.root/'new', ['muzzle'], self.root)
        self.assertEqual(lock.read_text(), 'owned elsewhere')
        self.assertFalse((self.root/'new').exists())

    def test_failure_retains_receipts_and_releases_only_own_lock(self):
        (self.root/'src').mkdir()
        (self.root/'src/source.qc').write_text('protected')
        before = gate.inputs(self.root)
        output = self.root/'new'
        def stage(folder, *args):
            folder.mkdir(parents=True)
            raise RuntimeError('staging failed')
        with patch.object(gate, 'stage', stage):
            with self.assertRaisesRegex(RuntimeError, 'staging failed'):
                gate.compile_families(self.compiler, output, ['muzzle'], self.root)
        self.assertEqual(before, gate.inputs(self.root))
        self.assertTrue(json.loads((output/'results.json').read_text())['unchanged'])
        self.assertFalse((self.root/'backups/.private-fixture.lock').exists())

    def test_help_is_safe_without_staging_imports_or_outputs(self):
        result = subprocess.run([sys.executable, str(Path(gate.__file__)), '--help'],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--family', result.stdout)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['compiler', 'private'])

    def test_all_families_use_native_staging_and_keep_production_exact(self):
        before = gate.inputs(gate.ROOT)
        with TemporaryDirectory() as td:
            for family, variants in gate.VARIANTS.items():
                for variant in variants:
                    folder = Path(td)/family/variant
                    gate.stage(folder, family, variant)
                    self.assertTrue((folder/'src/progs.src').is_file())
                    self.assertFalse((folder/'lq1/progs.dat').exists())
                    self.assertTrue(any((folder/'src').glob('*fixture*.qc')))
        self.assertEqual(before, gate.inputs(gate.ROOT))


if __name__ == '__main__':
    unittest.main()
