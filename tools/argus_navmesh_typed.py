"""Mesh-native typed links for the navmesh graph (#790).

EXPERIMENTAL (2026-11-18). argus_navmesh_graph inherits every typed link
from the shipped graph with its exact seats, so it cannot stand alone on a
map navgen has not solved. This module finds the links from the map
itself, judged by the rules the runtime executes them under:

- Jumps. A plain jump hop fires where a hull-0 point trace 32u ahead
  (4u above the origin to 40u below) finds no floor, only within 96u of
  the seat it was minted from (#665) and 48u or more short of the landing
  seat, turns onto the line to the landing and leaves at 270 u/s. A link
  stands when that launch, flown through hull 1 and the solid brush
  entities at spawn (the air layer's fly), touches no wall or ceiling and
  lands dry on a floor from which the landing seat is a mesh walk. Its
  approach speed follows navgen: the lowest staged speed whose whole
  -5..+15 firing window lands, else the 250 to 320 fallback window, else
  no link.
- Climbs. A jump hop to a seat more than a step up fires a standing jump
  within 72u of it. A link stands when the rise is under the jump apex
  (navgen's 44u at gravity 800), the body has headroom to the lip, and
  the upper floor begins before any void.
- Drop arcs. A run off a ledge at the routed drop commit's 240 u/s and at
  run speed must both land dry where the target seat is a walk, with the
  physics guard's straight-down probes finding floor (not a void or a
  liquid) past the lip. The walker's own straight-fall drops are refused
  when the 240 u/s run-off lands in lava or slime.
- Lifts. func_plat pads by navgen's 5b rules: travel is the height key or
  size_z - 8; the boarding pad is the nearest seat outside the swept
  column, at most 96u out, standing within 20u of the slab's seated top;
  the exit pad is the nearest seat to the top centre within 120u, height
  counted double.
- Teleporters. Each trigger_teleport gets a seat on the floor inside its
  box (arriving there sends the body away) and one where the destination
  drops it, stock teleport_touch's origin + 27.

Falls stop at navgen's DROPMAX 200 at gravity 800, scaled by 800/g on
other maps because the fall-damage rule keys on the landing speed
(velocity_z below -650), and never past the 280u the physics guard traces
down for a floor. Rocket jumps, sprints, swims and trains are not found
here: no worst-spawn reach on dm4 depends on them.
"""
from __future__ import annotations

import collections
import heapq
import math
from dataclasses import dataclass, field

import argus_navmesh as nm
from argus_jump_anchor import LIMIT as ANCHOR, launch_distance

STEP = nm.STEP
DROPMAX = nm.DROPMAX
JUMPVEL = nm.JUMPVEL
RUN = nm.RUN
DROP_STEP = 240.0      # the routed DROP commit's firm step (argus.qc)
LOOKAHEAD = 32.0       # a plain jump hop's launch lookahead (argus.qc)
PROBE_UP, PROBE_DOWN = 4.0, 40.0
MIN_LANDING = 48.0     # the hop refuses to fire inside 48u of its landing
CLIMB_REACH = 72.0     # a climb fires within 72u of a seat above
CLIMB_RISE = 44.0      # navgen's climb ceiling at gravity 800
GUARD_DEPTH = 280.0    # Argus_MoveHazard traces this far down for a floor
GUARD_REACH = 52.0     # and probes up to this far ahead
LINK_MAX = 340.0
WINDOW = (-5, 0, 5, 10, 15)
STAGED = range(40, 281, 5)
FALLBACK = range(250, 321, 5)
COARSE = (90.0, 150.0, 220.0, 280.0)
LEDGE_NEAR = ANCHOR + LOOKAHEAD + 16.0
LETHAL = (nm.CONTENTS_LAVA, nm.CONTENTS_SLIME)
SAVING_RATIO, SAVING_SLACK = 1.5, 128.0
PER_SOURCE = 2


def drop_limit(gravity):
    """The deepest fall a link may ask for, in units of origin height."""
    return min(DROPMAX * nm.GRAVITY / gravity, GUARD_DEPTH - 24.0)


