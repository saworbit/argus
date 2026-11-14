#!/usr/bin/env python3
"""Longitudinal tape scorecard: one row of human-facing metrics per tape.

usage:
  argus_longi.py <log> [<log> ...]          TSV on stdout, one row per tape
  argus_longi.py --human                    every runs/shane_*.log in play order
  argus_longi.py --lab dm4                  every runs/ab_dm4_*.log in mtime order
  argus_longi.py --append <tsv> <log> ...   add rows to a scorecard, no duplicates

A human is any ARGLOG name that never emits spawned or respawn (the Rust
parser's rule); 'player' is also read as human for obituary purposes on
tapes that predate human ARGLOG rows. Kills and deaths come from the engine
obituaries, which a listen server writes to the console log and a dedicated
one does not, so bot_kills_bot is 0 on every lab tape; use bot_deaths minus
bot_world there. Validated against the frag counters: 18 kills with one
world death reads 17 frags on shane_dm4_2026-08-27_v374.

Freeze rule matches argus_review.py and the Rust lab: under 20 u/s within a
32 u radius for 6 s or more. Written 2026-09-14 for the regression analysis
in docs/plans/2026-09-14-regression-analysis-and-recovery.md.

bot_world_unforced counts bot world deaths that no damage led into: the bot
lost no health in the 3 s before it reached lava or slime (or, for a world
death anywhere else, before its last sample). It separates a bot walking or
jumping off a ledge from a knock-in, which bot_world cannot. Liquid needs
hull-0 contents, so the map's BSP is looked up in ARGUS_MAPS, maps_local/
and engine/argus/maps/; without one the column is blank rather than a guess.
Two limits of a 2 Hz tape: a hit landing in the same half second as the
entry reads as unforced, and a drowning reads as forced.
"""
import re, sys, os, collections, math, glob
from functools import lru_cache
from pathlib import Path

from argus_bsp import load_classifier
from argus_tape import PAT, EVT, read_tape, track_names, freeze_windows, tactic_counts, deaths as tape_deaths, map_name
PLAIN = re.compile(r"^ARGUS (.+?) (unstick (?:embedded|pinned|fightpin|underfire)|shove|hunch|prefire|watch spawn|sprintjump)\b")
WORLD_PHRASES = ["tries to put the pin back in", "becomes bored with life", "discharges into", "heats up the water",
                 "electrocutes", "died", "was squished", "fell to", "can't exist on slime", "visits the Volcano God",
                 "turned into hot slag", "burst into flames", "sleeps with the fishes", "sucks it down", "blew up",
                 "was spiked", "was zapped", "ate a lavaball", "checks if his weapon", "was killed by a monster",
                 "was telefragged by his teammate"]
LAVA_PHRASES = ["visits the Volcano God", "turned into hot slag", "burst into flames", "ate a lavaball"]


def freezes(samples):
    """Return a list of (duration, hp_lost) for every 6 s+ statue in one bot's track."""
    return [(f.dur, f.hp_drop) for f in freeze_windows(samples)]


HAZARD = (-5, -4)  # CONTENTS_LAVA, CONTENTS_SLIME: the liquids that burn
PRIOR_SEC = 3.0    # how far before the entry damage counts as the cause
BOB_SEC = 1.0      # a dry gap this short inside the hazard is a bob, not an exit
_LOOKUP = object()


def bsp_for(mapname):
    """The map's BSP, or None: ARGUS_MAPS first, then the machine-local copies."""
    if not mapname:
        return None
    root = Path(__file__).resolve().parent.parent
    for folder in (os.environ.get('ARGUS_MAPS'), root / 'maps_local', root / 'engine' / 'argus' / 'maps'):
        if folder and (Path(folder) / f'{mapname}.bsp').is_file():
            return Path(folder) / f'{mapname}.bsp'
    return None


@lru_cache(maxsize=None)
def _classifier(path):
    try:
        return load_classifier(path)
    except OSError:
        return None


def in_hazard(sample, contents):
    """Lava or slime at the origin or at the feet, origin minus 23 (navgen's hostile_at)."""
    x, y, z = sample['x'], sample['y'], sample['z']
    return contents(x, y, z) in HAZARD or contents(x, y, z - 23) in HAZARD


