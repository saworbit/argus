"""Pure tactical annotations for an Argus waypoint graph.

The BSP-specific visibility probe stays in argus_navgen.py.  This module owns
the graph part so the shortest hidden target and its first hop can be tested
without constructing a BSP fixture.
"""

import heapq
import math


def compute_tactics(nodes, adjacency, visible):
    """Return per-node exposure counts and nearest hidden walk targets.

    ``visible[a][b]`` is a symmetric, static-world visibility matrix.
    ``adjacency`` contains only ordinary walk links because combat steering
    cannot safely execute a jump, teleporter, mover, swim, or door protocol.
    Each cover row is ``[target, first_hop]`` or ``[-1, -1]`` when no hidden
    node is reachable.
    """
    count = len(nodes)
    if len(adjacency) != count or len(visible) != count:
        raise ValueError("tactical inputs must have one row per node")
    if any(len(row) != count for row in visible):
        raise ValueError("visibility matrix must be square")

    exposure = [
        sum(1 for other in range(count) if other != node and visible[node][other])
        for node in range(count)
    ]
    cover = []
    for start in range(count):
        dist = [math.inf] * count
        first = [-1] * count
        dist[start] = 0.0
        queue = [(0.0, start)]
        best = -1
        while queue:
            walked, node = heapq.heappop(queue)
            if walked != dist[node]:
                continue
            if node != start and not visible[start][node]:
                best = node
                break
            for nxt in adjacency[node]:
                if nxt < 0 or nxt >= count:
                    raise ValueError("tactical adjacency contains an invalid node")
                a = nodes[node]
                b = nodes[nxt]
                step = math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))
                candidate = walked + step
                hop = nxt if node == start else first[node]
                if (candidate < dist[nxt]
                        or (candidate == dist[nxt]
                            and (first[nxt] < 0 or hop < first[nxt]))):
                    dist[nxt] = candidate
                    first[nxt] = hop
                    heapq.heappush(queue, (candidate, nxt))
        cover.append([best, first[best] if best >= 0 else -1])
    return exposure, cover
