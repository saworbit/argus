#!/usr/bin/env python3
"""Tests for tools/lab_mapgen.py: requests, brushes, entities, budgets, WAD, scenarios.

The unit cases need nothing outside this checkout. The integration case
compiles a real BSP with the pinned ericw-tools and runs navgen on it; it
self-skips when the tools are not installed (python tools/lab_mapgen.py tools
--install). With ARGUS_LAB_SMOKE_ENGINE=1 and a configured lab (ARGUS_ENGINE,
ARGUS_BASEDIR and a built argus-mcp) it also loads the map in the engine.
"""
import copy
from contextlib import redirect_stdout
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import lab_mapgen as mg  # noqa: E402 - tools path set just above
import argus_lab  # noqa: E402
from argus_bsp import Bsp  # noqa: E402

PLANE = re.compile(r"^\( (-?\d+) (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) (-?\d+) \) "
                   r"\( (-?\d+) (-?\d+) (-?\d+) \) (\S+) 0 0 0 1 1$")


def ring_request():
    return json.loads((ROOT / "labmaps" / "lab_voidcorner" / "request.json").read_text(encoding="utf-8"))


def small_request(**extra):
    request = {
        "name": "lab_unit",
        "intent": "unit test map",
        "regions": [
            {"name": "west", "kind": "room", "min": [0, 0], "size": [256, 256], "floor_z": 0,
             "connections": [{"to": "stair", "type": "stairs"}]},
            {"name": "stair", "kind": "stairs", "min": [256, 64], "size": [128, 128], "floor_z": 0,
             "to_z": 64, "axis": "+x"},
            {"name": "east", "kind": "room", "min": [384, 0], "size": [256, 256], "floor_z": 64,
             "connections": [{"to": "stair", "type": "stairs"}]},
        ],
        "entities": [
            {"classname": "info_player_deathmatch", "region": "west", "at": [0.25, 0.5], "angle": 0},
            {"classname": "info_player_deathmatch", "region": "east", "at": "centre", "angle": 180},
            {"classname": "item_health", "region": "east", "at": [0.5, 0.25]},
            {"classname": "weapon_supershotgun", "region": "stair", "at": [0.9, 0.5]},
        ],
    }
    request.update(extra)
    return request


