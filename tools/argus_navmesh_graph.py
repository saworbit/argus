"""Waypoint graph derived from the exact hull-1 navmesh.

EXPERIMENTAL (2026-11-13). navgen decimates a sampled fine graph; this
seats waypoints on the exact mesh from argus_navmesh and accepts a
walk link only when a body following its straight line stays on the
mesh, with real floor under its centre and no lava or slime at its
feet. Typed links (jump, rocket, sprint, teleporter, lift, swim,
train) are inherited from the shipped graph WITH THEIR EXACT ENDPOINT
SEATS, so every arc navgen verified survives unchanged and the
experiment isolates one variable: how the walk graph is built.

--native-typed (#790) inherits nothing: argus_navmesh_typed finds jumps,
climbs and drop arcs from the air layer's flights, lift pads from
func_plat and teleporters from the entity lump, and no shipped graph is
needed (one is read, when present, for its camera nodes and the
comparison figures only).

    python tools/argus_navmesh_graph.py dm4 OUTDIR [--radius 112]
        [--min-clear 20] [--prune 1.02] [--max-seats N] [--native-typed]

Writes OUTDIR/argus_nav_<map>.qc and its .json sidecar. Run navgen's
--reanalyze-tactics on the pair afterwards to fill exposure and cover.
BSPs use the shared lookup (ARGUS_MAPS first), so a worktree can borrow
the main checkout's machine-local maps.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_navmesh as nm  # noqa: E402
import argus_navmesh_typed as nt  # noqa: E402
from argus_nav_artifacts import canonical_sidecar, validate_pair  # noqa: E402
from argus_nav_budget import assess_edict_budget, survives_spawn  # noqa: E402
from argus_navjson import edges as nav_edges, normalize_nav  # noqa: E402
from argus_paths import bsp_path as find_bsp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STEP, DROPMAX = nm.STEP, nm.DROPMAX
LINK_MAX = 340.0       # navgen's LINK_PATH_MAX, the longest legal hop
MAX_LINKS = 8          # runtime link slots per node
SAMPLE = 6.0           # walker spacing along a link
NICK = 12.0            # longest off-mesh run a link may clip outright
SLIDE = (0.0, 8.0, -8.0, 16.0, -16.0)   # sideways give per step
CONTROL = ("weapon_", "item_armor", "item_artifact")
TYPED = ("jlinks", "sprintlinks", "rjlinks", "liftlinks", "swimlinks",
         "trainlinks")
HOSTILE = (nm.CONTENTS_LAVA, nm.CONTENTS_SLIME)


class MeshIndex:
    def __init__(self, frags, cell=64.0):
        self.frags, self.cell = frags, cell
        self.grid = collections.defaultdict(list)
        for i, f in enumerate(frags):
            xs = [p[0] for p in f["poly"]]
            ys = [p[1] for p in f["poly"]]
            for gx in range(math.floor(min(xs) / cell),
                            math.floor(max(xs) / cell) + 1):
                for gy in range(math.floor(min(ys) / cell),
                                math.floor(max(ys) / cell) + 1):
                    self.grid[(gx, gy)].append(i)

    def floors(self, x, y):
        out = []
        key = (math.floor(x / self.cell), math.floor(y / self.cell))
        for i in self.grid.get(key, ()):
            f = self.frags[i]
            if nm.point_in_poly_xy(x, y, f["poly"]):
                out.append(nm.plane_z(f["plane"], x, y))
        return out

    def locate(self, x, y, z, tol=3.0):
        """The fragment whose floor is nearest z under (x, y), within tol."""
        best, bd = None, tol
        key = (math.floor(x / self.cell), math.floor(y / self.cell))
        for i in self.grid.get(key, ()):
            f = self.frags[i]
            if nm.point_in_poly_xy(x, y, f["poly"]):
                d = abs(nm.plane_z(f["plane"], x, y) - z)
                if d <= bd:
                    best, bd = i, d
        return best


def real_floor(bsp, x, y, oz):
    """Is there world floor within a step under this origin's feet?"""
    return (bsp.h0(x, y, oz - 25.0) == nm.CONTENTS_SOLID
            or bsp.h0(x, y, oz - 25.0 - STEP) == nm.CONTENTS_SOLID)


def hostile_feet(bsp, x, y, oz):
    return bsp.h0(x, y, oz - 23.0) in HOSTILE


def clearance(bsp, mi, x, y, z, reach=96.0):
    """Shortest of eight rays to a wall or a real ledge."""
    best = reach
    for k in range(8):
        a = k * math.pi / 4
        dx, dy = math.cos(a), math.sin(a)
        cz, t = z, 0.0
        while t < best:
            t += 4.0
            px, py = x + dx * t, y + dy * t
            fl = [f for f in mi.floors(px, py) if abs(f - cz) <= STEP]
            if not fl or not real_floor(bsp, px, py, min(fl, key=lambda f: abs(f - cz))):
                best = min(best, t - 4.0)
                break
            cz = min(fl, key=lambda f: abs(f - cz))
    return best


