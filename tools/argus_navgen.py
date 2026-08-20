#!/usr/bin/env python3
"""argus_navgen.py — offline navigation compiler for Argus.

Pipeline:
  1. parse BSP29: planes, clipnodes, models, entities
  2. classify points against HULL 1 (the player hull) so "empty" means
     "a player standing here fits" — collision-accurate walkability for free
  3. sample standable origins on a 32u column grid
  4. build a directed fine graph: walk edges (|dz| <= 18, both ways),
     drop edges (19..200 down, one way)
  5. decimate to a sparse waypoint graph (< ~200 nodes, vanilla edict budget)
  6. link waypoints by Dijkstra over the fine graph; one-way links survive
  7. teleporter links from the entity lump
  7a. jump links (gap-lip parabola) and prize-only rocket-jump pads
      (quad/pent/ring/mega/LG/RL, horiz to 260u, at most two per
      landing; --no-rj skips pads)
  7b. lift links from func_plat (boarding/exit pads + vertical hop)
  8. emit argus_nav_<map>.qc + JSON + a debug plot of the graph
     (pass --no-dispatcher; the dispatcher file is hand-maintained)
  If src/argus_nav_<map>.costs.json exists (from learn_hotspots),
  fine-edge costs near those cells are inflated and lava-crossing
  walk links are dropped.

usage: argus_navgen.py map.bsp mapname out.qc out.png [--no-dispatcher] [--no-rj]

--no-dispatcher emits only Argus_Nav_Spawn_<mapname>, for multi-map
builds where a hand-maintained argus_nav_dispatch.qc selects per map.
"""
import re, struct, sys, heapq, collections

BSP, MAPNAME, OUTQC, OUTPNG = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
EMIT_DISPATCHER = "--no-dispatcher" not in sys.argv[5:]
if "--register" in sys.argv[5:]:
    # --register wires the map into the shared argus_nav_dispatch.qc,
    # so emitting a second Argus_Nav_Spawn in the per-map file would
    # collide at compile (Shane's drift list): registering implies
    # per-map output
    EMIT_DISPATCHER = False

CONTENTS_EMPTY, CONTENTS_SOLID = -1, -2
GRID = 32
if "--grid" in sys.argv[5:]:
    # a 32u-aligned grid can straddle narrow passages entirely (no
    # column of the grid stands inside them), severing yards that
    # are walkably connected — dm3's six dry islands (campaign queue
    # item 1). 16 quadruples sampling cost; use for maps that
    # shatter at 32.
    GRID = int(sys.argv[sys.argv.index("--grid") + 1])
CORRIDOR = "--corridor" in sys.argv[5:]
if CORRIDOR:
    # corridor mode proper (campaign item 1's designed answer):
    # sample FINE for connectivity, seat COARSE for the edict
    # budget. The 16u fine graph finds the narrow stairs and
    # doorways; decimation prefers the every-other-column
    # sublattice so open areas cost what a 32u run costs, and only
    # corridor interiors (where no coarse column stands) spend
    # seats from the fine set.
    GRID = 16
STEP = 18          # max walkable step up/down
DROPMAX = 200      # max safe intentional drop
WAYPOINT_R = 100   # decimation coverage radius
LINK_PATH_MAX = 340
MAX_NODES = 200
MAX_LINKS = 8

data = open(BSP, "rb").read()
assert struct.unpack_from("<i", data, 0)[0] == 29
lumps = [struct.unpack_from("<ii", data, 4 + i * 8) for i in range(15)]

def lump(i): o, l = lumps[i]; return data[o:o+l]