def climb_limit(gravity):
    """navgen's 44u climb at gravity 800, kept under the apex elsewhere."""
    return min(CLIMB_RISE, JUMPVEL * JUMPVEL / (2.0 * gravity) - 1.5)


@dataclass
class Context:
    """What every finder needs: the map, the mesh, and the mesh walker.

    walk(a, b) is argus_navmesh_graph's mesh walker bound to this map,
    returning "walk", "drop" or None; floors(x, y) lists mesh floor
    heights (origin space) under a point; locate(x, y, z) names the
    fragment under it.
    """
    bsp: object
    world: object
    frags: list
    floors: object
    locate: object
    walk: object
    gravity: float = nm.GRAVITY
    tboxes: list = field(default_factory=list)

    @property
    def drop_limit(self):
        return drop_limit(self.gravity)

    @property
    def climb_limit(self):
        return climb_limit(self.gravity)

    def floor_near(self, x, y, z, tol=STEP):
        fl = [h for h in self.floors(x, y) if abs(h - z) <= tol]
        return min(fl, key=lambda h: abs(h - z)) if fl else None


# ---- the runtime's own tests ----

def probe_fires(bsp, x, y, z):
    """argus.qc's plain-jump probe at a point already LOOKAHEAD ahead.

    traceline(p + '0 0 4', p - '0 0 40', TRUE, self) must run its whole
    length: a start in solid refuses the hop like a floor does. Liquids
    do not stop a traceline, so lava under the lip still fires it.
    """
    h = z + PROBE_UP
    while h >= z - PROBE_DOWN:
        if bsp.h0(x, y, h) == nm.CONTENTS_SOLID:
            return False
        h -= 2.0
    return bsp.h0(x, y, z - PROBE_DOWN) != nm.CONTENTS_SOLID


def guard_floor(bsp, x, y, z):
    """What Argus_MoveHazard sees under a probe: "floor", "liquid" or "void"."""
    fz = bsp.floor_under(x, y, z, GUARD_DEPTH)
    if fz is None:
        return "void"
    return "liquid" if bsp.h0(x, y, fz + 2.0) in LETHAL else "floor"


def launch_point(ctx, a, u, limit):
    """Where a plain jump hop from seat a, running along u, fires.

    Walks a's floor in 2u steps (each within a step of the last) and
    returns the first origin whose probe LOOKAHEAD ahead finds nothing,
    or None when the floor runs out or nothing fires within limit.
    """
    x0, y0, z = a
    t = 0.0
    while t <= limit:
        x, y = x0 + u[0] * t, y0 + u[1] * t
        nz = ctx.floor_near(x, y, z)
        if nz is None:
            return None
        z = nz
        if probe_fires(ctx.bsp, x + u[0] * LOOKAHEAD, y + u[1] * LOOKAHEAD, z):
            return (x, y, z)
        t += 2.0
    return None


def first_lip(ctx, a, u, limit):
    """The last point of a's floor along u before it falls away, or None."""
    x0, y0, z = a
    t, last = 0.0, None
    while t <= limit:
        x, y = x0 + u[0] * t, y0 + u[1] * t
        nz = ctx.floor_near(x, y, z)
        if nz is None:
            return last
        z, last = nz, (x, y, nz)
        t += 2.0
    return None


def flight(ctx, p, v, speed, vz):
    return nm.fly(ctx.world, p[0], p[1], p[2], v[0], v[1], speed, vz, ctx.gravity)


def landing(ctx, p, v, speed, vz, target):
    """Where a clean flight lands, when the target is a walk from there.

    Clean means the arc touched no wall or ceiling, landed dry on world
    floor (not a brush entity, which moves or may not be there), on the
    mesh, within the fall limit.
    """
    r = flight(ctx, p, v, speed, vz)
    if r["kind"] != "floor" or r["clip"] or r.get("on"):
        return None
    if r["fall"] > ctx.drop_limit:
        return None
    x, y, z = r["pos"]
    fz = ctx.floor_near(x, y, z, tol=3.0)
    if fz is None:
        return None
    land = (x, y, fz)
    if ctx.walk(land, target) is None:
        return None
    return land


def unit(a, b):
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    if d < 1e-6:
        return None, 0.0
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d), d


