#!/usr/bin/env python3
"""What the hazard guard's floor probe cannot see, read from the BSP.

`Argus_MoveHazard` traces 280 units down from a point ahead of the bot. That
distance is the survivable-drop line, so the verdict it returns is binary:
floor within reach, or a void. It cannot say whether the void is a long drop
onto stone or a short one into lava, and two gait changes have now been built
on guesses about that.

This answers it offline. For every waypoint in a map's generated graph it
samples eight headings at the guard's own reach, reproduces the guard's floor
test in hull 0, and for the directions the guard would call a void reports what
is actually underneath and how far down. It also reports how often the guard's
LETHAL verdict - floor found, with lava or slime on it - is reachable from a
waypoint at all.

The measured answer for the shipped graphs, which is why this tool exists:
every void the guard vetoes bottoms out in lava, on dm4 and dm2 alike, so
void-depth lava does not distinguish a catwalk from a deck edge. Meanwhile no
probe direction from any waypoint finds lava underfoot, because navgen seats
waypoints off hazards by construction - so anything keyed on that verdict acts
from off-graph positions only.

With --clearance it also audits each waypoint's cardinal elbow room against
navgen's own seat-shift bar, which answers the neighbouring question: are bots
scraping walls because waypoints sit against them? On the shipped dm4 and dm2
graphs, no - 7 per cent of waypoints are wall-adjacent, and only 6 and 14 per
cent of located wall slides happen near one, against 95 to 99 per cent near
any waypoint at all. Wall scraping is diffuse, not seated.

Examples:
  python tools/argus_voidprobe.py dm4
  python tools/argus_voidprobe.py dm4 dm2 --reach 52
  python tools/argus_voidprobe.py dm4 dm2 dm3 dm6 --clearance
"""

import argparse
import json
import math
import struct
from collections import Counter
from pathlib import Path

# Hull-0 leaf contents, as the BSP stores them.
SOLID, WATER, SLIME, LAVA = -2, -3, -4, -5
NAMES = {0: "empty", -1: "empty", SOLID: "solid", WATER: "water", SLIME: "slime", LAVA: "lava"}
LETHAL = (SLIME, LAVA)
# Argus_MoveHazard's own numbers: it traces this far down for floor, and its
# callers probe between 32 and 52 units ahead depending on gait speed.
DROP_WINDOW = 280
DEFAULT_REACH = 48


