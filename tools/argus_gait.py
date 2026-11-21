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
bot's own marker sits just before it. A window that follows a marker belongs
to the gait and has to fit inside what a hesitation is allowed to hold.

The controller has one other designed wait that prints no marker: the mover
hold. A lift or train hop parks the bot at its pad with ar_liftwait, friction
only and the stall detector suppressed, until the mover serves it or the hop's
deadline gives it up. A window that opens inside that bot's own hop is a
mover wait, reported with how the hop ended, so a bot standing at a lift that
never comes is not filed as a wedge (#628). Any other window with no marker
near it is the pre-existing wedge class.

Exit status is 1 when an attributable hesitation window lost health or
outlived the hold, so this can gate a ladder. Mover waits never fail the gate:
they are evidence about the mover controller, not about the gait.

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

from argus_tape import event_fields, freeze_windows, roles, sample_row

# "ARGUS <netname> hesitate <cause>" sits outside the closed ARGEVT verb set
# by design, like shove and sprintjump. Netnames may contain spaces, so this
# anchors on the keyword rather than on whitespace counts (the v3.37 lesson).
MARKER = re.compile(r"ARGUS (.+?) hesitate (heard|junction|settle)\s*$")

# Typed mover hops and the controller's outer bound on each, in seconds.
# src/argus.qc stamps ar_liftstart when the hop is planned at the mode-2
# advance and gives a lift hop up at ar_liftstart + 20 wherever the bot
# stands (8 s once it is waiting at the pad), and a train hop at + 15. No
# window that opens later can belong to the hop.
MOVER_HOPS = {"lift": 20.0, "train": 15.0}

# The bot's own verbs that end a hop: the give-ups, a new plan, a stall
# reset, a new life. A completed ride logs nothing at all, so a hop none of
# these closes stays open only until its bound.
MOVER_CLOSERS = frozenset(
    ("abandon", "routefail", "trapped", "stall", "route", "goal",
     "death", "respawn", "spawned")
)

# How long a window may run on past the hop that explains it: two telemetry
# rows, because a closing event takes the clock of the row before it. A
# window that outlives its hop by more is a mover overrun: the hold kept
# going after the controller's own bound or give-up should have ended it,
# which is a defect in its own right and is not hidden as a mover wait.
MOVER_SLACK = 1.0


def mover_hops(events, last=None):
    """Fold (t, name, verb) rows, in tape order, into one record per hop.

    Each record carries the bot, the hop verb, the clock it opened on, the
    clock it stopped holding (its closing event or its bound, whichever came
    first), the verb that closed it ("deadline" when nothing did in time,
    "tape end" when the tape stopped first; last is the tape's final clock)
    and whether the bot boarded before it closed.
    """
    open_hops, hops = {}, []

    def close(name, t, verb):
        hop = open_hops.pop(name)
        bound = hop["start"] + MOVER_HOPS[hop["verb"]]
        if t is not None and t <= bound:
            hop["end"], hop["close"] = t, verb
        elif t is None and last is not None and last < bound:
            hop["end"], hop["close"] = bound, "tape end"
        else:
            hop["end"], hop["close"] = bound, "deadline"
        hops.append(hop)

    for t, name, verb in events:
        if name in open_hops and (verb in MOVER_CLOSERS or verb in MOVER_HOPS):
            close(name, t, verb)
        if verb in MOVER_HOPS:
            open_hops[name] = {"name": name, "verb": verb, "start": t, "boarded": False}
        elif verb == "board" and name in open_hops:
            open_hops[name]["boarded"] = True
    for name in list(open_hops):
        close(name, None, None)
    hops.sort(key=lambda hop: hop["start"])
    return hops


def read_tape(path):
    """Bot tracks, hesitation markers and bot events on one reconstructed clock.

    Marker and event lines carry no timestamp of their own, so each takes the
    time of the most recent telemetry row. Rows arrive twice a second per bot,
    which is far finer than the attribution windows below.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    role = roles(text)
    bots = set(role["bots"])
    # Spaced names ("Joe Rogan") resolve before the legacy lexer, longest
    # first, exactly as the shared parser does.
    names = sorted(
        set(role["bots"]) | set(role["humans"]) | set(role["instruments"]),
        key=lambda name: (-len(name), name),
    )
    tracks = {}
    markers = []
    events = []
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
            continue
        event = event_fields(line, names)
        if event:
            events.append((clock, event[0], event[1]))
    # Human and instrument tracks are not this change's subject, and a human
    # standing still is signal rather than a defect.
    tracks = {name: rows for name, rows in tracks.items() if name in bots} or tracks
    return tracks, markers, events


def audit(path, max_hold, attribute_sec):
    tracks, markers, events = read_tape(path)
    causes = {}
    for mark in markers:
        causes[mark["cause"]] = causes.get(mark["cause"], 0) + 1
    last = max((rows[-1]["t"] for rows in tracks.values() if rows), default=None)
    hops = mover_hops(events, last)
    findings = []
    for name, rows in tracks.items():
        own = [mark["t"] for mark in markers if mark["name"] == name]
        own_hops = [hop for hop in hops if hop["name"] == name]
        for window in freeze_windows(rows):
            start = window.start["t"]
            attributed = any(-0.5 <= start - mark <= attribute_sec for mark in own)
            # A hesitation keeps first claim, so nothing the gait could fail
            # on is ever excused as a mover wait.
            hop = None if attributed else next(
                (hop for hop in own_hops if hop["start"] - 0.5 <= start < hop["end"]),
                None,
            )
            motion = vertical_motion(rows, window)
            verdict = _verdict(window, attributed, hop, max_hold)
            if motion and hop and hop["boarded"] and verdict == "mover wait":
                verdict = f"vertical {hop['verb']} travel"
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
                    "mover": None if hop is None else {
                        "verb": hop["verb"],
                        "t": round(hop["start"], 1),
                        "close": hop["close"],
                        "boarded": hop["boarded"],
                        "overrun": round(max(0.0, window.end["t"] - hop["end"]), 1),
                    },
                    "vertical_motion": motion,
                    "verdict": verdict,
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
        "mover_waits": sum(1 for row in findings if row["verdict"] == "mover wait"),
        "mover_overruns": sum(1 for row in findings if row["verdict"] == "mover overrun"),
        "vertical_travel": sum(1 for row in findings if row["verdict"].startswith("vertical ")),
        "findings": findings,
        "failures": sum(1 for row in findings if row["verdict"] == "FAIL"),
    }


def vertical_motion(rows, window):
    track = [r for r in rows if window.start["line"] <= r["line"] <= window.end["line"]]
    span = max(r["z"] for r in track) - min(r["z"] for r in track)
    if span < 32:
        return None
    direction, reversals = 0, 0
    pause = longest = 0.0
    for a, b in zip(track, track[1:]):
        elapsed = b["t"] - a["t"]
        delta = b["z"] - a["z"]
        if elapsed <= 0 or elapsed > 1.25:
            direction, pause = 0, 0.0
        elif abs(delta) < 4:
            pause += elapsed
            longest = max(longest, pause)
        else:
            new_direction = 1 if delta > 0 else -1
            reversals += int(direction != 0 and direction != new_direction)
            direction, pause = new_direction, 0.0
    return dict(span=round(span, 1), reversals=reversals, longest_pause_sec=round(longest, 1))


def _verdict(window, attributed, hop, max_hold):
    if not attributed:
        if hop is None:
            return "pre-existing"
        if window.end["t"] - hop["end"] > MOVER_SLACK:
            return "mover overrun"
        return "mover wait"
    if window.hp_drop > 0:
        return "FAIL"
    if window.dur > max_hold:
        return "FAIL"
    return "within hold"


def _hop_note(mover):
    if mover is None:
        return ""
    note = (f" ({mover['verb']} hop from t={mover['t']:.1f}, closed by {mover['close']},"
            f" {'boarded' if mover['boarded'] else 'never boarded'}")
    if mover["overrun"] > MOVER_SLACK:
        note += f"; still {mover['overrun']:.1f}s after it closed"
    return note + ")"


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
            movers = [
                f"{label} {report[key]}"
                for key, label in (("mover_waits", "mover waits"),
                                   ("mover_overruns", "mover overruns"),
                                   ("vertical_travel", "vertical travel windows"))
                if report[key]
            ]
            print(
                f"{report['file']}: hesitations {report['hesitations']}"
                f" ({report['per_bot']}/bot{': ' + causes if causes else ''});"
                f" freezes {report['freezes']}"
                + (f" ({', '.join(movers)})" if movers else "")
            )
            for row in report["findings"]:
                motion = row["vertical_motion"]
                note = ""
                if motion:
                    note = (f" z span {motion['span']:.1f}u, {motion['reversals']} reversals,"
                            f" longest vertical pause {motion['longest_pause_sec']:.1f}s")
                print(
                    f"    {row['verdict']:<13} {row['bot']:<10} t={row['start']:>7.1f}"
                    f" {row['seconds']:>5.1f}s hp_lost={row['hp_lost']:>4.0f}"
                    f" mode={row['mode']} at {row['pos']}" + _hop_note(row["mover"]) + note
                )
        if len(reports) > 1:
            print(
                f"-- {len(reports)} tapes: hesitations median "
                f"{statistics.median(r['hesitations'] for r in reports):.0f},"
                f" freezes median {statistics.median(r['freezes'] for r in reports):.0f},"
                f" mover waits {sum(r['mover_waits'] for r in reports)},"
                f" mover overruns {sum(r['mover_overruns'] for r in reports)},"
                f" attributable failures {sum(r['failures'] for r in reports)}"
            )
    return 1 if any(report["failures"] for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
