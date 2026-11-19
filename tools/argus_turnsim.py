#!/usr/bin/env python3
"""Trace a routed bot around a corner and rank waypoint seats offline."""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

from argus_bsp import Bsp, CONTENTS_EMPTY, CONTENTS_LAVA, CONTENTS_SLIME, CONTENTS_SOLID, STEPSIZE
from argus_floorlinks import LEVEL, TYPED, first_void
from argus_guard_replica import Guard
from argus_paths import bsp_path


ROOT = Path(__file__).resolve().parent.parent
DT = 0.01425
MAX_SPEED, STOP_SPEED, FRICTION, ACCELERATION, TURN_RATE = 320, 100, 4, 10, 320
LATERALS = (-12, 0, 12)
SPEEDS = (280, 320, 360)
FEET = 24
FOOTPRINT = tuple((x, y) for x in (-15, 0, 15) for y in (-15, 0, 15))


@dataclass(frozen=True)
class Trial:
    outcome: str
    wall_frames: int
    seconds: float
    position: tuple[float, float, float]


class World:
    def __init__(self, bsp):
        self.bsp = bsp
        self.guard = Guard(bsp.h0)

    def fits(self, x, y, z):
        return self.bsp.h1(x, y, z) == CONTENTS_EMPTY

    def hull_support(self, x, y, z):
        # A clip ledge can support the player even when the render hull is empty.
        return self.bsp.h1(x, y, z - .125) == CONTENTS_SOLID

    def supported(self, x, y, z):
        if self.hull_support(x, y, z):
            return True
        feet = z - FEET
        return any(self.guard.trace_down(x + dx, y + dy, feet + 1, feet - 2)
                   is not None for dx, dy in FOOTPRINT)

    def ground_height(self, x, y, z):
        """Return the current origin height or a reachable world step."""
        if self.fits(x, y, z) and self.supported(x, y, z):
            return z
        feet = z - FEET
        top = feet + STEPSIZE + 1
        floor = self.guard.trace_down(x, y, top, feet - STEPSIZE - 1)
        if floor is None or abs(floor - feet) > STEPSIZE:
            return None
        height = floor + FEET
        if self.fits(x, y, height) and self.supported(x, y, height):
            return height
        return None

    def seat_ok(self, point):
        x, y, z = point
        feet = z - FEET
        return (self.fits(x, y, z)
                and (self.hull_support(x, y, z)
                     or self.guard.trace_down(x, y, feet + 1, feet - 2) is not None)
                and self.bsp.h0(x, y, feet + 1) not in (CONTENTS_LAVA, CONTENTS_SLIME))

    def clear_line(self, a, b):
        dx, dy, dz = (end - start for start, end in zip(a, b))
        count = max(1, int(math.hypot(dx, dy) / 4))
        return all(
            self.bsp.h0(a[0] + dx * i / count, a[1] + dy * i / count, a[2] + dz * i / count)
            != CONTENTS_SOLID
            for i in range(1, count + 1)
        )

    def arrival_ready(self, pos, node, following, floor_test):
        if math.dist(pos, node) <= 8 or abs(following[2] - node[2]) > LEVEL:
            return True
        dx, dy = following[0] - pos[0], following[1] - pos[1]
        length = math.hypot(dx, dy) or 1
        sx, sy = dy * 15 / length, -dx * 15 / length
        for side in (-1, 1):
            a = (pos[0] + side * sx, pos[1] + side * sy, pos[2] + 8)
            b = (following[0] + side * sx, following[1] + side * sy, following[2] + 8)
            if not self.clear_line(a, b):
                return False
        return not floor_test or first_void(self.guard, pos, following) is None

    def drop_ahead(self, pos, target):
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        length = math.hypot(dx, dy) or 1
        x, y = pos[0] + dx * 48 / length, pos[1] + dy * 48 / length
        if self.bsp.h0(x, y, pos[2]) == CONTENTS_SOLID:
            return False
        feet = pos[2] - FEET
        return self.guard.trace_down(x, y, feet, feet - 280) is None


