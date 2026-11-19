#!/usr/bin/env python3
"""argus_guard_replica.py - which branch of the brink guard vetoed, read offline.

Argus_Physics runs the per-frame brink guard along the bot's velocity after
this frame's friction and acceleration, 32u ahead (plus 0.11u per u/s over
250, capped at 52) at origin height, and deflects when Argus_MoveHazard
vetoes. This tool replays that guard against a map's hull-0 tree for the
frames of a full-rate ARGMOT tape (scratch1 697) and names the branch:

  wall          the probe point is buried in solid that does not end within
                280u, and the knee recheck finds no stair tread
  lava          lava or slime covers the floor under the probe, not bridged
  void          no solid within 280u under the probe (and no pool)
  run_off_lava  the floor under the probe is dry, but a bot running off at its
  run_off_void  current speed lands in lava, slime or a void
                (Argus_DropLandHazard)
  none          no veto

Trace semantics follow the engine's hull check: a traceline that starts in
solid and never leaves it returns fraction 1 (allsolid), and one that leaves
it reports an impact at the next solid it enters. On probes that start in
solid with air below, that rule predicted 1250 of 1365 known outcomes on dm4,
lab_drymix and lab_drymix2 (the guard either deflected or did not); treating
every start in solid as fraction 1 predicted 518. Brush entities are not in
the hull-0 world tree, so doors, plats and func_walls are invisible here.

An ARGMOT row is sampled at StartFrame: it carries the pose at the start of
frame k and the cause written during frame k-1. So the guard that put
hazard_* on row k ran from row k-1's pose, with the velocity of the step into
it, and its wish is approximated by row k-1's.

The report validates the replica on the tape itself. Mode 2 route steering
has no steering-side hazard check, so a route-led deflection start is a known
guard veto (recall), and a steady routed ground frame is a known pass (false
vetoes, every fifth one sampled). A re-entry is a route-led deflection start
within two route frames of the bot's previous deflection episode.

MEASURED 2026-11-17 on eight dm4 control tapes (recall 0.895, false vetoes
0.019): of 1369 re-entries, 47 per cent are wall vetoes, 36 lava, 6 void and
2.5 run-off; on lab_voidcorner, lab_drymix and lab_drymix2 97 to 98 per cent
are lava vetoes, because a generated floor is a 16u slab over open air and a
probe buried in one finds the lava below (runs/dm4-reentry-guard.results.json).

--overhead GRAPH.qc.json scores the overhead-target protocol's primary
(docs/specs/2026-11-17-overhead-target-protocol.md) per tape: wall re-entries
whose steering points at a waypoint overhead behind solid. From row k-1's pose
and wish (the frame judge() replays), take the graph waypoint 24 to 340u away
horizontally whose bearing lies closest to the wish. The re-entry counts when
that bearing is within 8 degrees of the wish, the waypoint stands 64u or more
above the bot's origin, and a hull-0 sample every 8u on the straight line
between them, both ends excluded, is solid. The protocol's wording admits any
waypoint in the cone; the recorded reading took the closest in bearing only,
and that choice is what reproduces it. On the 32 dm4ov2 and dm4ov3 tapes this
matches every per-tape count in runs/dm4-overhead-target.results.json
(control and candidate means 15.75 and 11.62, then 12.12 and 12.75), and so it
does on the lab_dropwall2 rung and the first dm4 pair, which it was not fitted
on. Counting any waypoint in the cone gives 718 events on those 32 tapes
against the recorded 418.

--region X0 X1 Y0 Y1 Z0 Z1 adds, per tape, the same counts for events whose
row k-1 pose lies strictly inside that box, and the routed seconds spent
there: the intervals from each mode 2 row inside the box to the next row,
summed over stays. A stay still open when the bot's rows end is left out,
because the tape was cut inside it and its length is unknown. With the box
x 690 to 1060, y -700 to -390, z -160 to -90 this matches the room split in
that results file tape for tape (0.88 and 3.38 events a tape on dm4ov2, 2.62
and 1.00 on dm4ov3) and every routed-seconds figure to its one decimal.

usage:
  python tools/argus_guard_replica.py MAP TAPE.log [TAPE.log ...] [--json]
      [--overhead GRAPH.qc.json [--region X0 X1 Y0 Y1 Z0 Z1]]
  python tools/argus_guard_replica.py --help

MAP uses the shared BSP lookup (ARGUS_MAPS first). Exit 0 on success,
2 when the BSP, a tape or the graph is missing or a flag is malformed.
"""
import collections
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from argus_bsp import load_classifier  # noqa: E402 - tools path set just above
from argus_paths import bsp_path  # noqa: E402

