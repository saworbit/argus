"""Admission and slot invariants of the emitted runtime graph."""
import ast
import collections
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from argus_nav_slots import clamp_walk, require_slots, slot_count
from argus_names import map_name


class MapAdmission(unittest.TestCase):
    def test_shared_cases(self):
        cases = json.loads(Path(__file__).with_name('map_name_cases.json').read_text())
        for raw, expected in cases:
            if expected is None:
                with self.assertRaises(ValueError, msg=raw): map_name(raw)
            else:
                self.assertEqual(map_name(raw), expected)

    def test_generator_refuses_bad_name_before_reading_bsp_or_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'nav.qc'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('argus_navgen.py')),
                                     'missing.bsp', 'my-map', str(out), str(out)+'.png'],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('map must match', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class SlotAdmission(unittest.TestCase):
    def test_late_mint_counts_every_typed_family(self):
        tree = ast.parse(Path(__file__).with_name('argus_navgen.py').read_text(encoding='utf-8'))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_slot_free')
        for family in ('teles', 'rjlinks', 'lifts', 'swims', 'trains', 'sprints'):
            scope = {name: [] for name in ('teles', 'rjlinks', 'lifts', 'swims', 'trains', 'sprints')}
            scope.update(links={}, tele_out=collections.Counter(), MAX_LINKS=8)
            scope['slot_count'] = slot_count
            scope[family] = [(0, n) for n in range(1, 9)]
            scope['tele_out'].update(a for a, _ in scope['teles'])
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<slot admission>', 'exec'), scope)
            self.assertFalse(scope['_slot_free'](0), family)

    def test_typed_overflow_is_refused_without_mutating_walks(self):
        links = {0: {10: (100, 0)}}
        before = repr(links)
        with self.assertRaisesRegex(ValueError, 'typed link slot overflow'):
            clamp_walk(links, [(0, n) for n in range(1, 10)])
        self.assertEqual(repr(links), before)
        with self.assertRaisesRegex(ValueError, 'final link slot overflow'):
            require_slots(links, [(0, n) for n in range(1, 9)])

    def test_shared_pairs_use_one_slot_and_clamp_preserves_typed_routes(self):
        links = {0: {n: (n * 10, 0) for n in range(1, 10)}}
        typed = [(0, 1), (0, 2), (0, 9)]
        self.assertEqual(slot_count(0, links, typed, typed), 9)
        self.assertEqual(clamp_walk(links, typed), 1)
        self.assertEqual(set(links[0]), {1, 2, 3, 4, 5, 6, 7, 9})
        require_slots(links, typed)


if __name__ == '__main__':
    unittest.main()
