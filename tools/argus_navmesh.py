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

Three layers sit on the floor mesh without changing it: the air layer
(air_layer: where a body leaving a ledge lands), the water layer
(water_layer: swim volumes, their exits and the air they ask for, printed
by --audit) and the time layer (movers, mover_ledges: each plat, door and
train at every position it holds, printed by --air), the last two #791.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from argus_bsp import Bsp
from argus_spawn_settling import SPAWN_SETTLING, brush_spawnflags, entity_number

CONTENTS_EMPTY, CONTENTS_SOLID = -1, -2
CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5
WALKABLE_NZ = 0.7      # FL_ONGROUND needs trace_plane_normal_z > 0.7
STEP = 18.0            # SV_movestep step-up
DROPMAX = 200.0        # navgen's deliberate drop ceiling
SHIFT = 0.125          # how far below a floor face its support is read
ON = 0.01              # plane-side tolerance for polygon clipping


# Bsp (the handful of BSP29 lumps a navmesh needs, and its hull 0 and
# hull 1 point tests) is argus_bsp's, imported above (#814).


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


def floor_under(bsp, x, y, z, maxdrop=DROPMAX + 8.0):
    """The hull-1 floor below an origin, as (height, plane) or None.

    fall_to brackets the floor to 1/32u. The plane is the first clip node
    whose plane separates the empty point at that height from the solid
    one 1/16u below it, turned so its normal faces the empty side: the
    face a trace for the player box would report, and so the face whose
    normal z decides FL_ONGROUND.
    """
    f = fall_to(bsp, x, y, z, maxdrop)
    if f is None:
        return None
    za, zb = f, f - 1.0 / 16
    n = bsp.hull1
    while n >= 0:
        pn, c0, c1 = bsp.clip[n]
        nx, ny, nz, d = bsp.planes[pn]
        sa = nx * x + ny * y + nz * za - d
        sb = nx * x + ny * y + nz * zb - d
        ca = c0 if sa >= 0 else c1
        if ca != (c0 if sb >= 0 else c1):
            s = 1.0 if sa >= 0 else -1.0
            return f, (s * nx, s * ny, s * nz, s * d)
        n = ca
    return None


def nearest_fragment(frags, x, y, z, ztol=STEP, reach=64.0):
    """Plan distance to the nearest fragment within ztol of z, or None.

    Height is read on the fragment's own plane at its point nearest
    (x, y), so a floor counts only where a body could step onto it.
    Nothing past reach counts.
    """
    best = None
    for f in frags:
        poly = f["poly"]
        if (x < min(p[0] for p in poly) - reach or x > max(p[0] for p in poly) + reach
                or y < min(p[1] for p in poly) - reach
                or y > max(p[1] for p in poly) + reach):
            continue
        if point_in_poly_xy(x, y, poly):
            d, px, py = 0.0, x, y
        else:
            d, px, py = None, x, y
            m = len(poly)
            for i in range(m):
                ax, ay = poly[i][0], poly[i][1]
                bx, by = poly[(i + 1) % m][0], poly[(i + 1) % m][1]
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
                qx, qy = ax + dx * t, ay + dy * t
                e = math.hypot(x - qx, y - qy)
                if d is None or e < d:
                    d, px, py = e, qx, qy
        if d > reach or (best is not None and d >= best):
            continue
        if abs(plane_z(f["plane"], px, py) - z) <= ztol:
            best = d
    return best


# Why a shipped seat locates on no fragment (audit section 2b), in the order
# the audit tests them. Only "unexplained" is a candidate extractor miss.
OFFMESH_WHY = ("liquid", "in_solid", "no_floor", "steep", "unexplained")
OFFMESH_LABELS = (
    ("liquid", "in liquid, kept by the repair (feet in lava or slime)"),
    ("steep", f"dry, on a face too steep to stand on (normal z at most {WALKABLE_NZ})"),
    ("no_floor", "dry, no world floor within 30u below (a brush entity or mid-air)"),
    ("in_solid", "dry, inside the world"),
    ("unexplained", "dry, no fragment"),
)


