"""The one Python reader for Quake BSP29 files (#814).

Bsp checks the header once and refuses anything that is not BSP29 with a
ValueError, which, unlike an assert, still fires under python -O. It
slices lumps on demand and decodes each structure the first time
something asks for it, so a caller that wants only the entity lump never
parses the clip tree, and a test fixture that carries only the lumps it
needs still opens.

Every Python tool that reads a BSP goes through here: navgen, the navmesh
and its graph, the pointfile overlays, the analyzer's wireframe and lava
classifier, the reach audit, the map gate and the lab map compiler. The
Rust lab keeps its own reader in tools/argus_mcp/src/bsp.rs.
"""
from functools import cached_property
from pathlib import Path
import re
import struct

BSPVERSION = 29
LUMP_NAMES = ("entities", "planes", "textures", "vertexes", "visibility",
              "nodes", "texinfo", "faces", "lighting", "clipnodes",
              "leaves", "marksurfaces", "edges", "surfedges", "models")
(LUMP_ENTITIES, LUMP_PLANES, LUMP_TEXTURES, LUMP_VERTEXES, LUMP_VISIBILITY,
 LUMP_NODES, LUMP_TEXINFO, LUMP_FACES, LUMP_LIGHTING, LUMP_CLIPNODES,
 LUMP_LEAVES, LUMP_MARKSURFACES, LUMP_EDGES, LUMP_SURFEDGES,
 LUMP_MODELS) = range(len(LUMP_NAMES))
HEADER_SIZE = 4 + len(LUMP_NAMES) * 8

CONTENTS_EMPTY, CONTENTS_SOLID = -1, -2
CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5

# sv_move.c STEPSIZE: how far below the centre SV_CheckBottom lets a
# corner's floor sit before it calls the box unsupported.
STEPSIZE = 18

# How far water_top climbs above a submerged point before it stops.
# Two probes used to disagree: navgen's stopped 320u up and the
# pointfile surface overlay's 512u. 320 is the one that decides which
# swim links exist, and the overlay is there to show what navgen saw,
# so navgen's ceiling is the one kept. It also keeps navgen's output
# byte-identical.
WATER_TOP_REACH = 320

# The entity lump parse navgen and the navmesh already shared. The key
# must be non-empty; the value may be.
ENTITY_BLOCK = re.compile(r"\{(.*?)\}", re.S)
ENTITY_PAIR = re.compile(r'"([^"]+)"\s+"([^"]*)"')


