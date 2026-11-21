"""Measure accepted pickups, self-damage and host frame work on retained tapes."""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import statistics

from argus_tape import deaths, parse_tape, track_names

HOST_SPEEDS = re.compile(r"^\s*(\d+) tot\s+(\d+) server\s+\d+ gfx\s+\d+ snd$")
LEARNED_LINK = re.compile(r"^ARGUS live link ([0-7]) ")
GRAPH = re.compile(r"^ARGUS live graph nodes (\d+) allocated_edicts (\d+)$")
MAJORS = ("ra", "ya", "mh", "rl", "lg", "quad", "pent")
LINKS = ("walk", "jump", "drop", "portal", "plat", "train", "door", "swim")


def measure(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    tape = parse_tape(text)
    bots, _, _ = track_names(tape.samples, tape.events)
    assignments = [(line, actor, payload) for line, actor, verb, payload in tape.events
                   if verb == "arm" and actor in bots]
    arms = {actor: payload for _, actor, payload in assignments}
    start = max((line for line, _, _ in assignments), default=0)
    ledgers = defaultdict(Counter)
    handles = set(bots)
    for line, actor, verb, payload in tape.events:
        if line <= start or actor not in handles:
            continue
        arm = arms.get(actor, "bots")
        if verb == "major_pickup_v1" and payload in MAJORS:
            ledgers[arm][payload] += 1
        if verb == "self_damage_v1":
            ledgers[arm]["self_damage_hp"] += float(payload)
        if verb in ("momentum", "contest"):
            ledgers[arm][verb] += 1
    for line, victim, killer, *_ in deaths(tape.events):
        if line <= start:
            continue
        if victim in handles:
            ledgers[arms.get(victim, "bots")]["deaths"] += 1
        if killer in handles and victim != killer:
            ledgers[arms.get(killer, "bots")]["kills"] += 1

    links = Counter()
    server_ms = []
    active = False
    nodes = []
    for _, line in tape.lines:
        if line.strip() == "Server spawned.":
            active = True
        if match := LEARNED_LINK.match(line):
            links[LINKS[int(match[1])]] += 1
        if match := GRAPH.match(line):
            nodes.append((int(match[1]), int(match[2])))
        if active and (match := HOST_SPEEDS.match(line)):
            server_ms.append(int(match[2]))
    server_ms.sort()
    profiling = None
    if server_ms:
        profiling = dict(samples=len(server_ms), mean_ms=statistics.fmean(server_ms),
                         p95_ms=server_ms[math.ceil(0.95 * len(server_ms)) - 1],
                         max_ms=server_ms[-1])
    instrumented = "ARGUS duel_metrics v1" in text
    groups = {}
    totals = {key: sum(ledger[key] for ledger in ledgers.values()) for key in MAJORS}
    for arm in set(arms.values()) or {"bots"}:
        ledger = ledgers[arm]
        groups[arm] = dict(kills=ledger["kills"], deaths=ledger["deaths"],
                           self_damage_hp=ledger["self_damage_hp"] if instrumented else None,
                           momentum=ledger["momentum"], contest=ledger["contest"],
                           major_pickups={key: ledger[key] for key in MAJORS} if instrumented else None,
                           major_share_pct={
                               key: 100 * ledger[key] / totals[key] if totals[key] else None
                               for key in MAJORS
                           } if instrumented and arms else None)
    return dict(tape=path.stem, arms=groups, link_witnesses=dict(links), graph_samples=nodes,
                server_frames=profiling)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tapes", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps([measure(tape) for tape in args.tapes], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
