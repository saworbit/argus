#!/usr/bin/env python3
"""CLI regression tests for developer scripts in tools/."""
import json
import shutil
import subprocess
import sys
import tempfile
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

    def test_argus_navgen_grid_validation(self):
        res_missing = self.run_tool("argus_navgen.py", "dummy.bsp", "dm4", "out.qc", "out.png", "--grid")
        self.assertEqual(res_missing.returncode, 1)
        self.assertIn("error: --grid requires an integer argument", res_missing.stderr)

        res_invalid = self.run_tool("argus_navgen.py", "dummy.bsp", "dm4", "out.qc", "out.png", "--grid", "notanint")
        self.assertEqual(res_invalid.returncode, 1)
        self.assertIn("error: --grid argument must be an integer", res_invalid.stderr)

    def test_argus_reach_empty_spawns(self):
        # #113's fix is "no spawns in the BSP is a FAIL, not a pass".
        # This test used to call audit("dm2") against the real tree,
        # which returns None on any runner without maps_local (it is
        # gitignored licensed data), and assertFalse(None) passes - so
        # CI never ran the branch it names. Build the inputs instead.
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_reach
        tmp = Path(tempfile.mkdtemp(prefix="argus-reach-"))
        (tmp / "maps_local").mkdir()
        (tmp / "src").mkdir()
        (tmp / "maps_local" / "fixture.bsp").write_bytes(b"not a real bsp")
        (tmp / "src" / "argus_nav_fixture.qc.json").write_text(json.dumps({
            "nodes": [[0, 0, 24], [64, 0, 24], [128, 0, 24]],
            "links": [[0, 1, 1], [1, 0, 1], [1, 2, 1], [2, 1, 1]],
        }))
        orig_spawns = argus_reach.bsp_spawns
        orig_root = argus_reach.ROOT
        try:
            argus_reach.ROOT = tmp
            # a BSP with no deathmatch spawn at all is the #113 case
            argus_reach.bsp_spawns = lambda path: []
            self.assertIs(argus_reach.audit("fixture"), False)
            # and with a spawn present the same graph passes, so the
            # False above is the empty-spawn branch and not the skip
            argus_reach.bsp_spawns = lambda path: [(0, 0, 24)]
            self.assertIs(argus_reach.audit("fixture"), True)
            # a map with no BSP still skips, returning None
            self.assertIsNone(argus_reach.audit("absent"))
        finally:
            argus_reach.bsp_spawns = orig_spawns
            argus_reach.ROOT = orig_root
            shutil.rmtree(tmp, ignore_errors=True)

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
