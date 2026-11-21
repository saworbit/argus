#!/usr/bin/env python3
"""argus_bsp is the one Python BSP29 reader (#814).

Five tools used to read the BSP header for themselves. Two checked the
version with an assert, which python -O strips, one with sys.exit and
one with SystemExit. Every reader now refuses a file that is not BSP29
with the same ValueError, under -O as well, and these tests hold that
against a small built fixture.
"""
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import argus_bsp  # noqa: E402 - tools path set just above
from analyze_match import death_is_lava  # noqa: E402


class DeathClassification(unittest.TestCase):
    def test_shared_native_cases(self):
        cases = json.loads((HERE / 'testdata/lava_death_cases.json').read_text(encoding='utf-8'))
        for case in cases:
            with self.subTest(case=case['name']):
                hull = case['hull']
                contents = None if hull is None else lambda x, y, z: hull[1] if z >= hull[0] else hull[2]
                self.assertEqual(death_is_lava(contents, 0, 0, case['z']), case['lava'])


def write_bsp(path, version=29):
    """A world floor at z 0 with a pool of water east of x 256 up to z 600."""
    planes = b"".join(struct.pack("<ffffi", *row) for row in (
        (0.0, 0.0, 1.0, 0.0, 2),      # p0 world floor
        (0.0, 0.0, 1.0, 24.0, 2),     # p1 hull-1 floor, the origin height
        (1.0, 0.0, 0.0, 256.0, 0),    # p2 pool west edge
        (0.0, 0.0, 1.0, 600.0, 2),    # p3 pool surface
    ))
    # hull 0: solid below z 0, water east of x 256 below z 600.
    # Child -1 is leaf 0 (empty), -2 leaf 1 (solid), -3 leaf 2 (water).
    h0tree = ((0, 1, -2), (2, 2, -1), (3, -1, -3))
    nodes = b"".join(
        struct.pack("<i8h2H", p, c0, c1, -512, -512, -64, 512, 512, 640, 0, 0)
        for p, c0, c1 in h0tree)
    leaves = b"".join(
        struct.pack("<2i6h2H4B", content, -1, -512, -512, -64, 512, 512, 640,
                    0, 0, 0, 0, 0, 0)
        for content in (-1, -2, -3))
    # hull 1 collapses liquids to empty, exactly as qbsp does
    clipnodes = struct.pack("<ihh", 1, -1, -2)
    models = (struct.pack("<9f7i", -512.0, -512.0, -64.0, 512.0, 512.0, 640.0,
                          0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0)
              + struct.pack("<9f7i", 64.0, 0.0, 0.0, 128.0, 16.0, 64.0,
                            0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0))
    vertexes = struct.pack("<6f", 0.0, 0.0, 0.0, 64.0, 0.0, 0.0)
    edges = struct.pack("<4H", 0, 0, 0, 1)
    ents = (b'{\n"classname" "worldspawn"\n}\n'
            b'{\n"classname" "info_player_deathmatch"\n"origin" "0 0 24"\n}\n'
            b'{\n"classname" "func_door"\n"model" "*1"\n}\n\0')
    table, blob, base = [(0, 0)] * 15, b"", 4 + 15 * 8
    for idx, payload in ((0, ents), (1, planes), (3, vertexes), (5, nodes),
                         (9, clipnodes), (10, leaves), (12, edges), (14, models)):
        table[idx] = (base + len(blob), len(payload))
        blob += payload
    path.write_bytes(struct.pack("<i", version)
                     + b"".join(struct.pack("<ii", o, n) for o, n in table) + blob)
    return path


# Runs in a child interpreter so the parent can pass -O. Each loader is
# one the issue names; BaseException because sys.exit and SystemExit
# were among the refusals this replaced.
DRIVER = r'''
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
import analyze_match, argus_bsp, argus_navmesh, argus_pointfile, argus_reach
bsp = Path(sys.argv[2])
calls = (
    ("analyze_match", lambda: analyze_match.load_bsp(bsp)),
    ("argus_bsp", lambda: argus_bsp.load_classifier(bsp)),
    ("argus_navmesh", lambda: argus_navmesh.load_mesh(bsp)),
    ("argus_pointfile", lambda: argus_pointfile.Bsp(bsp)),
    ("argus_reach", lambda: argus_reach.bsp_spawns(bsp)),
)
print("optimize", sys.flags.optimize)
for name, call in calls:
    try:
        call()
    except BaseException as error:
        print(name, type(error).__name__ + ":", error)
    else:
        print(name, "accepted")
'''
LOADERS = ("analyze_match", "argus_bsp", "argus_navmesh", "argus_pointfile",
           "argus_reach")


