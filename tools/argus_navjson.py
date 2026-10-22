"""Shared navigation families and directed edges, matching nav_graph.rs."""
import json
from pathlib import Path

WALK = ("links", "jlinks")
FREE = ("teles", "liftlinks", "swimlinks", "doorlinks", "trainlinks")
GATED = ("rjlinks", "sprintlinks")
FAMILIES = WALK + FREE + GATED


def normalize_nav(nav):
    """Copy a graph with object and array nodes represented as origin arrays."""
    return {**nav, "nodes": [
        node["origin"] if isinstance(node, dict) else node
        for node in nav.get("nodes", [])
    ]}


def load_nav(path):
    """Read UTF-8 navigation JSON and normalize its node representation."""
    return normalize_nav(json.loads(Path(path).read_text(encoding="utf-8")))


def pairs(nav, families):
    """Yield in-range pairs; reject endpoint types that cannot name a node."""
    count = len(nav.get("nodes", []))
    for family in families:
        for link in nav.get(family, []):
            if len(link) >= 2:
                source, target = link[:2]
                if type(source) is not int or type(target) is not int:
                    raise ValueError(f'{family}: link endpoints must be integers')
                if 0 <= source < count and 0 <= target < count:
                    yield source, target


def edges(nav, gated=False):
    """Walk ordinary/free hops; opt in to equipment and skill gates.

    A typed gated pair stays gated even when also listed in links.
    """
    blocked = set() if gated else set(pairs(nav, GATED))
    seen = set()
    for pair in pairs(nav, FAMILIES if gated else WALK + FREE):
        if pair not in blocked and pair not in seen:
            seen.add(pair)
            yield pair
