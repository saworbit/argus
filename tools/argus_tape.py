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
EVENT_VERBS = "spawned|respawn|goal_push|goal_pop|goal|goal_pickup_v1|route|routefail|trapped|abandon|stall|stallnode|jump|rjump|lift|swim|door|train|board|hazard|engage|retarget|pursue|retreat|coverroute|lifeveto|grab|weapon|plan|arm|tactic|death|checkpoint|win|coop_stats"
EVT = re.compile(r"ARGEVT (.+?) (" + EVENT_VERBS + r")(?:\s+(.*))?$")
MAP = re.compile(r"(?:SpawnServer:\s+|ARGUS init on\s+)([A-Za-z0-9_]+)", re.I)
INSTRUMENTS = frozenset(("labprobe", "labcamera", "unconnected"))
VERBS = frozenset(EVENT_VERBS.split("|"))
LEGACY_SAMPLE = re.compile(r"(?:BOTLOG|ARGLOG) (\S+) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' yaw\s+(-?[\d.]+) blk\s+(\d+)")
SAMPLE_PREFIX = re.compile(r"(?:BOTLOG|ARGLOG) (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'(?: spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+))?")
MAP_FALLBACK = re.compile(r"(?:SpawnServer:\s*|Spawning server maps/)([A-Za-z0-9_]+)|^(?:maps/)?(\w+)\.bsp", re.M)
DEATH_PAYLOAD = re.compile(r"(?:(.+?)\s+)?pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'")


def samples(text):
    """Yield (name, sample) rows in tape order using the shared grammar."""
    for lineno, line in enumerate(text.splitlines(), 1):
        row = sample_row(line, lineno)
        if row is not None:
            yield row
        elif match := SAMPLE_PREFIX.search(line):
            yield match[1], dict(t=float(match[2]), x=float(match[3]), y=float(match[4]),
                                 z=float(match[5]), spd=float(match[6]) if match[6] else None,
                                 yaw=float(match[7]) if match[7] else None, line=lineno)


def map_name(text):
    """Prefer confirmed init records, with legacy console map-line fallback."""
    confirmed = {match[1].lower() for line in text.splitlines()
                 if 'ARGUS init on' in line and (match := MAP.search(line))}
    if confirmed:
        return next(iter(confirmed)) if len(confirmed) == 1 else None
    fallback, pending = None, None
    for line in text.splitlines():
        match = MAP_FALLBACK.search(line)
        if match:
            fallback = pending or fallback
            pending = next(group.lower() for group in match.groups() if group)
        elif line.startswith("Couldn't spawn server maps/"):
            pending = None
    return pending or fallback


def roles(text):
    """Shared role split; has_births also identifies scoreable modern tapes."""
    tape = parse_tape(text)
    tracks = {name: [] for name, _ in samples('\n'.join(line for _, line in tape.lines))}
    bots, humans, instruments = track_names(tracks, tape.events)
    return dict(bots=bots, humans=humans, instruments=instruments,
                has_births=any(event[2] in ('spawned', 'respawn') for event in tape.events))


def deaths(events):
    """Yield (line, victim, killer, x, y, z); empty historical killers are world."""
    for lineno, name, verb, rest in events:
        match = DEATH_PAYLOAD.fullmatch(rest.removesuffix(' thirdparty')) if verb == 'death' else None
        if match:
            yield (lineno, name, match[1] or 'world', *(float(match[i]) for i in (2, 3, 4)))


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


def freeze_windows(samples, *, stationary=False):
    """Under 20 u/s, inside a strict 32u XY circle, for at least 6s.

    The historical window ignores Z. The stationary gate also requires
    the whole Z range to stay within 32 units. Both keep tape order and
    the historical treatment of sample gaps and missing health.
    """
    out, i = [], 0
    while i < len(samples):
        first = samples[i]
        if first['spd'] >= 20:
            i += 1
            continue
        hp_first = first.get('hp') if first.get('hp') is not None else 0.0
        hp_min, j = hp_first, i
        low_z = high_z = first['z']
        while j + 1 < len(samples):
            row = samples[j + 1]
            dx, dy = row['x'] - first['x'], row['y'] - first['y']
            if row['spd'] >= 20 or math.sqrt(dx * dx + dy * dy) >= 32:
                break
            low_z, high_z = min(low_z, row['z']), max(high_z, row['z'])
            if stationary and high_z - low_z >= 32:
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


# ---------------------------------------------------------------- identity
# What a tape says about itself, the Python twin of tape_identity.rs:
#   ARGUS build <id>                              the QC source identity (#823)
#   ARGUS clock frame_us <n> tick_us <n> seed <n> frame_us 0 is the wall clock;
#                                                 above 0 the fixed lab clock
#   ARGUS mark <n> t <t> pos '<x y z>' yaw <deg> [seen <0|1> dist <u>] near <name|none>
BUILD_LINE = re.compile(r"^ARGUS build ([0-9a-f]{6,32})\s*$")
CLOCK_LINE = re.compile(r"^ARGUS clock frame_us\s+(\d+) tick_us\s+(\d+) seed\s+(\d+)\s*$")
MARK_LINE = re.compile(r"^ARGUS mark (\d+) t\s+(-?[\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'"
                       r" yaw\s+(-?[\d.]+)(?: near none| seen ([01]) dist\s+(-?[\d.]+) near (.+?))\s*$")


def identity(text):
    """Build, other builds, clock and marks from one level's text (use the busiest level's lines)."""
    out = dict(build=None, other_builds=[], clock=None, marks=[])
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.startswith("ARGUS "):
            continue
        if line == "ARGUS goal_pickup v1":
            out["goal_pickup_version"] = 1
            continue
        if m := BUILD_LINE.match(line):
            if out["build"] is None:
                out["build"] = m[1]
            elif m[1] != out["build"] and m[1] not in out["other_builds"]:
                out["other_builds"].append(m[1])
        elif m := CLOCK_LINE.match(line):
            frame = int(m[1])
            out["clock"] = dict(frame_us=frame, tick_us=int(m[2]), seed=int(m[3]),
                                kind="fixed" if frame > 0 else "realtime")
        elif m := MARK_LINE.match(line):
            fields = m.group(1, 2, 3, 4, 5, 6, 8)
            if any(field is not None and not field.isascii() for field in fields):
                continue
            try:
                n = int(m[1])
                t, x, y, z, yaw = map(float, fields[1:6])
                dist = None if m[8] is None else float(m[8])
            except ValueError:
                continue
            if n > 0xFFFFFFFF or not all(map(math.isfinite, (t, x, y, z, yaw, dist if dist is not None else 0.0))):
                continue
            out["marks"].append(dict(n=n, t=t, pos=(x, y, z), yaw=yaw,
                                     seen=None if m[7] is None else m[7] == "1", dist=dist, near=m[9]))
    return out


def tape_identity(text):
    """identity() over the busiest level, the segment every other reader uses."""
    return identity("\n".join(line for _, line in tape_lines(text)))
