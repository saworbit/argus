#!/usr/bin/env python3
"""Argus tape review battery: the checks every playtest and A/B tape
gets, in one tool. Spaced-name-safe (anchors on grammar keywords,
never whitespace counts - the v3.37 lesson).

usage:
  argus_review.py summary <log>              event counts, first goal,
                                             per-bot finals, freezes
  argus_review.py deaths <log>               every death + the victim's
                                             last 14 telemetry samples
  argus_review.py region <log> <bot|all> <x0> <x1> <y0> <y1>
                                             trace bots inside a rect,
                                             with interleaved events
  argus_review.py rides <log>                train events, east-deck
                                             crossings, bridge falls
                                             (dm2 geometry)

The freeze detector flags any bot below 20 u/s within a 24u cell for
6+ seconds - the signature of every stuck-bot defect found so far
(grate pin, pocket jitter hold, dead-lift statue, door-button wait).
"""
import re, sys, collections

PAT = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+) mode\s+(\d) st\s+(\d+) gl\s+(\d+)(?: hp\s+(-?[\d.]+) frg\s+(-?\d+))?")
# the event keyword must be matched from the closed vocabulary: a lazy
# (.+?) name followed by \w+ would split a spaced netname at its last
# word ("Joe" + event "Rogan")
EVT = re.compile(r"ARGEVT (.+?) (spawned|respawn|goal|route|routefail|"
                 r"trapped|abandon|stall|stallnode|jump|rjump|lift|swim|"
                 r"door|train|hazard|engage|pursue|retreat|weapon|plan|"
                 r"death)\b(.*)")
DEATH = re.compile(r"ARGEVT (.+?) death\s+(?:(.+?)\s+)?pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'")


def parse(log):
    bots, events, deaths = collections.defaultdict(list), [], []
    lineno = 0
    for line in open(log, errors="replace"):
        lineno += 1
        m = PAT.search(line)
        if m:
            g = m.groups()
            bots[g[0]].append(dict(t=float(g[1]), x=float(g[2]), y=float(g[3]),
                z=float(g[4]), spd=float(g[5]), yaw=float(g[6]), mode=int(g[7]),
                st=int(g[8]), gl=int(g[9]),
                hp=float(g[10]) if g[10] else None,
                frg=int(g[11]) if g[11] else None, line=lineno))
            continue
        m = DEATH.search(line)
        if m:
            deaths.append((lineno, m.group(1), m.group(2) or "world",
                           float(m.group(3)), float(m.group(4)), float(m.group(5))))
        m = EVT.search(line)
        if m:
            events.append((lineno, m.group(1), m.group(2), m.group(3).strip()[:70]))
    return bots, events, deaths


def freezes(bots):
    out = []
    for n, recs in bots.items():
        i = 0
        while i < len(recs):
            j = i
            while (j + 1 < len(recs) and recs[j+1]["spd"] < 20
                   and abs(recs[j+1]["x"] - recs[i]["x"]) < 24
                   and abs(recs[j+1]["y"] - recs[i]["y"]) < 24):
                j += 1
            dur = recs[j]["t"] - recs[i]["t"]
            if dur >= 6.0:
                r = recs[i]
                out.append((n, r["t"], recs[j]["t"], dur, r["x"], r["y"], r["z"],
                            r["mode"], r["line"], recs[j]["line"]))
            i = j + 1 if j > i else i + 1
    return out


