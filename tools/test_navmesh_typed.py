#!/usr/bin/env python3
"""The mesh-native typed-link finder (#790) on built maps.

The main fixture is a row of floating platforms over a pit 512u deep,
far past any legal fall, so a gap can only be crossed in the air. Every
platform top is at z 0, a standing origin at z 24:

    P1   x -512..0      with a 32u block at x -384..-256 and a 64u
                        block at x -192..-128 on it
    gap  x 0..128       a running jump clears it
    P2   x 128..384     a trigger_teleport stands at its east end
    gap  x 384..768     no jump at 320 u/s clears it
    P3   x 768..1024    the teleporter's destination
    L    x 1024..1120   a shelf at z -232, too deep to drop to
    F    x 1120..1600   a floor at z -128 a run off P3 lands on

Hull 1 carries every floor 16u past its brush, so the hull-1 gaps are
96u and 352u. The drop and lift checks reuse the air layer's lava-strip
fixture and a stub entity lump.
"""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import argus_navmesh as nm  # noqa: E402
import argus_navmesh_graph as g  # noqa: E402
import argus_navmesh_typed as nt  # noqa: E402
from argus_nav_artifacts import validate_pair  # noqa: E402
from test_navmesh_air import write_fixture as write_lava_strip  # noqa: E402

EMPTY, SOLID, LAVA = -1, -2, -5
WORLD = ((-4096.0, -4096.0, -4096.0), (4096.0, 4096.0, 4096.0))
Y = (-128.0, 128.0)
BOXES = (
    ((-512.0, Y[0], -64.0), (0.0, Y[1], 0.0)),        # P1
    ((-384.0, Y[0], 0.0), (-256.0, Y[1], 32.0)),      # 32u block
    ((-192.0, Y[0], 0.0), (-128.0, Y[1], 64.0)),      # 64u block
    ((128.0, Y[0], -64.0), (384.0, Y[1], 0.0)),       # P2
    ((768.0, Y[0], -64.0), (1024.0, Y[1], 0.0)),      # P3
    ((1024.0, Y[0], -300.0), (1120.0, Y[1], -232.0)),  # shelf L
    ((1120.0, Y[0], -400.0), (1600.0, Y[1], -128.0)),  # floor F
    ((-512.0, Y[0], -560.0), (1600.0, Y[1], -512.0)),  # the pit floor
)
TRIGGER = ((320.0, -32.0, 0.0), (384.0, 32.0, 64.0))
DEST = (900.0, 0.0, 40.0)


def _tree(region, boxes, node, leaf, plane):
    """Split region on box faces until each piece is inside one box or none."""
    inside = [b for b in boxes
              if all(b[0][k] < region[1][k] and b[1][k] > region[0][k] for k in range(3))]
    if not inside:
        return leaf(EMPTY)
    for mn, mx, c in sorted(inside, key=lambda b: b[2] != SOLID):
        if all(mn[k] <= region[0][k] and mx[k] >= region[1][k] for k in range(3)):
            return leaf(c)
    for mn, mx, _ in inside:
        for k in range(3):
            for d in (mn[k], mx[k]):
                if region[0][k] < d < region[1][k]:
                    hi = (tuple(d if i == k else region[0][i] for i in range(3)), region[1])
                    lo = (region[0], tuple(d if i == k else region[1][i] for i in range(3)))
                    return node(plane(k, d), _tree(hi, boxes, node, leaf, plane),
                                _tree(lo, boxes, node, leaf, plane))
    raise AssertionError("a box overlaps the region but has no face inside it")