def explain_offmesh(bsp, frags, seat, ztol=30.0):
    """Say why a seat that locates on no fragment cannot.

    Returns {"why", "nz", "near"}. why is one of OFFMESH_WHY: "liquid"
    (feet in lava or slime, whose fragments load_mesh drops; navgen
    --repair-links keeps such seats as exits), "in_solid" (the seat is
    inside the hull-1 world), "no_floor" (no hull-1 floor within ztol
    below it: a brush entity's top, a mover or mid-air), "steep" (the
    floor is a face whose normal z is at most WALKABLE_NZ, which a body
    cannot stand on and floor_fragments leaves out by design) or
    "unexplained". nz is the floor face's normal z where there is one;
    near is the plan distance to the nearest fragment within a step of
    the seat's height (nearest_fragment), None past 64u.
    """
    x, y, z = seat
    out = {"why": "unexplained", "nz": None,
           "near": nearest_fragment(frags, x, y, z)}
    if bsp.h0(x, y, z - 23) in (CONTENTS_LAVA, CONTENTS_SLIME):
        out["why"] = "liquid"
        return out
    # a seat embedded less than 1u in its floor still reads as on it
    if bsp.h1(x, y, z + 1.0) != CONTENTS_EMPTY:
        out["why"] = "in_solid"
        return out
    fl = floor_under(bsp, x, y, z + 1.0, maxdrop=ztol + 1.0)
    if fl is None:
        out["why"] = "no_floor"
        return out
    out["nz"] = fl[1][2]
    if fl[1][2] <= WALKABLE_NZ:
        out["why"] = "steep"
    return out


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
    for e in bsp.entities():
        cls = e.get("classname", "")
        m = e.get("model", "")
        if cls not in SPAWN_SETTLING["brush_classes"] or not m.startswith("*"):
            continue
        sf = brush_spawnflags(e)
        if deathmatch and sf & SPAWN_SETTLING["not_deathmatch_flag"]:
            continue
        mdl = bsp.models[int(m[1:])]
        mn, mx = list(mdl[0:3]), list(mdl[3:6])
        if cls == "func_door" and sf & SPAWN_SETTLING["door_start_open_flag"]:
            angle = entity_number(e, "angle")
            if angle in (-1.0, -2.0):
                d = (0.0, 0.0, 1.0 if angle == -1.0 else -1.0)
            else:
                r = math.radians(angle)
                d = (math.cos(r), math.sin(r), 0.0)
            lip = entity_number(e, "lip") or SPAWN_SETTLING["door_default_lip_u"]
            travel = abs(sum(d[k] * (mx[k] - mn[k]) for k in range(3))) - lip
            if travel > 0:
                mn = [mn[k] + d[k] * travel for k in range(3)]
                mx = [mx[k] + d[k] * travel for k in range(3)]
        elif cls == "func_plat" and not e.get("targetname"):
            h = entity_number(e, "height") or (mx[2] - mn[2] - SPAWN_SETTLING["plat_default_inset_u"])
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
    launch the body ends up, and "clip" counts the frames a wall or a
    ceiling took motion away, so a caller that needs a clean arc (the
    mesh-native jump finder) can refuse one that only landed by sliding.
    """
    vx, vy = ux * speed, uy * speed
    z0, t, clip = z, 0.0, 0
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
            clip += 1
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
                clip += 1
            else:
                land = fall_to(bsp, nx, ny, z + 0.5, maxdrop=(z - nz) + 2.0)
                lz = land if land is not None else nz
                kind = _feet_kind(bsp, nx, ny, lz)
                box_at = getattr(bsp, "box_at", None)
                on = box_at(nx, ny, lz - 0.5) if box_at else None
                return {"kind": kind if kind else "floor", "pos": (nx, ny, lz),
                        "t": t, "fall": z0 - lz, "on": on, "clip": clip}
        kind = _feet_kind(bsp, nx, ny, nz)
        if kind:
            return {"kind": kind, "pos": (nx, ny, nz), "t": t, "fall": z0 - nz,
                    "clip": clip}
        x, y, z = nx, ny, nz
        if z < bsp.mins[2] - 64:
            break
    return {"kind": "void", "pos": (x, y, z), "t": t, "fall": z0 - z, "clip": clip}


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
        judge_ledge(bsp, s, gravity)
    return samples


def judge_ledge(bsp, s, gravity=GRAVITY):
    """Fly one ledge sample off every AIR_VARIANTS way and grade it.

    Fills s["drop"], s["out"] and s["verdict"] exactly as air_layer
    describes, and returns s. The time layer (#791) grades the same
    point once per mover state with it.
    """
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
    return s


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
        r = run_off(bsp, nodes[a], nodes[b], speed, gravity)
        if r is None:
            continue
        rows.append({"a": a, "b": b, "lip": r["lip"], "straight": r["straight"],
                     "run": r["run"], "land": r["land"], "miss": r["miss"]})
    return rows


def run_off(bsp, a, b, speed=RUN, gravity=GRAVITY):
    """Run the straight line from origin a toward b and fly off its lip.

    The walk keeps to hull 1 a step at a time; the first point where the
    floor falls more than a step away is the lip, and the body flies off
    it along the line at speed. None when the line meets a wall or reaches
    b with no lip. Otherwise the lip, the straight-down landing kind
    ("straight"), the at-speed flight's kind ("run"), landing ("land") and
    the brush entity it landed on, if any ("on"), and how far that landing
    ends from b horizontally ("miss"). link_runs grades every descending
    link this way; navgen grades a spawn pad's exits with it (#783).
    """
    (ax, ay, az), (bx, by, _) = a, b
    d = math.hypot(bx - ax, by - ay)
    if d < 1.0:
        return None
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
        return None
    straight = fall_to(bsp, lip[0] + ux * 1.5, lip[1] + uy * 1.5,
                       lip[2] + 1.0, maxdrop=4096.0)
    skind = ("void" if straight is None else
             _feet_kind(bsp, lip[0] + ux * 1.5, lip[1] + uy * 1.5, straight) or "floor")
    r = fly(bsp, lip[0], lip[1], lip[2], ux, uy, speed, 0.0, gravity)
    miss = math.hypot(r["pos"][0] - bx, r["pos"][1] - by)
    return {"lip": lip, "straight": skind, "run": r["kind"], "land": r["pos"],
            "on": r.get("on"), "miss": miss}


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
    # 2b. and why (#788): the line used to lump the lava seats the repair
    # keeps on purpose in with dry ones, and every dry one on the shipped
    # graphs turned out to stand on a face too steep to stand on, not on a
    # floor the extractor lost
    out["offmesh"] = [dict(explain_offmesh(bsp, frags, nodes[i]), seat=i)
                      for i in out["offmesh_seats"]]
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


# ---- convex cells (#791) ----
#
# The floor mesh needs only the floor faces of each empty leaf. The water
# layer needs the leaves themselves, as solids, and the parts of them in
# water. A cell is a convex polytope held as its faces, each (n, d, poly)
# with n pointing INTO the cell (inside means n.p >= d). Pushing a cell
# down a BSP tree and splitting it at every node plane hands each leaf the
# exact piece of the cell inside it, which is how hull 1 (where a body
# fits) and hull 0 (what the contents are) are crossed without sampling.

MIN_CELL = 1.0         # cubic units; slivers from near-coplanar cuts go


def poly_area3(poly):
    sx = sy = sz = 0.0
    x0, y0, z0 = poly[0]
    for i in range(1, len(poly) - 1):
        ax, ay, az = poly[i][0] - x0, poly[i][1] - y0, poly[i][2] - z0
        bx, by, bz = poly[i + 1][0] - x0, poly[i + 1][1] - y0, poly[i + 1][2] - z0
        sx += ay * bz - az * by
        sy += az * bx - ax * bz
        sz += ax * by - ay * bx
    return math.sqrt(sx * sx + sy * sy + sz * sz) / 2.0


def cell_from_planes(planes):
    """The convex cell bounded by inward planes (n, d), or None if empty."""
    faces = []
    for i, (n, d) in enumerate(planes):
        poly = big_poly(n, d)
        for j, (m, e) in enumerate(planes):
            if j != i:
                poly = clip_keep(poly, m, e)
                if poly is None:
                    break
        if poly is not None and poly_area3(poly) > 1e-3:
            faces.append((n, d, poly))
    return faces if len(faces) >= 4 else None


def cell_box(mn, mx):
    return cell_from_planes([((1.0, 0.0, 0.0), mn[0]), ((-1.0, 0.0, 0.0), -mx[0]),
                             ((0.0, 1.0, 0.0), mn[1]), ((0.0, -1.0, 0.0), -mx[1]),
                             ((0.0, 0.0, 1.0), mn[2]), ((0.0, 0.0, -1.0), -mx[2])])


def cell_split(cell, n, d):
    """Split a cell by the plane n.p = d into (front, back); a side may be None."""
    sides = [_side(p, n, d) for _, _, poly in cell for p in poly]
    lo, hi = min(sides), max(sides)
    if lo >= -ON:
        return cell, None
    if hi <= ON:
        return None, cell
    cap = big_poly(n, d)
    for fn, fd, _ in cell:
        cap = clip_keep(cap, fn, fd)
        if cap is None:
            break
    if cap is None or poly_area3(cap) <= 1e-3:
        # the plane only grazes the cell: keep it whole on its main side
        return (cell, None) if hi >= -lo else (None, cell)
    front, back = [], []
    for fn, fd, poly in cell:
        f, b = split(poly, n, d)
        if f:
            front.append((fn, fd, f))
        if b:
            back.append((fn, fd, b))
    front.append((n, d, cap))
    back.append(((-n[0], -n[1], -n[2]), -d, cap[::-1]))
    return (front if len(front) >= 4 else None,
            back if len(back) >= 4 else None)


def cell_vertices(cell):
    seen = {}
    for _, _, poly in cell:
        for p in poly:
            seen.setdefault((round(p[0], 2), round(p[1], 2), round(p[2], 2)), p)
    return list(seen.values())


def cell_volume(cell, inside):
    return sum(poly_area3(poly) * max(0.0, _side(inside, n, d))
               for n, d, poly in cell) / 3.0


def cell_contains(cell, p, tol=0.0):
    return all(_side(p, n, d) >= -tol for n, d, _ in cell)


def tree_cells(bsp, cell, hull=1, dz=0.0):
    """Push a cell down a BSP tree; yield (contents, piece) at every leaf it reaches.

    hull 1 walks the clip nodes from the world's hull-1 head (player
    origins); hull 0 the render nodes, whose leaves keep real contents.
    dz raises the cell before the tree sees it, so hull 0 with dz EYE
    reads the contents at the eyes of every origin in the cell.
    """
    planes = bsp.planes
    stack = [(bsp.hull1 if hull == 1 else bsp.hull0, cell)]
    while stack:
        node, c = stack.pop()
        if node < 0:
            yield (node if hull == 1 else bsp.leaves[-1 - node][0]), c
            continue
        pn, c0, c1 = bsp.clip[node] if hull == 1 else bsp.nodes[node][:3]
        nx, ny, nz, d = planes[pn]
        f, b = cell_split(c, (nx, ny, nz), d - nz * dz)
        if f:
            stack.append((c0, f))
        if b:
            stack.append((c1, b))


def _area2d(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _clip2d(subject, clipper):
    """Sutherland-Hodgman: the part of a polygon inside a convex one, or None."""
    sign = 1.0 if _area2d(clipper) >= 0 else -1.0
    out = list(subject)
    m = len(clipper)
    for i in range(m):
        if len(out) < 3:
            return None
        (ax, ay), (bx, by) = clipper[i], clipper[(i + 1) % m]
        ex, ey = bx - ax, by - ay
        ds = [sign * (ex * (p[1] - ay) - ey * (p[0] - ax)) for p in out]
        nxt = []
        for k in range(len(out)):
            p, q = out[k], out[(k + 1) % len(out)]
            dp, dq = ds[k], ds[(k + 1) % len(out)]
            if dp >= 0:
                nxt.append(p)
            if (dp >= 0) != (dq >= 0):
                t = dp / (dp - dq)
                nxt.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
        out = nxt
    return out if len(out) >= 3 else None


def _hull2d(points):
    """Convex hull in plan, counter-clockwise (monotone chain)."""
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in points))
    if len(pts) < 3:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _closest_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ax + dx * t, ay + dy * t


def _closest2d(a, b):
    """Plan gap between two convex polygons and the nearest point on each.

    Overlapping polygons are 0 apart at the centre of their overlap.
    """
    inter = _clip2d(a, b)
    if inter is not None and abs(_area2d(inter)) > 0.5:
        c = (sum(p[0] for p in inter) / len(inter), sum(p[1] for p in inter) / len(inter))
        return 0.0, c, c
    best = (math.inf, None, None)
    for src, dst, flip in ((a, b, False), (b, a, True)):
        for p in src:
            for i in range(len(dst)):
                q = _closest_seg(p[0], p[1], *dst[i], *dst[(i + 1) % len(dst)])
                g = math.hypot(p[0] - q[0], p[1] - q[1])
                if g < best[0]:
                    best = (g, q, p) if flip else (g, p, q)
    return best


def _closest_on_poly(p, poly):
    """The point of a convex plan polygon nearest p (p itself when inside)."""
    if point_in_poly_xy(p[0], p[1], poly):
        return p
    best, bd = None, math.inf
    for i in range(len(poly)):
        q = _closest_seg(p[0], p[1], *poly[i], *poly[(i + 1) % len(poly)])
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d < bd:
            best, bd = q, d
    return best


def _closest3d(p, poly, n):
    """Distance from a point to a convex planar polygon whose unit normal is n."""
    o = poly[0]
    s = (p[0] - o[0]) * n[0] + (p[1] - o[1]) * n[1] + (p[2] - o[2]) * n[2]
    q = (p[0] - n[0] * s, p[1] - n[1] * s, p[2] - n[2] * s)
    ax = max(range(3), key=lambda k: abs(n[k]))
    keep = [k for k in range(3) if k != ax]
    flat = [(v[keep[0]], v[keep[1]]) for v in poly]
    qx, qy = q[keep[0]], q[keep[1]]
    if point_in_poly_xy(qx, qy, flat):
        return abs(s)
    best = math.inf
    for i in range(len(poly)):
        u, v = poly[i], poly[(i + 1) % len(poly)]
        d = (v[0] - u[0], v[1] - u[1], v[2] - u[2])
        L2 = d[0] ** 2 + d[1] ** 2 + d[2] ** 2
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, sum(
            (p[k] - u[k]) * d[k] for k in range(3)) / L2))
        best = min(best, math.dist(p, (u[0] + d[0] * t, u[1] + d[1] * t, u[2] + d[2] * t)))
    return best


# ---- the water layer (#791) ----
#
# A swimmer moves through a volume, not over a floor. Its volume is every
# player origin that hull 1 admits and hull 0 puts in water: waterlevel 2,
# the waist under, which is where Argus_Waterlevel starts the swim block.
# Its air runs out where the EYES are under too (origin + 22, waterlevel
# 3): Argus_WaterMove gives air_finished = time + 12 only while they are
# out. Both are exact cells, not samples: the hull-1 leaves inside each
# water area, split down the hull-0 tree at the origin and again 22 above
# it. Water only, as navgen's swim links are; slime and lava are not swum.

AIR_TIME = 12.0        # air_finished = time + 12 (client.qc, Argus_WaterMove)
SWIM_SPEED = 300.0     # the bot's swim terminal speed (src/argus.qc swim block)
EYE = 22.0             # Argus_Waterlevel: waterlevel 3 is origin + 22 in liquid
# navgen 7d keeps a dry exit seat whose origin lies from 12 below to 44
# above the water surface, and leaves the last 48u before it to the vault
LIP_BELOW, LIP_ABOVE, LIP_REACH = 12.0, 44.0, 48.0
VAULT_UP = 290.0       # the deathmatch water vault's velocity_z (src/argus.qc)


def water_boxes(bsp, pad=2.0):
    """Hull-0 water leaf bounds, padded, merged until no two overlap."""
    boxes = [[[v - pad for v in leaf[2:5]], [v + pad for v in leaf[5:8]]]
             for leaf in bsp.leaves if leaf[0] == CONTENTS_WATER]
    merged = True
    while merged:
        merged = False
        out = []
        for mn, mx in boxes:
            for o in out:
                if all(mn[k] <= o[1][k] and o[0][k] <= mx[k] for k in range(3)):
                    o[0] = [min(mn[k], o[0][k]) for k in range(3)]
                    o[1] = [max(mx[k], o[1][k]) for k in range(3)]
                    merged = True
                    break
            else:
                out.append([mn, mx])
        boxes = out
    return [(tuple(mn), tuple(mx)) for mn, mx in boxes]


def swim_cells(bsp):
    """Exact swim cells: hull-1 empty, hull-0 water at the origin.

    Each is split again where the eyes leave the water, and carries
    "breath": True when the eyes of every origin in it are out (the
    contents there read above CONTENTS_WATER, as Argus_Waterlevel tests).
    """
    cells = []
    for mn, mx in water_boxes(bsp):
        start = cell_box(mn, mx)
        if start is None:
            continue
        for c1, piece in tree_cells(bsp, start, hull=1):
            if c1 != CONTENTS_EMPTY:
                continue
            for c0, wet in tree_cells(bsp, piece, hull=0):
                if c0 != CONTENTS_WATER:
                    continue
                for ce, part in tree_cells(bsp, wet, hull=0, dz=EYE):
                    vs = cell_vertices(part)
                    c = centroid(vs)
                    vol = cell_volume(part, c)
                    if vol < MIN_CELL:
                        continue
                    cells.append({
                        "faces": part, "verts": vs, "centre": c, "volume": vol,
                        "breath": ce > CONTENTS_WATER,
                        "mins": tuple(min(v[k] for v in vs) for k in range(3)),
                        "maxs": tuple(max(v[k] for v in vs) for k in range(3))})
    return cells


def _plane_key(n, d):
    for v in n:
        if v > 0:
            return (n[0], n[1], n[2], d), 0
        if v < 0:
            return (-n[0], -n[1], -n[2], -d), 1
    return None, 0


def cell_portals(cells, min_area=1.0):
    """Shared faces between cells: two faces on one plane, facing each other, overlapping."""
    groups = {}
    for i, c in enumerate(cells):
        for n, d, poly in c["faces"]:
            key, side = _plane_key(n, d)
            if key is not None:
                groups.setdefault(key, ([], []))[side].append((i, poly))
    portals = []
    for key, (pos, neg) in groups.items():
        if not pos or not neg:
            continue
        n, d = key[:3], key[3]
        ax = max(range(3), key=lambda k: abs(n[k]))
        keep = [k for k in range(3) if k != ax]

        def flat(poly):
            pts = [(p[keep[0]], p[keep[1]]) for p in poly]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return pts, (min(xs), min(ys), max(xs), max(ys))
        fpos = [(i, *flat(p)) for i, p in pos]
        fneg = [(j, *flat(p)) for j, p in neg]
        for i, a, ba in fpos:
            for j, b, bb in fneg:
                if i == j or ba[2] < bb[0] or bb[2] < ba[0] or ba[3] < bb[1] or bb[3] < ba[1]:
                    continue
                inter = _clip2d(a, b)
                if inter is None or abs(_area2d(inter)) < min_area:
                    continue
                poly = []
                for u, v in inter:
                    p = [0.0, 0.0, 0.0]
                    p[keep[0]], p[keep[1]] = u, v
                    p[ax] = (d - n[keep[0]] * u - n[keep[1]] * v) / n[ax]
                    poly.append(tuple(p))
                portals.append({"a": i, "b": j, "poly": poly, "n": n,
                                "centre": centroid(poly)})
    return portals


def _dijkstra(adj, sources):
    import heapq
    dist = dict(sources)
    heap = [(d, p) for p, d in sources.items()]
    heapq.heapify(heap)
    while heap:
        d, p = heapq.heappop(heap)
        if d > dist.get(p, math.inf):
            continue
        for q, w in adj.get(p, ()):
            if d + w < dist.get(q, math.inf):
                dist[q] = d + w
                heapq.heappush(heap, (d + w, q))
    return dist


def _air_budget(cells, portals, members):
    """The breath-hold a pool asks for, in units swum with the eyes under.

    dive: the farthest submerged point from air, the straight leg inside
    its own cell to the nearest point of a way out and portal centre to
    portal centre after that. crossing: the longest swim with the eyes
    under that getting from one air region to another cannot avoid,
    surfacing wherever the way allows. crossing is None with fewer than
    two air regions, dive when the pool has no submerged water; dive is
    inf when no submerged cell reaches air at all. A submerged face onto
    dry player space (open_faces) is air for the dive, since stepping out
    there puts the waist above water; the crossing is between surfaces.
    """
    members = set(members)
    inc = {}
    for k, p in enumerate(portals):
        if p["a"] in members:
            inc.setdefault(p["a"], []).append(k)
            inc.setdefault(p["b"], []).append(k)
    portals = list(portals)
    dry = set()
    for i in members:
        if cells[i]["breath"]:
            continue
        for fk in cells[i].get("open", ()):
            n, _, poly = cells[i]["faces"][fk]
            portals.append({"a": i, "b": None, "poly": poly, "n": n, "centre": centroid(poly)})
            inc.setdefault(i, []).append(len(portals) - 1)
            dry.add(len(portals) - 1)

    def groups(pred):
        parent = {i: i for i in members if pred(i)}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for k in {k for i in parent for k in inc.get(i, ())}:
            a, b = portals[k]["a"], portals[k]["b"]
            if a in parent and b in parent:
                parent[find(a)] = find(b)
        return {i: find(i) for i in parent}
    air = groups(lambda i: cells[i]["breath"])
    sub = groups(lambda i: not cells[i]["breath"])
    out = {"air_regions": len(set(air.values())), "dive": None, "dive_at": None,
           "crossing": None, "crossing_at": None, "sealed": 0}
    if not sub:
        return out
    border = {}            # portal -> air region, for portals onto air
    for i in sub:
        for k in inc.get(i, ()):
            o = portals[k]["b"] if portals[k]["a"] == i else portals[k]["a"]
            if o in air:
                border[k] = air[o]
    adj = {}
    for i in sub:
        ks = inc.get(i, ())
        for x in ks:
            for y in ks:
                if x != y:
                    adj.setdefault(x, []).append(
                        (y, math.dist(portals[x]["centre"], portals[y]["centre"])))
    dist = _dijkstra(adj, {k: 0.0 for k in list(border) + sorted(dry)})
    worst, worst_at = None, None
    for i in sub:
        exits = [k for k in inc.get(i, ()) if k in dist]
        if not exits:
            continue
        for v in cells[i]["verts"]:
            d = min(_closest3d(v, portals[k]["poly"], portals[k]["n"]) + dist[k]
                    for k in exits)
            if worst is None or d > worst:
                worst, worst_at = d, v
    out["dive"], out["dive_at"] = (math.inf if worst is None else worst), worst_at
    out["sealed"] = len({sub[i] for i in sub
                         if not any(k in dist for k in inc.get(i, ()))})
    # Crossing: the shortest submerged swim between every pair of air
    # regions, then the longest edge of their minimum spanning tree. A
    # swimmer may surface in any region on the way, so getting between
    # two surfaces costs the worst leg of the best chain of them, and the
    # spanning tree's longest edge is the worst of those over all pairs.
    comps = {}
    for k, r in border.items():
        i = portals[k]["a"] if portals[k]["a"] in sub else portals[k]["b"]
        comps.setdefault(sub[i], {}).setdefault(r, []).append(k)
    edges = {}
    for regions in comps.values():
        if len(regions) < 2:
            continue
        for r, ks in regions.items():
            dr = _dijkstra(adj, {k: 0.0 for k in ks})
            for r2, ks2 in regions.items():
                if r2 == r:
                    continue
                d, k2 = min(((dr.get(k, math.inf), k) for k in ks2), default=(math.inf, None))
                key = (min(r, r2), max(r, r2))
                if d < edges.get(key, (math.inf,))[0]:
                    k1 = min(ks, key=lambda k: math.dist(portals[k]["centre"],
                                                         portals[k2]["centre"]))
                    edges[key] = (d, portals[k1]["centre"], portals[k2]["centre"])
    tree = {r: r for r in set(air.values())}

    def root(x):
        while tree[x] != x:
            tree[x] = tree[tree[x]]
            x = tree[x]
        return x
    best = None
    for (r, r2), e in sorted(edges.items(), key=lambda kv: kv[1][0]):
        if root(r) != root(r2):
            tree[root(r)] = root(r2)
            best = e
    if best is not None:
        out["crossing"], out["crossing_at"] = best[0], (best[1], best[2])
    return out


def _vault_clear(bsp, w, f, surf, zf, apex):
    """The vault in hull 1: rise from the water, cross the lip under the apex, step down.

    Tries every crossing height from just over the exit floor up to the
    vault's apex above the surface, the way the runtime asks whether
    the lip sits under the apex rather than under the eyes. A curb
    between the water and the bank (e1m2's flooded court has several)
    is cleared exactly when some height in that range is open from the
    water's edge to the floor.
    """
    lo, hi = max(surf, zf) + 2.0, surf + apex
    z = surf - 2.0
    while z < lo:
        if bsp.h1(w[0], w[1], z) != CONTENTS_EMPTY:
            return False
        z += 4.0
    gap = math.hypot(f[0] - w[0], f[1] - w[1])
    k = max(1, int(gap // 4.0))
    h = lo
    while h <= hi:
        if bsp.h1(w[0], w[1], h) != CONTENTS_EMPTY:
            return False                      # the rise itself is capped here
        if all(bsp.h1(w[0] + (f[0] - w[0]) * i / k, w[1] + (f[1] - w[1]) * i / k, h)
               == CONTENTS_EMPTY for i in range(k + 1)):
            zz = h
            while zz > zf + 1.0 and bsp.h1(f[0], f[1], zz) == CONTENTS_EMPTY:
                zz -= 4.0
            if zz <= zf + 1.0 and bsp.h1(f[0], f[1], zf + 1.0) == CONTENTS_EMPTY:
                return True
        h += 4.0
    return False


def _toward(p, c, by=1.0):
    d = math.hypot(c[0] - p[0], c[1] - p[1])
    if d <= by:
        return (c[0], c[1])
    return (p[0] + (c[0] - p[0]) * by / d, p[1] + (c[1] - p[1]) * by / d)


def _frag_bounds(frag):
    """(min x, min y, max x, max y, min z, max z) of a fragment."""
    p = frag["poly"]
    return (min(v[0] for v in p), min(v[1] for v in p), max(v[0] for v in p),
            max(v[1] for v in p), min(v[2] for v in p), max(v[2] for v in p))


def exit_floor(bsp, frag):
    """Can a fragment take a swimmer out of the water? navgen 7d's dry rule.

    navgen calls an exit seat dry when hull 0 8u above its origin is not
    water, which admits a wading floor with the waist just under: the
    load_mesh "wet" flag (water at the origin itself) refuses it, and on
    e1m2 that refused the shore floor two swim links land on, 4u under
    the surface. Tested at classify_liquid's torso points, raised 8u.
    """
    if not frag.get("wet"):
        return True
    poly = frag["poly"]
    cx, cy, cz = centroid(poly)
    pts = [(cx, cy, cz)] + [(p[0] + (cx - p[0]) * 0.2, p[1] + (cy - p[1]) * 0.2,
                             p[2] + (cz - p[2]) * 0.2) for p in poly]
    return all(bsp.h0(x, y, z + 8.0) != CONTENTS_WATER for x, y, z in pts)


def vault_apex(gravity=GRAVITY):
    """How far a deathmatch water vault rises: VAULT_UP squared over twice gravity."""
    return VAULT_UP * VAULT_UP / (2.0 * gravity)


def exit_test(bsp, cell, frag, bounds=None, gravity=GRAVITY):
    """Is a dry floor fragment an exit from a breathable cell? (verdict, detail).

    verdict is "exit" or the first rule it fails: "band" (the floor is
    not 12 below to 44 above the surface), "reach" (more than 48u away
    in plan) or "vault" (hull 1 refuses the rise and step across). The
    surface is the top of the cell's air region (water_layer sets
    "surf"), because the breathable band is often split into thin cells
    and only the highest of them reaches the water's surface.
    """
    surf = cell.get("surf", cell["maxs"][2])
    bb = bounds or _frag_bounds(frag)
    if bb[5] < surf - LIP_BELOW or bb[4] > surf + LIP_ABOVE:
        return "band", None
    if (bb[0] > cell["maxs"][0] + LIP_REACH or bb[2] < cell["mins"][0] - LIP_REACH
            or bb[1] > cell["maxs"][1] + LIP_REACH or bb[3] < cell["mins"][1] - LIP_REACH):
        return "reach", None
    plan = cell.setdefault("_plan", _hull2d(cell["verts"]))
    if len(plan) < 3:
        return "reach", None
    fpoly = [(p[0], p[1]) for p in frag["poly"]]
    gap, fp, wp = _closest2d(fpoly, plan)
    if gap > LIP_REACH:
        return "reach", None
    pc = centroid([(p[0], p[1], 0.0) for p in plan])
    fc = centroid([(p[0], p[1], 0.0) for p in fpoly])
    # The nearest pair alone is not enough: where a whole edge of the
    # cell lies at the same gap it can land on a wall's corner (e1m2's
    # channel under the court wall). So try the water's edge every 8u.
    tries = [(gap, wp, fp)]
    if gap <= 0.0:
        tries.append((0.0, fp, fp))
    for i in range(len(plan)):
        (ax, ay), (bx, by) = plan[i], plan[(i + 1) % len(plan)]
        k = max(1, int(math.hypot(bx - ax, by - ay) // 8.0))
        for j in range(k):
            w0 = (ax + (bx - ax) * j / k, ay + (by - ay) * j / k)
            f0 = _closest_on_poly(w0, fpoly)
            g = math.hypot(f0[0] - w0[0], f0[1] - w0[1])
            if g <= LIP_REACH:
                tries.append((g, w0, f0))
    apex, band_only = vault_apex(gravity), True
    for g, w0, f0 in sorted(tries, key=lambda t: t[0]):
        w, f = _toward(w0, pc), _toward(f0, fc)
        zf = plane_z(frag["plane"], *f)
        if not surf - LIP_BELOW <= zf <= surf + LIP_ABOVE:
            continue
        band_only = False
        if _vault_clear(bsp, w, f, surf, zf, apex):
            return "exit", {"gap": g, "surf": surf, "z": zf, "at": (f[0], f[1], zf)}
    return ("band" if band_only else "vault"), None


def open_faces(bsp, cell):
    """Indices of a cell's faces that open onto dry player space.

    A point just outside a face that hull 1 admits is either more of the
    swim volume (water there too) or dry space a body can step into, where
    the waist is out and Argus_WaterMove restores the air. A pool with no
    such face and no exit is a pocket hull 1 closes on every side, like
    the 4u slivers of water inside some walls, which no body enters.
    """
    out = []
    for k, (fn, fd, poly) in enumerate(cell["faces"]):
        cx, cy, cz = centroid(poly)
        pts = [(cx, cy, cz)] + [(p[0] + (cx - p[0]) * 0.2, p[1] + (cy - p[1]) * 0.2,
                                 p[2] + (cz - p[2]) * 0.2) for p in poly]
        for x, y, z in pts:
            q = (x - fn[0], y - fn[1], z - fn[2])
            if bsp.h1(*q) == CONTENTS_EMPTY and bsp.h0(*q) != CONTENTS_WATER:
                out.append(k)
                break
    return out


def water_layer(bsp, frags, gravity=GRAVITY):
    """Swim volumes, their exits onto the floor mesh, and the air each asks for.

    Returns {"cells", "portals", "pools"}. A pool is one connected swim
    volume: its cells, volume, surface and floor heights, the wet floor
    fragments under it, its exits (fragment index -> exit_test detail),
    "openings" (faces onto dry player space; 0 is a sealed pocket) and
    _air_budget's figures.
    """
    cells = swim_cells(bsp)
    portals = cell_portals(cells)
    for c in cells:
        c["open"] = open_faces(bsp, c)
    parent = list(range(len(cells)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for p in portals:
        if cells[p["a"]]["breath"] and cells[p["b"]]["breath"]:
            parent[find(p["a"])] = find(p["b"])
    tops = {}
    for i, c in enumerate(cells):
        if c["breath"]:
            tops[find(i)] = max(tops.get(find(i), -math.inf), c["maxs"][2])
    for i, c in enumerate(cells):
        if c["breath"]:
            c["surf"] = tops[find(i)]
    for p in portals:
        parent[find(p["a"])] = find(p["b"])
    members = {}
    for i in range(len(cells)):
        members.setdefault(find(i), []).append(i)
    dry = [(fi, f, _frag_bounds(f)) for fi, f in enumerate(frags) if exit_floor(bsp, f)]
    pools = []
    for ms in sorted(members.values(), key=lambda m: -sum(cells[i]["volume"] for i in m)):
        pool = {"cells": ms, "volume": sum(cells[i]["volume"] for i in ms),
                "surface": max(cells[i]["maxs"][2] for i in ms),
                "surfaces": sorted({round(cells[i]["surf"]) for i in ms if cells[i]["breath"]},
                                   reverse=True),
                "bottom": min(cells[i]["mins"][2] for i in ms),
                "mins": tuple(min(cells[i]["mins"][k] for i in ms) for k in range(3)),
                "maxs": tuple(max(cells[i]["maxs"][k] for i in ms) for k in range(3))}
        pool.update(_air_budget(cells, portals, ms))
        exits = {}
        for i in ms:
            if not cells[i]["breath"]:
                continue
            for fi, f, bb in dry:
                if fi in exits:
                    continue
                verdict, detail = exit_test(bsp, cells[i], f, bb, gravity)
                if verdict == "exit":
                    exits[fi] = detail
        pool["exits"] = exits
        pool["openings"] = sum(len(cells[i]["open"]) for i in ms)
        pool["floors"] = sorted(
            fi for fi, f in enumerate(frags) if f.get("wet")
            and any(cell_contains(cells[i]["faces"], centroid(f["poly"]), 1.0) for i in ms))
        pools.append(pool)
    for i in range(len(cells)):
        cells[i]["pool"] = None
    for pi, pool in enumerate(pools):
        for i in pool["cells"]:
            cells[i]["pool"] = pi
    return {"cells": cells, "portals": portals, "pools": pools}


def locate_cell(cells, p, tol=1.0):
    for i, c in enumerate(cells):
        if all(c["mins"][k] - tol <= p[k] <= c["maxs"][k] + tol for k in range(3)) \
                and cell_contains(c["faces"], p, tol):
            return i
    return None


SWIM_WALK = 320.0      # navgen 7d: an exit seat at most 320u from the swimmer


def _walk_from(exits, fwd, target, goal):
    """A short plan walk from an exit point to a seat over walk and drop portals.

    exits: {fragment: (x, y)}; fwd: fragment -> [(next fragment, crossing
    segment)]. Each leg runs straight to the point of the next crossing
    that is shortest on through to the seat. A leg stays inside the
    convex fragment it crosses, so the length is that of a real walk,
    never shorter than the shortest. Returns (length, exit fragment) or
    None when nothing arrives within SWIM_WALK.
    """
    import heapq

    def via(p, s, e):
        # |p m| + |m goal| is convex along the crossing: ternary search
        lo, hi = 0.0, 1.0

        def at(t):
            return (s[0] + (e[0] - s[0]) * t, s[1] + (e[1] - s[1]) * t)

        def cost(t):
            m = at(t)
            return math.hypot(m[0] - p[0], m[1] - p[1]) + math.hypot(goal[0] - m[0],
                                                                     goal[1] - m[1])
        for _ in range(24):
            a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if cost(a) <= cost(b):
                hi = b
            else:
                lo = a
        return at((lo + hi) / 2)
    def left(p):
        return math.hypot(goal[0] - p[0], goal[1] - p[1])
    # A*: ordered by the walk so far plus the straight line still to go,
    # so each fragment is first left from the crossing that best serves
    # this seat rather than the one nearest the water
    heap = [(left(p), 0.0, fi, p, fi) for fi, p in exits.items()]
    heapq.heapify(heap)
    best = set()
    while heap:
        est, d, fi, p, src = heapq.heappop(heap)
        if est > SWIM_WALK:
            break
        if fi in best:
            continue
        best.add(fi)
        if fi == target:
            return est, src
        for g, (s, e) in fwd.get(fi, ()):
            if g not in best:
                m = via(p, s, e)
                dm = d + math.hypot(m[0] - p[0], m[1] - p[1])
                heapq.heappush(heap, (dm + left(m), dm, g, m, src))
    return None


def swim_crosscheck(bsp, frags, layer, doc, portals=None, gravity=GRAVITY):
    """Judge every shipped swim link against the water layer.

    A link (a, b) needs a's seat in a swim volume (navgen's own probe, 8u
    above the seat, as well as the seat itself). It is "confirmed" when
    b's seat lies on one of that volume's exit fragments, and "walk from
    an exit" when b is reached on foot (mesh walk and drop portals) from
    one within navgen's 320u: dm3's trench seats stand on the floor a
    step below the sill the vault lands on. Otherwise the verdict names
    what failed: "dry seat" (a is in no swim volume), "exit off mesh" (b
    is on no fragment), or the exit test's own rule for b's fragment
    ("band", "reach", "vault") at its most forgiving cell of a's pool.
    """
    nodes = [tuple(n) for n in doc["nodes"]]
    cells, pools = layer["cells"], layer["pools"]
    if portals is None:
        portals = build_portals(bsp, frags)
    fwd = {}
    for p in portals:
        fwd.setdefault(p["a"], []).append((p["b"], (p["s"], p["e"])))
    rows = []
    for row in doc.get("swimlinks", []):
        a, b = row[0], row[1]
        pa = nodes[a]
        ci = locate_cell(cells, pa)
        if ci is None:
            ci = locate_cell(cells, (pa[0], pa[1], pa[2] + 8.0))
        fb = locate(frags, *nodes[b], ztol=30.0)
        rec = {"a": a, "b": b, "pool": None if ci is None else cells[ci]["pool"], "frag": fb,
               "via": None}
        if ci is None:
            rec["verdict"] = "dry seat"
        elif fb is None:
            rec["verdict"] = "exit off mesh"
        elif fb in pools[rec["pool"]]["exits"]:
            rec["verdict"] = "confirmed"
        else:
            exits = {fi: e["at"][:2] for fi, e in pools[rec["pool"]]["exits"].items()}
            walk = _walk_from(exits, fwd, fb, nodes[b])
            if walk is not None:
                rec["verdict"], rec["via"], rec["walk"] = "walk from an exit", walk[1], walk[0]
            else:
                order = {"vault": 0, "reach": 1, "band": 2}
                seen = [exit_test(bsp, cells[i], frags[fb], gravity=gravity)[0]
                        for i in pools[rec["pool"]]["cells"] if cells[i]["breath"]]
                rec["verdict"] = min(seen, key=lambda v: order.get(v, 3)) if seen else "no air"
        rows.append(rec)
    return rows


def _water_report(bsp, frags, doc, show=6, portals=None, gravity=GRAVITY):
    layer = water_layer(bsp, frags, gravity)
    pools, cells = layer["pools"], layer["cells"]
    budget = AIR_TIME * SWIM_SPEED
    sealed = [p for p in pools if not p["openings"] and not p["exits"]]
    print(f"  water layer: {len(pools)} swim volume(s), {len(cells)} cells, "
          f"{sum(len(p['exits']) for p in pools)} exits onto the mesh; air {AIR_TIME:.0f} s "
          f"at an assumed {SWIM_SPEED:.0f} u/s (the bot's swim terminal speed) = "
          f"{budget:.0f}u with the eyes under")
    minor = [p for p in pools if p not in sealed and not p["exits"]
             and (p["dive"] is None or p["dive"] <= 32.0)]
    if sealed:
        print(f"    {len(sealed)} sealed pocket(s), hull 1 closed on every side so no body "
              f"gets in: {sum(p['volume'] for p in sealed) / 1e6:.3f}M cu in all")
    if minor:
        print(f"    {len(minor)} film(s) or puddle(s) with no exit onto the mesh and every "
              f"point within 32u of air, not listed: "
              f"{sum(p['volume'] for p in minor) / 1e6:.3f}M cu in all")
    shown = [(pi, p) for pi, p in enumerate(pools) if p not in sealed and p not in minor]
    for pi, p in shown[:show]:
        mn, mx = p["mins"], p["maxs"]
        surfs = ", ".join(str(s) for s in p["surfaces"][:4]) or "none"
        print(f"    pool {pi}: ({mn[0]:.0f} {mn[1]:.0f}) to ({mx[0]:.0f} {mx[1]:.0f}), origins "
              f"z {p['bottom']:.0f} to {p['surface']:.0f}, {len(p['cells'])} cells, "
              f"{p['volume'] / 1e6:.2f}M cu; {len(p['exits'])} exits, "
              f"{len(p['floors'])} wet floors, {p['air_regions']} air region(s) at z {surfs}")
        if p["dive"] is None:
            print("      shallow: the eyes clear the surface everywhere in it")
        elif p["dive"] == math.inf:
            print("      NO AIR: no submerged cell reaches a breathable one")
        else:
            v = p["dive_at"]
            line = (f"      longest dive to air {p['dive']:.0f}u ({p['dive'] / SWIM_SPEED:.1f} s, "
                    f"{2 * p['dive'] / SWIM_SPEED:.1f} s there and back) from "
                    f"({v[0]:.0f} {v[1]:.0f} {v[2]:.0f})")
            if p["crossing"] is not None:
                c = p["crossing"]
                line += (f"; longest crossing between surfaces {c:.0f}u "
                         f"({c / SWIM_SPEED:.1f} s)")
            longest = max(2 * p["dive"], p["crossing"] or 0.0)
            line += (f"; {'within' if longest <= budget else 'OVER'} the {AIR_TIME:.0f} s budget")
            print(line)
            if p["sealed"]:
                print(f"      {p['sealed']} submerged component(s) with no way to air")
        lips = sorted((kv for kv in p["exits"].items() if kv[1]["z"] >= kv[1]["surf"]),
                      key=lambda kv: (kv[1]["gap"], kv[0]))
        wading = sorted((kv for kv in p["exits"].items() if kv[1]["z"] < kv[1]["surf"]),
                        key=lambda kv: (kv[1]["gap"], kv[0]))
        if p["exits"]:
            print(f"      exits: {len(lips)} over a lip, {len(wading)} wading out "
                  f"(a floor under the surface whose waist clears it)")
        for fi, e in (lips + wading)[:4]:
            at = e["at"]
            print(f"      exit f{fi} at ({at[0]:.0f} {at[1]:.0f} {at[2]:.0f}), "
                  f"{at[2] - e['surf']:+.0f} against the surface, {e['gap']:.0f}u from the water")
    if len(shown) > show:
        print(f"    ... {len(shown) - show} more, the largest "
              f"{shown[show][1]['volume'] / 1e6:.3f}M cu")
    rows = swim_crosscheck(bsp, frags, layer, doc, portals, gravity)
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    backed = ("confirmed", "walk from an exit")
    served = {r["pool"] for r in rows if r["verdict"] in backed}
    print(f"  shipped swim links ({len(rows)}) against the volumes: "
          + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"))
    nodes = doc["nodes"]
    for r in rows:
        if r["verdict"] == "confirmed":
            continue
        tail = (f"walk from an exit, {r['walk']:.0f}u from exit f{r['via']}"
                if r["verdict"] == "walk from an exit" else r["verdict"])
        where = "" if r["pool"] is None else f" (pool {r['pool']})"
        print(f"    n{r['a']} {tuple(round(v) for v in nodes[r['a']])} -> "
              f"n{r['b']} {tuple(round(v) for v in nodes[r['b']])}{where}: {tail}")
    unserved = [pi for pi, p in enumerate(pools) if p["exits"] and pi not in served
                and p["dive"] is not None]
    print(f"  deep pools with exits that no shipped swim link uses: {len(unserved)}"
          + (f" (pool {', '.join(str(pi) for pi in unserved[:8])})" if unserved else ""))
    return layer, rows


# ---- the time layer (#791) ----
#
# A plat or a door is a floor or a wall depending on when a body arrives:
# e1m1's *3 and dm2's *31 and *34 are floors only while parked. So every
# func_plat, func_door and func_train gets the positions stock QC moves it
# between, how long it holds each, and the times inside one cycle it is
# there. Each position carries its box (a wall while present) and its deck
# (the top face in origin space, a floor while present). func_door_secret
# stays where it was built: its two-stage move is not modelled.

MOVER_CLASSES = ("func_plat", "func_door", "func_train")
PLAT_WAIT = 3.0        # plat_hit_top: nextthink = ltime + 3


def _qnum(e, key, default):
    """A key read the way the spawn functions read it: missing or zero means default."""
    try:
        v = float(e.get(key, 0) or 0)
    except ValueError:
        v = 0.0
    return v or default


def _leg(dist, speed):
    """SUB_CalcMove's travel time, which never runs under 0.1 s."""
    return max(0.1, dist / speed)


