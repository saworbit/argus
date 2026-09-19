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
from argus_mapgate import assess_playability


def write_bsp(path, entities):
    ent_lump = "".join(
        "{\n" + "".join(f'"{key}" "{value}"\n' for key, value in ent.items()) + "}\n"
        for ent in entities
    ).encode("ascii") + b"\0"
    header_size = 4 + 15 * 8
    lumps = [(0, 0)] * 15
    lumps[0] = (header_size, len(ent_lump))
    path.write_bytes(
        struct.pack("<i", 29)
        + b"".join(struct.pack("<ii", offset, length) for offset, length in lumps)
        + ent_lump
    )


class TestArgusMapGate(unittest.TestCase):
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

    def write_entities(self, *extra):
        write_bsp(self.bsp, [
            {"classname": "worldspawn"},
            {"classname": "info_player_deathmatch", "origin": "0 0 24"},
            {"classname": "weapon_rocketlauncher", "origin": "128 0 24"},
            *extra,
        ])

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