def world_death_unforced(life, contents, death=None):
    """True, False or None for one world death, from the victim's samples this life.

    The entry is the first sample of the final run inside lava or slime,
    allowing dry gaps of up to BOB_SEC, because a bot struggling in shallow
    lava surfaces between samples and the burn before that bob is the hazard,
    not a cause. The death position, when it is in the hazard, ends that run
    a quarter second after the last sample: a bot can burn at a lava edge for
    a sample or two after its feet read dry. With no hazard at all (a crush,
    a drowning) the last sample stands in for the entry. The death is
    unforced when health never fell in the PRIOR_SEC before the entry.
    Megahealth rot above 100 is not damage. None means the tape cannot say:
    no samples this life, or a grammar without hp.
    """
    if not life or any(s.get('hp') is None for s in life):
        return None
    entry, entry_t = None, None
    if death is not None and in_hazard(death, contents):
        entry, entry_t = len(life), life[-1]['t'] + 0.25
    for i in range(len(life) - 1, -1, -1):
        if in_hazard(life[i], contents):
            entry, entry_t = i, life[i]['t']
        elif entry is None or entry_t - life[i]['t'] > BOB_SEC:
            break
    pre = len(life) - 1 if entry is None else entry - 1
    if pre < 0:
        return True
    start = life[pre]['t'] - PRIOR_SEC
    first = next(i for i in range(pre + 1) if life[i]['t'] >= start)
    window = life[max(first - 1, 0):pre + 1]
    for a, b in zip(window, window[1:]):
        if b['hp'] < a['hp'] and not (a['hp'] > 100 and b['hp'] >= 100):
            return False
    return True


def unforced_world_deaths(tape, botnames, contents):
    """Count of bot world deaths no damage led into, or '' when the tape cannot say.

    Blank without a BSP or on a tape whose samples carry no hp. A death with
    no sample in its own life (a spawn kill) is not counted either way.
    """
    lives = collections.defaultdict(int)
    count = 0
    for line, name, verb, rest in tape.events:
        if name not in botnames:
            continue
        if verb in ('spawned', 'respawn'):
            lives[name] = line
            continue
        if verb != 'death':
            continue
        death = next(iter(tape_deaths([(line, name, verb, rest)])), None)
        if death is None:
            continue  # the bare death line tapes before 2026-08-18 wrote beside the detailed one
        if death[2] == 'world':
            if contents is None:
                return ''
            life = [s for s in tape.samples.get(name, []) if lives[name] < s['line'] < line]
            if any(s.get('hp') is None for s in life):
                return ''
            point = dict(x=death[3], y=death[4], z=death[5])
            count += world_death_unforced(life, contents, point) is True
        lives[name] = line
    return count


