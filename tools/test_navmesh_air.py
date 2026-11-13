#!/usr/bin/env python3
"""The navmesh air layer on a built map where momentum decides the landing.

A platform (floor 128) stands west of x 0; a lower floor (0) runs east of
it, with a lava strip from x 64 to 256. Hull 1 carries the platform edge
16u out, at x 16. Stepping straight off lands dry at the foot of the wall,
which is all the floor mesh models. Running off does not:

    straight down   x ~ 18          dry
    walk, 240 u/s   x ~ 16 + 136    lava
    run, 320 u/s    x ~ 16 + 181    lava
    running jump    x ~ 16 + 319    dry, past the strip
"""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import argus_navmesh as nm  # noqa: E402


def write_fixture(path, ents_extra=b"", models_extra=b""):
    rows = (
        (1.0, 0.0, 0.0, 0.0, 0),     # p0 platform face (hull 0)
        (0.0, 0.0, 1.0, 128.0, 2),   # p1 platform top (hull 0)
        (0.0, 0.0, 1.0, 0.0, 2),     # p2 lower floor (hull 0)
        (1.0, 0.0, 0.0, 64.0, 0),    # p3 lava west edge
        (1.0, 0.0, 0.0, 256.0, 0),   # p4 lava east edge
        (0.0, 0.0, 1.0, 16.0, 2),    # p5 lava surface
        (1.0, 0.0, 0.0, 16.0, 0),    # p6 platform face, hull 1 (16u out)
        (0.0, 0.0, 1.0, 152.0, 2),   # p7 platform top, hull 1 origin
        (0.0, 0.0, 1.0, 24.0, 2),    # p8 lower floor, hull 1 origin
    )
    planes = b"".join(struct.pack("<ffffi", *r) for r in rows)
    # hull 0: children >= 0 are nodes, -1 empty, -2 solid, -3 lava
    h0tree = ((0, 2, 1), (1, -1, -2), (2, 3, -2), (3, 4, -1), (4, -1, 5),
              (5, -1, -3))
    h0nodes = b"".join(
        struct.pack("<i8h2H", p, c0, c1, -1024, -512, -64, 1024, 512, 512, 0, 0)
        for p, c0, c1 in h0tree)
    leaves = b"".join(
        struct.pack("<2i6h2H4B", c, -1, -1024, -512, -64, 1024, 512, 512,
                    0, 0, 0, 0, 0, 0)
        for c in (-1, -2, -5))
    # hull 1: children >= 0 are clipnodes, negative are contents
    clipnodes = b"".join(struct.pack("<ihh", *r) for r in (
        (6, 2, 1), (7, -1, -2), (8, -1, -2)))
    models = struct.pack("<9f7i", -512.0, -256.0, -64.0, 768.0, 256.0, 512.0,
                         0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0) + models_extra
    ents = b'{\n"classname" "worldspawn"\n}\n' + ents_extra + b"\0"
    table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
    for idx, payload in ((0, ents), (1, planes), (5, h0nodes), (9, clipnodes),
                         (10, leaves), (14, models)):
        table[idx] = (base + len(blob), len(payload))
        blob += payload
    path.write_bytes(struct.pack("<i", 29)
                     + b"".join(struct.pack("<ii", o, n) for o, n in table) + blob)


def arglog(name, t, x, y, z):
    return (f"ARGLOG {name} t {t:.1f} pos '{x:.1f} {y:.1f} {z:.1f}' spd 320 "
            f"yaw 0 mode 2 st 0 gl 0 hp 100 frg 0")


class AirLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bsp_path = Path(cls.tmp.name) / "fixture.bsp"
        write_fixture(cls.bsp_path)
        cls.bsp, cls.frags, _ = nm.load_mesh(cls.bsp_path)
        cls.samples = nm.air_layer(cls.bsp, cls.frags)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def edge(self):
        return [s for s in self.samples if abs(s["pos"][0] - 16.0) < 0.5]

    def test_only_the_platform_edge_is_a_ledge(self):
        self.assertTrue(self.edge())
        self.assertEqual(len(self.edge()), len(self.samples))
        for s in self.edge():
            self.assertAlmostEqual(s["n"][0], 1.0)

    def test_momentum_decides_the_landing(self):
        for s in self.edge():
            self.assertEqual(s["drop"], "floor")
            out = {k: r["kind"] for k, r in s["out"].items()}
            self.assertEqual(out["walk"], "lava")
            self.assertEqual(out["run"], "lava")
            self.assertEqual(out["jump"], "floor")
            self.assertEqual(s["verdict"], "danger")
            run_x = s["out"]["run"]["pos"][0]
            self.assertTrue(180 < run_x < 215, run_x)
            jump_x = s["out"]["jump"]["pos"][0]
            self.assertTrue(256 < jump_x < 360, jump_x)

    def test_flight_respects_gravity(self):
        r = nm.fly(self.bsp, 16.0, 0.0, 152.0, 1.0, 0.0, 320.0)
        # the fall ends when the FEET reach the lava surface at z 16, so
        # the origin drops 152 - 39 = 113: t = sqrt(2 * 113 / 800) = 0.531 s
        self.assertEqual(r["kind"], "lava")
        self.assertAlmostEqual(r["t"], 0.531, delta=0.02)
        slow = nm.fly(self.bsp, 16.0, 0.0, 152.0, 1.0, 0.0, 320.0, gravity=100.0)
        self.assertEqual(slow["kind"], "floor")   # e1m8 gravity floats it past

    def test_a_run_starting_short_of_the_edge_keeps_running(self):
        r = nm.fly(self.bsp, -40.0, 0.0, 152.0, 1.0, 0.0, 320.0)
        self.assertEqual(r["kind"], "lava")
        self.assertTrue(180 < r["pos"][0] < 215, r["pos"])

    def test_link_runs_show_the_speed_dependence(self):
        doc = {"nodes": [[-64.0, 0.0, 152.0], [400.0, 0.0, 24.0]],
               "links": [[0, 1, 0]]}
        fast = nm.link_runs(self.bsp, doc, speed=nm.RUN)
        self.assertEqual(len(fast), 1)
        self.assertEqual(fast[0]["straight"], "floor")
        self.assertEqual(fast[0]["run"], "lava")
        self.assertAlmostEqual(fast[0]["lip"][0], 14.0, delta=4.0)

    def test_entries_are_judged_against_a_base_rate(self):
        lines = []
        # one bot runs off the platform edge into the lava strip (its own
        # earlier windows would count as ordinary moves, which inflates
        # the base rate: conservative, but this fixture keeps one window)
        for t, x, z in ((1.5, -40, 152), (2.0, 120, 70), (2.5, 180, 24)):
            lines.append(arglog("Faller", t, x, 0, z))
        # another walks the platform far from any edge
        for i in range(12):
            lines.append(arglog("Walker", 1.0 + 0.5 * i, -480 + 30 * i, -150, 152))
        r = nm.entries_vs_ledges(self.bsp, self.samples, ["\n".join(lines)])
        self.assertEqual(r["entries"], 1)
        self.assertEqual(r["entries_danger"], 1)
        self.assertEqual(r["entries_jump"], 0)
        self.assertGreater(r["moves"], 5)
        self.assertEqual(r["moves_danger"], 0)

    def test_a_jump_event_splits_the_entry(self):
        lines = [arglog("Jumper", 1.5, -40, 0, 152),
                 "ARGEVT Jumper jump",
                 arglog("Jumper", 2.0, 120, 0, 70),
                 arglog("Jumper", 2.5, 180, 0, 24)]
        r = nm.entries_vs_ledges(self.bsp, self.samples, ["\n".join(lines)])
        self.assertEqual((r["entries"], r["entries_jump"], r["entries_danger_jump"]),
                         (1, 1, 1))


