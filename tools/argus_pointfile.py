#!/usr/bin/env python3
"""Draw Argus nav data into the running game as engine particles.

The engine has carried a debug channel since 1996 and we never used
it. qbsp writes maps/<name>.pts when a map leaks, and the client
command `pointfile` reads that file and spawns one static particle per
line, which is how mappers used to walk a leak to the void. The file
is just "x y z" per line, so anything can write it.

That makes it a free in-world view of the nav graph. Top-down PNGs
cannot show a seat hanging 152 units over lava, or a door seat that
stops 18 units short of the trigger it is waiting on. Standing in the
level looking at the dots does.

Usage:
  argus_pointfile.py <map> [--what nodes|links|swim|water|tape|fails|human|
                                  route|trail|jump|door|lift|train|rocket|
                                  sprint|tele] [--bot NAME]

  --what route draws what the router PLANNED, --what trail draws where
  the bot actually went. Run both for one bot and flip between them:
  intent and reality cannot share a file, because particle colour is
  (-index & 15) and cannot be chosen.
                           [--tape runs/<log>] [--step 12] [--max 8000]

Then in a LISTEN game (the command is client side, a dedicated server
has no renderer):
  pointfile

Limits worth knowing. Colour is (-index & 15), so it cycles every 16
points and cannot be given meaning; use one --what at a time instead.
The particle pool caps how much shows at once, so raise it with
-particles 16384 on the command line. Points are static and client
side: they never touch the server, the bots, or a match.
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(mapname):
    p = ROOT / "src" / f"argus_nav_{mapname}.qc.json"
    if not p.exists():
        sys.exit(f"no nav json for {mapname}: {p}")
    d = json.loads(p.read_text())
    nodes = [w["origin"] if isinstance(w, dict) else w for w in d["nodes"]]
    return d, nodes


def lerp(a, b, step):
    dx, dy, dz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    n = max(1, int((dx*dx + dy*dy + dz*dz) ** 0.5 / step))
    return [(a[0]+dx*i/n, a[1]+dy*i/n, a[2]+dz*i/n) for i in range(n + 1)]


def tape_points(tape):
    """freeze and stall positions, the cells worth standing in"""
    PAT = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+"
                     r"(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+)")
    rows = []
    for line in Path(tape).read_text(errors="replace").splitlines():
        m = PAT.search(line)
        if m:
            rows.append((m.group(1), float(m.group(2)),
                         (float(m.group(3)), float(m.group(4)), float(m.group(5))),
                         float(m.group(6))))
    # group by track first: the tape interleaves every bot and the
    # human, so a neighbour's moving sample would break the run of a
    # bot that is standing perfectly still
    per = {}
    for name, t, pos, spd in rows:
        per.setdefault(name, []).append((t, pos, spd))
    out = []
    for name in per:
        run = []
        for t, pos, spd in sorted(per[name]):
            if spd < 20:
                run.append(pos)
            else:
                if len(run) >= 12:      # 6 s at the 0.5 s sample rate
                    out.append(run[len(run) // 2])
                run = []
        if len(run) >= 12:
            out.append(run[len(run) // 2])
    return out


# typed links, one family at a time (#254 item 7). Cheap, and it
# makes a map's movement vocabulary legible: which crossings are
# jumps, which are rides, which need a door open.
TYPED = {
    "jump": "jlinks",
    "door": "doorlinks",
    "lift": "liftlinks",
    "train": "trainlinks",
    "rocket": "rjlinks",
    "sprint": "sprintlinks",
    "tele": "teles",
}


def event_points(tape, verbs):
    """Positions where a named event fired (#254 item 3).

    ARGEVT carries no position for most verbs, so the position is the
    emitting bot's nearest ARGLOG sample in time. That is accurate to
    half a second, which at run speed is about 160 units - good enough
    to stand in the right room, which is the whole point of drawing
    these rather than counting them.
    """
    LOG = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+"
                     r"(-?[\d.]+)\s+(-?[\d.]+)'")
    EVT = re.compile(r"ARGEVT (.+?) (\w+)")
    track, hits = {}, []
    for line in Path(tape).read_text(errors="replace").splitlines():
        m = LOG.search(line)
        if m:
            track[m.group(1)] = (float(m.group(3)), float(m.group(4)),
                                 float(m.group(5)))
            continue
        m = EVT.search(line)
        if m and m.group(2) in verbs:
            pos = track.get(m.group(1))
            if pos:
                hits.append(pos)
    return hits


def human_points(tape, step):
    """The human's own trail (#254 item 2).

    Human tracks have been in the tape since v3.66 and nobody has ever
    seen one. A human is a name with ARGLOG rows but no spawned or
    respawn event, the same rule the Rust parser uses.
    """
    LOG = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+"
                     r"(-?[\d.]+)\s+(-?[\d.]+)'")
    SPAWN = re.compile(r"ARGEVT (.+?) (?:spawned|respawn)\b")
    text = Path(tape).read_text(errors="replace")
    bots = set(SPAWN.findall(text))
    per = {}
    for line in text.splitlines():
        m = LOG.search(line)
        if m and m.group(1) not in bots:
            per.setdefault(m.group(1), []).append(
                (float(m.group(2)), (float(m.group(3)), float(m.group(4)),
                                     float(m.group(5)))))
    if not per:
        print("note: no human track in this tape (every name spawns)")
    pts = []
    for name in per:
        rows = [p for _, p in sorted(per[name])]
        for a, b in zip(rows, rows[1:]):
            d = sum((b[i] - a[i]) ** 2 for i in range(3)) ** 0.5
            if d < 700:        # a respawn is a teleport, not travel
                pts += lerp(a, b, step)
    return pts


# The router refuses rocket links to a bot that cannot pay for one and
# sprint links below skill 3, so a reconstruction that always allows
# them finds shortcuts the bot was never offered. Measured on dm2:
# including them matches the router's own hop count on 155 of 182
# routes, excluding them on 164. Pass --gated to include them.
GATED = ("rjlinks", "sprintlinks")


def _adj(d, gated=False):
    """Forward edges over the link classes the router can walk.

    The router is a BFS over these, so reconstructing with the same
    set reproduces the path it would have produced. Route events carry
    the hop COUNT plus start and goal positions but not the hops
    themselves, so the path has to be rebuilt rather than read.
    """
    n = len(d["nodes"])
    adj = [[] for _ in range(n)]
    keys = ("links", "jlinks", "doorlinks", "liftlinks", "trainlinks",
            "swimlinks", "teles") + (GATED if gated else ())
    for key in keys:
        for L in d.get(key, []):
            a, b = L[0], L[1]
            if 0 <= a < n and 0 <= b < n:
                adj[a].append(b)
    return adj


def _nearest(nodes, p):
    best, bd = None, 1e18
    for i, q in enumerate(nodes):
        dd = (q[0]-p[0])**2 + (q[1]-p[1])**2 + (q[2]-p[2])**2
        if dd < bd:
            bd, best = dd, i
    return best, bd ** 0.5


def route_points(tape, d, nodes, step, only=None, gated=False):
    """Planned routes, rebuilt hop by hop (#254 item 1).

    Draw this and then --what trail for the same bot: intent and
    reality, in the level, one file each. They cannot share a file
    because particle colour is (-index & 15) and cannot be chosen.
    """
    from collections import deque
    adj = _adj(d, gated)
    pat = re.compile(r"ARGEVT (.+?) route (\d+) start '\s*(-?[\d.]+)\s+"
                     r"(-?[\d.]+)\s+(-?[\d.]+)' goal '\s*(-?[\d.]+)\s+"
                     r"(-?[\d.]+)\s+(-?[\d.]+)'")
    pts, drawn, missed, mismatched = [], 0, 0, []
    for line in Path(tape).read_text(errors="replace").splitlines():
        m = pat.search(line)
        if not m:
            continue
        if only and m.group(1) != only:
            continue
        s, sd = _nearest(nodes, (float(m.group(3)), float(m.group(4)),
                                 float(m.group(5))))
        g, gd = _nearest(nodes, (float(m.group(6)), float(m.group(7)),
                                 float(m.group(8))))
        if s is None or g is None or sd > 64 or gd > 64:
            missed += 1
            continue
        prev, q = {s: None}, deque([s])
        while q:
            cur = q.popleft()
            if cur == g:
                break
            for nx in adj[cur]:
                if nx not in prev:
                    prev[nx] = cur
                    q.append(nx)
        if g not in prev:
            missed += 1
            continue
        path, cur = [], g
        while cur is not None:
            path.append(nodes[cur])
            cur = prev[cur]
        path.reverse()
        # SELF-CHECK. The route event carries the router's own hop
        # count, so a rebuild that disagrees means this link set has
        # drifted from the router's and the drawing is a lie. On e1m1
        # 79 of 79 agree exactly.
        if len(path) - 1 != int(m.group(2)):
            mismatched.append((int(m.group(2)), len(path) - 1))
        for a, b in zip(path, path[1:]):
            pts += lerp(a, b, step)
        drawn += 1
    print(f"rebuilt {drawn} planned route(s)"
          + (f", {missed} unresolvable against this graph" if missed else ""))
    if mismatched:
        # Some disagreement is expected and is not drift: the router's
        # path depends on what the bot was carrying at the time, and
        # the tape does not record that. A LARGE share disagreeing is
        # the signal worth acting on.
        print(f"note: {len(mismatched)} of {drawn} rebuilt path(s) differ "
              f"from the router's own hop count, e.g. reported "
              f"{mismatched[0][0]} rebuilt {mismatched[0][1]}. Expect a few: "
              f"equipment gating decides which links a given bot was "
              f"offered. Most of them differing means this link set has "
              f"drifted from the router's.")
    return pts


def trail_points(tape, step, only=None):
    """One track's actual path (#254 item 1's other half)."""
    LOG = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+"
                     r"(-?[\d.]+)\s+(-?[\d.]+)'")
    per = {}
    for line in Path(tape).read_text(errors="replace").splitlines():
        m = LOG.search(line)
        if m and (not only or m.group(1) == only):
            per.setdefault(m.group(1), []).append(
                (float(m.group(2)), (float(m.group(3)), float(m.group(4)),
                                     float(m.group(5)))))
    if not per:
        print(f"note: no track named {only!r} in this tape" if only
              else "note: no ARGLOG rows in this tape")
    pts = []
    for name in per:
        rows = [p for _, p in sorted(per[name])]
        for a, b in zip(rows, rows[1:]):
            if sum((b[i]-a[i])**2 for i in range(3)) ** 0.5 < 700:
                pts += lerp(a, b, step)
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--what", default="nodes",
                    choices=["nodes", "links", "swim", "water", "tape",
                             "fails", "human", "route", "trail"]
                            + sorted(TYPED))
    ap.add_argument("--tape")
    ap.add_argument("--bot", help="restrict route/trail to one track")
    ap.add_argument("--gated", action="store_true",
                    help="let rebuilt routes use rocket and sprint links")
    ap.add_argument("--step", type=float, default=12.0)
    ap.add_argument("--max", type=int, default=8000)
    ap.add_argument("--out", default=str(ROOT / "engine" / "argus" / "maps"))
    a = ap.parse_args()

    d, nodes = load(a.map)
    pts = []
    if a.what == "nodes":
        pts = [tuple(n) for n in nodes]
    elif a.what == "links":
        for L in d["links"]:
            pts += lerp(nodes[L[0]], nodes[L[1]], a.step)
    elif a.what == "swim":
        sl = d.get("swimlinks", [])
        if not sl:
            print(f"note: {a.map} has no swim links")
        for L in sl:
            pts += lerp(nodes[L[0]], nodes[L[1]], a.step)
    elif a.what == "water":
        for L in d.get("swimlinks", []):
            pts.append(tuple(nodes[L[0]]))
            pts.append(tuple(nodes[L[1]]))
    elif a.what == "tape":
        if not a.tape:
            sys.exit("--what tape needs --tape runs/<log>")
        pts = tape_points(a.tape)
    elif a.what == "fails":
        if not a.tape:
            sys.exit("--what fails needs --tape runs/<log>")
        pts = event_points(a.tape, {"routefail", "abandon", "hazard",
                                    "trapped", "stall"})
        if not pts:
            print(f"note: no failure events in {a.tape}")
    elif a.what == "human":
        if not a.tape:
            sys.exit("--what human needs --tape runs/<log>")
        pts = human_points(a.tape, a.step)
    elif a.what == "route":
        if not a.tape:
            sys.exit("--what route needs --tape runs/<log>")
        pts = route_points(a.tape, d, nodes, a.step, a.bot, a.gated)
    elif a.what == "trail":
        if not a.tape:
            sys.exit("--what trail needs --tape runs/<log>")
        pts = trail_points(a.tape, a.step, a.bot)
    elif a.what in TYPED:
        key = TYPED[a.what]
        links = d.get(key, [])
        if not links:
            print(f"note: {a.map} has no {a.what} links")
        for L in links:
            pts += lerp(nodes[L[0]], nodes[L[1]], a.step)

    if len(pts) > a.max:
        keep = len(pts) / a.max
        pts = [p for i, p in enumerate(pts) if int(i / keep) != int((i - 1) / keep)]
        print(f"thinned to {len(pts)} points (raise --max, and pass "
              f"-particles {max(8192, len(pts) * 2)} to the engine)")

    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    f = outdir / f"{a.map}.pts"
    f.write_text("".join(f"{p[0]:.1f} {p[1]:.1f} {p[2]:.1f}\n" for p in pts))
    print(f"wrote {f}  ({len(pts)} points, --what {a.what})")
    print("in a listen game, type: pointfile")


if __name__ == "__main__":
    main()