def gap_edges(ctx, p, v, land):
    """(void, edge): how far along v the launch floor ends and the
    landing floor begins. None when the landing is still on the launch
    floor, which is a walk the walker happened to refuse, not a jump."""
    total = math.hypot(land[0] - p[0], land[1] - p[1])
    z, t, void = p[2], 0.0, None
    while t <= total:
        x, y = p[0] + v[0] * t, p[1] + v[1] * t
        if void is None:
            nz = ctx.floor_near(x, y, z)
            if nz is None:
                void = t
            else:
                z = nz
        elif ctx.floor_near(x, y, land[2], tol=3.0) is not None:
            return void, t
        t += 2.0
    return None if void is None else (void, total)


def runway(ctx, edge, v):
    """navgen's landing runway: clear standable floor past the landing edge."""
    out = 0.0
    for d in range(8, 129, 8):
        x, y = edge[0] + v[0] * d, edge[1] + v[1] * d
        if ctx.bsp.h0(x, y, edge[2]) != nm.CONTENTS_EMPTY:
            break
        if not ctx.bsp.check_bottom(x, y, edge[2]):
            break
        out = float(d)
    return out


def jump_profile(ctx, a, b):
    """The runtime's plain jump from seat a to seat b, or None.

    Returns {"launch", "speed", "runway", "margin", "landing"}; speed 0
    is navgen's fallback (fire at 250 or more).
    """
    if b[2] - a[2] > STEP or a[2] - b[2] > ctx.drop_limit:
        return None
    u, d = unit(a, b)
    if u is None or d < MIN_LANDING or d > LINK_MAX:
        return None
    launch = launch_point(ctx, a, u, min(d, ANCHOR))
    if launch is None or launch_distance(a, launch) >= ANCHOR:
        return None
    v, rem = unit(launch, b)
    if v is None or rem < MIN_LANDING:
        return None
    cache = {}

    def lands(s):
        if s not in cache:
            cache[s] = landing(ctx, launch, v, float(s), JUMPVEL, b)
        return cache[s]
    first = next((lands(s) for s in COARSE if lands(s)), None)
    if first is None:
        return None
    # The far floor begins where it begins whatever the speed, so the
    # gap is read once. Like navgen, an arc has to pass at least 2u over
    # that edge: one that only just lands is a fall short at a frame's
    # worth of error.
    gap = gap_edges(ctx, launch, v, first)
    if gap is None:
        return None
    void, edge_d = gap
    g = ctx.gravity

    def margin(s):
        t = edge_d / s
        return launch[2] + JUMPVEL * t - 0.5 * g * t * t - lands(s)[2]

    def passes(s):
        land = lands(s)
        return (land is not None and math.hypot(land[0] - launch[0], land[1] - launch[1]) > void
                and margin(s) >= 2.0)
    speeds = None
    for v0 in STAGED:
        if all(passes(v0 + w) for w in WINDOW):
            speeds, speed = [v0 + w for w in WINDOW], v0
            break
    if speeds is None:
        if not all(passes(s) for s in FALLBACK):
            return None
        speeds, speed = list(FALLBACK), 0
    land = lands(speeds[0])
    edge = (launch[0] + v[0] * edge_d, launch[1] + v[1] * edge_d, land[2])
    return {"launch": launch, "speed": float(speed), "landing": land,
            "runway": runway(ctx, edge, v),
            "margin": round(min(margin(s) for s in speeds), 1)}