# planes
pl = lump(1)
planes = [struct.unpack_from("<ffff", pl, i * 20)[:4] for i in range(len(pl) // 20)]
# clipnodes
cn = lump(9)
clip = [struct.unpack_from("<ihh", cn, i * 8) for i in range(len(cn) // 8)]
# models
md = lump(14)
m0 = struct.unpack_from("<9f7i", md, 0)
mins, maxs = m0[0:3], m0[3:6]
HULL1 = m0[10]  # headnode[1]
# entities
ents_txt = lump(0).split(b"\0")[0].decode("ascii", "replace")

def hull_contents(x, y, z, node=None):
    n = HULL1 if node is None else node
    while n >= 0:
        pn, c0, c1 = clip[n]
        nx, ny, nz, d = planes[pn]
        n = c0 if (nx * x + ny * y + nz * z - d) >= 0 else c1
    return n

# ---- 3. column sampling ----
def column_floors(x, y):
    """standable origin z values for this column, top down"""
    out = []
    z = maxs[2] + 40
    prev = hull_contents(x, y, z)
    z -= 4
    while z > mins[2] - 4:
        c = hull_contents(x, y, z)
        if prev == CONTENTS_EMPTY and c != CONTENTS_EMPTY:
            # refine boundary: lowest empty z in (z, z+4]
            lo, hi = z, z + 4
            for _ in range(6):
                mid = (lo + hi) / 2
                if hull_contents(x, y, mid) == CONTENTS_EMPTY: hi = mid
                else: lo = mid
            if c == CONTENTS_SOLID:            # standing on ground, not liquid/sky
                out.append(round(hi, 1))
        prev = c
        z -= 4
    return out

# hull 0 sees what the clip hulls cannot: liquids. Parsed here, ahead
# of sampling, because seats and links need it, not just swim exits.
CONTENTS_WATER, CONTENTS_SLIME, CONTENTS_LAVA = -3, -4, -5
nd = lump(5)
h0nodes = [struct.unpack_from("<i8h2H", nd, i * 24) for i in range(len(nd) // 24)]
lf = lump(10)
h0leaves = [struct.unpack_from("<2i6h2H4B", lf, i * 28) for i in range(len(lf) // 28)]
HULL0 = m0[9]

def h0_contents(x, y, z):
    n = HULL0
    while n >= 0:
        node = h0nodes[n]
        nx, ny, nz, d = planes[node[0]]
        n = node[1] if (nx * x + ny * y + nz * z - d) >= 0 else node[2]
    return h0leaves[-1 - n][0]

def water_surface_z(x, y, z):
    top = z
    while top < z + 320 and h0_contents(x, y, top + 8) == CONTENTS_WATER:
        top += 8
    return top

samples = {}   # (cx,cy) -> list of z
xs = [mins[0] + GRID/2 + i * GRID for i in range(int((maxs[0]-mins[0]) // GRID) + 1)]
ys = [mins[1] + GRID/2 + i * GRID for i in range(int((maxs[1]-mins[1]) // GRID) + 1)]
nsamp = 0
for cx, x in enumerate(xs):
    for cy, y in enumerate(ys):
        f = column_floors(x, y)
        if f:
            samples[(cx, cy)] = f
            nsamp += len(f)
print(f"fine samples: {nsamp} standable points in {len(samples)} columns")

# ---- 4b. lava and slime seats are not standable ----
# hull 1 collapses liquids to empty, so the sampler happily seats
# waypoints on a lava pool's floor (dm2 shipped 29 of them). Classify
# every fine sample against hull 0 at torso height and drop hostile
# seats before decimation, links, pads or jump edges can build on
# them. Water seats stay: swim links (7d) need underwater waypoints.
_n_liquid = 0
for _k in list(samples.keys()):
    _keep = []
    for _z in samples[_k]:
        if h0_contents(xs[_k[0]], ys[_k[1]], _z + 24) in (CONTENTS_LAVA, CONTENTS_SLIME):
            _n_liquid += 1
        else:
            _keep.append(_z)
    if _keep:
        samples[_k] = _keep
    else:
        del samples[_k]
if _n_liquid:
    print(f"lava/slime seats dropped: {_n_liquid}")

# ---- 4. fine directed graph ----
# node id = (cx, cy, zi)
fine = collections.defaultdict(list)   # id -> [(id2, cost)]
def near(zs, z, tol):
    for i, zz in enumerate(zs):
        if abs(zz - z) <= tol: return i
    return None

for (cx, cy), zs in samples.items():
    for zi, z in enumerate(zs):
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nb = samples.get((cx+dx, cy+dy))
            if not nb: continue
            # walk edge
            j = near(nb, z, STEP)
            if j is not None:
                fine[(cx,cy,zi)].append(((cx+dx,cy+dy,j), GRID + abs(nb[j]-z), 0))
                continue
            # drop edge: any floor 19..200 below
            for j2, z2 in enumerate(nb):
                if STEP < z - z2 <= DROPMAX:
                    fine[(cx,cy,zi)].append(((cx+dx,cy+dy,j2), GRID + (z - z2) * 0.5, 0))
                    break

# ---- 4b. jump edges ----
# A full-speed jump (jumpvel 270, gravity 800; modelled at a
# conservative 280 u/s run so slower runtime jumps still land) carries
# the player across gaps the walk/drop scan never sees, e.g. dm4's quad
# ledge. From every sample whose neighbour cell is not walkable, scan 8
# directions 2..5 cells out for a landing floor between 64u below and
# 40u above, and verify the parabolic arc is clear in hull 1.
JUMPSPEED, JUMPVEL, GRAV = 280.0, 270.0, 800.0

def arc_clear(x0, y0, z0, x1, y1, z1):
    dx, dy = x1 - x0, y1 - y0
    dist = (dx*dx + dy*dy) ** 0.5
    t_total = dist / JUMPSPEED
    if z0 + JUMPVEL*t_total - 0.5*GRAV*t_total*t_total < z1 + 2:
        return False                    # arc arrives below the landing floor
    steps = max(4, int(dist // 16))
    for s in range(1, steps):
        f = s / steps
        t = t_total * f
        zt = z0 + JUMPVEL*t - 0.5*GRAV*t*t
        if hull_contents(x0 + dx*f, y0 + dy*f, zt) != CONTENTS_EMPTY:
            return False
        if hull_contents(x0 + dx*f, y0 + dy*f, zt + 20) != CONTENTS_EMPTY:
            return False                # head room along the arc
    return True

njump = 0
for (cx, cy), zs in samples.items():
    for zi, z in enumerate(zs):
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = samples.get((cx+dx, cy+dy))
            if nb is not None and near(nb, z, STEP) is not None:
                continue                # walkable: no jump needed
            for k in range(2, 6):
                cell = samples.get((cx+dx*k, cy+dy*k))
                if cell is None:
                    continue
                land = None
                for j2, z2 in enumerate(cell):
                    if -64 <= z2 - z <= 40:
                        land = (j2, z2)
                        break
                if land is None:
                    continue            # floors far below do not block a gap jump
                j2, z2 = land
                if arc_clear(xs[cx], ys[cy], z, xs[cx+dx*k], ys[cy+dy*k], z2):
                    step = (GRID*GRID*(dx*dx + dy*dy)) ** 0.5
                    fine[(cx,cy,zi)].append(((cx+dx*k, cy+dy*k, j2),
                                             step*k*1.5 + 40, 1))
                    njump += 1
                break                   # nearest level candidate settles this direction
print(f"jump edges: {njump}")

def pos(nid):
    cx, cy, zi = nid
    return (xs[cx], ys[cy], samples[(cx,cy)][zi])

# ---- 4b2. learned hotspot costs ----
# learn_hotspots writes src/argus_nav_<map>.costs.json. Fine-graph
# edges whose midpoint sits in a cell get their Dijkstra cost
# multiplied so the waypoint linker prefers a detour. Lava cells also
# drop the eventual walk link: unweighted runtime BFS would still
# take a costly hop if it exists.
import os as _os
_cost_path = _os.path.join(_os.path.dirname(_os.path.abspath(OUTQC)),
                           f"argus_nav_{MAPNAME}.costs.json")
COST_CELLS = []
if _os.path.isfile(_cost_path):
    import json as _json
    try:
        COST_CELLS = _json.load(open(_cost_path)).get("cells") or []
    except Exception as _e:
        print(f"hotspot costs: failed to read {_cost_path}: {_e}")
        COST_CELLS = []
    else:
        print(f"hotspot costs: {len(COST_CELLS)} cells from {_cost_path}")

def hotspot_mult(x, y, z):
    m = 1.0
    for c in COST_CELLS:
        r = float(c.get("radius", 128))
        dx = x - float(c.get("x", 0))
        dy = y - float(c.get("y", 0))
        dz = z - float(c.get("z", 0))
        if dx*dx + dy*dy + dz*dz <= r*r:
            m = max(m, float(c.get("cost", 1)))
    return m

if COST_CELLS:
    _inflated = 0
    for _u, _edges in list(fine.items()):
        _ux, _uy, _uz = pos(_u)
        _new = []
        for _v, _c, _isj in _edges:
            _vx, _vy, _vz = pos(_v)
            _mult = hotspot_mult((_ux+_vx)/2, (_uy+_vy)/2, (_uz+_vz)/2)
            if _mult > 1.0:
                _inflated += 1
            _new.append((_v, _c * _mult, _isj))
        fine[_u] = _new
    print(f"hotspot costs: inflated {_inflated} fine edges")

# ---- 4c. entity lump and edict budget ----
# vanilla max_edicts is 600 and the engine needs headroom for bodies,
# missiles and temp entities on top of the BSP's own entities and our
# waypoint nodes: cap waypoints so bsp entities + nodes stay under 500
# (Shane's project review: a 350-entity map plus a 200-node graph
# would Host_Error at spawn)
ent_blocks = re.findall(r"\{(.*?)\}", ents_txt, re.S)
def kv(block):
    return dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', block))
bmodels = [struct.unpack_from("<9f7i", md, i * 64) for i in range(len(md)//64)]
NODE_CAP = MAX_NODES
if len(ent_blocks) + NODE_CAP > 500:
    NODE_CAP = max(60, 500 - len(ent_blocks))
    print(f"edict budget: {len(ent_blocks)} bsp entities, "
          f"node cap lowered to {NODE_CAP}")

# ---- 5. decimate to waypoints ----
allnodes = [ (cx,cy,zi) for (cx,cy),zs in samples.items() for zi in range(len(zs)) ]
allnodes.sort()
if CORRIDOR:
    # seats prefer the coarse sublattice; fine samples seat only
    # where nothing coarse covers, which is exactly the inside of a
    # narrow passage (see the --corridor note at the top)
    allnodes = ([n for n in allnodes if n[0] % 2 == 0 and n[1] % 2 == 0]
                + [n for n in allnodes if n[0] % 2 or n[1] % 2])
r = WAYPOINT_R
while True:
    ways = []
    for nid in allnodes:
        x, y, z = pos(nid)
        ok = True
        for w in ways:
            wx, wy, wz = pos(w)
            if ((x-wx)**2 + (y-wy)**2 + (2*(z-wz))**2) ** 0.5 < r:
                ok = False; break
        if ok: ways.append(nid)
    if len(ways) <= NODE_CAP: break
    r *= 1.15
print(f"waypoints: {len(ways)} at coverage radius {r:.0f}")

# ---- 5b. plats: force waypoints at each lift's boarding and exit ----
# func_plat is compiled at its TOP position; travel is the height key
# or size_z - 8. Hull sampling cannot climb a lift shaft, so without
# help the levels a lift serves emerge as separate islands (dm3's
# stacked tower was the found case: 8 islands, 570 routefails in one
# match). Force a waypoint into the decimated set at the boarding
# point and the exit point of every plat BEFORE link building, so both
# pads get ordinary walk links to their own level; section 7c then
# types the vertical hop as Argus_NavLinkLift. Caveat: pads need a
# floor SAMPLE to promote, and a plat's slab is only static geometry
# at its drawn (top) position - a boarding point with no world floor
# under it (slab-only landings between stacked plats) cannot pad and
# is reported instead. (ent_blocks/kv/bmodels parse in section 4c.)

def closest_nid(x, y, z):
    best, bd = None, 1e9
    for (cx, cy), zs in samples.items():
        for zi, zz in enumerate(zs):
            d = (xs[cx] - x) ** 2 + (ys[cy] - y) ** 2 + (2 * (zz - z)) ** 2
            if d < bd:
                best, bd = (cx, cy, zi), d
    return best, bd ** 0.5

def force_way(x, y, z, snap=48):
    """Waypoint index for (x,y,z): reuse one within snap units, else
    promote the closest fine sample. None when nothing ever stood
    within 120u (no world floor there)."""
    nid, d = closest_nid(x, y, z)
    if nid is None or d > 120:
        return None
    if nid in ways:
        return ways.index(nid)
    px, py, pz = pos(nid)
    for i, w in enumerate(ways):
        wx, wy, wz = pos(w)
        if ((px-wx)**2 + (py-wy)**2 + (2*(pz-wz))**2) ** 0.5 < snap:
            return i
    if len(ways) >= NODE_CAP:
        return None
    ways.append(nid)
    return len(ways) - 1

def boarding_pad(bm, face_z):
    """WAIT_NODE discipline (mre's Obot design, proven necessary by
    the dm2 *31 statue forensics): the boarding pad must sit OUTSIDE
    the plat's footprint - a bot waiting inside the swept column
    blocks the descending slab with its body, and its touches
    postpone the cycle, so the plat never seats. Prefer a standable
    sample in a ring 4..96u outside the bbox whose floor is within a
    step of the slab's seated top face; nearest to the slab wins."""
    best, bestd = None, 1e9
    for (cx, cy), zs in samples.items():
        x, y = xs[cx], ys[cy]
        if bm[0] - 4 <= x <= bm[3] + 4 and bm[1] - 4 <= y <= bm[4] + 4:
            continue                    # inside the swept column
        if not (bm[0] - 96 <= x <= bm[3] + 96
                and bm[1] - 96 <= y <= bm[4] + 96):
            continue
        for zz in zs:
            if abs(zz - face_z) <= 20:
                dx = max(bm[0] - x, 0, x - bm[3])
                dy = max(bm[1] - y, 0, y - bm[4])
                d = (dx * dx + dy * dy) ** 0.5
                if d < bestd:
                    best, bestd = (x, y, zz), d
    if best is None:
        return None
    return force_way(best[0], best[1], best[2] + 24, snap=32)

lifts = []
for b in ent_blocks:
    e = kv(b)
    if e.get("classname") != "func_plat" or "model" not in e:
        continue
    bm = bmodels[int(e["model"].lstrip("*"))]
    top_z = bm[5]
    height = float(e.get("height", 0) or 0) or (bm[5] - bm[2] - 8)
    pcx, pcy = (bm[0] + bm[3]) / 2, (bm[1] + bm[4]) / 2
    lo = boarding_pad(bm, top_z - height)
    if lo is None:
        lo = force_way(pcx, pcy, top_z - height + 24)
        if lo is not None:
            print(f"plat at ({pcx:.0f} {pcy:.0f}): no boarding sample "
                  f"outside the footprint; pad falls back INSIDE the "
                  f"swept column (statue risk - see cartograph plats)")
    hi = force_way(pcx, pcy, top_z + 24)
    if lo is None or hi is None or lo == hi:
        print(f"plat at ({pcx:.0f} {pcy:.0f}) travel {height:.0f}: "
              f"no usable pad (bottom {lo}, top {hi})")
        continue
    lifts.append((lo, hi))
print(f"plats: {len(lifts)} lift(s) padded")

# ---- 5c. train links from func_train ----
# A func_train patrols its path_corners on its own clock: a MOVING
# bmodel, in neither static hull, so the bridge it forms is invisible
# to sampling (dm2's t4/t5 car at z 304 IS the west-to-east upper
# deck connection — the GL's 9-node pocket). Pad static floor at both
# endpoint approaches (probe outward past each side of the parked
# car) and emit a typed ride link EACH WAY; the runtime parks on the
# pad, boards when the car docks, holds while carried, walks off at
# the far pad. func_train parks with its MIN corner on the
# path_corner, so the rideable top is corner_z + size_z.
trains = []
_corners = {}
NO_TRAINS = "--no-trains" in sys.argv[5:]
# --no-trains: emit no ride links even where pads exist. dm2's first
# trains ladder (ab_dm2_trains/2) proved the links correct but the
# APPROACHES ruinous: GL routes funnel through the chronic nook to
# the t7 teleporter and into the rockets-bait sink (trapped 16,
# negative frags). The corridor campaign owns those approaches;
# until it lands, dm2 regens pass --no-trains.
for b in ent_blocks:
    e = kv(b)
    if e.get("classname") == "path_corner":
        _corners[e.get("targetname", "")] = e

def _train_pad(corner, sx, sy, sz):
    cx, cy = corner[0] + sx / 2, corner[1] + sy / 2
    top = corner[2] + sz
    probes = ((corner[0] - 40, cy), (corner[0] + sx + 40, cy),
              (cx, corner[1] - 40), (cx, corner[1] + sy + 40),
              (cx, cy))
    for px_, py_ in probes:
        w = force_way(px_, py_, top + 24, 64)
        if w is not None:
            wx, wy, wz = pos(ways[w])
            if abs(wz - (top + 24)) < 72:
                return w
    return None

for b in ent_blocks:
    e = kv(b)
    if NO_TRAINS:
        break
    if e.get("classname") != "func_train" or "model" not in e:
        continue
    bm = bmodels[int(e["model"].lstrip("*"))]
    sx, sy, sz = bm[3] - bm[0], bm[4] - bm[1], bm[5] - bm[2]
    seenc = []
    c = _corners.get(e.get("target", ""))
    while c is not None and c.get("targetname") not in [q.get("targetname") for q in seenc]:
        seenc.append(c)
        c = _corners.get(c.get("target", ""))
    if len(seenc) < 2:
        continue
    ca = [float(v) for v in seenc[0]["origin"].split()]
    cb = [float(v) for v in seenc[-1]["origin"].split()]
    pa = _train_pad(ca, sx, sy, sz)
    pb = _train_pad(cb, sx, sy, sz)
    if pa is None or pb is None or pa == pb:
        print(f"train {e.get('model')} corners ({ca[0]:.0f} {ca[1]:.0f}) to "
              f"({cb[0]:.0f} {cb[1]:.0f}): no usable pads ({pa}, {pb})")
        continue
    trains.append((pa, pb))
    trains.append((pb, pa))
    print(f"train {e.get('model')}: ride n{pa} <-> n{pb} "
          f"(top z {ca[2] + sz:.0f})")
print(f"trains: {len(trains) // 2} shuttle(s) padded")

# ---- 5d. stair-run seat promotion ----
# (Omicron review, 2026-08-20): the 1998 bot's hand-made dm3 graph
# seats stairs one waypoint per 16u step - 236 seats on dm3 against
# 67-133 on every other map - because stair runs are exactly where
# coverage-radius decimation goes blind: treads are a thin diagonal
# band in xyz, the coarse lattice seats the floors above and below,
# and the run between often carries no seat for links to verify
# through. Detect maximal rising runs in the fine columns (each step
# +6..20u per grid column along an axis, total rise 40+) and promote
# a seat at the bottom, the top, and a long run's midpoint.
# force_way reuses any seat already within snap range, so open
# floors absorb these into existing coverage and only bare stair
# runs spend new seats.
def _col_z_near(cx, cy, zref, tol):
    zs = samples.get((cx, cy))
    if not zs:
        return None
    best = None
    for zz in zs:
        if abs(zz - zref) <= tol and (best is None
                                      or abs(zz - zref) < abs(zz - best)):
            best = zz
    return best

stair_seats = 0
stair_runs = 0
for (scx, scy), szs in sorted(samples.items()):
    for (dx, dy) in ((1, 0), (0, 1)):
        for z0 in szs:
            # a run STARTS with a rise, from a column whose own back
            # neighbour is not a riser below (true bottom); treads
            # deeper than one grid column show up as flat steps
            # between rises, so flats continue a run (two in a row
            # ends it - that is a landing, not a tread)
            if _col_z_near(scx - dx, scy - dy, z0 - 13, 7) is not None:
                continue
            if _col_z_near(scx + dx, scy + dy, z0 + 13, 7) is None:
                continue
            run = [(scx, scy, z0)]
            zcur = z0
            nx, ny = scx + dx, scy + dy
            rises = 0
            flats = 0
            while True:
                zn = _col_z_near(nx, ny, zcur + 13, 7)
                if zn is not None:
                    rises += 1
                    flats = 0
                else:
                    zn = _col_z_near(nx, ny, zcur, 5)
                    if zn is None or flats >= 2:
                        break
                    flats += 1
                run.append((nx, ny, zn))
                zcur = zn
                nx, ny = nx + dx, ny + dy
            while len(run) > 1 and abs(run[-1][2] - run[-2][2]) < 6:
                run.pop()               # trim trailing flats
            if rises >= 3 and run[-1][2] - z0 >= 40:
                stair_runs += 1
                seats = [run[0], run[-1]]
                if len(run) >= 9:
                    seats.append(run[len(run) // 2])
                for pt in seats:
                    w = force_way(xs[pt[0]], ys[pt[1]], pt[2] + 24,
                                  snap=40)
                    if w is not None:
                        stair_seats += 1
print(f"stair runs: {stair_runs} run(s), {stair_seats} seats placed or reused")

# ---- 6. waypoint links via Dijkstra on the fine graph ----
# links[i][j] = (pathlen, isjump); a link is jump-typed when the best
# fine path from i to j crosses at least one jump edge
wset = {w: i for i, w in enumerate(ways)}
links = collections.defaultdict(dict)
for i, w in enumerate(ways):
    dist = {w: 0.0}
    jumped = {w: 0}
    pq = [(0.0, w)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e9) or d > LINK_PATH_MAX: continue
        if u in wset and u != w:
            # only link if the fine path is nearly straight — bots beeline links
            ux, uy, uz = pos(u); wx, wy, wz = pos(w)
            euclid = ((ux-wx)**2 + (uy-wy)**2 + (uz-wz)**2) ** 0.5
            if d <= 1.35 * euclid + 24:
                links[i][wset[u]] = (d, jumped[u])
            continue                    # stop expanding past another waypoint
        for v, c, isj in fine.get(u, ()):
            nd = d + c
            if nd < dist.get(v, 1e9) and nd <= LINK_PATH_MAX:
                dist[v] = nd
                jumped[v] = jumped[u] or isj
                heapq.heappush(pq, (nd, v))
for i in list(links):
    if len(links[i]) > MAX_LINKS:
        links[i] = dict(sorted(links[i].items(), key=lambda kv: kv[1])[:MAX_LINKS])

# ---- 6b. beeline verification ----
# The straightness ratio only approximates "beeline-walkable", and the
# runtime executes links as beelines. A link whose fine path climbs a
# staircase can pass the ratio while its straight line pierces the
# stairwell wall — bots then wedge against it for minutes (dm4 node
# 122 -> 107 was the found case). Walk each link's actual line through
# hull 1: floor continuity, step-ups <= STEP, drops only forward.
# Jump links are exempt; their arc was verified in hull 1 already.
def beeline_ok(a, b):
    ax, ay, az = pos(a)
    bx, by, bz = pos(b)
    dist = ((bx-ax)**2 + (by-ay)**2) ** 0.5
    if dist < 1:
        return True
    steps = int(dist // 16) + 1
    px, py = -(by-ay) / dist, (bx-ax) / dist    # unit perpendicular
    z = az
    bad = 0
    for s in range(1, steps + 1):
        f = s / steps
        cx, cy = ax + (bx-ax)*f, ay + (by-ay)*f
        nz = None
        # walkmove slides along walls, so a line that clips a corner is
        # still walkable when floor continues just beside it: probe the
        # line first, then perpendicular offsets either side
        for off in (0, 16, -16, 32, -32):
            floors = column_floors(cx + px*off, cy + py*off)
            for fz in floors:                 # climbable step first
                if -STEP <= z - fz <= STEP:
                    nz = fz
                    break
            if nz is None:
                for fz in floors:             # forward drop is fine
                    if STEP < z - fz <= DROPMAX:
                        nz = fz
                        break
            # a lava or slime floor is not a step, it is a death:
            # reject and let the next offset look for a dry line
            if nz is not None and h0_contents(cx + px*off, cy + py*off, nz + 24) in (CONTENTS_LAVA, CONTENTS_SLIME):
                nz = None
            if nz is not None:
                break
        if nz is None:
            # tolerate brief nicks; sustained wall is a lie
            bad = bad + 1
            if bad >= 3:
                return False
            continue
        bad = 0
        z = nz
    return abs(z - bz) <= STEP

VERBOSE = "--verbose" in sys.argv[5:]
nbad = 0
for i in list(links):
    for j in list(links[i]):
        if not links[i][j][1] and not beeline_ok(ways[i], ways[j]):
            if VERBOSE:
                px = pos(ways[i])
                qx = pos(ways[j])
                print(f"  pruned {i}->{j}: "
                      f"({px[0]:.0f},{px[1]:.0f},{px[2]:.0f}) -> "
                      f"({qx[0]:.0f},{qx[1]:.0f},{qx[2]:.0f})")
            del links[i][j]
            nbad += 1
print(f"beeline verification pruned {nbad} wall-piercing links")

# ---- 6c. door-typed walk links ----
# Hull 1 never contains func_door brushes, so a beeline through a
# doorway is a legal walk. At runtime the slab is solid until opened.
# Tag those hops so the bot can press the button instead of pinning.
def _seg_hits_aabb(ax, ay, az, bx, by, bz, mn, mx, pad=8.0):
    mins = (mn[0] - pad, mn[1] - pad, mn[2] - pad)
    maxs = (mx[0] + pad, mx[1] + pad, mx[2] + pad)
    for s in range(9):
        f = s / 8.0
        p = (ax + (bx - ax) * f, ay + (by - ay) * f, az + (bz - az) * f)
        if (mins[0] <= p[0] <= maxs[0] and mins[1] <= p[1] <= maxs[1]
                and mins[2] <= p[2] <= maxs[2]):
            return True
    return False

door_boxes = []
for _b in ent_blocks:
    _e = kv(_b)
    if _e.get("classname") not in ("func_door", "func_door_secret"):
        continue
    if "model" not in _e:
        continue
    try:
        _bm = bmodels[int(_e["model"].lstrip("*"))]
    except (ValueError, IndexError):
        continue
    door_boxes.append(((_bm[0], _bm[1], _bm[2]), (_bm[3], _bm[4], _bm[5])))

doorlinks = []
if door_boxes:
    for i in list(links):
        for j in list(links[i]):
            if links[i][j][1]:
                continue
            ax, ay, az = pos(ways[i])
            bx, by, bz = pos(ways[j])
            if any(_seg_hits_aabb(ax, ay, az, bx, by, bz, mn, mx)
                   for mn, mx in door_boxes):
                doorlinks.append((i, j))
print(f"door links: {len(doorlinks)} (from {len(door_boxes)} door brush(es))")

_nlava = 0
if COST_CELLS:
    for i in list(links):
        for j in list(links[i]):
            if links[i][j][1]:
                continue
            ax, ay, az = pos(ways[i])
            bx, by, bz = pos(ways[j])
            mx, my, mz = (ax+bx)/2, (ay+by)/2, (az+bz)/2
            _lava = False
            for c in COST_CELLS:
                if c.get("kind") != "lava":
                    continue
                r = float(c.get("radius", 128))
                dx = mx - float(c.get("x", 0))
                dy = my - float(c.get("y", 0))
                dz = mz - float(c.get("z", 0))
                if dx*dx + dy*dy + dz*dz <= r*r:
                    _lava = True
                    break
            if _lava:
                del links[i][j]
                _nlava += 1
    print(f"hotspot costs dropped {_nlava} lava-crossing walk links")

nlinks = sum(len(v) for v in links.values())
oneway = sum(1 for i in links for j in links[i] if i not in links.get(j, {}))
njlinks = sum(1 for i in links for j in links[i] if links[i][j][1])
print(f"links: {nlinks} ({oneway} one-way, {njlinks} jump)")

# ---- 7. teleporters ----
def nearest_way(x, y, z):
    best, bd = None, 1e9
    for i, w in enumerate(ways):
        wx, wy, wz = pos(w)
        d = ((x-wx)**2 + (y-wy)**2 + (2*(z-wz))**2) ** 0.5
        if d < bd: best, bd = i, d
    return best
teles = []
dests = {}
for b in ent_blocks:
    e = kv(b)
    if e.get("classname") == "info_teleport_destination" and "targetname" in e:
        o = [float(v) for v in e.get("origin", "0 0 0").split()]
        dests[e["targetname"]] = o
for b in ent_blocks:
    e = kv(b)
    if e.get("classname") == "trigger_teleport" and e.get("target") in dests:
        mi = int(e["model"].lstrip("*"))
        bm = bmodels[mi]
        c = [(bm[0]+bm[3])/2, (bm[1]+bm[4])/2, (bm[2]+bm[5])/2]
        d = dests[e["target"]]
        teles.append((nearest_way(*c), nearest_way(*d)))
print(f"teleporter links: {len(teles)}")

# ---- 7a2. rocket-jump links ----
# Near-vertical blasts onto ledges a normal jump cannot hold: launch
# node to landing node, 40..240u up, modest horizontal travel. Model:
# jump 270 plus a conservative 380 of self-rocket knockback = 650 up,
# apex ~264u. Clearance: the ascent column above the launch point and
# the descent column above the landing must be open in hull 1, and the
# apex must see the landing. Emitted as Argus_NavLinkRocket; the
# runtime only routes them for bots holding RL, rockets and health.
RJ_VZ = 650.0
RJ_APEX = (RJ_VZ * RJ_VZ) / (2 * 800.0)

def rj_feasible(ax, ay, az, bx, by, bz, min_dz=100):
    dz = bz - az
    # 100 minimum: below that stairs or a plain jump exist and the
    # unweighted BFS would take the blast as a one-hop shortcut (first
    # A/B: bots rocket-jumped 48u stair climbs and shortfell into the
    # pit on long drifts). Sink escapes (7g) pass min_dz=40: their
    # entries are stripped so no through-route can abuse the low rise.
    # Horizontal cap 230: dm4 quad pads with
    # open sky sit ~180-220u out; the runtime aims toward the landing
    # (not 85-down) so the blast carries that far.
    if dz <= min_dz or dz > 240:
        return False
    horiz = ((bx-ax)**2 + (by-ay)**2) ** 0.5
    if horiz > 260:
        return False
    if dz + 24 > RJ_APEX:
        return False
    # ascent column above the launch, to landing height plus headroom
    z = az + 8
    top = az + dz + 56
    while z < top:
        if hull_contents(ax, ay, z) != CONTENTS_EMPTY:
            return False
        z += 24
    # descent column above the landing
    z = bz + 8
    top = bz + 56
    while z < top:
        if hull_contents(bx, by, z) != CONTENTS_EMPTY:
            return False
        z += 24
    # rise first, then drift in above the landing. A linear sag
    # dropped the midpoint into the ledge underside (dm4 quad).
    apex = max(az + 160, bz + 48)
    steps = max(2, int(horiz // 24))
    for s in range(1, steps + 1):
        f = s / steps
        x = ax + (bx-ax) * f
        y = ay + (by-ay) * f
        if f < 0.4:
            z = az + 80 + (apex - az - 80) * (f / 0.4)
        else:
            z = apex + (bz + 40 - apex) * ((f - 0.4) / 0.6)
        if hull_contents(x, y, z) != CONTENTS_EMPTY:
            return False
    return True

tele_out = collections.Counter(a for a, b in teles)
rjlinks = []
NO_RJ = "--no-rj" in sys.argv[5:]

def ensure_way(nid, radius=40):
    """Return the waypoint index for nid, promoting it if nothing is close."""
    if nid is None:
        return None
    x, y, z = pos(nid)
    best, bd = None, 1e9
    for i, w in enumerate(ways):
        wx, wy, wz = pos(w)
        d = ((x - wx) ** 2 + (y - wy) ** 2 + (2 * (z - wz)) ** 2) ** 0.5
        if d < bd:
            best, bd = i, d
    if best is not None and bd < radius:
        return best
    if len(ways) >= NODE_CAP:
        return best
    ways.append(nid)
    return len(ways) - 1

def try_rj(i, j):
    if i is None or j is None or i == j:
        return
    used = (len(links.get(i, {})) + tele_out[i]
            + sum(1 for x, _ in rjlinks if x == i))
    if used >= MAX_LINKS or j in links.get(i, {}):
        return
    if (i, j) in rjlinks:
        return
    ax, ay, az = pos(ways[i])
    bx, by, bz = pos(ways[j])
    if rj_feasible(ax, ay, az, bx, by, bz):
        rjlinks.append((i, j))

if not NO_RJ:
    # Prize items only. An all-pairs pass with the 230u horiz cap
    # minted 100+ shortcuts (stairs, pit lips) and BFS ate them.
    prize = (
        "item_artifact_super_damage",
        "item_artifact_invulnerability",
        "item_artifact_invisibility",
        "item_artifact_super_health",
        "item_health",
        "weapon_lightning",
        "weapon_rocketlauncher",
    )
    landings = []
    for b in ent_blocks:
        e = kv(b)
        cls = e.get("classname")
        if cls not in prize:
            continue
        if cls == "item_health" and int(e.get("spawnflags", "0") or 0) & 2 == 0:
            continue
        o = [float(v) for v in e.get("origin", "0 0 0").split()]
        nid, d = closest_nid(o[0], o[1], o[2])
        if nid is None or d > 96:
            continue
        j = ensure_way(nid, 48)
        if j is not None:
            landings.append((j, cls, o))
    n_promoted = 0
    for j, cls, o in landings:
        bx, by, bz = pos(ways[j])
        cands = []
        for (cx, cy), zs in samples.items():
            ax, ay = xs[cx], ys[cy]
            horiz = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            if horiz > 260:
                continue
            for zi, az in enumerate(zs):
                if not (100 < bz - az <= 240):
                    continue
                if not rj_feasible(ax, ay, az, bx, by, bz):
                    continue
                cands.append((horiz, cx, cy, zi))
        cands.sort()
        kept = 0
        for horiz, cx, cy, zi in cands:
            if kept >= 2:
                break
            before_n = len(ways)
            i = ensure_way((cx, cy, zi), 40)
            before = len(rjlinks)
            try_rj(i, j)
            if len(rjlinks) > before:
                kept += 1
                if i is not None and i >= before_n:
                    n_promoted += 1
    print(f"rocket-jump links: {len(rjlinks)} "
          f"({len(landings)} prize landings, {n_promoted} pads promoted)")
else:
    print("rocket-jump links: 0 (--no-rj)")

# ---- 7a3. pad walk-ins ----
# ensure_way promotes launch pads AFTER Dijkstra, so a promoted pad
# had no walk links at all: nothing ever routed ONTO it, and the RJ
# links were reachable only when a bot happened to stand there (zero
# rjump events in the v3.20 dm4 tape — Shane's fix-now list). Stitch
# every launch pad into the walk graph via its nearest
# beeline-verified neighbour, both directions when both survive.
inbound = set()
for _i in links:
    for _j in links[_i]:
        inbound.add(_j)
n_stitch = 0
for a in sorted(set(x for x, _ in rjlinks)):
    if a in inbound and len(links.get(a, {})) > 0:
        continue
    ax, ay, az = pos(ways[a])
    best_j, best_d = None, 1e9
    for j, w in enumerate(ways):
        if j == a:
            continue
        jx, jy, jz = pos(w)
        d2 = ((jx-ax)**2 + (jy-ay)**2 + (2*(jz-az))**2) ** 0.5
        if d2 < best_d and d2 <= 260:
            if beeline_ok(ways[j], ways[a]):
                best_j, best_d = j, d2
    if best_j is None:
        print(f"pad walk-in: no beeline neighbour for pad {a}; RJ link may be unreachable")
        continue
    links.setdefault(best_j, {})[a] = (best_d, 0)
    n_stitch += 1
    if beeline_ok(ways[a], ways[best_j]):
        links.setdefault(a, {})[best_j] = (best_d, 0)
        n_stitch += 1
print(f"pad walk-ins: {n_stitch} stitch links for promoted launch pads")

# ---- 7d. swim-exit links ----
# Hull 1 cannot see water (liquids are EMPTY in clip hulls), so a
# pool's floor samples emerge as an island: bots that fall in tread
# water while every route fails (dm3's central trench: 15 nodes
# connected to nothing, 670 swim events in one match). Classify
# waypoints against HULL 0 - the render BSP, where leaves keep real
# contents - and link each underwater waypoint to nearby dry
# waypoints at the surface lip. The runtime executes these with a
# waterjump gated to swim-link hops only, which by construction can
# never fire over dm4's lava: swim links are only emitted for
# CONTENTS_WATER, never slime or lava.
# h0_contents / water_surface_z now live above sampling (lava slice)

swims = []
n_swimnodes = 0
for i, w in enumerate(ways):
    wx, wy, wz = pos(w)
    if h0_contents(wx, wy, wz + 8) != CONTENTS_WATER:
        continue
    n_swimnodes += 1
    surf = water_surface_z(wx, wy, wz)
    exits = []
    for j, v in enumerate(ways):
        if i == j:
            continue
        vx, vy, vz = pos(v)
        if h0_contents(vx, vy, vz + 8) == CONTENTS_WATER:
            continue                      # dry exits only
        if not (surf - 12 <= vz <= surf + 44):
            continue                      # lip beyond a waterjump
        # the horizontal leg is SWUM, not jumped — the vault only
        # covers the final lip, so range is about keeping the runtime
        # beeline sane, not about jump physics
        horiz = ((vx - wx) ** 2 + (vy - wy) ** 2) ** 0.5
        if horiz > 320:
            continue
        # step the swim path in hull 0: every sample just under the
        # surface must be water or empty — a lip behind a pillar
        # used to emit anyway (Shane's correctness list). Stop 48u
        # short of the exit: the bank wall AT the lip is expected
        # (it is what the waterjump vaults) — checking into it
        # rejected every legitimate exit on the first pass
        span = horiz - 48
        if span > 24:
            steps = max(2, int(span // 24))
            clear = True
            for s in range(1, steps + 1):
                f = (s / steps) * (span / horiz)
                px_ = wx + (vx - wx) * f
                py_ = wy + (vy - wy) * f
                if h0_contents(px_, py_, surf - 8) not in (CONTENTS_WATER, -1):
                    # solid just under the surface: a submerged ridge
                    # a swimmer passes over, unless it is solid above
                    # the surface too — then it is a pillar or wall
                    if h0_contents(px_, py_, surf + 16) != -1:
                        clear = False
                        break
            if not clear:
                continue
        exits.append((horiz, i, j))
    for horiz, a, b in sorted(exits)[:2]:  # two nearest lips per node
        swims.append((a, b))
print(f"swim-exit links: {len(swims)} from {n_swimnodes} underwater waypoints")

# ---- 7e. link-slot budget ----
# a node has 8 link slots and the runtime's Argus_NavLink drops the
# 9th: typed links (teleporter, RJ, lift, swim) are emitted after
# walks and were falling off exactly on the best-connected nodes
# (lqdm2 n126 lost its teleporter — Shane's fix-now list). Evict the
# LONGEST plain walk links to guarantee room; jump-typed links are
# kept preferentially.
typed_out = collections.Counter()
for _a, _b in teles: typed_out[_a] += 1
for _a, _b in rjlinks: typed_out[_a] += 1
for _a, _b in lifts: typed_out[_a] += 1
for _a, _b in trains: typed_out[_a] += 1
for _a, _b in swims: typed_out[_a] += 1
n_evict = 0
for _i in list(links):
    room = 8 - typed_out[_i]
    if len(links[_i]) > room:
        keep_links = sorted(links[_i].items(),
                            key=lambda kv: (not kv[1][1], kv[1][0]))[:max(0, room)]
        n_evict += len(links[_i]) - len(keep_links)
        links[_i] = dict(keep_links)
if n_evict:
    print(f"link budget: evicted {n_evict} longest walk links so typed links fit 8 slots")
nlinks = sum(len(v) for v in links.values())

# ---- 7f. escape links for inbound-only nodes ----
# the isolated-node prune keeps anything with degree > 0, but a node
# with ONLY inbound links is a trap: Argus_NearestNode can pick it as
# a route START and BFS fails on the spot (dm3 n30, the west-yard
# routefail hotspot — Shane's correctness list). Stitch an outbound
# escape to the nearest beeline-verified neighbour; if nothing
# passes, strip its inbound walks so the prune removes it.
typed_from = set(a for a, _b in teles) | set(a for a, _b in rjlinks) \
    | set(a for a, _b in lifts) | set(a for a, _b in swims) \
    | set(a for a, _b in trains)
inbound_walk = collections.defaultdict(list)
for _i in links:
    for _j in links[_i]:
        inbound_walk[_j].append(_i)
n_escape = 0
n_trapped = 0
for i in range(len(ways)):
    if len(links.get(i, {})) > 0 or i in typed_from:
        continue                          # has an outbound already
    if not inbound_walk[i]:
        continue                          # fully isolated: prune's job
    ax, ay, az = pos(ways[i])
    cands = []
    for j, w in enumerate(ways):
        if j == i:
            continue
        jx, jy, jz = pos(w)
        d2 = ((jx - ax) ** 2 + (jy - ay) ** 2 + (2 * (jz - az)) ** 2) ** 0.5
        if d2 <= 300:
            cands.append((d2, j))
    stitched = False
    for d2, j in sorted(cands)[:8]:
        if beeline_ok(ways[i], ways[j]):
            links.setdefault(i, {})[j] = (d2, 0)
            n_escape += 1
            stitched = True
            break
    if not stitched:
        for src in inbound_walk[i]:
            links[src].pop(i, None)
        n_trapped += 1
if n_escape or n_trapped:
    print(f"escape links: {n_escape} stitched, {n_trapped} trap nodes stripped for prune")
    nlinks = sum(len(v) for v in links.values())

# ---- 7g. rocket-jump escapes from sink components ----
# 7f catches single inbound-only nodes, but trap nodes that cycle
# among THEMSELVES pass the per-node test: dm4's big-room pit floor
# is a two-node cycle with six drop links in and no exit of any kind,
# so a bot knocked in abandons in a spiral until the lava edge gets
# it. Find sink components (SCC with no link of any type leaving),
# stitch a rocket-jump escape to the rim (min rise 40, not the
# shortcut-guard 100 — the map itself makes RL-less occupants doomed
# there). Walk entries into the sink are KEPT: a first draft stripped
# them to stop dive-in-blast-out BFS shortcuts, and the strip
# amputated rim nodes whose only outbound led into the pit,
# recreating the very inbound-only traps 7f exists to catch (the
# sinkfix2 ladder match, abandon clusters at dm4 n3/n4). The RJ
# escape is equipment-gated at BFS time anyway, so a pit transit
# costs a rocket and ~100 effective health — rare and survivable
# where the amputation was a stall storm. A sink holding an item is
# left alone and reported: deliberate entry needs weighted costing
# (parked).
if not NO_RJ:
    _adj = collections.defaultdict(set)
    for _i in links:
        for _j in links[_i]:
            _adj[_i].add(_j)
    for _a, _b in teles + rjlinks + lifts + swims + trains:
        _adj[_a].add(_b)

    # iterative Tarjan
    _index = {}
    _low = {}
    _onstk = set()
    _stk = []
    _sccs = []
    _ctr = [0]
    for _root in range(len(ways)):
        if _root in _index:
            continue
        _work = [(_root, iter(sorted(_adj[_root])))]
        _index[_root] = _low[_root] = _ctr[0]
        _ctr[0] += 1
        _stk.append(_root)
        _onstk.add(_root)
        while _work:
            _v, _it = _work[-1]
            _adv = False
            for _w in _it:
                if _w not in _index:
                    _index[_w] = _low[_w] = _ctr[0]
                    _ctr[0] += 1
                    _stk.append(_w)
                    _onstk.add(_w)
                    _work.append((_w, iter(sorted(_adj[_w]))))
                    _adv = True
                    break
                elif _w in _onstk:
                    _low[_v] = min(_low[_v], _index[_w])
            if _adv:
                continue
            _work.pop()
            if _work:
                _low[_work[-1][0]] = min(_low[_work[-1][0]], _low[_v])
            if _low[_v] == _index[_v]:
                _c = set()
                while True:
                    _w = _stk.pop()
                    _onstk.discard(_w)
                    _c.add(_w)
                    if _w == _v:
                        break
                _sccs.append(_c)

    _item_pos = []
    for _b in ent_blocks:
        _e = kv(_b)
        _cls = _e.get("classname", "")
        if _cls.startswith("item_") or _cls.startswith("weapon_"):
            _o = _e.get("origin")
            if _o:
                _item_pos.append([float(v) for v in _o.split()])

    _biggest = max(_sccs, key=len) if _sccs else set()
    n_sinkesc = 0
    for _comp in _sccs:
        if _comp is _biggest:
            continue
        if any(_j not in _comp for _i in _comp for _j in _adj[_i]):
            continue                      # something leaves: not a sink
        _entries = [(_i, _j) for _i in links if _i not in _comp
                    for _j in links[_i] if _j in _comp]
        if not _entries:
            continue                      # unreachable island: prune's job
        _held = None
        for _m in _comp:
            _mx, _my, _mz = pos(ways[_m])
            for _ip in _item_pos:
                if (abs(_ip[0] - _mx) < 80 and abs(_ip[1] - _my) < 80
                        and abs(_ip[2] - _mz) < 64):
                    _held = _ip
                    break
            if _held:
                break
        if _held:
            # an item inside means routes SHOULD enter (utility bait),
            # which makes an escape mandatory, not optional: bots that
            # take the bait must be able to leave. The first policy
            # left these routable but unstitched, and Shane's v3.25
            # dm2 playtest watched bots pace forever at the
            # item_rockets sink '2232 -112 -160' (trapped suicides
            # covering for it in the tape)
            print(f"sink component {sorted(_comp)} holds an item at "
                  f"{_held} - stitching escape, entries kept")
        _cands = []
        for _m in _comp:
            _mx, _my, _mz = pos(ways[_m])
            _used = (len(links.get(_m, {})) + tele_out[_m]
                     + sum(1 for x, _ in rjlinks if x == _m))
            if _used >= MAX_LINKS:
                continue
            for _o in range(len(ways)):
                if _o in _comp:
                    continue
                _ox, _oy, _oz = pos(ways[_o])
                _h = ((_ox - _mx) ** 2 + (_oy - _my) ** 2) ** 0.5
                _dz = _oz - _mz
                if _dz <= 40 or _dz > 240 or _h > 260:
                    continue
                _cands.append((_dz + _h, _m, _o))
        _kept = 0
        _from = set()
        for _score, _m, _o in sorted(_cands):
            if _kept >= 2 or _m in _from:
                continue
            _mx, _my, _mz = pos(ways[_m])
            _ox, _oy, _oz = pos(ways[_o])
            if not rj_feasible(_mx, _my, _mz, _ox, _oy, _oz, min_dz=40):
                continue
            rjlinks.append((_m, _o))
            _from.add(_m)
            _kept += 1
            n_sinkesc += 1
        if _kept:
            _esc = [(a, b) for a, b in rjlinks[-_kept:]]
            print(f"sink {sorted(_comp)} (floor z {pos(ways[min(_comp)])[2]:.0f}): "
                  f"{_kept} RJ escape(s) {_esc}")
        else:
            print(f"sink component {sorted(_comp)} has no feasible RJ "
                  f"escape - bots knocked in stay trapped")
    if n_sinkesc:
        print(f"sink escapes: {n_sinkesc} RJ links stitched")

# ---- 7b. prune isolated waypoints ----
# A waypoint with no links in either direction (typically a secret alcove
# or an in-wall sliver) wastes an edict and, worse, makes every route
# starting or ending at it fail instantly if the runtime picks it as the
# nearest node. Drop them and remap indices.
deg = collections.Counter()
for i in links:
    for j in links[i]:
        deg[i] += 1
        deg[j] += 1
for a, b in teles:
    deg[a] += 1
    deg[b] += 1
for a, b in rjlinks:
    deg[a] += 1
    deg[b] += 1
for a, b in lifts:
    deg[a] += 1
    deg[b] += 1
for a, b in swims:
    deg[a] += 1
    deg[b] += 1
for a, b in trains:
    deg[a] += 1
    deg[b] += 1
keep = [i for i in range(len(ways)) if deg[i]]
if len(keep) < len(ways):
    remap = {old: new for new, old in enumerate(keep)}
    print(f"pruned {len(ways) - len(keep)} isolated waypoints")
    ways = [ways[i] for i in keep]
    links = {remap[i]: {remap[j]: d for j, d in ls.items() if j in remap}
             for i, ls in links.items() if i in remap}
    teles = [(remap[a], remap[b]) for a, b in teles]
    rjlinks = [(remap[a], remap[b]) for a, b in rjlinks]
    lifts = [(remap[a], remap[b]) for a, b in lifts]
    swims = [(remap[a], remap[b]) for a, b in swims]
    trains = [(remap[a], remap[b]) for a, b in trains]
    doorlinks = [(remap[a], remap[b]) for a, b in doorlinks
                 if a in remap and b in remap]

# ---- 8a0. compute camera vantage nodes ----
cam_nodes = []
for i, w in enumerate(ways):
    x, y, z = pos(w)
    out_drop = 0
    for j in links.get(i, {}):
        jx, jy, jz = pos(ways[j])
        if z - jz > 64:
            out_drop += 1
    if out_drop >= 2 or len(links.get(i, {})) >= 4:
        if all(((x - c[0])**2 + (y - c[1])**2)**0.5 > 240 for c, _, _ in cam_nodes):
            nbs = [pos(ways[j]) for j in links.get(i, {})]
            if nbs:
                avg_x = sum(p[0] for p in nbs) / len(nbs)
                avg_y = sum(p[1] for p in nbs) / len(nbs)
                import math
                yaw = math.degrees(math.atan2(avg_y - y, avg_x - x))
                cam_nodes.append(([x, y, z + 32], [-15, round(yaw, 1), 0], f"arena_{len(cam_nodes)+1}"))
                if len(cam_nodes) >= 6:
                    break

# ---- 8a. emit QC ----
with open(OUTQC, "w") as f:
    f.write("/* generated by argus_navgen.py — do not edit */\n\n")
    f.write(f"void() Argus_Nav_Spawn_{MAPNAME} =\n{{\n")
    for i, w in enumerate(ways):
        f.write(f"    local entity n{i};\n")
    f.write("\n")
    for i, w in enumerate(ways):
        x, y, z = pos(w)
        f.write(f"    n{i} = Argus_NavNode ('{x:.0f} {y:.0f} {z:.0f}');\n")
    f.write("\n")
    _doorset = set(doorlinks)
    for i in sorted(links):
        for j in links[i]:
            if links[i][j][1]:
                f.write(f"    Argus_NavLinkJump (n{i}, n{j});\n")
            elif (i, j) in _doorset:
                f.write(f"    Argus_NavLinkDoor (n{i}, n{j});\n")
            else:
                f.write(f"    Argus_NavLink (n{i}, n{j});\n")
    for a, b in teles:
        f.write(f"    Argus_NavLink (n{a}, n{b});    // teleporter\n")
    for a, b in rjlinks:
        f.write(f"    Argus_NavLinkRocket (n{a}, n{b});\n")
    for a, b in lifts:
        f.write(f"    Argus_NavLinkLift (n{a}, n{b});\n")
    for a, b in swims:
        f.write(f"    Argus_NavLinkSwim (n{a}, n{b});\n")
    for a, b in trains:
        f.write(f"    Argus_NavLinkTrain (n{a}, n{b});\n")
    if cam_nodes:
        f.write("\n    // Camera vantage nodes (Cartographer spectator anchors)\n")
        for cpos, cang, ctag in cam_nodes:
            f.write(f"    Argus_AddCamNode ('{cpos[0]:.0f} {cpos[1]:.0f} {cpos[2]:.0f}', '{cang[0]:.0f} {cang[1]:.0f} {cang[2]:.0f}', \"{ctag}\");\n")
    f.write(f'    dprint ("ARGNAV {len(ways)} nodes, '
            f'{nlinks + len(teles) + len(rjlinks) + len(lifts) + len(swims) + len(trains)} links\\n");\n')
    f.write("};\n")
    if EMIT_DISPATCHER:
        f.write("\nvoid() Argus_Nav_Spawn =\n{\n")
        f.write(f'    if (mapname == "{MAPNAME}")\n')
        f.write(f"        Argus_Nav_Spawn_{MAPNAME} ();\n")
        f.write("};\n")
import json
with open(OUTQC + ".json", "w") as jf:
    json.dump({"nodes": [pos(w) for w in ways],
               "links": [[i, j, int(i in links.get(j, {}))] for i in sorted(links) for j in links[i]],
               "jlinks": [[i, j] for i in sorted(links) for j in links[i] if links[i][j][1]],
               "rjlinks": rjlinks,
               "liftlinks": lifts,
               "swimlinks": swims,
               "trainlinks": trains,
               "doorlinks": doorlinks,
               "cam_nodes": [{"pos": cpos, "ang": cang, "tag": ctag} for cpos, cang, ctag in cam_nodes],
               "teles": teles}, jf)
print("wrote", OUTQC, "+ .json")
nents = len(ent_blocks)
edicts = len(ways) + nents
print(f"edict estimate: {edicts} (waypoints {len(ways)} + entities {nents})")
if edicts > 500:
    print(f"WARNING: edict estimate {edicts} exceeds 500; vanilla max_edicts is 600")

# ---- 8a2. --register: wire the map into the build ----
# Generating nav used to take four disconnected manual steps (navgen,
# progs.src line, dispatcher branch, recompile) and missing one made
# bots silently degrade to line-of-sight seeking (Shane's project
# review). --register does the two file edits here, idempotently; the
# compile stays yours.
if "--register" in sys.argv[5:]:
    import os
    srcdir = os.path.dirname(os.path.abspath(OUTQC))
    qcname = os.path.basename(OUTQC)
    ps = os.path.join(srcdir, "progs.src")
    dp = os.path.join(srcdir, "argus_nav_dispatch.qc")
    if not (os.path.exists(ps) and os.path.exists(dp)):
        print("register: progs.src / argus_nav_dispatch.qc not beside "
              "the output; skipped")
    else:
        t = open(ps).read()
        if qcname in t:
            print(f"register: {qcname} already in progs.src")
        elif "argus_nav_dispatch.qc" not in t:
            print("register: no argus_nav_dispatch.qc line in progs.src; skipped")
        else:
            open(ps, "w").write(t.replace(
                "argus_nav_dispatch.qc", f"{qcname}\nargus_nav_dispatch.qc", 1))
            print(f"register: added {qcname} to progs.src")
        t = open(dp).read()
        if f'"{MAPNAME}"' in t:
            print(f"register: dispatcher already routes {MAPNAME}")
        else:
            i = t.rfind("};")
            if i < 0:
                print("register: dispatcher end not found; skipped")
            else:
                branch = (f'    else if (mapname == "{MAPNAME}")\n'
                          f"        Argus_Nav_Spawn_{MAPNAME} ();\n")
                open(dp, "w").write(t[:i] + branch + t[i:])
                print(f"register: dispatcher branch added for {MAPNAME} "
                      f"(recompile to take effect)")

# ---- 8b. debug plot ----
# The PNG is a convenience, not a product: the QC and json are already
# written by this point. A python without matplotlib (the MCP invokes
# ARGUS_PYTHON, which may be a bare install) must not turn a successful
# generation into a failure exit.
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print(f"debug plot skipped: matplotlib not available in this python "
          f"(nav QC and json are written and valid)")
    sys.exit(0)
vo, vl = lumps[3]; eo, el = lumps[12]
verts = [struct.unpack_from("<fff", data, vo + i*12) for i in range(vl // 12)]
edges = [struct.unpack_from("<HH", data, eo + i*4) for i in range(el // 4)]
fig, ax = plt.subplots(figsize=(12, 12))
for a, b in edges[1:]:
    if a < len(verts) and b < len(verts):
        ax.plot([verts[a][0], verts[b][0]], [verts[a][1], verts[b][1]],
                color="0.88", lw=0.3, zorder=1)
for i in sorted(links):
    x1, y1, _ = pos(ways[i])
    for j in links[i]:
        x2, y2, _ = pos(ways[j])
        if links[i][j][1]:
            ax.plot([x1, x2], [y1, y2], color="#d62728", lw=1.5, ls=":",
                    alpha=0.9, zorder=2)
            continue
        two = i in links.get(j, {})
        ax.plot([x1, x2], [y1, y2], color="#2a9d5c" if two else "#cc8800",
                lw=0.9 if two else 1.2, alpha=0.7, zorder=2)
for a, b in teles:
    x1, y1, _ = pos(ways[a]); x2, y2, _ = pos(ways[b])
    ax.plot([x1, x2], [y1, y2], color="purple", lw=1.4, ls="--", zorder=2)
for a, b in rjlinks:
    x1, y1, _ = pos(ways[a]); x2, y2, _ = pos(ways[b])
    ax.plot([x1, x2], [y1, y2], color="#e377c2", lw=1.8, ls="-.", zorder=2)
wx = [pos(w)[0] for w in ways]; wy = [pos(w)[1] for w in ways]
ax.scatter(wx, wy, s=16, c="#1e6bd9", zorder=3)
ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
ax.set_title(f"Argus nav graph — {MAPNAME}: {len(ways)} nodes, {nlinks} links "
             f"({oneway} one-way, orange; {njlinks} jump, red dotted; "
             f"{len(rjlinks)} rocket-jump, magenta dash-dot), "
             f"{len(teles)} teleporter", fontsize=11)
plt.tight_layout(); plt.savefig(OUTPNG, dpi=130)
print("wrote", OUTPNG)
