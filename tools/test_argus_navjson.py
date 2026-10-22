"""Parity checks for Python navigation readers and build registration."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from argus_navjson import FAMILIES, FREE, GATED, WALK, edges, load_nav
from argus_registration import registration


class TestNavReaders(unittest.TestCase):
    def test_noninteger_endpoints_never_create_a_route(self):
        from argus_mapgate import _graph_edges
        from argus_pointfile import _adj
        for family in FAMILIES:
            for invalid in (0.5, 0.0, '0', True, False, None, [], {}):
                for link in ([invalid, 1], [0, invalid]):
                    with self.subTest(family=family, link=link):
                        nav = {'nodes': [[0, 0, 0], [64, 0, 0]], family: [link]}
                        for reader in (lambda value: list(edges(value, gated=True)),
                                       _graph_edges, _adj):
                            with self.assertRaisesRegex(ValueError, 'endpoints must be integers'):
                                reader(nav)

    def test_registration_comments_respect_strings_and_escapes(self):
        cases = json.loads((Path(__file__).parent / 'testdata/registration.json').read_text())
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(registration(case['dispatch'], case['progs'], 'fixture'),
                                 tuple(case['expected']))

    def test_register_refuses_custom_filename_before_any_file_changes(self):
        script = Path(__file__).parent / 'argus_navgen.py'
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)
            original = {'progs.src': 'defs.qc\nargus_nav_dispatch.qc\n',
                        'argus_nav_dispatch.qc': 'void() Argus_Nav_Spawn = { };\n'}
            for name, content in original.items():
                (src / name).write_text(content)
            for _ in range(2):
                run = subprocess.run([sys.executable, str(script), 'missing.bsp', 'fixture',
                                      str(src / 'custom.qc'), str(src / 'unused.png'), '--register'],
                                     capture_output=True, text=True, timeout=10)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn('--register requires argus_nav_fixture.qc', run.stderr)
                self.assertEqual({p.name: p.read_text() for p in src.iterdir()}, original)

    def test_families_match_the_rust_loader(self):
        source = (Path(__file__).parent / "argus_mcp/src/nav_graph.rs").read_text()
        source = source.split("#[cfg(test)]")[0]
        rust = set(re.findall(r'"(\w*links|teles)"', source))
        self.assertEqual(set(FAMILIES), rust)
        self.assertEqual(len(FAMILIES), len(set(FAMILIES)))

    def test_each_family_has_the_same_gating_in_all_readers(self):
        from argus_mapgate import _graph_edges
        from argus_pointfile import _adj
        from argus_reach import load_graph
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nav.json"
            for family in FAMILIES:
                graph = {"nodes": [{"origin": [0, 0, 24]}, [64, 0, 24]], family: [[0, 1]]}
                path.write_text(json.dumps(graph))
                nav = load_nav(path)
                self.assertEqual(nav["nodes"], [[0, 0, 24], [64, 0, 24]])
                expected = [] if family in GATED else [(0, 1)]
                self.assertEqual(list(edges(nav)), expected, family)
                self.assertEqual(list(edges(nav, gated=True)), [(0, 1)], family)
                self.assertEqual(_adj(nav)[0], [b for _, b in expected], family)
                self.assertEqual(_graph_edges(nav)[0], [b for _, b in expected], family)
                _, walk, free, gated = load_graph(path)
                self.assertEqual(set((0, b) for b in walk[0]) | set(free), set(expected), family)
                self.assertEqual(set(gated), {(0, 1)} if family in GATED else set(), family)

    def test_gated_aliases_and_invalid_endpoints_do_not_invent_routes(self):
        nav = {"nodes": [[0, 0, 0], [1, 0, 0]],
               "links": [[0, 1, 1], [-1, 0], [0, 9], [0]], "rjlinks": [[0, 1]]}
        self.assertEqual(list(edges(nav)), [])
        self.assertEqual(list(edges(nav, gated=True)), [(0, 1)])

    def test_registration_ignores_comments_and_requires_exact_progs_lines(self):
        branch = 'if (mapname == "fixture") spawn ();'
        qc = "argus_nav_fixture.qc\nargus_nav_dispatch.qc\n"
        for dispatch, progs, expected in [
            (branch, qc, (True, True)), (branch, "", (True, False)),
            ("", qc, (False, True)), ("", "", (False, False)),
            ('// ' + branch, qc, (False, True)),
            ('/* ' + branch + ' */', qc, (False, True)),
            ('// "fixture"', qc, (False, True)),
            (branch, '// argus_nav_fixture.qc', (True, False)),
            (branch, 'argus_nav_fixture.qc.bak', (True, False)),
        ]:
            self.assertEqual(registration(dispatch, progs, "fixture"), expected)


if __name__ == "__main__":
    unittest.main()
