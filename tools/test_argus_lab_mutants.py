"""Fast tests for the lab spine mutation check (#824).

The full table takes minutes, so it stays out of CI. These tests check that
every row still names one place in the spine, that a stale row stops the run
before any suite starts, and that the harness reports a known mutant caught
and an untested one missed.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import argus_lab_mutants as mutants  # noqa: E402

SCRIPT = TOOLS / 'argus_lab_mutants.py'
ROW = {row[0]: row for row in mutants.MUTANTS}


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=600)


class TestMutants(unittest.TestCase):
    def test_every_row_names_one_place_in_the_spine(self):
        source = mutants.TARGET.read_text(encoding='utf-8')
        self.assertEqual(mutants.table_problems(mutants.MUTANTS, source), [])
        self.assertGreaterEqual(len(mutants.MUTANTS), 50)

    def test_a_stale_row_exits_non_zero_before_any_suite_runs(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / 'suite-ran'
            suite = Path(td) / 'test_marker.py'
            suite.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n', encoding='utf-8')
            table = Path(td) / 'table.json'
            table.write_text(json.dumps([list(ROW['a number is never a boolean']),
                                         ['a guard that moved', 'text the spine no longer holds', 'pass']]))
            res = run('--table', str(table), '--suite', str(suite))
            self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
            self.assertIn("'a guard that moved': the original text is no longer in the spine", res.stdout)
            self.assertFalse(marker.exists(), 'the suite ran although the table was stale')

    def test_an_ambiguous_or_uncompilable_row_is_a_problem(self):
        source = 'a = 1\nb = 1\n'
        problems = mutants.table_problems([('twice', '= 1', '= 2'), ('broken', 'a = 1', 'a = ('),
                                           ('same', 'b = 1', 'b = 1')], source)
        self.assertEqual(len(problems), 3, problems)
        self.assertIn('appears 2 times', problems[0])
        self.assertIn('does not compile', problems[1])
        self.assertIn('must differ', problems[2])

    def test_a_tested_guard_is_caught_and_an_untested_one_missed(self):
        with tempfile.TemporaryDirectory() as td:
            suite = Path(td) / 'test_tiny.py'
            suite.write_text('import sys, unittest\n'
                             f'sys.path.insert(0, {str(TOOLS)!r})\n'
                             'import argus_lab\n'
                             'class T(unittest.TestCase):\n'
                             '    def test_a_boolean_is_not_a_number(self):\n'
                             '        self.assertFalse(argus_lab.is_number(True))\n', encoding='utf-8')
            table = Path(td) / 'table.json'
            table.write_text(json.dumps([list(ROW['a number is never a boolean']),
                                         list(ROW['a cell bounds height'])]))
            res = run('--table', str(table), '--suite', str(suite), '--jobs', '2')
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn('caught  a number is never a boolean (T.test_a_boolean_is_not_a_number', res.stdout)
            self.assertIn('MISSED  a cell bounds height', res.stdout)
            self.assertIn('1 of 2 guards caught', res.stdout)
            # the spine on disk is untouched: the mutant lived in memory only
            self.assertIn(ROW['a number is never a boolean'][1], mutants.TARGET.read_text(encoding='utf-8'))

    def test_the_real_suite_catches_a_known_mutant(self):
        label = 'an open claim explains every kind in its cell'
        res = run('--only', label, '--jobs', '1')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('unbroken suite passes', res.stdout)
        self.assertIn(f'caught  {label} (TestFourthRoundFindings.', res.stdout)
        self.assertIn('1 of 1 guards caught', res.stdout)

    def test_an_unknown_label_is_refused(self):
        res = run('--only', 'no such guard')
        self.assertEqual(res.returncode, 2)
        self.assertIn("no row labelled 'no such guard'", res.stdout)


if __name__ == '__main__':
    unittest.main()
