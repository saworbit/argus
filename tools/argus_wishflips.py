#!/usr/bin/env python3
"""argus_wishflips.py - runs of per-frame wish flips in full-rate ARGMOT tapes.

The reversal measure (#697) counts turns of more than 120 degrees in travel
direction at over 120 u/s, so it cannot see a bot whose wish heading flips
on every frame while it barely moves (#754): the combat hazard block
re-chooses a strafe side every frame whenever the heading it refuses is not
the strafe heading. This reads consecutive ARGMOT rows per bot (the tape
needs `scratch1 697`) and counts runs of three or more adjacent frames whose
wish changes by more than 100 degrees from the previous frame, with how long
each run lasted and how far the bot moved during it.

usage:
  python tools/argus_wishflips.py TAPE.log [TAPE.log ...] [--json] [--min-run N] [--degrees D]

Exit 0 on success, 2 when a tape is missing or carries no ARGMOT rows.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from argus_guard_replica import read_tape  # noqa: E402 - tools path set just above


def angle_change(a, b):
    """Smallest absolute difference between two headings in degrees."""
    return abs((b - a + 180.0) % 360.0 - 180.0)


def flip_runs(rows, degrees=100.0, min_run=3):
    """Runs of at least min_run consecutive frames whose wish moved more than degrees.

    rows are read_tape's (ms, x, y, z, wish, cause, mode, onground) tuples for
    one bot. A run counts frames, so three flips span four rows.
    """
    runs, start = [], None
    for k in range(1, len(rows) + 1):
        flipped = k < len(rows) and angle_change(rows[k - 1][4], rows[k][4]) > degrees
        if flipped and start is None:
            start = k - 1
        elif not flipped and start is not None:
            flips = k - 1 - start
            if flips >= min_run:
                a, b = rows[start], rows[k - 1]
                runs.append({"t": round(a[0] / 1000.0, 2), "flips": flips,
                             "seconds": round((b[0] - a[0]) / 1000.0, 2),
                             "moved": round(math.dist(a[1:4], b[1:4]), 1),
                             "wish": [round(r[4], 1) for r in rows[start:start + 4]]})
            start = None
    return runs


def scan(path, degrees=100.0, min_run=3):
    bots = read_tape(path)
    report = {"tape": str(path), "bots": {}, "runs": 0, "flip_frames": 0, "seconds": 0.0}
    for name, rows in sorted(bots.items()):
        runs = flip_runs(rows, degrees, min_run)
        report["bots"][name] = runs
        report["runs"] += len(runs)
        report["flip_frames"] += sum(r["flips"] for r in runs)
        report["seconds"] = round(report["seconds"] + sum(r["seconds"] for r in runs), 2)
    return report, bool(bots)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    opts = {"--min-run": 3, "--degrees": 100.0}
    for flag in list(opts):
        if flag in args:
            i = args.index(flag)
            try:
                opts[flag] = type(opts[flag])(args[i + 1])
            except (IndexError, ValueError):
                print(f"{flag} needs a number", file=sys.stderr)
                return 2
            del args[i:i + 2]
    missing = [a for a in args if not Path(a).is_file()]
    if missing:
        print("missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    reports = []
    for tape in args:
        report, had_rows = scan(tape, opts["--degrees"], opts["--min-run"])
        if not had_rows:
            print(f"{tape}: no ARGMOT rows (record with scratch1 697)", file=sys.stderr)
            return 2
        reports.append(report)
    if as_json:
        print(json.dumps(reports, indent=2))
        return 0
    for r in reports:
        print(f"{r['tape']}: {r['runs']} run(s) of {opts['--min-run']}+ per-frame wish flips over "
              f"{opts['--degrees']:g} degrees, {r['flip_frames']} flips, {r['seconds']} s")
        for name, runs in r["bots"].items():
            for run in runs:
                print(f"  {name} t {run['t']}: {run['flips']} flips in {run['seconds']} s, "
                      f"moved {run['moved']}u, wish {run['wish']}")
    total = sum(r["runs"] for r in reports)
    print(f"total: {total} run(s) on {len(reports)} tape(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