def _state(name, mn, mx, dwell):
    deck = [(mn[0] - 16, mn[1] - 16, mx[2] + 24), (mx[0] + 16, mn[1] - 16, mx[2] + 24),
            (mx[0] + 16, mx[1] + 16, mx[2] + 24), (mn[0] - 16, mx[1] + 16, mx[2] + 24)]
    return {"name": name, "mins": tuple(mn), "maxs": tuple(mx), "dwell": dwell,
            "deck": deck, "present": []}


def _shift(mn, mx, d, t):
    return (tuple(mn[k] + d[k] * t for k in range(3)), tuple(mx[k] + d[k] * t for k in range(3)))


def _timeline(mv, phases):
    """Record each state's windows from (state name or None while moving, t0, t1)."""
    mv["timeline"] = phases
    by = {s["name"]: s for s in mv["states"]}
    for name, t0, t1 in phases:
        if name is not None:
            by[name]["present"].append((t0, t1))


def _plat(e, mn, mx):
    h = entity_number(e, "height") or (mx[2] - mn[2] - SPAWN_SETTLING["plat_default_inset_u"])
    speed = _qnum(e, "speed", 150.0)
    T = _leg(abs(h), speed)
    top = _state("top", mn, mx, PLAT_WAIT)
    bottom = _state("bottom", *_shift(mn, mx, (0.0, 0.0, -1.0), h), None)
    mv = {"cls": "func_plat", "speed": speed, "travel": T, "states": [bottom, top],
          "spawn": "top" if e.get("targetname") else "bottom", "rest": "bottom",
          "trigger": "targeted" if e.get("targetname") else "touch",
          "period": 2 * T + PLAT_WAIT}
    # plats.qc: a rider at the bottom starts it up; it holds the top 3 s
    # (one more after each touch there) and comes back down to rest. A
    # targeted plat waits at the top for its trigger, then does the same.
    _timeline(mv, [(None, 0.0, T), ("top", T, T + PLAT_WAIT),
                   (None, T + PLAT_WAIT, 2 * T + PLAT_WAIT), ("bottom", 2 * T + PLAT_WAIT, None)])
    return mv


