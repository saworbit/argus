#!/usr/bin/env python3
"""CLI regression tests for developer scripts in tools/."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestToolsCLI(unittest.TestCase):
    def run_tool(self, script_name, *args):
        path = ROOT / "tools" / script_name
        cmd = [sys.executable, str(path), *args]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))

    def test_analyze_match_missing_args(self):
        res = self.run_tool("analyze_match.py")
        self.assertEqual(res.returncode, 1)
        self.assertIn("error: analyze_match.py requires at least map.bsp, logA, and out.png", res.stderr)

    def test_analyze_match_help(self):
        res = self.run_tool("analyze_match.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Botlab/Argus match analysis v3", res.stdout)

        res_short = self.run_tool("analyze_match.py", "-h")
        self.assertEqual(res_short.returncode, 0)

    def test_argus_review_help(self):
        res = self.run_tool("argus_review.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Argus tape review battery", res.stdout)

        res_none = self.run_tool("argus_review.py")
        self.assertEqual(res_none.returncode, 0)

    def test_argus_review_missing_log(self):
        for cmd in ("summary", "deaths", "rides"):
            res = self.run_tool("argus_review.py", cmd)
            self.assertEqual(res.returncode, 1)
            self.assertIn(f"error: {cmd} requires <log>", res.stderr)

    def test_argus_review_region_missing_coords(self):
        res = self.run_tool("argus_review.py", "region")
        self.assertEqual(res.returncode, 1)
        self.assertIn("error: region requires <log> <bot|all> <x0> <x1> <y0> <y1>", res.stderr)

    def test_argus_reach_help(self):
        res = self.run_tool("argus_reach.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Directed-reach audit for SHIPPED nav graphs", res.stdout)

    def test_argus_reach_missing_map(self):
        res = self.run_tool("argus_reach.py", "nonexistent_map_name_test")
        self.assertEqual(res.returncode, 1)
        self.assertIn("REACH GATE: verdict FAIL", res.stdout)


if __name__ == "__main__":
    unittest.main()
