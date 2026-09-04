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
  argus_pointfile.py <map> [--what nodes|links|swim|water|tape]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--what", default="nodes",
                    choices=["nodes", "links", "swim", "water", "tape"])
    ap.add_argument("--tape")
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