class Bsp:
    """A BSP29 file with its header and lump table checked once.

    The tables are lists of tuples in file order, decoded on first use:
    planes (nx, ny, nz, dist), nodes and leaves (hull 0), clip (the
    clip nodes hulls 1 and 2 walk), models, vertexes and edges.
    """

    def __init__(self, path):
        data = Path(path).read_bytes()
        if len(data) < HEADER_SIZE:
            raise ValueError(f"{path}: file is too small for a BSP29 header")
        (version,) = struct.unpack_from("<i", data, 0)
        if version != BSPVERSION:
            raise ValueError(f"{path}: BSP version {version}, expected {BSPVERSION}")
        lumps = []
        for index, name in enumerate(LUMP_NAMES):
            offset, length = struct.unpack_from("<ii", data, 4 + index * 8)
            if offset < 0 or length < 0 or offset + length > len(data):
                raise ValueError(f"{path}: invalid {name} lump")
            lumps.append((offset, length))
        self.path = path
        self.data = data
        self.version = version
        self.lumps = tuple(lumps)

    def lump(self, index):
        offset, length = self.lumps[index]
        return self.data[offset:offset + length]

    def records(self, index, fmt):
        """A lump read as an array of fixed-size records; a ragged tail is ignored."""
        record = struct.Struct(fmt)
        raw = self.lump(index)
        return list(record.iter_unpack(raw[:len(raw) - len(raw) % record.size]))

    @cached_property
    def planes(self):
        # the trailing plane type is dropped: nothing here reads it
        return [row[:4] for row in self.records(LUMP_PLANES, "<4fi")]

    @cached_property
    def nodes(self):
        return self.records(LUMP_NODES, "<i8h2H")

    @cached_property
    def leaves(self):
        return self.records(LUMP_LEAVES, "<2i6h2H4B")

    @cached_property
    def clip(self):
        return self.records(LUMP_CLIPNODES, "<ihh")

    @cached_property
    def models(self):
        return self.records(LUMP_MODELS, "<9f7i")

    @cached_property
    def vertexes(self):
        return self.records(LUMP_VERTEXES, "<3f")

    @cached_property
    def edges(self):
        return self.records(LUMP_EDGES, "<2H")

    @cached_property
    def mins(self):
        return self.models[0][0:3]

    @cached_property
    def maxs(self):
        return self.models[0][3:6]

    @cached_property
    def hull0(self):
        return self.models[0][9]

    @cached_property
    def hull1(self):
        return self.models[0][10]

    def entity_text(self):
        """The entity lump as text, up to its terminating NUL."""
        return self.lump(LUMP_ENTITIES).split(b"\0")[0].decode("ascii", "replace")

    def entities(self):
        """One dict of key/value pairs per entity block, in lump order."""
        return [dict(ENTITY_PAIR.findall(block))
                for block in ENTITY_BLOCK.findall(self.entity_text())]

    def h0(self, x, y, z):
        """Contents of the world model's hull-0 leaf holding a point.

        Hull 0 is the render tree, where leaves keep real contents, so
        this is the only test here that sees water, slime and lava.
        """
        n = self.hull0
        nodes, planes = self.nodes, self.planes
        while n >= 0:
            node = nodes[n]
            nx, ny, nz, d = planes[node[0]]
            n = node[1] if (nx * x + ny * y + nz * z - d) >= 0 else node[2]
        return self.leaves[-1 - n][0]

    def h1(self, x, y, z, node=None):
        """Contents of hull 1 (the player hull) at a player ORIGIN.

        qbsp folds the player box into this tree, so EMPTY means a
        player standing here fits. Liquids read EMPTY. Pass node to
        start the walk below the world model's head node.
        """
        n = self.hull1 if node is None else node
        clip, planes = self.clip, self.planes
        while n >= 0:
            pn, c0, c1 = clip[n]
            nx, ny, nz, d = planes[pn]
            n = c0 if (nx * x + ny * y + nz * z - d) >= 0 else c1
        return n

    def floor_under(self, x, y, z, maxdrop, *, step=2.0):
        """The first sampled hull-0 solid at or below z, or None."""
        if step <= 0:
            raise ValueError("floor step must be positive")
        d = 0.0
        while d <= maxdrop:
            if self.h0(x, y, z - d) == CONTENTS_SOLID:
                return z - d
            d += step
        return None

    def check_bottom(self, x, y, oz):
        """SV_CheckBottom for a player box whose origin sits at oz.

        navgen runs it before it seats a waypoint (#250), the navmesh
        graph before it keeps a candidate seat, and the pointfile
        draws the seats it refuses. A seat that fails it is one the
        engine will not walk onto, which is how e1m6 shipped a node 14
        units past a lava lip.
        """
        fz = oz - 24                       # mins[2] of the player box
        corners = ((x - 16, y - 16), (x + 16, y - 16),
                   (x - 16, y + 16), (x + 16, y + 16))
        if all(self.h0(cx, cy, fz - 1) == CONTENTS_SOLID for cx, cy in corners):
            return True
        mid = self.floor_under(x, y, fz, 2 * STEPSIZE)
        if mid is None:
            return False
        for cx, cy in corners:
            c = self.floor_under(cx, cy, fz, 2 * STEPSIZE)
            if c is None or c < mid - STEPSIZE:
                return False
        return True

    def water_top(self, x, y, z):
        """The water surface above a point known to be in water.

        Climbs in 8u steps while the point above is still water, and
        stops WATER_TOP_REACH above z however deep the pool runs.
        """
        top = z
        while top < z + WATER_TOP_REACH and self.h0(x, y, top + 8) == CONTENTS_WATER:
            top += 8
        return top


def load_classifier(bsp_path):
    """Return contents(x, y, z) from the world model hull-0 BSP tree.

    Opening errors propagate so each caller retains its own missing-BSP
    policy; a file that is not BSP29 raises ValueError. This point
    classifier does not perform player-hull collision tests.
    """
    return Bsp(bsp_path).h0


def load_bsp(path):
    """The wireframe inputs: vertexes, edges, and the world model's mins and maxs."""
    bsp = Bsp(path)
    return bsp.vertexes, bsp.edges, bsp.mins, bsp.maxs