def classifier(bsp_path):
    """Hull-0 point contents, the same tree walk the analyser uses."""
    data = Path(bsp_path).read_bytes()

    def lump(index):
        off, length = struct.unpack_from("<ii", data, 4 + index * 8)
        return data[off : off + length]

    raw = lump(1)
    planes = [struct.unpack_from("<4f", raw, i * 20) for i in range(len(raw) // 20)]
    raw = lump(5)
    nodes = [struct.unpack_from("<i8h2H", raw, i * 24) for i in range(len(raw) // 24)]
    raw = lump(10)
    leaves = [struct.unpack_from("<2i6h2H4B", raw, i * 28) for i in range(len(raw) // 28)]
    root = struct.unpack_from("<9f7i", lump(14), 0)[9]

    def contents(x, y, z):
        node = root
        while node >= 0:
            plane = planes[nodes[node][0]]
            side = plane[0] * x + plane[1] * y + plane[2] * z - plane[3]
            node = nodes[node][1] if side >= 0 else nodes[node][2]
        return leaves[-1 - node][0]

    return contents


def waypoints(nav_path):
    nav = json.loads(Path(nav_path).read_text(encoding="utf-8"))
    nodes = nav["nodes"] if isinstance(nav, dict) and "nodes" in nav else nav
    out = []
    for node in nodes:
        if isinstance(node, dict):
            out.append(tuple(node["origin"])[:3] if "origin" in node
                       else (node["x"], node["y"], node["z"]))
        else:
            out.append(tuple(node[:3]))
    return out


def clear_cardinals(contents, x, y, z, offset=24, lift=8):
    """How many of the four cardinals are open, navgen's 5a2 test.

    That pass shifts a decimation seat when walls sit inside 24 units of it,
    because the runtime hazard guard probes at POINT resolution while the bot
    is a 32-unit box: a seat against a wall face makes every arriving bot bury
    its probe in the wall and dither at its own steering target. Replicated
    here so a shipped graph can be audited without regenerating it.
    """
    return sum(1 for dx, dy in ((offset, 0), (-offset, 0), (0, offset), (0, -offset))
               if contents(x + dx, y + dy, z + lift) in (0, -1))


def clearance(bsp, nav):
    """Per-waypoint cardinal clearance for a shipped graph."""
    contents = classifier(bsp)
    counts = Counter()
    tight = []
    for point in waypoints(nav):
        open_dirs = clear_cardinals(contents, *point)
        counts[open_dirs] += 1
        if open_dirs < 4:
            tight.append(tuple(round(v, 1) for v in point))
    return counts, tight


def survey(bsp, nav, reach, floor_step=8, deep_step=16, deep_limit=1400):
    contents = classifier(bsp)
    verdicts = Counter()
    under_void = Counter()
    depths = []
    for x, y, z in waypoints(nav):
        for step in range(8):
            angle = math.radians(step * 45)
            px = x + math.cos(angle) * reach
            py = y + math.sin(angle) * reach
            verdicts["probes"] += 1
            floor = None
            for down in range(4, DROP_WINDOW + 4, floor_step):
                if contents(px, py, z - down) == SOLID:
                    floor = down
                    break
            if floor is None:
                verdicts["void"] += 1
                hit = None
                for down in range(DROP_WINDOW + 4, deep_limit, deep_step):
                    value = contents(px, py, z - down)
                    if value in (SOLID, WATER, SLIME, LAVA):
                        hit = (NAMES.get(value, value), down)
                        break
                hit = hit or ("nothing", 0)
                under_void[hit[0]] += 1
                if hit[0] in ("lava", "slime"):
                    depths.append(hit[1])
                continue
            # Floor found. The guard calls it lethal when the contents just
            # above that floor are lava or slime.
            if contents(px, py, z - floor + 2) in LETHAL:
                verdicts["lethal floor"] += 1
            else:
                verdicts["solid floor"] += 1
    return verdicts, under_void, depths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("maps", nargs="+", help="map names, e.g. dm4 dm2")
    parser.add_argument("--reach", type=int, default=DEFAULT_REACH,
                        help=f"probe distance ahead (default {DEFAULT_REACH})")
    parser.add_argument("--bsp-dir", default="maps_local")
    parser.add_argument("--nav-dir", default="src")
    parser.add_argument("--clearance", action="store_true",
                        help="also audit per-waypoint cardinal clearance against "
                             "navgen's own seat-shift bar")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = {}
    for name in args.maps:
        bsp = Path(args.bsp_dir) / f"{name}.bsp"
        nav = Path(args.nav_dir) / f"argus_nav_{name}.qc.json"
        if not bsp.is_file() or not nav.is_file():
            print(f"{name}: skipped (need {bsp} and {nav})")
            continue
        verdicts, under_void, depths = survey(bsp, nav, args.reach)
        total = verdicts["probes"]
        report[name] = {
            "probe_directions": total,
            "reach": args.reach,
            "lethal_floor": verdicts["lethal floor"],
            "solid_floor": verdicts["solid floor"],
            "void": verdicts["void"],
            "under_the_void": dict(under_void),
            "lethal_depth_range": [min(depths), max(depths)] if depths else None,
        }
        if args.format == "text":
            print(f"{name}: {total} probe directions at {args.reach}u "
                  f"from {total // 8} waypoints")
            for label, key in (("floor, lava on it", "lethal floor"),
                               ("floor, safe", "solid floor"),
                               ("void", "void")):
                count = verdicts[key]
                print(f"    {label:<20} {count:>5}  {100 * count / total:>5.1f}%")
            for key, count in under_void.most_common():
                print(f"      under the void: {key:<8} {count:>5}")
            if depths:
                print(f"      lethal liquid {min(depths)} to {max(depths)} units below")
        if args.clearance:
            counts, tight = clearance(bsp, nav)
            total = sum(counts.values())
            report[name]["clearance"] = {
                "waypoints": total,
                "by_open_cardinals": {str(k): counts[k] for k in sorted(counts)},
                "tight": len(tight),
                "tight_positions": tight,
            }
            if args.format == "text":
                spread = "  ".join(f"{k}:{counts.get(k, 0)}" for k in range(5))
                print(f"    waypoints with a wall inside 24u: {len(tight)}/{total}"
                      f"  (open cardinals {spread})")
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