def _door(e, mn, mx, sf):
    angle = entity_number(e, "angle")
    vertical = angle in (-1.0, -2.0)
    if vertical:
        d = (0.0, 0.0, 1.0 if angle == -1.0 else -1.0)  # subs.qc SetMovedir
    else:
        r = math.radians(angle)
        d = (math.cos(r), math.sin(r), 0.0)
    lip = entity_number(e, "lip") or SPAWN_SETTLING["door_default_lip_u"]
    travel = abs(sum(d[k] * (mx[k] - mn[k]) for k in range(3))) - lip
    if travel <= 0:
        return None
    speed = _qnum(e, "speed", 100.0)
    wait = _qnum(e, "wait", 3.0)
    if sf & (8 | 16):
        wait = -1.0                                     # key doors never return
    toggle = bool(sf & 32)
    T = _leg(travel, speed)
    hold = None if (wait < 0 or toggle) else wait
    moved = _shift(mn, mx, d, travel)
    if sf & 1:
        # DOOR_START_OPEN: spawns a travel away and closes when triggered
        rest, other = _state("open", *moved, None), _state("shut", mn, mx, hold)
    else:
        rest, other = _state("shut", mn, mx, None), _state("open", *moved, hold)
    trigger = ("key" if sf & (8 | 16) else "targeted" if e.get("targetname")
               else "shot" if _qnum(e, "health", 0.0) else "touch")
    mv = {"cls": "func_door", "speed": speed, "travel": T, "states": [rest, other],
          "spawn": rest["name"], "rest": rest["name"], "trigger": trigger,
          "wait": wait, "toggle": toggle,
          "period": None if hold is None else 2 * T + hold,
          "vertical": vertical}
    if hold is None:
        _timeline(mv, [(None, 0.0, T), (other["name"], T, None)])
    else:
        _timeline(mv, [(None, 0.0, T), (other["name"], T, T + hold),
                       (None, T + hold, 2 * T + hold), (rest["name"], 2 * T + hold, None)])
    return mv