def analyse(path, contents=_LOOKUP):
    tape = read_tape(path)
    bots = tape.samples
    by_line = {line: (name, verb, rest) for line, name, verb, rest in tape.events}
    ev = collections.Counter()
    perbot_ev = collections.defaultdict(collections.Counter)
    plain = collections.Counter()
    deaths = [(name, killer, z) for _, name, killer, _, _, z in tape_deaths(tape.events)]
    spawnnames = set()
    mapname = map_name("\n".join(line for _, line in tape.lines))
    if contents is _LOOKUP:
        bsp = bsp_for(mapname)
        contents = _classifier(str(bsp)) if bsp else None
    raw = []
    for lineno, line in tape.lines:
        if PAT.search(line):
            continue
        event = by_line.get(lineno)
        if event:
            name, verb, rest = event
            ev[verb] += 1
            perbot_ev[name][verb] += 1
            if verb in ('spawned', 'respawn'):
                spawnnames.add(name)
            continue
        m = PLAIN.match(line)
        if m:
            verb = m.group(2)
            plain['unstick' if verb.startswith('unstick') else verb.split()[0]] += 1
            continue
        if line.startswith('ARG'):
            continue
        raw.append(line.rstrip('\n'))
    names = set(bots) | spawnnames
    botnames, humans, instruments = track_names(bots, tape.events)
    names -= set(instruments)
    allnames = list(names | {'player'})
    obit = collections.Counter()
    hum_names = set(humans) | {'player'}
    for line in raw:
        if ':' in line:
            continue
        victim = None
        for nm in sorted(allnames, key=len, reverse=True):
            if line.startswith(nm + ' '):
                victim = nm
                break
        if not victim:
            continue
        rest = line[len(victim) + 1:]
        if (rest.startswith('entered') or rest.startswith('left') or 'lost a' in rest or rest.startswith('is now')
                or rest.startswith('got') or rest.startswith('found') or 'changed name' in rest):
            continue
        killer = None
        for nm in sorted(allnames, key=len, reverse=True):
            if nm == victim:
                continue
            if (nm + "'s") in rest or rest.endswith(' by ' + nm) or (' by ' + nm + ' ') in rest:
                killer = nm
                break
        if killer is None:
            if any(p in rest for p in WORLD_PHRASES):
                killer = 'world'
            else:
                continue
        vk = 'human' if victim in hum_names else 'bot'
        kk = 'world' if killer == 'world' else ('human' if killer in hum_names else 'bot')
        obit[(vk, kk)] += 1
        if killer == 'world' and any(p in rest for p in LAVA_PHRASES):
            obit[(vk, 'lava')] += 1
    t0 = min((s[0]['t'] for s in bots.values() if s), default=0)
    t1 = max((s[-1]['t'] for s in bots.values() if s), default=0)
    # A tape shorter than 10 s has no rates worth printing: the
    # 2026-09-05 e1m3 session spans 0.3 s and reported 1412 stalls
    # a minute, which is one stall. Floor the divisor so a stub
    # tape reads as a stub and not as a catastrophe.
    dur = max(t1 - t0, 10)
    fz = []
    cells = set()
    spd = []
    mode2 = 0
    nsamp = 0
    for b in botnames:
        s = bots[b]
        fz += freezes(s)
        for st in s:
            cells.add((b, int(st['x'] // 64), int(st['y'] // 64), int(st['z'] // 64)))
            spd.append(st['spd'])
            nsamp += 1
            if st['mode'] == 2:
                mode2 += 1
    fzmax = max([d for d, _ in fz], default=0)
    fzfire = sum(1 for d, h in fz if h > 0)
    botfrags = {b: (bots[b][-1]['frg'] if bots[b] and bots[b][-1]['frg'] is not None else None) for b in botnames}
    humfrags = {h: (bots[h][-1]['frg'] if bots[h] and bots[h][-1]['frg'] is not None else None) for h in humans}
    bdeaths = [d for d in deaths if d[0] in botnames]
    lava_evt = sum(1 for d in bdeaths if d[1] == 'world' and d[2] < -300)
    st_by = [perbot_ev[b]['stall'] for b in botnames]
    fr = [v for v in botfrags.values() if v is not None]
    tactics = tactic_counts(tape.events)
    result = dict(file=os.path.basename(path), map=mapname or '?', dur=round(dur), bots=len(botnames),
                human=','.join(humans) or ('player' if obit else '-'),
                stalls=ev['stall'], stall_pm=round(ev['stall'] * 60 / dur, 1), stall_max_bot=max(st_by, default=0),
                freezes=len(fz), fz_max=round(fzmax, 1), fz_fire=fzfire,
                routefail=ev['routefail'], rf_pm=round(ev['routefail'] * 60 / dur, 1), trapped=ev['trapped'],
                abandon=ev['abandon'], unstick=plain['unstick'],
                engage=ev['engage'], eng_pm=round(ev['engage'] * 60 / dur, 1), pursue=ev['pursue'],
                retreat=ev['retreat'], grab=ev['grab'], goal=ev['goal'], weapon=ev['weapon'],
                hazard=ev['hazard'], haz_pm=round(ev['hazard'] * 60 / dur, 1),
                bot_deaths=len(bdeaths), bot_world=sum(1 for d in bdeaths if d[1] == 'world'), bot_lava_z=lava_evt,
                bot_lava_obit=obit[('bot', 'lava')],
                bot_world_unforced=unforced_world_deaths(tape, set(botnames), contents),
                bot_kills_human=obit[('human', 'bot')], human_kills_bot=obit[('bot', 'human')],
                human_deaths=obit[('human', 'bot')] + obit[('human', 'world')], human_world=obit[('human', 'world')],
                bot_kills_bot=obit[('bot', 'bot')],
                human_frg=';'.join(f'{h}={v}' for h, v in humfrags.items()),
                bot_frg=';'.join(f'{b}={v}' for b, v in botfrags.items()),
                frag_spread=(max(fr) - min(fr)) if fr else '',
                cells=len(cells), cells_pm=round(len(cells) * 60 / dur, 1), avg_spd=round(sum(spd) / max(len(spd), 1)),
                mode2=round(100 * mode2 / max(nsamp, 1)),
                doors=ev['door'], lifts=ev['lift'], boards=ev['board'], trains=ev['train'], jumps=ev['jump'],
                rjump=ev['rjump'], swim=ev['swim'], hunch=plain['hunch'], prefire=plain['prefire'],
                watch=plain['watch'], shove=plain['shove'])
    for phase in ('prepare', 'opening', 'covered', 'reappear', 'returnshot', 'abort'):
        result['tactic_' + phase] = tactics['tactic_' + phase]
    result['tactic_abort_reasons'] = ';'.join(
        f'{key.removeprefix("tactic_abort_")}={count}' for key, count in sorted(tactics.items())
        if key.startswith('tactic_abort_'))
    return result


def human_order(files):
    """Play order for shane_*.log: date in the name, then the build tag."""
    def key(f):
        b = os.path.basename(f)
        d = re.search(r'(\d{4}-\d{2}-\d{2})', b)
        d = d.group(1) if d else '0000'
        v = re.search(r'_v(\d+)[a-z]?\.log', b)
        v = int(v.group(1)) if v else 0
        tag = re.search(r'_v\d+([a-z])\.log', b)
        tag = tag.group(1) if tag else ''
        return (d, v, tag, b)
    return sorted(files, key=key)


def append_rows(out_path, rows):
    """Append rows to a TSV scorecard, one row per tape, never duplicated.

    The scorecard is the project's memory of what the player saw. A
    session that is not scored is a session nobody can compare to the
    one before it, which is how the dm2 stall rate tripled across a
    month of play without anyone noticing.
    """
    existing = []
    header = None
    if os.path.exists(out_path):
        with open(out_path, encoding='utf-8') as fh:
            lines = [l.rstrip('\n') for l in fh if l.strip()]
        if lines:
            header = lines[0].split('\t')
            existing = [dict(zip(header, l.split('\t'))) for l in lines[1:]]
    seen = {r.get('file') for r in existing}
    added = 0
    for r in rows:
        if r['file'] in seen:
            continue
        existing.append({k: str(v) for k, v in r.items()})
        seen.add(r['file'])
        added += 1
    if not existing:
        return 0
    keys = list(rows[0].keys()) if rows else header
    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write('\t'.join(keys) + '\n')
        for r in existing:
            fh.write('\t'.join(str(r.get(k, '')) for k in keys) + '\n')
    return added


if __name__ == '__main__':
    args = sys.argv[1:]
    append_to = None
    if args[:1] == ['--append']:
        if len(args) < 2:
            sys.exit('--append needs a path')
        append_to = args[1]
        args = args[2:]
    if args[:1] == ['--human']:
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'runs')
        files = human_order(glob.glob(os.path.join(root, 'shane_*.log')))
    elif args[:1] == ['--lab'] and len(args) > 1:
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'runs')
        files = sorted(glob.glob(os.path.join(root, f'ab_{args[1]}_*.log')), key=os.path.getmtime)
    else:
        files = args
    rows = [analyse(p) for p in files]
    if not rows:
        sys.exit(0)
    if append_to:
        n = append_rows(append_to, rows)
        print(f"{n} row(s) appended to {append_to}")
        sys.exit(0)
    keys = list(rows[0].keys())
    print('\t'.join(keys))
    for r in rows:
        print('\t'.join(str(r[k]) for k in keys))
