#!/usr/bin/env python3
"""Map-matched movement distance between Argus bots and human tracks.

The input is ordinary ARGLOG telemetry, not demo entity angles. Human and bot
positions therefore have the same cadence and precision, and bot tracks are not
PVS-culled. Lower scores mean the bot-track distribution is closer to the
human reference distribution; the score is evidence, never a quality gate.

Examples:
  python tools/argus_humanness.py --human
  python tools/argus_humanness.py --reference "runs/shane_*.log" runs/ab_dm2_*.log
  python tools/argus_humanness.py --format json runs/candidate.log
"""

import argparse
import glob
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SAMPLE = re.compile(
    r"(?:BOTLOG|ARGLOG) (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+"
    r"(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+)"
)
SPAWN = re.compile(r"ARGEVT (.+?) (?:spawned|respawn)\b")
MAP = re.compile(r"ARGUS init on ([A-Za-z0-9_]+)\b")
MAP_FALLBACK = re.compile(r"SpawnServer:\s*([A-Za-z0-9_]+)\b")
INSTRUMENTS = {"labprobe", "unconnected"}
FEATURES = (
    "speed_median",
    "active_speed_p90",
    "pause_fraction",
    "pause_mean_sec",
    "direction_changes_pm",
    "cells_pm",
    "gyration",
    "local_dwell_fraction",
)
# A reference can be genuinely tight (dm2 human median speed differs by less
# than 1 u/s across several sessions). Dividing by that tiny IQR would let one
# feature swamp the entire score. These floors are practical effect sizes in
# the feature's native unit, not fitted to a candidate.
SCALE_FLOORS = {
    "speed_median": 32.0,
    "active_speed_p90": 32.0,
    "pause_fraction": 0.05,
    "pause_mean_sec": 0.5,
    "direction_changes_pm": 5.0,
    "cells_pm": 10.0,
    "gyration": 128.0,
    "local_dwell_fraction": 0.10,
}


def percentile(values, q):
    values = sorted(values)
    if not values:
        raise ValueError("percentile of an empty sequence")
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return values[lo]
    weight = position - lo
    return values[lo] * (1 - weight) + values[hi] * weight


def read_tape(path):
    """Return map and role-separated tracks from one telemetry tape."""
    with open(path, encoding="utf-8", errors="replace") as tape:
        lines = list(tape)

    boundaries = [index for index, line in enumerate(lines) if MAP.search(line)]
    if len(boundaries) <= 1:
        segments = [lines]
    else:
        segments = [
            lines[start : boundaries[index + 1] if index + 1 < len(boundaries) else None]
            for index, start in enumerate(boundaries)
        ]

    parsed = [_read_segment(segment) for segment in segments]
    selected = max(
        parsed,
        key=lambda segment: (segment["span"], segment["samples"]),
    )
    selected.update(
        {
            "file": os.path.basename(path),
            "path": str(path),
            "segments": len(parsed),
            "ignored_segments": len(parsed) - 1,
        }
    )
    return selected


def _read_segment(lines):
    """Parse one map episode; role evidence never crosses this boundary."""
    tracks = defaultdict(list)
    spawned = set()
    map_names = set()
    fallback_map = None
    for line in lines:
        match = MAP.search(line)
        if match:
            map_names.add(match.group(1).lower())
        elif fallback_map is None:
            match = MAP_FALLBACK.search(line)
            if match:
                fallback_map = match.group(1).lower()
        match = SPAWN.search(line)
        if match:
            spawned.add(match.group(1))
        match = SAMPLE.search(line)
        if match:
            name, t, x, y, z, speed, yaw = match.groups()
            tracks[name].append(
                {
                    "t": float(t),
                    "x": float(x),
                    "y": float(y),
                    "z": float(z),
                    "speed": max(0.0, float(speed)),
                    "yaw": float(yaw),
                }
            )
    for samples in tracks.values():
        samples.sort(key=lambda sample: sample["t"])
    # Match the Rust parser: without any spawn evidence, a legacy or sliced
    # tape cannot distinguish a person from a bot and must not invent one.
    humans = {
        name: samples
        for name, samples in tracks.items()
        if spawned and name not in spawned and name not in INSTRUMENTS
    }
    bots = {
        name: samples
        for name, samples in tracks.items()
        if name in spawned and name not in INSTRUMENTS
    }
    spans = [samples[-1]["t"] - samples[0]["t"] for samples in tracks.values() if len(samples) > 1]
    return {
        # A multi-map console log cannot support one map-matched distance.
        "map": (
            next(iter(map_names))
            if len(map_names) == 1
            else (fallback_map if not map_names else None)
        ),
        "humans": humans,
        "bots": bots,
        "span": max(spans, default=0.0),
        "samples": sum(len(samples) for samples in tracks.values()),
    }