ROW = re.compile(r"^ARGMOT (.+?) ms (\S+) pos '\s*(\S+)\s+(\S+)\s+(\S+)' wish\s+(\S+) cause (\S+) "
                 r"ctx '\s*(\S+)\s+(\S+)\s+(\S+)'")
SOLID, WATER, SLIME, LAVA = -2, -3, -4, -5
MAXSPEED, STOPSPEED, FRICTION, ACCEL, GRAVITY = 320.0, 100.0, 4.0, 10.0, 800.0
FLOOR_REACH = 280.0
STEP = 4.0
BRANCHES = ("wall", "lava", "void", "run_off_lava", "run_off_void", "none", "unjudged")
# the overhead-target primary: cone, rise, horizontal reach and line sampling
OVERHEAD_CONE, OVERHEAD_RISE, OVERHEAD_NEAR, OVERHEAD_FAR, LINE_STEP = 8.0, 64.0, 24.0, 340.0, 8.0
TAPE_COUNTS = ("route_led_starts", "re_entries", "wall_re_entries", "overhead")


class Guard:
    """Argus_MoveHazard over a contents(x, y, z) function.

    gravity is the map's sv_gravity, which Argus_DropLandHazard reads
    through Argus_Gravity: 100 on e1m8, 800 elsewhere.
    """

    def __init__(self, contents, gravity=GRAVITY):
        self.c = contents
        self.gravity = gravity

    @classmethod
    def from_bsp(cls, bsp):
        return cls(load_classifier(bsp))

    def _refine(self, inside, outside, solid_at):
        for _ in range(4):
            mid = (inside + outside) / 2
            if solid_at(mid):
                inside = mid
            else:
                outside = mid
        return outside

    def trace_down(self, x, y, top, bottom):
        """traceline (x y top) to (x y bottom): the impact z, or None for fraction 1."""
        c = self.c
        z = top
        if c(x, y, top) == SOLID:
            while z - STEP >= bottom and c(x, y, z - STEP) == SOLID:
                z -= STEP
            if z - STEP < bottom:
                return None             # never left the solid: allsolid
            z -= STEP
        while z - STEP >= bottom:
            if c(x, y, z - STEP) == SOLID:
                return self._refine(z - STEP, z, lambda zz: c(x, y, zz) == SOLID)
            z -= STEP
        return bottom if c(x, y, bottom) == SOLID else None

    def trace_ahead(self, x, y, z, fx, fy, dist):
        """traceline along a heading at constant z: distance to the impact, or None."""
        c = self.c

        def solid(d):
            return c(x + fx * d, y + fy * d, z) == SOLID

        d = 0.0
        if solid(0.0):
            while d < dist and solid(min(dist, d + STEP)):
                d = min(dist, d + STEP)
            if d >= dist:
                return None
            d = min(dist, d + STEP)
        while d < dist:
            nd = min(dist, d + STEP)
            if solid(nd):
                lo, hi = d, nd
                for _ in range(4):
                    mid = (lo + hi) / 2
                    if solid(mid):
                        hi = mid
                    else:
                        lo = mid
                return lo
            d = nd
        return None

    def solid_between(self, a, b, step=LINE_STEP):
        """True when a sample every step units strictly between points a and b is solid."""
        d = math.dist(a, b)
        i = 1
        while i * step < d:
            t = i * step / d
            if self.c(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t) == SOLID:
                return True
            i += 1
        return False

    def _bridge_solid(self, x, y, z):
        f = self.trace_down(x, y, z + 4, z - 48)
        return f is not None and self.c(x, y, f + 2) not in (LAVA, SLIME)

    def bridge(self, x, y, z):
        """Argus_HazardBridge: opposed dry support 17u either side, on either axis."""
        if self._bridge_solid(x + 17, y, z) and self._bridge_solid(x - 17, y, z):
            return True
        return self._bridge_solid(x, y + 17, z) and self._bridge_solid(x, y - 17, z)

    def drop_land(self, oz, ax, ay, fx, fy, spd, floorz):
        """Argus_DropLandHazard: where a bot running off at spd comes down."""
        drop = oz - 24 - floorz
        if drop <= 18 or spd < 1:
            return None
        carry = spd * math.sqrt(2 * drop / self.gravity)
        hit = self.trace_ahead(ax, ay, oz, fx, fy, carry)
        if hit is not None:
            carry = max(0.0, hit - 16)
        lx, ly = ax + fx * carry, ay + fy * carry
        f = self.trace_down(lx, ly, oz + 4, oz - FLOOR_REACH)
        if f is None:
            return None if self.c(lx, ly, oz - FLOOR_REACH) == WATER else "run_off_void"
        if self.c(lx, ly, f + 2) in (LAVA, SLIME):
            return None if self.bridge(lx, ly, oz) else "run_off_lava"
        return None

    def move_hazard(self, x, y, z, yaw, pdist, spd):
        """The branch of Argus_MoveHazard that vetoes this probe, or 'none'."""
        fx, fy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        ax, ay = x + fx * pdist, y + fy * pdist
        c = self.c
        f = self.trace_down(ax, ay, z + 4, z - FLOOR_REACH)
        if f is None:
            if c(ax, ay, z + 4) == SOLID:
                tread = self.trace_down(ax, ay, z + 26, z - 8)
                if tread is not None and c(ax, ay, tread + 2) not in (LAVA, SLIME):
                    return "none"       # a stair tread at climbable height
                if c(ax, ay, z - FLOOR_REACH) == WATER:
                    return "none"
                return "wall"
            return "none" if c(ax, ay, z - FLOOR_REACH) == WATER else "void"
        if c(ax, ay, f + 2) in (LAVA, SLIME):
            return "none" if self.bridge(ax, ay, z) else "lava"
        return self.drop_land(z, ax, ay, fx, fy, spd, f) or "none"


