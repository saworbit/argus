#!/usr/bin/env python3
"""argus_floorlinks.py - shipped walk links whose own line fails the early-switch floor test.

Argus_WalkArrivalReady lets a bot switch to its next waypoint early only if
floor lies within 60u under the straight line from where it stands to that
waypoint (Argus_WalkLineFloored, #775). Some level walk links cross a void
corner, so the line from their own source seat fails that test, and the
runtime holds a bot on such a link until it stands within 8u of the seat.
That hold is deliberate where the void is lethal: on dm4 these links ring
the lava pit, and skipping the test on them took world lava deaths from 13
to 22 over eight played pairs (#905). A listed link is a corner that wants
an elbow seat (the #778 and #904 pattern), so a bot can take it without
the hold.

This replays the runtime test offline on hull 0 for every level walk link
(height change at most 18u, not typed) of a shipped graph: a sample every 12u
along the line, at the height interpolated between the two seats, traced 60u
down; a sample that starts in solid is a wall, not a void. Brush entities are
not in hull 0, so a walkway that is a func_wall or a plat reads as a void
here while the runtime sees floor: treat a listed link on one as suspect.

usage:
  python tools/argus_floorlinks.py dm3
  python tools/argus_floorlinks.py dm4 dm2 e1m8 --json
  python tools/argus_floorlinks.py dm3 --graph path/to/argus_nav_dm3.qc.json

MAP resolves to ARGUS_MAPS/<map>.bsp (default maps_local/) and the graph to
src/argus_nav_<map>.qc.json. Exit 0 on success, 2 when a BSP or graph is
missing or an argument is malformed.
"""
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from argus_guard_replica import SOLID, Guard  # noqa: E402 - tools path set just above

SAMPLE = 12.0       # Argus_WalkLineFloored's step
DEPTH = 60.0        # how far below the line it looks for floor
LEVEL = 18.0        # Argus_WalkArrivalReady skips the test past this height change
TYPED = ("jlinks", "sprintlinks", "rjlinks", "liftlinks", "swimlinks", "trainlinks",
         "doorlinks", "teles")


def first_void(guard, a, b):
    """The first sample on a -> b with no floor within DEPTH, or None when floored."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return None
    ux, uy = dx / length, dy / length
    s = SAMPLE
    while s < length:
        px, py = a[0] + ux * s, a[1] + uy * s
        pz = a[2] + (b[2] - a[2]) * (s / length)
        if guard.c(px, py, pz) != SOLID and guard.trace_down(px, py, pz, pz - DEPTH) is None:
            return (round(px, 1), round(py, 1), round(pz, 1), s)
        s += SAMPLE
    return None


def failing_links(guard, doc):
    """(level walk links checked, [(a, b, void sample), ...]) for a shipped graph document."""
    nodes = [tuple(float(v) for v in n) for n in doc["nodes"]]
    typed = set()
    for key in TYPED:
        typed |= {(int(p[0]), int(p[1])) for p in doc.get(key, [])}
    checked, failing = 0, []
    for row in doc.get("links", []):
        a, b = int(row[0]), int(row[1])
        if (a, b) in typed or abs(nodes[b][2] - nodes[a][2]) > LEVEL:
            continue
        checked += 1
        void = first_void(guard, nodes[a], nodes[b])
        if void is not None:
            failing.append((a, b, void))
    return checked, failing


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    graph = None
    if "--graph" in args:
        i = args.index("--graph")
        if i + 1 >= len(args):
            print("--graph needs a path", file=sys.stderr)
            return 2
        graph = Path(args[i + 1])
        del args[i:i + 2]
    if not args or (graph is not None and len(args) != 1):
        print("give one or more maps (exactly one with --graph)", file=sys.stderr)
        return 2
    maps = Path(os.environ.get("ARGUS_MAPS", HERE.parent / "maps_local"))
    reports = []
    for name in args:
        bsp = maps / f"{name}.bsp"
        path = graph or HERE.parent / "src" / f"argus_nav_{name}.qc.json"
        missing = [str(p) for p in (bsp, path) if not p.is_file()]
        if missing:
            print("missing: " + ", ".join(missing), file=sys.stderr)
            return 2
        doc = json.loads(path.read_text(encoding="utf-8"))
        checked, failing = failing_links(Guard.from_bsp(bsp), doc)
        nodes = doc["nodes"]
        reports.append({"map": name, "checked": checked, "failing": [
            {"from": a, "to": b, "from_pos": nodes[a], "to_pos": nodes[b],
             "void": list(v[:3]), "along": v[3]} for a, b, v in failing]})
    if as_json:
        print(json.dumps(reports, indent=2))
        return 0
    for r in reports:
        print(f"{r['map']}: {len(r['failing'])} of {r['checked']} level walk links fail the "
              f"floor test from their own seat")
        for f in r["failing"]:
            print(f"  n{f['from']} -> n{f['to']}: no floor within {DEPTH:.0f}u at "
                  f"({f['void'][0]:.0f} {f['void'][1]:.0f} {f['void'][2]:.0f}), "
                  f"{f['along']:.0f}u along")
    return 0


if __name__ == "__main__":
    sys.exit(main())
