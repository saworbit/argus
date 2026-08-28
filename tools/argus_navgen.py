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
# sprint jumps (Shane, 2026-08-21: "the jump to the MH and Red armour
# over the lava can be done if you shift sprint and time it just
# right - a high skill bot should just do that as a matter of
# course"): a second arc model at full run speed for edges the
# conservative 280 model refuses. These emit as a distinct typed
# link, the router only hands them to skill 2+ bots, and the runtime
# demands real sprint speed at the lip before firing.
SPRINTSPEED = 316.0

def arc_clear(x0, y0, z0, x1, y1, z1, speed=JUMPSPEED):
    dx, dy = x1 - x0, y1 - y0
    dist = (dx*dx + dy*dy) ** 0.5
    t_total = dist / speed
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
nsprint = 0
sprint_edges = []       # (from_nid, to_nid, horiz) for seat promotion
for (cx, cy), zs in samples.items():
    for zi, z in enumerate(zs):
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = samples.get((cx+dx, cy+dy))
            if nb is not None and near(nb, z, STEP) is not None:
                continue                # walkable: no jump needed
            # the normal scan reaches 5 cells; the sprint arc at full
            # run speed carries ~250u, which at a 16u corridor grid is
            # 15 cells out - scan the whole physical range and let
            # arc_clear's physics decide which model closes the gap
            for k in range(2, int(260 // GRID) + 2):
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
                step = (GRID*GRID*(dx*dx + dy*dy)) ** 0.5
                if k <= 5 and \
                        arc_clear(xs[cx], ys[cy], z, xs[cx+dx*k], ys[cy+dy*k], z2):
                    # the ORIGINAL 5-cell reach: only the sprint model
                    # earns the extended range - a 280-model jump has
                    # ~189u of flat range and the extended scan was
                    # minting 200u+ plain jump links that failed
                    # exactly like the unmodelled sprints did
                    fine[(cx,cy,zi)].append(((cx+dx*k, cy+dy*k, j2),
                                             step*k*1.5 + 40, 1))
                    njump += 1
                elif arc_clear(xs[cx], ys[cy], z, xs[cx+dx*k], ys[cy+dy*k],
                               z2, SPRINTSPEED):
                    # sprint-only arcs do NOT join the fine graph:
                    # threading them through Dijkstra either starves
                    # them (cost budget, straightness ratio) or
                    # re-types walkable links as skill-gated sprint.
                    # They emit DIRECTLY as typed links in 7a4, the
                    # proven rocket-jump pattern - and the pattern is
                    # the point: trick moves are a family (sprint
                    # arcs now, grenade jumps next), each an arc
                    # model plus a typed link plus a toll.
                    step = (GRID*GRID*(dx*dx + dy*dy)) ** 0.5
                    if step*k >= 120:
                        sprint_edges.append(((cx, cy, zi),
                                             (cx+dx*k, cy+dy*k, j2),
                                             step*k))
                    nsprint += 1
                break                   # nearest level candidate settles this direction
print(f"jump edges: {njump} plus {nsprint} sprint-only")

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
# typed-infrastructure promotions (plat pads, stair seats, sprint
# lips, RJ pads) may spend the edict headroom past the decimation
# target: the 200-node ceiling exists for edicts, not for its own
# sake, and on dm2 the corridor+stair+sprint seat passes consumed
# it before RJ pads got their turn - every ensure_way then snapped
# to the same wrong seat and all four RJ links vanished
PROMO_CAP = max(NODE_CAP, min(500 - len(ent_blocks) - 12, 260))

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

# ---- 5a2. wall-clearance seat shift ----
# The runtime hazard guard probes 32-52u ahead at POINT resolution
# while the bot is a 32u-wide box: a waypoint seated against a wall
# face makes every arriving bot bury its probe in the wall and
# deflect-dither AT its own steering target (dm3 '541 313 56': 82
# hazard deflections and a third of the tape's stalls in one cell,
# the knit3 ladder). When a decimation seat has walls inside 24u and
# a neighbouring sample at step height has more elbow room, seat
# there instead. Runs BEFORE the promotions: pads, stair seats and
# sprint anchors are geometry-anchored and never shifted.
def _clear_dirs(_x, _y, _z):
    _n = 0
    for _dx, _dy in ((24, 0), (-24, 0), (0, 24), (0, -24)):
        if hull_contents(_x + _dx, _y + _dy, _z + 8) == CONTENTS_EMPTY:
            _n += 1
    return _n


_wayset = set(ways)
_shifted = 0
for _wi in range(len(ways)):
    _cx, _cy, _zi = ways[_wi]
    _x, _y, _z = pos(ways[_wi])
    _c0 = _clear_dirs(_x, _y, _z)
    if _c0 >= 4:
        continue
    _best = None
    _bestc = _c0
    for _nb in ((_cx + 1, _cy), (_cx - 1, _cy),
                (_cx, _cy + 1), (_cx, _cy - 1)):
        _zs = samples.get(_nb)
        if not _zs:
            continue
        for _nzi in range(len(_zs)):
            _cand = (_nb[0], _nb[1], _nzi)
            if _cand in _wayset:
                continue
            _px, _py, _pz = pos(_cand)
            if abs(_pz - _z) > STEP:
                continue
            _cc = _clear_dirs(_px, _py, _pz)
            if _cc > _bestc:
                _bestc = _cc
                _best = _cand
    if _best is not None:
        _wayset.discard(ways[_wi])
        _wayset.add(_best)
        ways[_wi] = _best
        _shifted += 1
print(f"wall-clearance shift moved {_shifted} seats")

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
    if len(ways) >= PROMO_CAP:
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

def virtual_pad(bm, face_z):
    """Omicron's 1998 answer (their PLATBOTTOM seats sat ON the slab
    rest-top at dm2 *31): when no static floor serves the seated
    face at all, inject a SYNTHETIC sample at the slab centre so the
    pad exists anyway. The v3.47+ runtime already handles rest-top
    pads - the lift wait steers at the slab centre when seated and
    boards by contact - so the only missing piece was ever this
    seat. Virtual pads bypass PROMO_CAP (three per map at most, and
    they are the map's designed circulation). Dijkstra cannot link
    them (no fine-graph presence): section 6b3 stitches their
    walk-ins by direct clearance."""
    pcx, pcy = (bm[0] + bm[3]) / 2, (bm[1] + bm[4]) / 2
    cx = min(range(len(xs)), key=lambda i: abs(xs[i] - pcx))
    cy = min(range(len(ys)), key=lambda i: abs(ys[i] - pcy))
    zs = samples.setdefault((cx, cy), [])
    zs.append(face_z)
    ways.append((cx, cy, len(zs) - 1))
    return len(ways) - 1


# ---- 5a3. guaranteed control-item seats ----
# The idea-bank entry ("guaranteed waypoints at items") made urgent
# by the dm3 RL platform: decimation left the map's number-two
# control item 241u from its nearest seat, so bots goalled it,
# mode-1'd onto the moated platform, and had no route out - Shane
# watched one pace there for forty seconds. Every weapon, armour,
# powerup and mega now promotes the closest fine sample to a seat
# BEFORE link building; the exits then get Dijkstra, knitting and
# the puppet's verdicts like any other node.
_nitem = 0
for _b in ent_blocks:
    _e = kv(_b)
    _cls = _e.get("classname", "")
    _is_ctl = (_cls.startswith("weapon_")
               or _cls.startswith("item_armor")
               or _cls.startswith("item_artifact")
               or (_cls == "item_health"
                   and int(_e.get("spawnflags", "0") or 0) & 2))
    if not _is_ctl:
        continue
    _o = _e.get("origin")
    if not _o:
        continue
    _ox, _oy, _oz = (float(v) for v in _o.split())
    if force_way(_ox, _oy, _oz + 24, snap=48) is not None:
        _nitem += 1
print(f"control-item seats: {_nitem} guaranteed")

lifts = []
vpads = []
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
    if lo is None:
        lo = virtual_pad(bm, top_z - height)
        vpads.append((lo, bm))
        print(f"plat at ({pcx:.0f} {pcy:.0f}): VIRTUAL pad on the "
              f"slab rest-top at z {top_z - height:.0f} (the 5b gap, "
              f"closed per the dm3 musing)")
    hi = force_way(pcx, pcy, top_z + 24)
    if lo is None or hi is None or lo == hi:
        print(f"plat at ({pcx:.0f} {pcy:.0f}) travel {height:.0f}: "
              f"no usable pad (bottom {lo}, top {hi})")
        continue
    lifts.append((lo, hi))
print(f"plats: {len(lifts)} lift(s) padded ({len(vpads)} virtual)")

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

# ---- 5e. sprint-jump launch and landing seats ----
# A trick jump is only routable if waypoints stand AT its lip and
# its landing (the RJ pad-promotion lesson). First collapse the
# parallel-scan duplicates - a 226u crossing shows up once per
# 16u-spaced column along the lip - keeping the longest of each
# cluster, then promote both ends exactly (snap 8: any looser and
# the seat lands beside the lip, and the runtime beeline launches
# from the wrong spot).
sprint_edges.sort(key=lambda e: -e[2])
_kept_edges = []
for _sa, _sb, _sd in sprint_edges:
    ax_, ay_ = xs[_sa[0]], ys[_sa[1]]
    bx_, by_ = xs[_sb[0]], ys[_sb[1]]
    dup = False
    for _ka, _kb, _kd in _kept_edges:
        kax, kay = xs[_ka[0]], ys[_ka[1]]
        kbx, kby = xs[_kb[0]], ys[_kb[1]]
        if (((ax_-kax)**2 + (ay_-kay)**2) ** 0.5 < 64
                and ((bx_-kbx)**2 + (by_-kby)**2) ** 0.5 < 64):
            dup = True
            break
    if not dup:
        _kept_edges.append((_sa, _sb, _sd))
sprint_edges = _kept_edges
sprint_seats = 0
for _sa, _sb, _sd in sprint_edges:
    for pt in (_sa, _sb):
        w = force_way(xs[pt[0]], ys[pt[1]], samples[(pt[0], pt[1])][pt[2]] + 24,
                      snap=8)
        if w is not None:
            sprint_seats += 1
if sprint_edges:
    print(f"sprint seats: {sprint_seats} placed or reused for "
          f"{len(sprint_edges)} deduped long sprint edge(s)")

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
            # only link if the fine path is nearly straight — bots beeline links.
            # A sprint-class path carries a +110 lineup tax that the
            # straightness ratio would misread as crookedness: accept
            # it when the cost is essentially just the arc (the seats
            # sit at the lip and the landing), reject winding
            # walk-then-arc composites the runtime cannot beeline.
            ux, uy, uz = pos(u); wx, wy, wz = pos(w)
            euclid = ((ux-wx)**2 + (uy-wy)**2 + (uz-wz)**2) ** 0.5
            if d <= 1.35 * euclid + 24:
                links[i][wset[u]] = (d, jumped[u])
            continue                    # stop expanding past another waypoint
        for v, c, isj in fine.get(u, ()):
            nd = d + c
            if nd < dist.get(v, 1e9) and nd <= LINK_PATH_MAX:
                dist[v] = nd
                # carry the STRONGEST edge class on the path: 2 =
                # sprint-only jump outranks 1 = normal jump, so a
                # link whose fine path needs the full-speed arc is
                # typed sprint even if it also crosses a plain gap
                jumped[v] = max(jumped[u], isj)
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
    wallrun = 0
    for s in range(1, steps + 1):
        f = s / steps
        cx, cy = ax + (bx-ax)*f, ay + (by-ay)*f
        nz = None
        # walkmove slides along walls, so a line that clips a corner is
        # still walkable when floor continues just beside it: probe the
        # line first, then perpendicular offsets either side
        useoff = 0
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
                useoff = off
                break
        if nz is None:
            # tolerate brief nicks; sustained wall is a lie
            bad = bad + 1
            if bad >= 3:
                return False
            continue
        # NEGATIVE RESULTS, three of them (2026-08-28, the quad-court
        # pit-mouth link n68->n248): a +-16 offset cap, an any-offset
        # streak, and a runtime-veto-simulation streak were each
        # tried here to kill links whose centre line crosses ground
        # the brink guard deflects at. All three amputated half the
        # west wing (121-140 nodes to the poison prune): HazardSteer
        # makes rim-hugging lines PARTIALLY walkable, so walkability
        # under steering slack is graded, and a binary line-level
        # criterion cannot separate "slides past with a wobble" from
        # "deflect-dances forever". The pit-mouth class needs APEX
        # SEATS (seat the elbow so routes bend around small voids) -
        # the corridor-campaign design, filed in the dm3 musing.
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

# ---- 6b2. symmetric closure on climbable one-ways ----
# The Dijkstra pass links i->j when a fine path exists in that
# direction, but neighbour candidacy is not symmetric: dm3 shipped 55
# near-level one-way links (dz 16 steps linked downhill only), and
# every spurious one-way starves directed reach for no geometric
# reason. For each one-way walk link whose REVERSE beeline verifies
# (beeline_ok refuses climbs past STEP, so true drops stay one-way),
# add the reverse. Jump-tagged links are directional arcs and are
# never closed.
nclosed = 0
for i in list(links):
    for j in list(links[i]):
        if links[i][j][1]:
            continue                      # jump arc: directional
        if i in links.get(j, {}):
            continue                      # already two-way
        if beeline_ok(ways[j], ways[i]):
            links.setdefault(j, {})[i] = (links[i][j][0], 0)
            nclosed += 1
print(f"symmetric closure added {nclosed} reverse links")

# ---- 6b2b. jump-up links (dm3 musing S3) ----
# The one-way membrane is made of drop lips. Jump 270 apexes at
# ~45u: any one-way drop whose rise is jumpable gets its REVERSE
# minted as a jump-typed link (an_jumpmask - the runtime's climb
# branch fires beside the lip). Clearance: the line at apex-torso
# height must be open, and the lip's top edge must not overhang.
njup = 0
for i in list(links):
    for j in list(links[i]):
        if links[i][j][1]:
            continue
        if i in links.get(j, {}):
            continue
        ix, iy, iz = pos(ways[i])
        jx, jy, jz = pos(ways[j])
        rise = iz - jz                      # climbing back j -> i
        h = ((ix - jx) ** 2 + (iy - jy) ** 2) ** 0.5
        if not (STEP < rise <= 44) or h > 180:
            continue
        clear = True
        for f in (0.35, 0.6, 0.85):
            px = jx + (ix - jx) * f
            py = jy + (iy - jy) * f
            if h0_contents(px, py, jz + 76) == CONTENTS_SOLID:
                clear = False
                break
        if clear and h0_contents(ix, iy, iz + 40) != CONTENTS_SOLID:
            links.setdefault(j, {})[i] = (links[i][j][0], 1)
            njup += 1
print(f"jump-up links minted: {njup}")

# ---- 6b3. virtual plat pad walk-ins ----
# A virtual pad (5b) has no fine-graph presence, so Dijkstra gave it
# nothing. Stitch direct walk links to nodes at seated-face height
# with a clear straight line - at rest the slab occupies this space
# (its compiled position is TOP), so the BSP reads open here and a
# midpoint clearance check is honest.
for _vp, _bm in vpads:
    _vx, _vy, _vz = pos(ways[_vp])
    _added = 0
    _cands = []
    for _o in range(len(ways)):
        if _o == _vp:
            continue
        _ox, _oy, _oz = pos(ways[_o])
        _h = ((_ox - _vx) ** 2 + (_oy - _vy) ** 2) ** 0.5
        if abs(_oz - _vz) <= 24 and 20 < _h <= 220:
            _cands.append((_h, _o))
    for _h, _o in sorted(_cands)[:4]:
        _ox, _oy, _oz = pos(ways[_o])
        _ok = True
        for _f in (0.3, 0.5, 0.7):
            if h0_contents(_vx + (_ox - _vx) * _f,
                           _vy + (_oy - _vy) * _f,
                           _vz + 30) == CONTENTS_SOLID:
                _ok = False
                break
        if _ok:
            links.setdefault(_o, {})[_vp] = (_h, 0)
            links.setdefault(_vp, {})[_o] = (_h, 0)
            _added += 1
    print(f"virtual pad n{_vp} ({_vx:.0f} {_vy:.0f} {_vz:.0f}): "
          f"{_added} walk-in(s)")

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
    if len(ways) >= PROMO_CAP:
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
        # snap 16, not 48: the arc is re-verified against the SEAT,
        # and a landing seat offset half a hull sideways aims the
        # rise-then-drift arc into the ledge underside
        j = ensure_way(nid, 16)
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
            # snap 4: promote the EXACT sample that passed
            # rj_feasible. Any looser and the candidate snaps onto a
            # nearby stair/sprint seat whose position fails the arc
            # or whose link slots are already full (dm2 lost all four
            # RJ links to both modes at once)
            i = ensure_way((cx, cy, zi), 4)
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

# ---- 7a4. sprint-jump typed links (direct emission) ----
# The rocket-jump pattern, not the Dijkstra one: threading sprint
# arcs through the fine graph either starved them (cost budget,
# straightness ratio) or re-typed walkable links as skill-gated
# sprint. Each deduped long arc becomes exactly one typed link
# between its promoted seats, re-verified from the seat positions.
# This is the extensible shape for the whole trick-move family:
# an arc model, a typed link, and a toll the router checks.
sprints = []
for _sa, _sb, _sd in sprint_edges:
    i = ensure_way(_sa, 8)
    j = ensure_way(_sb, 8)
    if i is None or j is None or i == j:
        continue
    if (i, j) in sprints or j in links.get(i, {}):
        continue
    ax, ay, az = pos(ways[i])
    bx, by, bz = pos(ways[j])
    if not arc_clear(ax, ay, az, bx, by, bz, SPRINTSPEED):
        continue                # seat drifted off the verified sample
    sprints.append((i, j))
print(f"sprint links: {len(sprints)} typed "
      f"({len(sprint_edges)} deduped long arcs)")

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
for _a, _b in sprints: typed_out[_a] += 1
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
    | set(a for a, _b in trains) | set(a for a, _b in sprints)
inbound_walk = collections.defaultdict(list)
for _i in links:
    for _j in links[_i]:
        inbound_walk[_j].append(_i)
# inbound of ANY type: a teleporter DESTINATION with no walk links
# slipped between this pass (which demanded walk inbound) and the
# prune (where the tele reference counts as degree). dm2's t2
# destination seat shipped with zero outbound links - every bot
# whose route started there failed the whole goal menu and took the
# trapped exit on open floor (v369 tape, Carmack -2 in 64 s)
inbound_typed = collections.defaultdict(int)
for _a, _b in teles + rjlinks + lifts + swims + trains + sprints:
    inbound_typed[_b] += 1
n_escape = 0
n_trapped = 0
for i in range(len(ways)):
    if len(links.get(i, {})) > 0 or i in typed_from:
        continue                          # has an outbound already
    if not inbound_walk[i] and not inbound_typed[i]:
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
        if inbound_typed[i]:
            # a typed ARRIVAL (tele destination, ride exit) cannot be
            # stripped away - the arrival is real geometry. No escape
            # within reach is a generation-stopping defect: say so.
            print(f"escape links: typed-arrival node {i} at "
                  f"{pos(ways[i])} has NO reachable outbound - bots "
                  f"arriving here are stranded; fix the seat")
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
        # a DOWNWARD sink - a ledge, like the dm4 quad perch {55,56} -
        # escapes by DROPPING, not by rocket: try beeline-verified
        # one-way drop links to lower nodes first, and only a
        # still-trapped component falls through to the RJ stitcher.
        # (2026-08-27: the hunch multiplied quad-ledge traffic and 26
        # routefails piled onto n56 in one match; reach from the ledge
        # was 2 of 145 and had been since the graph shipped - the
        # up-only stitcher printed "no feasible RJ escape" and moved
        # on.)
        _dropped = 0
        for _m in sorted(_comp):
            if _dropped >= 2:
                break
            _mx, _my, _mz = pos(ways[_m])
            _used = (len(links.get(_m, {})) + tele_out[_m]
                     + sum(1 for x, _ in rjlinks if x == _m))
            if _used >= MAX_LINKS:
                continue
            _dc = []
            for _o in range(len(ways)):
                if _o in _comp:
                    continue
                _ox, _oy, _oz = pos(ways[_o])
                _h = ((_ox - _mx) ** 2 + (_oy - _my) ** 2) ** 0.5
                _dz = _mz - _oz
                if not (STEP < _dz <= DROPMAX) or _h > 240:
                    continue
                _dc.append((_h + _dz, _o))
            for _s, _o in sorted(_dc)[:8]:
                if beeline_ok(ways[_m], ways[_o]):
                    links.setdefault(_m, {})[_o] = (_s, 0)
                    _dropped += 1
                    print(f"sink {sorted(_comp)}: drop escape {_m}->{_o}")
                    break
        if _dropped:
            n_sinkesc += _dropped
            continue                      # escaped by drops; no RJ needed
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

# ---- 7g2. reachability knitting ----
# 7g heals strict sinks (SCCs with zero outgoing edges), but dm3
# taught the general case: a pocket that leaks into ANOTHER dying
# pocket passes the sink test and still never reaches the mainland,
# and one-way drop chains turn a vertical map into a downward DAG
# where every spawn strands (worst dm3 spawn: 4 of 252 nodes).
# The honest criterion is reachability itself: iterate until every
# node can reach the largest SCC (the mainland) and be reached from
# it, stitching one link per round - a two-way walk join where the
# separation is flat (fine-sampling gaps between components), a
# one-way drop where the pocket sits above, a rocket jump only as
# the last resort (equipment-gated at BFS time, invisible to
# RL-less bots - the v3.69 lesson). Unhealable pockets are reported
# and left for the prune or the trapped exit.

def _knit_sccs(_fwd, _n):
    _index = {}
    _low = {}
    _onstk = set()
    _stk = []
    _out = []
    _ctr = [0]
    for _root in range(_n):
        if _root in _index:
            continue
        _work = [(_root, iter(sorted(_fwd[_root])))]
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
                    _work.append((_w, iter(sorted(_fwd[_w]))))
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
                _out.append(_c)
    return _out


def _knit_pass(_toward_main, _use_rj):
    # _toward_main True stitches ESCAPES (pocket -> mainland-reaching
    # set); False stitches ENTRIES (mainland-reachable set -> pocket).
    # _use_rj False runs the pass blind to rocket-jump links entirely
    # (neither traversing nor stitching them): RJ edges are equipment-
    # gated at BFS time, so ungated connectivity is the real bar - a
    # spawn whose only escape is an RJ link strands every RL-less bot
    # (dm3 n43 measured 5% ungated against 62% gated).
    _added = 0
    _frozen = set()
    _reported = set()
    for _round in range(96):
        _fwd = collections.defaultdict(set)
        for _i in links:
            for _j in links[_i]:
                _fwd[_i].add(_j)
        _typed = teles + lifts + swims + trains
        if _use_rj:
            _typed = _typed + rjlinks
        for _a, _b in _typed:
            _fwd[_a].add(_b)
        _rev = collections.defaultdict(set)
        for _i in _fwd:
            for _j in _fwd[_i]:
                _rev[_j].add(_i)
        _sccs = _knit_sccs(_fwd, len(ways))
        _main = max(_sccs, key=len)
        # good = nodes already connected to the mainland in the
        # direction this pass cares about
        _walkdir = _rev if _toward_main else _fwd
        _good = set(_main)
        _q = list(_main)
        while _q:
            _u = _q.pop()
            for _v in _walkdir[_u]:
                if _v not in _good:
                    _good.add(_v)
                    _q.append(_v)
        _pockets = [_c for _c in _sccs
                    if not (_c & _good) and frozenset(_c) not in _frozen]
        if not _pockets:
            break
        _comp = max(_pockets, key=len)
        _stitched = False
        # candidate pairs: _m inside the pocket, _o in the good set;
        # for entries the link runs _o -> _m
        _walkc = []
        _dropc = []
        _rjc = []
        for _m in _comp:
            _mx, _my, _mz = pos(ways[_m])
            for _o in _good:
                _ox, _oy, _oz = pos(ways[_o])
                _h = ((_ox - _mx) ** 2 + (_oy - _my) ** 2) ** 0.5
                _dz = _mz - _oz            # positive: pocket above
                # |dz| to 90: stair runs climb that much over a 320
                # beeline, and beeline_ok refuses dishonest climbs
                # anyway. (Tried for the dm3 west wing's entry
                # stranding and did NOT heal it - that wing hides
                # behind drop lips on every side, one-way by nature;
                # its entries are corridor-campaign work. Kept
                # because the wider window is free and honest.)
                if _h <= 320 and abs(_dz) <= 90:
                    _walkc.append((_h, _m, _o))
                _dd = _dz if _toward_main else -_dz
                if STEP < _dd <= DROPMAX and _h <= 240:
                    _dropc.append((_h + _dd, _m, _o, 0))
                elif DROPMAX < _dd <= 500 and _h <= 96:
                    # the DIVE: a fall past DROPMAX is legal when it
                    # lands in water - and since the v3.75-era water
                    # work the runtime executes it (MoveHazard passes
                    # deep-water columns, the advance gate closes on
                    # a submerged target, the lip-drop steps off).
                    # The first knit1 build minted these while the
                    # runtime still vetoed them and the whole dm3
                    # deep level went dark: never emit a link class
                    # the runtime cannot walk.
                    _lx, _ly, _lz = ((_ox, _oy, _oz) if _toward_main
                                     else (_mx, _my, _mz))
                    if h0_contents(_lx, _ly, _lz) == CONTENTS_WATER:
                        _dropc.append((_h + _dd + 500, _m, _o, 1))
                _du = -_dz if _toward_main else _dz
                if (40 < _du <= 240 and _h <= 260 and not NO_RJ
                        and _use_rj):
                    _rjc.append((_du + _h, _m, _o))

        def _src_dst(_m, _o):
            return (_m, _o) if _toward_main else (_o, _m)

        def _slot_free(_s):
            _u = (len(links.get(_s, {})) + tele_out[_s]
                  + sum(1 for x, _ in rjlinks if x == _s))
            return _u < MAX_LINKS

        for _h, _m, _o in sorted(_walkc)[:48]:
            _s, _d = _src_dst(_m, _o)
            if _slot_free(_s) and beeline_ok(ways[_s], ways[_d]):
                links.setdefault(_s, {})[_d] = (_h, 0)
                if _slot_free(_d) and beeline_ok(ways[_d], ways[_s]):
                    links.setdefault(_d, {})[_s] = (_h, 0)
                print(f"knit walk {_s}->{_d}")
                _stitched = True
                break
        if not _stitched:
            # JUMP stitch (the RL-islet class, taught by the puppet's
            # verdicts): a same-level pocket ringed by a short void -
            # the dm3 RL platform sits behind a 32-64u moat - joins
            # by a jump link when the centre-line void fits the
            # proven jump envelope and everything else on the line
            # is honest floor. Mirrors the 7g2c remint criterion.
            for _h, _m, _o in sorted(_walkc)[:48]:
                _s, _d = _src_dst(_m, _o)
                if not _slot_free(_s) or _h > 280:
                    continue
                _sx, _sy, _sz = pos(ways[_s])
                _dx2, _dy2, _dz2 = pos(ways[_d])
                _steps = int(_h // 16) + 1
                _void = 0
                _maxvoid = 0
                _dry = 0
                for _st2 in range(1, _steps + 1):
                    _f = _st2 / _steps
                    _cx2 = _sx + (_dx2 - _sx) * _f
                    _cy2 = _sy + (_dy2 - _sy) * _f
                    _okf = False
                    for _fz in column_floors(_cx2, _cy2):
                        if abs(_sz - 24 - _fz) <= 48:
                            _okf = True
                            break
                    if _okf:
                        _dry += 1
                        _void = 0
                    else:
                        _void += 1
                        _maxvoid = max(_maxvoid, _void)
                if not (0 < _maxvoid * 16 <= 200):
                    continue
                if _dry < _steps - _maxvoid - 2:
                    continue              # more than one clean gap
                if h0_contents((_sx + _dx2) / 2, (_sy + _dy2) / 2,
                               _sz + 60) == CONTENTS_SOLID:
                    continue              # no arc clearance
                links.setdefault(_s, {})[_d] = (_h, 1)
                print(f"knit jump {_s}->{_d} (void {_maxvoid * 16}u)")
                _stitched = True
                break
        if not _stitched:
            for _sc, _m, _o, _wet in sorted(_dropc)[:48]:
                _s, _d = _src_dst(_m, _o)
                if not _slot_free(_s):
                    continue
                if _wet:
                    # beeline refuses drops past DROPMAX; a dive only
                    # needs the lip edge clear of solid
                    _sx, _sy, _sz = pos(ways[_s])
                    _dx2, _dy2, _dz2 = pos(ways[_d])
                    if h0_contents((_sx + _dx2) / 2, (_sy + _dy2) / 2,
                                   _sz + 8) == CONTENTS_SOLID:
                        continue
                elif not beeline_ok(ways[_s], ways[_d]):
                    continue
                links.setdefault(_s, {})[_d] = (_sc, 0)
                print(f"knit {'dive' if _wet else 'drop'} {_s}->{_d}")
                _stitched = True
                break
        if not _stitched:
            for _sc, _m, _o in sorted(_rjc)[:24]:
                _s, _d = _src_dst(_m, _o)
                _sx, _sy, _sz = pos(ways[_s])
                _dx, _dy, _dz2 = pos(ways[_d])
                if (_slot_free(_s)
                        and rj_feasible(_sx, _sy, _sz, _dx, _dy, _dz2,
                                        min_dz=40)):
                    rjlinks.append((_s, _d))
                    print(f"knit RJ {_s}->{_d}")
                    _stitched = True
                    break
        if _stitched:
            _added += 1
            # a new stitch can make a frozen pocket healable through
            # the node it just connected: retry everything
            _frozen.clear()
        else:
            _frozen.add(frozenset(_comp))
            if frozenset(_comp) not in _reported:
                _reported.add(frozenset(_comp))
                _dir = "escape" if _toward_main else "entry"
                print(f"knit: pocket {sorted(_comp)} has no feasible "
                      f"{_dir} - left stranded")
    return _added


# ungated connectivity first (walk and drop only, RJ edges invisible),
# then a gated sweep for whatever geometry truly demands a rocket
_nknit = (_knit_pass(True, False) + _knit_pass(False, False)
          + _knit_pass(True, True) + _knit_pass(False, True))
print(f"reachability knitting stitched {_nknit} links")

# ---- 7g2b. human-trace link mining (dm3 musing S1) ----
# The sessions are already recorded and harvested; a demo track is a
# 69 Hz proof of where a human actually walked. Snap every sample of
# every runs/demos/*<map>*.tracks.json to the graph, collect node
# transitions the graph has no edge for, and mint the ones that pass
# the SAME verification as any other link - beeline for walks, the
# jump-up clearance for climbs. Human-proven is not bot-walkable
# (the knit1 lip-statue lesson), so nothing is trusted from the
# trace alone; the trace only NOMINATES. Teleport/knockback
# artifacts are cut by the segment-length filter and a two-sighting
# minimum.
import glob as _glob
import os as _os
_tracedir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                          "..", "runs", "demos")
_tracefiles = sorted(_glob.glob(_os.path.join(
    _tracedir, f"*{MAPNAME}*.tracks.json")))
if _tracefiles:
    import json as _json
    _cellidx = {}
    for _i in range(len(ways)):
        _x, _y, _z = pos(ways[_i])
        _cellidx.setdefault((int(_x // 128), int(_y // 128)),
                            []).append(_i)

    def _snap(_x, _y, _z):
        _best, _bd = -1, 80.0 * 80.0
        _cx, _cy = int(_x // 128), int(_y // 128)
        for _gx in (_cx - 1, _cx, _cx + 1):
            for _gy in (_cy - 1, _cy, _cy + 1):
                for _i in _cellidx.get((_gx, _gy), ()):
                    _nx, _ny, _nz = pos(ways[_i])
                    if abs(_nz - _z) > 56:
                        continue
                    _d = (_nx - _x) ** 2 + (_ny - _y) ** 2
                    if _d < _bd:
                        _bd = _d
                        _best = _i
        return _best

    _sightings = {}
    for _tf in _tracefiles:
        try:
            _doc = _json.load(open(_tf))
        except Exception:
            print(f"trace mining: unreadable {_os.path.basename(_tf)}")
            continue
        for _tr in _doc.get("tracks", []):
            if _tr.get("kind") != "player":
                continue
            _ts = _tr.get("t", [])
            _psl = _tr.get("pos", [])
            _cur = -1
            _last = None
            for _t, _p in zip(_ts, _psl):
                if _last is not None and (
                        (_p[0] - _last[0]) ** 2
                        + (_p[1] - _last[1]) ** 2) > 200 * 200:
                    _cur = -1           # teleport / respawn: break
                _last = _p
                _b = _snap(_p[0], _p[1], _p[2])
                if _b < 0 or _b == _cur:
                    continue
                _a = _cur
                _cur = _b
                if _a < 0 or _b in links.get(_a, {}):
                    continue
                _sightings[(_a, _b)] = _sightings.get((_a, _b), 0) + 1
    _mined_w = 0
    _mined_j = 0
    for (_a, _b), _c in sorted(_sightings.items(),
                               key=lambda kv: -kv[1]):
        if _c < 2 or _mined_w + _mined_j >= 24:
            continue
        if _b in links.get(_a, {}):
            continue
        _ax, _ay, _az = pos(ways[_a])
        _bx, _by, _bz = pos(ways[_b])
        _h = ((_bx - _ax) ** 2 + (_by - _ay) ** 2) ** 0.5
        if _h > 400:
            continue
        if beeline_ok(ways[_a], ways[_b]):
            links.setdefault(_a, {})[_b] = (_h, 0)
            _mined_w += 1
            print(f"trace-mined walk {_a}->{_b} (x{_c})")
        elif STEP < _bz - _az <= 44 and _h <= 180:
            _clear = True
            for _f in (0.35, 0.6, 0.85):
                if h0_contents(_ax + (_bx - _ax) * _f,
                               _ay + (_by - _ay) * _f,
                               _az + 76) == CONTENTS_SOLID:
                    _clear = False
                    break
            if _clear:
                links.setdefault(_a, {})[_b] = (_h, 1)
                _mined_j += 1
                print(f"trace-mined jump-up {_a}->{_b} (x{_c})")
    print(f"trace mining: {len(_tracefiles)} track file(s), "
          f"{len(_sightings)} unmapped transitions seen, minted "
          f"{_mined_w} walk + {_mined_j} jump links")

# ---- 7g2c. engine-verdict prune and remint ----
# The lab's NetQuake client (netclient.rs) walks links in the REAL
# engine and records the ones no player can WALK - empirical ground
# truth, the referee the three failed 2026-08-28 geometric criteria
# were approximating. Its first sweep convicted the dm3 quad-court
# pit-mouth pair at the exact ladder-tape coordinates. Verdicts are
# stored by ENDPOINT COORDINATES (indices shift per regen).
# A refuted WALK link is not always a dead link: the first two
# convictions cross a 40u deck opening a human clears without
# breaking stride - the link was MISTYPED, not dishonest. So the
# verdict pass remints: a refuted pair whose centre-line void is a
# short gap (<= 3 samples, one jump arc) becomes a JUMP link - the
# runtime launches at the lip like the dm4 lava-gap crossing - and
# only unjumpable refusals die outright. Deleting both dm3 pairs
# without the remint stranded 123 nodes: the "dishonest" links were
# load-bearing, which is exactly why bots jammed on them.
import json as _json
_probepath = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.abspath(OUTQC)),
    f"argus_nav_{MAPNAME}.probe.json")
if __import__("os").path.exists(_probepath):
    try:
        _pdoc = _json.load(open(_probepath))
    except Exception:
        _pdoc = {}
    _pfailed = _pdoc.get("failed", [])
    _ndrop = 0
    _nremint = 0
    for _pf, _pt in _pfailed:
        for _i in list(links):
            _ix, _iy, _iz = pos(ways[_i])
            if abs(_ix - _pf[0]) > 24 or abs(_iy - _pf[1]) > 24 \
                    or abs(_iz - _pf[2]) > 24:
                continue
            for _j in list(links[_i]):
                if links[_i][_j][1]:
                    continue              # already jump-typed
                _jx, _jy, _jz = pos(ways[_j])
                if abs(_jx - _pt[0]) > 24 or abs(_jy - _pt[1]) > 24 \
                        or abs(_jz - _pt[2]) > 24:
                    continue
                # measure the centre-line void: consecutive samples
                # with no survivable floor from the walker's height
                _h = ((_jx - _ix) ** 2 + (_jy - _iy) ** 2) ** 0.5
                _steps = int(_h // 16) + 1
                _void = 0
                _maxvoid = 0
                for _s in range(1, _steps + 1):
                    _f = _s / _steps
                    _cx = _ix + (_jx - _ix) * _f
                    _cy = _iy + (_jy - _iy) * _f
                    _ok = False
                    for _fz in column_floors(_cx, _cy):
                        if _iz - 24 - _fz <= DROPMAX:
                            _ok = True
                            break
                    if _ok:
                        _void = 0
                    else:
                        _void += 1
                        _maxvoid = max(_maxvoid, _void)
                # jump range at speed: the shipped dm4 link clears
                # a 192u lava gap, so the remint window matches
                # that proven envelope, not a single stride
                if 0 < _maxvoid * 16 <= 200 and _h <= 280:
                    _d = links[_i][_j][0]
                    links[_i][_j] = (_d, 1)
                    _nremint += 1
                    print(f"engine verdict: {_i}->{_j} reminted as "
                          f"JUMP (void {_maxvoid * 16}u on the line)")
                else:
                    del links[_i][_j]
                    _ndrop += 1
                    print(f"engine verdict: {_i}->{_j} dropped "
                          f"(void {_maxvoid * 16}u - not one jump)")
    print(f"engine-verdict pass: {_nremint} reminted as jump, "
          f"{_ndrop} dropped ({len(_pfailed)} failed pair(s) on file)")

# ---- 7g3. route-poison prune ----
# A node that STILL cannot reach the mainland after knitting is route
# poison: every route starting there fails, and four failures with no
# enemy in sight is the trapped suicide - Carmack died at
# '-784 280 -16' seconds into the first human session on the knitted
# dm3 graph, spawn-adjacent to an unhealable pocket. Strip those
# nodes' links so the isolated-waypoint prune removes them: a bot
# physically standing there routes from the nearest SURVIVING node
# and simply walks the gap, which beats dying.
_fwd = collections.defaultdict(set)
for _i in links:
    for _j in links[_i]:
        _fwd[_i].add(_j)
for _a, _b in teles + rjlinks + lifts + swims + trains:
    _fwd[_a].add(_b)
_sccs = _knit_sccs(_fwd, len(ways))
_main = max(_sccs, key=len) if _sccs else set()
_rev = collections.defaultdict(set)
for _i in _fwd:
    for _j in _fwd[_i]:
        _rev[_j].add(_i)
_canreach = set(_main)
_q = list(_main)
while _q:
    _u = _q.pop()
    for _v in _rev[_u]:
        if _v not in _canreach:
            _canreach.add(_v)
            _q.append(_v)
_pset = set(range(len(ways))) - _canreach
if _pset:
    print(f"route-poison prune: {len(_pset)} stranded nodes stripped "
          f"{sorted(_pset)}")
    for _i in list(links):
        if _i in _pset:
            del links[_i]
            continue
        for _j in list(links[_i]):
            if _j in _pset:
                del links[_i][_j]
    teles[:] = [(a, b) for a, b in teles
                if a not in _pset and b not in _pset]
    rjlinks[:] = [(a, b) for a, b in rjlinks
                  if a not in _pset and b not in _pset]
    lifts[:] = [(a, b) for a, b in lifts
                if a not in _pset and b not in _pset]
    swims[:] = [(a, b) for a, b in swims
                if a not in _pset and b not in _pset]
    trains[:] = [(a, b) for a, b in trains
                 if a not in _pset and b not in _pset]
    sprints[:] = [(a, b) for a, b in sprints
                  if a not in _pset and b not in _pset]

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
for a, b in sprints:
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
    sprints = [(remap[a], remap[b]) for a, b in sprints]
    doorlinks = [(remap[a], remap[b]) for a, b in doorlinks
                 if a in remap and b in remap]

# ---- 7h. directed-reach gate ----
# The v369 dm2 ship stranded bots on the central floor: the graph
# LOOKED healthy (one big weak island, typed links all present) but
# the hall was a directed sink and every route from it failed - the
# storm shipped because nobody computed directed reach. Never again:
# BFS over every forward edge from the node nearest each deathmatch
# spawn and shout when any spawn's reach is poor. This is a REPORT
# gate, not an auto-fix - a bad number means the graph needs its own
# session, not a silent band-aid.
_fwd = collections.defaultdict(list)
for _i in links:
    for _j in links[_i]:
        _fwd[_i].append(_j)
for _a, _b in teles + rjlinks + lifts + swims + trains + sprints:
    _fwd[_a].append(_b)
_spawn_reach = []
for b in ent_blocks:
    e = kv(b)
    if e.get("classname") not in ("info_player_deathmatch", "info_player_start"):
        continue
    o = [float(v) for v in e.get("origin", "0 0 0").split()]
    _best, _bd = None, 1e9
    for _i, _w in enumerate(ways):
        _wx, _wy, _wz = pos(_w)
        _d = ((_wx-o[0])**2 + (_wy-o[1])**2 + (_wz-o[2])**2) ** 0.5
        if _d < _bd:
            _best, _bd = _i, _d
    if _best is None:
        continue
    _seen = {_best}
    _q = [_best]
    while _q:
        _u = _q.pop()
        for _v in _fwd.get(_u, ()):
            if _v not in _seen:
                _seen.add(_v)
                _q.append(_v)
    _spawn_reach.append((len(_seen), _best, o))
if _spawn_reach:
    _spawn_reach.sort()
    _worst, _wnode, _wspawn = _spawn_reach[0]
    _pct = 100 * _worst // max(1, len(ways))
    print(f"directed reach: worst spawn {_pct}% "
          f"({_worst}/{len(ways)} from n{_wnode} near "
          f"{_wspawn[0]:.0f} {_wspawn[1]:.0f} {_wspawn[2]:.0f})")
    if _pct < 60:
        print("directed reach: WARNING - routes from that spawn will "
              "fail most goals; bots there take the trapped exit. Do "
              "NOT ship this graph without a look.")

# ---- 8a05. region classes (dm3 musing S4) ----
# After the poison prune every surviving node can REACH the mainland;
# what remains split is entry: pockets the mainland cannot route
# into. Bake that as a per-node region - mainland 0, each stranded
# pocket its own id - so the runtime can refuse to shop a goal its
# region provably cannot reach BEFORE any router call. The
# match-start poison menus (four instant routefails, the trapped
# probation) become impossible instead of merely survivable.
_fwd = collections.defaultdict(set)
for _i in links:
    for _j in links[_i]:
        _fwd[_i].add(_j)
for _a, _b in teles + rjlinks + lifts + swims + trains:
    _fwd[_a].add(_b)
_sccs = _knit_sccs(_fwd, len(ways))
_main = max(_sccs, key=len) if _sccs else set()
_F = set(_main)
_q = list(_main)
while _q:
    _u = _q.pop()
    for _v in _fwd[_u]:
        if _v not in _F:
            _F.add(_v)
            _q.append(_v)
regions = [0] * len(ways)
_rid = 0
_und = collections.defaultdict(set)
for _i in _fwd:
    for _j in _fwd[_i]:
        _und[_i].add(_j)
        _und[_j].add(_i)
for _i in range(len(ways)):
    if _i in _F or regions[_i]:
        continue
    _rid += 1
    _q = [_i]
    regions[_i] = _rid
    while _q:
        _u = _q.pop()
        for _v in _und[_u]:
            if _v not in _F and not regions[_v]:
                regions[_v] = _rid
                _q.append(_v)
print(f"regions: mainland {len(_F)} nodes, "
      f"{_rid} stranded pocket(s) covering "
      f"{len(ways) - len(_F)} nodes")

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
    for a, b in sprints:
        f.write(f"    Argus_NavLinkSprint (n{a}, n{b});\n")
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
    for i, r in enumerate(regions):
        if r:
            f.write(f"    Argus_NavRegion (n{i}, {r});\n")
    if cam_nodes:
        f.write("\n    // Camera vantage nodes (Cartographer spectator anchors)\n")
        for cpos, cang, ctag in cam_nodes:
            f.write(f"    Argus_AddCamNode ('{cpos[0]:.0f} {cpos[1]:.0f} {cpos[2]:.0f}', '{cang[0]:.0f} {cang[1]:.0f} {cang[2]:.0f}', \"{ctag}\");\n")
    f.write(f'    dprint ("ARGNAV {len(ways)} nodes, '
            f'{nlinks + len(teles) + len(rjlinks) + len(lifts) + len(swims) + len(trains) + len(sprints)} links\\n");\n')
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
               "sprintlinks": sprints,
               "rjlinks": rjlinks,
               "liftlinks": lifts,
               "swimlinks": swims,
               "trainlinks": trains,
               "doorlinks": doorlinks,
               "regions": regions,
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