def physics_heading(vx, vy, wish, dt, wishspeed=MAXSPEED):
    """Argus_Friction then Argus_Accelerate toward the wish for one ground frame: (yaw, speed)."""
    spd = math.hypot(vx, vy)
    if spd >= 1:
        control = max(spd, STOPSPEED)
        scale = max(0.0, spd - dt * control * FRICTION) / spd
        vx, vy = vx * scale, vy * scale
    else:
        vx = vy = 0.0
    wx, wy = math.cos(math.radians(wish)), math.sin(math.radians(wish))
    add = wishspeed - (vx * wx + vy * wy)
    if add > 0:
        acc = min(ACCEL * dt * wishspeed, add)
        vx, vy = vx + acc * wx, vy + acc * wy
    return math.degrees(math.atan2(vy, vx)), math.hypot(vx, vy)


def probe_distance(spd):
    """The physics guard's speed-scaled probe reach."""
    reach = 32.0 if spd <= 250 else 32 + (spd - 250) * 0.11
    return min(reach, 52.0)


def read_tape(path):
    """ARGMOT rows per bot: (ms, x, y, z, wish, cause, mode, onground)."""
    bots = collections.defaultdict(list)
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            if line.startswith("ARGMOT "):
                m = ROW.match(line)
                if m:
                    bots[m.group(1)].append((float(m.group(2)), float(m.group(3)), float(m.group(4)),
                                             float(m.group(5)), float(m.group(6)), m.group(7),
                                             int(float(m.group(8))), int(float(m.group(10)))))
    return bots


def judge(guard, rows, k):
    """The replica's verdict on the guard that wrote row k's cause, or None when unjudgeable."""
    t0, x0, y0 = rows[k - 2][0:3]
    t1, x1, y1, z1, wish = rows[k - 1][0:5]
    dt0 = (t1 - t0) / 1000.0
    dt = (rows[k][0] - t1) / 1000.0
    if not (0.004 <= dt0 <= 0.05 and 0.004 <= dt <= 0.05):
        return None
    vx, vy = (x1 - x0) / dt0, (y1 - y0) / dt0
    if math.hypot(vx, vy) > 700:
        return None                     # a teleport or a respawn, not a step
    yaw, spd = physics_heading(vx, vy, wish, dt)
    if spd <= 1:
        return None
    return guard.move_hazard(x1, y1, z1, yaw, probe_distance(spd), spd)


def _table(counter):
    total = sum(counter.values())
    out = {"n": total}
    for b in BRANCHES:
        if counter[b]:
            out[b] = counter[b]
    out["share"] = {b: round(counter[b] / total, 3) for b in BRANCHES if counter[b]} if total else {}
    return out


def route_led_starts(guard, rows):
    """Each route-led deflection start on one bot's rows: (k, verdict, grounded, re_entry).

    A start is a hazard_* cause right after a mode 2 route_steer row; it is a
    re-entry when it comes within two route frames of the bot's previous
    deflection episode.
    """
    route_run, seen = 99, False
    for k in range(1, len(rows)):
        cause, prev = rows[k][5], rows[k - 1]
        haz = cause.startswith("hazard_")
        if haz and not prev[5].startswith("hazard_"):
            if prev[5] == "route_steer" and prev[6] == 2 and k >= 2:
                yield k, judge(guard, rows, k) or "unjudged", prev[7] == 1, seen and route_run <= 2
            seen = True
        route_run = 0 if haz else (route_run + 1 if cause == "route_steer" else 99)