def climb_ok(ctx, a, b):
    """The runtime's climb: a standing jump within 72u of a seat above."""
    rise = b[2] - a[2]
    if not STEP < rise <= ctx.climb_limit:
        return False
    u, d = unit(a, b)
    if u is None or d > LINK_MAX:
        return False
    z, t = a[2], 0.0
    while d - t >= CLIMB_REACH:
        nz = ctx.floor_near(a[0] + u[0] * t, a[1] + u[1] * t, z)
        if nz is None:
            # a gap, or a face more than 72u short of the seat: the bot
            # meets it before the climb may fire and stops there
            return False
        z, t = nz, t + 2.0
    fx, fy = a[0] + u[0] * t, a[1] + u[1] * t
    fz = ctx.floor_near(fx, fy, z)
    if fz is None or b[2] - fz <= STEP:
        return False
    h = fz
    while h <= b[2] + 4.0:
        if ctx.world.h1(fx, fy, h) != nm.CONTENTS_EMPTY:
            return False                  # no headroom over the take-off
        h += 4.0
    rest = d - t
    s, z = 0.0, fz
    while s <= rest:
        x, y = fx + u[0] * s, fy + u[1] * s
        if ctx.world.h1(x, y, b[2] + 4.0) != nm.CONTENTS_EMPTY:
            return False                  # the lip has no clearance over it
        top = ctx.floor_near(x, y, b[2])
        if top is not None and top - z > STEP:
            return ctx.walk((x, y, top), b) == "walk"
        nz = ctx.floor_near(x, y, z)
        if nz is None:
            return False                  # a void before the face
        z, s = nz, s + 2.0
    return False


def drop_arc(ctx, a, b):
    """A run off the line a->b that lands where b is a walk, or None.

    Both the routed drop commit (240 u/s) and a full run (320) must land
    clean, and the physics guard's straight-down probes past the lip must
    find floor, or the bot never takes the step at all.
    """
    if not STEP < a[2] - b[2] <= ctx.drop_limit:
        return None
    u, d = unit(a, b)
    if u is None or d > LINK_MAX:
        return None
    lip = first_lip(ctx, a, u, d)
    if lip is None:
        return None
    k = 4.0
    while k <= GUARD_REACH:
        if guard_floor(ctx.bsp, lip[0] + u[0] * k, lip[1] + u[1] * k, lip[2]) != "floor":
            return None
        k += 8.0
    lands = [landing(ctx, lip, u, s, 0.0, b) for s in (DROP_STEP, RUN)]
    if not all(lands):
        return None
    if any(lip[2] - p[2] <= STEP for p in lands):
        return None
    return {"lip": lip, "landings": lands}


def drop_lands_lethal(ctx, a, b, speed=DROP_STEP):
    """Does the run-off of a plain drop a->b land in lava or slime?"""
    u, d = unit(a, b)
    if u is None:
        return False
    lip = first_lip(ctx, a, u, d)
    if lip is None:
        return False
    return flight(ctx, lip, u, speed, 0.0)["kind"] in ("lava", "slime")


# ---- seats the map's own entities ask for ----

def teleporters(ctx):
    """[(source seat, destination seat, trigger box)] from the entity lump."""
    ents = ctx.bsp.entities()
    dests = {}
    for e in ents:
        if e.get("classname") == "info_teleport_destination" and "targetname" in e:
            dests[e["targetname"]] = tuple(float(v) for v in e.get("origin", "0 0 0").split())
    out, refused = [], []
    for e in ents:
        if e.get("classname") != "trigger_teleport" or e.get("target") not in dests:
            continue
        m = e.get("model", "")
        if not m.startswith("*"):
            continue
        mdl = ctx.bsp.models[int(m[1:])]
        mn, mx = mdl[0:3], mdl[3:6]
        box = ((mn[0] - 16, mn[1] - 16, mn[2] - 32), (mx[0] + 16, mx[1] + 16, mx[2] + 24))
        cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
        src, best = None, None
        x = mn[0]
        while x <= mx[0]:
            y = mn[1]
            while y <= mx[1]:
                for z in ctx.floors(x, y):
                    p = (x, y, z)
                    if not _inside(p, box) or ctx.bsp.h0(x, y, z - 23.0) in LETHAL:
                        continue
                    dd = math.hypot(x - cx, y - cy)
                    if best is None or dd < best:
                        src, best = p, dd
                y += 8.0
            x += 8.0
        ox, oy, oz = dests[e["target"]]
        fz = nm.fall_to(ctx.world, ox, oy, oz + 27.0, maxdrop=256.0)
        dst = None
        if fz is not None:
            mz = ctx.floor_near(ox, oy, fz, tol=3.0)
            if mz is not None and ctx.bsp.h0(ox, oy, mz - 23.0) not in LETHAL:
                dst = (ox, oy, mz)
        if src is None or dst is None or any(_inside(dst, b) for b in ctx.tboxes):
            refused.append((e.get("target"), src, dst))
            continue
        out.append((src, dst, box))
    return out, refused


