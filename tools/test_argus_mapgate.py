#!/usr/bin/env python3
"""Regression tests for the first-registration playability gate."""
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from argus_bsp import (LUMP_ENTITIES, LUMP_LEAVES, LUMP_MODELS, LUMP_NAMES,
                       LUMP_NODES, LUMP_PLANES)
from argus_mapgate import assess_playability


def write_bsp(path, entities, *, brush_pad=False):
    ent_lump = "".join(
        "{\n" + "".join(f'"{key}" "{value}"\n' for key, value in ent.items()) + "}\n"
        for ent in entities
    ).encode("ascii") + b"\0"
    # World floor at z 0, with an optional brush reaching up to z 256.
    data = [b""] * len(LUMP_NAMES)
    data[LUMP_ENTITIES] = ent_lump
    data[LUMP_PLANES] = struct.pack("<4fi", 0, 0, 1, 0, 2)
    data[LUMP_NODES] = struct.pack("<i8h2H", 0, -1, -2, *([0] * 8))
    data[LUMP_LEAVES] = b"".join(
        struct.pack("<2i6h2H4B", contents, -1, *([0] * 12))
        for contents in (-1, -2)
    )

    def model(bounds):
        return struct.pack("<9f7i", *bounds, *([0] * 10))

    data[LUMP_MODELS] = model((-1024, -1024, -256, 1024, 1024, 1024))
    if brush_pad:
        data[LUMP_MODELS] += model((480, -32, 0, 544, 32, 256))
    offset = 4 + len(data) * 8
    lumps = []
    for lump in data:
        lumps.append((offset, len(lump)))
        offset += len(lump)
    path.write_bytes(
        struct.pack("<i", 29)
        + b"".join(struct.pack("<ii", offset, length) for offset, length in lumps)
        + b"".join(data)
    )


