"""Plan waypoint splices for level walks that fail the early-switch floor test."""
from collections import Counter, defaultdict
import math

from argus_floorlinks import LEVEL, failing_links, first_void
from argus_turnsim import LATERALS, SPEEDS, simulate

SEARCH_RADIUS = 72
SEARCH_STEP = 8
MIN_LEG = 16
APPROACHES = (0, *(offset for offset in LATERALS if offset))


def nearby_seats(world, start, end, samples):
    centre = [round(sum(point[i] for point in samples) / len(samples)) for i in range(3)]
    seats = set()
    for dx in range(-SEARCH_RADIUS, SEARCH_RADIUS + 1, SEARCH_STEP):
        for dy in range(-SEARCH_RADIUS, SEARCH_RADIUS + 1, SEARCH_STEP):
            if dx * dx + dy * dy > SEARCH_RADIUS ** 2:
                continue
            x, y = centre[0] + dx, centre[1] + dy
            z = world.ground_height(x, y, centre[2])
            if z is None:
                continue
            point = (x, y, round(z))
            if (max(abs(point[2] - start[2]), abs(point[2] - end[2])) <= LEVEL
                    and min(math.dist(start, point), math.dist(end, point)) >= MIN_LEG
                    and world.seat_ok(point)):
                seats.add(point)
    return sorted(seats, key=lambda p: (math.dist(start, p) + math.dist(p, end), p))


def elbow_passes(world, start, seat, end, walk_ok):
    legs = ((start, seat), (seat, end), (end, seat), (seat, start))
    if any(first_void(world.guard, a, b) is not None or not walk_ok(a, b) for a, b in legs):
        return False
    # Try the central approach first so most failed turns stop after one trial.
    return all(simulate(world, chain, lateral, speed).outcome == "arrived"
               for chain in ((start, seat, end), (end, seat, start))
               for lateral in APPROACHES
               for speed in SPEEDS)


def plan_elbows(world, graph, *, seat_ok, walk_ok, admits):
    """Return a coordinate splice and a reason for each original link left in place."""
    nodes = [tuple(p) for p in graph["nodes"]]
    # The JSON retains precision, while QC spawns the player at whole units.
    emitted = [tuple(round(v) for v in point) for point in nodes]
    origins = Counter(emitted)
    _, failed = failing_links(world.guard, graph)
    by_corner = defaultdict(list)
    for a, b, sample in failed:
        by_corner[tuple(sorted((a, b)))].append((a, b, sample))
    spec = {"seats": [], "walks": [], "cuts": []}
    unresolved = []
    for (a, b), directions in sorted(by_corner.items()):
        start, end = emitted[a], emitted[b]
        point = None
        if origins[start] != 1 or origins[end] != 1:
            reason = "ambiguous endpoint coordinates"
        elif not admits(len(nodes) + len(spec["seats"])):
            reason = "waypoint budget"
        elif not (world.seat_ok(start) and world.seat_ok(end)):
            reason = "unsupported or hazardous endpoint"
        else:
            reason = "no safe elbow in the search"
            samples = [sample for _, _, sample in directions]
            point = next((p for p in nearby_seats(world, start, end, samples)
                          if p not in origins
                          and seat_ok(p)
                          and elbow_passes(world, start, p, end, walk_ok)
                          and ((start, end) == (nodes[a], nodes[b])
                               or elbow_passes(world, nodes[a], p, nodes[b], walk_ok))), None)
        if point is None:
            unresolved.extend((src, dest, reason) for src, dest, _ in directions)
            continue
        origins[point] += 1
        spec["seats"].append(point)
        for src, dest, _ in directions:
            spec["cuts"].append((nodes[src], nodes[dest]))
            spec["walks"].extend(((nodes[src], point), (point, nodes[dest])))
    return spec, unresolved
