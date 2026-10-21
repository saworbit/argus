"""ARGLOG samples, track identity and freezes aligned with parse_arglog.rs.

Rust remains the gate definition. This module shares the review consumers'
small sample/freeze core; it does not implement the rest of MatchTape.
"""
import collections
from dataclasses import dataclass
import math
from pathlib import Path
import re

PAT = re.compile(r"(?:BOTLOG|ARGLOG) (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+) mode\s+(\d) st\s+(\d+) gl\s+(\d+)(?: hp\s+(-?[\d.]+) frg\s+(-?\d+))?")
EVENT_VERBS = "spawned|respawn|goal_push|goal_pop|goal|route|routefail|trapped|abandon|stall|stallnode|jump|rjump|lift|swim|door|train|board|hazard|engage|pursue|retreat|coverroute|lifeveto|grab|weapon|plan|arm|tactic|death|checkpoint|win|coop_stats"
EVT = re.compile(r"ARGEVT (.+?) (" + EVENT_VERBS + r")(?:\s+(.*))?$")
MAP = re.compile(r"(?:SpawnServer:\s+|ARGUS init on\s+)([A-Za-z0-9_]+)", re.I)
INSTRUMENTS = frozenset(("labprobe", "unconnected"))
VERBS = frozenset(EVENT_VERBS.split("|"))


def event_fields(line, names=()):
    """Resolve against complete sample identities before the legacy lexer.

    Pass known names longest first. Terminal spawn records supply their own
    identity.
    Other legacy rows keep the old closed-vocabulary interpretation.
    """
    if 'ARGEVT ' not in line:
        return None
    body = line.split('ARGEVT ', 1)[1].rstrip()
    for name in names:
        if body.startswith(name + ' '):
            fields = body[len(name) + 1:].split(None, 1)
            if fields and fields[0] in VERBS:
                return name, fields[0], fields[1].strip() if len(fields) > 1 else ''
    for verb in ('spawned', 'respawn'):
        suffix = ' ' + verb
        if body.endswith(suffix) and body[:-len(suffix)]:
            return body[:-len(suffix)], verb, ''
    match = EVT.search(line)
    if match:
        name, verb, rest = match.groups()
        return name, verb, (rest or '').strip()
    return None


def sample_row(line, lineno):
    """Return (name, sample) with the source line number, or None for other rows."""
    match = PAT.search(line)
    if not match:
        return None
    g = match.groups()
    return g[0], dict(t=float(g[1]), x=float(g[2]), y=float(g[3]),
                     z=float(g[4]), spd=float(g[5]), yaw=float(g[6]),
                     mode=int(g[7]), st=int(g[8]), gl=int(g[9]),
                     hp=float(g[10]) if g[10] else None,
                     frg=int(g[11]) if g[11] else None, line=lineno)


def tape_lines(text):
    """Use the busiest level, choosing the last tie, just as Rust does."""
    segments, current, seen_samples = [], [], False
    for lineno, line in enumerate(text.splitlines(), 1):
        if seen_samples and MAP.search(line) and "SpawnServer" in line:
            segments.append(current)
            current, seen_samples = [], False
        current.append((lineno, line))
        if line.startswith("ARGLOG "):
            seen_samples = True
    segments.append(current)
    return max(enumerate(segments), key=lambda entry: (
        sum(line.startswith("ARGLOG ") for _, line in entry[1]), entry[0],
    ))[1]


@dataclass
class Tape:
    """Selected level lines, samples by identity, and (line, name, verb, rest) events."""
    lines: list
    samples: dict
    events: list

    def bot_samples(self):
        """Return bot tracks, excluding human and lab instrument identities."""
        bots, _, _ = track_names(self.samples, self.events)
        return {name: self.samples[name] for name in bots}


def parse_tape(text):
    """Parse the busiest level using complete sample and birth identities."""
    lines = tape_lines(text)
    names = sorted({match.group(1) for _, line in lines if (match := PAT.search(line))},
                   key=lambda name: (-len(name), name))
    births = {event[0] for _, line in lines if (event := event_fields(line, names))
              and event[1] in ('spawned', 'respawn')}
    names = sorted(set(names) | births, key=lambda name: (-len(name), name))
    samples = collections.defaultdict(list)
    events = []
    for lineno, line in lines:
        row = sample_row(line, lineno)
        if row is not None:
            name, sample = row
            samples[name].append(sample)
            continue
        event = event_fields(line, names)
        if event:
            events.append((lineno, *event))
    return Tape(lines, samples, events)


def read_tape(path):
    """Parse a UTF-8 tape, replacing undecodable bytes in console output."""
    return parse_tape(Path(path).read_text(encoding="utf-8", errors="replace"))


def track_names(samples, events):
    """Return sorted (bots, humans, instruments); tapes without births keep legacy bots."""
    spawned = {name for _, name, verb, _ in events if verb in ("spawned", "respawn")}
    instruments = set(samples) & INSTRUMENTS
    humans = (set(samples) - spawned - instruments) if spawned else set()
    return sorted(set(samples) - humans - instruments), sorted(humans), sorted(instruments)


@dataclass(frozen=True)
class Freeze:
    """Endpoints, elapsed seconds and health loss for one stationary window."""
    start: dict
    end: dict
    dur: float
    hp_drop: float


def freeze_windows(samples):
    """Under 20 u/s, inside a strict 32u XY circle, for at least 6s.

    Keep tape order. Rust has no Z or sample-gap filter. Missing initial
    health is zero, and later health can only lower that initial minimum.
    """
    out, i = [], 0
    while i < len(samples):
        first = samples[i]
        if first['spd'] >= 20:
            i += 1
            continue
        hp_first = first.get('hp') if first.get('hp') is not None else 0.0
        hp_min, j = hp_first, i
        while j + 1 < len(samples):
            row = samples[j + 1]
            dx, dy = row['x'] - first['x'], row['y'] - first['y']
            if row['spd'] >= 20 or math.sqrt(dx * dx + dy * dy) >= 32:
                break
            if row.get('hp') is not None:
                hp_min = min(hp_min, row['hp'])
            j += 1
        dur = samples[j]['t'] - first['t']
        if dur >= 6:
            out.append(Freeze(first, samples[j], dur, max(0.0, hp_first - hp_min)))
        i = j + 1
    return out


def tactic_counts(events):
    """Observed phases and abort reasons; a shot event proves no hit."""
    counts = collections.Counter()
    for _, _, verb, rest in events:
        if verb != 'tactic':
            continue
        fields = rest.split()
        if fields and fields[0] in ('prepare', 'opening', 'covered', 'reappear', 'returnshot', 'abort'):
            counts['tactic_' + fields[0]] += 1
            if (fields[0] == 'abort' and len(fields) > 1
                    and fields[1].isascii() and fields[1].replace('_', '').isalnum()):
                counts['tactic_abort_' + fields[1]] += 1
    return counts