def _train(e, mn, mx, corners):
    speed = _qnum(e, "speed", 100.0)
    size = tuple(mx[k] - mn[k] for k in range(3))
    seq, names = [], []
    c = corners.get(e.get("target", ""))
    while c is not None and c.get("targetname") not in names:
        seq.append(c)
        names.append(c.get("targetname"))
        c = corners.get(c.get("target", ""))
    if len(seq) < 2:
        return None

    def org(c):
        try:
            return tuple(float(v) for v in c.get("origin", "0 0 0").split()[:3])
        except ValueError:
            return (0.0, 0.0, 0.0)

    def hold(c):
        # train_wait: a corner's wait, or the 0.1 s think when it has none
        w = _qnum(c, "wait", 0.0)
        return w if w > 0 else (0.0 if w < 0 else 0.1)
    loop = names.index(c.get("targetname")) if c is not None else None
    states = []
    for k, corner in enumerate(seq):
        o = org(corner)
        states.append(_state(f"corner {names[k]}", o, tuple(o[j] + size[j] for j in range(3)),
                             hold(corner)))
    mv = {"cls": "func_train", "speed": speed, "states": states,
          "spawn": states[0]["name"], "trigger": "targeted" if e.get("targetname") else "auto",
          "rest": states[0]["name"] if e.get("targetname") else None}
    # plats.qc func_train_find puts the min corner on the first path_corner
    # and train_next leaves 0.1 s later (untargeted); each corner then holds
    # its own wait. A chain that does not loop stops at its last corner.
    phases, t, depart = [(states[0]["name"], 0.0, 0.1)], 0.1, {0: 0.1}
    order = list(range(1, len(seq))) + ([] if loop is None else [loop])
    prev = 0
    for k in order:
        leg = _leg(math.dist(org(seq[prev]), org(seq[k])), speed)
        phases.append((None, t, t + leg))
        t += leg
        if loop is None and k == len(seq) - 1:
            phases.append((states[k]["name"], t, None))
            break
        phases.append((states[k]["name"], t, t + states[k]["dwell"]))
        t += states[k]["dwell"]
        depart.setdefault(k, t)
        prev = k
    # one lap: from leaving the corner the loop closes on to leaving it again
    mv["period"] = None if loop is None else t - depart[loop]
    mv["travel"] = max(p[2] - p[1] for p in phases if p[0] is None)
    _timeline(mv, phases)
    if loop == 0:
        # the 0.1 s at spawn is the first lap's start, not a second visit
        states[0]["present"] = states[0]["present"][1:]
    return mv


