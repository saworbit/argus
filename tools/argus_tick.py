#!/usr/bin/env python3
"""Recover the server tick rate a tape ran at from its telemetry cadence.

usage:
  argus_tick.py <log> [<log> ...]          one line per tape
  argus_tick.py --all                      every runs/*.log, mtime order

Argus_Telemetry fires on the first frame after ar_nextlog = time + 0.5, so
the gap between consecutive ARGLOG rows of one bot is 0.5 plus however much
of a frame is needed to cross that line: n * dt with n = floor(0.5 / dt) + 1.
The t field prints to one decimal, so the gaps that reach a tape are a
two-point mixture of 0.5 and 0.6 and the MEAN carries the rate in the
fraction of 0.6s: 7 per cent at 70 Hz, 15 per cent at 19 Hz, 32 per cent at
14.5 Hz. A median reads 0.5 for all three and is useless here.
Calibrated 2026-09-14 against two probes with host_speeds counting frames:

  dedicated, default sys_ticrate      19.3 frames/s   mean gap 0.5154
  dedicated, +sys_ticrate 0.0139      69.4 frames/s   mean gap 0.5053
  every human listen session          about 71 Hz     mean gap 0.506 to 0.509

Two lab clusters exist in runs/: 0.5145 to 0.5155 (about 19 Hz, a 1 ms
Windows timer) and 0.535 to 0.555 (about 14 to 15 Hz, the 15.6 ms timer:
four sleeps of 15.6 ms plus the frame's own work). No tape in the archive
reads 0.6, which is what a true 0.1 s frametime would produce; the v4.07
"frametime 0.1" finding was ftos rounding a 0.05 to 0.07 frame to one
decimal. Written for docs/plans/2026-09-14-regression-analysis-and-recovery.md.
"""
import re, sys, os, glob, statistics as st

PAT = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos")


def estimate(path):
    per = {}
    for line in open(path, errors='replace'):
        m = PAT.search(line)
        if m:
            per.setdefault(m.group(1), []).append(float(m.group(2)))
    inc = []
    for ts in per.values():
        for a, b in zip(ts, ts[1:]):
            d = b - a
            # never below 0.45: the true gap is n*dt with n chosen to
            # cross 0.5, so it cannot be shorter. Shorter ones are
            # ar_nextlog reset on respawn, and on ab_dm3_fourbot1 566
            # of them dragged the mean to 0.4877, below the floor.
            if 0.45 <= d < 0.75:
                inc.append(d)
    if len(inc) < 20:
        return None
    return st.mean(inc), len(inc)


def classify(mean_gap):
    if mean_gap < 0.5105:
        return 'about 70 Hz (listen rate)'
    if mean_gap < 0.522:
        return 'about 19 Hz (dedicated, 1 ms timer)'
    if mean_gap < 0.56:
        return 'about 14 to 15 Hz (dedicated, coarse timer)'
    return 'slower than 12 Hz'


if __name__ == '__main__':
    args = sys.argv[1:]
    if args[:1] == ['--all']:
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'runs')
        files = sorted(glob.glob(os.path.join(root, '*.log')), key=os.path.getmtime)
    else:
        files = args
    for p in files:
        r = estimate(p)
        if r:
            print(f"{os.path.basename(p):44} gap {r[0]:.4f}  n={r[1]:<5} {classify(r[0])}")
        else:
            print(f"{os.path.basename(p):44} too few samples")
