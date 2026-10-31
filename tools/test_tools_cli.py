#!/usr/bin/env python3
"""CLI regression tests for developer scripts in tools/."""
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_argus_mcp_binary(root=ROOT, *, installed=False):
    if installed:
        search_dirs = [root / "tools" / "argus_mcp" / "install" / "bin"]
    else:
        search_dirs = [
            root / "tools" / "argus_mcp" / "target" / "debug",
            root / "tools" / "argus_mcp" / "target" / "release",
        ]
    for directory in search_dirs:
        for name in ("argus-mcp.exe", "argus-mcp"):
            path = directory / name
            if path.is_file():
                return path
    return None


class TestToolsCLI(unittest.TestCase):
    def test_nav_preview_regressions(self):
        res = self.run_tool("test_nav_preview.py")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_navgen_missing_plotter_does_not_present_an_old_preview(self):
        tmp = self.door_fixture(collision_gap=True)
        qc, png = tmp / "new.qc", tmp / "out.png"
        png.write_bytes(b"old graph preview")
        code = (
            "import sys, runpy; sys.path.insert(0, " + repr(str(ROOT / "tools")) + "); "
            "sys.modules['matplotlib'] = None; "
            "sys.argv = " + repr([str(ROOT / "tools/argus_navgen.py"), str(tmp / "fixture.bsp"),
                                  "fixture", str(qc), str(png), "--no-dispatcher"]) + "; "
            "runpy.run_path(sys.argv[0], run_name='__main__')"
        )
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(qc.is_file())
        self.assertTrue(Path(str(qc) + ".json").is_file())
        state = json.loads(Path(str(png) + ".json").read_text())
        self.assertFalse(state["generated"])
        self.assertNotIn("png_md5", state)
        self.assertEqual(png.read_bytes(), b"old graph preview")
        self.assertIn("debug plot skipped", res.stdout)

    def test_tactic_fixture_checker_regressions(self):
        res = self.run_tool("test_tactic_fixture.py")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_tactic_review_regressions(self):
        res = self.run_tool("test_tactic_review.py")
        self.assertEqual(res.returncode, 0, res.stderr)

    def run_tool(self, script_name, *args):
        path = ROOT / "tools" / script_name
        cmd = [sys.executable, str(path), *args]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))

    def test_analyze_match_import_has_no_cli_or_plotting_side_effects(self):
        code = ("import sys; sys.path.insert(0, " + repr(str(ROOT/"tools")) + "); "
                "sys.argv=['analyze_match.py', '--help']; import analyze_match; "
                "assert 'matplotlib' not in sys.modules; print('safe import')")
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run([sys.executable, "-c", code], cwd=td,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "safe import\n")
            self.assertEqual(list(Path(td).iterdir()), [])

    def _hull0_bsp(self, path, root=1):
        def node(plane, front, back):
            return struct.pack("<i8h2H", plane, front, back, *([0]*8))
        def leaf(contents):
            return struct.pack("<2i6h2H4B", contents, *([0]*13))
        parts = {
            1: struct.pack("<4fi", 1, 0, 0, 0, 0) + struct.pack("<4fi", 0, 0, 1, 0, 2),
            5: node(0, -3, -3) + node(1, -1, 2) + node(0, -2, -3),
            10: leaf(-1) + leaf(-5) + leaf(-4),
            14: struct.pack("<9f7i", *([0.0]*9), root, *([0]*6)),
        }
        data, entries = b"", []
        for i in range(15):
            part = parts.get(i, b"")
            entries.append((124+len(data), len(part)))
            data += part
        path.write_bytes(struct.pack("<i", 29) + b"".join(struct.pack("<ii", *row) for row in entries) + data)

    def test_analyzer_and_voidprobe_share_world_hull0_classification(self):
        sys.path.insert(0, str(ROOT/"tools"))
        import analyze_match
        import argus_bsp
        import argus_voidprobe
        self.assertIs(argus_voidprobe.classifier, argus_bsp.load_classifier)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"world.bsp"
            self._hull0_bsp(path)
            for contents in (argus_voidprobe.classifier(path), analyze_match.bsp_contents_classifier(path)):
                self.assertEqual(contents(1, 0, 10), -1)
                self.assertEqual(contents(1, 0, -10), -5)
                self.assertEqual(contents(-1, 0, -10), -4)
            # A negative world headnode denotes a leaf directly.
            self._hull0_bsp(path, root=-2)
            self.assertEqual(argus_bsp.load_classifier(path)(-1, 0, 10), -5)

    def test_analyzer_preserves_lava_death_boundary_and_missing_bsp_policy(self):
        sys.path.insert(0, str(ROOT/"tools"))
        import analyze_match
        import argus_voidprobe
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td)/"missing.bsp"
            self.assertIsNone(analyze_match.bsp_contents_classifier(missing))
            with self.assertRaises(OSError):
                argus_voidprobe.classifier(missing)
            self.assertFalse(analyze_match.death_is_lava(None, 0, 0, -300))
            self.assertTrue(analyze_match.death_is_lava(None, 0, 0, -301))
            for contents in (-2, -3):
                self.assertFalse(analyze_match.death_is_lava(lambda *p: contents, 0, 0, -400))
            path = Path(td)/"world.bsp"
            self._hull0_bsp(path)
            contents = analyze_match.bsp_contents_classifier(path)
            self.assertTrue(analyze_match.death_is_lava(contents, 1, 0, 10))
            self.assertTrue(analyze_match.death_is_lava(contents, -1, 0, 10))
            self.assertFalse(analyze_match.death_is_lava(contents, 1, 0, 24))

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

    def test_mcp_example_uses_the_stable_install(self):
        config = json.loads((ROOT / ".mcp.json.example").read_text(encoding="utf-8"))
        command = config["mcpServers"]["argus"]["command"].replace("\\", "/")
        self.assertIn("/tools/argus_mcp/install/bin/argus-mcp", command)
        self.assertNotIn("/target/", command)

    def test_mcp_config_migration_preserves_json_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / "tools" / "argus_mcp" / "install" / "bin" / "argus-mcp.exe"
            installed.parent.mkdir(parents=True)
            installed.touch()
            path = root / ".mcp.json"
            old_command = str(root / "tools/argus_mcp/target/release/argus-mcp.exe")
            before = {
                "mcpServers": {
                    "argus": {
                        "command": old_command,
                        "env": {"ARGUS_ROOT": "C:/argus", "KEEP": "yes"},
                        "startup_timeout_sec": 15,
                        "tool_timeout_sec": 700,
                    },
                    "other": {"command": old_command},
                }
            }
            path.write_text(json.dumps(before, indent=4), encoding="utf-8")

            res = self.run_tool("migrate_mcp_config.py", str(path))

            self.assertEqual(res.returncode, 0, res.stderr)
            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                Path(after["mcpServers"]["argus"]["command"]),
                installed,
            )
            self.assertEqual(after["mcpServers"]["argus"]["env"], before["mcpServers"]["argus"]["env"])
            self.assertEqual(after["mcpServers"]["argus"]["startup_timeout_sec"], 15)
            self.assertEqual(after["mcpServers"]["argus"]["tool_timeout_sec"], 700)
            self.assertEqual(after["mcpServers"]["other"], before["mcpServers"]["other"])
            self.assertIn("restart the MCP client", res.stdout)

    def test_mcp_config_migration_preserves_toml_settings_and_comments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / "tools" / "argus_mcp" / "install" / "bin" / "argus-mcp.exe"
            installed.parent.mkdir(parents=True)
            installed.touch()
            path = root / "config.toml"
            old_command = (root / "tools/argus_mcp/target/release/argus-mcp.exe").as_posix()
            before = f"""# keep this comment
[mcp_servers.argus]
command = "{old_command}"
startup_timeout_sec = 15
tool_timeout_sec = 700
tool_timeouts = {{ match_run = 700, compile_qc = 120 }}

[mcp_servers.argus.env]
ARGUS_ROOT = "C:/argus"
KEEP = "yes"

[mcp_servers.other]
command = "leave-me-alone"
"""
            path.write_text(before, encoding="utf-8")

            res = self.run_tool("migrate_mcp_config.py", str(path))

            self.assertEqual(res.returncode, 0, res.stderr)
            after = path.read_text(encoding="utf-8")
            self.assertIn("# keep this comment", after)
            self.assertIn(installed.as_posix(), after)
            self.assertNotIn(old_command, after)
            for unchanged in (
                "startup_timeout_sec = 15",
                "tool_timeout_sec = 700",
                "tool_timeouts = { match_run = 700, compile_qc = 120 }",
                'ARGUS_ROOT = "C:/argus"',
                'KEEP = "yes"',
                'command = "leave-me-alone"',
            ):
                self.assertIn(unchanged, after)

    def test_mcp_config_migration_refuses_a_near_match(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            before = """[mcp_servers.argus]
command = "C:/argus/tools/argus_mcp/target/debug/argus-mcp.exe"
tool_timeout_sec = 700
"""
            path.write_text(before, encoding="utf-8")

            res = self.run_tool("migrate_mcp_config.py", str(path))

            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertIn("unchanged", res.stdout)

    def test_mcp_config_migration_refuses_a_missing_stable_binary(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            before = f"""[mcp_servers.argus]
command = "{(Path(td) / 'tools/argus_mcp/target/release/argus-mcp.exe').as_posix()}"
tool_timeout_sec = 700
"""
            path.write_text(before, encoding="utf-8")

            res = self.run_tool("migrate_mcp_config.py", str(path))

            self.assertEqual(res.returncode, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertIn("stable installed binary not found", res.stderr)

    def test_mcp_binary_discovery_separates_source_and_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "tools" / "argus_mcp" / "target" / "debug" / "argus-mcp"
            installed = root / "tools" / "argus_mcp" / "install" / "bin" / "argus-mcp"
            source.parent.mkdir(parents=True)
            installed.parent.mkdir(parents=True)
            source.touch()
            installed.touch()

            self.assertEqual(find_argus_mcp_binary(root), source)
            self.assertEqual(find_argus_mcp_binary(root, installed=True), installed)

            source.unlink()
            self.assertIsNone(find_argus_mcp_binary(root))

    def test_argus_review_help(self):
        res = self.run_tool("argus_review.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Argus tape review battery", res.stdout)

        res_none = self.run_tool("argus_review.py")
        self.assertEqual(res_none.returncode, 0)

    def test_python_tape_readers_share_the_closed_event_vocabulary(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_longi
        import argus_review

        for verb in ("coverroute", "lifeveto"):
            line = f"ARGEVT Joe Rogan {verb}"
            self.assertEqual(argus_review.EVT.match(line).group(2), verb)
            self.assertEqual(argus_longi.EVT.match(line).group(2), verb)

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

    def test_navgen_edict_budget_names_slack_and_blocks_overflow(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from argus_nav_budget import assess_edict_budget

        safe = assess_edict_budget(200, 88, 120)
        self.assertEqual(safe.status, "ok")
        self.assertEqual(safe.slack, 243)
        self.assertTrue(safe.can_register)
        self.assertIn("waypoints 200", safe.line())
        self.assertIn("live bsp entities 88 of 120", safe.line())
        self.assertIn("world and client slots 9", safe.line())
        self.assertIn("runtime reserve 60 for four bots", safe.line())
        self.assertIn("slack 243", safe.line())

        tight = assess_edict_budget(260, 252, 300)
        self.assertEqual(tight.status, "tight")
        self.assertEqual(tight.slack, 19)
        self.assertTrue(tight.can_register)

        overflow = assess_edict_budget(260, 272, 300)
        self.assertEqual(overflow.status, "over-budget")
        self.assertEqual(overflow.slack, -1)
        self.assertFalse(overflow.can_register)

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
                     classname="func_door", angle="0", collision_gap=False,
                     landing_step=False, extra_entities=0, extra_items=0):
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
            + ''.join(
                '{\n"classname" "info_player_deathmatch"\n'
                '"origin" "0 0 24"\n}\n'
                for _ in range(extra_entities)
            )
            + ''.join(
                '{\n"classname" "weapon_rocketlauncher"\n'
                '"origin" "128 0 24"\n}\n'
                for _ in range(extra_items)
            )
        ).encode("ascii") + b"\0"
        models = struct.pack("<9f7i", -512.0, -512.0, -64.0,
                             512.0, 512.0, 512.0, 0.0, 0.0, 0.0,
                             0, 0, 0, 0, 0, 0, 0)
        models += struct.pack("<9f7i", 0.0, -32.0, 0.0,
                              64.0, 32.0, 64.0, 0.0, 0.0, 0.0,
                              0, 0, 0, 0, 0, 0, 0)
        planes = clipnodes = h0nodes = leaves = b""
        if collision_gap:
            # Infinite floor with a 64u gap at x 64..128. Both hull 1
            # and hull 0 use the same three-plane tree: above z=0 is
            # empty; below is solid except between the two x planes.
            plane_rows = [
                struct.pack("<ffffi", 0.0, 0.0, 1.0, 0.0, 2),
                struct.pack("<ffffi", 1.0, 0.0, 0.0, 64.0, 0),
                struct.pack("<ffffi", 1.0, 0.0, 0.0, 128.0, 0),
                # Hull 1 expands the z=0 floor to player-origin z=24.
                struct.pack("<ffffi", 0.0, 0.0, 1.0, 24.0, 2),
            ]
            if landing_step:
                # The far bank is 16u higher. Separate hull-0 and
                # hull-1 z planes make its actual standable origin 40,
                # not the linearly interpolated height of the link.
                plane_rows.extend((
                    struct.pack("<ffffi", 0.0, 0.0, 1.0, 16.0, 2),
                    struct.pack("<ffffi", 0.0, 0.0, 1.0, 40.0, 2),
                ))
                h0tree = ((4, -1, 1), (2, -2, 2),
                          (0, -1, 3), (1, -1, -2))
                h1tree = ((5, -1, 1), (2, -2, 2),
                          (3, -1, 3), (1, -1, -2))
            else:
                h0tree = ((0, -1, 1), (1, 2, -2), (2, -2, -1))
                h1tree = ((3, -1, 1), (1, 2, -2), (2, -2, -1))
            planes = b"".join(plane_rows)
            clipnodes = b"".join(struct.pack("<ihh", *row) for row in h1tree)
            h0nodes = b"".join(
                struct.pack("<i8h2H", p, c0, c1,
                            -512, -512, -64, 512, 512, 512, 0, 0)
                for p, c0, c1 in h0tree)
            leaves = b"".join(
                struct.pack("<2i6h2H4B", content, -1,
                            -512, -512, -64, 512, 512, 512,
                            0, 0, 0, 0, 0, 0)
                for content in (-1, -2))
        table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
        for idx, payload in ((0, ents), (1, planes), (5, h0nodes),
                             (9, clipnodes), (10, leaves), (14, models)):
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

    def reprofile(self, tmp, qc="nav.qc"):
        return self.run_tool("argus_navgen.py", str(tmp / "fixture.bsp"),
                             "fixture", str(tmp / qc), str(tmp / "out.png"),
                             "--reprofile-jumps")

    def reanalyze_tactics(self, tmp, qc="nav.qc"):
        return self.run_tool("argus_navgen.py", str(tmp / "fixture.bsp"),
                             "fixture", str(tmp / qc), str(tmp / "out.png"),
                             "--reanalyze-tactics")

    def test_argus_navgen_retype_doors_is_in_the_usage(self):
        res = self.run_tool("argus_navgen.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("--retype-doors", res.stdout)

    def test_argus_navgen_does_not_register_an_over_budget_graph(self):
        # There is no legal waypoint allowance after world/client/runtime
        # reservations. Fail before decimation, and never register the map.
        tmp = self.door_fixture(collision_gap=True, extra_entities=540)
        src = tmp / "src"
        src.mkdir()
        progs = src / "progs.src"
        dispatcher = src / "argus_nav_dispatch.qc"
        progs.write_text("progs.dat\nargus_nav_dispatch.qc\n")
        dispatcher.write_text("void() Argus_Nav_Spawn =\n{\n};\n")

        res = self.run_tool(
            "argus_navgen.py", str(tmp / "fixture.bsp"), "fixture",
            str(src / "argus_nav_fixture.qc"), str(tmp / "out.png"),
            "--register",
        )

        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("edict budget: status over-budget", res.stdout)
        self.assertIn("register: skipped because the graph is over-budget",
                      res.stdout)
        self.assertNotIn("argus_nav_fixture.qc\n", progs.read_text())
        self.assertNotIn('mapname == "fixture"', dispatcher.read_text())

    def test_argus_navgen_does_not_first_register_without_a_playability_verdict(self):
        tmp = self.door_fixture(collision_gap=True)
        src = tmp / "src"
        src.mkdir()
        progs = src / "progs.src"
        dispatcher = src / "argus_nav_dispatch.qc"
        progs.write_text("progs.dat\nargus_nav_dispatch.qc\n")
        dispatcher.write_text("void() Argus_Nav_Spawn =\n{\n};\n")

        res = self.run_tool(
            "argus_navgen.py", str(tmp / "fixture.bsp"), "fixture",
            str(src / "argus_nav_fixture.qc"), str(tmp / "out.png"),
            "--register",
        )

        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("playability gate: status experimental", res.stdout)
        self.assertIn("register: skipped because reach and mill evidence are incomplete",
                      res.stdout)
        self.assertNotIn("argus_nav_fixture.qc\n", progs.read_text())
        self.assertNotIn('mapname == "fixture"', dispatcher.read_text())

    def test_argus_navgen_removes_a_refused_jump_and_records_the_png_overlay(self):
        tmp = self.door_fixture(collision_gap=True)
        src = tmp / "src"
        src.mkdir()
        qc = src / "argus_nav_fixture.qc"
        png = tmp / "out.png"
        args = (
            "argus_navgen.py", str(tmp / "fixture.bsp"), "fixture",
            str(qc), str(png), "--no-dispatcher",
        )
        first = self.run_tool(*args)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        before = json.loads((Path(str(qc) + ".json")).read_text())
        self.assertTrue(before["jlinks"], "fixture must generate a jump")
        a, b = before["jlinks"][0]
        refused = {
            "kind": "jump",
            "from": before["nodes"][a],
            "to": before["nodes"][b],
        }
        (src / "argus_nav_fixture.probe.json").write_text(json.dumps({
            "failed": [],
            "typed_failed": [refused],
        }))

        second = self.run_tool(*args)

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("typed engine verdict: jump", second.stdout)
        after = json.loads((Path(str(qc) + ".json")).read_text())
        self.assertNotIn([a, b], after["jlinks"])
        self.assertIn(refused, after["probe_rejected"])
        if "debug plot skipped" in second.stdout:
            self.assertFalse(png.exists())
        else:
            self.assertTrue(png.is_file())
            self.assertGreater(png.stat().st_size, 0)

    def test_argus_navgen_first_registers_after_current_reach_and_mill_evidence(self):
        tmp = self.door_fixture(
            collision_gap=True, extra_entities=1, extra_items=1,
        )
        src = tmp / "src"
        src.mkdir()
        qc = src / "argus_nav_fixture.qc"
        png = tmp / "out.png"
        args = (
            "argus_navgen.py", str(tmp / "fixture.bsp"), "fixture",
            str(qc), str(png), "--no-dispatcher",
        )
        first = self.run_tool(*args)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        graph_path = Path(str(qc) + ".json")
        digest = hashlib.md5(
            graph_path.read_bytes(), usedforsecurity=False,
        ).hexdigest()
        (src / "argus_nav_fixture.probe.json").write_text(json.dumps({
            "failed": [],
            "verification": {
                "graph_md5": digest,
                "deathmatch": {
                    "walk": {
                        "swept": 1, "passed": 1, "failed": 0,
                        "teleport_failures": 0,
                    },
                    "jump": {
                        "swept": 1, "passed": 1, "failed": 0,
                        "teleport_failures": 0,
                    },
                },
            },
        }))
        progs = src / "progs.src"
        dispatcher = src / "argus_nav_dispatch.qc"
        progs.write_text("progs.dat\nargus_nav_dispatch.qc\n")
        dispatcher.write_text("void() Argus_Nav_Spawn =\n{\n};\n// mapname == \"fixture\"\n")

        registered = self.run_tool(*args, "--register")

        self.assertEqual(
            registered.returncode, 0, registered.stdout + registered.stderr,
        )
        self.assertIn("playability gate: status playable", registered.stdout)
        self.assertIn("argus_nav_fixture.qc\n", progs.read_text())
        self.assertIn('mapname == "fixture"', dispatcher.read_text())

    def test_argus_navgen_reprofile_jumps_is_in_the_usage(self):
        res = self.run_tool("argus_navgen.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("--reprofile-jumps", res.stdout)

    def test_argus_navgen_reanalyze_tactics_is_in_the_usage(self):
        res = self.run_tool("argus_navgen.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("--reanalyze-tactics", res.stdout)

    def test_argus_navgen_reanalyze_tactics_preserves_topology(self):
        tmp = self.door_fixture(collision_gap=True)
        before = json.loads((tmp / "nav.qc.json").read_text())
        res = self.reanalyze_tactics(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("topology untouched", res.stdout)
        after = json.loads((tmp / "nav.qc.json").read_text())
        self.assertEqual(after["exposure"], [5] * 6)
        self.assertEqual(after["cover_targets"], [[-1, -1]] * 6)
        self.assertEqual({k: v for k, v in after.items()
                          if k not in ("exposure", "cover_targets")}, before)
        qc = (tmp / "nav.qc").read_text(encoding="ascii")
        self.assertEqual(qc.count("Argus_NavTactics ("), 6)
        self.assertIn("Argus_NavTactics (n0, 5, world, world);", qc)

    def test_argus_navgen_reprofile_jumps_needs_a_shipped_graph(self):
        tmp = self.door_fixture()
        res = self.reprofile(tmp, qc="absent.qc")
        self.assertEqual(res.returncode, 1)
        self.assertIn("have to exist already", res.stderr)

    def test_argus_navgen_reprofile_jumps_refuses_a_mismatched_graph(self):
        tmp = self.door_fixture(jsonnodes=self.DOOR_FIXTURE_NODES[:5])
        before = (tmp / "nav.qc").read_bytes()
        res = self.reprofile(tmp)
        self.assertEqual(res.returncode, 1)
        self.assertIn("not the same graph", res.stderr)
        self.assertEqual((tmp / "nav.qc").read_bytes(), before)

    def test_argus_navgen_reprofile_jumps_preserves_topology(self):
        # A vertical auto-hop has no horizontal runway to query, so the
        # fixture only needs the entity/model lumps used by the door tests.
        # That keeps this CI-owned and independent of licensed map BSPs.
        nodes = [list(p) for p in self.DOOR_FIXTURE_NODES]
        nodes[0] = [0.0, 0.0, 24.0]
        nodes[1] = [0.0, 0.0, 64.0]
        tmp = self.door_fixture(nodes=nodes)
        before = json.loads((tmp / "nav.qc.json").read_text())
        res = self.reprofile(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1 direct/fallback link(s); topology untouched",
                      res.stdout)

        qc = (tmp / "nav.qc").read_text(encoding="ascii")
        self.assertIn("Argus_NavLinkJump (n1, n0, 0);", qc)
        after = json.loads((tmp / "nav.qc.json").read_text())
        self.assertEqual(after["jumpapproach"], [[1, 0, 0.0, 0.0, 0.0]])
        self.assertEqual({k: v for k, v in after.items()
                          if k != "jumpapproach"}, before)

    def test_argus_navgen_reprofile_jumps_profiles_the_physical_gap(self):
        nodes = [list(p) for p in self.DOOR_FIXTURE_NODES]
        # The typed link is n1 -> n0. Its waypoints are 128u apart, but
        # the physical void in the fixture is only x 64..128.
        nodes[1] = [32.0, 0.0, 24.0]
        nodes[0] = [160.0, 0.0, 24.0]
        tmp = self.door_fixture(nodes=nodes, collision_gap=True)
        res = self.reprofile(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("1 staged gap(s), 0 direct/fallback link(s)",
                      res.stdout)

        row = json.loads((tmp / "nav.qc.json").read_text())["jumpapproach"][0]
        self.assertEqual(row[:2], [1, 0])
        self.assertGreater(row[2], 0)
        self.assertLessEqual(row[2], 280)
        self.assertGreaterEqual(row[4], 2)
        margins = []
        for speed in range(int(row[2]) - 5, int(row[2]) + 16):
            t = 112.0 / speed
            margins.append(270.0 * t - 400.0 * t * t)
        self.assertAlmostEqual(row[4], min(margins), places=1)
        qc = (tmp / "nav.qc").read_text(encoding="ascii")
        self.assertIn(f"Argus_NavLinkJump (n1, n0, {row[2]:.0f});", qc)

    def test_argus_navgen_reprofile_uses_the_standable_landing_height(self):
        nodes = [list(p) for p in self.DOOR_FIXTURE_NODES]
        nodes[1] = [32.0, 0.0, 24.0]
        nodes[0] = [160.0, 0.0, 40.0]
        tmp = self.door_fixture(nodes=nodes, collision_gap=True,
                                landing_step=True)
        res = self.reprofile(tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        row = json.loads((tmp / "nav.qc.json").read_text())["jumpapproach"][0]
        self.assertGreater(row[2], 0)

        # Runtime launches 32u before the player hull loses support,
        # at x=32/z=24, and first regains support at x=144/z=40. The
        # stored margin is
        # the worst of the complete accepted speed window against
        # those physical origins, not the coarse link's interpolated z.
        margins = []
        for speed in range(int(row[2]) - 5, int(row[2]) + 16):
            t = 112.0 / speed
            margins.append(24.0 + 270.0 * t - 400.0 * t * t - 40.0)
        self.assertAlmostEqual(row[4], min(margins), places=1)

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

    def test_humanness_reader_uses_the_rust_role_rule(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_humanness

        with tempfile.TemporaryDirectory() as td:
            tape = Path(td) / "roles.log"
            lines = ["ARGUS init on dm4\n", "ARGEVT Reap spawned\n"]
            for i in range(20):
                lines.extend(
                    (
                        f"ARGLOG Reap t {i}.0 pos '{i * 64} 0 24' spd 64 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                        f"ARGLOG Shane t {i}.0 pos '0 {i * 64} 24' spd 64 yaw 90 mode 0 st 0 gl 0 hp 100 frg 0\n",
                        f"ARGLOG labprobe t {i}.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                    )
                )
            tape.write_text("".join(lines), encoding="utf-8")
            parsed = argus_humanness.read_tape(tape)
            self.assertEqual(parsed["map"], "dm4")
            self.assertEqual(set(parsed["bots"]), {"Reap"})
            self.assertEqual(set(parsed["humans"]), {"Shane"})

            # A tail slice without spawn evidence cannot label every track human.
            tape.write_text("".join(line for line in lines if "ARGEVT" not in line), encoding="utf-8")
            parsed = argus_humanness.read_tape(tape)
            self.assertEqual(parsed["humans"], {})
            self.assertEqual(parsed["bots"], {})

    def test_humanness_reader_selects_one_dominant_map_segment(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_humanness

        with tempfile.TemporaryDirectory() as td:
            tape = Path(td) / "two_maps.log"
            lines = ["ARGUS init on dm4\n", "ARGEVT OldBot spawned\n"]
            for i in range(20):
                lines.append(
                    f"ARGLOG OldBot t {i}.0 pos '{i * 64} 0 24' spd 64 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n"
                )
            lines.extend(("ARGUS init on dm2\n", "ARGEVT Reap spawned\n"))
            for i in range(40):
                lines.extend(
                    (
                        f"ARGLOG Reap t {i}.0 pos '{i * 64} 0 24' spd 64 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                        f"ARGLOG Shane t {i}.0 pos '0 {i * 64} 24' spd 64 yaw 90 mode 0 st 0 gl 0 hp 100 frg 0\n",
                    )
                )
            tape.write_text("".join(lines), encoding="utf-8")

            parsed = argus_humanness.read_tape(tape)
            self.assertEqual(parsed["map"], "dm2")
            self.assertEqual(parsed["segments"], 2)
            self.assertEqual(parsed["ignored_segments"], 1)
            self.assertEqual(set(parsed["bots"]), {"Reap"})
            self.assertEqual(set(parsed["humans"]), {"Shane"})
            self.assertNotIn("OldBot", parsed["bots"])

    def test_humanness_profile_reports_signed_feature_gaps(self):
        """The distance is unsigned; --profile has to say which way."""
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_humanness

        def tape(path, bot_step, human_step):
            lines = ["ARGUS init on dm4\n", "ARGEVT Reap spawned\n"]
            for i in range(80):
                lines.extend(
                    (
                        f"ARGLOG Reap t {i * 0.5} pos '{i * bot_step} 0 24' "
                        f"spd {bot_step * 2} yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                        f"ARGLOG Shane t {i * 0.5} pos '0 {i * human_step} 24' "
                        f"spd {human_step * 2} yaw 90 mode 0 st 0 gl 0 hp 100 frg 0\n",
                    )
                )
            path.write_text("".join(lines), encoding="utf-8")
            return argus_humanness.read_tape(path)

        with tempfile.TemporaryDirectory() as td:
            # The bot travels twice as far per sample as the reference human.
            parsed = tape(Path(td) / "signed.log", 160, 80)
            reference, counts = argus_humanness.build_reference([parsed])
            features, bot_counts = argus_humanness.collect_bot_features([parsed])
            rows = argus_humanness.profile_rows(features, bot_counts, reference, counts)
            by_feature = {row["feature"]: row for row in rows}
            speed = by_feature["speed_median"]
            self.assertEqual(speed["map"], "dm4")
            self.assertEqual(speed["bot_tracks"], 1)
            self.assertEqual(speed["human_tracks"], 1)
            self.assertGreater(speed["delta"], 0)
            self.assertGreater(speed["delta_scaled"], 0)
            self.assertAlmostEqual(
                speed["delta"], speed["bot_median"] - speed["human_median"], places=6
            )
            # Every scored feature appears exactly once per map.
            self.assertEqual(
                sorted(by_feature), sorted(argus_humanness.FEATURES)
            )

            # Reverse the roles and the sign has to follow.
            parsed = tape(Path(td) / "signed2.log", 60, 150)
            reference, counts = argus_humanness.build_reference([parsed])
            features, bot_counts = argus_humanness.collect_bot_features([parsed])
            rows = argus_humanness.profile_rows(features, bot_counts, reference, counts)
            speed = next(row for row in rows if row["feature"] == "speed_median")
            self.assertLess(speed["delta"], 0)
            self.assertLess(speed["delta_scaled"], 0)

    def test_gait_audit_separates_chosen_pauses_from_wedges(self):
        """A freeze belongs to the gait only when a marker precedes it."""
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_gait

        def tape(path, marker_at):
            lines = ["ARGUS init on dm4\n", "ARGEVT Reap spawned\n"]
            for i in range(60):
                t = i * 0.5
                # Still from t=10 to t=20, on the spot, losing health.
                if 10.0 <= t <= 20.0:
                    speed, hp = 0, 100 - (t - 10.0) * 4
                else:
                    speed, hp = 320, 100
                if marker_at is not None and abs(t - marker_at) < 0.01:
                    lines.append("ARGUS Reap hesitate settle\n")
                lines.append(
                    f"ARGLOG Reap t {t} pos '0 0 24' spd {speed} yaw 0 "
                    f"mode 2 st 0 gl 0 hp {hp:.0f} frg 0\n"
                )
            path.write_text("".join(lines), encoding="utf-8")
            return path

        with tempfile.TemporaryDirectory() as td:
            # No marker: the stationary window is somebody else's defect.
            report = argus_gait.audit(tape(Path(td) / "wedge.log", None), 8.0, 4.0)
            self.assertEqual(report["hesitations"], 0)
            self.assertEqual(report["freezes"], 1)
            self.assertEqual(report["findings"][0]["verdict"], "pre-existing")
            self.assertEqual(report["failures"], 0)

            # Marker just before, health lost inside: that is the gait's.
            report = argus_gait.audit(tape(Path(td) / "chosen.log", 9.5), 8.0, 4.0)
            self.assertEqual(report["hesitations"], 1)
            self.assertEqual(report["causes"], {"settle": 1})
            self.assertEqual(report["findings"][0]["verdict"], "FAIL")
            self.assertGreater(report["findings"][0]["hp_lost"], 0)
            self.assertEqual(report["failures"], 1)

            # Same marker, far enough ahead that it explains nothing.
            report = argus_gait.audit(tape(Path(td) / "stale.log", 2.0), 8.0, 4.0)
            self.assertEqual(report["findings"][0]["verdict"], "pre-existing")
            self.assertEqual(report["failures"], 0)

    def test_voidprobe_separates_lethal_floor_from_lethal_void(self):
        """The guard's two hazard verdicts are different questions."""
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_voidprobe

        # A synthetic world: contents are chosen by height alone, which is
        # all the classifier contract needs here.
        def fake(layout):
            return lambda x, y, z: layout(z)

        with tempfile.TemporaryDirectory() as td:
            nav = Path(td) / "nav.json"
            nav.write_text(json.dumps([[0, 0, 0]]), encoding="utf-8")
            real = argus_voidprobe.classifier
            try:
                # A lava pool: surface just below the feet, stone at its
                # bottom. The guard finds that stone and reads the contents
                # just above it, which is the lethal verdict.
                argus_voidprobe.classifier = lambda _p: fake(
                    lambda z: -2 if z <= -28 else (-5 if z <= -2 else -1)
                )
                verdicts, under, depths = argus_voidprobe.survey("x", nav, 48)
                self.assertEqual(verdicts["probes"], 8)
                self.assertEqual(verdicts["lethal floor"], 8)
                self.assertEqual(verdicts["void"], 0)
                self.assertEqual(depths, [])

                # No floor in the drop window, lava far below: the void case
                # that was measured and refused.
                argus_voidprobe.classifier = lambda _p: fake(
                    lambda z: -5 if z <= -400 else -1
                )
                verdicts, under, depths = argus_voidprobe.survey("x", nav, 48)
                self.assertEqual(verdicts["void"], 8)
                self.assertEqual(verdicts["lethal floor"], 0)
                self.assertEqual(under["lava"], 8)
                self.assertTrue(all(d >= 400 for d in depths), depths)

                # Plain floor: neither verdict.
                argus_voidprobe.classifier = lambda _p: fake(
                    lambda z: -2 if z <= -16 else -1
                )
                verdicts, under, depths = argus_voidprobe.survey("x", nav, 48)
                self.assertEqual(verdicts["solid floor"], 8)
                self.assertEqual(verdicts["lethal floor"], 0)
                self.assertEqual(verdicts["void"], 0)
            finally:
                argus_voidprobe.classifier = real

    def test_voidprobe_clearance_matches_navgens_seat_shift_bar(self):
        """navgen shifts a seat with walls inside 24u; this audits for them."""
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_voidprobe

        # Contents by x alone: a wall face at x >= 24, open elsewhere.
        wall_east = lambda x, y, z: -2 if x >= 24 else -1
        self.assertEqual(argus_voidprobe.clear_cardinals(wall_east, 0, 0, 0), 3)
        # Open everywhere: the pass skips these.
        self.assertEqual(
            argus_voidprobe.clear_cardinals(lambda x, y, z: -1, 0, 0, 0), 4
        )
        # Boxed in on all four.
        self.assertEqual(
            argus_voidprobe.clear_cardinals(lambda x, y, z: -2, 0, 0, 0), 0
        )

        with tempfile.TemporaryDirectory() as td:
            nav = Path(td) / "nav.json"
            nav.write_text(json.dumps([[0, 0, 0], [512, 0, 0]]), encoding="utf-8")
            real = argus_voidprobe.classifier
            try:
                argus_voidprobe.classifier = lambda _p: wall_east
                counts, tight = argus_voidprobe.clearance("x", nav)
                # The seat at the origin has the wall; the far one is inside it.
                self.assertEqual(sum(counts.values()), 2)
                self.assertEqual(len(tight), 2)
                argus_voidprobe.classifier = lambda _p: (lambda x, y, z: -1)
                counts, tight = argus_voidprobe.clearance("x", nav)
                self.assertEqual(counts[4], 2)
                self.assertEqual(tight, [])
            finally:
                argus_voidprobe.classifier = real

    def test_voidprobe_reads_the_shipped_dm4_graph(self):
        """Needs the machine-local BSP; skips where it is absent."""
        bsp = ROOT / "maps_local" / "dm4.bsp"
        nav = ROOT / "src" / "argus_nav_dm4.qc.json"
        if not bsp.is_file() or not nav.is_file():
            self.skipTest("needs maps_local/dm4.bsp and the dm4 nav sidecar")
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_voidprobe

        verdicts, under, depths = argus_voidprobe.survey(bsp, nav, 48)
        self.assertEqual(verdicts["probes"], verdicts["void"]
                         + verdicts["solid floor"] + verdicts["lethal floor"])
        # Waypoints are seated off hazards by construction, so no probe
        # direction from one finds lava underfoot. If this ever fires, the
        # cautious gait's trigger has changed meaning.
        self.assertEqual(verdicts["lethal floor"], 0)
        # Every void dm4 vetoes bottoms out in lava.
        self.assertGreater(verdicts["void"], 0)
        self.assertEqual(under.get("lava"), verdicts["void"])

    def test_gait_audit_exit_status_gates(self):
        res = self.run_tool("argus_gait.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("hesitation", res.stdout)
        res = self.run_tool("argus_gait.py", "no_such_tape_*.log")
        self.assertEqual(res.returncode, 2)

    def test_humanness_uses_the_real_mixed_session_dominant_segment(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_humanness

        tape = ROOT / "runs" / "shane_e1m3_2026-09-05_v409.log"
        if not tape.is_file():
            self.skipTest("mixed e1m2/e1m3 session not present")
        parsed = argus_humanness.read_tape(tape)
        self.assertEqual(parsed["map"], "e1m2")
        self.assertEqual(parsed["segments"], 2)
        self.assertEqual(parsed["ignored_segments"], 1)
        self.assertEqual(len(parsed["humans"]), 1)
        self.assertIsNotNone(
            argus_humanness.track_metrics(next(iter(parsed["humans"].values())))
        )

    def test_humanness_distance_is_zero_for_equal_distributions(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import argus_humanness

        self.assertAlmostEqual(
            argus_humanness.normalized_wasserstein([1, 2, 4], [1, 2, 4]),
            0.0,
        )
        self.assertGreater(
            argus_humanness.normalized_wasserstein([10, 20, 40], [1, 2, 4]),
            1.0,
        )

    def test_humanness_cli_reports_map_matched_movement_distance(self):
        def tape(path, human_scale, bot_scale):
            lines = ["ARGUS init on dm4\n", "ARGEVT Reap spawned\n"]
            for i in range(40):
                hx = i * human_scale
                bx = i * bot_scale
                lines.extend(
                    (
                        f"ARGLOG Shane t {i}.0 pos '{hx} {i % 4 * 64} 24' spd {human_scale} yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                        f"ARGLOG Reap t {i}.0 pos '{bx} {i % 4 * 64} 24' spd {bot_scale} yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                    )
                )
            path.write_text("".join(lines), encoding="utf-8")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            references = []
            for index, scale in enumerate((58, 64, 70)):
                path = root / f"human_{index}.log"
                tape(path, scale, scale)
                references.append(path)
            candidate = root / "candidate.log"
            tape(candidate, 64, 64)
            res = self.run_tool(
                "argus_humanness.py",
                "--reference",
                str(root / "human_*.log"),
                str(candidate),
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            lines = res.stdout.splitlines()
            row = dict(zip(lines[0].split("\t"), lines[1].split("\t")))
            self.assertEqual(row["map"], "dm4")
            self.assertEqual(row["bot_tracks"], "1")
            self.assertEqual(row["human_reference_tracks"], "3")
            self.assertLess(float(row["distance"]), 1.0)

    def test_humanness_scores_a_real_tape_against_the_archive(self):
        tape = ROOT / "runs" / "ab_dm4_B3.log"
        if not tape.is_file():
            self.skipTest("dm4 candidate tape not present")
        res = self.run_tool("argus_humanness.py", str(tape))
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        row = dict(zip(lines[0].split("\t"), lines[1].split("\t")))
        self.assertEqual(row["map"], "dm4")
        self.assertEqual(row["bot_tracks"], "3")
        self.assertGreaterEqual(int(row["human_reference_tracks"]), 3)
        self.assertGreater(float(row["distance"]), 0.0)
        for feature in (
            "speed_median",
            "pause_fraction",
            "direction_changes_pm",
            "cells_pm",
            "gyration",
            "local_dwell_fraction",
        ):
            self.assertTrue(math.isfinite(float(row[feature])), feature)

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

    def test_tick_estimator_tolerates_played_rate_jitter(self):
        """Sampling jitter around the old cutoff does not change class."""
        with tempfile.TemporaryDirectory() as td:
            tape = Path(td) / "same_runner.log"
            t = 1.0
            lines = []
            # 13 long gaps among 100 gives 0.513, below the calibrated
            # 0.5145 legacy dedicated cluster but above the old cutoff.
            for i in range(101):
                lines.append(
                    f"ARGLOG Reap t {t:.1f} pos '0 0 24' spd 0 "
                    "yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n"
                )
                if i < 100:
                    t += 0.6 if i < 13 else 0.5
            tape.write_text("".join(lines))

            res = self.run_tool("argus_tick.py", str(tape))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("70 Hz", res.stdout)

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
            with out.open() as scorecard:
                rows = list(_csv.DictReader(scorecard, delimiter="\t"))
            self.assertEqual(len(rows), 1, rows)
            self.assertEqual(rows[0]["bot_kills_human"], "10")

    def test_argus_mcp_cli_subcommands(self):
        mcp_bin = find_argus_mcp_binary()
        if not mcp_bin:
            if os.environ.get("ARGUS_REQUIRE_SOURCE_MCP") == "1":
                self.fail("argus-mcp source binary not built")
            self.skipTest("argus-mcp source binary not built")

        for cmd in ("--help", "compile -h", "reach -h", "harvest -h",
                    "analyze -h", "nav -h", "benchmark -h", "within-ab -h", "tactic-suite -h"):
            args = cmd.split()
            res = subprocess.run([str(mcp_bin), *args], capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(res.returncode, 0, f"failed on {cmd}: {res.stderr}")

    def test_argus_mcp_compare_rejects_an_empty_candidate_list(self):
        mcp_bin = find_argus_mcp_binary()
        if not mcp_bin:
            if os.environ.get("ARGUS_REQUIRE_SOURCE_MCP") == "1":
                self.fail("argus-mcp source binary not built")
            self.skipTest("argus-mcp source binary not built")

        res = subprocess.run(
            [str(mcp_bin), "compare", ",", "control"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("candidate list must not be empty", res.stderr)
        self.assertNotIn("panicked", res.stderr)

    def test_installed_argus_mcp_starts(self):
        mcp_bin = find_argus_mcp_binary(installed=True)
        if not mcp_bin:
            self.skipTest("argus-mcp stable install not present")

        res = subprocess.run([str(mcp_bin), "--help"], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, res.stderr)

    def _links_repo(self, root, files):
        subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True, check=True)
        for name, text in files.items():
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True, check=True)

    def test_argus_ci_links_passes_on_tracked_documentation(self):
        result = self.run_tool("argus_ci.py", "links")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("links: ok", result.stdout)

    def test_argus_ci_links_accepts_heading_html_and_reference_anchors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._links_repo(root, {
                "README.md": '[good](docs/guide.md#first-heading)\n'
                             '[legacy](docs/guide.md#v3-92)\n'
                             '[named](docs/guide.md#named)\n'
                             '[duplicate][ref]\n\n[ref]: docs/guide.md#first-heading-1 "title"\n',
                "docs/guide.md": '# First `heading`\n<a id="v3-92"></a>\n'
                                 '<a name="named"></a>\n# First heading\n',
            })
            result = self.run_tool("argus_ci.py", "links", "--root", td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_argus_ci_links_rejects_missing_path_and_fragment(self):
        for destination, message in (("missing.md", "missing path"),
                                     ("guide.md#missing", "missing fragment")):
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self._links_repo(root, {"README.md": f"[bad]({destination})\n", "guide.md": "# Present\n"})
                result = self.run_tool("argus_ci.py", "links", "--root", td)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(message, result.stdout)
                self.assertIn("README.md:1", result.stdout)

    def test_argus_ci_links_skips_archives_untracked_examples_and_external_urls(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._links_repo(root, {
                "README.md": '[web](https://example.invalid/no-document#absent)\n'
                             '[mail](mailto:nobody@example.invalid)\n'
                             '`[code](missing.md)`\n```md\n[example](missing.md)\n```\n'
                             '<!-- [comment](missing.md) -->\n',
                "backups/old.md": "[old](missing.md)",
                "docs/plans/old.md": "[old](missing.md)",
            })
            (root/"untracked.md").write_text("[bad](missing.md)")
            result = self.run_tool("argus_ci.py", "links", "--root", td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_argus_ci_links_handles_encoded_spaces_parentheses_and_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._links_repo(root, {
                "README.md": '[encoded](guide%20one.md#caf%C3%A9)\n'
                             '[angle](<guide one.md#caf\u00e9>)\n'
                             '![image](image(1).png)\n'
                             '[nested](docs/nested.md)\n',
                "guide one.md": "# Caf\u00e9\n",
                "image(1).png": "placeholder",
                "docs/nested.md": "[home](../README.md)\n",
            })
            result = self.run_tool("argus_ci.py", "links", "--root", td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_argus_ci_links_reads_html_src_srcset_and_href(self):
        page = ('<picture>\n<source srcset="{dark} 1x, art/dark@2x.svg 2x">\n'
                '<img src="{img}" alt="Argus">\n</picture>\n'
                '<a href="{href}">guide</a>\n')
        good = dict(dark="art/dark.svg", img="art/light.svg", href="guide.md#present")
        files = {"art/dark.svg": "<svg/>", "art/dark@2x.svg": "<svg/>",
                 "art/light.svg": "<svg/>", "guide.md": "# Present\n"}
        with tempfile.TemporaryDirectory() as td:
            self._links_repo(Path(td), {"README.md": page.format(**good), **files})
            result = self.run_tool("argus_ci.py", "links", "--root", td)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for key, bad, message in (("dark", "art/missing.svg", "missing path"),
                                  ("img", "art/missing.svg", "missing path"),
                                  ("href", "guide.md#absent", "missing fragment")):
            with self.subTest(attribute=key), tempfile.TemporaryDirectory() as td:
                self._links_repo(Path(td), {"README.md": page.format(**{**good, key: bad}), **files})
                result = self.run_tool("argus_ci.py", "links", "--root", td)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(message, result.stdout)

    def test_argus_ci_links_does_not_accept_code_block_headings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._links_repo(root, {"README.md": "[bad](guide.md#sample)\n",
                                   "guide.md": "```md\n# Sample\n```\n"})
            result = self.run_tool("argus_ci.py", "links", "--root", td)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("missing fragment", result.stdout)

    def test_argus_ci_all_includes_the_link_gate(self):
        # Match the invariant job: shallow PR checkouts have no origin/main.
        with tempfile.TemporaryDirectory() as td:
            changed = self._changed_file(td, [])
            result = self.run_tool("argus_ci.py", "all", "--changed-files", changed)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("links: ok", result.stdout)

    def test_argus_ci_help(self):
        res = self.run_tool("argus_ci.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Argus repo invariant battery", res.stdout)

    def test_ci_uses_an_explicit_ubuntu_runner(self):
        workflows = [
            ROOT / ".github" / "workflows" / "fast.yml",
            ROOT / ".github" / "workflows" / "compile.yml",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
        self.assertNotIn("runs-on: ubuntu-latest", text)
        self.assertEqual(text.count("runs-on: ubuntu-24.04"), 4)

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

    def _raw_index_blob(self, root, path, content):
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            input=content, capture_output=True, cwd=str(root), check=True,
        ).stdout.decode().strip()
        subprocess.run(
            ["git", "update-index", "--add", "--cacheinfo",
             "100644", blob, path],
            capture_output=True, cwd=str(root), check=True,
        )

    def _eol_repo(self, root):
        subprocess.run(
            ["git", "init", "-q"], capture_output=True,
            cwd=str(root), check=True,
        )
        (root / ".gitattributes").write_text(
            "* text=auto eol=lf\n*.bat text eol=crlf\n"
            "*.cmd text eol=crlf\n",
            encoding="utf-8", newline="\n",
        )
        subprocess.run(
            ["git", "add", ".gitattributes"], capture_output=True,
            cwd=str(root), check=True,
        )

    def test_argus_ci_eol_passes_on_the_tree(self):
        res = self.run_tool("argus_ci.py", "eol")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("eol: ok", res.stdout)

    def test_argus_ci_eol_rejects_an_api_style_crlf_blob(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._eol_repo(root)
            self._raw_index_blob(root, "bad.txt", b"one\r\ntwo\r\n")

            res = self.run_tool("argus_ci.py", "eol", "--root", td)

            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn("bad.txt", res.stdout)
            self.assertIn("stored with CRLF in Git", res.stdout)

    def test_argus_ci_eol_keeps_windows_script_crlf_policy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._eol_repo(root)
            self._raw_index_blob(root, "keep.cmd", b"@echo off\r\n")

            res = self.run_tool("argus_ci.py", "eol", "--root", td)

            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("eol: ok", res.stdout)

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
    Argus_NavLinkJump (n0, n1, 220);
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