def write_boxes(path, solids, lavas=(), ents=b"", models=()):
    """A BSP29 file whose hull 0 and hull 1 hold axis-aligned boxes.

    Hull 1 grows every solid by the player box (16 either side, 32 below
    the box and 24 above it, in origin space) and, like qbsp, leaves
    liquids out.
    """
    planes, index = [], {}

    def plane(k, d):
        if (k, d) not in index:
            index[(k, d)] = len(planes)
            n = [0.0, 0.0, 0.0]
            n[k] = 1.0
            planes.append(struct.pack("<ffffi", *n, d, k))
        return index[(k, d)]
    h0nodes, leaves = [], []

    def h0node(p, front, back):
        h0nodes.append((p, front, back))
        return len(h0nodes) - 1

    def h0leaf(c):
        leaves.append(c)
        return -len(leaves)
    clip = []

    def h1node(p, front, back):
        clip.append((p, front, back))
        return len(clip) - 1
    boxes0 = [(mn, mx, SOLID) for mn, mx in solids] + [(mn, mx, LAVA) for mn, mx in lavas]
    boxes1 = [((mn[0] - 16, mn[1] - 16, mn[2] - 32), (mx[0] + 16, mx[1] + 16, mx[2] + 24), SOLID)
              for mn, mx in solids]
    # _tree numbers a node after its children, so each root is the last
    # node it made; the world model's head nodes say where each one is
    root0 = _tree(WORLD, boxes0, h0node, h0leaf, plane)
    root1 = _tree(WORLD, boxes1, h1node, lambda c: c, plane)
    blob_nodes = b"".join(struct.pack("<i8h2H", p, f, b, -4096, -4096, -4096, 4096, 4096, 4096, 0, 0)
                          for p, f, b in h0nodes)
    blob_leaves = b"".join(struct.pack("<2i6h2H4B", c, -1, -4096, -4096, -4096, 4096, 4096, 4096,
                                       0, 0, 0, 0, 0, 0) for c in leaves)
    blob_clip = b"".join(struct.pack("<ihh", p, f, b) for p, f, b in clip)
    world = struct.pack("<9f7i", -1024.0, -512.0, -600.0, 1700.0, 512.0, 256.0,
                        0.0, 0.0, 0.0, root0, root1, root1, 0, 0, 0, 0)
    extra = b"".join(struct.pack("<9f7i", *mn, *mx, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
                     for mn, mx in models)
    lump = b'{\n"classname" "worldspawn"\n}\n' + ents + b"\0"
    table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
    for idx, payload in ((0, lump), (1, b"".join(planes)), (5, blob_nodes),
                         (9, blob_clip), (10, blob_leaves), (14, world + extra)):
        table[idx] = (base + len(blob), len(payload))
        blob += payload
    Path(path).write_bytes(struct.pack("<i", 29)
                           + b"".join(struct.pack("<ii", o, n) for o, n in table) + blob)


def context(bsp_path):
    bsp, frags, _ = nm.load_mesh(bsp_path)
    mi = g.MeshIndex(frags)
    tboxes = g.teleport_boxes(bsp)
    ctx = nt.Context(bsp=bsp, world=nm.WithBrushes(bsp, nm.brush_boxes(bsp)), frags=frags,
                     floors=mi.floors, locate=mi.locate,
                     walk=lambda a, b: g.walk(bsp, mi, a, b, tboxes),
                     gravity=nm.map_gravity(bsp_path), tboxes=tboxes)
    return bsp, frags, ctx


def write_platforms(path):
    ents = (b'{\n"classname" "info_player_deathmatch"\n"origin" "-448 0 24"\n}\n'
            b'{\n"classname" "trigger_teleport"\n"model" "*1"\n"target" "t1"\n}\n'
            b'{\n"classname" "info_teleport_destination"\n"targetname" "t1"\n'
            + f'"origin" "{DEST[0]:.0f} {DEST[1]:.0f} {DEST[2]:.0f}"\n}}\n'.encode("ascii"))
    write_boxes(path, BOXES, ents=ents, models=[TRIGGER])


class Platforms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "platforms.bsp"
        write_platforms(cls.path)
        cls.bsp, cls.frags, cls.ctx = context(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_fixture_reads_as_built(self):
        self.assertEqual(self.bsp.h0(-100, 0, -10), SOLID)
        self.assertEqual(self.bsp.h0(64, 0, -10), EMPTY)
        self.assertEqual(self.bsp.h1(8, 0, 20), SOLID)       # P1 grown 16u east
        self.assertEqual(self.bsp.h1(24, 0, 20), EMPTY)
        self.assertEqual(self.bsp.h1(8, 0, 24), EMPTY)       # a standing origin is empty
        self.assertEqual(self.ctx.floor_near(-100, 0, 24), 24.0)
        self.assertIsNone(self.ctx.floor_near(64, 0, 24))

    def test_a_running_jump_clears_the_narrow_gap(self):
        a, b = (-96.0, 0.0, 24.0), (224.0, 0.0, 24.0)
        self.assertIsNone(self.ctx.walk(a, b))
        prof = nt.jump_profile(self.ctx, a, b)
        self.assertIsNotNone(prof)
        # the probe fires 32u short of the hull-0 lip at x 0
        self.assertAlmostEqual(prof["launch"][0], -32.0, delta=3.0)
        self.assertLess(nt.launch_distance(a, prof["launch"]), nt.ANCHOR)
        # 142u to the far floor at 270 up: about 211 u/s is the least
        # that lands, so the first whole window starts a notch above it
        self.assertTrue(210 <= prof["speed"] <= 240, prof)
        self.assertGreaterEqual(prof["margin"], 2.0)
        self.assertGreater(prof["landing"][0], 112.0)

    def test_no_jump_clears_the_wide_gap(self):
        a, b = (300.0, 0.0, 24.0), (850.0, 0.0, 24.0)
        self.assertIsNone(nt.jump_profile(self.ctx, a, b))
        self.assertIsNone(nt.jump_profile(self.ctx, (330.0, 0.0, 24.0), (800.0, 0.0, 24.0)))

    def test_a_launch_past_the_anchor_is_refused(self):
        # from x -160 the probe fires 128u out: past the 96u anchor (#665)
        self.assertIsNone(nt.jump_profile(self.ctx, (-160.0, 64.0, 24.0), (256.0, 64.0, 24.0)))

    def test_a_climb_goes_up_32_and_not_64(self):
        self.assertTrue(nt.climb_ok(self.ctx, (-448.0, 0.0, 24.0), (-360.0, 0.0, 56.0)))
        # 80u past the face: the bot meets the face before it is within 72u
        self.assertFalse(nt.climb_ok(self.ctx, (-448.0, 0.0, 24.0), (-320.0, 0.0, 56.0)))
        self.assertFalse(nt.climb_ok(self.ctx, (-224.0, 0.0, 24.0), (-160.0, 0.0, 88.0)))
        self.assertFalse(nt.climb_ok(self.ctx, (-96.0, 0.0, 24.0), (224.0, 0.0, 56.0)))

    def test_a_run_off_lands_where_straight_down_cannot(self):
        a, b = (1000.0, 0.0, 24.0), (1300.0, 0.0, -104.0)
        self.assertIsNone(self.ctx.walk(a, b))
        arc = nt.drop_arc(self.ctx, a, b)
        self.assertIsNotNone(arc)
        for land in arc["landings"]:
            self.assertGreater(land[0], 1104.0)
            self.assertAlmostEqual(land[2], -104.0, delta=1.0)
        # straight down from the lip is the shelf, 256u below the origin
        self.assertEqual(nt.guard_floor(self.bsp, 1040.0, 0.0, 24.0), "floor")
        # and no arc is found off the far side of the wide gap
        self.assertIsNone(nt.drop_arc(self.ctx, (1000.0, 0.0, 24.0), (1300.0, 0.0, -488.0)))

    def test_the_teleporter_seats_inside_its_trigger(self):
        tele, refused = nt.teleporters(self.ctx)
        self.assertEqual(refused, [])
        self.assertEqual(len(tele), 1)
        src, dst, box = tele[0]
        self.assertTrue(g.in_box(src, box))
        self.assertAlmostEqual(src[0], 352.0, delta=8.0)
        self.assertEqual(src[2], 24.0)
        self.assertEqual(dst, (DEST[0], DEST[1], 24.0))    # origin + 27 falls to P3

    def test_gravity_scales_the_fall_and_the_climb(self):
        self.assertEqual(nt.drop_limit(800.0), 200.0)
        self.assertEqual(nt.drop_limit(100.0), 256.0)      # the guard's 280u trace
        self.assertEqual(nt.climb_limit(800.0), 44.0)
        self.assertLess(nt.climb_limit(1600.0), 22.0)


class NativeGraph(unittest.TestCase):
    """build(native=True) on the platforms, with no shipped graph at all."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        write_platforms(tmp / "platforms.bsp")
        cls.g = g.build("platforms", native=True, bsp_path=tmp / "platforms.bsp",
                        ship_path=tmp / "absent.qc.json")
        cls.qc = g.emit(cls.g, tmp / "out")
        cls.text = cls.qc.read_text(encoding="ascii")
        cls.doc = json.loads((tmp / "out" / "argus_nav_platforms.qc.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def where(self, i):
        x = self.doc["nodes"][i][0]
        return "P1" if x < 0 else "P2" if x < 400 else "P3" if x < 1030 else "F"

    def test_the_pair_validates(self):
        validate_pair(self.text, self.doc, tactics=False)
        self.assertIn("native typed links", self.text.splitlines()[0])
        self.assertEqual(self.doc["mesh_report"]["typed_source"], "native")

    def test_jumps_cross_the_narrow_gap_both_ways_and_never_the_wide_one(self):
        hops = {(self.where(a), self.where(b)) for a, b in self.doc["jlinks"]}
        self.assertIn(("P1", "P2"), hops)
        self.assertIn(("P2", "P1"), hops)
        self.assertFalse({("P2", "P3"), ("P3", "P2")} & hops)
        for row in self.doc["jumpapproach"]:
            self.assertEqual(len(row), 5)

    def test_the_teleporter_is_the_only_way_to_p3(self):
        teles = [(self.where(a), self.where(b)) for a, b in self.doc["teles"]]
        self.assertEqual(teles, [("P2", "P3")])
        self.assertFalse(self.doc["rjlinks"] or self.doc["sprintlinks"] or self.doc["swimlinks"])

    def test_the_run_off_reaches_the_lower_floor(self):
        down = {(self.where(a), self.where(b)) for a, b, _ in self.doc["links"]}
        self.assertIn(("P3", "F"), down)

    def test_no_node_has_more_than_eight_links(self):
        outs = {}
        for a, b in [tuple(r[:2]) for f in ("links", "jlinks", "teles", "liftlinks")
                     for r in self.doc[f]]:
            outs.setdefault(a, set()).add(b)
        self.assertLessEqual(max(len(v) for v in outs.values()), 8)

    def test_the_spawn_reaches_everything_but_the_pit_and_the_tall_block(self):
        reach = self.doc["mesh_report"]["assessment"]["reach"]
        # the pit floor and the top of the 64u block have no way in
        shut = sum(1 for p in self.doc["nodes"] if p[2] < -400 or p[2] > 80)
        self.assertGreater(shut, 0)
        self.assertEqual(reach["worst_all"], len(self.doc["nodes"]) - shut)
        self.assertEqual(reach["worst_all"], reach["worst_ungated"])


class LethalRunOff(unittest.TestCase):
    """The air layer's platform beside a lava strip: stepping off lands
    dry at the wall's foot, running off at 240 lands in the lava."""

    def test_a_straight_drop_with_a_lethal_run_off_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "strip.bsp"
            write_lava_strip(path)
            _, _, ctx = context(path)
            a, b = (-64.0, 0.0, 152.0), (40.0, 0.0, 24.0)
            self.assertEqual(ctx.walk(a, b), "drop")
            self.assertTrue(nt.drop_lands_lethal(ctx, a, b))
            self.assertFalse(nt.drop_lands_lethal(ctx, (-64.0, 0.0, 152.0), (-200.0, 0.0, 152.0)))


class LiftPads(unittest.TestCase):
    """navgen's 5b rules on a stub lump: a plat 64u square whose top is
    compiled at z 0 and whose seated face is 128 below it."""

    def ctx(self, ent):
        b = type("B", (), {})()
        b.models = [None, (-200.0, -32.0, -136.0, -136.0, 32.0, 0.0)]
        b.entities = lambda: [ent]
        return nt.Context(bsp=b, world=None, frags=[], floors=None, locate=None, walk=None)

    def test_pads_stand_outside_the_column_and_at_the_top(self):
        cands = [(-168.0, 0.0, -120.0),     # inside the swept column
                 (-240.0, 0.0, -120.0),     # 40u west of it, at the seated face
                 (-320.0, 0.0, -120.0),     # past the 96u ring
                 (-240.0, 0.0, -40.0),      # outside, but far above the face
                 (-168.0, 64.0, 24.0)]      # by the top
        out, refused = nt.lift_pads(self.ctx({"classname": "func_plat", "model": "*1"}), cands)
        self.assertEqual(refused, [])
        self.assertEqual(out, [((-240.0, 0.0, -120.0), (-168.0, 64.0, 24.0), (-168.0, 0.0, 0.0))])

    def test_the_height_key_moves_the_face(self):
        cands = [(-240.0, 0.0, -120.0), (-240.0, 0.0, -56.0), (-168.0, 64.0, 24.0)]
        out, _ = nt.lift_pads(self.ctx({"classname": "func_plat", "model": "*1",
                                        "height": "64"}), cands)
        self.assertEqual(out[0][0], (-240.0, 0.0, -56.0))

    def test_no_boarding_seat_is_a_refusal(self):
        out, refused = nt.lift_pads(self.ctx({"classname": "func_plat", "model": "*1"}),
                                    [(-168.0, 64.0, 24.0)])
        self.assertEqual(out, [])
        self.assertEqual(len(refused), 1)


if __name__ == "__main__":
    unittest.main()
