"""Read ordinary-session tactical evaluation ticks without claiming human feel."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from argus_tape import map_name, parse_tape

CHECK = re.compile(r"^TACTICCHECK (.+) t\s+([\d.]+) stage (\w+)$")
DIFFICULTY = re.compile(r"^ARGUS difficulty (.+) t\s+([\d.]+) base\s+([\d.-]+) cognition\s+([\d.-]+) aim\s+([\d.-]+) offset\s+([\d.-]+) drift\s+([\d.-]+) adaptive\s+(\d+) aimshare_pct\s+([\d.]+)$")


def review(text):
    tape = parse_tape(text)
    ticks = defaultdict(Counter)
    tiers = []
    for _, line in tape.lines:
        if match := CHECK.fullmatch(line.strip()):
            ticks[match[1]][match[3]] += 1
        if match := DIFFICULTY.fullmatch(line.strip()):
            tiers.append(dict(bot=match[1], t=float(match[2]), base=float(match[3]),
                              cognition=float(match[4]), aim=float(match[5]), offset=float(match[6]),
                              drift=float(match[7]), adaptive=bool(int(match[8])), aimshare_pct=float(match[9])))
    phases = defaultdict(Counter)
    for _, name, verb, rest in tape.events:
        if verb == 'tactic':
            phases[name][rest] += 1
    bots = {}
    for name in sorted(ticks.keys() | phases.keys()):
        stages = ticks.get(name)
        bots[name] = dict(evaluation_ticks=dict(stages) if stages else None,
                          phases=dict(phases[name]), return_hits=None)
    return dict(map=map_name('\n'.join(line for _, line in tape.lines)), bots=bots,
                difficulty=tiers,
                note='Evaluation ticks are throttled checks, not independent encounters. Tactic shots are attack acknowledgements; ordinary-session return hits and human feel are unmeasured.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.log.read_text(encoding='utf-8', errors='replace')), indent=2))
