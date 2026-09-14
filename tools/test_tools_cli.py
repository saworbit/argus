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

    # ---- --retype-doors (#330) ----
    # The fixtures are BUILT, not borrowed from maps_local, because
    # that directory is gitignored licensed data and a test that skips
    # on the runner is a test CI never runs (the lesson recorded on
    # test_argus_reach_empty_spawns, one method up). A retype needs a
    # BSP only for its entity lump and its model bboxes, so twelve
    # lines of struct is a whole map as far as this mode is concerned.
    DOOR_FIXTURE_LINKS = [
        "    Argus_NavLink (n0, n1);",
        "    Argus_NavLinkDoor (n2, n3);",
        "    Argus_NavLink (n4, n5);",
        "    Argus_NavLinkJump (n1, n0);",
        "    Argus_NavLink (n3, n0);    // teleporter",
    ]
    DOOR_FIXTURE_NODES = [[-64.0, 0.0, 24.0], [128.0, 0.0, 24.0],
                          [80.0, 0.0, 24.0], [112.0, 0.0, 24.0],
                          [-64.0, 200.0, 24.0], [128.0, 200.0, 24.0]]

    def fixture_qc(self, nodes):
        out = ["/* generated by argus_navgen.py - do not edit */", "",
               "void() Argus_Nav_Spawn_fixture =", "{"]
        out += [f"    local entity n{i};" for i in range(len(nodes))]
        out.append("")
        out += [f"    n{i} = Argus_NavNode "
                f"('{p[0]:.0f} {p[1]:.0f} {p[2]:.0f}');"
                for i, p in enumerate(nodes)]
        out.append("")
        out += self.DOOR_FIXTURE_LINKS
        out.append(f'    dprint ("ARGNAV {len(nodes)} nodes, 5 links\\n");')
        out.append("};")
        return "\r\n".join(out) + "\r\n"

    def door_fixture(self, spawnflags=0, jsonnodes=None, nodes=None,
                     classname="func_door", angle="0"):
        """A one-door map, its graph, and the temp dir holding them.

        The door brush is built across x 0..64, y -32..32, z 0..64. At
        angle 0 it slides +x and parks across 56..120 (travel is size
        minus lip): n0 to n1 runs the length of the corridor and crosses
        both boxes, n2 to n3 sits inside the parked box only, which is
        #309's class, and n4 to n5 runs past the door entirely.
        """
        import struct
        nodes = self.DOOR_FIXTURE_NODES if nodes is None else nodes
        tmp = Path(tempfile.mkdtemp(prefix="argus-retype-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ents = (
            '{\n"classname" "worldspawn"\n}\n'
            f'{{\n"classname" "{classname}"\n"model" "*1"\n'
            f'"angle" "{angle}"\n"lip" "8"\n"spawnflags" "{spawnflags}"\n}}\n'
        ).encode("ascii") + b"\0"
        models = struct.pack("<9f7i", -512.0, -512.0, -64.0,
                             512.0, 512.0, 512.0, 0.0, 0.0, 0.0,
                             0, 0, 0, 0, 0, 0, 0)
        models += struct.pack("<9f7i", 0.0, -32.0, 0.0,
                              64.0, 32.0, 64.0, 0.0, 0.0, 0.0,
                              0, 0, 0, 0, 0, 0, 0)
        table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
        for idx, payload in ((0, ents), (1, b""), (9, b""), (14, models)):
            table[idx] = (base + len(blob), len(payload))
            blob += payload
        (tmp / "fixture.bsp").write_bytes(
            struct.pack("<i", 29)
            + b"".join(struct.pack("<ii", o, n) for o, n in table) + blob)
        # CRLF, because that is what navgen writes on the rig these
        # graphs come from and a rewrite must not reflow the file
        (tmp / "nav.qc").write_bytes(self.fixture_qc(nodes).encode("ascii"))
        (tmp / "nav.qc.json").write_text(json.dumps({
            "nodes": nodes if jsonnodes is None else jsonnodes,
            "links": [[0, 1, 1], [1, 0, 1], [2, 3, 1], [3, 2, 1]],
            "jlinks": [[1, 0]],
            "doorlinks": [[2, 3]],
            "regions": [0, 0, 0, 0, 0, 0],
            "teles": [[3, 0]],
        }))
        return tmp

    def retype(self, tmp, qc="nav.qc"):
        return self.run_tool("argus_navgen.py", str(tmp / "fixture.bsp"),
                             "fixture", str(tmp / qc), str(tmp / "out.png"),
                             "--retype-doors")

    def test_argus_navgen_retype_doors_is_in_the_usage(self):
        res = self.run_tool("argus_navgen.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("--retype-doors", res.stdout)

    def test_argus_navgen_retype_doors_needs_a_shipped_graph(self):
        tmp = self.door_fixture()
        res = self.retype(tmp, qc="absent.qc")
        self.assertEqual(res.returncode, 1)
        self.assertIn("have to exist already", res.stderr)

    def test_argus_navgen_retype_doors_refuses_a_mismatched_graph(self):
        # a json from another graph must not silently retype this one
        tmp = self.door_fixture(jsonnodes=self.DOOR_FIXTURE_NODES[:5])
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 1)
        self.assertIn("not the same graph", res.stderr)
        self.assertEqual((tmp / "nav.qc").read_bytes(),
                         self.fixture_qc(self.DOOR_FIXTURE_NODES).encode())

        moved = [list(p) for p in self.DOOR_FIXTURE_NODES]
        moved[3] = [113.0, 0.0, 24.0]
        tmp = self.door_fixture(jsonnodes=moved)
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 1)
        self.assertIn("n3 reads 112 0 24", res.stderr)

    def test_argus_navgen_retype_doors_rewrites_only_the_verbs(self):
        tmp = self.door_fixture()
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1 door links, 1 newly typed, 1 untyped", res.stdout)
        self.assertIn("of those 1: 0 cross the box the door is compiled in, "
                      "1 cross a slab where it parks", res.stdout)
        self.assertIn("door *1 parks on link n0->n1 when open", res.stdout)

        out = (tmp / "nav.qc").read_bytes()
        self.assertNotIn(b"\n", out.replace(b"\r\n", b""))
        got = out.decode("ascii").replace("\r\n", "\n").splitlines()
        want = self.fixture_qc(self.DOOR_FIXTURE_NODES).replace(
            "\r\n", "\n").splitlines()
        # the corridor link is typed, the parked-slab-only one is not,
        # and every other line in the file is untouched. Both the jump
        # verb and the teleporter line cross the same shut slab, and a
        # regen types neither, so neither may move here.
        want[want.index("    Argus_NavLink (n0, n1);")] = \
            "    Argus_NavLinkDoor (n0, n1);"
        want[want.index("    Argus_NavLinkDoor (n2, n3);")] = \
            "    Argus_NavLink (n2, n3);"
        self.assertEqual(got, want)

        js = json.loads((tmp / "nav.qc.json").read_text())
        self.assertEqual(js["doorlinks"], [[0, 1]])
        self.assertEqual(list(js), ["nodes", "links", "jlinks", "doorlinks",
                                    "regions", "teles"])
        self.assertEqual(js["links"], [[0, 1, 1], [1, 0, 1], [2, 3, 1],
                                       [3, 2, 1]])
        self.assertEqual(js["jlinks"], [[1, 0]])
        self.assertEqual(js["teles"], [[3, 0]])
        self.assertEqual(js["nodes"], self.DOOR_FIXTURE_NODES)

    def test_argus_navgen_retype_doors_reads_start_open(self):
        # DOOR_START_OPEN swaps pos1 and pos2, so the compiled box IS
        # the parked one and the shut slab is a travel away (#309 had
        # this backwards for seven doors). Same fixture, one spawnflag:
        # the door now shuts across 56..120, so the verdicts swap.
        tmp = self.door_fixture(spawnflags=1)
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("2 door links, 1 newly typed, 0 untyped", res.stdout)
        js = json.loads((tmp / "nav.qc.json").read_text())
        self.assertEqual(js["doorlinks"], [[0, 1], [2, 3]])

    def test_argus_navgen_retype_doors_reads_a_vertical_start_open(self):
        # subs.qc SetMovedir reads angle -1 as UP, so this door shuts
        # 56 units above the box it was compiled in (#330: the two
        # angles were the wrong way round, which reflected every
        # vertical START_OPEN slab to the far side of its doorway).
        # Seat the graph at z 80, between the two answers.
        nodes = [[p[0], p[1], 80.0] for p in self.DOOR_FIXTURE_NODES]
        tmp = self.door_fixture(spawnflags=1, angle="-1", nodes=nodes)
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1 door links, 1 newly typed, 1 untyped", res.stdout)
        js = json.loads((tmp / "nav.qc.json").read_text())
        self.assertEqual(js["doorlinks"], [[0, 1]])

    def test_argus_navgen_retype_doors_reads_a_secret_door(self):
        # a func_door_secret is built shut and its bit 1 is
        # SECRET_OPEN_ONCE, not START_OPEN (#330). Read as a
        # func_door's flag it swapped the box a travel away and the
        # crossing lost the type it had earned.
        tmp = self.door_fixture(spawnflags=1, classname="func_door_secret")
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1 door links, 1 newly typed, 1 untyped", res.stdout)
        js = json.loads((tmp / "nav.qc.json").read_text())
        self.assertEqual(js["doorlinks"], [[0, 1]])

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
