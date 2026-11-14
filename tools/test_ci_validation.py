"""Focused regression tests for repository validation rules."""
import contextlib
import io
import json
import shutil
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

    @staticmethod
    def _refuted_repo(td, files, registry=None):
        """A throwaway git repo holding a synthetic refuted-claims registry."""
        root = Path(td)
        subprocess.run(["git", "init", "-q", td], check=True, capture_output=True)
        if registry is None:
            registry = {"archives": ["docs/plans/", "runs/"],
                        "default_markers": ["refut"],
                        "claims": [{"id": "cheese", "pattern": r"moon\s+is\s+cheese",
                                    "claim": "the moon is cheese",
                                    "correction": "it is rock", "refuted": "1969-07-20",
                                    "example": "everyone knows the moon is cheese"}]}
        files = {"tools/refuted_claims.json": json.dumps(registry), **files}
        for name, text in files.items():
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        return root

    def test_refuted_flags_current_claims_and_spares_history(self):
        files = {"AGENTS.md": "Rule: the moon is cheese.\n",
                 "src/bot.qc": "// the moon is cheese, so calibrate to it\nfloat x;\n",
                 "docs/notes.md": "Old notes said the moon is cheese.\nThat was refuted in 1969.\n",
                 "docs/apart.md": "The moon is cheese.\n\nSomething else was refuted.\n",
                 "src/comment.qc": "// the moon is cheese\n//\n// refuted elsewhere\n",
                 "docs/plans/old.md": "the moon is cheese\n",
                 "runs/tape.log": "the moon is cheese\n",
                 "data.json": "\"the moon is cheese\"\n"}
        with tempfile.TemporaryDirectory() as td:
            root = self._refuted_repo(td, files)
            (root/"untracked.md").write_text("the moon is cheese\n", encoding="utf-8")
            failures = ci.check_refuted(root)
        flagged = sorted(f.split(": ")[1] for f in failures)
        self.assertEqual(flagged, ["AGENTS.md:1", "docs/apart.md:1",
                                   "src/bot.qc:1", "src/comment.qc:1"], failures)
        self.assertTrue(all("was refuted 1969-07-20; it is rock" in f for f in failures))

    def test_refuted_reads_the_untracked_brief_when_present(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._refuted_repo(td, {"docs/ok.md": "Nothing to see.\n"})
            (root/"CLAUDE.md").write_text("# Brief\n\nCalibrate: the moon is cheese.\n",
                                          encoding="utf-8")
            failures = ci.check_refuted(root)
        self.assertEqual([f.split(": ")[1] for f in failures], ["CLAUDE.md:3"], failures)
        self.assertNotIsInstance(failures, ci.PartialOk)

    def test_refuted_says_when_the_brief_was_not_checked(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._refuted_repo(td, {"docs/ok.md": "Nothing to see.\n"})
            result = ci.check_refuted(root)
            self.assertIsInstance(result, ci.PartialOk)
            self.assertEqual(result, [])
            self.assertIn("CLAUDE.md", result.message)
            self.assertIn("not checked", result.message)
            (root/"CLAUDE.md").write_text("The moon is rock.\n", encoding="utf-8")
            checked = ci.check_refuted(root)
        self.assertEqual(checked, [])
        self.assertNotIsInstance(checked, ci.PartialOk)

    def test_refuted_registry_entries_must_prove_themselves(self):
        registry = {"default_markers": ["refut"], "claims": [
            {"id": "drifted", "pattern": "moon is cheese", "claim": "c", "correction": "r",
             "refuted": "d", "example": "the sun is cheese"},
            {"id": "marked", "pattern": "moon is cheese", "claim": "c", "correction": "r",
             "refuted": "d", "example": "the refuted moon is cheese"},
            {"id": "broken", "pattern": "(", "claim": "c", "correction": "r",
             "refuted": "d", "example": "x"},
            {"id": "bare", "pattern": "x"}]}
        with tempfile.TemporaryDirectory() as td:
            failures = ci.check_refuted(self._refuted_repo(td, {}, registry))
        joined = "\n".join(failures)
        self.assertEqual(len(failures), 4, failures)
        self.assertIn("drifted does not match its own example", joined)
        self.assertIn("marked has an example that carries a marker", joined)
        self.assertIn("broken has a bad pattern", joined)
        self.assertIn("bare lacks claim, correction, refuted, example", joined)

    def test_refuted_reports_a_missing_registry_and_git_failure(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True, capture_output=True)
            failures = ci.check_refuted(Path(td))
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("cannot read tools/refuted_claims.json", failures[0])
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="not a repository")
        with patch.object(ci.subprocess, "run", return_value=result):
            failures = ci.check_refuted(Path("missing"))
        self.assertEqual(failures, ["refuted: git ls-files failed: not a repository"])

    def test_shipped_refuted_registry_is_valid(self):
        claims, archives, failures = ci.load_refuted_registry(ci.ROOT)
        self.assertEqual(failures, [])
        self.assertGreaterEqual(len(claims), 3)
        self.assertIn("docs/changelog-history.md", archives)

    def test_all_runs_the_refuted_gate(self):
        self.assertIs(ci.CHECKS["refuted"], ci.check_refuted)

    def test_all_runs_the_lab_gate_and_it_passes_on_the_tree(self):
        self.assertIs(ci.CHECKS["lab"], ci.check_lab)
        self.assertEqual(ci.check_lab(ci.ROOT), [])

    def test_lab_gate_reports_a_bad_claim_and_skips_without_an_objective(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertIsInstance(ci.check_lab(root), ci.Skipped)
            (root / "tools").mkdir()
            (root / "runs").mkdir()
            (root / "docs").mkdir()
            shutil.copy(ci.ROOT / "tools" / "lab_objective.json", root / "tools")
            shutil.copy(ci.ROOT / "tools" / "argus_lab.py", root / "tools")
            obj = json.loads((root / "tools" / "lab_objective.json").read_text(encoding="utf-8"))
            obj["limits_doc"] = "docs/limits.md"
            (root / "tools" / "lab_objective.json").write_text(json.dumps(obj), encoding="utf-8")
            (root / "docs" / "limits.md").write_text("# limits\n", encoding="utf-8")
            (root / "tools" / "lab_claims.json").write_text(json.dumps({"claims": [
                {"id": "x", "title": "X", "status": "fixed", "kind": "defect", "statement": "s",
                 "evidence": ["#1"]}]}), encoding="utf-8")
            failures = ci.check_lab(root)
        self.assertTrue(any("a fixed claim says when" in f for f in failures), failures)

    def test_all_runs_the_dash_gate(self):
        called = []
        stubs = {name: (lambda root, _name=name, **kw: called.append(_name) or [])
                 for name in (*ci.CHECKS, "dashes")}
        with patch.dict(ci.CHECKS, stubs), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ci.main(["all"]), 0)
        self.assertIn("dashes", called)


if __name__ == "__main__":
    unittest.main()