def bridge():
    """A func_wall deck over the lava strip, x 150..250, top at z 32."""
    model = struct.pack("<9f7i", 150.0, -64.0, 0.0, 250.0, 64.0, 32.0,
                        0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
    ent = b'{\n"classname" "func_wall"\n"model" "*1"\n}\n'
    return ent, model


class Brushes(unittest.TestCase):
    """The world hull knows nothing of brush entities (e1m7's pads and
    lava bridge deck), so a deck over the strip must catch the run."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "bridge.bsp"
        ent, model = bridge()
        write_fixture(path, ent, model)
        cls.bsp, cls.frags, _ = nm.load_mesh(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_brush_boxes_reads_the_deck(self):
        self.assertEqual(nm.brush_boxes(self.bsp),
                         [("func_wall", (150.0, -64.0, 0.0), (250.0, 64.0, 32.0))])

    def test_the_deck_catches_the_run(self):
        world = nm.WithBrushes(self.bsp, nm.brush_boxes(self.bsp))
        r = nm.fly(world, 16.0, 0.0, 152.0, 1.0, 0.0, 320.0)
        self.assertEqual(r["kind"], "floor")
        self.assertEqual(r["on"], "func_wall")
        self.assertAlmostEqual(r["pos"][2], 56.0, delta=1.0)   # deck top + 24
        bare = nm.fly(nm.WithBrushes(self.bsp, []), 16.0, 0.0, 152.0, 1.0, 0.0, 320.0)
        self.assertEqual(bare["kind"], "lava")

    def test_verdict_changes_with_the_deck(self):
        with_deck = nm.air_layer(nm.WithBrushes(self.bsp, nm.brush_boxes(self.bsp)),
                                 self.frags)
        without = nm.air_layer(self.bsp, self.frags)
        self.assertTrue(with_deck and without)
        self.assertEqual({s["verdict"] for s in without}, {"danger"})
        # in front of the deck a straight run lands on it; turned runs can
        # still miss it, so those points become risky, not safe
        front = [s for s in with_deck if abs(s["pos"][1]) <= 40]
        beside = [s for s in with_deck if abs(s["pos"][1]) >= 120]
        self.assertTrue(front and beside)
        self.assertNotIn("danger", {s["verdict"] for s in front})
        self.assertEqual({s["verdict"] for s in beside}, {"danger"})

    def test_spawn_positions_follow_doors_qc_and_plats_qc(self):
        b = type("B", (), {})()
        b.models = [None, (0.0, 0.0, 0.0, 64.0, 16.0, 64.0)]
        b.entities = [{"classname": "func_door", "model": "*1", "angle": "0",
                       "spawnflags": "1", "lip": "8"},
                      {"classname": "func_plat", "model": "*1"},
                      {"classname": "func_wall", "model": "*1", "spawnflags": "2048"}]
        boxes = nm.brush_boxes(b)
        # START_OPEN door: travel 64 - 8 = 56 along +x; plat: down 64 - 8 = 56
        self.assertEqual(boxes[0], ("func_door", (56.0, 0.0, 0.0), (120.0, 16.0, 64.0)))
        self.assertEqual(boxes[1], ("func_plat", (0.0, 0.0, -56.0), (64.0, 16.0, 8.0)))
        self.assertEqual(len(boxes), 2)   # a 2048 wall is not in deathmatch


class MapGravity(unittest.TestCase):
    def test_world_qc_gravity(self):
        self.assertEqual(nm.map_gravity("maps_local/e1m8.bsp"), 100.0)
        self.assertEqual(nm.map_gravity("maps/lq_e1m8.bsp"), 100.0)
        self.assertEqual(nm.map_gravity("maps_local/dm4.bsp"), 800.0)


if __name__ == "__main__":
    unittest.main()
