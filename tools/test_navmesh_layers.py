#!/usr/bin/env python3
"""The navmesh water and time layers (#791) on built maps.

POOL: a pit from x 0 to 256 in a floor at z 0, its bed at z -192 and
water up to z -16. Hull 1 carries the banks 16u in, so the swim volume
is origins x 16..240, z -168..-16, and the eyes (origin + 22) clear the
surface above z -38:

    bank z 0 | water, surface -16     | bank z 0
             | breathable  -38..-16   |
             | submerged  -168..-38   |
             +-------- bed -192 ------+

TUNNEL: the same pit with a wall from x 96 to 160 hanging down to z -60,
so the surface splits into two air regions joined only under the wall.

PLAT: test_navmesh_air's platform beside a lava strip with a func_plat
whose top stands level with the platform (z 128) and whose bottom rests
in the strip (z 16), so a ledge in front of it is bridged in one state
and lethal in the other.
"""
import contextlib
import io
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import argus_navmesh as nm  # noqa: E402
from test_navmesh_air import write_fixture as write_air_fixture  # noqa: E402

EMPTY, SOLID, WATER = -1, -2, -3


def write_bsp(path, planes, h0tree, leaves, clipnodes, ents=b""):
    """A BSP29 with the lumps the mesh reads.

    h0tree rows are (plane, front, back) with children >= 0 nodes and -1 - k
    leaf k; leaves rows are (contents, mins, maxs); clipnodes rows are
    (plane, front, back) with negative children contents.
    """
    pl = b"".join(struct.pack("<ffffi", *r) for r in planes)
    nodes = b"".join(struct.pack("<i8h2H", p, c0, c1, -1024, -1024, -512, 1024, 1024, 512, 0, 0)
                     for p, c0, c1 in h0tree)
    lv = b"".join(struct.pack("<2i6h2H4B", c, -1, *mn, *mx, 0, 0, 0, 0, 0, 0)
                  for c, mn, mx in leaves)
    cl = b"".join(struct.pack("<ihh", *r) for r in clipnodes)
    models = struct.pack("<9f7i", -512.0, -512.0, -256.0, 768.0, 512.0, 256.0,
                         0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
    ent = b'{\n"classname" "worldspawn"\n}\n' + ents + b"\0"
    table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
    for idx, payload in ((0, ent), (1, pl), (5, nodes), (9, cl), (10, lv), (14, models)):
        table[idx] = (base + len(blob), len(payload))
        blob += payload
    path.write_bytes(struct.pack("<i", 29)
                     + b"".join(struct.pack("<ii", o, n) for o, n in table) + blob)


BIG = ((-1024, -1024, -512), (1024, 1024, 512))
WATER_BOX = ((0, -256, -192), (256, 256, -16))


def write_pool(path):
    planes = (
        (1.0, 0.0, 0.0, 0.0, 0),      # p0 west bank face
        (1.0, 0.0, 0.0, 256.0, 0),    # p1 east bank face
        (0.0, 0.0, 1.0, 0.0, 2),      # p2 bank top
        (0.0, 0.0, 1.0, -192.0, 2),   # p3 pit bed
        (0.0, 0.0, 1.0, -16.0, 2),    # p4 water surface
        (1.0, 0.0, 0.0, 16.0, 0),     # p5 hull 1: west bank
        (1.0, 0.0, 0.0, 240.0, 0),    # p6 hull 1: east bank
        (0.0, 0.0, 1.0, 24.0, 2),     # p7 hull 1: bank top
        (0.0, 0.0, 1.0, -168.0, 2),   # p8 hull 1: pit bed
    )
    # leaves: 0 empty, 1 solid, 2 water
    h0 = ((0, 1, 4), (1, 4, 2), (3, 3, -2), (4, -1, -3), (2, -1, -2))
    h1 = ((7, EMPTY, 1), (5, 2, SOLID), (6, SOLID, 3), (8, EMPTY, SOLID))
    write_bsp(path, planes, h0, ((EMPTY, *BIG), (SOLID, *BIG), (WATER, *WATER_BOX)), h1)


def write_tunnel(path):
    planes = (
        (1.0, 0.0, 0.0, 0.0, 0),      # p0
        (1.0, 0.0, 0.0, 256.0, 0),    # p1
        (0.0, 0.0, 1.0, 0.0, 2),      # p2
        (0.0, 0.0, 1.0, -192.0, 2),   # p3
        (0.0, 0.0, 1.0, -16.0, 2),    # p4 surface
        (1.0, 0.0, 0.0, 96.0, 0),     # p5 wall west face
        (1.0, 0.0, 0.0, 160.0, 0),    # p6 wall east face
        (0.0, 0.0, 1.0, -60.0, 2),    # p7 wall bottom
        (1.0, 0.0, 0.0, 16.0, 0),     # p8 hull 1
        (1.0, 0.0, 0.0, 240.0, 0),    # p9
        (0.0, 0.0, 1.0, 24.0, 2),     # p10
        (0.0, 0.0, 1.0, -168.0, 2),   # p11
        (1.0, 0.0, 0.0, 80.0, 0),     # p12 hull 1: wall west
        (1.0, 0.0, 0.0, 176.0, 0),    # p13 hull 1: wall east
        (0.0, 0.0, 1.0, -92.0, 2),    # p14 hull 1: wall bottom
    )
    # node 0 x>=0, 1 x>=256, 2 bed, 3 wall west, 4 wall east, 5 wall bottom,
    # 6 wall top (flush with the banks), 7 water surface, 8 outside the pit
    h0 = ((0, 1, 8), (1, 8, 2), (3, 3, -2), (5, 4, 7), (6, 7, 5), (7, 6, 7),
          (2, -1, -2), (4, -1, -3), (2, -1, -2))
    h1 = ((10, EMPTY, 1), (8, 2, SOLID), (9, SOLID, 3), (11, 4, SOLID),
          (12, 5, EMPTY), (13, EMPTY, 6), (14, SOLID, EMPTY))
    write_bsp(path, planes, h0, ((EMPTY, *BIG), (SOLID, *BIG), (WATER, *WATER_BOX)), h1)


class Pool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "pool.bsp"
        write_pool(cls.path)
        cls.bsp, cls.frags, _ = nm.load_mesh(cls.path)
        cls.layer = nm.water_layer(cls.bsp, cls.frags)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_mesh_is_untouched(self):
        # two dry banks and the wet pit bed, exactly as before the layers
        self.assertEqual(len(self.frags), 3)
        self.assertEqual(sorted(f["wet"] for f in self.frags), [False, False, True])
        for f in self.frags:
            self.assertEqual(set(f), {"poly", "plane", "leaf", "wet"})

    def test_swim_volume_is_hull1_in_water(self):
        cells = self.layer["cells"]
        lo = [min(c["mins"][k] for c in cells) for k in range(3)]
        hi = [max(c["maxs"][k] for c in cells) for k in range(3)]
        self.assertAlmostEqual(lo[0], 16.0, delta=0.01)
        self.assertAlmostEqual(hi[0], 240.0, delta=0.01)
        self.assertAlmostEqual(lo[2], -168.0, delta=0.01)
        self.assertAlmostEqual(hi[2], -16.0, delta=0.01)
        span_y = hi[1] - lo[1]
        vol = sum(c["volume"] for c in cells)
        self.assertAlmostEqual(vol, 224.0 * span_y * 152.0, delta=vol * 1e-6)

    def test_the_eyes_split_the_volume(self):
        cells = self.layer["cells"]
        breath = [c for c in cells if c["breath"]]
        under = [c for c in cells if not c["breath"]]
        self.assertTrue(breath and under)
        self.assertAlmostEqual(min(c["mins"][2] for c in breath), -38.0, delta=0.01)
        self.assertAlmostEqual(max(c["maxs"][2] for c in under), -38.0, delta=0.01)
        for c in breath:
            self.assertEqual(c["surf"], -16.0)

    def test_one_pool_its_floor_and_both_banks_as_exits(self):
        pools = self.layer["pools"]
        self.assertEqual(len(pools), 1)
        p = pools[0]
        self.assertEqual(p["surface"], -16.0)
        self.assertEqual(p["surfaces"], [-16])
        self.assertEqual(p["air_regions"], 1)
        self.assertIsNone(p["crossing"])
        wet = [i for i, f in enumerate(self.frags) if f["wet"]]
        self.assertEqual(p["floors"], wet)
        banks = sorted(i for i, f in enumerate(self.frags) if not f["wet"])
        self.assertEqual(sorted(p["exits"]), banks)
        for e in p["exits"].values():
            self.assertAlmostEqual(e["z"] - e["surf"], 40.0, delta=0.01)
            self.assertLessEqual(e["gap"], 1.0)

    def test_dive_is_straight_up_from_the_bed(self):
        # deepest origin -168, eyes clear at -38: 130u, which is 0.43 s
        p = self.layer["pools"][0]
        self.assertAlmostEqual(p["dive"], 130.0, delta=0.5)
        self.assertAlmostEqual(p["dive_at"][2], -168.0, delta=0.01)
        self.assertEqual(p["sealed"], 0)
        self.assertEqual(nm.AIR_TIME * nm.SWIM_SPEED, 3600.0)

    def test_exit_rules(self):
        cell = next(c for c in self.layer["cells"] if c["breath"])

        def frag(x0, x1, z):
            return {"poly": [(x0, -64.0, z), (x1, -64.0, z), (x1, 64.0, z), (x0, 64.0, z)],
                    "plane": (0.0, 0.0, 1.0, z), "wet": False}
        # 70 over the surface: beyond the waterjump's 44
        self.assertEqual(nm.exit_test(self.bsp, cell, frag(-128.0, 16.0, 54.0))[0], "band")
        # in the band but 100u from the water
        self.assertEqual(nm.exit_test(self.bsp, cell, frag(-228.0, -84.0, 24.0))[0], "reach")
        self.assertEqual(nm.exit_test(self.bsp, cell, frag(-128.0, 16.0, 24.0))[0], "exit")
        self.assertAlmostEqual(nm.vault_apex(), 290.0 ** 2 / 1600.0)

    def test_shipped_swim_links_are_judged(self):
        bed = (128.0, 0.0, -168.0)
        doc = {"nodes": [list(bed), [-64.0, 0.0, 24.0], [-400.0, 0.0, 24.0],
                         [300.0, 0.0, 24.0]],
               "swimlinks": [[0, 1], [0, 2], [1, 3]]}
        rows = nm.swim_crosscheck(self.bsp, self.frags, self.layer, doc)
        self.assertEqual([r["verdict"] for r in rows], ["confirmed", "confirmed", "dry seat"])
        self.assertEqual(rows[0]["pool"], 0)

    def test_audit_prints_the_water_layer(self):
        nav = Path(self.tmp.name) / "nav.json"
        nav.write_text(json.dumps({"nodes": [[128.0, 0.0, -168.0], [-64.0, 0.0, 24.0]],
                                   "links": [], "swimlinks": [[0, 1]]}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(nm.main([str(self.path), "--audit", "--nav", str(nav)]), 0)
        text = out.getvalue()
        self.assertIn("water layer: 1 swim volume(s)", text)
        self.assertIn("longest dive to air 130u", text)
        self.assertIn("exits: 2 over a lip, 0 wading out", text)
        self.assertIn("shipped swim links (1) against the volumes: confirmed 1", text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            nm.main([str(self.path), "--audit", "--nav", str(nav), "--no-water"])
        self.assertNotIn("water layer", out.getvalue())


class Tunnel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "tunnel.bsp"
        write_tunnel(path)
        cls.bsp, cls.frags, _ = nm.load_mesh(path)
        cls.layer = nm.water_layer(cls.bsp, cls.frags)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_two_surfaces_joined_under_the_wall(self):
        pools = self.layer["pools"]
        self.assertEqual(len(pools), 1)
        p = pools[0]
        self.assertEqual(p["air_regions"], 2)
        # down 54 from the breath line to under the wall, 96 across, 54 up:
        # the portal-centre chain can only run longer than the straight legs
        self.assertGreater(p["crossing"], 150.0)
        self.assertLess(p["crossing"], 400.0)
        west, east = sorted(q[0] for q in p["crossing_at"])
        self.assertLess(west, 96.0)
        self.assertGreater(east, 160.0)

    def test_the_wall_top_is_an_exit_from_both_sides(self):
        p = self.layer["pools"][0]
        tops = [i for i, f in enumerate(self.frags)
                if not f["wet"] and 80.0 <= nm.centroid(f["poly"])[0] <= 176.0]
        self.assertEqual(len(tops), 1)
        self.assertIn(tops[0], p["exits"])


def plat(targeted=False):
    """func_plat *1: top x 32..160, y -64..64, z 96..128; height 112."""
    model = struct.pack("<9f7i", 32.0, -64.0, 96.0, 160.0, 64.0, 128.0,
                        0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
    ent = b'{\n"classname" "func_plat"\n"model" "*1"\n"height" "112"\n'
    if targeted:
        ent += b'"targetname" "t1"\n'
    return ent + b"}\n", model


class PlatBothEnds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "plat.bsp"
        write_air_fixture(cls.path, *plat())
        cls.bsp, cls.frags, _ = nm.load_mesh(cls.path)
        cls.mvs = nm.movers(cls.bsp)
        cls.recs = nm.mover_ledges(cls.bsp, cls.frags, cls.mvs)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_both_ends_of_the_travel(self):
        self.assertEqual(len(self.mvs), 1)
        mv = self.mvs[0]
        self.assertEqual((mv["cls"], mv["model"], mv["spawn"], mv["rest"], mv["trigger"]),
                         ("func_plat", "*1", "bottom", "bottom", "touch"))
        by = {s["name"]: s for s in mv["states"]}
        self.assertEqual((by["top"]["mins"], by["top"]["maxs"]),
                         ((32.0, -64.0, 96.0), (160.0, 64.0, 128.0)))
        self.assertEqual((by["bottom"]["mins"], by["bottom"]["maxs"]),
                         ((32.0, -64.0, -16.0), (160.0, 64.0, 16.0)))
        T = 112.0 / 150.0
        self.assertAlmostEqual(mv["travel"], T)
        self.assertAlmostEqual(mv["period"], 2 * T + 3.0)
        self.assertEqual(by["top"]["present"], [(T, T + 3.0)])
        self.assertEqual(by["bottom"]["present"], [(2 * T + 3.0, None)])
        self.assertEqual(by["top"]["deck"][0], (16.0, -80.0, 152.0))
        # the spawn state is where brush_boxes has always put it
        self.assertEqual([(b[1], b[2]) for b in nm.brush_boxes(self.bsp)],
                         [(by["bottom"]["mins"], by["bottom"]["maxs"])])

    def test_a_targeted_plat_waits_at_the_top(self):
        path = Path(self.tmp.name) / "plat_t.bsp"
        write_air_fixture(path, *plat(targeted=True))
        mv = nm.movers(nm.Bsp(path))[0]
        self.assertEqual((mv["spawn"], mv["trigger"]), ("top", "targeted"))

    def front(self):
        return [b for b in self.recs[0]["beside"]
                if abs(b["pos"][0] - 16.0) < 0.5 and abs(b["pos"][1]) <= 40.0]

    def test_a_ledge_in_front_is_bridged_at_the_top_and_lethal_at_the_bottom(self):
        front = self.front()
        self.assertTrue(front)
        for b in front:
            self.assertEqual(b["verdicts"]["top"], "bridged")
        centre = [b for b in front if abs(b["pos"][1]) <= 16.0]
        self.assertTrue(centre)
        for b in centre:
            # a walk lands on the deck at the bottom, a run overshoots it into the lava
            self.assertEqual(b["verdicts"]["bottom"], "danger")
            self.assertTrue(b["on"]["bottom"])
        self.assertGreaterEqual(self.recs[0]["changed"], len(front))

    def test_the_deck_has_its_own_ledges_in_each_state(self):
        deck = self.recs[0]["deck"]
        # at the top it is a floor level with the platform, so its west edge
        # is a walk; off the north and south edges over the strip is lava,
        # and off the east edge only a straight drop is (a run clears it)
        self.assertTrue(deck["top"])
        self.assertTrue(all(s["pos"][0] > 16.5 for s in deck["top"]))
        self.assertTrue({"danger", "momentum"} <= {s["verdict"] for s in deck["top"]})
        # at the bottom it stands 16u over the floor under the lava, within a
        # step on every side: a wade the floor mesh already drops, no ledge
        self.assertEqual(deck["bottom"], [])

    def test_air_report_lists_both_states(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(nm.main([str(self.path), "--air"]), 0)
        text = out.getvalue()
        self.assertIn("movers: 1 in deathmatch (1 plat, 0 doors, 0 trains)", text)
        self.assertIn("*1 func_plat, touch: bottom (spawn, rest); top (3.0 s of each 4.5 s cycle)",
                      text)
        self.assertIn("bottom: danger", text)
        self.assertIn("top: bridged", text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            nm.main([str(self.path), "--air", "--no-movers"])
        self.assertNotIn("movers:", out.getvalue())


def stub(ents, size=(64.0, 16.0, 64.0)):
    b = type("B", (), {})()
    b.models = [None, (0.0, 0.0, 0.0, *size)]
    b.entities = lambda: ents
    return b


class Timing(unittest.TestCase):
    """doors.qc, plats.qc and SUB_CalcMove arithmetic on stub entity lists."""

    def test_door_cycle(self):
        mv = nm.movers(stub([{"classname": "func_door", "model": "*1", "angle": "0",
                              "speed": "50", "wait": "2"}]))[0]
        by = {s["name"]: s for s in mv["states"]}
        T = 56.0 / 50.0                       # size 64 less the default lip 8
        self.assertEqual((mv["spawn"], mv["rest"], mv["trigger"]), ("shut", "shut", "touch"))
        self.assertEqual(by["open"]["mins"], (56.0, 0.0, 0.0))
        self.assertAlmostEqual(mv["period"], 2 * T + 2.0)
        self.assertEqual(by["open"]["present"], [(T, T + 2.0)])

    def test_start_open_runs_in_reverse(self):
        mv = nm.movers(stub([{"classname": "func_door", "model": "*1", "angle": "0",
                              "spawnflags": "1", "targetname": "t"}]))[0]
        by = {s["name"]: s for s in mv["states"]}
        self.assertEqual((mv["spawn"], mv["trigger"]), ("open", "targeted"))
        self.assertEqual(by["open"]["mins"], (56.0, 0.0, 0.0))
        self.assertEqual(by["shut"]["mins"], (0.0, 0.0, 0.0))
        self.assertEqual(by["shut"]["dwell"], 3.0)
        # and it agrees with the spawn box the air layer already used
        self.assertEqual(nm.brush_boxes(stub([{"classname": "func_door", "model": "*1",
                                               "angle": "0", "spawnflags": "1"}]))[0][1],
                         by["open"]["mins"])

    def test_doors_that_never_come_back(self):
        for flags in ("8", "16", "32"):
            mv = nm.movers(stub([{"classname": "func_door", "model": "*1", "angle": "-2",
                                  "spawnflags": flags}]))[0]
            by = {s["name"]: s for s in mv["states"]}
            self.assertIsNone(mv["period"], flags)
            self.assertIsNone(by["open"]["dwell"], flags)
            self.assertEqual(by["open"]["mins"], (0.0, 0.0, -56.0))   # -2 is DOWN
            self.assertEqual(by["open"]["present"][0][1], None)

    def test_secret_doors_and_deathmatch_removals_are_not_movers(self):
        self.assertEqual(nm.movers(stub([
            {"classname": "func_door_secret", "model": "*1"},
            {"classname": "func_door", "model": "*1", "spawnflags": "2048"},
            {"classname": "func_wall", "model": "*1"}])), [])

    def test_train_laps_its_corners(self):
        ents = [{"classname": "func_train", "model": "*1", "target": "a", "speed": "50"},
                {"classname": "path_corner", "targetname": "a", "target": "b",
                 "origin": "0 0 0", "wait": "2"},
                {"classname": "path_corner", "targetname": "b", "target": "a",
                 "origin": "100 0 0"}]
        mv = nm.movers(stub(ents))[0]
        by = {s["name"]: s for s in mv["states"]}
        self.assertEqual((mv["spawn"], mv["rest"], mv["trigger"]), ("corner a", None, "auto"))
        self.assertEqual(by["corner b"]["mins"], (100.0, 0.0, 0.0))
        self.assertEqual(by["corner b"]["maxs"], (164.0, 16.0, 64.0))
        # leave a at 0.1, 2 s to b, b holds the 0.1 s think, 2 s back, a holds 2
        self.assertAlmostEqual(mv["period"], 6.1)
        self.assertEqual(len(by["corner a"]["present"]), 1)
        self.assertAlmostEqual(by["corner a"]["present"][0][0], 4.2)
        self.assertAlmostEqual(by["corner b"]["present"][0][0], 2.1)
        self.assertAlmostEqual(by["corner b"]["present"][0][1], 2.2)

    def test_a_short_move_still_takes_sub_calcmoves_tenth(self):
        self.assertEqual(nm._leg(1.0, 100.0), 0.1)
        self.assertTrue(math.isclose(nm._leg(300.0, 100.0), 3.0))


if __name__ == "__main__":
    unittest.main()
