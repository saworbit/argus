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
"""
import re, sys, os, collections, math, glob

PAT = re.compile(r"ARGLOG (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+) mode\s+(\d) st\s+(\d+) gl\s+(\d+)(?: hp\s+(-?[\d.]+) frg\s+(-?\d+))?")
EVT = re.compile(r"ARGEVT (.+?) (spawned|respawn|goal_push|goal_pop|goal|route|routefail|trapped|abandon|stall|stallnode|jump|rjump|lift|swim|door|train|board|hazard|engage|pursue|retreat|grab|weapon|plan|death|checkpoint|win|coop_stats)\b(.*)")
DEATH = re.compile(r"ARGEVT (.+?) death\s+(?:(.+?)\s+)?pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'")
PLAIN = re.compile(r"^ARGUS (.+?) (unstick (?:embedded|pinned|fightpin)|shove|hunch|prefire|watch spawn|sprintjump)\b")
WORLD_PHRASES = ["tries to put the pin back in", "becomes bored with life", "discharges into", "heats up the water",
                 "electrocutes", "died", "was squished", "fell to", "can't exist on slime", "visits the Volcano God",
                 "turned into hot slag", "burst into flames", "sleeps with the fishes", "sucks it down", "blew up",
                 "was spiked", "was zapped", "ate a lavaball", "checks if his weapon", "was killed by a monster",
                 "was telefragged by his teammate"]
LAVA_PHRASES = ["visits the Volcano God", "turned into hot slag", "burst into flames", "ate a lavaball"]


def freezes(samples):
    """Return a list of (duration, hp_lost) for every 6 s+ statue in one bot's track."""
    out = []
    i = 0
    n = len(samples)
    while i < n:
        a = samples[i]
        if a['spd'] >= 20:
            i += 1
            continue
        j = i
        hp0 = a['hp']
        hpmin = hp0
        while j + 1 < n:
            b = samples[j + 1]
            if (b['spd'] < 20 and math.hypot(b['x'] - a['x'], b['y'] - a['y']) < 32
                    and abs(b['z'] - a['z']) < 32 and b['t'] - samples[j]['t'] < 3):
                j += 1
                if b['hp'] is not None and hpmin is not None:
                    hpmin = min(hpmin, b['hp'])
            else:
                break
        dur = samples[j]['t'] - a['t']
        if dur >= 6:
            out.append((dur, (hp0 - hpmin) if (hp0 is not None and hpmin is not None) else 0))
        i = j + 1
    return out


def analyse(path):
    bots = collections.defaultdict(list)
    ev = collections.Counter()
    perbot_ev = collections.defaultdict(collections.Counter)
    plain = collections.Counter()
    deaths = []
    spawnnames = set()
    mapname = None
    raw = []
    for line in open(path, errors='replace'):
        m = PAT.search(line)
        if m:
            g = m.groups()
            bots[g[0]].append(dict(t=float(g[1]), x=float(g[2]), y=float(g[3]), z=float(g[4]), spd=float(g[5]),
                                   mode=int(g[7]), st=int(g[8]), gl=int(g[9]),
                                   hp=float(g[10]) if g[10] else None, frg=int(g[11]) if g[11] else None))
            continue
        m = EVT.search(line)
        if m:
            name, verb, rest = m.groups()
            ev[verb] += 1
            perbot_ev[name][verb] += 1
            if verb in ('spawned', 'respawn'):
                spawnnames.add(name)
            if verb == 'death':
                d = DEATH.search(line)
                if d:
                    deaths.append((d.group(1), d.group(2) or '', float(d.group(5))))
            continue
        m = PLAIN.match(line)
        if m:
            verb = m.group(2)
            plain['unstick' if verb.startswith('unstick') else verb.split()[0]] += 1
            continue
        if line.startswith('ARG'):
            continue
        if mapname is None:
            mm = (re.search(r'SpawnServer: (\w+)', line) or re.search(r'Spawning server maps/(\w+)', line)
                  or re.search(r'^(?:maps/)?(\w+)\.bsp', line))
            if mm:
                mapname = mm.group(1)
        raw.append(line.rstrip('\n'))
    names = set(bots) | spawnnames
    humans = [n for n in bots if n not in spawnnames]
    botnames = [n for n in bots if n in spawnnames]
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
    dur = max(t1 - t0, 1)
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
    return dict(file=os.path.basename(path), map=mapname or '?', dur=round(dur), bots=len(botnames),
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
