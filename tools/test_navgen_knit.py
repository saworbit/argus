#!/usr/bin/env python3
"""navgen's last-resort knit stitches (#623, #624), on built maps.

Each fixture is a handful of axis-aligned boxes compiled into hull 0 (with
water) and hull 1 (the player box, liquids empty), the way qbsp does it.

The pool: a dry mainland (floor 0) west of x 0, a deep basin (floor -520)
from x 0 to 288 and a submerged shelf (floor -64) from 288 to 576, under
water up to z -8. Nothing walks, drops or jumps between the three, the
basin is too deep for 7d's surface probe, and the old dive stops at 500u,
so before the stitches the poison prune ate the basin and the shelf. The
swim stitch joins basin and shelf through the water and the bank stitch
walks the mainland into it.

The ledge: a 128u pillar on a flat floor under a ceiling that leaves no
room for the jump stitch's arc. Its only way down is a fall longer than
DROPMAX. The deep-drop stitch keeps it when a pickup stands on it, and
not when nothing does or when the fall is past KNIT_DEEP_DROP.
"""
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EMPTY, SOLID, WATER = -1, -2, -3
# hull 1 is the player box, mins -16 -16 -24, maxs 16 16 32: a solid box
# grows by maxs below and by -mins above, so an origin inside the grown box
# puts some part of the player inside the brush
HULL1_GROW_LO = (16.0, 16.0, 32.0)
HULL1_GROW_HI = (16.0, 16.0, 24.0)


def _content(boxes, p):
    found = EMPTY
    for mn, mx, c in boxes:
        if all(mn[k] < p[k] < mx[k] for k in range(3)):
            if c == SOLID:
                return SOLID
            found = c
    return found


def _tree(boxes, lo, hi, plane, out):
    """Split the region on box faces until every box contains or misses it.

    out collects (plane, front, back) in pre-order, so the root is 0. A
    child is a node index or a content code, which is also the hull-0 leaf
    child for the three leaves this fixture writes (-1, -2, -3).
    """
    for mn, mx, _c in boxes:
        for axis in range(3):
            if not all(mn[k] < hi[k] and mx[k] > lo[k] for k in range(3) if k != axis):
                continue
            for v in (mn[axis], mx[axis]):
                if lo[axis] < v < hi[axis]:
                    index = len(out)
                    out.append(None)
                    front_lo, back_hi = list(lo), list(hi)
                    front_lo[axis] = back_hi[axis] = v
                    front = _tree(boxes, front_lo, hi, plane, out)
                    back = _tree(boxes, lo, back_hi, plane, out)
                    out[index] = (plane(axis, v), front, back)
                    return index
    return _content(boxes, [(lo[k] + hi[k]) / 2 for k in range(3)])


def write_bsp(path, boxes, mins, maxs, entities=()):
    rows, index = [], {}

    def plane(axis, dist):
        key = (axis, float(dist))
        if key not in index:
            index[key] = len(rows)
            normal = [0.0, 0.0, 0.0]
            normal[axis] = 1.0
            rows.append((*normal, float(dist), axis))
        return index[key]

    h0 = []
    _tree(boxes, list(mins), list(maxs), plane, h0)
    grown = [([mn[k] - HULL1_GROW_LO[k] for k in range(3)],
              [mx[k] + HULL1_GROW_HI[k] for k in range(3)], SOLID)
             for mn, mx, c in boxes if c == SOLID]
    h1 = []
    _tree(grown, list(mins), list(maxs), plane, h1)
    lo = [max(-32767, int(v)) for v in mins]
    hi = [min(32767, int(v)) for v in maxs]
    nodes = b"".join(struct.pack("<i8h2H", p, f, b, *lo, *hi, 0, 0) for p, f, b in h0)
    clip = b"".join(struct.pack("<ihh", p, f, b) for p, f, b in h1)
    leaves = b"".join(struct.pack("<2i6h2H4B", c, -1, *lo, *hi, 0, 0, 0, 0, 0, 0)
                      for c in (EMPTY, SOLID, WATER))
    planes = b"".join(struct.pack("<ffffi", *r) for r in rows)
    models = struct.pack("<9f7i", *mins, *maxs, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
    text = '{\n"classname" "worldspawn"\n}\n'
    for e in entities:
        text += "{\n" + "".join(f'"{k}" "{v}"\n' for k, v in e.items()) + "}\n"
    table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
    for idx, payload in ((0, text.encode("ascii") + b"\0"), (1, planes), (5, nodes),
                         (9, clip), (10, leaves), (14, models)):
        table[idx] = (base + len(blob), len(payload))
        blob += payload
    path.write_bytes(struct.pack("<i", 29)
                     + b"".join(struct.pack("<ii", o, n) for o, n in table) + blob)


def regen(tmp):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "argus_navgen.py"),
         str(tmp / "fixture.bsp"), "fixture", str(tmp / "argus_nav_fixture.qc"),
         str(tmp / "out.png"), "--no-dispatcher", "--no-rj"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300)


