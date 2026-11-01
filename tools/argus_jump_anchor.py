"""The plain-jump launch must fit the runtime's three-dimensional anchor."""
import math

LIMIT = 96.0


def launch_distance(source, launch):
    # QC emits integer node origins. Measure against the seat actually loaded.
    seat = tuple(float(f'{v:.0f}') for v in source)
    return math.dist(seat, launch)


def require_anchor(source, launch):
    distance = launch_distance(source, launch)
    if not math.isfinite(distance) or distance >= LIMIT:
        raise ValueError(f'jump launch is {distance:.3f}u from its source; runtime requires < {LIMIT:.0f}u; re-seat the link')
    return distance


def audit(nodes, jumps, gap_points):
    rows = []
    for source, target in sorted(jumps):
        gap = gap_points(nodes[source], nodes[target])
        if gap is None:
            rows.append(dict(source=source, target=target, profile='direct_or_fallback', launch_distance=None, admissible=None))
        else:
            launch = gap[0]
            distance = launch_distance(nodes[source], launch)
            rows.append(dict(source=source, target=target, profile='gap', launch=list(launch),
                             launch_distance=distance, admissible=math.isfinite(distance) and distance < LIMIT))
    return dict(anchor_limit=LIMIT, jumps=len(rows), profiled=sum(row['profile']=='gap' for row in rows),
                direct_or_fallback=sum(row['profile']=='direct_or_fallback' for row in rows),
                violations=[row for row in rows if row['admissible'] is False], links=rows)
