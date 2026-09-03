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

    def test_argus_review_freeze_detector(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_review
        # 1 Hz samples over 6s (Issue #156):
        # Bot1 drifts 25 u in x over 6s (25 < 32 u circle): freeze in Euclidean metric!
        # (Under old 24 u box metric this was falsely rejected because dx > 24).
        bot1_recs = [
            {"t": float(i), "x": 100.0 + (i * 25.0 / 6.0), "y": 200.0, "z": 0.0, "spd": 4.0, "mode": 2, "line": i + 1}
            for i in range(7)
        ]
        # Bot2 drifts 35 u in x over 6s (35 > 32 u circle): not a freeze.
        bot2_recs = [
            {"t": float(i), "x": 100.0 + (i * 35.0 / 6.0), "y": 200.0, "z": 0.0, "spd": 5.0, "mode": 2, "line": i + 10}
            for i in range(7)
        ]
        bots = {"Bot1": bot1_recs, "Bot2": bot2_recs}
        fz = argus_review.freezes(bots)
        self.assertEqual(len(fz), 1)
        self.assertEqual(fz[0][0], "Bot1")
        self.assertAlmostEqual(fz[0][3], 6.0)

    def test_argus_mcp_cli_subcommands(self):
        bin_names = ["argus-mcp.exe", "argus-mcp"]
        mcp_bin = None
        for profile in ("debug", "release"):
            for name in bin_names:
                p = ROOT / "tools" / "argus_mcp" / "target" / profile / name
                if p.is_file():
                    mcp_bin = p
                    break
            if mcp_bin:
                break
        if not mcp_bin:
            self.skipTest("argus-mcp binary not built")

        for cmd in ("--help", "compile -h", "reach -h", "harvest -h", "analyze -h", "nav -h"):
            args = cmd.split()
            res = subprocess.run([str(mcp_bin), *args], capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(res.returncode, 0, f"failed on {cmd}: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