def graph(tmp):
    doc = json.loads((tmp / "argus_nav_fixture.qc.json").read_text())
    nodes = [tuple(n) for n in doc["nodes"]]
    edges = set()
    for family in ("links", "jlinks", "swimlinks", "doorlinks"):
        edges |= {(a, b) for a, b, *_ in doc.get(family, [])}
    return nodes, edges, doc


def reach(edges, start):
    seen, todo = {start}, [start]
    while todo:
        u = todo.pop()
        for a, b in edges:
            if a == u and b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


class SwimAndBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory(prefix="argus-knit-pool-")
        cls.tmp = Path(cls.dir.name)
        y0, y1, floor = -48.0, 48.0, -640.0
        write_bsp(cls.tmp / "fixture.bsp", [
            ([-512.0, y0, floor], [0.0, y1, 0.0], SOLID),       # mainland
            ([0.0, y0, floor], [288.0, y1, -520.0], SOLID),     # basin floor
            ([288.0, y0, floor], [576.0, y1, -64.0], SOLID),    # shelf
            ([0.0, y0, floor], [576.0, y1, -8.0], WATER),
        ], (-512.0, y0, floor), (576.0, y1, 128.0))
        cls.res = regen(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_basin_and_shelf_survive_and_join_the_mainland(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr + self.res.stdout)
        self.assertIn("knit swim ", self.res.stdout)
        self.assertIn("knit bank ", self.res.stdout)
        self.assertNotIn("route-poison prune", self.res.stdout)
        nodes, edges, _ = graph(self.tmp)
        basin = [i for i, n in enumerate(nodes) if n[2] < -400]
        shelf = [i for i, n in enumerate(nodes) if -60 < n[2] < -20]
        land = [i for i, n in enumerate(nodes) if n[2] > 0]
        self.assertTrue(basin and shelf and land, nodes)
        everyone = set(range(len(nodes)))
        for start in (basin[0], shelf[0], land[0]):
            self.assertEqual(reach(edges, start), everyone,
                             f"n{start} does not reach the whole pool")

    def test_a_swim_link_climbs_out_onto_the_bank(self):
        nodes, _, doc = graph(self.tmp)
        out = [(a, b) for a, b, *_ in doc.get("swimlinks", [])
               if nodes[a][2] < 0 < nodes[b][2]]
        self.assertTrue(out, doc.get("swimlinks"))


class DeepDrop(unittest.TestCase):
    def build(self, height, item):
        tmp = Path(self.dir.name) / f"h{height}-{int(item)}"
        tmp.mkdir()
        entities = [{"classname": "item_health", "origin": f"0 0 {height}"}] if item else []
        write_bsp(tmp / "fixture.bsp", [
            ([-384.0, -384.0, -64.0], [384.0, 384.0, 0.0], SOLID),
            ([-64.0, -64.0, 0.0], [64.0, 64.0, float(height)], SOLID),
            # 64u over the ledge: room to stand, none for a jump's arc
            ([-384.0, -384.0, height + 64.0], [384.0, 384.0, height + 160.0], SOLID),
        ], (-384.0, -384.0, -64.0), (384.0, 384.0, height + 160.0), entities)
        return tmp, regen(tmp)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="argus-knit-ledge-")

    def tearDown(self):
        self.dir.cleanup()

    def test_a_ledge_holding_a_pickup_keeps_its_fall(self):
        tmp, res = self.build(220, True)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("knit deep drop ", res.stdout)
        nodes, edges, _ = graph(tmp)
        ledge = [i for i, n in enumerate(nodes) if n[2] > 200]
        self.assertTrue(ledge, nodes)
        self.assertTrue(any(a in ledge and nodes[b][2] < 40 for a, b in edges))

    def test_a_bare_ledge_or_a_longer_fall_is_pruned(self):
        for height, item in ((220, False), (260, True)):
            tmp, res = self.build(height, item)
            self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
            self.assertNotIn("knit deep drop ", res.stdout, (height, item))
            nodes, _, _ = graph(tmp)
            self.assertFalse([n for n in nodes if n[2] > 200], (height, item))


if __name__ == "__main__":
    unittest.main()
