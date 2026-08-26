#!/usr/bin/env python3
"""Directed-reach audit for SHIPPED nav graphs.

navgen's 7h gate (v3.70) prints directed reach at GENERATION time, so
graphs that predate it shipped unmeasured - the v3.70 handoff owes
reach numbers for dm4/dm3/dm6 to this day. This tool runs the same
BFS over the committed argus_nav_<map>.qc.json plus the BSP's spawn
points, so the number describes the graph bots actually run, not a
fresh regen.

Two figures per spawn, because the v3.69 dm2 storm hid behind the
first one:
  all      - every forward edge (walk/drop, jump, tele, RJ, lift,
             swim, train, sprint), navgen 7h semantics.
  ungated  - equipment-gated edges removed (rocket-jump needs
             RL+rocket+100 effective health, sprint links are skill
             3+). A spawn whose reach collapses without them is a
             sink for any bot that cannot pay the toll.

Usage: python tools/argus_reach.py [map ...]
       (default: every map with both maps_local/<map>.bsp and
        src/argus_nav_<map>.qc.json)

Exit code 1 when any spawn's all-edges reach is under 60% (the 7h
WARNING bar), so a rig script can gate on it.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WARN_PCT = 60


def bsp_spawns(path):
    data = path.read_bytes()
    (version,) = struct.unpack_from("<i", data, 0)
    if version != 29:
        raise SystemExit(f"{path}: BSP version {version}, expected 29")
    ofs, ln = struct.unpack_from("<ii", data, 4)  # lump 0 = entities
    text = data[ofs:ofs + ln].split(b"\0")[0].decode("latin-1")
    spawns = []
    for block in text.split("}"):
        if '"classname"' not in block:
            continue
        kv = {}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith('"'):
                parts = line.split('"')
                if len(parts) >= 5:
                    kv[parts[1]] = parts[3]
        if kv.get("classname") in ("info_player_deathmatch",
                                   "info_player_start"):
            o = kv.get("origin", "0 0 0").split()
            spawns.append(tuple(float(v) for v in o))
    return spawns


def load_graph(path):
    nav = json.loads(path.read_text())
    nodes = nav["nodes"]
    fwd_walk = [[] for _ in nodes]
    for entry in nav.get("links", []):
        i, j = entry[0], entry[1]
        fwd_walk[i].append(j)
    # typed hops every bot can take
    free = (nav.get("teles", []) + nav.get("liftlinks", [])
            + nav.get("swimlinks", []) + nav.get("trainlinks", []))
    # typed hops behind an equipment or skill gate
    gated = nav.get("rjlinks", []) + nav.get("sprintlinks", [])
    return nodes, fwd_walk, free, gated


def reach_from(start, fwd):
    seen = {start}
    q = [start]
    while q:
        u = q.pop()
        for v in fwd[u]:
            if v not in seen:
                seen.add(v)
                q.append(v)
    return len(seen)


def audit(mapname):
    bsp = ROOT / "maps_local" / f"{mapname}.bsp"
    navj = ROOT / "src" / f"argus_nav_{mapname}.qc.json"
    if not bsp.exists() or not navj.exists():
        print(f"{mapname}: skipped (need {bsp.name} and {navj.name})")
        return True
    nodes, walk, free, gated = load_graph(navj)
    fwd_all = [list(n) for n in walk]
    for a, b in free + gated:
        fwd_all[a].append(b)
    fwd_ungated = [list(n) for n in walk]
    for a, b in free:
        fwd_ungated[a].append(b)

    spawns = bsp_spawns(bsp)
    n = len(nodes)
    rows = []
    for o in spawns:
        best = min(range(n), key=lambda i: (nodes[i][0] - o[0]) ** 2
                   + (nodes[i][1] - o[1]) ** 2 + (nodes[i][2] - o[2]) ** 2)
        rows.append((reach_from(best, fwd_all),
                     reach_from(best, fwd_ungated), best, o))
    rows.sort()
    print(f"{mapname}: {n} nodes, {len(spawns)} spawns "
          f"(gated edges: {len(gated)})")
    ok = True
    for r_all, r_un, node, o in rows:
        pa = 100 * r_all // max(1, n)
        pu = 100 * r_un // max(1, n)
        mark = ""
        if pa < WARN_PCT:
            mark = "  << WARNING under 60%"
            ok = False
        elif pa - pu >= 20:
            mark = "  << gated-edge dependent"
        print(f"  spawn {o[0]:6.0f} {o[1]:6.0f} {o[2]:5.0f}  n{node:<4} "
              f"all {r_all}/{n} ({pa}%)  ungated {r_un}/{n} ({pu}%){mark}")
    worst = rows[0]
    print(f"  worst spawn: {100 * worst[0] // max(1, n)}% all, "
          f"{100 * worst[1] // max(1, n)}% ungated")
    return ok


def main():
    maps = sys.argv[1:]
    if not maps:
        maps = sorted(p.stem.replace("argus_nav_", "").replace(".qc", "")
                      for p in (ROOT / "src").glob("argus_nav_*.qc.json"))
    ok = True
    for m in maps:
        ok = audit(m) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
