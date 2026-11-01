"""Focused regression tests for repository validation rules."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import argus_ci as ci


class CIValidationTests(unittest.TestCase):
    def test_navigation_receipts_share_their_tapes_append_once_guard(self):
        self.assertTrue(ci.PROTECTED_TAPE.fullmatch('runs/ab_dm4_test.nav.json'))
        self.assertTrue(ci.PROTECTED_TAPE.fullmatch('runs/shane_dm2_test.nav.json'))
        self.assertFalse(ci.PROTECTED_TAPE.fullmatch('runs/unrelated-results.json'))

    def test_setext_underlines_do_not_promote_other_blocks(self):
        cases = {
            "1. Install\n---\n": set(),
            "2) Install\n===\n": set(),
            "- Install\n---\n": set(),
            "+ Install\n---\n": set(),
            "* Install\n---\n": set(),
            "> Note\n---\n": set(),
            "## Setup\n---\n": {"setup"},
            "---\n---\n": set(),
            "    Code\n---\n": set(),
            "Install\n---\n": {"install"},
            "Install\n===\n": {"install"},
            "Install\n---\n\nInstall\n===\n": {"install", "install-1"},
            "## Setup\n---\n\n## Setup\n": {"setup", "setup-1"},
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(ci.markdown_anchors(source), expected)

    def test_dashes_checks_tracked_prose_and_sources_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q", td], check=True, capture_output=True)
            files = {"docs/read me.md": "Good\nBad \u2013 range\nBad \u2014 clause\n",
                     "src/bot.qc": "// \u2013\n", "tools/helper.py": "# \u2014\n",
                     "tools/argus_mcp/src/gui.html": "<!-- \u2013 -->\n",
                     "tools/argus_mcp/src/demo.rs": "// \u2014\n",
                     "docs/image.png": "\u2013", "runs/old.log": "\u2014"}
            for name, text in files.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
            (root/"untracked.md").write_text("\u2014", encoding="utf-8")
            failures = ci.check_dashes(root)
            self.assertEqual(len(failures), 6, failures)
            self.assertTrue(any("docs/read me.md:2" in f and "U+2013" in f for f in failures))
            self.assertTrue(any("docs/read me.md:3" in f and "U+2014" in f for f in failures))
            self.assertTrue(all("no en or em dashes" in f for f in failures))
            for name in files:
                path = root/name
                path.write_text(files[name].replace("\u2013", "to").replace("\u2014", "."), encoding="utf-8")
            self.assertEqual(ci.check_dashes(root), [])

    def test_dashes_reports_git_failure(self):
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="not a repository")
        with patch.object(ci.subprocess, "run", return_value=result):
            failures = ci.check_dashes(Path("missing"))
        self.assertEqual(len(failures), 1)
        self.assertIn("git ls-files failed", failures[0])

    def test_all_runs_the_dash_gate(self):
        called = []
        stubs = {name: (lambda root, _name=name, **kw: called.append(_name) or [])
                 for name in (*ci.CHECKS, "dashes")}
        with patch.dict(ci.CHECKS, stubs), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ci.main(["all"]), 0)
        self.assertIn("dashes", called)


if __name__ == "__main__":
    unittest.main()
