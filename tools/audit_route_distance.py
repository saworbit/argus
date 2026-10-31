"""Compare shipped first-found routes with shortest distances, without tapes.

Reads link order and the eight-link capacity from generated QC. The dry,
skill-2, no-rocket profile applies the runtime jump-apex gate. Keyed doors
and transient avoid spots require engine fixtures rather than this audit.
"""
import argparse
from collections import deque
import heapq
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
MAPS = 'dm3,dm6,lqdm2,e1m1,e1m2,e1m5,e1m6,e1m7'


def graph(map_name, gravity=800):
    data = json.loads((ROOT / f'src/argus_nav_{map_name}.qc.json').read_text())
    points = data['nodes']
    links = [[] for _ in points]
    slots = [0] * len(points)
    source = (ROOT / 'src/argus.qc').read_text()
    jump_velocity = float(re.search(r'float AR_JUMPVEL\s*=\s*([\d.]+);', source)[1])
    apex = jump_velocity ** 2 / (2 * gravity)
    qc = (ROOT / f'src/argus_nav_{map_name}.qc').read_text()
    for kind, source, target in re.findall(r'Argus_NavLink(\w*) \(n(\d+), n(\d+)', qc):
        a, b = int(source), int(target)
        slots[a] += 1
        assert slots[a] <= 8, f'{map_name}: overflow at {a}'
        if kind == 'Rocket':
            continue
        if kind == 'Jump' and points[b][2] - points[a][2] > apex:
            continue
        links[a].append((b, math.dist(points[a], points[b])))
    return links


def first_found(links, start):
    distances = {start: 0}
    queue = deque([start])
    while queue:
        a = queue.popleft()
        for b, length in links[a]:
            if b not in distances:
                distances[b] = distances[a] + length
                queue.append(b)
    return distances


def shortest(links, start, objective='hops-distance'):
    scores = {start: (0, 0)}
    queue = [(0, 0, start)]
    while queue:
        first, second, a = heapq.heappop(queue)
        hops, distance = (first, second) if objective == 'hops-distance' else (second, first)
        if (hops, distance) != scores[a]:
            continue
        for b, length in links[a]:
            candidate = (hops + 1, distance + length)
            old = scores.get(b, (math.inf, math.inf))
            if (candidate if objective == 'hops-distance' else candidate[::-1]) < (
                    old if objective == 'hops-distance' else old[::-1]):
                scores[b] = candidate
                priority = candidate if objective == 'hops-distance' else candidate[::-1]
                heapq.heappush(queue, (*priority, b))
    return {node: score[1] for node, score in scores.items()}


def relaxed(links, start, objective='hops-distance'):
    """Independent queue model checked against the priority-queue oracle."""
    distances = {start: 0}
    hops = {start: 0}
    queue = deque([start])
    queued = {start}
    pops = 0
    while queue:
        a = queue.popleft()
        queued.remove(a)
        pops += 1
        for b, length in links[a]:
            candidate = distances[a] + length
            proposed = (hops[a] + 1, candidate)
            old = (hops.get(b, math.inf), distances.get(b, math.inf))
            if b != a and (proposed if objective == 'hops-distance' else proposed[::-1]) < (
                    old if objective == 'hops-distance' else old[::-1]):
                distances[b] = candidate
                hops[b] = hops[a] + 1
                if b not in queued:
                    queued.add(b)
                    queue.append(b)
        assert pops <= len(links) ** 2, 'queue failed to settle'
    return distances, pops


def audit(map_name, gravity=800, objective='hops-distance'):
    links = graph(map_name, gravity)
    ratios = []
    pops = []
    worst = dict(ratio=0)
    for start in range(len(links)):
        old = first_found(links, start)
        oracle = shortest(links, start, objective)
        candidate, expanded = relaxed(links, start, objective)
        assert candidate.keys() == oracle.keys() == old.keys()
        assert all(abs(candidate[b] - distance) < .001 for b, distance in oracle.items())
        pops.append(expanded)
        for target, distance in old.items():
            if target == start or oracle[target] == 0:
                continue
            ratio = distance / oracle[target]
            ratios.append(ratio)
            if ratio > worst['ratio']:
                worst = dict(ratio=ratio, start=start, target=target,
                             first_distance=distance, shortest_distance=oracle[target])
    return dict(map=map_name, objective=objective, nodes=len(links), pairs=len(ratios),
                median_excess_pct=(statistics.median(ratios) - 1) * 100,
                over25pct=sum(r > 1.25 for r in ratios), worst=worst,
                max_queue_pops=max(pops), median_queue_pops=statistics.median(pops),
                oracle_matches=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps', default=MAPS)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--gravity', type=float, default=800)
    parser.add_argument('--objective', choices=('hops-distance', 'distance'), default='hops-distance')
    args = parser.parse_args()
    assert args.gravity > 0
    rows = [audit(m, args.gravity, args.objective) for m in args.maps.split(',')]
    text = json.dumps(rows, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