def teleport_boxes(bsp):
    out = []
    for e in bsp.entities():
        if e.get("classname") != "trigger_teleport":
            continue
        m = e.get("model", "")
        if not m.startswith("*"):
            continue
        mdl = bsp.models[int(m[1:])]
        mn, mx = mdl[0:3], mdl[3:6]
        out.append(((mn[0] - 16, mn[1] - 16, mn[2] - 32),
                    (mx[0] + 16, mx[1] + 16, mx[2] + 24)))
    return out


def in_box(p, box):
    mn, mx = box
    return all(mn[i] < p[i] < mx[i] for i in range(3))


def walk(bsp, mi, a, b, tboxes, end_in_tele=False, end_box=None):
    """Follow a->b on the mesh. Returns 'walk', 'drop' or None.

    end_box is the trigger the target seat stands in. A body teleports
    the moment it touches that trigger, so a link may cross it at any
    depth (the native finder seats a teleporter source at the middle of
    its trigger, which on dm3 is more than 48u from every edge).
    """
    ax, ay, az = a
    bx, by, bz = b
    d = math.hypot(bx - ax, by - ay)
    n = max(1, math.ceil(d / SAMPLE))
    z = az
    miss = 0.0
    dropped = False
    # ESCAPE MODE: a seat already in shallow lava or slime (dm4's pit
    # floor, 15u deep) is where a knocked-in bot stands. Walks out of
    # it may cross the liquid, or it cannot reach the rocket-jump pad
    # navgen's 7g escape gave it. Walks from dry ground never may.
    escape = hostile_feet(bsp, ax, ay, az)
    px, py = (-(by - ay) / d, (bx - ax) / d) if d > 0 else (0.0, 0.0)
    for i in range(1, n + 1):
        f = i / n
        cx, cy = ax + (bx - ax) * f, ay + (by - ay) * f
        # walkmove slides along a wall it meets, so a line that clips
        # a corner is walkable while floor continues just beside it:
        # try the centre, then up to half a body width either side
        ok = False
        for off in SLIDE:
            x, y = cx + px * off, cy + py * off
            fl = mi.floors(x, y)
            step = [h for h in fl if abs(h - z) <= STEP]
            nz, fell = None, False
            if step:
                nz = min(step, key=lambda h: abs(h - z))
            else:
                below = [h for h in fl if h < z - STEP]
                if below and z - max(below) <= DROPMAX:
                    nz, fell = max(below), True
            if nz is None:
                continue
            if hostile_feet(bsp, x, y, nz) and not escape:
                if off == 0:
                    return None
                continue
            if real_floor(bsp, x, y, nz):
                ok = True
                dropped = dropped or fell
                break
        if not ok:
            miss += d / n
            if miss > NICK:
                return None
            continue
        miss = 0.0
        z = nz
        if tboxes and not (end_in_tele and d * (1 - f) < 48):
            if any(in_box((x, y, z), bx_) for bx_ in tboxes if bx_ is not end_box):
                return None
    if abs(z - bz) > STEP:
        return None
    return "drop" if dropped else "walk"


