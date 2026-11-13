"""Exact navigation mesh from a Quake BSP's player clip hull.

EXPERIMENTAL (2026-11-13). navgen samples hull 1 on a grid and keeps
what the grid happens to stand on; this reads the clip tree itself.
Every empty leaf of hull 1 is a convex region where the player ORIGIN
fits. Its upward-facing boundary faces that sit on solid are the exact
set of origins the player can stand on: a navmesh in configuration
space, with the 32x32x56 body already folded in by qbsp's hull
expansion. Nothing is sampled, so a 20u corridor or a 16u stair tread
is found exactly as it is.

Library first (load_mesh), CLI second:

    python tools/argus_navmesh.py maps_local/dm4.bsp [--png out.png]
        [--nav src/argus_nav_dm4.qc.json] [--json out.json] [--audit]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path

CONTENTS_EMPTY, CONTENTS_SOLID = -1, -2
CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5
WALKABLE_NZ = 0.7      # FL_ONGROUND needs trace_plane_normal_z > 0.7
STEP = 18.0            # SV_movestep step-up
DROPMAX = 200.0        # navgen's deliberate drop ceiling
SHIFT = 0.125          # how far below a floor face its support is read
ON = 0.01              # plane-side tolerance for polygon clipping


class Bsp:
    """The handful of BSP29 lumps a navmesh needs."""

    def __init__(self, path):
        data = Path(path).read_bytes()
        if struct.unpack_from("<i", data, 0)[0] != 29:
            raise ValueError(f"{path}: not a BSP29 file")

        def lump(i):
            off, length = struct.unpack_from("<ii", data, 4 + i * 8)
            return data[off:off + length]

        raw = lump(1)
        self.planes = [struct.unpack_from("<4f", raw, i * 20)
                       for i in range(len(raw) // 20)]
        raw = lump(9)
        self.clip = [struct.unpack_from("<ihh", raw, i * 8)
                     for i in range(len(raw) // 8)]
        raw = lump(5)
        self.nodes0 = [struct.unpack_from("<i8h2H", raw, i * 24)
                       for i in range(len(raw) // 24)]
        raw = lump(10)
        self.leaves0 = [struct.unpack_from("<2i6h2H4B", raw, i * 28)
                        for i in range(len(raw) // 28)]
        raw = lump(14)
        self.models = [struct.unpack_from("<9f7i", raw, i * 64)
                       for i in range(len(raw) // 64)]
        m0 = self.models[0]
        self.mins, self.maxs = m0[0:3], m0[3:6]
        self.hull0, self.hull1 = m0[9], m0[10]
        text = lump(0).split(b"\0")[0].decode("ascii", "replace")
        self.entities = [dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', b))
                         for b in re.findall(r"\{(.*?)\}", text, re.S)]

    def h1(self, x, y, z, node=None):
        n = self.hull1 if node is None else node
        clip, planes = self.clip, self.planes
        while n >= 0:
            pn, c0, c1 = clip[n]
            nx, ny, nz, d = planes[pn]
            n = c0 if nx * x + ny * y + nz * z - d >= 0 else c1
        return n

    def h0(self, x, y, z):
        n = self.hull0
        nodes, planes = self.nodes0, self.planes
        while n >= 0:
            node = nodes[n]
            nx, ny, nz, d = planes[node[0]]
            n = node[1] if nx * x + ny * y + nz * z - d >= 0 else node[2]
        return self.leaves0[-1 - n][0]


# ---- polygon helpers (3D, convex, vertex lists) ----

def _side(p, n, d):
    return n[0] * p[0] + n[1] * p[1] + n[2] * p[2] - d


def split(poly, n, d):
    """Split a convex polygon by plane (n, d). Returns (front, back)."""
    ds = [_side(p, n, d) for p in poly]
    if all(x >= -ON for x in ds):
        return poly, None
    if all(x <= ON for x in ds):
        return None, poly
    front, back = [], []
    m = len(poly)
    for i in range(m):
        p, q = poly[i], poly[(i + 1) % m]
        dp, dq = ds[i], ds[(i + 1) % m]
        if dp >= -ON:
            front.append(p)
        if dp <= ON:
            back.append(p)
        if (dp > ON and dq < -ON) or (dp < -ON and dq > ON):
            t = dp / (dp - dq)
            x = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t,
                 p[2] + (q[2] - p[2]) * t)
            front.append(x)
            back.append(x)
    return (front if len(front) >= 3 else None,
            back if len(back) >= 3 else None)


def clip_keep(poly, n, d):
    return split(poly, n, d)[0]


def big_poly(n, d, r=1.0e5):
    cx, cy, cz = n[0] * d, n[1] * d, n[2] * d
    a = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = (n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2],
         n[0] * a[1] - n[1] * a[0])
    ul = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    u = (u[0] / ul, u[1] / ul, u[2] / ul)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2],
         n[0] * u[1] - n[1] * u[0])
    return [(cx + s * r * u[0] + t * r * v[0],
             cy + s * r * u[1] + t * r * v[1],
             cz + s * r * u[2] + t * r * v[2])
            for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def area_xy(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i][0], poly[i][1]
        x1, y1 = poly[(i + 1) % len(poly)][0], poly[(i + 1) % len(poly)][1]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def centroid(poly):
    n = len(poly)
    return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n,
            sum(p[2] for p in poly) / n)


def plane_z(plane, x, y):
    nx, ny, nz, d = plane
    return (d - nx * x - ny * y) / nz


# ---- the extraction ----

def floor_fragments(bsp):
    """Every solid-backed walkable face of every empty hull-1 leaf.

    Returns a list of dicts: poly (origin-space vertices), plane
    (inward-up n, d), leaf (serial of the empty leaf above it).
    """
    pad = 64.0
    box = [(1.0, 0.0, 0.0, bsp.mins[0] - pad),
           (-1.0, 0.0, 0.0, -(bsp.maxs[0] + pad)),
           (0.0, 1.0, 0.0, bsp.mins[1] - pad),
           (0.0, -1.0, 0.0, -(bsp.maxs[1] + pad)),
           (0.0, 0.0, 1.0, bsp.mins[2] - pad),
           (0.0, 0.0, -1.0, -(bsp.maxs[2] + pad))]
    frags = []
    leaves = [0]

    def support(poly, node, floor_n):
        # walk the face down the tree as if it sat SHIFT below itself,
        # so the plane it lies on resolves to the side beneath it
        if node < 0:
            if node == CONTENTS_SOLID:
                yield poly
            return
        pn, c0, c1 = bsp.clip[node]
        nx, ny, nz, d = bsp.planes[pn]
        n = (nx, ny, nz)
        d2 = d + SHIFT * (nx * floor_n[0] + ny * floor_n[1] + nz * floor_n[2])
        front, back = split(poly, n, d2)
        if front:
            yield from support(front, c0, floor_n)
        if back:
            yield from support(back, c1, floor_n)

    def leaf(hs):
        leaves[0] += 1
        serial = leaves[0]
        for i, (nx, ny, nz, d) in enumerate(hs):
            if nz <= WALKABLE_NZ:
                continue
            poly = big_poly((nx, ny, nz), d)
            for j, (mx, my, mz, e) in enumerate(hs):
                if j == i:
                    continue
                if (abs(mx - nx) < 1e-5 and abs(my - ny) < 1e-5
                        and abs(mz - nz) < 1e-5 and abs(e - d) < 1e-3):
                    continue
                poly = clip_keep(poly, (mx, my, mz), e)
                if poly is None:
                    break
            if poly is None or abs(area_xy(poly)) < 1.0:
                continue
            for piece in support(poly, bsp.hull1, (nx, ny, nz)):
                if abs(area_xy(piece)) >= 1.0:
                    frags.append({"poly": piece, "plane": (nx, ny, nz, d),
                                  "leaf": serial})

    def walk(node, hs):
        if node < 0:
            if node == CONTENTS_EMPTY:
                leaf(hs)
            return
        pn, c0, c1 = bsp.clip[node]
        nx, ny, nz, d = bsp.planes[pn]
        walk(c0, hs + [(nx, ny, nz, d)])
        walk(c1, hs + [(-nx, -ny, -nz, -d)])

    sys.setrecursionlimit(10000)
    walk(bsp.hull1, list(box))
    return frags, leaves[0]


def classify_liquid(bsp, frag):
    """Worst hull-0 contents at the fragment's torso points."""
    poly = frag["poly"]
    cx, cy, cz = centroid(poly)
    pts = [(cx, cy, cz)]
    for p in poly:
        pts.append((p[0] + (cx - p[0]) * 0.2, p[1] + (cy - p[1]) * 0.2,
                    p[2] + (cz - p[2]) * 0.2))
    worst = CONTENTS_EMPTY
    for x, y, z in pts:
        c = bsp.h0(x, y, z)
        if c in (CONTENTS_LAVA, CONTENTS_SLIME):
            return c
        if c == CONTENTS_WATER:
            worst = CONTENTS_WATER
    return worst