class Reader(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.path = write_bsp(self.tmp / "fixture.bsp")
        self.bsp = argus_bsp.Bsp(self.path)

    def test_tables_decode_from_the_lumps(self):
        b = self.bsp
        self.assertEqual(b.version, 29)
        self.assertEqual(b.planes[0], (0.0, 0.0, 1.0, 0.0))
        self.assertEqual(len(b.planes), 4)
        self.assertEqual(len(b.models), 2)
        self.assertEqual(b.mins, (-512.0, -512.0, -64.0))
        self.assertEqual(b.maxs, (512.0, 512.0, 640.0))
        self.assertEqual((b.hull0, b.hull1), (0, 0))
        self.assertEqual(b.entities(), [
            {"classname": "worldspawn"},
            {"classname": "info_player_deathmatch", "origin": "0 0 24"},
            {"classname": "func_door", "model": "*1"},
        ])

    def test_hull0_sees_liquid_and_hull1_does_not(self):
        b = self.bsp
        self.assertEqual(b.h0(0, 0, 10), argus_bsp.CONTENTS_EMPTY)
        self.assertEqual(b.h0(0, 0, -10), argus_bsp.CONTENTS_SOLID)
        self.assertEqual(b.h0(300, 0, 10), argus_bsp.CONTENTS_WATER)
        self.assertEqual(b.h0(300, 0, 610), argus_bsp.CONTENTS_EMPTY)
        self.assertEqual(b.h1(300, 0, 30), argus_bsp.CONTENTS_EMPTY)
        self.assertEqual(b.h1(0, 0, 10), argus_bsp.CONTENTS_SOLID)
        self.assertEqual(argus_bsp.load_classifier(self.path)(300, 0, 10),
                         argus_bsp.CONTENTS_WATER)

    def test_check_bottom_forgives_a_step_and_no_more(self):
        b = self.bsp
        self.assertTrue(b.check_bottom(0, 0, 24))     # standing on the floor
        self.assertTrue(b.check_bottom(0, 0, 30))     # 6u up, within a step
        self.assertFalse(b.check_bottom(0, 0, 64))    # 40u up, past two steps

    def test_water_top_stops_at_navgen_ceiling(self):
        # 320u is navgen's ceiling and the one kept: a deep pool reads
        # its surface 320u above the probe, a shallow one where it is
        self.assertEqual(argus_bsp.WATER_TOP_REACH, 320)
        self.assertEqual(self.bsp.water_top(300, 0, 24), 344)
        self.assertEqual(self.bsp.water_top(300, 0, 400), 592)

    def test_wireframe_inputs(self):
        verts, edges, mins, maxs = argus_bsp.load_bsp(self.path)
        self.assertEqual(verts, [(0.0, 0.0, 0.0), (64.0, 0.0, 0.0)])
        self.assertEqual(edges, [(0, 0), (0, 1)])
        self.assertEqual((mins, maxs), (self.bsp.mins, self.bsp.maxs))

    def test_refusals_are_value_errors(self):
        short = self.tmp / "short.bsp"
        short.write_bytes(struct.pack("<i", 29))
        with self.assertRaisesRegex(ValueError, "too small for a BSP29 header"):
            argus_bsp.Bsp(short)
        other = write_bsp(self.tmp / "other.bsp", version=30)
        with self.assertRaisesRegex(ValueError, "BSP version 30, expected 29"):
            argus_bsp.Bsp(other)
        bad = self.tmp / "bad.bsp"
        data = bytearray(self.path.read_bytes())
        struct.pack_into("<ii", data, 4 + 14 * 8, len(data), 64)
        bad.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, "invalid models lump"):
            argus_bsp.Bsp(bad)
        with self.assertRaises(OSError):
            argus_bsp.Bsp(self.tmp / "missing.bsp")


class SameRefusalEverywhere(unittest.TestCase):
    """Acceptance (2) of #814: one ValueError from every reader, with or without -O."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.good = write_bsp(self.tmp / "good.bsp")
        self.other = write_bsp(self.tmp / "other.bsp", version=30)
        self.expected = f"ValueError: {self.other}: BSP version 30, expected 29"

    def drive(self, flags, path):
        res = subprocess.run([sys.executable, *flags, "-c", DRIVER, str(HERE), str(path)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        lines = res.stdout.splitlines()
        self.assertEqual(lines[0], f"optimize {1 if flags else 0}")
        return dict(line.split(" ", 1) for line in lines[1:])

    def test_library_readers(self):
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                # the control proves each loader opens a real BSP29 file,
                # so the refusal below cannot pass by refusing everything
                self.assertEqual(self.drive(flags, self.good),
                                 {name: "accepted" for name in LOADERS})
                self.assertEqual(self.drive(flags, self.other),
                                 {name: self.expected for name in LOADERS})

    def test_navgen(self):
        qc = self.tmp / "argus_nav_fixture.qc"
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                res = subprocess.run(
                    [sys.executable, *flags, str(HERE / "argus_navgen.py"), str(self.other),
                     "fixture", str(qc), str(self.tmp / "out.png"), "--no-dispatcher"],
                    capture_output=True, text=True, timeout=120)
                self.assertNotEqual(res.returncode, 0, res.stdout)
                self.assertEqual(res.stderr.strip().splitlines()[-1], self.expected)
                self.assertFalse(qc.exists())


if __name__ == "__main__":
    unittest.main()