def simulate(world, chain, lateral=0, speed=320, *, back=80, floor_test=True):
    """Start back units short of the middle seat and integrate through it."""
    a, elbow, target = chain
    dx, dy = elbow[0] - a[0], elbow[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return Trial("unsupported start", 0, 0, a)
    ux, uy = dx / length, dy / length
    along = max(0, length - back)
    # Sample the requested offset when it fits. Near walls, move the
    # starting origin towards the centre until it can stand.
    while True:
        x, y = a[0] + ux * along - uy * lateral, a[1] + uy * along + ux * lateral
        z = world.ground_height(x, y, a[2] + (elbow[2] - a[2]) * along / length)
        if z is not None:
            break
        if lateral == 0:
            return Trial("unsupported start", 0, 0, (x, y, a[2]))
        lateral -= math.copysign(min(4, abs(lateral)), lateral)

    yaw = math.atan2(uy, ux)
    vx, vy = ux * speed, uy * speed
    node = elbow
    walls = 0
    turn = math.radians(TURN_RATE * DT)
    for frame in range(math.ceil(8 / DT)):
        seconds = frame * DT
        pos = (x, y, z)
        distance = math.hypot(node[0] - x, node[1] - y)
        if node == target:
            if distance < 16 and abs(z - target[2]) <= LEVEL:
                return Trial("arrived", walls, seconds, pos)
        elif distance < 112 and world.arrival_ready(pos, elbow, target, floor_test):
            if distance < 48 or (
                abs(target[2] - z) < 48 and not world.drop_ahead(pos, target)
                and world.clear_line((x, y, z + 15), (target[0], target[1], target[2] + 15))
            ):
                node = target

        wish = math.atan2(node[1] - y, node[0] - x)
        delta = (wish - yaw + math.pi) % math.tau - math.pi
        yaw += max(-turn, min(turn, delta))
        current_speed = math.hypot(vx, vy)
        if current_speed > 1:
            edge_x = x + vx * 16 / current_speed
            edge_y = y + vy * 16 / current_speed
            feet = z - FEET
            edge = world.guard.trace_down(edge_x, edge_y, feet, feet - 34) is None
            loss = DT * max(current_speed, STOP_SPEED) * FRICTION * (2 if edge else 1)
            scale = max(0, current_speed - loss) / current_speed
            vx, vy = vx * scale, vy * scale
        wx, wy = math.cos(yaw), math.sin(yaw)
        add = min(ACCELERATION * DT * MAX_SPEED, MAX_SPEED - vx * wx - vy * wy)
        if add > 0:
            vx, vy = vx + add * wx, vy + add * wy

        nx, ny = x + vx * DT, y + vy * DT
        height = world.ground_height(nx, ny, z)
        if height is None:
            if world.fits(nx, ny, z):
                return Trial("fell", walls, seconds + DT, (nx, ny, z))
            walls += 1
            height = world.ground_height(nx, y, z)
            if height is not None:
                ny, vy = y, 0
            else:
                height = world.ground_height(x, ny, z)
                if height is None:
                    return Trial("wall", walls, seconds + DT, pos)
                nx, vx = x, 0
        x, y, z = nx, ny, height
    return Trial("timeout", walls, 8, (x, y, z))


def trials(world, chain, back, floor_test=True):
    return [simulate(world, chain, offset, speed, back=back, floor_test=floor_test)
            for offset in LATERALS for speed in SPEEDS]


def score(results):
    return (sum(result.outcome != "arrived" for result in results),
            sum(result.wall_frames for result in results),
            sum(result.seconds for result in results))


def summarise(results):
    return {"outcomes": dict(Counter(result.outcome for result in results)),
            "wall_frames": sum(result.wall_frames for result in results),
            "seconds": round(sum(result.seconds for result in results), 3)}


def search(world, chain, back, radius, spacing):
    a, elbow, b = chain
    baseline = trials(world, chain, back)
    ranked = [(score(baseline), (0, 0), elbow, baseline)]
    seen = {(0, 0)}
    centres, reach = [(0, 0)], radius
    while True:
        offsets = sorted({
            (cx + dx, cy + dy) for cx, cy in centres
            for dx in range(-reach, reach + 1, spacing)
            for dy in range(-reach, reach + 1, spacing)
            if math.hypot(cx + dx, cy + dy) <= radius and (cx + dx, cy + dy) not in seen
        })
        for dx, dy in offsets:
            x, y = elbow[0] + dx, elbow[1] + dy
            z = world.ground_height(x, y, elbow[2])
            if z is None:
                continue
            point = (x, y, z)
            if min(math.dist(a, point), math.dist(b, point)) < 16 or not world.seat_ok(point):
                continue
            result = trials(world, (a, point, b), back)
            ranked.append((score(result), (dx, dy), point, result))
        ranked.sort(key=lambda row: (row[0], row[1]))
        if spacing <= 4:
            break
        seen.update(offsets)
        centres = [row[1] for row in ranked[:3]]
        reach, spacing = spacing, max(4, spacing // 2)
    _, _, best_point, best = ranked[0]
    return {"original": elbow, "seat": best_point,
            "before": summarise(baseline), "after": summarise(best)}


def level_corners(graph):
    nodes = graph["nodes"]
    typed = {(row[0], row[1]) for key in TYPED for row in graph.get(key, [])}
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for a, b, *_ in graph["links"]:
        if (a, b) in typed or abs(nodes[a][2] - nodes[b][2]) > LEVEL:
            continue
        incoming[b].add(a)
        outgoing[a].add(b)
    for elbow in sorted(incoming.keys() & outgoing.keys()):
        x, y, _ = nodes[elbow]
        for a in sorted(incoming[elbow]):
            dx, dy = x - nodes[a][0], y - nodes[a][1]
            for b in sorted(outgoing[elbow] - {a}):
                ex, ey = nodes[b][0] - x, nodes[b][1] - y
                length = math.hypot(dx, dy) * math.hypot(ex, ey)
                if length and dx * ex + dy * ey < length * math.cos(math.radians(15)):
                    yield a, elbow, b


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "search"):
        cmd = commands.add_parser(name)
        cmd.add_argument("map")
        cmd.add_argument("--graph", type=Path, help="use a different graph JSON")
        cmd.add_argument("--fwd", nargs=3, metavar=("FROM", "ELBOW", "TO"),
                         help="node indices, with an optional X before the elbow index")
        cmd.add_argument("--back", type=float, default=80, help="start this far short of the elbow")
        cmd.add_argument("--json", action="store_true")
    commands.choices["audit"].add_argument("--without-floor-test", action="store_true")
    commands.choices["search"].add_argument("--radius", type=int, default=96)
    commands.choices["search"].add_argument("--spacing", type=int, default=16)
    args = parser.parse_args(argv)
    map_name = args.map.lower()
    if not map_name.isascii() or not map_name.replace("_", "").isalnum():
        parser.error("map must contain only letters, numbers or underscores")
    if not math.isfinite(args.back) or args.back <= 0:
        parser.error("--back must be finite and positive")
    if args.command == "search" and (
        not 4 <= args.spacing <= args.radius <= 192 or args.radius % args.spacing
    ):
        parser.error("--radius must be a multiple of --spacing, up to 192, with spacing at least 4")
    try:
        bsp = bsp_path(ROOT, map_name)
        if bsp is None:
            raise FileNotFoundError(f"missing {map_name}.bsp (set ARGUS_MAPS)")
        world = World(Bsp(bsp))
        if args.command == "search" and not args.fwd and map_name == "dm3" and not args.graph:
            fixture = ROOT / "tools/fixtures/turnsim_dm3.json"
            corners = json.loads(fixture.read_text(encoding="utf-8"))
        else:
            graph_path = args.graph or ROOT / "src" / f"argus_nav_{map_name}.qc.json"
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            nodes = graph["nodes"]
            if args.fwd:
                a, elbow, b = args.fwd
                indices = [int(a), int(elbow.upper().removeprefix("X")), int(b)]
                if min(indices) < 0 or max(indices) >= len(nodes) or len(set(indices)) != 3:
                    parser.error("--fwd needs three distinct indices in the graph")
                turns = [indices]
            elif args.command == "audit":
                turns = level_corners(graph)
            else:
                parser.error("search needs --fwd outside the default dm3 fixture")
            corners = ({"nodes": indices, "points": [nodes[i] for i in indices]}
                       for indices in turns)
        rows = []
        checked = 0
        for corner in corners:
            chain = [tuple(point) for point in corner["points"]]
            checked += 1
            if args.command == "search":
                result = search(world, chain, args.back, args.radius, args.spacing)
            else:
                runs = trials(world, chain, args.back, not args.without_floor_test)
                result = summarise(runs)
                if args.fwd:
                    result["trials"] = [asdict(run) for run in runs]
                elif result["outcomes"] == {"arrived": len(runs)} and not result["wall_frames"]:
                    continue
            rows.append({"nodes": corner["nodes"], **result})
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        parser.exit(2, f"turnsim: {error}\n")
    if args.json:
        print(json.dumps({"map": map_name, "checked": checked, "corners": rows}, indent=2))
    else:
        print(f"{map_name}: simulated {checked} corners")
        for row in rows:
            route = " -> ".join(f"n{i}" for i in row["nodes"])
            if args.command == "search":
                print(f"  {route}: seat {row['seat']}; {row['before']} to {row['after']}")
            else:
                print(f"  {route}: {row['outcomes']}, {row['wall_frames']} wall frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