def _inside(p, box):
    mn, mx = box
    return all(mn[i] < p[i] < mx[i] for i in range(3))


def lift_pads(ctx, cands):
    """[(boarding seat, exit seat, plat centre)] by navgen's 5b rules."""
    out, refused = [], []
    for e in ctx.bsp.entities():
        if e.get("classname") != "func_plat" or not e.get("model", "").startswith("*"):
            continue
        bm = ctx.bsp.models[int(e["model"][1:])]
        top = bm[5]
        height = float(e.get("height", 0) or 0) or (bm[5] - bm[2] - 8)
        face = top - height
        pcx, pcy = (bm[0] + bm[3]) / 2, (bm[1] + bm[4]) / 2
        lo, lod = None, None
        for c in cands:
            x, y, z = c
            if bm[0] - 4 <= x <= bm[3] + 4 and bm[1] - 4 <= y <= bm[4] + 4:
                continue                    # inside the swept column
            if not (bm[0] - 96 <= x <= bm[3] + 96 and bm[1] - 96 <= y <= bm[4] + 96):
                continue
            if abs(z - face) > 20:
                continue
            dx = max(bm[0] - x, 0, x - bm[3])
            dy = max(bm[1] - y, 0, y - bm[4])
            dd = math.hypot(dx, dy)
            if lod is None or dd < lod:
                lo, lod = c, dd
        hi, hid = None, None
        for c in cands:
            dd = math.sqrt((c[0] - pcx) ** 2 + (c[1] - pcy) ** 2 + (2 * (c[2] - top - 24)) ** 2)
            if dd <= 120 and (hid is None or dd < hid):
                hi, hid = c, dd
        if lo is None or hi is None or lo == hi:
            refused.append(((pcx, pcy, top), lo, hi))
            continue
        out.append((lo, hi, (pcx, pcy, top)))
    return out, refused


# ---- arc sites on the mesh, before any seat exists ----

def fragment_graph(ctx):
    """fa -> [(fb, portal midpoint)] over the mesh's walk and drop portals."""
    out = collections.defaultdict(list)
    for p in nm.build_portals(ctx.bsp, ctx.frags):
        mx, my = (p["s"][0] + p["e"][0]) / 2, (p["s"][1] + p["e"][1]) / 2
        out[p["a"]].append((p["b"], (mx, my, p["zb"])))
    return out


def mesh_length(fgraph, fa, start, fb, goal, cap):
    """Approximate walking length fa -> fb through portal midpoints."""
    dist, entry = {fa: 0.0}, {fa: start}
    heap = [(0.0, fa)]
    while heap:
        d, f = heapq.heappop(heap)
        if d > dist[f] or d > cap:
            continue
        if f == fb:
            return d + math.dist(entry[f], goal)
        for g, m in fgraph.get(f, ()):
            nd = d + math.dist(entry[f], m)
            if nd < dist.get(g, math.inf):
                dist[g], entry[g] = nd, m
                heapq.heappush(heap, (nd, g))
    return math.inf


def arc_sites(ctx, fgraph, ledges, offsets=(0.0, 30.0, -30.0)):
    """Jump and drop arcs off every ledge point that save a long walk.

    Each site is flown at one speed only (280 for a jump, 240 and 320
    for a drop); the seat-level checks re-fly every speed later. A site
    is kept when the landing fragment is unreachable over walk and drop
    portals, or the walk is more than 1.5x the arc plus 128u.
    """
    sites = []
    for s in ledges:
        x, y, z = s["pos"]
        fa = s["frag"]
        for off in offsets:
            r = math.radians(off)
            n = s["n"]
            u = (n[0] * math.cos(r) - n[1] * math.sin(r), n[0] * math.sin(r) + n[1] * math.cos(r))
            back = 0.0
            while back < ANCHOR and ctx.floor_near(x - u[0] * (back + 8), y - u[1] * (back + 8), z):
                back += 8.0
            start = (x - u[0] * back, y - u[1] * back, z)
            sz = ctx.floor_near(start[0], start[1], z)
            if sz is not None:
                start = (start[0], start[1], sz)
                launch = launch_point(ctx, start, u, back + 8.0)
                if launch is not None:
                    _site(ctx, sites, fgraph, "jump", fa, launch, u,
                          flight(ctx, launch, u, 280.0, JUMPVEL))
            r1 = flight(ctx, (x, y, z), u, DROP_STEP, 0.0)
            r2 = flight(ctx, (x, y, z), u, RUN, 0.0)
            if r1["kind"] == "floor" and r2["kind"] == "floor" and not r2["clip"]:
                f1 = ctx.locate(*r1["pos"])
                if f1 is not None and f1 == ctx.locate(*r2["pos"]):
                    _site(ctx, sites, fgraph, "drop", fa, (x, y, z), u, r1)
    return sites