def _edges_xy(poly):
    """Projected edges with outward normals, whatever the winding."""
    ccw = area_xy(poly) > 0
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(dx, dy)
        if ln < 0.5:
            continue
        ux, uy = dx / ln, dy / ln
        nx, ny = (uy, -ux) if ccw else (-uy, ux)
        out.append(((p[0], p[1]), (q[0], q[1]), (ux, uy), (nx, ny), ln))
    return out


def build_portals(bsp, frags, min_overlap=2.0, line_tol=0.75):
    """Directed crossings between fragments.

    Two fragments touch when an edge of each is collinear in plan,
    the two lie on OPPOSITE sides of it (a floor under a balcony shares
    the balcony's edge line but sits on the same side, and nobody
    falls into the space beneath their own feet) and the overlap is
    long enough to carry an origin through. The height difference then
    says what the crossing is: within one step, a walk both ways; a
    higher side with open air past its edge, a one-way drop down to
    DROPMAX.
    """
    cell = 64.0
    grid = {}
    edges = []
    for fi, f in enumerate(frags):
        for e in _edges_xy(f["poly"]):
            ei = len(edges)
            edges.append((fi, e))
            (ax, ay), (bx, by) = e[0], e[1]
            x0, x1 = sorted((ax, bx))
            y0, y1 = sorted((ay, by))
            for gx in range(int(math.floor(x0 / cell)),
                            int(math.floor(x1 / cell)) + 1):
                for gy in range(int(math.floor(y0 / cell)),
                                int(math.floor(y1 / cell)) + 1):
                    grid.setdefault((gx, gy), []).append(ei)
    seen = set()
    portals = []
    for bucket in grid.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                key = (a, b) if a < b else (b, a)
                if key in seen:
                    continue
                seen.add(key)
                fa, ea = edges[a]
                fb, eb = edges[b]
                if fa == fb:
                    continue
                pa, qa, ua, na, la = ea
                pb, qb, ub, nb, lb = eb
                if na[0] * nb[0] + na[1] * nb[1] > -0.999:
                    continue
                # perpendicular distance of b's endpoints from a's line
                dpb = (pb[0] - pa[0]) * na[0] + (pb[1] - pa[1]) * na[1]
                dqb = (qb[0] - pa[0]) * na[0] + (qb[1] - pa[1]) * na[1]
                if abs(dpb) > line_tol or abs(dqb) > line_tol:
                    continue
                t0 = (pb[0] - pa[0]) * ua[0] + (pb[1] - pa[1]) * ua[1]
                t1 = (qb[0] - pa[0]) * ua[0] + (qb[1] - pa[1]) * ua[1]
                lo, hi = max(0.0, min(t0, t1)), min(la, max(t0, t1))
                if hi - lo < min_overlap:
                    continue
                s = (pa[0] + ua[0] * lo, pa[1] + ua[1] * lo)
                e = (pa[0] + ua[0] * hi, pa[1] + ua[1] * hi)
                portals.extend(_classify(bsp, frags, fa, fb, s, e, na))
    portals.extend(find_drops(bsp, frags))
    return portals