def _pause_lengths(samples):
    pauses = []
    start = None
    previous = None
    gaps = [
        b["t"] - a["t"]
        for a, b in zip(samples, samples[1:])
        if 0 < b["t"] - a["t"] <= 2.0
    ]
    cadence = statistics.median(gaps) if gaps else 0.0
    for sample in samples:
        contiguous = previous is None or 0 < sample["t"] - previous["t"] <= 2.0
        if sample["speed"] < 20 and contiguous:
            if start is None:
                start = sample["t"]
        else:
            if start is not None and previous is not None:
                pauses.append(max(cadence, previous["t"] - start + cadence))
            start = sample["t"] if sample["speed"] < 20 else None
        previous = sample
    if start is not None and previous is not None:
        pauses.append(max(cadence, previous["t"] - start + cadence))
    return pauses


def _direction_changes(samples):
    headings = []
    for first, second in zip(samples, samples[1:]):
        dt = second["t"] - first["t"]
        dx = second["x"] - first["x"]
        dy = second["y"] - first["y"]
        distance = math.hypot(dx, dy)
        if not 0 < dt <= 2.0 or distance < 20 or distance > 512:
            headings.append(None)
        else:
            headings.append(math.degrees(math.atan2(dy, dx)))
    changes = 0
    previous = None
    for heading in headings:
        if heading is None:
            previous = None
            continue
        if previous is not None:
            delta = abs((heading - previous + 180) % 360 - 180)
            if delta >= 45:
                changes += 1
        previous = heading
    return changes


def _local_dwell_fraction(samples, window_sec=30.0, radius=1024.0):
    """Fraction of full trailing windows confined to one 1024u neighbourhood."""
    local = 0
    windows = 0
    left = 0
    for right, sample in enumerate(samples):
        while left < right and sample["t"] - samples[left]["t"] > window_sec:
            left += 1
        window = samples[left : right + 1]
        if len(window) < 2 or window[-1]["t"] - window[0]["t"] < window_sec * 0.9:
            continue
        cx = sum(point["x"] for point in window) / len(window)
        cy = sum(point["y"] for point in window) / len(window)
        extent = max(math.hypot(point["x"] - cx, point["y"] - cy) for point in window)
        windows += 1
        local += extent <= radius
    return local / windows if windows else 0.0


def track_metrics(samples):
    """Summarize one sufficiently long, same-cadence ARGLOG track."""
    if len(samples) < 20:
        return None
    duration = samples[-1]["t"] - samples[0]["t"]
    if duration < 10:
        return None
    speeds = [sample["speed"] for sample in samples]
    active = [speed for speed in speeds if speed >= 20]
    pauses = _pause_lengths(samples)
    cx = sum(sample["x"] for sample in samples) / len(samples)
    cy = sum(sample["y"] for sample in samples) / len(samples)
    gyration = math.sqrt(
        sum((sample["x"] - cx) ** 2 + (sample["y"] - cy) ** 2 for sample in samples)
        / len(samples)
    )
    cells = {
        (
            math.floor(sample["x"] / 64),
            math.floor(sample["y"] / 64),
            math.floor(sample["z"] / 64),
        )
        for sample in samples
    }
    return {
        "speed_median": statistics.median(speeds),
        "active_speed_p90": percentile(active or speeds, 0.90),
        "pause_fraction": sum(speed < 20 for speed in speeds) / len(speeds),
        "pause_mean_sec": statistics.mean(pauses) if pauses else 0.0,
        "direction_changes_pm": _direction_changes(samples) * 60.0 / duration,
        "cells_pm": len(cells) * 60.0 / duration,
        "gyration": gyration,
        "local_dwell_fraction": _local_dwell_fraction(samples),
    }