def _site(ctx, sites, fgraph, kind, fa, src, u, r):
    if r["kind"] != "floor" or r["clip"] or r.get("on") or r["fall"] > ctx.drop_limit:
        return
    if kind == "drop" and r["fall"] <= STEP:
        return
    fb = ctx.locate(*r["pos"])
    if fb is None or fb == fa:
        return
    arc = math.dist(src, r["pos"])
    walk = mesh_length(fgraph, fa, src, fb, r["pos"], SAVING_RATIO * arc + SAVING_SLACK + 1)
    if walk <= SAVING_RATIO * arc + SAVING_SLACK:
        return
    sites.append({"kind": kind, "fa": fa, "fb": fb, "src": src, "u": u,
                  "land": r["pos"], "saving": min(walk, 1e6) - arc})


def cluster(sites, spread=256.0, per_group=2):
    """At most two representatives per (kind, source, landing) fragment pair."""
    groups = collections.defaultdict(list)
    for s in sites:
        groups[(s["kind"], s["fa"], s["fb"])].append(s)
    out = []
    for key in sorted(groups):
        picked = []
        for s in sorted(groups[key], key=lambda s: (-s["saving"], s["src"])):
            if all(math.dist(s["src"], p["src"]) > spread for p in picked):
                picked.append(s)
            if len(picked) >= per_group:
                break
        out.extend(picked)
    return out


def site_targets(site):
    """Where the seats for a site should stand: behind the launch, past the landing."""
    u, src, land = site["u"], site["src"], site["land"]
    back = 40.0 if site["kind"] == "jump" else 48.0
    return ((src[0] - u[0] * back, src[1] - u[1] * back, src[2]),
            (land[0] + u[0] * 40.0, land[1] + u[1] * 40.0, land[2]))


# ---- choosing the links between final seats ----

def adjacency(ok, seats, extra=None):
    """Weighted out-lists: plain links by length, extra pairs by their own."""
    adj = collections.defaultdict(list)
    for (i, j) in ok:
        adj[i].append((j, math.dist(seats[i], seats[j])))
    for (i, j), w in (extra or {}).items():
        adj[i].append((j, w))
    return adj


def plain_lengths(adj, src, cap):
    """Dijkstra from one seat over a weighted adjacency, up to cap."""
    dist = {src: 0.0}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u] or d > cap:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def seat_ledges(seats, ledges, cell=64.0):
    """Per seat, the ledge points a link from it could leave by."""
    grid = collections.defaultdict(list)
    for s in ledges:
        x, y, _ = s["pos"]
        grid[(math.floor(x / cell), math.floor(y / cell))].append(s)
    out = []
    for x, y, z in seats:
        near = []
        for gx in range(math.floor((x - LINK_MAX) / cell), math.floor((x + LINK_MAX) / cell) + 1):
            for gy in range(math.floor((y - LINK_MAX) / cell), math.floor((y + LINK_MAX) / cell) + 1):
                for s in grid.get((gx, gy), ()):
                    sx, sy, sz = s["pos"]
                    if abs(sz - z) <= 2 * STEP and math.hypot(sx - x, sy - y) <= LINK_MAX:
                        near.append(s)
        out.append(near)
    return out