def find_drops(bsp, frags, spacing=8.0):
    """One-way drops off every ledge edge, wherever the body lands.

    Sharing an edge line is how WALK neighbours meet, but a ledge over
    the middle of a lower floor shares nothing with it (dm4 n45 to
    n66, a 192u drop the edge pairing never saw). So walk every edge,
    step a body just past it, and let fall_to say where it lands: open
    air at head height, no floor within a step, a landing more than a
    step and at most DROPMAX down, on a fragment that is actually there.
    """
    out = []
    for fa, f in enumerate(frags):
        for (p, q, u, n, ln) in _edges_xy(f["poly"]):
            if ln < 4.0:
                continue
            k = max(1, int((ln - 4.0) // spacing))
            run = None
            for i in range(k + 1):
                t = 2.0 + (ln - 4.0) * (i / k)
                x, y = p[0] + u[0] * t, p[1] + u[1] * t
                z = plane_z(f["plane"], x, y)
                px, py = x + n[0] * 1.5, y + n[1] * 1.5
                land = fall_to(bsp, px, py, z + 1.0)
                fb = None
                if land is not None and STEP < z - land <= DROPMAX:
                    fb = locate(frags, px, py, land, ztol=2.5)
                if run is not None and (fb != run[0]):
                    out.append(_drop_rec(frags, fa, run))
                    run = None
                if fb is not None and fb != fa:
                    if run is None:
                        run = [fb, (x, y), (x, y)]
                    else:
                        run[2] = (x, y)
            if run is not None:
                out.append(_drop_rec(frags, fa, run))
    return out


def _drop_rec(frags, fa, run):
    fb, s, e = run
    mx, my = (s[0] + e[0]) / 2, (s[1] + e[1]) / 2
    return {"a": fa, "b": fb, "kind": "drop", "s": s, "e": e,
            "za": plane_z(frags[fa]["plane"], mx, my),
            "zb": plane_z(frags[fb]["plane"], mx, my)}


def _classify(bsp, frags, fa, fb, s, e, na):
    """0-2 directed crossings for one shared edge, A's outward = na."""
    A, B = frags[fa], frags[fb]
    mx, my = (s[0] + e[0]) / 2, (s[1] + e[1]) / 2
    dz_ends = [plane_z(B["plane"], x, y) - plane_z(A["plane"], x, y)
               for x, y in (s, e, (mx, my))]
    za = plane_z(A["plane"], mx, my)
    zb = plane_z(B["plane"], mx, my)
    out = []
    rec = {"s": s, "e": e, "za": za, "zb": zb}
    if max(abs(d) for d in dz_ends) <= STEP:
        out.append(dict(rec, a=fa, b=fb, kind="walk"))
        out.append(dict(rec, a=fb, b=fa, kind="walk", za=zb, zb=za))
    return out


def fall_to(bsp, x, y, z, maxdrop=DROPMAX + 8.0):
    """First hull-1 floor below an origin in open air, or None."""
    if bsp.h1(x, y, z) != CONTENTS_EMPTY:
        return None
    lo = z
    while z - lo <= maxdrop:
        nxt = lo - 8.0
        if bsp.h1(x, y, nxt) != CONTENTS_EMPTY:
            a, b = nxt, lo
            for _ in range(8):
                mid = (a + b) / 2
                if bsp.h1(x, y, mid) == CONTENTS_EMPTY:
                    b = mid
                else:
                    a = mid
            return b
        lo = nxt
    return None


def components(n, portals, kinds=("walk",)):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for p in portals:
        if p["kind"] in kinds:
            ra, rb = find(p["a"]), find(p["b"])
            if ra != rb:
                parent[ra] = rb
    return [find(i) for i in range(n)]


def point_in_poly_xy(x, y, poly):
    inside = False
    m = len(poly)
    for i in range(m):
        x0, y0 = poly[i][0], poly[i][1]
        x1, y1 = poly[(i + 1) % m][0], poly[(i + 1) % m][1]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xc > x:
                inside = not inside
    return inside


def locate(frags, x, y, z, ztol=40.0):
    """Fragment index under an origin, nearest in height, or None."""
    best, bd = None, ztol
    for i, f in enumerate(frags):
        poly = f["poly"]
        if not point_in_poly_xy(x, y, poly):
            continue
        dz = abs(plane_z(f["plane"], x, y) - z)
        if dz <= bd:
            best, bd = i, dz
    return best


def load_mesh(bsp_path):
    bsp = Bsp(bsp_path)
    frags, nleaves = floor_fragments(bsp)
    kept, hostile = [], 0
    for f in frags:
        c = classify_liquid(bsp, f)
        if c in (CONTENTS_LAVA, CONTENTS_SLIME):
            hostile += 1
            continue
        f["wet"] = c == CONTENTS_WATER
        kept.append(f)
    return bsp, kept, {"empty_leaves": nleaves, "fragments": len(frags),
                       "hostile_dropped": hostile}


# ---- the air layer ----
#
# The floor mesh says where a player can STAND. A Quake player who leaves
# a floor keeps moving: at 320 u/s a 190u fall carries about 220u sideways
# before it lands, which is how dm4's n45 -> n66 crosses 40u of lava and
# how e1m7's routed bots run off their upper walkways into the lake. So
# fly a player origin off every ledge through hull 1, at the speeds a bot
# actually leaves one, and see where it lands.

GRAVITY = 800.0        # sv_gravity on every map Argus ships but e1m8
RUN, WALK = 320.0, 240.0
JUMPVEL = 270.0        # AR_JUMPVEL
AIR_DT = 0.01
LETHAL = ("lava", "slime")
# (name, horizontal speed, heading offset in degrees, launch velocity_z)
AIR_VARIANTS = (("walk", WALK, 0.0, 0.0), ("run", RUN, 0.0, 0.0),
                ("run+30", RUN, 30.0, 0.0), ("run-30", RUN, -30.0, 0.0),
                ("jump", RUN, 0.0, JUMPVEL))


BRUSH_CLASSES = ("func_wall", "func_door", "func_door_secret", "func_plat")


def brush_boxes(bsp, deathmatch=True):
    """World boxes of solid brush entities, where each sits at spawn.

    The world hull knows nothing of them, and e1m7 showed why that
    matters: its deathmatch spawn pads (func_wall) and its lava bridge
    deck (a func_door) are dry floor the runtime guard approves stepping
    toward, and the first air layer flew straight through all of them
    (9 of 28 run-offs in the e1m7 investigation). Positions follow the
    stock spawn code navgen also follows: a DOOR_START_OPEN door sits one
    travel along its move direction from where it was built (doors.qc
    swaps pos1 and pos2), an untargeted plat rests one travel below its
    compiled top (plats.qc), walls and secret doors stay where they were
    built. Trains move and are left out. spawnflags 2048 removes an
    entity in deathmatch.
    """
    out = []
    for e in bsp.entities:
        cls = e.get("classname", "")
        m = e.get("model", "")
        if cls not in BRUSH_CLASSES or not m.startswith("*"):
            continue
        sf = int(float(e.get("spawnflags", "0") or 0))
        if deathmatch and sf & 2048:
            continue
        mdl = bsp.models[int(m[1:])]
        mn, mx = list(mdl[0:3]), list(mdl[3:6])
        if cls == "func_door" and sf & 1:
            a = (e.get("angle", "0") or "0").strip()
            if a in ("-1", "-2"):
                d = (0.0, 0.0, 1.0 if a == "-1" else -1.0)
            else:
                try:
                    r = math.radians(float(a))
                except ValueError:
                    r = 0.0
                d = (math.cos(r), math.sin(r), 0.0)
            lip = float(e.get("lip", 8) or 8) or 8.0
            travel = abs(sum(d[k] * (mx[k] - mn[k]) for k in range(3))) - lip
            if travel > 0:
                mn = [mn[k] + d[k] * travel for k in range(3)]
                mx = [mx[k] + d[k] * travel for k in range(3)]
        elif cls == "func_plat" and not e.get("targetname"):
            h = float(e.get("height", 0) or 0) or (mx[2] - mn[2] - 8.0)
            mn[2] -= h
            mx[2] -= h
        out.append((cls, tuple(mn), tuple(mx)))
    return out


class WithBrushes:
    """A Bsp whose hull-1 test also refuses solid brush entities.

    Duck-types the Bsp interface every air-layer function uses (h1, h0,
    mins, maxs), so the flight, the ledge sampler, the straight drop and
    the link runs all see pads, doors and plats without changing logic.
    A player origin collides with a world box when it lies inside the box
    grown by the player hull: 16 either side, 32 below, 24 above.
    """

    def __init__(self, bsp, boxes, cell=128.0):
        self.bsp = bsp
        self.mins, self.maxs = bsp.mins, bsp.maxs
        self.entities, self.models = bsp.entities, bsp.models
        self.cell = cell
        self.boxes = [(cls, (mn[0] - 16, mn[1] - 16, mn[2] - 32),
                       (mx[0] + 16, mx[1] + 16, mx[2] + 24))
                      for cls, mn, mx in boxes]
        self.grid = {}
        for i, (_, mn, mx) in enumerate(self.boxes):
            for gx in range(math.floor(mn[0] / cell), math.floor(mx[0] / cell) + 1):
                for gy in range(math.floor(mn[1] / cell), math.floor(mx[1] / cell) + 1):
                    self.grid.setdefault((gx, gy), []).append(i)

    def box_at(self, x, y, z):
        for i in self.grid.get((math.floor(x / self.cell), math.floor(y / self.cell)), ()):
            cls, mn, mx = self.boxes[i]
            if mn[0] < x < mx[0] and mn[1] < y < mx[1] and mn[2] < z < mx[2]:
                return cls
        return None

    def h1(self, x, y, z, node=None):
        c = self.bsp.h1(x, y, z)
        if c != CONTENTS_EMPTY:
            return c
        return CONTENTS_SOLID if self.box_at(x, y, z) else CONTENTS_EMPTY

    def h0(self, x, y, z):
        return self.bsp.h0(x, y, z)


def _feet_kind(bsp, x, y, oz):
    c = bsp.h0(x, y, oz - 23.0)
    return {CONTENTS_LAVA: "lava", CONTENTS_SLIME: "slime",
            CONTENTS_WATER: "water"}.get(c)


def fly(bsp, x, y, z, ux, uy, speed, vz=0.0, gravity=GRAVITY, tmax=3.0):
    """Ballistic flight of a player origin through hull 1.

    Returns {"kind", "pos", "t", "fall"}: kind is "floor" (dry landing),
    "lava", "slime" or "water" (the feet entered it, which ends the fall
    whatever lies under it) or "void" (nothing within tmax). A wall met in
    flight stops the motion into it, axis by axis, the way SV_FlyMove
    clips velocity; a ceiling kills the rise. "fall" is how far below the
    launch the body ends up.
    """
    vx, vy = ux * speed, uy * speed
    z0, t = z, 0.0
    while t < tmax:
        t += AIR_DT
        # Still on a floor: keep running at this height until it ends. A
        # body falls from the edge, not from wherever its run started
        # (the first link-run check fell at its first step and "landed"
        # back on the platform it had not yet left).
        grounded = vz <= 0 and bsp.h1(x, y, z - 0.25) != CONTENTS_EMPTY
        if grounded:
            vz = 0.0
        else:
            vz -= gravity * AIR_DT
        nx, ny = x + vx * AIR_DT, y + vy * AIR_DT
        if bsp.h1(nx, ny, z) != CONTENTS_EMPTY:
            if bsp.h1(nx, y, z) == CONTENTS_EMPTY:
                ny, vy = y, 0.0
            elif bsp.h1(x, ny, z) == CONTENTS_EMPTY:
                nx, vx = x, 0.0
            else:
                nx, ny, vx, vy = x, y, 0.0, 0.0
        nz = z + vz * AIR_DT
        if bsp.h1(nx, ny, nz) != CONTENTS_EMPTY:
            if vz > 0:
                vz, nz = 0.0, z
            else:
                land = fall_to(bsp, nx, ny, z + 0.5, maxdrop=(z - nz) + 2.0)
                lz = land if land is not None else nz
                kind = _feet_kind(bsp, nx, ny, lz)
                box_at = getattr(bsp, "box_at", None)
                on = box_at(nx, ny, lz - 0.5) if box_at else None
                return {"kind": kind if kind else "floor", "pos": (nx, ny, lz),
                        "t": t, "fall": z0 - lz, "on": on}
        kind = _feet_kind(bsp, nx, ny, nz)
        if kind:
            return {"kind": kind, "pos": (nx, ny, nz), "t": t, "fall": z0 - nz}
        x, y, z = nx, ny, nz
        if z < bsp.mins[2] - 64:
            break
    return {"kind": "void", "pos": (x, y, z), "t": t, "fall": z0 - z}


def ledge_points(bsp, frags, spacing=16.0):
    """Points along every fragment edge where a body walks into open air."""
    out = []
    for fi, f in enumerate(frags):
        for ei, (p, q, u, n, ln) in enumerate(_edges_xy(f["poly"])):
            if ln < 4.0:
                continue
            k = max(1, int(ln // spacing))
            for i in range(k):
                t = (i + 0.5) * ln / k
                x, y = p[0] + u[0] * t, p[1] + u[1] * t
                z = plane_z(f["plane"], x, y)
                px, py = x + n[0] * 1.5, y + n[1] * 1.5
                if bsp.h1(px, py, z + 1.0) != CONTENTS_EMPTY:
                    continue                  # a wall, or a step up
                if fall_to(bsp, px, py, z + 1.0, maxdrop=STEP + 2.0) is not None:
                    continue                  # floor within a step: walk on
                out.append({"frag": fi, "edge": (fi, ei), "pos": (x, y, z),
                            "n": n, "u": u})
    return out


def map_gravity(bsp_path):
    """sv_gravity as stock world.qc sets it: 100 on e1m8, 800 elsewhere."""
    return 100.0 if Path(bsp_path).stem.lower() in ("e1m8", "lq_e1m8") else GRAVITY


def danger_stretches(samples, verdict="danger"):
    """Runs of consecutive same-verdict points along one edge, longest first."""
    runs, cur = [], None
    for s in samples:
        if s["verdict"] == verdict and cur and cur["edge"] == s["edge"]:
            cur["end"] = s["pos"]
            cur["points"] += 1
        else:
            if cur:
                runs.append(cur)
            cur = ({"edge": s["edge"], "start": s["pos"], "end": s["pos"], "points": 1}
                   if s["verdict"] == verdict else None)
    if cur:
        runs.append(cur)
    for r in runs:
        r["length"] = math.hypot(r["end"][0] - r["start"][0],
                                 r["end"][1] - r["start"][1])
    return sorted(runs, key=lambda r: (-r["points"], r["start"]))


def air_layer(bsp, frags, spacing=16.0, gravity=GRAVITY):
    """Fly every ledge point off in each AIR_VARIANTS way.

    Each sample gains "drop" (the straight-down landing the floor mesh
    models), "out" ({variant: flight result}) and "verdict": "danger"
    when a straight run at RUN lands in lava or slime, "risky" when only
    a turned run, a walk or a jump does, "momentum" when the straight drop
    is lethal but every way off at speed lands dry (dm4's n45 class), and
    "safe" otherwise.
    """
    samples = ledge_points(bsp, frags, spacing)
    for s in samples:
        x, y, z = s["pos"]
        nx, ny = s["n"]
        px, py = x + nx * 1.5, y + ny * 1.5
        straight = fall_to(bsp, px, py, z + 1.0, maxdrop=4096.0)
        if straight is None:
            s["drop"] = "void"
        else:
            s["drop"] = _feet_kind(bsp, px, py, straight) or "floor"
        s["out"] = {}
        for name, speed, off, vz in AIR_VARIANTS:
            a = math.radians(off)
            ux = nx * math.cos(a) - ny * math.sin(a)
            uy = nx * math.sin(a) + ny * math.cos(a)
            s["out"][name] = fly(bsp, x, y, z, ux, uy, speed, vz, gravity)
        kinds = {k: r["kind"] for k, r in s["out"].items()}
        if kinds["run"] in LETHAL:
            s["verdict"] = "danger"
        elif any(k in LETHAL for k in kinds.values()):
            s["verdict"] = "risky"
        elif s["drop"] in LETHAL:
            s["verdict"] = "momentum"
        else:
            s["verdict"] = "safe"
    return samples


def link_runs(bsp, doc, speed=RUN, gravity=GRAVITY):
    """Run every descending plain link at speed and see where it lands.

    Walk the straight line from the source on hull 1 until the floor
    falls away, then fly off that lip along the link's heading. Returns
    one row per link that has a lip: the straight-down and at-speed
    landings and how far the at-speed landing ends from the target seat.
    """
    nodes = [tuple(p) for p in doc["nodes"]]
    typed = set()
    for k in TYPED_FAMILIES:
        typed |= {tuple(r[:2]) for r in doc.get(k, [])}
    rows = []
    for row in doc.get("links", []):
        a, b = row[0], row[1]
        if (a, b) in typed or nodes[a][2] - nodes[b][2] <= STEP:
            continue
        (ax, ay, az), (bx, by, bz) = nodes[a], nodes[b]
        d = math.hypot(bx - ax, by - ay)
        if d < 1.0:
            continue
        ux, uy = (bx - ax) / d, (by - ay) / d
        z, t, lip = az, 0.0, None
        while t < d:
            t += 4.0
            x, y = ax + ux * t, ay + uy * t
            if bsp.h1(x, y, z + STEP) != CONTENTS_EMPTY:
                break                         # a wall before any lip
            f = fall_to(bsp, x, y, z + STEP, maxdrop=2 * STEP)
            if f is None:
                lip = (x - ux * 4.0, y - uy * 4.0, z)
                break
            z = f
        if lip is None:
            continue
        straight = fall_to(bsp, lip[0] + ux * 1.5, lip[1] + uy * 1.5,
                           lip[2] + 1.0, maxdrop=4096.0)
        skind = ("void" if straight is None else
                 _feet_kind(bsp, lip[0] + ux * 1.5, lip[1] + uy * 1.5, straight) or "floor")
        r = fly(bsp, lip[0], lip[1], lip[2], ux, uy, speed, 0.0, gravity)
        miss = math.hypot(r["pos"][0] - bx, r["pos"][1] - by)
        rows.append({"a": a, "b": b, "lip": lip, "straight": skind,
                     "run": r["kind"], "land": r["pos"], "miss": miss})
    return rows


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def entries_vs_ledges(bsp, samples, tape_texts, near=32.0, dz=48.0, window=2):
    """Do bots enter lava by leaving the ledges the air layer calls lethal?

    A proximity count alone proves nothing (2026-11-13: every e1m7 lava
    death sat near a lava seat because the seats are in the lake). So the
    same test runs on two populations of consecutive 0.5 s sample pairs:
    lava ENTRIES (dry, then feet in lava or slime) and ordinary dry MOVES
    (both dry, more than 32u apart). A pair "crosses" a ledge class when
    its segment passes within `near` of one of its points at a height
    within `dz` of the pair's dry end. The answer is the ratio of the two
    rates, not either count. `window` widens each population to its last
    N segments: 0.5 s samples at 320 u/s are 160u apart, so a bot that
    left the ledge between two samples enters the lava from a sample that
    was already in the air (e1m7: 118 of 223 entries fell more than 48u
    from a pair that crossed no ledge).
    """
    import argus_tape as at
    cell = 64.0
    grids = {}
    for s in samples:
        g = grids.setdefault(s["verdict"], {})
        x, y, z = s["pos"]
        g.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append((x, y, z))

    def crosses(verdicts, path):
        return any(crosses1(verdicts, a, b) for a, b in zip(path, path[1:]))

    def crosses1(verdicts, a, b):
        x0, x1 = sorted((a["x"], b["x"]))
        y0, y1 = sorted((a["y"], b["y"]))
        for v in verdicts:
            g = grids.get(v, {})
            for gx in range(math.floor((x0 - near) / cell), math.floor((x1 + near) / cell) + 1):
                for gy in range(math.floor((y0 - near) / cell), math.floor((y1 + near) / cell) + 1):
                    for (x, y, z) in g.get((gx, gy), ()):
                        if abs(z - a["z"]) <= dz and _seg_dist(
                                x, y, a["x"], a["y"], b["x"], b["y"]) <= near:
                            return True
        return False

    stats = {"entries": 0, "moves": 0,
             "entries_danger": 0, "moves_danger": 0,
             "entries_lethal_any": 0, "moves_lethal_any": 0,
             "entries_any_ledge": 0, "moves_any_ledge": 0,
             "entries_jump": 0, "entries_danger_jump": 0}
    lethal = ("danger", "risky")
    every = ("danger", "risky", "momentum", "safe")
    # Two classes hide inside "left a danger ledge" (the e1m7 lava
    # investigation): a run-off, where a grounded bot walks off at speed,
    # and a deliberate jump from a low floor at the lake edge, which is a
    # danger ledge too. A jump or rocket jump event in the window splits
    # them. Events carry no time of their own, so each takes the time of
    # the latest sample before it in the tape.
    jump_re = re.compile(r"ARGEVT (.+?) (?:jump|rjump)\s*$")
    time_re = re.compile(r"ARGLOG .+? t\s+([\d.]+)")
    for text in tape_texts:
        tracks = {}
        for name, s in at.samples(text):
            tracks.setdefault(name, []).append(s)
        jumps, now = {}, 0.0
        for line in text.splitlines():
            m = time_re.search(line)
            if m:
                now = float(m.group(1))
                continue
            m = jump_re.search(line)
            if m:
                jumps.setdefault(m.group(1), []).append(now)
        for name, ss in tracks.items():
            wet = [_feet_kind(bsp, s["x"], s["y"], s["z"]) in LETHAL for s in ss]
            for k in range(window, len(ss)):
                path = ss[k - window:k + 1]
                if any(b["t"] - a["t"] > 1.0 for a, b in zip(path, path[1:])):
                    continue                  # respawn or a gap in the tape
                if any(wet[k - window:k]):
                    continue                  # already in it
                a, b = path[0], path[-1]
                if wet[k]:
                    key = "entries"
                elif math.hypot(b["x"] - a["x"], b["y"] - a["y"]) > 32.0:
                    key = "moves"
                else:
                    continue
                stats[key] += 1
                jumped = key == "entries" and any(
                    path[0]["t"] - 0.01 <= tj <= b["t"] + 0.01
                    for tj in jumps.get(name, ()))
                if jumped:
                    stats["entries_jump"] += 1
                if crosses(("danger",), path):
                    stats[key + "_danger"] += 1
                    if jumped:
                        stats["entries_danger_jump"] += 1
                if crosses(lethal, path):
                    stats[key + "_lethal_any"] += 1
                if crosses(every, path):
                    stats[key + "_any_ledge"] += 1
    return stats


TYPED_FAMILIES = ("jlinks", "sprintlinks", "rjlinks", "liftlinks",
                  "swimlinks", "trainlinks", "teles")


def audit(bsp, frags, doc):
    """Cross-examine a shipped graph against the exact mesh.

    Every check here found a real defect on the day it was written
    (2026-11-13): seats standing in liquid navgen's floor+48 test cannot
    see, walk links the mesh says no body can follow, and the vertical
    "walks" a zero-length beeline_ok passes unconditionally.
    """
    nodes = [tuple(n) for n in doc["nodes"]]
    out = {}
    # 1. seats whose FEET are in lava or slime: WaterMove burns at
    # waterlevel 1, but navgen 4b classifies at origin+24 (floor+48)
    out["liquid_seats"] = [
        (i, n, bsp.h0(n[0], n[1], n[2] - 23)) for i, n in enumerate(nodes)
        if bsp.h0(n[0], n[1], n[2] - 23) in (CONTENTS_LAVA, CONTENTS_SLIME)]
    # 1b. of those, the ones a dry seat still routes INTO (navgen
    # --repair-links leaves liquid seats in place as escape seats but
    # cuts every way in that is not a dry seat's only exit)
    wet = {i for i, _, _ in out["liquid_seats"]}
    out["liquid_entries"] = [
        (a, b) for a, b, *_ in doc.get("links", [])
        if b in wet and a not in wet]
    # 2. seats on no fragment at all
    where = [locate(frags, x, y, z, 30.0) for x, y, z in nodes]
    out["offmesh_seats"] = [i for i, f in enumerate(where) if f is None]
    # 3. plain links the mesh cannot carry: no walk/drop path between
    # the fragments under the two seats (typed hops are exempt)
    ports = build_portals(bsp, frags)
    fwd = {}
    for p in ports:
        fwd.setdefault(p["a"], set()).add(p["b"])
    typed = set()
    for k in TYPED_FAMILIES:
        typed |= {tuple(r[:2]) for r in doc.get(k, [])}
    reach = {}

    def reachable(a):
        if a not in reach:
            seen, stack = {a}, [a]
            while stack:
                u = stack.pop()
                for v in fwd.get(u, ()):
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            reach[a] = seen
        return reach[a]
    bad, vertical = [], []
    for row in doc.get("links", []):
        a, b = row[0], row[1]
        if (a, b) in typed:
            continue
        na, nb = nodes[a], nodes[b]
        if (math.hypot(nb[0] - na[0], nb[1] - na[1]) < 1.0
                and nb[2] - na[2] > STEP):
            vertical.append((a, b))
        fa, fb = where[a], where[b]
        if fa is None or fb is None:
            continue
        if fb not in reachable(fa):
            bad.append((a, b))
    out["mesh_unreachable_links"] = bad
    out["vertical_walks"] = vertical
    out["portals"] = len(ports)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bsp")
    ap.add_argument("--png")
    ap.add_argument("--nav", help="shipped nav json to overlay and audit")
    ap.add_argument("--json", help="write fragments as json")
    ap.add_argument("--audit", action="store_true",
                    help="cross-examine the shipped graph (src/argus_nav_<map>.qc.json "
                         "unless --nav names one)")
    ap.add_argument("--air", action="store_true",
                    help="fly a body off every ledge at walk, run and jump speeds "
                         "and report where it lands")
    ap.add_argument("--tapes", nargs="*", default=[],
                    help="with --air: tapes whose lava entries to test against "
                         "the lethal ledges, with ordinary moves as the base rate")
    ap.add_argument("--air-png", help="with --air: draw the ledge verdicts over the mesh")
    ap.add_argument("--gravity", type=float,
                    help="override sv_gravity (default: 100 on e1m8, else 800)")
    ap.add_argument("--no-brushes", action="store_true",
                    help="with --air: world hull only, ignoring walls, doors and plats")
    a = ap.parse_args(argv)
    bsp, frags, stats = load_mesh(a.bsp)
    if a.air:
        return _air_report(a, bsp, frags)
    if a.audit:
        nav = a.nav or str(Path(__file__).resolve().parent.parent / "src"
                           / f"argus_nav_{Path(a.bsp).stem}.qc.json")
        doc = json.loads(Path(nav).read_text())
        r = audit(bsp, frags, doc)
        nodes = doc["nodes"]
        print(f"{Path(a.bsp).stem}: {len(frags)} fragments, {r['portals']} "
              f"portals, {len(nodes)} shipped seats")
        print(f"  seats with feet in lava/slime: {len(r['liquid_seats'])}")
        for i, n, c in r["liquid_seats"][:8]:
            print(f"    n{i} {tuple(round(v) for v in n)} "
                  f"{'lava' if c == CONTENTS_LAVA else 'slime'}")
        print(f"  ordinary links from a dry seat into one of them: "
              f"{len(r['liquid_entries'])}")
        print(f"  seats on no mesh fragment: {len(r['offmesh_seats'])}")
        print(f"  vertical walk links (same xy, rising past a step): "
              f"{len(r['vertical_walks'])}")
        for x, y in r["vertical_walks"][:8]:
            print(f"    n{x} {tuple(round(v) for v in nodes[x])} -> "
                  f"n{y} {tuple(round(v) for v in nodes[y])}")
        print(f"  plain links with no mesh walk/drop path: "
              f"{len(r['mesh_unreachable_links'])} (ballistic drops land here too)")
        for x, y in r["mesh_unreachable_links"][:8]:
            print(f"    n{x} {tuple(round(v) for v in nodes[x])} -> "
                  f"n{y} {tuple(round(v) for v in nodes[y])}")
        return 0
    area = sum(abs(area_xy(f["poly"])) for f in frags)
    print(f"{a.bsp}: {stats['empty_leaves']} empty hull-1 leaves, "
          f"{stats['fragments']} floor fragments, "
          f"{stats['hostile_dropped']} on lava/slime dropped")
    print(f"  kept {len(frags)} fragments, {area:.0f} sq u of standable "
          f"origin, {sum(1 for f in frags if f['wet'])} wet")
    if a.json:
        Path(a.json).write_text(json.dumps(
            [{"poly": [list(map(lambda v: round(v, 2), p)) for p in f["poly"]],
              "plane": [round(v, 6) for v in f["plane"]], "wet": f["wet"]}
             for f in frags]), encoding="ascii")
    if a.png:
        render(frags, a.png, a.nav)
    return 0


def _air_report(a, bsp, frags):
    stem = Path(a.bsp).stem
    gravity = a.gravity if a.gravity else map_gravity(a.bsp)
    boxes = [] if a.no_brushes else brush_boxes(bsp)
    world = WithBrushes(bsp, boxes)
    samples = air_layer(world, frags, gravity=gravity)
    v = {k: sum(1 for s in samples if s["verdict"] == k)
         for k in ("danger", "risky", "momentum", "safe")}
    on = sum(1 for s in samples for r in s["out"].values() if r.get("on"))
    print(f"{stem} air layer at gravity {gravity:.0f}: {len(samples)} ledge points, "
          f"16u apart; {len(boxes)} solid brush entities"
          + (f", {on} flights land on one" if boxes else " (--no-brushes)"))
    print(f"  danger   {v['danger']:4d}  a straight run at {RUN:.0f} u/s lands in lava or slime")
    print(f"  risky    {v['risky']:4d}  only a walk, a turned run or a jump does")
    print(f"  momentum {v['momentum']:4d}  lethal straight down, dry every way at speed")
    print(f"  safe     {v['safe']:4d}")
    for r in danger_stretches(samples)[:8]:
        s, e = r["start"], r["end"]
        print(f"    danger stretch {r['points']:2d} pts  ({s[0]:.0f} {s[1]:.0f} {s[2] - 24:.0f}) "
              f"to ({e[0]:.0f} {e[1]:.0f} {e[2] - 24:.0f})  floor height")
    nav = a.nav or str(Path(__file__).resolve().parent.parent / "src"
                       / f"argus_nav_{stem}.qc.json")
    if Path(nav).exists():
        doc = json.loads(Path(nav).read_text())
        # Both speeds, because the lip speed decides it: the runtime takes
        # a router-promised drop with a 240 u/s step, and dm4's five links
        # that land in lava at 320 all land dry at 240 - real lava entries
        # pass their lips LESS often than ordinary moves do (0.7 against
        # 2.2 per cent over 120 tapes). A 320-only verdict cried wolf.
        rows = link_runs(world, doc, speed=RUN, gravity=gravity)
        slow = {(r["a"], r["b"]): r for r in link_runs(world, doc, speed=WALK, gravity=gravity)}
        both = [r for r in rows if r["run"] in LETHAL
                and slow.get((r["a"], r["b"]), {}).get("run") in LETHAL]
        fast = [r for r in rows if r["run"] in LETHAL and r not in both]
        saved = [r for r in rows if r["straight"] in LETHAL and r["run"] not in LETHAL]
        print(f"  descending plain links: {len(rows)} with a lip; land in lava or slime "
              f"at both {WALK:.0f} and {RUN:.0f} u/s: {len(both)}; at {RUN:.0f} only: "
              f"{len(fast)}; lethal straight down but dry at speed: {len(saved)}")
        for r in both[:6] + fast[:6]:
            tag = "both speeds" if r in both else f"{RUN:.0f} only"
            print(f"    n{r['a']} -> n{r['b']} ({tag}) lands {r['run']} at "
                  f"({r['land'][0]:.0f} {r['land'][1]:.0f} {r['land'][2]:.0f})")
    if a.tapes:
        texts = []
        for t in a.tapes:
            text = Path(t).read_text(errors="replace")
            if f"SpawnServer: {stem}" in text:
                texts.append(text)
        r = entries_vs_ledges(world, samples, texts)
        e = r["entries_danger"] / max(1, r["entries"])
        m = r["moves_danger"] / max(1, r["moves"])
        print(f"  tapes {len(texts)}: {r['entries']} lava or slime entries, "
              f"{100 * e:.1f}% left a danger ledge in the last second, against "
              f"{100 * m:.1f}% of {r['moves']} ordinary 1 s windows "
              f"({e / m:.1f}x)" if m else
              f"  tapes {len(texts)}: {r['entries']} entries, no ordinary moves to compare")
        dj, d = r["entries_danger_jump"], r["entries_danger"]
        print(f"    of those {d} danger-ledge entries, {d - dj} were run-offs and "
              f"{dj} followed a jump event; {r['entries_jump']} of all "
              f"{r['entries']} entries followed one")
    if a.air_png:
        render_air(frags, samples, a.air_png, f"{stem}: ledge verdicts at {RUN:.0f} u/s")
    return 0


def render_air(frags, samples, path, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    fig, ax = plt.subplots(figsize=(14, 14))
    ax.add_collection(PolyCollection([[(p[0], p[1]) for p in f["poly"]] for f in frags],
                                     facecolors="#e6e6e6", edgecolors="#9a9a9a",
                                     linewidths=0.3))
    colours = {"danger": "#d62728", "risky": "#ff9f1c", "momentum": "#1f77b4",
               "safe": "#2ca02c"}
    for k, c in colours.items():
        pts = [s["pos"] for s in samples if s["verdict"] == k]
        if pts:
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=9, c=c,
                       label=f"{k} ({len(pts)})", zorder=5)
    ax.legend(loc="upper right")
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title(title)
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def render(frags, path, nav=None, title=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    zs = [centroid(f["poly"])[2] for f in frags]
    lo, hi = min(zs), max(zs)
    fig, ax = plt.subplots(figsize=(14, 14))
    cmap = plt.get_cmap("viridis")
    polys = [[(p[0], p[1]) for p in f["poly"]] for f in frags]
    cols = [cmap((z - lo) / max(1.0, hi - lo)) for z in zs]
    pc = PolyCollection(polys, facecolors=cols, edgecolors="k",
                        linewidths=0.15)
    ax.add_collection(pc)
    if nav:
        doc = json.loads(Path(nav).read_text())
        xs = [n[0] for n in doc["nodes"]]
        ys = [n[1] for n in doc["nodes"]]
        ax.scatter(xs, ys, s=10, c="red", zorder=5)
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title(title or f"{len(frags)} fragments, z {lo:.0f}..{hi:.0f}")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
