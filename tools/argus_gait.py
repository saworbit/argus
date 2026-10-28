#!/usr/bin/env python3
"""Attribute stationary windows to deliberate hesitation, or to something else.

The gait work adds chosen pauses, which is the one behaviour this project
treats as a hard failure when it goes wrong: a bot standing still while
something shoots it. Neither existing instrument answers the question on its
own. The humanness distance scores pause-length distributions and is
perfectly happy with a statue. The tape brief counts freezes without saying
what caused them, and dm4 produces long ones on unchanged code - the control
arm of this very ladder carried an 11.8 s one.

So this reads the two together. Freeze windows come from the shared
tools/argus_tape.freeze_windows, which is aligned with MatchTape::freezes in
the Rust gate, and each one is attributed to a hesitation only when that
bot's own marker sits just before it. A window with no marker near it is the
pre-existing wedge class; a window that follows a marker belongs to the gait
and has to fit inside what a hesitation is allowed to hold.

Exit status is 1 when an attributable window lost health or outlived the
hold, so this can gate a ladder.

Examples:
  python tools/argus_gait.py runs/gaitA_dm4_*.log
  python tools/argus_gait.py --format json runs/cand.log
"""

import argparse
import glob
import json
import re
import statistics
from pathlib import Path

from argus_tape import freeze_windows, roles, sample_row

# "ARGUS <netname> hesitate <cause>" sits outside the closed ARGEVT verb set
# by design, like shove and sprintjump. Netnames may contain spaces, so this
# anchors on the keyword rather than on whitespace counts (the v3.37 lesson).
MARKER = re.compile(r"ARGUS (.+?) hesitate (heard|junction|settle)\s*$")


def read_tape(path):
    """Bot tracks and hesitation markers on one reconstructed clock.

    Marker lines carry no timestamp of their own, so each takes the time of
    the most recent telemetry row. Rows arrive twice a second per bot, which
    is far finer than the attribution window below.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    bots = set(roles(text)["bots"])
    tracks = {}
    markers = []
    clock = 0.0
    for lineno, line in enumerate(text.splitlines(), 1):
        row = sample_row(line, lineno)
        if row is not None:
            name, sample = row
            clock = sample["t"]
            tracks.setdefault(name, []).append(sample)
            continue
        mark = MARKER.search(line.rstrip())
        if mark:
            markers.append({"t": clock, "name": mark[1], "cause": mark[2]})
    # Human and instrument tracks are not this change's subject, and a human
    # standing still is signal rather than a defect.
    tracks = {name: rows for name, rows in tracks.items() if name in bots} or tracks
    return tracks, markers


def audit(path, max_hold, attribute_sec):
    tracks, markers = read_tape(path)
    causes = {}
    for mark in markers:
        causes[mark["cause"]] = causes.get(mark["cause"], 0) + 1
    findings = []
    for name, rows in tracks.items():
        own = [mark["t"] for mark in markers if mark["name"] == name]
        for window in freeze_windows(rows):
            attributed = any(
                -0.5 <= window.start["t"] - mark <= attribute_sec for mark in own
            )
            findings.append(
                {
                    "bot": name,
                    "start": round(window.start["t"], 1),
                    "seconds": round(window.dur, 1),
                    "hp_lost": round(window.hp_drop, 0),
                    "pos": [
                        round(window.start["x"], 1),
                        round(window.start["y"], 1),
                        round(window.start["z"], 1),
                    ],
                    "mode": window.start["mode"],
                    "hesitation": attributed,
                    "verdict": _verdict(window, attributed, max_hold),
                }
            )
    findings.sort(key=lambda row: row["start"])
    return {
        "file": Path(path).name,
        "tracks": len(tracks),
        "hesitations": len(markers),
        "causes": causes,
        "per_bot": round(len(markers) / len(tracks), 2) if tracks else 0.0,
        "freezes": len(findings),
        "findings": findings,
        "failures": sum(1 for row in findings if row["verdict"] == "FAIL"),
    }


def _verdict(window, attributed, max_hold):
    if not attributed:
        return "pre-existing"
    if window.hp_drop > 0:
        return "FAIL"
    if window.dur > max_hold:
        return "FAIL"
    return "within hold"


def expand(patterns):
    paths = []
    for pattern in patterns:
        paths.extend(sorted(glob.glob(pattern)) or [pattern])
    return [path for path in paths if Path(path).is_file()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", help="telemetry tapes or glob patterns")
    parser.add_argument(
        "--max-hold",
        type=float,
        default=8.0,
        help="longest freeze one hesitation may account for; a hesitation "
        "window plus its brake cannot reach this (default 8.0)",
    )
    parser.add_argument(
        "--attribute-sec",
        type=float,
        default=4.0,
        help="how long after a marker a window may still be attributed to it",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    paths = expand(args.logs)
    if not paths:
        parser.error("no tapes matched")
    reports = [audit(path, args.max_hold, args.attribute_sec) for path in paths]

    if args.format == "json":
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        for report in reports:
            causes = ", ".join(f"{k} {v}" for k, v in sorted(report["causes"].items()))
            print(
                f"{report['file']}: hesitations {report['hesitations']}"
                f" ({report['per_bot']}/bot{': ' + causes if causes else ''});"
                f" freezes {report['freezes']}"
            )
            for row in report["findings"]:
                print(
                    f"    {row['verdict']:<12} {row['bot']:<10} t={row['start']:>7.1f}"
                    f" {row['seconds']:>5.1f}s hp_lost={row['hp_lost']:>4.0f}"
                    f" mode={row['mode']} at {row['pos']}"
                )
        if len(reports) > 1:
            print(
                f"-- {len(reports)} tapes: hesitations median "
                f"{statistics.median(r['hesitations'] for r in reports):.0f},"
                f" freezes median {statistics.median(r['freezes'] for r in reports):.0f},"
                f" attributable failures {sum(r['failures'] for r in reports)}"
            )
    return 1 if any(report["failures"] for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
