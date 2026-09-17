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

    def test_argus_navgen_models_a_vertical_start_open_parked_slab(self):
        # #331: a vertical door that starts open is the one vertical
        # case that parks IN its doorway. doors.qc swaps pos1 and pos2,
        # so it sits a travel clear at spawn and the first trigger puts
        # the slab back in the box it was compiled in. Seat the graph
        # at z 60, where both the shut box (56..120) and the parked one
        # (0..64) reach, so the same link is typed and reported.
        nodes = [[p[0], p[1], 60.0] for p in self.DOOR_FIXTURE_NODES]
        tmp = self.door_fixture(spawnflags=1, angle="-1", nodes=nodes)
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1 parked slab(s)", res.stdout)
        self.assertIn("door *1 parks on link n0->n1 when open", res.stdout)

    def test_argus_navgen_leaves_a_plain_vertical_door_unparked(self):
        # the other half of the filter, and the reason it is a filter
        # rather than a blanket change: a vertical door WITHOUT
        # START_OPEN travels out of the doorway when it opens, so it
        # has no parked box and 5b3 must keep saying so. Same fixture,
        # same seats, spawnflags 0.
        nodes = [[p[0], p[1], 60.0] for p in self.DOOR_FIXTURE_NODES]
        tmp = self.door_fixture(spawnflags=0, angle="-1", nodes=nodes)
        res = self.retype(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("0 parked slab(s)", res.stdout)
        self.assertNotIn("parks on link", res.stdout)

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

    def test_longi_reproduces_the_v405_row(self):
        """The scorecard is the instrument that sees what Shane sees.

        The v405 session is the last human dm4 tape on record and the
        CHANGELOG reports it as 18 and 11 with 7 stalls and no freezes.
        If the scorecard cannot reproduce that row it cannot judge the
        sessions phases 1 and 2 turn on.
        """
        tape = ROOT / "runs" / "shane_dm4_2026-08-29_v405.log"
        if not tape.is_file():
            self.skipTest("v405 session tape not present")
        res = self.run_tool("argus_longi.py", str(tape))
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        row = dict(zip(lines[0].split("\t"), lines[1].split("\t")))
        self.assertEqual(row["bot_kills_human"], "10")
        self.assertEqual(row["human_kills_bot"], "18")
        self.assertEqual(row["stalls"], "7")
        self.assertEqual(row["freezes"], "0")
        self.assertEqual(row["unstick"], "0")

    def test_tick_estimator_separates_listen_from_dedicated(self):
        """A tape says which game it recorded, or it cannot be compared."""
        pairs = [
            ("shane_dm4_2026-08-29_v405.log", "70 Hz"),
            ("ab_dm2_corridor1.log", "19 Hz"),
            ("ab_dm2_doors.log", "14 to 15 Hz"),
        ]
        for name, want in pairs:
            tape = ROOT / "runs" / name
            if not tape.is_file():
                continue
            res = self.run_tool("argus_tick.py", str(tape))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn(want, res.stdout, f"{name}: {res.stdout}")

    def test_harvest_appends_a_scorecard_row(self):
        """Every harvested session lands one row in the scorecard.

        A human session that is not scored is a session nobody can
        compare to the one before it, which is how a month of them
        passed without the dm2 stall rate being noticed.
        """
        import csv as _csv
        tape = ROOT / "runs" / "shane_dm4_2026-08-29_v405.log"
        if not tape.is_file():
            self.skipTest("v405 session tape not present")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "human_scorecard.tsv"
            res = self.run_tool(
                "argus_longi.py", "--append", str(out), str(tape)
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            # appending twice must not duplicate the tape
            res = self.run_tool(
                "argus_longi.py", "--append", str(out), str(tape)
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            rows = list(_csv.DictReader(out.open(), delimiter="\t"))
            self.assertEqual(len(rows), 1, rows)
            self.assertEqual(rows[0]["bot_kills_human"], "10")

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

    def test_argus_ci_help(self):
        res = self.run_tool("argus_ci.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Argus repo invariant battery", res.stdout)

    def test_argus_ci_ship_passes_on_the_tree(self):
        # CLAUDE.md is gitignored (machine-local), so this tree holds
        # it locally but a CI checkout never does. Pass either way:
        # the full "ship: ok" when CLAUDE.md is present, the partial
        # "handoff hash not checked" wording when it is not. Either
        # way returncode must be 0 - that is the claim that matters.
        res = self.run_tool("argus_ci.py", "ship")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(
            "ship: ok" in res.stdout or "handoff hash not checked" in res.stdout,
            res.stdout + res.stderr)

    def test_argus_ci_ship_passes_without_claude_md(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game" / "argus").mkdir(parents=True)
            (root / "engine" / "argus").mkdir(parents=True)
            for p in ("game", "engine"):
                (root / p / "argus" / "progs.dat").write_bytes(b"aaaa")
            res = self.run_tool("argus_ci.py", "ship", "--root", str(root))
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("handoff hash not checked", res.stdout)

    def test_argus_ci_ship_catches_a_mismatched_pair_without_claude_md(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game" / "argus").mkdir(parents=True)
            (root / "engine" / "argus").mkdir(parents=True)
            (root / "game" / "argus" / "progs.dat").write_bytes(b"aaaa")
            (root / "engine" / "argus" / "progs.dat").write_bytes(b"bbbb")
            res = self.run_tool("argus_ci.py", "ship", "--root", str(root))
            self.assertEqual(res.returncode, 1)
            self.assertIn("differ", res.stdout)

    def test_argus_ci_ship_catches_a_mismatched_pair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game" / "argus").mkdir(parents=True)
            (root / "engine" / "argus").mkdir(parents=True)
            (root / "game" / "argus" / "progs.dat").write_bytes(b"aaaa")
            (root / "engine" / "argus" / "progs.dat").write_bytes(b"bbbb")
            (root / "CLAUDE.md").write_text(
                "## State at handoff (test)\n\nMD5 "
                "74B87337454200D4D33F80C4663DC5E5\n", encoding="utf-8")
            res = self.run_tool("argus_ci.py", "ship", "--root", str(root))
            self.assertEqual(res.returncode, 1)
            self.assertIn("differ", res.stdout)

    def test_argus_ci_ship_catches_a_stale_handoff_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game" / "argus").mkdir(parents=True)
            (root / "engine" / "argus").mkdir(parents=True)
            for p in ("game", "engine"):
                (root / p / "argus" / "progs.dat").write_bytes(b"aaaa")
            (root / "CLAUDE.md").write_text(
                "## State at handoff (test)\n\nMD5 "
                "00000000000000000000000000000000\n", encoding="utf-8")
            res = self.run_tool("argus_ci.py", "ship", "--root", str(root))
            self.assertEqual(res.returncode, 1)
            self.assertIn("handoff claims", res.stdout)

    def _changed_file(self, root, lines):
        p = Path(root) / "changed.txt"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)

    def test_argus_ci_tapes_allows_additions(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, [
                "A\truns/ab_dm4_newladder1.log",
                "A\truns/shane_dm2_2026-09-17.log",
            ])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 0, res.stdout)
            self.assertIn("tapes: ok", res.stdout)

    def test_argus_ci_tapes_exempts_mx_and_probe(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, [
                "M\truns/mx_dm2.log",
                "M\truns/probe_dm2.log",
            ])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_tapes_rejects_an_overwritten_ladder_tape(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["M\truns/ab_dm2_doortype2.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)
            self.assertIn("ab_dm2_doortype2.log", res.stdout)
            self.assertIn("append-once", res.stdout)

    def test_argus_ci_tapes_rejects_a_deleted_session_tape(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["D\truns/shane_dm4_2026-08-29_v405.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)
            self.assertIn("deleted", res.stdout)

    def test_argus_ci_tapes_accepts_the_github_status_words(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["modified\truns/ab_dm2_doortype2.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)

    def test_argus_ci_tapes_escape_hatch(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["M\truns/ab_dm4_unstick.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf,
                                "--commit-msg", "Re-run the ladder [tape-rewrite]")
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_tapes_escape_hatch_via_combined_title_and_commits(self):
        # fast.yml now builds --commit-msg from "$PR_TITLE $(cat
        # commit_msgs.txt)" - the escape token has to work from either
        # half of that combined string, not just a bare commit message.
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["M\truns/ab_dm4_unstick.log"])
            res = self.run_tool(
                "argus_ci.py", "tapes", "--changed-files", cf,
                "--commit-msg",
                "Fix the corner case\nRe-run the ladder [tape-rewrite]")
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_tapes_empty_changed_file_list_is_skipped(self):
        # A push to main gives fast.yml an empty changed.txt and no
        # --base - there is no changed-file information to check, and
        # "ok" here would be the vacuous pass #328 slipped through on.
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, [])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 0, res.stdout)
            tapes_line = next(
                line for line in res.stdout.splitlines()
                if line.startswith("tapes"))
            self.assertIn("skipped", tapes_line)
            self.assertNotIn("ok", tapes_line)

    def test_argus_ci_tapes_bad_base_ref_fails_loudly(self):
        # A missing ref, a shallow clone, or git not on PATH must fail
        # the check, not silently pass as "ok" - this is the local
        # pre-push path the tool exists to serve.
        res = self.run_tool("argus_ci.py", "tapes", "--base", "no/such/ref")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("no/such/ref", res.stdout)

    def test_argus_ci_tapes_rejects_a_renamed_ladder_tape(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["R100\truns/ab_dm2_doortype2.log\truns/ab_renamed.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)
            self.assertIn("ab_dm2_doortype2.log", res.stdout)
            self.assertIn("was renamed", res.stdout)

    def test_argus_ci_tapes_allows_a_renamed_exempt_tape(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["R100\truns/mx_dm2.log\truns/mx_dm2_old.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 0, res.stdout)

    def _nav_qc(self, root, name, body):
        d = Path(root) / "src"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")

    def test_argus_ci_nav_passes_on_the_tree(self):
        res = self.run_tool("argus_ci.py", "nav")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("nav: ok", res.stdout)

    def test_argus_ci_nav_accepts_a_healthy_graph(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc", """
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('64 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLink (n1, n0);
""")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_nav_catches_an_over_budget_node(self):
        links = "\n".join("    Argus_NavLink (n0, n%d);" % i
                          for i in range(1, 11))
        nodes = "\n".join("    n%d = Argus_NavNode ('%d 0 0');" % (i, i * 64)
                          for i in range(0, 11))
        back = "\n".join("    Argus_NavLink (n%d, n0);" % i
                         for i in range(1, 11))
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc",
                         nodes + "\n" + links + "\n" + back + "\n")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 1)
            self.assertIn("8-slot", res.stdout)

    def test_argus_ci_nav_catches_a_no_exit_orphan(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc", """
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('64 0 0');
    n2 = Argus_NavNode ('128 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLink (n1, n0);
    Argus_NavLink (n1, n2);
""")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 1)
            self.assertIn("no outbound edge", res.stdout)

    def test_argus_ci_nav_counts_typed_links_as_exits(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc", """
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('64 0 0');
    n2 = Argus_NavNode ('128 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLink (n1, n0);
    Argus_NavLink (n1, n2);
    Argus_NavLinkRocket (n2, n0);
""")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_nav_skips_the_dispatcher(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_dispatch.qc",
                         "void() Argus_NavLoad = { };\n")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 0, res.stdout)


if __name__ == "__main__":
    unittest.main()