def cmd_summary(log):
    bots, events, deaths = parse(log)
    print("bots:", {n: len(r) for n, r in bots.items()})
    print("last t:", {n: round(r[-1]["t"], 1) for n, r in bots.items()})
    print("events:", dict(collections.Counter(e[2] for e in events).most_common()))
    first_goal = next((e for e in events if e[2] == "goal"), None)
    if first_goal:
        near = max((r["t"] for rr in bots.values() for r in rr
                    if r["line"] < first_goal[0]), default=0)
        print(f"first goal: t {near:.1f}  ({first_goal[1]}{first_goal[3]})")
    world = sum(1 for d in deaths if d[2] == "world")
    print(f"deaths {len(deaths)} (world {world})")
    for n, rr in bots.items():
        r = rr[-1]
        print(f"  {n}: st {r['st']} gl {r['gl']} frg {r['frg']} "
              f"ends '{r['x']:.0f} {r['y']:.0f} {r['z']:.0f}'")
    fz = freezes(bots)
    if fz:
        for n, t0, t1, dur, x, y, z, mode, l0, l1 in fz:
            print(f"FROZEN {n}: t {t0:.1f}..{t1:.1f} ({dur:.1f}s) at "
                  f"'{x:.0f} {y:.0f} {z:.0f}' mode {mode} lines {l0}..{l1}")
    else:
        print("no freezes (6s+ at <20 u/s)")


def cmd_deaths(log):
    bots, events, deaths = parse(log)
    for ln, v, k, x, y, z in deaths:
        print(f"L{ln}: {v} killed by {k} at '{x:.0f} {y:.0f} {z:.0f}'")
        trail = [r for r in bots.get(v, []) if r["line"] < ln][-14:]
        for r in trail:
            print(f"    t {r['t']:6.1f} '{r['x']:7.1f} {r['y']:8.1f} "
                  f"{r['z']:6.1f}' spd {r['spd']:6.1f} mode {r['mode']} st {r['st']}")


def cmd_region(log, who, x0, x1, y0, y1):
    bots, events, deaths = parse(log)
    evby = collections.defaultdict(list)
    for ln, n, ev, rest in events:
        evby[n].append((ln, ev, rest))
    for n, recs in bots.items():
        if who != "all" and n != who:
            continue
        inside = False
        shown = 0
        for i, r in enumerate(recs):
            now = x0 <= r["x"] <= x1 and y0 <= r["y"] <= y1
            if now:
                if not inside and shown:
                    print(f"--- {n} re-enters ---")
                print(f"{n} t {r['t']:6.1f} '{r['x']:7.1f} {r['y']:8.1f} "
                      f"{r['z']:6.1f}' spd {r['spd']:6.1f} yaw {r['yaw']:5.0f} "
                      f"mode {r['mode']} st {r['st']}")
                shown += 1
                nxt = recs[i+1]["line"] if i + 1 < len(recs) else 1 << 30
                for ln, ev, rest in evby[n]:
                    if r["line"] < ln < nxt:
                        print(f"    EVT {ev}{rest}")
            elif inside:
                print(f"{n} t {r['t']:6.1f} LEFT to "
                      f"'{r['x']:.0f} {r['y']:.0f} {r['z']:.0f}'")
            inside = now


def cmd_rides(log):
    bots, events, deaths = parse(log)
    trains = collections.Counter(e[1] for e in events if e[2] == "train")
    print("train events:", dict(trains) or "none")
    for name, tr in bots.items():
        west = False
        for t in tr:
            deck = 330 < t["z"] < 380 and -1150 < t["y"] < -950
            if deck and t["x"] < 1650:
                west = True
            elif deck and t["x"] > 1900 and west:
                print(f"CROSSING COMPLETE: {name} t {t['t']:.1f} "
                      f"'{t['x']:.0f} {t['y']:.0f} {t['z']:.0f}'")
                west = False
            elif (t["z"] < 200 and west and 1450 < t["x"] < 1900
                  and -1150 < t["y"] < -950):
                print(f"bridge fall: {name} t {t['t']:.1f} "
                      f"'{t['x']:.0f} {t['y']:.0f} {t['z']:.0f}'")
                west = False
            elif not deck and t["z"] < 300:
                west = False


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "summary":
        cmd_summary(sys.argv[2])
    elif cmd == "deaths":
        cmd_deaths(sys.argv[2])
    elif cmd == "region":
        cmd_region(sys.argv[2], sys.argv[3], *map(float, sys.argv[4:8]))
    elif cmd == "rides":
        cmd_rides(sys.argv[2])
    else:
        print(__doc__)