def steady_frames(rows):
    """Every fifth steady routed ground frame on one bot's rows: known guard passes."""
    n = 0
    for k in range(2, len(rows)):
        prev = rows[k - 1]
        if rows[k][5] == "route_steer" and prev[5] == "route_steer" and prev[6] == 2 and prev[7] == 1:
            n += 1
            if n % 5 == 0:
                yield k


def load_nodes(path):
    """Waypoint origins from a navgen graph: the .qc.json "nodes" list, or a bare list."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [tuple(float(v) for v in n[:3]) for n in (data["nodes"] if isinstance(data, dict) else data)]


def overhead_target(guard, nodes, rows, k):
    """The waypoint index behind an overhead-target re-entry at row k, or None.

    From row k-1's pose and wish, the waypoint 24 to 340u away horizontally
    whose bearing lies closest to the wish; it counts when that bearing is
    within 8 degrees, it stands 64u or more above the bot and solid lies on
    the straight line to it.
    """
    _, x, y, z, wish = rows[k - 1][0:5]
    best, off = None, None
    for i, (nx, ny, nz) in enumerate(nodes):
        if OVERHEAD_NEAR <= math.hypot(nx - x, ny - y) <= OVERHEAD_FAR:
            d = abs((math.degrees(math.atan2(ny - y, nx - x)) - wish + 180) % 360 - 180)
            if off is None or d < off:
                best, off = i, d
    if best is None or off > OVERHEAD_CONE or nodes[best][2] - z < OVERHEAD_RISE:
        return None
    return best if guard.solid_between((x, y, z), nodes[best]) else None


def in_box(box, x, y, z):
    """True when (x, y, z) lies strictly inside box (x0, x1, y0, y1, z0, z1)."""
    return box[0] < x < box[1] and box[2] < y < box[3] and box[4] < z < box[5]


def routed_seconds(rows, box):
    """Seconds one bot spent routed (mode 2) inside box, over the stays the tape closes."""
    total = stay = 0.0
    for k in range(1, len(rows)):
        prev = rows[k - 1]
        if prev[6] == 2 and in_box(box, *prev[1:4]):
            stay += (rows[k][0] - prev[0]) / 1000.0
        else:
            total, stay = total + stay, 0.0
    return total


def _mean(values):
    return round(sum(values) / len(values), 2) if values else None


def classify(guard, tapes, nodes=None, box=None):
    """Validation, route-led deflection starts and re-entries by branch over the given tapes.

    Given a graph's nodes it also scores each tape's overhead-target wall
    re-entries, and given a box as well, the same counts and the routed
    seconds inside it.
    """
    reentry, starts, steady = collections.Counter(), collections.Counter(), collections.Counter()
    per_tape = []
    for tape in tapes:
        tally, inside = collections.Counter(), collections.Counter()
        for rows in read_tape(tape).values():
            for k, verdict, grounded, again in route_led_starts(guard, rows):
                kinds = []
                if grounded:
                    starts[verdict] += 1
                    kinds.append("route_led_starts")
                if again:
                    reentry[verdict] += 1
                    kinds.append("re_entries")
                    if verdict == "wall":
                        kinds.append("wall_re_entries")
                        if nodes is not None and overhead_target(guard, nodes, rows, k) is not None:
                            kinds.append("overhead")
                tally.update(kinds)
                if box is not None and in_box(box, *rows[k - 1][1:4]):
                    inside.update(kinds)
            for k in steady_frames(rows):
                steady[judge(guard, rows, k) or "unjudged"] += 1
            if box is not None:
                inside["routed_seconds"] += routed_seconds(rows, box)
        entry = {"tape": str(tape), **{key: tally[key] for key in TAPE_COUNTS}}
        if box is not None:
            entry["region"] = {**{key: inside[key] for key in TAPE_COUNTS},
                               "routed_seconds": round(inside["routed_seconds"], 1)}
        per_tape.append(entry)
    judged = sum(v for b, v in starts.items() if b != "unjudged")
    sampled = sum(v for b, v in steady.items() if b != "unjudged")
    report = {
        "validation": {
            "route_led_starts_on_ground": judged,
            "recall": round(1 - starts["none"] / judged, 3) if judged else None,
            "steady_frames_sampled": sampled,
            "false_veto": round(1 - steady["none"] / sampled, 3) if sampled else None,
        },
        "route_led_starts": _table(starts),
        "re_entries": _table(reentry),
    }
    if nodes is not None:
        report["overhead"] = {
            "rule": {"cone_deg": OVERHEAD_CONE, "rise": OVERHEAD_RISE, "near": OVERHEAD_NEAR,
                     "far": OVERHEAD_FAR, "line_step": LINE_STEP, "waypoint": "closest bearing to the wish"},
            "mean": _mean([t["overhead"] for t in per_tape]),
            "per_tape": per_tape,
        }
        if box is not None:
            report["overhead"]["region"] = {
                "box": list(box),
                "mean": _mean([t["region"]["overhead"] for t in per_tape]),
                "mean_routed_seconds": _mean([t["region"]["routed_seconds"] for t in per_tape]),
            }
    return report


USAGE = ("usage: argus_guard_replica.py MAP TAPE.log [TAPE.log ...] [--json] "
         "[--overhead GRAPH.qc.json [--region X0 X1 Y0 Y1 Z0 Z1]]")


def _take(args, flag, n):
    """Remove flag and its n values from args: the values, or None when the flag is absent."""
    if flag not in args:
        return None
    i = args.index(flag)
    values = args[i + 1:i + 1 + n]
    del args[i:i + 1 + n]
    if len(values) < n:
        raise ValueError(f"{flag} takes {n} value(s)")
    return values


def _parse(args):
    """(map and tapes, graph path or None, box or None, as_json) from the command line."""
    graph = _take(args, "--overhead", 1)
    box = _take(args, "--region", 6)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if box is not None:
        if graph is None:
            raise ValueError("--region needs --overhead GRAPH.qc.json")
        try:
            box = tuple(float(v) for v in box)
        except ValueError:
            raise ValueError("--region takes six numbers: X0 X1 Y0 Y1 Z0 Z1") from None
        if not (box[0] < box[1] and box[2] < box[3] and box[4] < box[5]):
            raise ValueError("--region wants each axis low then high")
    if len(args) < 2:
        raise ValueError("a map and at least one tape are required")
    return args, graph[0] if graph else None, box, as_json


def _print_overhead(o):
    rule = o["rule"]
    print(f"  overhead-target wall re-entries: mean {o['mean']} a tape (cone {rule['cone_deg']:g} deg, "
          f"rise {rule['rise']:g}u, {rule['near']:g} to {rule['far']:g}u, closest waypoint by bearing)")
    for t in o["per_tape"]:
        print(f"    {t['tape']}: {t['overhead']} of {t['wall_re_entries']} wall re-entries "
              f"({t['re_entries']} re-entries, {t['route_led_starts']} route-led starts)")
    if "region" in o:
        r = o["region"]
        b = r["box"]
        print(f"  inside x {b[0]:g} to {b[1]:g}, y {b[2]:g} to {b[3]:g}, z {b[4]:g} to {b[5]:g}: "
              f"overhead-target mean {r['mean']} a tape, routed {r['mean_routed_seconds']} s a tape")
        for t in o["per_tape"]:
            g = t["region"]
            print(f"    {t['tape']}: {g['overhead']} of {g['wall_re_entries']} wall re-entries, "
                  f"{g['routed_seconds']} s routed")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    try:
        args, graph, box, as_json = _parse(args)
    except ValueError as exc:
        print(f"{exc}\n{USAGE}", file=sys.stderr)
        return 2
    bsp = bsp_path(HERE.parent, args[0])
    wanted = [*map(Path, args[1:])] + ([Path(graph)] if graph else [])
    missing = [f"{args[0]}.bsp"] if bsp is None else []
    missing.extend(str(path) for path in wanted if not path.is_file())
    if missing:
        print("missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    nodes = load_nodes(graph) if graph else None
    report = {"map": args[0], "tapes": args[1:], **classify(Guard.from_bsp(bsp), args[1:], nodes, box)}
    if graph:
        report["overhead"] = {"graph": graph, "nodes": len(nodes), **report["overhead"]}
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        v = report["validation"]
        print(f"{args[0]}: {len(args) - 1} tape(s); replica recall {v['recall']} on "
              f"{v['route_led_starts_on_ground']} route-led deflections, false vetoes {v['false_veto']} on "
              f"{v['steady_frames_sampled']} steady frames")
        for key in ("re_entries", "route_led_starts"):
            t = report[key]
            parts = ", ".join(f"{b} {t[b]} ({100 * t['share'][b]:.0f}%)" for b in BRANCHES if b in t)
            print(f"  {key.replace('_', ' ')}: {t['n']}: {parts}")
        if graph:
            _print_overhead(report["overhead"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
