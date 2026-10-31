"""An experimental graph on disk is not evidence that bots loaded navigation."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import report_map_intelligence as report


class ReportProvenance(unittest.TestCase):
    def test_missing_coverage_is_not_zero(self):
        self.assertIsNone(report.coverage([dict(brief={})]))
        self.assertEqual(report.coverage([dict(brief=dict(nav_coverage=dict(pct=0)))]), 0)

    def test_uncompiled_experimental_coverage_is_not_a_runtime_score(self):
        row = dict(compiled_navigation=False, brief=dict(nav_coverage=dict(pct=92)))
        self.assertIsNone(report.coverage([row]))
        row['compiled_navigation'] = True
        self.assertEqual(report.coverage([row]), 92)

    def test_frozen_source_controls_registration_and_tape_integrity(self):
        with TemporaryDirectory() as name:
            root = Path(name); folder = root / 'arm'; (folder / 'src').mkdir(parents=True)
            (root / 'runs').mkdir(); tape = root / 'runs/test.log'; tape.write_bytes(b'original console\r\n')
            (folder / 'protocol.json').write_text(json.dumps(dict(binary_sha256='binary')))
            (folder / 'results.json').write_text(json.dumps([dict(name='test', map='e1m3',
                binary_sha256='binary', raw_sha256=hashlib.sha256(tape.read_bytes()).hexdigest(),
                brief=dict(nav_coverage=dict(pct=92)))]))
            src = folder / 'src'
            (src / 'progs.src').write_text('argus_nav_e1m3.qc\n')
            (src / 'argus_nav_dispatch.qc').write_text('void() Argus_Nav_Spawn = {};\n')
            with patch.object(report, 'ROOT', root):
                _, rows = report.load(folder)
                self.assertFalse(rows[0]['compiled_navigation'])
                (src / 'argus_nav_dispatch.qc').write_text('if (mapname == "e1m3") Argus_Nav_Spawn_e1m3 ();\n')
                _, rows = report.load(folder)
                self.assertTrue(rows[0]['compiled_navigation'])
                tape.write_bytes(b'changed')
                with self.assertRaises(AssertionError):
                    report.load(folder)


if __name__ == '__main__':
    unittest.main()