def crosses_ledge(a, u, near, reach, level=None):
    """Does the line from a along u leave by one of these ledge points?"""
    for s in near:
        sx, sy, sz = s["pos"]
        if level is not None and abs(sz - level) > STEP:
            continue
        if s["n"][0] * u[0] + s["n"][1] * u[1] < 0.2:
            continue
        dx, dy = sx - a[0], sy - a[1]
        t = dx * u[0] + dy * u[1]
        if 0.0 <= t <= reach and abs(dx * u[1] - dy * u[0]) <= 40.0:
            return True
    return False


def find_links(ctx, seats, ok, ledges, skip=frozenset()):
    """Mesh-native jumps, climbs and drop arcs between final seats.

    ok maps verified plain pairs to "walk" or "drop"; only pairs the
    walker refused are tried. skip holds seats that may not launch (a
    seat inside a teleporter trigger). Returns (jumps, drops, stats):
    jumps maps a pair to its profile, drops maps a pair to its arc. A
    gap jump or a drop arc is only tried where the line leaves by a
    ledge point; a climb needs none. Going down, a drop arc is tried
    before a jump: a plain step off is the cheaper promise to keep.
    """
    n = len(seats)
    near = seat_ledges(seats, ledges)
    stats = collections.Counter()
    jumps, drops = {}, {}
    for i in range(n):
        if i in skip:
            continue
        a = seats[i]
        for j in range(n):
            if i == j or (i, j) in ok:
                continue
            b = seats[j]
            u, d = unit(a, b)
            if u is None or d > LINK_MAX:
                continue
            dz = b[2] - a[2]
            if dz > STEP:
                if climb_ok(ctx, a, b):
                    jumps[(i, j)] = {"speed": 0.0, "runway": 0.0, "margin": 0.0,
                                     "climb": True}
                    stats["climbs_verified"] += 1
                continue
            if -dz > ctx.drop_limit:
                continue
            if -dz > STEP and crosses_ledge(a, u, near[i], d):
                stats["drop_pairs_tried"] += 1
                arc = drop_arc(ctx, a, b)
                if arc:
                    drops[(i, j)] = arc
                    stats["drop_arcs_verified"] += 1
                    continue
            if crosses_ledge(a, u, near[i], LEDGE_NEAR, level=a[2]):
                stats["jump_pairs_tried"] += 1
                prof = jump_profile(ctx, a, b)
                if prof:
                    jumps[(i, j)] = prof
                    stats["jumps_verified"] += 1
    return jumps, drops, stats


def keep_useful(seats, ok, jumps, drops, extra=None):
    """Keep a typed hop only where the graph has no comparable route.

    A jump or arc a->b is a candidate when the route over verified plain
    links (and extra, the teleporter and lift hops by their own costs) is
    longer than 1.5x the hop plus 128u, or missing. Candidates are taken
    greedily, largest saving first, and each one taken joins the graph,
    so a row of ledge seats does not each keep a jump to the same floor:
    the second is judged against the first. Two per source at most, as a
    jump is riskier than a walk and slots are eight.
    """
    adj = adjacency(ok, seats, extra)
    pool = [("jump", i, j, info) for (i, j), info in jumps.items()]
    pool += [("drop", i, j, info) for (i, j), info in drops.items()]
    scored = []
    for kind, i, j, info in pool:
        hop = math.dist(seats[i], seats[j])
        limit = SAVING_RATIO * hop + SAVING_SLACK
        walk = plain_lengths(adj, i, limit + 1).get(j, math.inf)
        if walk > limit:
            scored.append((-(min(walk, 1e6) - hop), hop, i, j, kind, info))
    scored.sort(key=lambda r: r[:4])
    kj, kd = {}, {}
    taken = collections.Counter()
    for _, hop, i, j, kind, info in scored:
        if taken[i] >= PER_SOURCE:
            continue
        limit = SAVING_RATIO * hop + SAVING_SLACK
        if plain_lengths(adj, i, limit + 1).get(j, math.inf) <= limit:
            continue
        adj[i].append((j, hop))
        taken[i] += 1
        (kj if kind == "jump" else kd)[(i, j)] = info
    return kj, kd
