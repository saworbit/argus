#!/usr/bin/env python3
"""Decide whether a generated deathmatch graph is ready to register.

The verdict joins two claims which stay deliberately separate:

* every deathmatch spawn can route to every live pickup in the BSP;
* the current graph has a short engine probe for ordinary and jump links.

Usage: python tools/argus_mapgate.py map.bsp nav.qc.json [probe.json]
"""
from dataclasses import dataclass
import hashlib
import json
import struct
import sys
from pathlib import Path


SPAWN_MAX_U = 200
ITEM_MAX_U = 200
SPAWNFLAG_NOT_DEATHMATCH = 2048


def _distance(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def _parse_entities(path):
    data = Path(path).read_bytes()
    if len(data) < 4 + 15 * 8:
        raise ValueError(f"{path}: file is too small for a BSP29 header")
    (version,) = struct.unpack_from("<i", data, 0)
    if version != 29:
        raise ValueError(f"{path}: BSP version {version}, expected 29")
    offset, length = struct.unpack_from("<ii", data, 4)
    if offset < 0 or length < 0 or offset + length > len(data):
        raise ValueError(f"{path}: invalid entity lump")
    text = data[offset:offset + length].split(b"\0")[0].decode("latin-1")
    entities = []
    for block in text.split("}"):
        values = {}
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith('"'):
                continue
            parts = line.split('"')
            if len(parts) >= 5:
                values[parts[1]] = parts[3]
        if values:
            entities.append(values)
    return entities


def _origin(entity):
    raw = entity.get("origin")
    if not raw:
        return None
    try:
        values = [float(value) for value in raw.split()]
    except ValueError:
        return None
    return tuple(values) if len(values) == 3 else None


def _is_pickup(classname):
    return (
        classname.startswith("weapon_")
        or classname.startswith("item_armor")
        or classname == "item_health"
        or classname == "item_artifact_super_health"
        or classname.startswith("item_artifact_")
        or classname in ("item_shells", "item_spikes", "item_rockets", "item_cells")
    )


def _graph_edges(graph):
    count = len(graph.get("nodes", []))
    edges = [[] for _ in range(count)]
    families = (
        "links", "teles", "liftlinks", "swimlinks", "trainlinks",
        "rjlinks", "sprintlinks",
    )
    for family in families:
        for link in graph.get(family, []):
            if len(link) < 2:
                continue
            source, target = int(link[0]), int(link[1])
            if 0 <= source < count and 0 <= target < count:
                edges[source].append(target)
    return edges


def _reachable(start, edges):
    seen = {start}
    pending = [start]
    while pending:
        source = pending.pop()
        for target in edges[source]:
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def _nearest(nodes, point):
    if not nodes:
        return None, float("inf")
    index = min(range(len(nodes)), key=lambda i: _distance(nodes[i], point))
    return index, _distance(nodes[index], point)


def graph_md5(path):
    return hashlib.md5(Path(path).read_bytes(), usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class PlayabilityVerdict:
    playable: bool
    spawn_count: int
    item_count: int
    graph_md5: str
    reasons: tuple

    def line(self):
        status = "playable" if self.playable else "experimental"
        return (
            f"playability gate: status {status}; spawns {self.spawn_count}; "
            f"deathmatch pickups {self.item_count}; graph md5 {self.graph_md5}"
        )


def assess_playability(bsp_path, graph_path, probe_path=None):
    bsp_path = Path(bsp_path)
    graph_path = Path(graph_path)
    if probe_path is None:
        name = graph_path.name.replace(".qc.json", ".probe.json")
        probe_path = graph_path.with_name(name)
    probe_path = Path(probe_path)

    graph = json.loads(graph_path.read_text())
    nodes = graph.get("nodes", [])
    digest = graph_md5(graph_path)
    entities = _parse_entities(bsp_path)
    spawns = []
    items = []
    for entity in entities:
        classname = entity.get("classname", "")
        point = _origin(entity)
        if point is None:
            continue
        if classname in ("info_player_deathmatch", "info_player_start"):
            spawns.append((classname, point))
            continue
        try:
            spawnflags = int(float(entity.get("spawnflags", "0") or 0))
        except ValueError:
            spawnflags = 0
        if (_is_pickup(classname)
                and not spawnflags & SPAWNFLAG_NOT_DEATHMATCH):
            items.append((classname, point))

    reasons = []
    if not nodes:
        reasons.append("the generated graph has no nodes")
    if not spawns:
        reasons.append("the BSP has no deathmatch spawn")
    edges = _graph_edges(graph)
    item_nodes = []
    for classname, point in items:
        node, distance = _nearest(nodes, point)
        item_nodes.append((classname, node))
        if distance > ITEM_MAX_U:
            reasons.append(
                f"{classname} at {point[0]:.0f} {point[1]:.0f} {point[2]:.0f} "
                f"is {distance:.0f}u from the graph"
            )
    for _, point in spawns:
        node, distance = _nearest(nodes, point)
        if node is None:
            continue
        if distance > SPAWN_MAX_U:
            reasons.append(
                f"spawn at {point[0]:.0f} {point[1]:.0f} {point[2]:.0f} "
                f"is {distance:.0f}u from the graph"
            )
        seen = _reachable(node, edges)
        for classname, item_node in item_nodes:
            if item_node is not None and item_node not in seen:
                reasons.append(
                    f"spawn at {point[0]:.0f} {point[1]:.0f} {point[2]:.0f} "
                    f"cannot reach {classname} at node {item_node}"
                )

    if not probe_path.is_file():
        reasons.append("the current graph has no mill verdict")
    else:
        try:
            probe = json.loads(probe_path.read_text())
        except (OSError, json.JSONDecodeError):
            probe = {}
        verification = probe.get("verification", {})
        if str(verification.get("graph_md5", "")).lower() != digest.lower():
            reasons.append("the mill verdict belongs to a different graph")
        deathmatch = verification.get("deathmatch", {})
        jump_pairs = {tuple(link[:2]) for link in graph.get("jlinks", [])}
        door_pairs = {tuple(link[:2]) for link in graph.get("doorlinks", [])}
        walk_count = sum(
            1 for link in graph.get("links", [])
            if tuple(link[:2]) not in jump_pairs and tuple(link[:2]) not in door_pairs
        )
        required = []
        if walk_count:
            required.append(("walk", "ordinary links have no current mill pass"))
        if jump_pairs:
            required.append(("jump", "jump links have no current mill pass"))
        if not required:
            reasons.append("the graph has no link class the mill can verify")
        for kind, missing in required:
            evidence = deathmatch.get(kind, {})
            swept = int(evidence.get("swept", 0) or 0)
            failed = int(evidence.get("failed", 0) or 0)
            teleports = int(evidence.get("teleport_failures", 0) or 0)
            if swept <= 0:
                reasons.append(missing)
            elif failed:
                reasons.append(f"the {kind} mill pass refused {failed} link(s)")
            elif teleports:
                reasons.append(
                    f"the {kind} mill pass could not place the puppet for "
                    f"{teleports} link(s)"
                )

    unique_reasons = tuple(dict.fromkeys(reasons))
    return PlayabilityVerdict(
        playable=not unique_reasons,
        spawn_count=len(spawns),
        item_count=len(items),
        graph_md5=digest,
        reasons=unique_reasons,
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (2, 3) or any(arg in ("-h", "--help") for arg in argv):
        print(__doc__.strip())
        return 0 if any(arg in ("-h", "--help") for arg in argv) else 1
    verdict = assess_playability(*argv)
    print(verdict.line())
    for reason in verdict.reasons:
        print(f"  {reason}")
    return 0 if verdict.playable else 1


if __name__ == "__main__":
    sys.exit(main())