def los(bsp, a, b):
    """Torso-height sight through hull 0 (point traces, stepped)."""
    ax, ay, az = a[0], a[1], a[2] + 22
    bx, by, bz = b[0], b[1], b[2] + 22
    d = math.dist((ax, ay, az), (bx, by, bz))
    n = max(1, int(d // 8))
    for i in range(1, n):
        f = i / n
        if bsp.h0(ax + (bx - ax) * f, ay + (by - ay) * f,
                  az + (bz - az) * f) == nm.CONTENTS_SOLID:
            return False
    return True


def sccs(fwd, n):
    order, seen = [], [False] * n
    for s in range(n):
        if seen[s]:
            continue
        stack = [(s, iter(fwd[s]))]
        seen[s] = True
        while stack:
            u, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                order.append(u)
            elif not seen[nxt]:
                seen[nxt] = True
                stack.append((nxt, iter(fwd[nxt])))
    rev = collections.defaultdict(list)
    for u in range(n):
        for v in fwd[u]:
            rev[v].append(u)
    comp = [-1] * n
    out = []
    for s in reversed(order):
        if comp[s] >= 0:
            continue
        group, stack = [], [s]
        comp[s] = len(out)
        while stack:
            u = stack.pop()
            group.append(u)
            for v in rev[u]:
                if comp[v] < 0:
                    comp[v] = len(out)
                    stack.append(v)
        out.append(group)
    return out


def build(mapname, radius=112.0, min_clear=20.0, prune=1.02, max_seats=None,
          gap_max=200.0, native=False, bsp_path=None, ship_path=None):
    bsp_path = Path(bsp_path) if bsp_path else find_bsp(ROOT, mapname)
    if bsp_path is None:
        raise FileNotFoundError(f"missing {mapname}.bsp (set ARGUS_MAPS or --bsp)")
    bsp, frags, stats = nm.load_mesh(bsp_path)
    mi = MeshIndex(frags)
    tboxes = teleport_boxes(bsp)
    ship_path = Path(ship_path) if ship_path else ROOT / "src" / f"argus_nav_{mapname}.qc.json"
    if native and not ship_path.exists():
        ship = {}
    else:
        ship = json.loads(ship_path.read_text())
    snodes = [tuple(p) for p in ship.get("nodes", [])]

    # 2. candidate seats on the mesh
    cands = []
    cand_frag = {}
    for fi, f in enumerate(frags):
        poly = f["poly"]
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        pts = [nm.centroid(poly)[:2]]
        x = math.floor(min(xs) / 16) * 16 + 8
        while x < max(xs):
            y = math.floor(min(ys) / 16) * 16 + 8
            while y < max(ys):
                if nm.point_in_poly_xy(x, y, poly):
                    pts.append((x, y))
                y += 16
            x += 16
        for x, y in pts:
            z = nm.plane_z(f["plane"], x, y)
            if hostile_feet(bsp, x, y, z) or not real_floor(bsp, x, y, z):
                continue
            if not bsp.check_bottom(x, y, z):
                continue
            if any(in_box((x, y, z), b) for b in tboxes):
                continue
            cands.append((x, y, z))
            cand_frag.setdefault((x, y, z), fi)
    clear = {c: clearance(bsp, mi, *c) for c in cands}

    # 2b. native typed infrastructure (#790): what the map's own
    # entities and ledges ask for, found before any seat is placed
    ctx = native_seats = None
    if native:
        ctx = nt.Context(
            bsp=bsp, world=nm.WithBrushes(bsp, nm.brush_boxes(bsp)), frags=frags,
            floors=mi.floors, locate=mi.locate,
            walk=lambda a, b: walk(bsp, mi, a, b, tboxes),
            gravity=nm.map_gravity(bsp_path), tboxes=tboxes)
        native_seats = native_infrastructure(ctx, cands, cand_frag)

    def clear_at(p):
        return clear.get(tuple(p), 0.0)

    def place(radius):
        seats, kinds, origin = [], [], {}

        def add_seat(p, kind, src=None):
            seats.append(tuple(p))
            kinds.append(kind)
            if src is not None:
                origin[src] = len(seats) - 1
            return len(seats) - 1

        native_pairs = []
        if native:
            # 1n. native seats: teleporter and lift pads, then the seats
            # the arc sites asked for, each placed once
            at = {}

            def seat_at(p):
                if p not in at:
                    at[p] = add_seat(p, "typed")
                return at[p]
            for fam, a, b in native_seats["pairs"]:
                native_pairs.append((fam, seat_at(a), seat_at(b)))
            for p in native_seats["seats"]:
                seat_at(p)
        else:
            # 1. inherited seats: every endpoint of a typed or teleporter hop
            inherit = set()
            for fam in TYPED + ("teles",):
                for row in ship.get(fam, []):
                    inherit.update(row[:2])
            for s in sorted(inherit):
                add_seat(snodes[s], "inherit", s)

        def covered(c, r):
            for s in seats:
                if (math.hypot(s[0] - c[0], s[1] - c[1]) < r
                        and abs(s[2] - c[2]) <= 36 and los(bsp, s, c)):
                    return True
            return False

        # 3. control items get a seat of their own, as navgen's 5a3 does
        for e in bsp.entities():
            cls = e.get("classname", "")
            mega = cls == "item_health" and int(e.get("spawnflags", "0")) & 2
            if not (cls.startswith(CONTROL) or mega) or "origin" not in e:
                continue
            if int(e.get("spawnflags", "0")) & 2048:
                continue
            ix, iy, iz = map(float, e["origin"].split())
            near = [c for c in cands if math.hypot(c[0] - ix, c[1] - iy) <= 48
                    and -8 <= c[2] - iz <= 48]
            if not near or covered((ix, iy, iz + 24), 48):
                continue
            best = max(near, key=lambda c: min(clear[c], 48)
                       - 0.5 * math.hypot(c[0] - ix, c[1] - iy))
            add_seat(best, "item")

        # 4. coverage, roomiest first: seats stand in the middle of a
        # space, and a corridor only spends one where nothing covers it
        order = sorted(cands, key=lambda c: (-min(clear[c], 64.0), c))
        for c in order:
            if clear[c] < min_clear:
                continue
            if not covered(c, radius):
                add_seat(c, "cover")
        for c in sorted(cands, key=lambda c: (-clear[c], c)):
            if not covered(c, radius * 0.75):
                add_seat(c, "narrow")

        return seats, kinds, origin, native_pairs

    seats, kinds, origin, native_pairs = place(radius)

    # 5. walk links, verified on the mesh
    n = len(seats)
    # a seat INSIDE a trigger box sends whoever arrives away, so it has
    # no walks out; navgen also seats teleporter sources beside the
    # trigger, and two dm4 destinations double as sources, which a
    # list-based rule turned into dead ends (spawn reach 29 per cent)
    tele_src = {i for i in range(n) if any(in_box(seats[i], b) for b in tboxes)}
    tele_box = {}
    if native:
        tele_box = {i: next(b for b in tboxes if in_box(seats[i], b)) for i in tele_src}
    # typed maps a pair to its family and, for a jump, its approach
    # (speed, landing runway, arc margin); both modes fill it
    typed = {}
    if native:
        for fam, i, j in native_pairs:
            if i != j:
                typed[(i, j)] = (fam, None)
    else:
        for fam in TYPED + ("teles",):
            for row in ship.get(fam, []):
                if row[0] in origin and row[1] in origin:
                    typed.setdefault((origin[row[0]], origin[row[1]]), (fam, None))
    typed_pairs = set(typed)
    ok = {}
    for i in range(n):
        for j in range(n):
            if i == j or (i, j) in typed_pairs:
                continue
            a, b = seats[i], seats[j]
            if math.hypot(b[0] - a[0], b[1] - a[1]) > LINK_MAX:
                continue
            if i in tele_src:
                continue    # arriving in a teleporter sends you away
            r = walk(bsp, mi, a, b, tboxes, end_in_tele=j in tele_src,
                     end_box=tele_box.get(j))
            if r:
                ok[(i, j)] = r

    # 5n. native jumps, climbs and drop arcs between the seats, and the
    # straight-fall drops whose run-off lands in lava or slime refused
    native_stats = collections.Counter()
    if native:
        for (i, j), r in list(ok.items()):
            if r == "drop" and nt.drop_lands_lethal(ctx, seats[i], seats[j]):
                del ok[(i, j)]
                native_stats["drops_refused_lethal_runoff"] += 1
            elif r == "drop" and nt.drop_lands_lethal(ctx, seats[i], seats[j], nt.RUN):
                native_stats["drops_lethal_at_run_only"] += 1
        jumps, arcs, found = nt.find_links(ctx, seats, ok, native_seats["ledges"],
                                           skip=frozenset(tele_src))
        native_stats.update(found)
        # a teleporter costs a nominal 64u in the length test and a lift
        # its ride, so a jump that only duplicates either is refused
        extra = {pair: 64.0 if kind[0] == "teles" else math.dist(seats[pair[0]], seats[pair[1]])
                 for pair, kind in typed.items()}
        jumps, arcs = nt.keep_useful(seats, ok, jumps, arcs, extra)
        for (i, j), prof in jumps.items():
            typed[(i, j)] = ("jlinks", (prof["speed"], prof["runway"], prof["margin"]))
            native_stats["climbs_kept" if prof.get("climb") else "jumps_kept"] += 1
        for pair in arcs:
            ok[pair] = "arc"
        native_stats["drop_arcs_kept"] = len(arcs)
        typed_pairs = set(typed)

    def L(i, j):
        return math.dist(seats[i], seats[j])

    removed = 0
    if max_seats and n > max_seats:
        # TOPOLOGY-PRESERVING DECIMATION. Growing the radius until the
        # graph fits (navgen's answer) left dm3 with 132 of 241 seats on
        # the mainland: sparse seats cannot see each other round corners,
        # and the straight-line walker is right to refuse what they
        # cannot see. So build dense and take seats away instead, the
        # most crowded first, and only when every route through a seat
        # survives without it: each in-neighbour must still reach each
        # out-neighbour within three hops, and the seat must stay within
        # gap_max of a remaining seat it can see. Chokepoint and corner
        # seats are exactly the ones that cannot pass, so they stay.
        alive = set(range(n))
        fadj = collections.defaultdict(set)
        radj = collections.defaultdict(set)
        for (i, j) in list(ok) + list(typed_pairs):
            fadj[i].add(j)
            radj[j].add(i)
        fixed = {i for i in range(n) if kinds[i] in ("inherit", "item")}
        if native:
            # native typed seats are fixed only when a link stands on them
            fixed |= {i for pair in typed_pairs for i in pair}
            fixed |= {i for pair, r in ok.items() if r == "arc" for i in pair}

        def crowd(v):
            return sum(1 for u in alive if u != v and L(u, v) < 160)

        def reaches(u, w, skip):
            frontier, seen = {u}, {u}
            for _ in range(3):
                nxt = set()
                for x in frontier:
                    for y in fadj[x]:
                        if y == w:
                            return True
                        if y != skip and y in alive and y not in seen:
                            seen.add(y)
                            nxt.add(y)
                frontier = nxt
            return False

        # COVERAGE FIRST (#790). Crowding alone took dm3 at 249 seats to
        # 77 per cent of the mesh covered against the shipped graph's 89,
        # because it cannot tell a crowded seat that covers floor nobody
        # else sees from one that is redundant. So a seat's cost is the
        # candidate points only it covers, and the cheapest go first;
        # crowding breaks ties. A seat whose cost rose since the pass was
        # sorted waits for the next pass.
        covers = cover_lists(bsp, cands, seats)
        count = collections.Counter(c for cs in covers for c in cs)

        def unique(v):
            return sum(1 for c in covers[v] if count[c] == 1)

        changed = True
        while changed and len(alive) > max_seats:
            changed = False
            cost = {v: unique(v) for v in alive if v not in fixed}
            order = sorted(cost, key=lambda v: (cost[v], -crowd(v), clear_at(seats[v]), v))
            for v in order:
                if len(alive) <= max_seats:
                    break
                if unique(v) > cost[v]:
                    continue
                ins = [u for u in radj[v] if u in alive and u != v]
                outs = [w for w in fadj[v] if w in alive and w != v]
                if not all(reaches(u, w, v) for u in ins for w in outs if u != w):
                    continue
                if not any(L(u, v) <= gap_max and abs(seats[u][2] - seats[v][2]) <= 36
                           and los(bsp, seats[u], seats[v])
                           for u in alive if u != v):
                    continue
                alive.discard(v)
                for c in covers[v]:
                    count[c] -= 1
                removed += 1
                changed = True
        keep = sorted(alive)
        remap = {old: new for new, old in enumerate(keep)}
        seats = [seats[i] for i in keep]
        kinds = [kinds[i] for i in keep]
        origin = {s_: remap[i] for s_, i in origin.items() if i in remap}
        ok = {(remap[i], remap[j]): r for (i, j), r in ok.items()
              if i in remap and j in remap}
        typed_pairs = {(remap[i], remap[j]) for (i, j) in typed_pairs
                       if i in remap and j in remap}
        typed = {(remap[i], remap[j]): v for (i, j), v in typed.items()
                 if i in remap and j in remap}
        n = len(seats)

    out_adj = collections.defaultdict(set)
    for (i, j) in ok:
        out_adj[i].add(j)
    kept = {}
    for (i, j), r in ok.items():
        lij = L(i, j)
        red = False
        for k in out_adj[i]:
            if k != j and (k, j) in ok and L(i, k) < lij and L(k, j) < lij:
                if L(i, k) + L(k, j) <= prune * lij:
                    red = True
                    break
        if not red:
            kept[(i, j)] = r

    # 6. eight slots per node: typed hops first, then the shortest
    # walks, evicting long ones another kept link already serves
    outs = collections.defaultdict(list)
    for (i, j) in typed_pairs:
        outs[i].append(j)
    plain = collections.defaultdict(list)
    for (i, j) in kept:
        plain[i].append(j)
    evicted = 0
    final_plain = set()
    for i in range(n):
        room = MAX_LINKS - len(outs[i])
        chosen = sorted(plain[i], key=lambda j: L(i, j))
        # The router counts hops, so a long link is worth more than its
        # length suggests. Evict the longest link a two-hop detour
        # through the node's own remaining links already serves; only
        # when none is redundant does plain length decide.
        while len(chosen) > max(0, room):
            victim = None
            for j in sorted(chosen, key=lambda j: -L(i, j)):
                if any(k != j and (k, j) in kept and L(i, k) + L(k, j) <= 1.25 * L(i, j)
                       for k in chosen):
                    victim = j
                    break
            if victim is None:
                victim = max(chosen, key=lambda j: L(i, j))
            chosen.remove(victim)
            evicted += 1
        for j in chosen:
            final_plain.add((i, j))

    # 7. regions, navgen 8a05 semantics
    fwd = collections.defaultdict(set)
    for (i, j) in final_plain | typed_pairs:
        fwd[i].add(j)
    groups = sccs(fwd, n)
    main = set(max(groups, key=len))
    reach = set(main)
    q = list(main)
    while q:
        u = q.pop()
        for v in fwd[u]:
            if v not in reach:
                reach.add(v)
                q.append(v)
    und = collections.defaultdict(set)
    for u in fwd:
        for v in fwd[u]:
            und[u].add(v)
            und[v].add(u)
    regions, rid = [0] * n, 0
    for s in range(n):
        if s in reach or regions[s]:
            continue
        rid += 1
        regions[s] = rid
        q = [s]
        while q:
            u = q.pop()
            for v in und[u]:
                if v not in reach and not regions[v]:
                    regions[v] = rid
                    q.append(v)

    families = (native_families(typed) if native
                else inherited_families(ship, origin))
    report = {
        "fragments": len(frags), "candidates": len(cands), "seats": n,
        "radius": round(radius, 1), "decimated": removed,
        "seat_kinds": dict(collections.Counter(kinds)),
        "verified_pairs": len(ok), "after_prune": len(kept),
        "evicted_by_slots": evicted, "plain_links": len(final_plain),
        "drops": sum(1 for p in final_plain if kept.get(p) == "drop"),
        "typed_links": len(typed_pairs), "mainland": len(main),
        "reach_from_mainland": len(reach), "stranded_regions": rid,
        "teleport_boxes": len(tboxes), **stats,
    }
    if native:
        report.update({
            "typed_source": "native",
            "gravity": ctx.gravity,
            "drop_arcs": sum(1 for p in final_plain if kept.get(p) == "arc"),
            "climbs": sum(1 for p in families["jlinks"]
                          if seats[p[1]][2] - seats[p[0]][2] > STEP),
            "finder": dict(sorted(native_stats.items())),
            "arc_sites": native_seats["sites"],
            "refused_teleporters": native_seats["refused_teleporters"],
            "refused_lifts": native_seats["refused_lifts"],
        })
    return {
        "map": mapname, "seats": seats, "kinds": kinds, "origin": origin,
        "plain": final_plain, "kept": kept, "typed": typed_pairs,
        "families": families, "regions": regions, "ship": ship, "report": report,
        "bsp": bsp, "cands": cands, "native": native,
    }


def inherited_families(ship, origin):
    """The shipped graph's typed families in this graph's seat numbers."""
    jl = {(origin[r[0]], origin[r[1]]) for r in ship.get("jlinks", [])
          if r[0] in origin and r[1] in origin}
    appr = {(origin[r[0]], origin[r[1]]): r[2:] for r in ship.get("jumpapproach", [])
            if r[0] in origin and r[1] in origin}

    def remap(fam):
        return [[origin[r[0]], origin[r[1]]] for r in ship.get(fam, [])
                if r[0] in origin and r[1] in origin]
    out = {"jlinks": jl, "jumpapproach": appr}
    for fam in ("sprintlinks", "teles", "rjlinks", "liftlinks", "swimlinks", "trainlinks"):
        out[fam] = remap(fam)
    return out


def native_families(typed):
    """The finder's typed pairs, grouped as the emitter writes them."""
    jl = {p for p, (fam, _) in typed.items() if fam == "jlinks"}
    out = {"jlinks": jl,
           "jumpapproach": {p: list(typed[p][1]) for p in jl}}
    for fam in ("sprintlinks", "teles", "rjlinks", "liftlinks", "swimlinks", "trainlinks"):
        out[fam] = [list(p) for p in sorted(p for p, (f, _) in typed.items() if f == fam)]
    return out


def native_infrastructure(ctx, cands, cand_frag):
    """Seats the native finder needs before coverage seating.

    Teleporter and lift pads come in pairs; arc sites (jumps and drops
    off ledges that save a long walk) each ask for a seat behind the
    launch and one past the landing, chosen from the mesh candidates.
    """
    out = {"pairs": [], "seats": [], "sites": {}, "refused_teleporters": [],
           "refused_lifts": []}
    tele, refused = nt.teleporters(ctx)
    for src, dst, _ in tele:
        out["pairs"].append(("teles", src, dst))
    out["refused_teleporters"] = [[t, s and list(s), d and list(d)] for t, s, d in refused]
    lifts, refused = nt.lift_pads(ctx, cands)
    for lo, hi, _ in lifts:
        out["pairs"].append(("liftlinks", lo, hi))
    out["refused_lifts"] = [[list(c), lo and list(lo), hi and list(hi)] for c, lo, hi in refused]
    ledges = nm.ledge_points(ctx.world, ctx.frags)
    out["ledges"] = ledges
    sites = nt.cluster(nt.arc_sites(ctx, nt.fragment_graph(ctx), ledges))
    out["sites"] = dict(collections.Counter(s["kind"] for s in sites))
    grid = collections.defaultdict(list)
    for c in cands:
        grid[(math.floor(c[0] / 32), math.floor(c[1] / 32))].append(c)

    def pick(target, frag, reach):
        best, bd = None, None
        x, y, z = target
        for gx in range(math.floor((x - reach) / 32), math.floor((x + reach) / 32) + 1):
            for gy in range(math.floor((y - reach) / 32), math.floor((y + reach) / 32) + 1):
                for c in grid.get((gx, gy), ()):
                    if abs(c[2] - z) > STEP:
                        continue
                    d = math.hypot(c[0] - x, c[1] - y)
                    if d > reach:
                        continue
                    key = (cand_frag.get(c) != frag, d)
                    if bd is None or key < bd:
                        best, bd = c, key
        return best
    placed = []
    for site in sites:
        src_t, dst_t = nt.site_targets(site)
        src = pick(src_t, site["fa"], 48.0)
        dst = pick(dst_t, site["fb"], 64.0) or pick(site["land"], site["fb"], 64.0)
        if src is None or dst is None:
            continue
        for p in (src, dst):
            if not any(math.dist(p, q) < 24.0 for q in placed):
                placed.append(p)
    out["seats"] = placed
    return out


def spawn_reach(nav, spawns):
    """argus_reach's worst-spawn figures for a graph held in memory."""
    nav = normalize_nav(nav)
    nodes = nav["nodes"]
    n = len(nodes)
    if not n or not spawns:
        return None
    fwd = {}
    for gated in (True, False):
        fwd[gated] = [[] for _ in range(n)]
        for a, b in nav_edges(nav, gated=gated):
            fwd[gated][a].append(b)

    def reach_from(start, adj):
        seen, q = {start}, [start]
        while q:
            u = q.pop()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen
    rows, far = [], 0.0
    for o in spawns:
        best = min(range(n), key=lambda i: sum((nodes[i][k] - o[k]) ** 2 for k in range(3)))
        far = max(far, math.dist(nodes[best], o))
        every, ungated = reach_from(best, fwd[True]), reach_from(best, fwd[False])
        rows.append((len(every), len(ungated), sorted(every)))
    rows.sort()
    r_all, r_un, reached = rows[0]
    return {"nodes": n, "spawns": len(spawns), "worst_all": r_all,
            "worst_ungated": r_un, "worst_all_pct": 100 * r_all // n,
            "worst_ungated_pct": 100 * r_un // n, "farthest_spawn_u": round(far),
            "reached": reached}


def spawn_points(bsp):
    out = []
    for e in bsp.entities():
        if e.get("classname") in ("info_player_deathmatch", "info_player_start"):
            out.append(tuple(float(v) for v in e.get("origin", "0 0 0").split()))
    return out


def _near_seats(seats, radius):
    grid = collections.defaultdict(list)
    for i, s in enumerate(seats):
        grid[(math.floor(s[0] / radius), math.floor(s[1] / radius))].append(i)

    def near(c):
        gx, gy = math.floor(c[0] / radius), math.floor(c[1] / radius)
        for ix in (gx - 1, gx, gx + 1):
            for iy in (gy - 1, gy, gy + 1):
                yield from grid.get((ix, iy), ())
    return near


def _covers(bsp, s, c, radius, dz):
    """Placement's own test: within radius, a step band of 36u, in sight."""
    return (math.hypot(s[0] - c[0], s[1] - c[1]) < radius and abs(s[2] - c[2]) <= dz
            and los(bsp, s, c))


def cover_lists(bsp, cands, seats, radius=112.0, dz=36.0):
    """Per seat, the indices of the candidate points it covers."""
    near = _near_seats(seats, radius)
    out = [[] for _ in seats]
    for ci, c in enumerate(cands):
        for i in near(c):
            if _covers(bsp, seats[i], c, radius, dz):
                out[i].append(ci)
    return out


def coverage(bsp, cands, seats, radius=112.0, dz=36.0):
    """Share of mesh candidate points a seat covers, by placement's own test."""
    if not cands:
        return 0.0
    seats = [tuple(s) for s in seats]
    near = _near_seats(seats, radius)
    hit = sum(1 for c in cands
              if any(_covers(bsp, seats[i], c, radius, dz) for i in near(c)))
    return hit / len(cands)


def assess(g, doc):
    """Reach, coverage and edicts for the emitted graph and the shipped one.

    Reach percentages count each graph's own nodes, so a graph that seats
    lava (the shipped dm4 keeps its pit-floor escape seats) reads lower
    for it. Reachable coverage does not: it is the share of mesh points
    covered by a seat the worst spawn can reach, the same floor for both.
    """
    bsp, ship = g["bsp"], g["ship"]
    spawns = spawn_points(bsp)
    ents = bsp.entities()
    live = sum(1 for e in ents if survives_spawn(e))

    def figures(nav):
        nodes = normalize_nav(nav)["nodes"]
        reach = spawn_reach(nav, spawns)
        reached = reach.pop("reached") if reach else range(len(nodes))
        budget = assess_edict_budget(len(nodes), live, len(ents))
        return {
            "reach": reach,
            "coverage_pct": round(100 * coverage(bsp, g["cands"], nodes), 1),
            "reachable_coverage_pct": round(
                100 * coverage(bsp, g["cands"], [nodes[i] for i in reached]), 1),
            "edicts": {"status": budget.status, "waypoints": budget.waypoints,
                       "live_entities": live, "total": budget.total,
                       "ceiling": budget.ceiling, "slack": budget.slack},
            "typed_by_family": {f: len(nav.get(f, [])) for f in TYPED + ("teles",)},
        }
    out = figures(doc)
    if ship.get("nodes"):
        out["shipped"] = figures(ship)
    return out


def emit(g, outdir):
    m = g["map"]
    seats, ship = g["seats"], g["ship"]
    banner = "EXPERIMENTAL, native typed links" if g.get("native") else "EXPERIMENTAL"
    lines = [f"/* generated by argus_navmesh_graph.py ({banner}) - do not edit */",
             "", f"void() Argus_Nav_Spawn_{m} =", "{"]
    lines += [f"    local entity n{i};" for i in range(len(seats))]
    lines.append("")
    for i, (x, y, z) in enumerate(seats):
        lines.append(f"    n{i} = Argus_NavNode ('{x:.0f} {y:.0f} {z:.0f}');")
    lines.append("")
    emitted = set()

    def put(verb, a, b, extra="", tail=""):
        if (a, b) in emitted:
            return
        emitted.add((a, b))
        lines.append(f"    {verb} (n{a}, n{b}{extra});{tail}")

    fams = g["families"]
    jl, appr = fams["jlinks"], fams["jumpapproach"]
    walkpairs = sorted(g["plain"] | jl)
    for a, b in walkpairs:
        if (a, b) in jl:
            sp, rw, mg = appr.get((a, b), [280.0, 0.0, 0.0])
            put("Argus_NavLinkJump", a, b, f", {sp:.0f}",
                f"    // approach {sp:.0f}, landing {rw:.0f}, arc {mg:.0f}")
        else:
            put("Argus_NavLink", a, b)

    sprints, teles, rjs = fams["sprintlinks"], fams["teles"], fams["rjlinks"]
    lifts, swims, trains = fams["liftlinks"], fams["swimlinks"], fams["trainlinks"]
    for a, b in sprints:
        put("Argus_NavLinkSprint", a, b)
    for a, b in teles:
        put("Argus_NavLink", a, b, tail="    // teleporter")
    swimset = {tuple(p) for p in swims}
    for a, b in rjs:
        if (a, b) not in swimset:
            put("Argus_NavLinkRocket", a, b)
    for a, b in lifts:
        put("Argus_NavLinkLift", a, b)
    for a, b in swims:
        put("Argus_NavLinkSwim", a, b)
    for a, b in trains:
        put("Argus_NavLinkTrain", a, b)
    for i, r in enumerate(g["regions"]):
        if r:
            lines.append(f"    Argus_NavRegion (n{i}, {r});")
    cams = ship.get("cam_nodes", [])
    if cams:
        lines += ["", "    // Camera vantage nodes (Cartographer spectator anchors)"]
        for c in cams:
            p, a = c["pos"], c["ang"]
            lines.append(f"    Argus_AddCamNode ('{p[0]:.0f} {p[1]:.0f} {p[2]:.0f}', "
                         f"'{a[0]:.0f} {a[1]:.0f} {a[2]:.0f}', \"{c['tag']}\");")
    lines.append(f'    dprint ("ARGNAV {len(seats)} nodes, {len(emitted)} links\\n");')
    lines.append("};")
    text = "\n".join(lines) + "\n"
    doc = {
        "nodes": [list(s) for s in seats],
        "links": [], "jlinks": [list(p) for p in sorted(jl)],
        "jumpapproach": [[a, b, *appr.get((a, b), [280.0, 0.0, 0.0])] for a, b in sorted(jl)],
        "sprintlinks": sprints, "rjlinks": rjs, "liftlinks": lifts,
        "swimlinks": swims, "trainlinks": trains, "doorlinks": [],
        "regions": g["regions"], "teles": teles, "cam_nodes": cams,
        "trace_inputs": [], "mesh_report": g["report"],
    }
    doc = canonical_sidecar(doc, text)
    validate_pair(text, doc, tactics=False)
    if g.get("bsp") is not None:
        g["report"]["assessment"] = assess(g, doc)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    qc = outdir / f"argus_nav_{m}.qc"
    qc.write_bytes(text.encode("ascii"))
    (outdir / f"argus_nav_{m}.qc.json").write_bytes(
        json.dumps(doc).encode("ascii"))
    return qc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("outdir")
    ap.add_argument("--radius", type=float, default=112.0)
    ap.add_argument("--min-clear", type=float, default=20.0)
    ap.add_argument("--prune", type=float, default=1.02)
    ap.add_argument("--max-seats", type=int)
    ap.add_argument("--native-typed", action="store_true",
                    help="inherit no typed link: find jumps, climbs, drop arcs, lifts "
                         "and teleporters from the map itself (#790)")
    ap.add_argument("--bsp", help="the BSP to read (default: shared BSP lookup, ARGUS_MAPS first)")
    a = ap.parse_args(argv)
    g = build(a.map, a.radius, a.min_clear, a.prune, a.max_seats,
              native=a.native_typed, bsp_path=a.bsp)
    qc = emit(g, a.outdir)
    print(json.dumps(g["report"], indent=1))
    print("wrote", qc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