def jump_request(gap, rise):
    """Two walkways facing across `gap`, the east one `rise` higher, joined by a jump."""
    return {
        "name": "lab_unitjump",
        "intent": "unit test jump",
        "regions": [
            {"name": "west", "kind": "walkway", "min": [0, 0], "size": [256, 96], "floor_z": 0,
             "solid_below": True, "connections": [{"to": "east", "type": "jump"}]},
            {"name": "east", "kind": "walkway", "min": [256 + gap, 0], "size": [256, 96],
             "floor_z": rise, "solid_below": True},
        ],
        "entities": [
            {"classname": "info_player_deathmatch", "region": "west", "at": [0.25, 0.5], "angle": 0},
            {"classname": "info_player_deathmatch", "region": "east", "at": [0.75, 0.5], "angle": 180},
            {"classname": "item_health", "region": "east", "at": "centre"},
        ],
    }


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def parse_map(text):
    """Entities as (keys, brushes) with each brush a list of (p0, p1, p2, texture)."""
    entities = []
    depth = 0
    keys, brushes, brush = {}, [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line == "{":
            depth += 1
            if depth == 1:
                keys, brushes = {}, []
            else:
                brush = []
            continue
        if line == "}":
            if depth == 2:
                brushes.append(brush)
            else:
                entities.append((keys, brushes))
            depth -= 1
            continue
        if depth == 1:
            m = re.fullmatch(r'"([^"]+)" "([^"]*)"', line)
            assert m, f"bad key line {line!r}"
            keys[m.group(1)] = m.group(2)
        elif depth == 2:
            m = PLANE.fullmatch(line)
            assert m, f"bad plane line {line!r}"
            n = [int(v) for v in m.groups()[:9]]
            brush.append((tuple(n[0:3]), tuple(n[3:6]), tuple(n[6:9]), m.group(10)))
        else:
            raise AssertionError(f"text outside an entity: {line!r}")
    assert depth == 0
    return entities


class RequestTests(unittest.TestCase):
    def test_defaults_are_filled_and_key_order_does_not_change_the_identity(self):
        a = mg.normalise(small_request())
        shuffled = json.loads(json.dumps(small_request()), object_pairs_hook=lambda kv: dict(reversed(kv)))
        b = mg.normalise(shuffled)
        self.assertEqual(mg.source_sha256(a), mg.source_sha256(b))
        self.assertEqual(a["constraints"]["max_brushes"], 200)
        self.assertEqual(a["claim_tier"], "isolation")
        self.assertRegex(mg.scenario_id(a), r"^lab_unit-[0-9a-f]{10}$")

    def test_names_tiers_and_unknown_fields_are_refused(self):
        for bad in (small_request(name="dm4"), small_request(name="lab-x"), small_request(claim_tier="stock"),
                    small_request(colour="red")):
            with self.assertRaises(mg.RequestError):
                mg.normalise(bad)

    def test_region_and_entity_errors_name_the_field(self):
        req = small_request()
        req["entities"].append({"classname": "item_health", "region": "nowhere"})
        with self.assertRaisesRegex(mg.RequestError, "nowhere"):
            mg.normalise(req)
        req = small_request()
        req["entities"].append({"classname": "monster_ogre", "region": "west"})
        with self.assertRaisesRegex(mg.RequestError, "classname"):
            mg.normalise(req)
        req = small_request()
        req["regions"][0]["min"] = [3990, 0]
        with self.assertRaisesRegex(mg.RequestError, "protocol 15"):
            mg.normalise(req)


class GeometryTests(unittest.TestCase):
    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            req = mg.normalise(ring_request())
            _, first = mg.generate(req, Path(td) / "a")
            _, second = mg.generate(copy.deepcopy(req), Path(td) / "b")
            self.assertEqual((Path(td) / "a" / "lab_voidcorner.map").read_bytes(),
                             (Path(td) / "b" / "lab_voidcorner.map").read_bytes())
            self.assertEqual(first["map_sha256"], second["map_sha256"])
            self.assertEqual(first["wad_sha256"], second["wad_sha256"])

    def test_every_brush_is_a_closed_box_with_outward_planes(self):
        req = mg.normalise(small_request(constraints={"teleporters": 1}))
        req["regions"][0]["connections"].append({"to": "east", "type": "teleporter"})
        text = mg.map_text(req, mg.plan(req))
        entities = parse_map(text)
        brushes = [b for _, bs in entities for b in bs]
        self.assertGreater(len(brushes), 6)
        for brush in brushes:
            self.assertEqual(len(brush), 6)
            normals = []
            points = []
            for p0, p1, p2, _tex in brush:
                t1 = tuple(p0[i] - p1[i] for i in range(3))
                t2 = tuple(p2[i] - p1[i] for i in range(3))
                n = cross(t1, t2)
                self.assertEqual(sum(1 for v in n if v), 1, f"plane is not axial: {n}")
                normals.append(tuple(1 if v > 0 else -1 if v < 0 else 0 for v in n))
                points.append(p1)
            self.assertEqual(sorted(normals), sorted([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                                                      (0, 0, 1), (0, 0, -1)]))
            lo = [min(p[i] for p in points) for i in range(3)]
            hi = [max(p[i] for p in points) for i in range(3)]
            centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
            for n, p in zip(normals, points):
                dist = sum(n[i] * p[i] for i in range(3))
                self.assertLess(sum(n[i] * centre[i] for i in range(3)), dist, "centre is not behind a face")

    def test_stairs_climb_one_riser_at_a_time_and_reach_to_z(self):
        req = mg.normalise(small_request())
        stair = req["regions"][1]
        treads = mg.stair_steps(stair)
        self.assertEqual(len(treads), 4)
        tops = [t[4] for t in treads]
        self.assertEqual(tops, [16, 32, 48, 64])
        self.assertLess(treads[0][0], treads[-1][0], "+x stairs climb east")

    def test_adjacency_and_connections_follow_the_layout(self):
        req = mg.normalise(ring_request())
        adj = {(r["a"], r["b"]): r for r in mg.adjacency(req)}
        self.assertEqual(adj[("south", "east")]["relation"], "edge")
        self.assertEqual(adj[("south", "east")]["walk"], "walk")
        self.assertEqual(adj[("south", "east")]["length"], 64)
        bad = ring_request()
        bad["regions"][0]["floor_z"] = 64
        with self.assertRaisesRegex(mg.RequestError, "steps 64u"):
            mg.plan(mg.normalise(bad))
        drop = ring_request()
        drop["regions"][0]["floor_z"] = 64
        drop["regions"][0]["connections"] = [{"to": "east", "type": "drop"}, {"to": "west", "type": "drop"}]
        self.assertTrue(mg.plan(mg.normalise(drop))["connections"])

    def test_a_jump_no_running_jump_crosses_is_refused_before_compiling(self):
        # The plain hop takes off 32u short of the lip and lands once the
        # box is over the far edge: at 320 u/s, 200u level, 129u at 40 up.
        self.assertAlmostEqual(mg.jump_reach(0), 200.0, places=3)
        self.assertAlmostEqual(mg.jump_reach(40), 129.7, places=1)
        self.assertIsNone(mg.jump_reach(48), "nothing lands above the apex")
        # lab_jumpgap's 96u level gap is buildable both ways (#866)
        req = mg.normalise(json.loads(
            (ROOT / "labmaps" / "lab_jumpgap" / "request.json").read_text(encoding="utf-8")))
        jumps = [(c["gap"], c["dz"]) for c in mg.check_connections(req) if c["type"] == "jump"]
        self.assertEqual(jumps, [(96, 0), (96, 0)])
        self.assertTrue(mg.plan(mg.normalise(jump_request(160, 0)))["connections"])
        self.assertTrue(mg.plan(mg.normalise(jump_request(128, 40)))["connections"])
        # plan() runs before generate() writes the .map, so before any compile
        with self.assertRaisesRegex(mg.RequestError, r"no running jump crosses a 136u gap onto a "
                                    r"landing 40u up.*only up to 130u"):
            mg.plan(mg.normalise(jump_request(136, 40)))
        with self.assertRaisesRegex(mg.RequestError, "at most 160u apart"):
            mg.plan(mg.normalise(jump_request(168, 0)))

    def test_the_hull_occupant_stands_in_clear_air(self):
        req = mg.normalise(ring_request())
        ents = mg.build_entities(req)
        occ = [dict(e["keys"]) for e in ents if dict(e["keys"])["classname"] == "info_intermission"]
        self.assertEqual(len(occ), 1)
        x, y, z = (int(v) for v in occ[0]["origin"].split())
        for r in req["regions"]:
            if r["kind"] == "block":
                x0, y0, x1, y1 = mg.footprint(r)
                self.assertFalse(x0 - 48 < x < x1 + 48 and y0 - 48 < y < y1 + 48)
        self.assertEqual(z, 48)


class EntityTests(unittest.TestCase):
    def test_entities_are_placed_by_region_name(self):
        req = mg.normalise(small_request())
        ents = [dict(e["keys"]) for e in mg.build_entities(req)]
        spawns = [e for e in ents if e["classname"] == "info_player_deathmatch"]
        self.assertEqual(spawns[0]["origin"], "64 128 24")
        self.assertEqual(spawns[1]["origin"], "512 128 88")
        health = next(e for e in ents if e["classname"] == "item_health")
        self.assertEqual(health["origin"], "496 48 72", "health boxes are centred from their 0 0 0 corner")
        ssg = next(e for e in ents if e["classname"] == "weapon_supershotgun")
        self.assertEqual(ssg["origin"].split()[2], str(64 + 8), "the top tread carries the weapon")
        self.assertEqual(sum(1 for e in ents if e["classname"] == "info_player_start"), 1)

    def test_doors_and_teleporters_become_brush_entities(self):
        req = small_request(constraints={"teleporters": 1})
        req["regions"][0]["connections"].append({"to": "east", "type": "teleporter"})
        req["regions"].append({"name": "annex", "kind": "room", "min": [0, 256], "size": [256, 128],
                               "floor_z": 0, "connections": [{"to": "west", "type": "door"}]})
        ents = mg.build_entities(mg.normalise(req))
        classes = [dict(e["keys"])["classname"] for e in ents]
        self.assertIn("func_door", classes)
        self.assertIn("trigger_teleport", classes)
        tele = next(dict(e["keys"]) for e in ents if dict(e["keys"])["classname"] == "trigger_teleport")
        dest = next(dict(e["keys"]) for e in ents if dict(e["keys"])["classname"] == "info_teleport_destination")
        self.assertEqual(tele["target"], dest["targetname"])


class ConstraintTests(unittest.TestCase):
    def test_brush_budget(self):
        with self.assertRaisesRegex(mg.RequestError, "max_brushes"):
            mg.plan(mg.normalise(small_request(constraints={"max_brushes": 8})))

    def test_entity_budget(self):
        with self.assertRaisesRegex(mg.RequestError, "max_entities"):
            mg.plan(mg.normalise(small_request(constraints={"max_entities": 5})))
        with self.assertRaises(mg.RequestError):
            mg.normalise(small_request(constraints={"max_entities": 61}))

    def test_teleporter_budget(self):
        req = small_request()
        req["regions"][0]["connections"].append({"to": "east", "type": "teleporter"})
        with self.assertRaisesRegex(mg.RequestError, "teleporter"):
            mg.plan(mg.normalise(req))

    def test_liquids_and_sky(self):
        with self.assertRaisesRegex(mg.RequestError, "liquids"):
            mg.normalise(small_request(base={"liquid": "slime"}, constraints={"liquids": ["lava"]}))
        open_sky = mg.map_text(*(lambda r: (r, mg.plan(r)))(mg.normalise(small_request(constraints={"sky": True}))))
        closed = mg.map_text(*(lambda r: (r, mg.plan(r)))(mg.normalise(small_request())))
        self.assertIn(mg.TEX_SKY, open_sky)
        self.assertNotIn(mg.TEX_SKY, closed)

    def test_spawn_minimum_and_spawns_in_lava(self):
        req = small_request(constraints={"min_spawns": 3})
        with self.assertRaisesRegex(mg.RequestError, "min_spawns"):
            mg.plan(mg.normalise(req))
        req = small_request(constraints={"liquids": ["lava"]})
        req["regions"].append({"name": "pool", "kind": "pit", "min": [0, 256], "size": [128, 128],
                               "floor_z": -64, "liquid": "lava"})
        req["entities"].append({"classname": "info_player_deathmatch", "region": "pool"})
        with self.assertRaisesRegex(mg.RequestError, "lava"):
            mg.plan(mg.normalise(req))


class CoverageTests(unittest.TestCase):
    def test_a_floor_with_no_waypoint_is_uncovered_unless_marked_off_graph(self):
        req = mg.normalise(small_request())
        nodes = [[128, 128, 24], [512, 128, 88]]
        self.assertEqual(mg.coverage(req, nodes)["uncovered"], [])
        # a waypoint above the floor's seat height (a block top, a walkway over it) does not count
        cut = mg.coverage(req, [[128, 128, 24], [512, 128, 200]])
        self.assertEqual(cut["uncovered"], ["east"])
        self.assertFalse(cut["covered"])
        marked = small_request()
        marked["regions"][2]["off_graph"] = True
        exempt = mg.coverage(mg.normalise(marked), [[128, 128, 24]])
        self.assertTrue(exempt["covered"])
        self.assertEqual(exempt["exempt"], ["east"])
        # stairs are not checked, and off_graph is refused where nothing is checked
        self.assertEqual([r["name"] for r in exempt["regions"]], ["west", "east"])
        bad = small_request()
        bad["regions"][1]["off_graph"] = True
        with self.assertRaisesRegex(mg.RequestError, "off_graph"):
            mg.normalise(bad)

    def test_off_graph_false_keeps_the_scenario_id(self):
        plain = mg.normalise(small_request())
        said = small_request()
        said["regions"][0]["off_graph"] = False
        self.assertEqual(mg.scenario_id(plain), mg.scenario_id(mg.normalise(said)))

    def test_the_gate_would_have_refused_lab_drymix(self):
        # lab_drymix registered with its west run-off ledge off the graph, and
        # that pocket carried 58 per cent of its brink re-entries
        name = "lab_drymix"
        graph = ROOT / "src" / f"argus_nav_{name}.qc.json"
        if not graph.is_file():
            self.skipTest(f"no {graph.name}")
        req = mg.load_request(ROOT / "labmaps" / name / "request.json")
        nodes = json.loads(graph.read_text(encoding="utf-8"))["nodes"]
        result = mg.coverage(req, nodes)
        self.assertFalse(result["covered"])
        self.assertIn("ledge_s", result["uncovered"])
        voidcorner = mg.load_request(ROOT / "labmaps" / "lab_voidcorner" / "request.json")
        vgraph = ROOT / "src" / "argus_nav_lab_voidcorner.qc.json"
        self.assertTrue(mg.coverage(voidcorner, json.loads(vgraph.read_text(encoding="utf-8"))["nodes"])["covered"])


class WadTests(unittest.TestCase):
    def test_wad_holds_every_texture_the_map_names(self):
        data = mg.wad_bytes()
        self.assertEqual(data[:4], b"WAD2")
        count, table = struct.unpack_from("<ii", data, 4)
        names = set()
        for i in range(count):
            pos, disk, size, kind = struct.unpack_from("<iiib", data, table + 32 * i)
            self.assertEqual(kind, 0x44)
            self.assertEqual(disk, size)
            names.add(data[table + 32 * i + 16:table + 32 * i + 32].split(b"\0")[0].decode())
            width, height = struct.unpack_from("<II", data, pos + 16)
            self.assertEqual(size, 40 + width * height * 85 // 64)
        req = mg.normalise(ring_request())
        used = set(re.findall(r"\) (\S+) 0 0 0 1 1", mg.map_text(req, mg.plan(req))))
        self.assertTrue(used <= names, used - names)


class ScenarioTests(unittest.TestCase):
    def make_root(self, td):
        root = Path(td)
        (root / "tools").mkdir()
        (root / "runs").mkdir()
        (root / "docs").mkdir()
        (root / "docs" / "lab-scenarios.md").write_text("# Lab scenarios\n")
        (root / "tools" / "lab_instruments.json").write_text(json.dumps({"schema": 1}))
        req = mg.normalise(ring_request())
        (root / "labmaps" / "lab_voidcorner").mkdir(parents=True)
        (root / "labmaps" / "lab_voidcorner" / "request.json").write_text("{}")
        (root / "labmaps" / "lab_voidcorner" / "manifest.json").write_text("{}")
        manifest = {"map": "lab_voidcorner", "scenario_id": mg.scenario_id(req), "claim_tier": "isolation",
                    "intent": req["intent"], "claims": req["claims"],
                    "files": {"request": "labmaps/lab_voidcorner/request.json"},
                    "generator": {"source_sha256": mg.source_sha256(req)}}
        mg.register_scenario(root, manifest)
        for run, mapname in (("lab_tape", "lab_voidcorner"), ("stock_tape", "dm4")):
            (root / "runs" / f"{run}.log").write_text(f"SpawnServer: {mapname}\nARGUS init on {mapname}\n")
        return root

    def test_interrupted_registry_replace_preserves_the_previous_document(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            path = root / "tools" / "lab_instruments.json"
            before = path.read_bytes()
            files = set(path.parent.iterdir())
            manifest = {
                "map": "lab_second", "scenario_id": "lab_second-test", "claim_tier": "isolation",
                "intent": "Check a second scenario.", "claims": [],
                "files": {"request": "labmaps/lab_second/request.json"},
                "generator": {"source_sha256": "0" * 64},
            }

            def interrupted(staged, dest):
                self.assertEqual(Path(dest), path)
                self.assertEqual(Path(staged).parent, path.parent)
                staged_doc = json.loads(Path(staged).read_text(encoding="utf-8"))
                self.assertIn("lab_second", staged_doc["lab_scenarios"]["scenarios"])
                self.assertEqual(path.read_bytes(), before)
                raise OSError("interrupted before replace")

            with patch.object(mg.os, "replace", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "interrupted before replace"):
                    mg.register_scenario(root, manifest)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(set(path.parent.iterdir()), files)

            mg.register_scenario(root, manifest)
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(doc["lab_scenarios"]["scenarios"]), {"lab_voidcorner", "lab_second"})

    def test_register_scenario_validates(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            doc = json.loads((root / "tools" / "lab_instruments.json").read_text())
            self.assertEqual(argus_lab.validate_scenarios(root, doc), [])
            row = doc["lab_scenarios"]["scenarios"]["lab_voidcorner"]
            self.assertEqual(row["claim_tier"], "isolation")
            row["claim_tier"] = "stock"
            self.assertTrue(argus_lab.validate_scenarios(root, doc))

    def test_a_lab_result_needs_stock_tapes_to_name_a_stock_map(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            claim = {"id": "x", "status": "supported", "maps": ["lab_voidcorner", "dm4"],
                     "evidence": ["lab_tape"]}
            errors = argus_lab.promotion_errors(root, claim, "claim x")
            self.assertTrue(any("real geometry" in e for e in errors), errors)
            claim["evidence"] = ["lab_tape", "stock_tape"]
            self.assertEqual(argus_lab.promotion_errors(root, claim, "claim x"), [])
            isolation = {"id": "y", "status": "supported", "maps": ["lab_voidcorner"], "evidence": ["lab_tape"]}
            self.assertEqual(argus_lab.promotion_errors(root, isolation, "claim y"), [])
            hidden = {"id": "z", "status": "supported", "maps": ["dm4"], "evidence": ["lab_tape", "stock_tape"]}
            self.assertTrue(argus_lab.promotion_errors(root, hidden, "claim z"))

    def test_a_ladder_results_file_can_carry_the_tape_maps(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            sha = "0" * 64
            (root / "runs" / "ladder.results.json").write_text(json.dumps({"tapes": [
                {"run": "a", "map": "lab_voidcorner", "sha256": sha},
                {"run": "b", "map": "dm4", "sha256": sha}]}))
            claim = {"id": "x", "status": "supported", "maps": ["lab_voidcorner", "dm4"],
                     "evidence": ["runs/ladder.results.json"]}
            self.assertEqual(argus_lab.promotion_errors(root, claim, "claim x"), [])
            claim["maps"] = ["lab_voidcorner", "dm2"]
            self.assertTrue(argus_lab.promotion_errors(root, claim, "claim x"))
            unhashed = root / "runs" / "loose.results.json"
            unhashed.write_text(json.dumps({"tapes": [{"run": "b", "map": "dm4"}]}))
            self.assertEqual(argus_lab.evidence_maps(root, "runs/loose.results.json"), set())


class CliOutputPaths(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.parent = Path(fixture.name)
        self.root = self.parent / "checkout"
        self.root.mkdir()
        self.request = self.parent / "request.json"
        self.request.write_text(json.dumps(small_request()), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("ARGUS_")}
        env["ARGUS_ROOT"] = str(self.root)
        patch_env = patch.dict(os.environ, env, clear=True)
        patch_env.start()
        self.addCleanup(patch_env.stop)

    def invoke(self, command, *args):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = mg.main([command, str(self.request), *map(str, args), "--json"])
        return status, json.loads(stdout.getvalue())

    def test_generate_rejects_an_absolute_directory_outside_the_checkout(self):
        misplaced = self.parent / "misplaced"
        result = subprocess.run([sys.executable, str(HERE / "lab_mapgen.py"),
                                 "generate", str(self.request), "--out", str(misplaced), "--json"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("--out", json.loads(result.stdout)["error"])
        self.assertFalse(misplaced.exists())

    def test_generate_accepts_a_directory_under_labmaps(self):
        status, result = self.invoke("generate", "--out", "labmaps/private")
        self.assertEqual(status, 0, result)
        self.assertTrue((self.root / result["map"]).is_file())

    def test_nav_checks_both_outputs_before_starting_navgen(self):
        for flag, destination in (("--qc", "runs/preview.qc"), ("--png", "src/preview.png")):
            with self.subTest(flag=flag), patch.object(mg.subprocess, "run") as launch:
                status, result = self.invoke("nav", flag, destination)
                self.assertEqual(status, 2, result)
                self.assertIn(flag, result["error"])
                launch.assert_not_called()

    def test_nav_checks_the_qc_sidecar_before_starting_navgen(self):
        source = self.root / "src"
        source.mkdir()
        qc = source / "private.qc"
        sidecar = self.parent / "target.json"
        sidecar.write_text("keep", encoding="utf-8")
        try:
            Path(f"{qc}.json").symlink_to(sidecar)
        except OSError:
            self.skipTest("creating a file symlink requires permission")
        with patch.object(mg.subprocess, "run") as launch:
            status, result = self.invoke("nav", "--qc", qc)
        self.assertEqual(status, 2, result)
        self.assertIn(".qc.json", result["error"])
        launch.assert_not_called()
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "keep")

    def test_nav_preserves_existing_source_but_keeps_the_map_regeneration_path(self):
        source = self.root / "src"
        source.mkdir()
        existing = source / "argus.qc"
        existing.write_text("keep", encoding="utf-8")
        status, result = self.invoke("nav", "--qc", existing)
        self.assertEqual(status, 2, result)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

        installed = self.root / "maps_local"
        installed.mkdir()
        (installed / "lab_unit.bsp").touch()
        default_qc = source / "argus_nav_lab_unit.qc"
        default_qc.touch()
        with patch.object(mg.subprocess, "run") as launch:
            launch.return_value = subprocess.CompletedProcess([], 0, "", "")
            mg.run_navgen(self.root, mg.normalise(small_request()))
        self.assertIn(str(default_qc), launch.call_args.args[0])

    def test_record_accepts_the_native_nav_log_location(self):
        log = self.root / "labmaps" / "lab_unit" / "navgen.log"
        log.parent.mkdir(parents=True)
        log.write_text("review", encoding="utf-8")
        with patch.object(mg, "record", return_value={"ok": True}) as record:
            status, result = self.invoke("record", "--nav-out", log)
            self.assertEqual(status, 0, result)
            self.assertEqual(record.call_args.args[2], "review")
        status, result = self.invoke("record", "--nav-out", self.request)
        self.assertEqual(status, 2, result)
        self.assertIn("--nav-out", result["error"])


TOOLS_READY = mg.tools_status(ROOT)["ready"]


@unittest.skipUnless(TOOLS_READY, "ericw-tools not installed (python tools/lab_mapgen.py tools --install)")
class IntegrationSmoke(unittest.TestCase):
    """A real BSP, a real navgen pass and, when asked, a real engine load."""

    def test_compile_navgen_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            request = small_request(name="lab_smoketest")
            path = td / "request.json"
            path.write_text(json.dumps(request))
            env = dict(os.environ, ARGUS_ROOT=str(ROOT), ARGUS_MAPS=str(td / "maps"),
                       ARGUS_BASEDIR=str(td / "engine"), ARGUS_GAME="argus", ARGUS_SRC=str(td / "src"))
            req = mg.normalise(request)
            out = td / "build"
            old = dict(os.environ)
            os.environ.update(env)
            try:
                compiled, the_plan, _files = mg.compile_map(ROOT, req, out)
                placed = mg.install_bsp(ROOT, req, out / "lab_smoketest.bsp")
            finally:
                os.environ.clear()
                os.environ.update(old)
            self.assertTrue(all(step["ok"] for step in compiled["steps"].values()), compiled)
            self.assertFalse(compiled["steps"]["qbsp"]["leak"])
            bsp = out / "lab_smoketest.bsp"
            self.assertEqual(Bsp(bsp).version, 29)
            self.assertEqual(compiled["bsp_entities"], the_plan["entity_count"])
            self.assertTrue((td / "maps" / "lab_smoketest.bsp").is_file(), placed)
            again, _, _ = mg.compile_map(ROOT, req, td / "again")
            self.assertEqual(again["bsp_sha256"], compiled["bsp_sha256"], "the compile is reproducible")

            qc = td / "src" / "argus_nav_lab_smoketest.qc"
            qc.parent.mkdir()
            nav = subprocess.run([sys.executable, str(HERE / "argus_navgen.py"), str(bsp), "lab_smoketest",
                                  str(qc), str(td / "nav.png"), "--no-dispatcher"],
                                 capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(nav.returncode, 0, nav.stdout[-2000:] + nav.stderr[-2000:])
            graph = json.loads(Path(str(qc) + ".json").read_text())
            self.assertGreater(len(graph["nodes"]), 10)
            x0, y0, z0, x1, y1, z1 = the_plan["extent"]
            for node in graph["nodes"]:
                self.assertTrue(x0 <= node[0] <= x1 and y0 <= node[1] <= y1 and z0 <= node[2] <= z1,
                                f"waypoint {node} is outside the sealed hull")
            from argus_mapgate import assess_playability
            verdict = assess_playability(bsp, str(qc) + ".json")
            self.assertEqual([r for r in verdict.reasons if "mill" not in r], [],
                             "only the engine mill may stand between this graph and registration")

            if os.environ.get("ARGUS_LAB_SMOKE_ENGINE") == "1":
                self.engine_load(bsp, td)

    def test_build_then_record_registers_the_scenario(self):
        """The Python half of lab_request in a scratch root: build, navgen, record."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir()
            (root / "tools" / "lab_instruments.json").write_text(json.dumps({"schema": 1}) + "\n")
            src = root / "src"
            src.mkdir()
            (src / "progs.src").write_text("argus_nav.qc\nargus_nav_dispatch.qc\n")
            (src / "argus_nav_dispatch.qc").write_text("void() Argus_Nav_Spawn =\n{\n};\n")
            env = {"ARGUS_ROOT": str(root), "ARGUS_MAPS": str(root / "maps"), "ARGUS_BASEDIR": str(root / "engine"),
                   "ARGUS_GAME": "argus", "ARGUS_SRC": str(src), "ARGUS_ERICW": str(mg.tools_dir(ROOT))}
            req = mg.normalise(small_request(name="lab_recordtest"))
            old = dict(os.environ)
            os.environ.update(env)
            try:
                manifest = mg.build(root, req)
                self.assertTrue((root / "maps" / "lab_recordtest.bsp").is_file())
                self.assertTrue((root / "engine" / "argus" / "maps" / "lab_recordtest.bsp").is_file())
                self.assertEqual(manifest["install"]["maps"], "maps/lab_recordtest.bsp")
                self.assertTrue(manifest["navgen_readiness"]["ready"], manifest["navgen_readiness"])
                (root / "runs").mkdir()
                done = mg.run_navgen(root, req, png=str(root / "runs" / "nav.png"))
                mill = {"confirm": True, "passes": [{"kind": "walk", "failed": 0, "teleport_failures": 0}]}
                final = mg.record(root, req, done["stdout"], mill, registered=False)
            finally:
                os.environ.clear()
                os.environ.update(old)
            self.assertEqual(final["registration"]["registered"], False)
            self.assertGreater(final["nav"]["nodes"], 10)
            self.assertIn("edict budget: status ok", final["nav"]["edict_budget"])
            self.assertEqual(final["mill"], mill)
            doc = json.loads((root / "tools" / "lab_instruments.json").read_text())
            row = doc["lab_scenarios"]["scenarios"]["lab_recordtest"]
            self.assertEqual(row["id"], mg.scenario_id(req))
            self.assertEqual(row["claim_tier"], "isolation")
            self.assertFalse(row["registered"])
            self.assertIn("isolation", doc["lab_scenarios"]["rule"])
            on_disk = json.loads((root / "labmaps" / "lab_recordtest" / "manifest.json").read_text())
            self.assertEqual(on_disk["compile"]["bsp_sha256"], final["compile"]["bsp_sha256"])

    def engine_load(self, bsp, td):
        """Load the map in the real engine through the lab's own match path."""
        lab = os.environ.get("ARGUS_LAB") or str(ROOT / "tools" / "argus_mcp" / "install" / "bin" / "argus-mcp.exe")
        base = Path(os.environ.get("ARGUS_BASEDIR", ROOT / "engine"))
        if not Path(lab).is_file() or not (base / "argus" / "progs.dat").is_file():
            self.skipTest("no lab binary or engine game directory for the engine load")
        game = base / "argus_labsmoke"
        if game.exists():
            shutil.rmtree(game)
        (game / "maps").mkdir(parents=True)
        try:
            for name in ("autoexec.cfg", "progs.dat"):
                shutil.copyfile(base / "argus" / name, game / name)
            if (base / "argus" / "progs").is_dir():
                shutil.copytree(base / "argus" / "progs", game / "progs")
            shutil.copyfile(bsp, game / "maps" / bsp.name)
            env = dict(os.environ, ARGUS_GAME="argus_labsmoke", ARGUS_RUNS=str(td / "runs"))
            (td / "runs").mkdir(exist_ok=True)
            run = subprocess.run([lab, "match", "lab_smoketest", "15", "labsmoke_load", "--skill", "1",
                                  "--port", "26119"], capture_output=True, text=True, env=env, timeout=240)
            self.assertEqual(run.returncode, 0, run.stdout[-2000:] + run.stderr[-2000:])
            tape = (td / "runs" / "labsmoke_load.log").read_text(encoding="latin-1")
            self.assertIn("ARGUS init on lab_smoketest", tape)
            for marker in ("Host_Error", "PR_RunError", "SV_Error", "runaway loop"):
                self.assertNotIn(marker, tape)
            self.assertRegex(tape, r"ARGLOG \S")
        finally:
            shutil.rmtree(game, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