def build_reference(tapes):
    """Collect human track summaries independently for every map."""
    reference = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(int)
    for tape in tapes:
        if not tape["map"]:
            continue
        for samples in tape["humans"].values():
            metrics = track_metrics(samples)
            if metrics is None:
                continue
            counts[tape["map"]] += 1
            for feature in FEATURES:
                reference[tape["map"]][feature].append(metrics[feature])
    return reference, counts


def normalized_wasserstein(candidate, human, scale_floor=1.0):
    """Empirical W1 distance, scaled by the human reference spread."""
    if not candidate or not human:
        return None
    samples = max(len(candidate), len(human), 21)
    distances = []
    for index in range(samples):
        q = (index + 0.5) / samples
        distances.append(abs(percentile(candidate, q) - percentile(human, q)))
    raw = statistics.mean(distances)
    spread = percentile(human, 0.75) - percentile(human, 0.25)
    spread = max(spread, scale_floor)
    return raw / spread


def score_tape(tape, reference, reference_counts):
    bot_metrics = [
        metrics
        for samples in tape["bots"].values()
        if (metrics := track_metrics(samples)) is not None
    ]
    if not tape["map"] or tape["map"] not in reference or not bot_metrics:
        return None
    distances = {}
    for feature in FEATURES:
        distances[feature] = normalized_wasserstein(
            [metrics[feature] for metrics in bot_metrics],
            reference[tape["map"]][feature],
            SCALE_FLOORS[feature],
        )
    available = [value for value in distances.values() if value is not None]
    return {
        "file": tape["file"],
        "map": tape["map"],
        "bot_tracks": len(bot_metrics),
        "human_reference_tracks": reference_counts[tape["map"]],
        "distance": statistics.mean(available),
        **distances,
    }


def expand_paths(patterns):
    paths = []
    seen = set()
    for pattern in patterns:
        matches = glob.glob(pattern)
        for value in matches or [pattern]:
            path = str(Path(value))
            if path not in seen and Path(path).is_file():
                paths.append(path)
                seen.add(path)
    return paths


def format_tsv(rows):
    columns = (
        "file",
        "map",
        "bot_tracks",
        "human_reference_tracks",
        "distance",
        *FEATURES,
    )
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append(
            "\t".join(
                f"{row[column]:.3f}" if isinstance(row[column], float) else str(row[column])
                for column in columns
            )
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", help="candidate logs or glob patterns")
    parser.add_argument(
        "--reference",
        action="append",
        default=[],
        metavar="GLOB",
        help="human reference logs (repeatable; default: runs/shane_*.log)",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="score bots in the human reference sessions themselves",
    )
    parser.add_argument("--format", choices=("tsv", "json"), default="tsv")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    reference_patterns = args.reference or [str(root / "runs" / "shane_*.log")]
    reference_paths = expand_paths(reference_patterns)
    if not reference_paths:
        parser.error("no human reference logs matched")
    candidate_paths = reference_paths if args.human or not args.logs else expand_paths(args.logs)
    if not candidate_paths:
        parser.error("no candidate logs matched")

    reference_tapes = [read_tape(path) for path in reference_paths]
    reference, counts = build_reference(reference_tapes)
    if not reference:
        parser.error("reference logs contain no usable human ARGLOG tracks")

    rows = []
    skipped = []
    noted = set()
    for tape in reference_tapes:
        if tape["ignored_segments"]:
            noted.add(tape["path"])
            print(
                f"{tape['file']}: selected dominant {tape['map']} segment; "
                f"ignored {tape['ignored_segments']} other map segment(s)",
                file=sys.stderr,
            )
    for path in candidate_paths:
        tape = read_tape(path)
        if tape["ignored_segments"] and tape["path"] not in noted:
            print(
                f"{tape['file']}: selected dominant {tape['map']} segment; "
                f"ignored {tape['ignored_segments']} other map segment(s)",
                file=sys.stderr,
            )
        row = score_tape(tape, reference, counts)
        if row is None:
            skipped.append(tape["file"])
        else:
            rows.append(row)
    if not rows:
        parser.error("no candidate had both usable bot tracks and a same-map human reference")
    if skipped:
        print("skipped without usable bots or same-map reference: " + ", ".join(skipped), file=sys.stderr)
    if args.format == "json":
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        print(format_tsv(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