def movers(bsp, deathmatch=True):
    """Every func_plat, func_door and func_train with its positions and timing.

    Each mover: cls, model, speed, travel (seconds for its longest move),
    states (name, mins, maxs, dwell, deck, present), spawn (the state it
    spawns in), rest (the state it waits in for a trigger, or None for a
    train that runs from spawn), period (seconds for one cycle back to
    rest or round its loop; None when it never comes back), trigger and
    timeline. Times run from the moment it leaves rest (from spawn for a
    train); a window ending in None lasts until something moves it.
    """
    ents = bsp.entities()
    corners = {e.get("targetname"): e for e in ents if e.get("classname") == "path_corner"}
    out = []
    for e in ents:
        cls = e.get("classname", "")
        m = e.get("model", "")
        if cls not in MOVER_CLASSES or not m.startswith("*"):
            continue
        sf = brush_spawnflags(e)
        if deathmatch and sf & SPAWN_SETTLING["not_deathmatch_flag"]:
            continue
        mdl = bsp.models[int(m[1:])]
        mn, mx = tuple(mdl[0:3]), tuple(mdl[3:6])
        if cls == "func_plat":
            mv = _plat(e, mn, mx)
        elif cls == "func_door":
            mv = _door(e, mn, mx, sf)
        else:
            mv = _train(e, mn, mx, corners)
        if mv is not None:
            mv["model"] = m
            out.append(mv)
    return out


