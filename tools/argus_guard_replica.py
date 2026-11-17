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

usage:
  python tools/argus_guard_replica.py MAP TAPE.log [TAPE.log ...] [--json]
  python tools/argus_guard_replica.py --help

MAP resolves to ARGUS_MAPS/<map>.bsp (default maps_local/). Exit 0 on success,
2 when the BSP or a tape is missing.
"""
import collections
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from argus_bsp import load_classifier  # noqa: E402 - tools path set just above

ROW = re.compile(r"^ARGMOT (.+?) ms (\S+) pos '\s*(\S+)\s+(\S+)\s+(\S+)' wish\s+(\S+) cause (\S+) "
                 r"ctx '\s*(\S+)\s+(\S+)\s+(\S+)'")
SOLID, WATER, SLIME, LAVA = -2, -3, -4, -5
MAXSPEED, STOPSPEED, FRICTION, ACCEL, GRAVITY = 320.0, 100.0, 4.0, 10.0, 800.0
FLOOR_REACH = 280.0
STEP = 4.0
BRANCHES = ("wall", "lava", "void", "run_off_lava", "run_off_void", "none", "unjudged")


class Guard:
    """Argus_MoveHazard over a contents(x, y, z) function."""

    def __init__(self, contents):
        self.c = contents

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
        carry = spd * math.sqrt(2 * drop / GRAVITY)
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


def classify(guard, tapes):
    """Validation, route-led deflection starts and re-entries by branch over the given tapes."""
    reentry, starts, steady = collections.Counter(), collections.Counter(), collections.Counter()
    for tape in tapes:
        for rows in read_tape(tape).values():
            route_run, seen, n = 99, False, 0
            for k in range(1, len(rows)):
                cause, prev = rows[k][5], rows[k - 1]
                haz = cause.startswith("hazard_")
                if haz and not prev[5].startswith("hazard_"):
                    if prev[5] == "route_steer" and prev[6] == 2 and k >= 2:
                        verdict = judge(guard, rows, k) or "unjudged"
                        if prev[7] == 1:
                            starts[verdict] += 1
                        if seen and route_run <= 2:
                            reentry[verdict] += 1
                    seen = True
                elif (not haz and k >= 2 and cause == "route_steer" and prev[5] == "route_steer"
                      and prev[6] == 2 and prev[7] == 1):
                    n += 1
                    if n % 5 == 0:
                        steady[judge(guard, rows, k) or "unjudged"] += 1
                route_run = 0 if haz else (route_run + 1 if cause == "route_steer" else 99)
    judged = sum(v for b, v in starts.items() if b != "unjudged")
    sampled = sum(v for b, v in steady.items() if b != "unjudged")
    return {
        "validation": {
            "route_led_starts_on_ground": judged,
            "recall": round(1 - starts["none"] / judged, 3) if judged else None,
            "steady_frames_sampled": sampled,
            "false_veto": round(1 - steady["none"] / sampled, 3) if sampled else None,
        },
        "route_led_starts": _table(starts),
        "re_entries": _table(reentry),
    }


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) < 2:
        print("usage: argus_guard_replica.py MAP TAPE.log [TAPE.log ...] [--json]", file=sys.stderr)
        return 2
    maps = Path(os.environ.get("ARGUS_MAPS", HERE.parent / "maps_local"))
    bsp = maps / f"{args[0]}.bsp"
    missing = [str(p) for p in [bsp, *map(Path, args[1:])] if not Path(p).is_file()]
    if missing:
        print("missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    report = {"map": args[0], "tapes": args[1:], **classify(Guard.from_bsp(bsp), args[1:])}
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