class TestArgusMapGate(unittest.TestCase):
    def test_malformed_endpoints_cannot_pass_playability(self):
        from argus_navjson import FAMILIES
        self.write_entities()
        for family in FAMILIES:
            self.write_graph()
            graph = json.loads(self.graph.read_text())
            graph[family] = [[0.5, 1]]
            self.graph.write_text(json.dumps(graph))
            self.write_probe()
            with self.subTest(family=family):
                with self.assertRaisesRegex(ValueError, 'endpoints must be integers'):
                    assess_playability(self.bsp, self.graph, self.probe)

    def test_reach_measures_a_spawn_where_the_body_comes_to_rest(self):
        # #789: a floating spawn falls to the first floor; #783: a spawn on a
        # brush-entity pad stays on it; a spawn on the floor keeps its origin.
        from argus_reach import standing_point

        class World:
            def floor_under(self, x, y, z, maxdrop):
                return -740.0 - 24 if x > 900 else 0.0

        world = World()
        self.assertEqual(standing_point(world, (1024.0, 720.0, -104.0)), (1024.0, 720.0, -740.0))
        self.assertEqual(standing_point(world, (0.0, 0.0, 24.0)), (0.0, 0.0, 24.0))
        pad = [("func_wall", (100.0, -400.0, 0.0), (160.0, -320.0, 256.0))]
        self.assertEqual(standing_point(world, (128.0, -360.0, 280.0), pad), (128.0, -360.0, 280.0))
        self.assertEqual(standing_point(world, (128.0, -360.0, 280.0)), (128.0, -360.0, 24.0))
        above = [("func_wall", (100.0, -400.0, 0.0), (160.0, -320.0, 400.0))]
        self.assertEqual(standing_point(world, (128.0, -360.0, 280.0), above), (128.0, -360.0, 24.0))

    def test_door_only_hop_is_in_every_reader(self):
        from argus_mapgate import _graph_edges
        from argus_pointfile import _adj
        from argus_reach import load_graph
        graph = {"nodes": [[0, 0, 24], [64, 0, 24]], "doorlinks": [[0, 1]]}
        self.assertIn(1, _graph_edges(graph)[0])
        self.assertIn(1, _adj(graph)[0])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nav.json"
            path.write_text(json.dumps(graph))
            _, walk, free, _ = load_graph(path)
        self.assertTrue(1 in walk[0] or (0, 1) in map(tuple, free))

    def test_playability_does_not_assume_equipment_or_skill_gated_hops(self):
        from argus_mapgate import _graph_edges
        for family in ("rjlinks", "sprintlinks"):
            graph = {"nodes": [[0, 0, 24], [64, 0, 24]], family: [[0, 1]]}
            self.assertNotIn(1, _graph_edges(graph)[0])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="argus-mapgate-")
        self.root = Path(self.tmp.name)
        self.bsp = self.root / "fixture.bsp"
        self.graph = self.root / "argus_nav_fixture.qc.json"
        self.probe = self.root / "argus_nav_fixture.probe.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_graph(self, links=None, jlinks=None):
        self.graph.write_text(json.dumps({
            "nodes": [[0, 0, 24], [64, 0, 24], [128, 0, 24]],
            "links": links if links is not None else [
                [0, 1, 1], [1, 0, 1], [1, 2, 0], [2, 1, 0],
            ],
            "jlinks": jlinks or [],
            "teles": [],
            "liftlinks": [],
            "swimlinks": [],
            "trainlinks": [],
            "rjlinks": [],
            "sprintlinks": [],
            "doorlinks": [],
        }))

    def write_probe(self, graph_md5=None, walk=4, jump=None, failed=0):
        graph_md5 = graph_md5 or hashlib.md5(
            self.graph.read_bytes(), usedforsecurity=False
        ).hexdigest()
        dm = {
            "walk": {
                "swept": walk,
                "passed": max(0, walk - failed),
                "failed": failed,
                "teleport_failures": 0,
            }
        }
        if jump is not None:
            dm["jump"] = {
                "swept": jump,
                "passed": jump,
                "failed": 0,
                "teleport_failures": 0,
            }
        self.probe.write_text(json.dumps({
            "verification": {
                "graph_md5": graph_md5,
                "deathmatch": dm,
            }
        }))

    def write_entities(self, *extra, brush_pad=False):
        write_bsp(self.bsp, [
            {"classname": "worldspawn"},
            {"classname": "info_player_deathmatch", "origin": "0 0 24"},
            {"classname": "weapon_rocketlauncher", "origin": "128 0 24"},
            *extra,
        ], brush_pad=brush_pad)

    def test_current_reach_and_engine_evidence_are_playable(self):
        self.write_entities()
        self.write_graph()
        self.write_probe()

        verdict = assess_playability(self.bsp, self.graph, self.probe)

        self.assertTrue(verdict.playable, verdict.reasons)
        self.assertEqual(verdict.spawn_count, 1)
        self.assertEqual(verdict.item_count, 1)
        self.assertIn("status playable", verdict.line())

    def test_unreachable_item_fails_even_when_the_graph_itself_has_links(self):
        self.write_entities()
        self.write_graph(links=[[0, 1, 1], [1, 0, 1]])
        self.write_probe(walk=2)

        verdict = assess_playability(self.bsp, self.graph, self.probe)

        self.assertFalse(verdict.playable)
        self.assertTrue(any("cannot reach weapon_rocketlauncher" in r
                            for r in verdict.reasons), verdict.reasons)

    def test_floating_spawn_uses_the_floor_for_distance_and_reach(self):
        self.write_entities({"classname": "info_player_deathmatch", "origin": "0 0 500"})
        self.write_graph()
        graph = json.loads(self.graph.read_text())
        for aerial_seats in ([], [[0, 0, 500]]):
            with self.subTest(aerial_seats=aerial_seats):
                self.graph.write_text(json.dumps({
                    **graph, "nodes": graph["nodes"] + aerial_seats,
                }))
                self.write_probe()
                verdict = assess_playability(self.bsp, self.graph, self.probe)
                self.assertTrue(verdict.playable, verdict.reasons)

    def test_floating_spawn_lands_on_a_solid_brush_pad(self):
        self.write_entities(
            {"classname": "func_wall", "model": "*1"},
            {"classname": "info_player_deathmatch", "origin": "512 0 512"},
            brush_pad=True,
        )
        self.write_graph()
        graph = json.loads(self.graph.read_text())
        graph["nodes"] += [[512, 0, 280], [512, 0, 24]]
        graph["links"].append([3, 2, 0])
        self.graph.write_text(json.dumps(graph))
        self.write_probe()
        verdict = assess_playability(self.bsp, self.graph, self.probe)
        self.assertTrue(verdict.playable, verdict.reasons)

    def test_probe_must_name_the_current_graph(self):
        self.write_entities()
        self.write_graph()
        self.write_probe(graph_md5="stale")

        verdict = assess_playability(self.bsp, self.graph, self.probe)

        self.assertFalse(verdict.playable)
        self.assertTrue(any("different graph" in r for r in verdict.reasons),
                        verdict.reasons)

    def test_generated_jumps_require_a_jump_probe(self):
        self.write_entities()
        self.write_graph(jlinks=[[1, 2]])
        self.write_probe()

        verdict = assess_playability(self.bsp, self.graph, self.probe)

        self.assertFalse(verdict.playable)
        self.assertTrue(any("jump links have no current mill pass" in r
                            for r in verdict.reasons), verdict.reasons)
        self.write_probe(jump=1)
        self.assertTrue(
            assess_playability(self.bsp, self.graph, self.probe).playable
        )

    def test_items_removed_in_deathmatch_do_not_block_registration(self):
        self.write_entities({
            "classname": "weapon_lightning",
            "origin": "4096 0 24",
            "spawnflags": "2048",
        })
        self.write_graph()
        self.write_probe()

        verdict = assess_playability(self.bsp, self.graph, self.probe)

        self.assertTrue(verdict.playable, verdict.reasons)
        self.assertEqual(verdict.item_count, 1)


if __name__ == "__main__":
    unittest.main()