def _spawn_state(mv):
    return next(s for s in mv["states"] if s["name"] == mv["spawn"])


def _state_grade(world, s, gravity):
    """One ledge point in one mover state: walled, bridged, or the air verdict."""
    x, y, z = s["pos"]
    nx, ny = s["n"]
    px, py = x + nx * 1.5, y + ny * 1.5
    if world.h1(x, y, z + 1.0) != CONTENTS_EMPTY or world.h1(px, py, z + 1.0) != CONTENTS_EMPTY:
        return dict(s, verdict="walled", out={})
    if fall_to(world, px, py, z + 1.0, maxdrop=STEP + 2.0) is not None:
        return dict(s, verdict="bridged", out={})
    return judge_ledge(world, dict(s), gravity)


def _deck_points(world, st, spacing=16.0):
    """Ledge points along a state's deck edges: open air past them, no floor within a step."""
    poly = st["deck"]
    out = []
    for ei, (p, q, u, n, ln) in enumerate(_edges_xy(poly)):
        k = max(1, int(ln // spacing))
        z = poly[0][2]
        for i in range(k):
            t = (i + 0.5) * ln / k
            x, y = p[0] + u[0] * t, p[1] + u[1] * t
            if world.h1(x - n[0] * 4.0, y - n[1] * 4.0, z + 1.0) != CONTENTS_EMPTY:
                continue                      # no room to stand on the deck here
            px, py = x + n[0] * 1.5, y + n[1] * 1.5
            if world.h1(px, py, z + 1.0) != CONTENTS_EMPTY:
                continue
            if fall_to(world, px, py, z + 1.0, maxdrop=STEP + 2.0) is not None:
                continue
            out.append({"frag": None, "edge": ("deck", st["name"], ei), "pos": (x, y, z),
                        "n": n, "u": u})
    return out


def mover_ledges(bsp, frags, mvs=None, spacing=16.0, near=64.0, gravity=GRAVITY):
    """Air-layer verdicts for ledges beside each mover, once per mover state.

    "beside" is every world-mesh ledge point (walls and secret doors in
    place, no movers) within `near` of the mover's swept box in plan and
    no more than a jump below it. Each is graded in a world holding this
    mover at one state and every other mover at its spawn state: walled
    (the mover fills the step or the spot), bridged (a floor within a step
    past the edge, the mover's deck), or air_layer's verdict. "deck" holds
    the ledge points of the mover's own deck in each state. A flight that
    lands on this mover reports it in "on".
    """
    mvs = movers(bsp) if mvs is None else mvs
    statics = [b for b in brush_boxes(bsp) if b[0] not in MOVER_CLASSES]
    cands = ledge_points(WithBrushes(bsp, statics), frags, spacing)
    spawn = [(mv["cls"], _spawn_state(mv)["mins"], _spawn_state(mv)["maxs"]) for mv in mvs]
    out = []
    for mi, mv in enumerate(mvs):
        label = f"{mv['cls']} {mv['model']}"
        lo = [min(s["mins"][k] for s in mv["states"]) for k in range(3)]
        hi = [max(s["maxs"][k] for s in mv["states"]) for k in range(3)]
        beside = [s for s in cands
                  if lo[0] - 16 - near <= s["pos"][0] <= hi[0] + 16 + near
                  and lo[1] - 16 - near <= s["pos"][1] <= hi[1] + 16 + near
                  and s["pos"][2] >= lo[2] - 80.0]
        others = spawn[:mi] + spawn[mi + 1:]
        rec = {"mover": mv, "beside": [dict(s, verdicts={}, on={}) for s in beside], "deck": {}}
        for st in mv["states"]:
            world = WithBrushes(bsp, statics + others + [(label, st["mins"], st["maxs"])])
            for b in rec["beside"]:
                g = _state_grade(world, b, gravity)
                b["verdicts"][st["name"]] = g["verdict"]
                b["on"][st["name"]] = any(r.get("on") == label for r in g["out"].values())
            rec["deck"][st["name"]] = [judge_ledge(world, s, gravity)
                                       for s in _deck_points(world, st, spacing)]
        rec["changed"] = sum(1 for b in rec["beside"] if len(set(b["verdicts"].values())) > 1)
        out.append(rec)
    return out


def _fmt_present(mv, st):
    parts = []
    if st["name"] == mv["spawn"]:
        parts.append("spawn")
    if st["name"] == mv.get("rest"):
        parts.append("rest")
    for t0, t1 in st["present"]:
        if st["name"] == mv.get("rest") and t1 is None:
            continue
        if t1 is None:
            parts.append(f"from {t0:.1f} s on")
        elif mv.get("period"):
            parts.append(f"{t1 - t0:.1f} s of each {mv['period']:.1f} s cycle")
        else:
            parts.append(f"{t0:.1f} to {t1:.1f} s")
    return f"{st['name']} ({', '.join(parts)})"


def _count_line(verdicts):
    order = ("walled", "bridged", "danger", "risky", "momentum", "safe")
    c = {k: sum(1 for v in verdicts if v == k) for k in order}
    return ", ".join(f"{k} {c[k]}" for k in order if c[k]) or "none"


def _mover_report(bsp, frags, gravity, show=12):
    mvs = movers(bsp)
    if not mvs:
        print("  movers: none in deathmatch")
        return []
    recs = mover_ledges(bsp, frags, mvs, gravity=gravity)
    kinds = {k: sum(1 for m in mvs if m["cls"] == k) for k in MOVER_CLASSES}

    def count_of(k, word):
        return f"{kinds[k]} {word}{'' if kinds[k] == 1 else 's'}"
    print(f"  movers: {len(mvs)} in deathmatch ({count_of('func_plat', 'plat')}, "
          f"{count_of('func_door', 'door')}, {count_of('func_train', 'train')}), "
          f"each graded at every "
          f"rest and travel end with the others at spawn; "
          f"{sum(1 for r in recs if r['changed'])} change a ledge verdict with their state")
    ranked = sorted(recs, key=lambda r: (-r["changed"], -len(r["beside"]), r["mover"]["model"]))
    listed = [r for r in ranked if r["changed"]][:show]
    rest = [r for r in ranked if r not in listed and (r["beside"] or any(r["deck"].values()))]
    for r in listed:
        mv = r["mover"]
        how = (f"legs up to {mv['travel']:.1f} s at {mv['speed']:.0f} u/s"
               if mv["cls"] == "func_train" else
               f"{mv['travel']:.1f} s each way at {mv['speed']:.0f} u/s")
        print(f"    {mv['model']} {mv['cls']}, {mv['trigger']}: "
              + "; ".join(_fmt_present(mv, st) for st in mv["states"][:4])
              + (f"; +{len(mv['states']) - 4} corners" if len(mv["states"]) > 4 else "")
              + f"; {how}")
        names = [st["name"] for st in mv["states"]]
        print(f"      {len(r['beside'])} ledge points beside it: " + " | ".join(
            f"{n}: {_count_line([b['verdicts'][n] for b in r['beside']])}" for n in names[:4])
            + f"; {r['changed']} change with the state")
        print("      deck edges: " + " | ".join(
            f"{n}: {_count_line([s['verdict'] for s in r['deck'][n]])}" for n in names[:4]))
    if rest:
        print(f"    {len(rest)} more with ledges beside them or on their decks, the same in "
              f"every state or past the first {show}: "
              + ", ".join(r["mover"]["model"] for r in rest[:16])
              + (" ..." if len(rest) > 16 else ""))
    return recs


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
                    help="with --air: world hull only, ignoring walls, doors and plats "
                         "(and the per-state mover report)")
    ap.add_argument("--no-water", action="store_true",
                    help="with --audit: skip the swim volumes and the swim-link cross-check")
    ap.add_argument("--no-movers", action="store_true",
                    help="with --air: skip grading the ledges beside each mover per state")
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
        for why, label in OFFMESH_LABELS:
            rows = [o for o in r["offmesh"] if o["why"] == why]
            print(f"    {label}: {len(rows)}")
            if why == "liquid":
                continue
            for o in rows[:8]:
                n = nodes[o["seat"]]
                bits = [] if o["nz"] is None else [f"floor normal z {o['nz']:.2f}"]
                bits.append("no fragment within 64u" if o["near"] is None else
                            f"nearest fragment {o['near']:.0f}u away")
                print(f"      n{o['seat']} {tuple(round(v) for v in n)} {', '.join(bits)}")
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
        if not a.no_water:
            _water_report(bsp, frags, doc,
                          gravity=a.gravity if a.gravity else map_gravity(a.bsp))
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
    if not (a.no_brushes or a.no_movers):
        _mover_report(bsp, frags, gravity)
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
