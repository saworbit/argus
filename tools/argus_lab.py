#!/usr/bin/env python3
"""Argus lab spine: the objective, the evidence ledger, the claims and the
checks that join the lab's instruments into one loop.

usage:
  argus_lab.py state [--write PATH]               what is true now, generated from the evidence
  argus_lab.py stale [--json] [--strict]          artefacts whose inputs have moved
  argus_lab.py session [TAPE ...] [--last N]      score human sessions against the objective
  argus_lab.py skeptic RUN ... --vs RUN ... [--metric M] [--json]
                                                  audit a comparison before believing it
  argus_lab.py triage TAPE [--json]               match a tape's trouble to known claims
  argus_lab.py review TAPE                        one fresh session: gates, goal eligibility, new trouble
  argus_lab.py claims [--status S] [--check]      list or validate the claims ledger
  argus_lab.py ledger [--write PATH]              the joined evidence index as JSON
  argus_lab.py pyramid --maps M[,M] [--through N] [--dry-run]
                                                  run the cheap evidence tiers first
  argus_lab.py night [--maps M[,M]] [--engine]    the unattended sweep: tiers, new tapes, staleness
  every command takes --root DIR (default: this checkout)

The spine adds no instrument. It reads what the lab already keeps: the tape
corpus cache (runs/tape_index.tsv, written by argus-mcp corpus), the human
scorecard, the baselines, the benchmark suites, the puppet verdict sidecars
and the measurement limits, plus two hand-written files: the objective
(tools/lab_objective.json) and the claims (tools/lab_claims.json, with
tools/refuted_claims.json imported as refuted rules). Raw artefacts stay the
source of truth; nothing here is a second parser for tapes.

Evidence tiers, cheapest first: 1 static checks, 2 deterministic cases
(fixtures, benchmark tasks, puppet sweeps), 3 within-match A/B, 4 banded
ladder, 5 a human session. A change climbs only as far as it needs to.
"""
import argparse
import bisect
import collections
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_longi  # noqa: E402
import argus_tape  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ('open', 'supported', 'refuted', 'fixed', 'parked')
KINDS = ('defect', 'hypothesis', 'rule', 'graveyard')
TIERS = {1: 'static checks', 2: 'deterministic cases', 3: 'within-match A/B',
         4: 'banded ladder', 5: 'human session'}
SEVERITIES = ('void', 'stale', 'info')
ISSUE = re.compile(r'^#\d+$')
DATE = re.compile(r'(\d{4}-\d{2}-\d{2})')
ARGNAV = re.compile(r'^ARGNAV (\d+) nodes, (\d+) links', re.M)
SKILL_BASE = re.compile(r'^ARGUS difficulty .+? t\s+[\d.]+ base (\d+)', re.M)
SKILL_TIER = re.compile(r'^ARGUS .+? skill (\d+) aim -?\d+', re.M)
LIMIT_METRICS = ('stalls', 'engages', 'lava_deaths', 'freezes', 'cover', 'goals')
REGRESSION_COUNT = 5


# ---------------------------------------------------------------- loading

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_text(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def objective(root):
    return read_json(root / 'tools' / 'lab_objective.json')


def own_claims(root):
    return read_json(root / 'tools' / 'lab_claims.json')['claims']


def all_claims(root):
    """The hand-written claims plus the refuted-rule registry, imported as refuted rules."""
    out = [dict(c, source='lab_claims.json') for c in own_claims(root)]
    reg = root / 'tools' / 'refuted_claims.json'
    if reg.is_file():
        for r in read_json(reg)['claims']:
            out.append(dict(id='rule:' + r['id'], title=r['claim'], status='refuted', kind='rule',
                            tier=None, maps=[], statement=r['correction'],
                            evidence=r.get('evidence', []), source='refuted_claims.json'))
    return out


def tsv(path):
    lines = [l for l in read_text(path).splitlines() if l.strip()]
    if not lines:
        return []
    head = lines[0].split('\t')
    return [dict(zip(head, l.split('\t'))) for l in lines[1:]]


def tape_index(root):
    return {r['run']: r for r in tsv(root / 'runs' / 'tape_index.tsv')}


def scorecard(root):
    return tsv(root / 'runs' / 'human_scorecard.tsv')


def num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def limits(root, obj):
    """{map: {metric: {sigma, mean, tapes}}} from the committed measurement-limits doc."""
    out, mapname = {}, None
    for line in read_text(root / obj['limits_doc']).splitlines():
        heading = re.match(r'^(#{2,3})\s+(\S+)\s*$', line)
        if heading:
            mapname = heading.group(2) if heading.group(1) == '###' else None
            continue
        if not mapname or not line.startswith('|') or line.startswith('|---'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 5 or cells[0] == 'metric':
            continue
        try:
            out.setdefault(mapname, {})[cells[0]] = dict(
                tapes=int(cells[2]), mean=float(cells[3]), sigma=float(cells[4]))
        except ValueError:
            continue
    return out


def mde(sigma, n, z=2.8):
    """Smallest difference in arm means detectable at n tapes a side (5% false positives, 80% power)."""
    return z * sigma * math.sqrt(2.0 / n) if n > 0 else math.inf


def tapes_needed(sigma, effect, z=2.8):
    """Tapes a side for an effect of this size to clear the detection limit."""
    if effect <= 0:
        return math.inf
    return max(2, math.ceil(2 * (z * sigma / effect) ** 2))


def git(root, *args):
    try:
        res = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout if res.returncode == 0 else None


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def installs(root):
    """Commits that changed the shipped binary, newest first: the install history."""
    out = []
    for line in (git(root, 'log', '--format=%H %cs %s', '--', 'game/argus/progs.dat') or '').splitlines():
        sha, date, subject = (line.split(' ', 2) + ['', ''])[:3]
        out.append(dict(commit=sha, date=date, subject=subject))
    return out


def build_on(date, history):
    """The install in force on a date, or None when the date predates the history."""
    if not date:
        return None
    for row in history:
        if row['date'] <= date:
            return row
    return None


def graph(root, mapname):
    path = root / 'src' / f'argus_nav_{mapname}.qc.json'
    if not path.is_file():
        return None
    doc = read_json(path)
    return dict(md5=md5(path), nodes=len(doc.get('nodes', [])), doc=doc)


LOG_STARTED = re.compile(r'^LOG started on: (\d{2})/(\d{2})/(\d{4})', re.M)


def tape_date(path, text=None):
    """YYYY-MM-DD from the tape's own header, else from its file name; the header is what a clone keeps."""
    m = LOG_STARTED.search(text if text is not None else read_text(path)[:400])
    if m:
        return f'{m.group(3)}-{m.group(1)}-{m.group(2)}'
    m = DATE.search(Path(path).name)
    return m.group(1) if m else None


def argnav(text):
    m = ARGNAV.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def skill_of(text):
    bases = sorted({int(b) for b in SKILL_BASE.findall(text)})
    if bases:
        return bases
    tiers = sorted({int(t) for t in SKILL_TIER.findall(text)})
    return tiers or None


def plural(n, word, many=None):
    return f'{n} {word if n == 1 else (many or word + "s")}'


def finding(area, severity, item, detail, fix=''):
    return dict(area=area, severity=severity, item=item, detail=detail, fix=fix)


def common_checkout(root):
    """The main checkout behind a worktree, which holds the machine-local maps, binaries and lab config."""
    out = git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if not out:
        return None
    common = Path(out.strip())
    parent = common.parent if common.name == '.git' else None
    return parent if parent and parent.resolve() != root.resolve() else None


def local_roots(root):
    return [r for r in (root, common_checkout(root)) if r]


def lab_binary(root):
    env = os.environ.get('ARGUS_LAB')
    if env and Path(env).is_file():
        return env
    for base in local_roots(root):
        for rel in ('tools/argus_mcp/target-stage/release', 'tools/argus_mcp/install/bin',
                    'tools/argus_mcp/target/release', 'tools/argus_mcp/target/debug'):
            for name in ('argus-mcp.exe', 'argus-mcp'):
                if (base / rel / name).is_file():
                    return str(base / rel / name)
    return shutil.which('argus-mcp')


def lab_env(root):
    """The environment argus-mcp needs, from the shell or the machine-local .mcp.json, reading this tree."""
    env = dict(os.environ)
    keys = ('ARGUS_FTEQCC', 'ARGUS_ENGINE', 'ARGUS_BASEDIR', 'ARGUS_PYTHON')
    if not all(env.get(k) for k in keys):
        for base in local_roots(root):
            path = base / '.mcp.json'
            if not path.is_file():
                continue
            try:
                server = read_json(path).get('mcpServers', {}).get('argus', {})
            except (OSError, ValueError):
                continue
            for k, v in (server.get('env') or {}).items():
                if k in keys and not env.get(k):
                    env[k] = v
            break
    env['ARGUS_ROOT'] = str(root)
    return env


def bsp_path(root, mapname):
    folders = [os.environ.get('ARGUS_MAPS')]
    for base in local_roots(root):
        folders += [base / 'maps_local', base / 'engine' / 'argus' / 'maps']
    for folder in folders:
        if folder and (Path(folder) / f'{mapname}.bsp').is_file():
            return Path(folder) / f'{mapname}.bsp'
    return None


def corpus_rows(root, names, mapname=None):
    """Tape-index rows for these runs: the cache first, then argus-mcp corpus, which parses the rest.

    Returns (rows by run, how each was found). Python never parses a tape's
    metrics itself; the Rust parser is the gate definition.
    """
    index = tape_index(root)
    rows = {n: index[n] for n in names if n in index}
    source = {n: 'index' for n in rows}
    missing = [n for n in names if n not in rows and (root / 'runs' / f'{n}.log').is_file()]
    lab = lab_binary(root) if missing else None
    if missing and lab:
        cmd = [lab, 'corpus'] + (['--map', mapname] if mapname else [])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                 env=lab_env(root), timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            res = None
        if res is not None and res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            head = lines[0].split(',') if lines else []
            for line in lines[1:]:
                row = dict(zip(head, line.split(',')))
                if row.get('run') in missing:
                    rows[row['run']] = row
                    source[row['run']] = 'parsed by argus-mcp corpus'
    return rows, source


# ---------------------------------------------------------------- validation

def validate(root):
    """Schema and reference errors in the objective and the claims; empty when sound."""
    errors = []
    try:
        obj = objective(root)
    except (OSError, ValueError) as exc:
        return [f'lab_objective.json: {exc}']
    for key in ('schema', 'status', 'tiers', 'calibration', 'hard_gates', 'goal_targets', 'labels',
                'metric_boundaries', 'limits_doc'):
        if key not in obj:
            errors.append(f'lab_objective.json: missing {key}')
    if obj.get('status') not in ('draft', 'signed'):
        errors.append('lab_objective.json: status must be draft or signed')
    if obj.get('status') == 'signed' and not obj.get('signed_off'):
        errors.append('lab_objective.json: a signed objective names who signed it and when in signed_off')
    header = set()
    card = root / 'runs' / 'human_scorecard.tsv'
    if card.is_file():
        first = read_text(card).splitlines()[:1]
        header = set(first[0].split('\t')) if first else set()
    gate_ids = set()
    for g in obj.get('hard_gates', []):
        gid = g.get('id', '?')
        if gid in gate_ids:
            errors.append(f'lab_objective.json: duplicate gate {gid}')
        gate_ids.add(gid)
        if 'scan' in g:
            if not g['scan'] or not all(isinstance(p, str) and p for p in g['scan']):
                errors.append(f'gate {gid}: scan must be a list of non-empty strings')
        elif 'column' in g:
            if ('max' in g) == ('below' in g):
                errors.append(f'gate {gid}: give exactly one of max or below')
            if header and g['column'] not in header:
                errors.append(f'gate {gid}: column {g["column"]} is not in runs/human_scorecard.tsv')
        else:
            errors.append(f'gate {gid}: needs scan or column')
    for key, target in obj.get('goal_targets', {}).items():
        if not (isinstance(target.get('low'), (int, float)) and isinstance(target.get('high'), (int, float))
                and target['low'] <= target['high']):
            errors.append(f'goal target {key}: needs numeric low <= high')
    for b in obj.get('metric_boundaries', []):
        if not DATE.fullmatch(str(b.get('date', ''))) or not b.get('metrics'):
            errors.append(f'metric boundary {b}: needs a YYYY-MM-DD date and metrics')
    if not (root / obj.get('limits_doc', '')).is_file():
        errors.append(f'lab_objective.json: limits_doc {obj.get("limits_doc")} does not exist')
    try:
        claims = own_claims(root)
    except (OSError, ValueError, KeyError) as exc:
        return errors + [f'lab_claims.json: {exc}']
    ids = set()
    registry = set()
    reg = root / 'tools' / 'refuted_claims.json'
    if reg.is_file():
        registry = {c['id'] for c in read_json(reg)['claims']}
    for c in claims:
        cid = c.get('id', '?')
        where = f'claim {cid}'
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', str(cid)):
            errors.append(f'{where}: id must be lower-case words joined by hyphens')
        if cid in ids:
            errors.append(f'{where}: duplicate id')
        if cid in registry:
            errors.append(f'{where}: already in refuted_claims.json, which is imported')
        ids.add(cid)
        for key in ('title', 'status', 'kind', 'statement', 'evidence'):
            if not c.get(key):
                errors.append(f'{where}: missing {key}')
        if c.get('status') not in STATUSES:
            errors.append(f'{where}: status must be one of {", ".join(STATUSES)}')
        if c.get('kind') not in KINDS:
            errors.append(f'{where}: kind must be one of {", ".join(KINDS)}')
        if c.get('tier') not in (None, 1, 2, 3, 4):
            errors.append(f'{where}: tier must be 1 to 4 or null')
        if 'cheapest_tier' in c and c['cheapest_tier'] not in TIERS:
            errors.append(f'{where}: cheapest_tier must be 1 to 5')
        if c.get('status') == 'fixed' and not DATE.fullmatch(str(c.get('fixed_on', ''))):
            errors.append(f'{where}: a fixed claim says when, as fixed_on YYYY-MM-DD')
        if c.get('kind') == 'graveyard' and c.get('status') not in ('refuted', 'parked'):
            errors.append(f'{where}: a graveyard entry is refuted or parked')
        if c.get('kind') == 'hypothesis' and c.get('status') == 'open' and not c.get('refute_by'):
            errors.append(f'{where}: an open hypothesis says what would refute it (refute_by)')
        for cell in c.get('cells', []):
            at = cell.get('at')
            if (not isinstance(cell.get('map'), str) or not isinstance(at, list) or len(at) != 3
                    or not all(isinstance(v, (int, float)) for v in at)
                    or not isinstance(cell.get('radius'), (int, float)) or cell['radius'] <= 0):
                errors.append(f'{where}: a cell is {{map, at: [x, y, z], radius > 0}}')
            elif cell['map'] not in c.get('maps', []):
                errors.append(f'{where}: cell map {cell["map"]} is not in maps')
        for ref in c.get('evidence', []):
            if not evidence_resolves(root, ref):
                errors.append(f'{where}: evidence {ref} does not resolve (a path, #n or a run in runs/)')
    return errors


def evidence_resolves(root, ref):
    ref = str(ref)
    if ISSUE.match(ref):
        return True
    if (root / ref).exists():
        return True
    return (root / 'runs' / f'{ref}.log').is_file()


# ---------------------------------------------------------------- sessions

def session_date(root, row, index):
    date = tape_date(root / 'runs' / row.get('file', ''))
    if date:
        return date
    started = index.get(Path(row.get('file', '')).stem, {}).get('started', '')
    m = DATE.search(started)
    return m.group(1) if m else None


def evaluate_session(root, row, obj, history, index):
    """Hard gates, goal measures and eligibility for one scorecard row."""
    path = root / 'runs' / row['file']
    text = read_text(path)
    gates = []
    for g in obj['hard_gates']:
        if 'scan' in g:
            hits = [l.strip() for l in text.splitlines() if any(p in l for p in g['scan'])] if text else None
            value = None if hits is None else len(hits)
            ok = None if value is None else value == 0
            note = hits[0][:100] if hits else ''
        else:
            value = num(row.get(g['column']))
            ok = None if value is None else (value <= g['max'] if 'max' in g else value < g['below'])
            note = ''
        gates.append(dict(id=g['id'], value=value, ok=ok, note=note))
    dur = num(row.get('dur')) or 0.0
    bk, hk = num(row.get('bot_kills_human')), num(row.get('human_kills_bot'))
    bk_pm = bk * 60 / dur if dur and bk is not None else None
    ratio = (hk / bk if bk else (math.inf if hk else None)) if hk is not None and bk is not None else None
    skill = skill_of(text)
    cal = obj['calibration']
    date = session_date(root, row, index)
    build = build_on(date, history)
    reasons = []
    if row.get('map') not in cal['goal_maps']:
        reasons.append(f'map {row.get("map")} is not a goal map')
    if dur < cal['min_session_sec']:
        reasons.append(f'{dur:.0f} s is under {cal["min_session_sec"]} s')
    if skill is None:
        reasons.append('the tape does not name its skill tier')
    elif skill != [cal['skill']]:
        reasons.append(f'skill {",".join(map(str, skill))}, not {cal["skill"]}')
    if bk_pm is None:
        reasons.append('no kill counts (no human in the obituaries)')
    return dict(file=row['file'], map=row.get('map'), date=date, dur=dur, skill=skill,
                build=build['commit'][:7] if build else None, gates=gates,
                failed=[g['id'] for g in gates if g['ok'] is False],
                unknown=[g['id'] for g in gates if g['ok'] is None],
                bk_pm=bk_pm, ratio=ratio, eligible=not reasons, reasons=reasons)


def band(value, target):
    if value is None:
        return 'unknown'
    if value < target['low']:
        return 'below target'
    if value > target['high']:
        return 'above target'
    return 'in target'


def goal_verdicts(sessions, obj, history):
    """Per goal map: the median goal measures over the last N eligible sessions on the installed build."""
    cal, targets = obj['calibration'], obj['goal_targets']
    current = history[0]['commit'][:7] if history else None
    out = {}
    for mapname in cal['goal_maps']:
        mine = [s for s in sessions if s['map'] == mapname and s['eligible']]
        on_build = [s for s in mine if s['build'] == current]
        need = cal['sessions_per_verdict']
        if len(on_build) < need:
            out[mapname] = dict(status='insufficient', have=len(on_build), need=need, build=current,
                                eligible_any_build=len(mine))
            continue
        recent = sorted(on_build, key=lambda s: s['date'] or '')[-need:]
        bk = statistics.median(s['bk_pm'] for s in recent)
        ratios = [s['ratio'] for s in recent if s['ratio'] is not None]
        ratio = statistics.median(ratios) if ratios else None
        out[mapname] = dict(status='measured', build=current, sessions=[s['file'] for s in recent],
                            bk_pm=bk, bk_band=band(bk, targets['bot_kills_human_pm']),
                            ratio=ratio, ratio_band=band(ratio, targets['kill_ratio']))
    return out


def sessions_report(root, obj, files=None, last=None):
    index = tape_index(root)
    history = installs(root)
    rows = scorecard(root)
    if files:
        wanted = {Path(f).name for f in files}
        known = {r['file'] for r in rows}
        rows = [r for r in rows if r['file'] in wanted]
        for name in sorted(wanted - known):
            path = Path(name) if Path(name).is_file() else root / 'runs' / name
            if path.is_file():
                rows.append({k: str(v) for k, v in argus_longi.analyse(str(path)).items()})
    if last:
        rows = rows[-last:]
    sessions = [evaluate_session(root, r, obj, history, index) for r in rows]
    all_sessions = [evaluate_session(root, r, obj, history, index) for r in scorecard(root)]
    return sessions, goal_verdicts(all_sessions, obj, history)


def fmt(value, digits=1):
    if value is None:
        return '-'
    if value == math.inf:
        return 'inf'
    return f'{value:.{digits}f}'


def print_sessions(sessions, verdicts, out=None):
    out = out or sys.stdout
    print('| Session | Map | Min | Skill | Gates failed | Bot kills/min | Kill ratio | Counts for goal |', file=out)
    print('| --- | --- | --- | --- | --- | --- | --- | --- |', file=out)
    for s in sessions:
        failed = ', '.join(s['failed']) or 'none'
        if s['unknown']:
            failed += f' (unknown: {", ".join(s["unknown"])})'
        skill = ','.join(map(str, s['skill'])) if s['skill'] else '?'
        counts = 'yes' if s['eligible'] else 'no: ' + '; '.join(s['reasons'])
        print(f'| {s["file"]} | {s["map"]} | {s["dur"] / 60:.1f} | {skill} | {failed} | {fmt(s["bk_pm"])} '
              f'| {fmt(s["ratio"])} | {counts} |', file=out)
    print(file=out)
    for mapname, v in verdicts.items():
        if v['status'] == 'insufficient':
            print(f'- {mapname}: no goal verdict yet; {v["have"]} of {v["need"]} skill-1 sessions on the '
                  f'installed build {v["build"]} ({v["eligible_any_build"]} eligible on any build).', file=out)
        else:
            print(f'- {mapname}: bot kills {fmt(v["bk_pm"], 2)} a minute ({v["bk_band"]}), kill ratio '
                  f'{fmt(v["ratio"], 2)} ({v["ratio_band"]}), over {", ".join(v["sessions"])}.', file=out)


# ---------------------------------------------------------------- staleness

def stale_findings(root, obj):
    out = []
    index = tape_index(root)
    runs = root / 'runs'

    # Tapes the corpus cache has not persisted: every query parses them again.
    match_tapes = [p.stem for p in runs.glob('*.log') if b'ARGLOG ' in p.read_bytes()[:200000]]
    unindexed = sorted(t for t in match_tapes if t not in index)
    if unindexed:
        out.append(finding('tape index', 'info', 'runs/tape_index.tsv',
                           f'{len(unindexed)} match tapes are parsed on demand by every corpus query, '
                           f'e.g. {", ".join(unindexed[:3])}',
                           'argus-mcp corpus --write persists them and makes queries fast'))

    # Baselines: a verdict is only as current as the tape it is measured against.
    path = runs / 'baselines.json'
    baselines = read_json(path) if path.is_file() else {}
    for mapname, names in sorted(baselines.items()):
        names = [names] if isinstance(names, str) else names
        g = graph(root, mapname)
        for name in names:
            row = index.get(name)
            if not (runs / f'{name}.log').is_file():
                out.append(finding('baseline', 'void', f'{mapname}: {name}', 'the baseline tape is missing',
                                   f'pick a new baseline with baseline_set for {mapname}'))
                continue
            if row is None:
                out.append(finding('baseline', 'stale', f'{mapname}: {name}', 'the baseline is not in the corpus index',
                                   'argus-mcp corpus --rebuild --write'))
            elif row.get('tick_class') != 'listen':
                out.append(finding('baseline', 'void', f'{mapname}: {name}',
                                   f'recorded at {row.get("tick_class")}, not the played rate, so verdicts against it are void',
                                   f'record three listen-class tapes and point baselines.json {mapname} at them'))
            banner = argnav(read_text(runs / f'{name}.log'))
            if g and banner and banner[0] != g['nodes']:
                out.append(finding('baseline', 'stale', f'{mapname}: {name}',
                                   f'ran a {banner[0]}-node graph; the shipped graph has {g["nodes"]}',
                                   're-baseline on the current graph'))

    # Benchmark suites pin the graph they were written for.
    for suite in sorted((root / 'benchmarks').glob('*.json')):
        doc = read_json(suite)
        g = graph(root, doc.get('map', ''))
        if g is None:
            out.append(finding('benchmark', 'void', suite.name, f'no shipped graph for {doc.get("map")}'))
        elif doc.get('graph_md5') != g['md5']:
            out.append(finding('benchmark', 'stale', suite.name,
                               f'pins graph {str(doc.get("graph_md5"))[:8]}, the shipped {doc["map"]} graph is {g["md5"][:8]}',
                               'check each task still starts and ends on the graph, then re-pin graph_md5'))

    # Puppet convictions: a refused link still shipped, or a verdict whose endpoints left the graph.
    for side in sorted((root / 'src').glob('argus_nav_*.probe.json')):
        mapname = side.name[len('argus_nav_'):-len('.probe.json')]
        g = graph(root, mapname)
        if g is None:
            continue
        doc = g['doc']
        nodes = doc.get('nodes', [])

        def node_at(p):
            for i, n in enumerate(nodes):
                if all(abs(a - b) <= 1.0 for a, b in zip(n, p)):
                    return i
            return None

        walks = {tuple(l[:2]) for l in doc.get('links', [])}
        typed = {tuple(l[:2]) for key in ('jlinks', 'doorlinks', 'rjlinks', 'sprintlinks') for l in doc.get(key, [])}
        verdicts = read_json(side)
        # A sweep stamps its server mode, and the modes disagree (#310): a
        # conviction from a co-op sweep says nothing about deathmatch.
        modes = verdicts.get('modes') or {'unstamped': {'failed': verdicts.get('failed', [])}}
        for mode, body in sorted(modes.items()):
            failed = body.get('failed', [])
            shipped, orphans = [], 0
            for a, b in failed:
                ia, ib = node_at(a), node_at(b)
                if ia is None or ib is None:
                    orphans += 1
                elif (ia, ib) in walks and (ia, ib) not in typed:
                    shipped.append(f'n{ia}->n{ib}')
            label = side.name if mode == 'unstamped' else f'{side.name} ({mode} sweep)'
            if shipped:
                out.append(finding('verdicts', 'stale', label,
                                   f'{plural(len(shipped), "link")} the puppet refused still shipped as plain walks, '
                                   f'e.g. {", ".join(shipped[:3])}',
                                   f'regenerate {mapname} so navgen reminds or drops them, with its own ladder'))
            if orphans:
                out.append(finding('verdicts', 'info', label,
                                   f'{orphans} of {len(failed)} convictions name endpoints no longer in the graph, '
                                   'so a regeneration already consumed or outlived them'))

    # Sessions nobody scored, and scored rows the current tool could fill further.
    rows = scorecard(root)
    scored = {r['file'] for r in rows}
    unscored = sorted(p.name for p in runs.glob('shane_*.log') if p.name not in scored)
    if unscored:
        out.append(finding('scorecard', 'stale', 'runs/human_scorecard.tsv',
                           f'{plural(len(unscored), "session tape")} not scored, e.g. {", ".join(unscored[:3])}',
                           'python tools/argus_longi.py --append runs/human_scorecard.tsv <tape>'))
    for g in obj['hard_gates']:
        col = g.get('column')
        if col and rows and col in rows[0]:
            blank = [r['file'] for r in rows if r.get(col, '') == '' and num(r.get('bot_world')) != 0]
            if blank and col == 'bot_world_unforced':
                out.append(finding('scorecard', 'info', col, f'{len(blank)} rows have no value (no BSP when scored)'))

    # The measurement limits are a snapshot; tapes recorded since can move them.
    m = DATE.search(obj['limits_doc'])
    if m:
        since = [r for r in index.values() if r.get('kind') == 'bot' and r.get('tick_class') == 'listen'
                 and r.get('started', '')[:10] > m.group(1)]
        if len(since) >= 10:
            out.append(finding('limits', 'stale', obj['limits_doc'],
                               f'{len(since)} listen-class bot tapes recorded since the limits were measured',
                               'argus-mcp measure --write ' + obj['limits_doc']))

    # The installed binary against the source it was built from.
    history = installs(root)
    if history:
        since = (git(root, 'log', '--format=%h %s', f'{history[0]["commit"]}..HEAD', '--', 'src') or '').splitlines()
        if since:
            out.append(finding('install', 'info', 'game/argus/progs.dat',
                               f'installed on {history[0]["date"]}; {plural(len(since), "commit")} changed src/ since: '
                               + '; '.join(since[:3]),
                               'compile and install when a human session should test them'))

    if obj.get('status') != 'signed':
        out.append(finding('objective', 'info', 'tools/lab_objective.json',
                           'the objective is a draft; goal targets are not signed off'))
    return out


def print_findings(findings, out=None):
    out = out or sys.stdout
    if not findings:
        print('Nothing stale.', file=out)
        return
    order = {s: i for i, s in enumerate(SEVERITIES)}
    for f in sorted(findings, key=lambda f: (order[f['severity']], f['area'], f['item'])):
        line = f'- {f["severity"].upper()} {f["area"]}: {f["item"]}: {f["detail"]}'
        if f['fix']:
            line += f'. Fix: {f["fix"]}'
        print(line, file=out)


# ---------------------------------------------------------------- skeptic

def boundaries_crossed(obj, metric, dates):
    dates = [d for d in dates if d]
    if not dates:
        return []
    lo, hi = min(dates), max(dates)
    return [b for b in obj['metric_boundaries'] if metric in b['metrics'] and lo < b['date'] <= hi]


def skeptic(root, arm_a, arm_b, metrics=None, obj=None):
    """Every reason the comparison of arm_a (control) with arm_b cannot be read at face value."""
    obj = obj or objective(root)
    void, confounds, notes = [], [], []
    names = list(dict.fromkeys(arm_a + arm_b))
    overlap = sorted(set(arm_a) & set(arm_b))
    if overlap:
        void.append(f'the same tape is in both arms: {", ".join(overlap)}')
    known = tape_index(root)
    guess = next((known[n]['map'] for n in names if n in known), None)
    if guess is None:
        m = re.match(r'^(?:ab|band|mx|smoke|nm|rep)_([a-z0-9]+)_', names[0]) if names else None
        guess = m.group(1) if m else None
    found, source = corpus_rows(root, names, guess)
    missing = [n for n in names if n not in found]
    if missing:
        void.append(f'no corpus row for {", ".join(missing)}: not in runs/, or no argus-mcp binary to parse it')
    parsed = [n for n, s in source.items() if s != 'index']
    if parsed:
        notes.append(f'{plural(len(parsed), "tape")} not in the index, parsed by argus-mcp corpus')
    rows_a = [found[r] for r in arm_a if r in found]
    rows_b = [found[r] for r in arm_b if r in found]
    rows = rows_a + rows_b
    if not rows_a or not rows_b:
        void.append('one arm has no indexed tapes')
        return dict(verdict='void', void=void, confounds=confounds, notes=notes, metrics={})
    maps = sorted({r['map'] for r in rows})
    if len(maps) > 1:
        void.append(f'the arms span maps {", ".join(maps)}')
    kinds = sorted({r.get('kind') for r in rows})
    if kinds != ['bot']:
        void.append(f'tape kinds {", ".join(map(str, kinds))}: human and fixture tapes never enter a bot comparison')
    ticks = sorted({r.get('tick_class') for r in rows})
    if len(ticks) > 1:
        void.append(f'tick classes differ ({", ".join(map(str, ticks))}): a rate change before it is a behaviour change')
    elif ticks != ['listen']:
        notes.append(f'recorded at {ticks[0]}, not the played rate')

    def per_arm(names, reader):
        return {n: reader(read_text(root / 'runs' / f'{n}.log')) for n in names}

    banners_a, banners_b = per_arm(arm_a, argnav), per_arm(arm_b, argnav)
    set_a, set_b = set(banners_a.values()) - {None}, set(banners_b.values()) - {None}
    if len(set_a) > 1 or len(set_b) > 1:
        confounds.append('graphs differ inside an arm: ' + '; '.join(
            f'{n} {b[0]} nodes' for n, b in {**banners_a, **banners_b}.items() if b))
    elif set_a and set_b and set_a != set_b:
        a, b = next(iter(set_a)), next(iter(set_b))
        confounds.append(f'the arms ran different graphs ({a[0]} against {b[0]} nodes); '
                         'only a graph change may differ this way')
    skills_a = {tuple(s) for s in per_arm(arm_a, skill_of).values() if s}
    skills_b = {tuple(s) for s in per_arm(arm_b, skill_of).values() if s}
    if skills_a and skills_b and skills_a != skills_b:
        confounds.append(f'skill tiers differ: {sorted(skills_a)} against {sorted(skills_b)}')
    durs = [num(r.get('duration_sec')) or 0 for r in rows]
    rates = bool(durs) and min(durs) > 0 and max(durs) / min(durs) > 1.1
    if rates:
        notes.append(f'durations run {min(durs):.0f} to {max(durs):.0f} s; per-minute rates are compared, '
                     'with spread taken from these arms because the limits doc is per tape')
    if len(arm_a) < 2 or len(arm_b) < 2:
        notes.append('one tape a side: no spread to measure, and the stall band floor is zero')

    lim = limits(root, obj).get(maps[0], {}) if len(maps) == 1 else {}
    dates = [r.get('started', '')[:10] for r in rows]
    results = {}
    for metric in metrics or LIMIT_METRICS:
        va = [num(r.get(metric)) for r in rows_a]
        vb = [num(r.get(metric)) for r in rows_b]
        if any(v is None for v in va + vb):
            results[metric] = dict(effect='not in the index')
            continue
        if rates:
            va = [v * 60 / num(r.get('duration_sec')) for v, r in zip(va, rows_a)]
            vb = [v * 60 / num(r.get('duration_sec')) for v, r in zip(vb, rows_b)]
        mean_a, mean_b = statistics.fmean(va), statistics.fmean(vb)
        n = min(len(va), len(vb))
        source = 'limits doc'
        sigma = lim.get(metric, {}).get('sigma')
        if sigma is None or rates:
            if len(va) >= 2 and len(vb) >= 2:
                sigma = math.sqrt((statistics.variance(va) * (len(va) - 1) + statistics.variance(vb) * (len(vb) - 1))
                                  / (len(va) + len(vb) - 2))
                source = 'these arms only'
            else:
                sigma, source = None, 'unknown'
        limit = mde(sigma, n, obj.get('mde_z', 2.8)) if sigma else None
        delta = mean_b - mean_a
        if limit is None and delta == 0:
            effect = 'no change'
        elif limit is None:
            effect = 'unmeasurable: no spread known' if sigma is None else 'unmeasurable: no spread in the data'
        elif abs(delta) > limit:
            effect = 'moved'
        else:
            effect = 'no detectable effect'
        crossed = boundaries_crossed(obj, metric, dates)
        results[metric] = dict(a=mean_a, b=mean_b, delta=delta, limit=limit, sigma_from=source, n=n, effect=effect,
                               boundaries=[f'{b["date"]}: {b["what"]}' for b in crossed])
        if crossed:
            confounds.append(f'{metric} crosses a metric boundary: ' + '; '.join(results[metric]['boundaries']))
    verdict = 'void' if void else ('caveated' if confounds else 'clean')
    return dict(verdict=verdict, void=void, confounds=confounds, notes=notes, metrics=results,
                map=maps[0] if len(maps) == 1 else None, arm_a=arm_a, arm_b=arm_b)


def print_skeptic(rep, out=None):
    out = out or sys.stdout
    print(f'Verdict: {rep["verdict"]}', file=out)
    for key, label in (('void', 'Void'), ('confounds', 'Confound'), ('notes', 'Note')):
        for line in rep[key]:
            print(f'- {label}: {line}', file=out)
    if rep['metrics']:
        print(file=out)
        print('| Metric | Control | Candidate | Change | Detection limit | Reading |', file=out)
        print('| --- | --- | --- | --- | --- | --- |', file=out)
        for metric, m in rep['metrics'].items():
            if 'a' not in m:
                print(f'| {metric} | - | - | - | - | {m["effect"]} |', file=out)
                continue
            lim = f'{m["limit"]:.1f} ({m["sigma_from"]}, n={m["n"]})' if m['limit'] is not None else '-'
            print(f'| {metric} | {m["a"]:.1f} | {m["b"]:.1f} | {m["delta"]:+.1f} | {lim} | {m["effect"]} |', file=out)


# ---------------------------------------------------------------- triage

def triage(root, tape_path, claims=None, radius=96.0):
    """Cluster a tape's stalls, freezes and world deaths, and name the claim each cluster belongs to."""
    tape = argus_tape.read_tape(str(tape_path))
    text = '\n'.join(line for _, line in tape.lines)
    mapname = argus_tape.map_name(text)
    recorded = tape_date(tape_path)
    bots, _, _ = argus_tape.track_names(tape.samples, tape.events)
    bots = set(bots)
    samples = {n: sorted(rows, key=lambda r: r['line']) for n, rows in tape.samples.items()}
    lines = {n: [r['line'] for r in rows] for n, rows in samples.items()}
    points = []

    def where(name, line):
        rows = samples.get(name, [])
        i = bisect.bisect_left(lines.get(name, []), line) - 1
        return rows[i] if i >= 0 else None

    bsp = bsp_path(root, mapname) if mapname else None
    contents = argus_longi._classifier(str(bsp)) if bsp else None
    lives = collections.defaultdict(int)
    for line, name, verb, rest in tape.events:
        if name not in bots:
            continue
        if verb in ('spawned', 'respawn'):
            lives[name] = line
        elif verb == 'stall':
            s = where(name, line)
            if s:
                points.append(dict(kind='stall', bot=name, x=s['x'], y=s['y'], z=s['z']))
        elif verb == 'death':
            d = next(iter(argus_tape.deaths([(line, name, verb, rest)])), None)
            if d is None:
                continue
            if d[2] == 'world':
                life = [r for r in samples.get(name, []) if lives[name] < r['line'] < line]
                pos = dict(x=d[3], y=d[4], z=d[5])
                verdict = argus_longi.world_death_unforced(life, contents, pos) if contents else None
                kind = 'unforced death' if verdict else ('knock-in' if verdict is False else 'world death')
                points.append(dict(kind=kind, bot=name, **pos))
            lives[name] = line
    for name in bots:
        for f in argus_tape.freeze_windows(samples.get(name, [])):
            kind = 'freeze under fire' if f.hp_drop > 0 else 'freeze'
            points.append(dict(kind=kind, bot=name, x=f.start['x'], y=f.start['y'], z=f.start['z']))

    clusters = []
    for p in points:
        for c in clusters:
            if math.dist((p['x'], p['y'], p['z']), c['centre']) <= radius:
                c['points'].append(p)
                k = len(c['points'])
                c['centre'] = tuple((c['centre'][i] * (k - 1) + v) / k for i, v in enumerate((p['x'], p['y'], p['z'])))
                break
        else:
            clusters.append(dict(centre=(p['x'], p['y'], p['z']), points=[p]))
    claims = claims if claims is not None else all_claims(root)
    out = []
    for c in clusters:
        kinds = collections.Counter(p['kind'] for p in c['points'])
        matches = []
        for cl in claims:
            for cell in cl.get('cells', []):
                if cell['map'] == mapname and math.dist(c['centre'], cell['at']) <= cell['radius'] + 32:
                    matches.append(dict(id=cl['id'], status=cl['status'], fixed_on=cl.get('fixed_on')))
                    break
        severe = kinds['freeze under fire'] + kinds['unforced death'] + kinds['freeze']
        flag = 'new'
        if matches:
            flag = 'known'
            fixed = [m for m in matches if m['status'] == 'fixed']
            if fixed and len(matches) == len(fixed):
                # Trouble at a fixed cell is a regression only on a tape recorded after the fix.
                # A stall or two can recur at any cell; a regression needs a freeze,
                # an unforced death, or REGRESSION_COUNT events.
                heavy = severe > 0 or len(c['points']) >= REGRESSION_COUNT
                after = [m for m in fixed if recorded and m['fixed_on'] and recorded > m['fixed_on']]
                if not recorded:
                    flag = 'regression? (undated tape)' if heavy else 'known'
                elif after:
                    flag = 'regression?' if heavy else 'known'
                else:
                    flag = 'before the fix'
        out.append(dict(centre=[round(v) for v in c['centre']], count=len(c['points']), kinds=dict(kinds),
                        bots=sorted({p['bot'] for p in c['points']}), matches=matches, flag=flag,
                        severe=severe))
    out.sort(key=lambda c: (-c['severe'], -c['count']))
    return dict(tape=str(tape_path), map=mapname, date=recorded, bsp=bool(contents), clusters=out)


def print_triage(rep, min_count=3, out=None):
    out = out or sys.stdout
    print(f'Triage of {Path(rep["tape"]).name} on {rep["map"]}, recorded {rep.get("date") or "on an unknown date"}'
          + ('' if rep['bsp'] else ' (no BSP: world deaths are not split into knock-ins and unforced)'), file=out)
    shown = [c for c in rep['clusters'] if c['count'] >= min_count or c['severe']]
    if not shown:
        print('No cluster of trouble.', file=out)
        return
    print('| Where | Count | What | Bots | Claim | Reading |', file=out)
    print('| --- | --- | --- | --- | --- | --- |', file=out)
    for c in shown:
        what = ', '.join(f'{k} {v}' for k, v in sorted(c['kinds'].items()))
        claim = ', '.join(f'{m["id"]} ({m["status"]})' for m in c['matches']) or '-'
        print(f'| {" ".join(map(str, c["centre"]))} | {c["count"]} | {what} | {", ".join(c["bots"])} | {claim} '
              f'| {c["flag"]} |', file=out)


def review(root, path, out=None):
    """One fresh session: its hard gates, whether it counts for a goal verdict, and its untriaged trouble.

    The harvester calls this after scoring, so a session is read against the
    objective and the claims the moment it lands, not when someone remembers.
    """
    out = out or sys.stdout
    obj = objective(root)
    path = Path(path)
    row = next((r for r in scorecard(root) if r['file'] == path.name), None)
    if row is None:
        row = {k: str(v) for k, v in argus_longi.analyse(str(path)).items()}
    s = evaluate_session(root, row, obj, installs(root), tape_index(root))
    failed = ', '.join(s['failed']) or 'none'
    print(f'gates failed: {failed}' + (f' (unknown: {", ".join(s["unknown"])})' if s['unknown'] else ''), file=out)
    if s['bk_pm'] is not None:
        print(f'bot kills on the human {fmt(s["bk_pm"], 2)} a minute, kill ratio {fmt(s["ratio"], 2)}', file=out)
    print('counts for a goal verdict' if s['eligible'] else 'does not count for a goal verdict: ' + '; '.join(s['reasons']),
          file=out)
    rep = triage(root, path)
    worth = [c for c in rep['clusters'] if c['flag'] in ('new', 'regression?', 'regression? (undated tape)')
             and (c['count'] >= 3 or c['severe'])]
    for c in worth:
        what = ', '.join(f'{k} {v}' for k, v in sorted(c['kinds'].items()))
        print(f'{c["flag"]}: {" ".join(map(str, c["centre"]))}: {what}', file=out)
    if not worth:
        print('no new or regressed cluster of trouble', file=out)
    return s, worth


# ---------------------------------------------------------------- claims and ledger

def print_claims(claims, out=None):
    out = out or sys.stdout
    print('| Claim | Status | Kind | Tier | Cheapest test | Title |', file=out)
    print('| --- | --- | --- | --- | --- | --- |', file=out)
    for c in claims:
        cheap = TIERS.get(c.get('cheapest_tier'), '-')
        tier = c.get('tier') if c.get('tier') is not None else '-'
        print(f'| {c["id"]} | {c["status"]} | {c["kind"]} | {tier} | {cheap} | {c["title"]} |', file=out)


def studies(root):
    out = []
    for path in sorted((root / 'runs').glob('*.results.json')):
        try:
            doc = read_json(path)
        except (OSError, ValueError) as exc:
            out.append(dict(file=path.name, error=str(exc)))
            continue
        if not isinstance(doc, dict):
            out.append(dict(file=path.name, schema=None))
            continue
        status = doc.get('status') or doc.get('verdict') or doc.get('decision')
        if isinstance(status, dict):
            status = status.get('status') or status.get('verdict') or 'see file'
        out.append(dict(file=path.name, schema=doc.get('schema') or doc.get('schema_version'),
                        status=status if isinstance(status, (str, type(None))) else 'see file',
                        source_sha256=doc.get('source_sha256')))
    return out


def ledger(root, obj=None):
    obj = obj or objective(root)
    index = tape_index(root)
    head = (git(root, 'log', '-1', '--format=%H %cs %s') or '').strip()
    installed = {}
    for rel in ('game/argus/progs.dat', 'engine/argus/progs.dat', 'lq1/progs.dat'):
        if (root / rel).is_file():
            installed[rel] = md5(root / rel)
    graphs = {}
    for path in sorted((root / 'src').glob('argus_nav_*.qc.json')):
        mapname = path.name[len('argus_nav_'):-len('.qc.json')]
        g = graph(root, mapname)
        graphs[mapname] = dict(id=f'{mapname}@{g["md5"]}', nodes=g['nodes'])
    tapes = collections.Counter((r.get('kind'), r.get('tick_class')) for r in index.values())
    claims = all_claims(root)
    return dict(
        generated=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        head=head, installed=installed, installs=installs(root)[:5], graphs=graphs,
        objective=dict(status=obj['status'], signed_off=obj.get('signed_off')),
        tapes=[dict(kind=k, tick_class=t, count=n) for (k, t), n in sorted(tapes.items(), key=str)],
        scorecard_rows=len(scorecard(root)),
        claims=dict(collections.Counter(c['status'] for c in claims)),
        studies=studies(root),
        benchmarks=[dict(file=p.name, map=read_json(p).get('map'), graph_md5=read_json(p).get('graph_md5'))
                    for p in sorted((root / 'benchmarks').glob('*.json'))],
        baselines=read_json(root / 'runs' / 'baselines.json') if (root / 'runs' / 'baselines.json').is_file() else {},
        stale=stale_findings(root, obj))


# ---------------------------------------------------------------- state

def state(root, out=None):
    out = out or sys.stdout
    obj = objective(root)
    head = (git(root, 'log', '-1', '--format=%h %s') or '?').strip()
    now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print('# Argus lab state', file=out)
    print(file=out)
    print(f'Generated {now} at {head}. Rebuild with `python tools/argus_lab.py state`.', file=out)
    print(file=out)

    print('## Build', file=out)
    print(file=out)
    history = installs(root)
    game = root / 'game' / 'argus' / 'progs.dat'
    engine = root / 'engine' / 'argus' / 'progs.dat'
    if game.is_file():
        g = md5(game).upper()
        same = engine.is_file() and md5(engine).upper() == g
        print(f'- Gameplay binary MD5 `{g}`; the engine copy {"matches" if same else "DIFFERS"}.', file=out)
        status = re.search(r'\| Gameplay binary \|.*?MD5 `([0-9A-F]{32})`', read_text(root / 'CHANGELOG.md'))
        if status:
            print(f'- The changelog status table names `{status.group(1)}`: '
                  f'{"matches" if status.group(1) == g else "DIFFERS"}.', file=out)
    if history:
        top = history[0]
        since = (git(root, 'log', '--format=%h', f'{top["commit"]}..HEAD', '--', 'src') or '').split()
        print(f'- Installed by {top["commit"][:7]} on {top["date"]} ({top["subject"]}); '
              + (f'{plural(len(since), "commit")} changed src/ since.' if since else 'src/ is unchanged since.'), file=out)
    print(file=out)

    print('## Objective', file=out)
    print(file=out)
    if obj['status'] == 'signed':
        print(f'- Signed off: {obj["signed_off"]}.', file=out)
    else:
        print('- Draft, not signed off: goal targets in `tools/lab_objective.json` are proposals.', file=out)
    print(file=out)

    print('## Human sessions', file=out)
    print(file=out)
    sessions, verdicts = sessions_report(root, obj, last=5)
    print_sessions(sessions, verdicts, out)
    print(file=out)

    print('## Stale artefacts', file=out)
    print(file=out)
    findings = stale_findings(root, obj)
    counts = collections.Counter(f['severity'] for f in findings)
    print(f'{counts["void"]} void, {counts["stale"]} stale, {counts["info"]} for information. '
          'Void means a verdict that depends on it cannot be trusted.', file=out)
    print(file=out)
    print_findings(findings, out)
    print(file=out)

    print('## Claims', file=out)
    print(file=out)
    claims = all_claims(root)
    by = collections.Counter(c['status'] for c in claims)
    print(', '.join(f'{by[s]} {s}' for s in STATUSES if by[s]) + '.', file=out)
    print(file=out)
    opened = sorted((c for c in claims if c['status'] == 'open'),
                    key=lambda c: (c.get('cheapest_tier') or 9, c.get('tier') or 9, c['id']))
    print_claims(opened, out)
    print(file=out)

    print('## Next', file=out)
    print(file=out)
    for c in opened[:3]:
        step = c.get('next') or c.get('refute_by') or c['statement']
        refs = ', '.join(e for e in c.get('evidence', []) if ISSUE.match(str(e)))
        print(f'- {c["id"]} ({TIERS.get(c.get("cheapest_tier"), "untiered")}{", " + refs if refs else ""}): {step}',
              file=out)


# ---------------------------------------------------------------- pyramid

def pyramid_plan(root, maps, through, obj, effect_pct=30.0):
    """The tier steps for these maps: each a dict with a command or a reason it cannot run."""
    py = sys.executable
    lab = lab_binary(root)
    steps = [dict(tier=1, name='repo invariants', cmd=[py, 'tools/argus_ci.py', 'all']),
             dict(tier=1, name='claims and objective', cmd=[py, 'tools/argus_lab.py', '--root', str(root), 'claims', '--check'])]
    for m in maps:
        bsp = bsp_path(root, m)
        g = graph(root, m)
        if g is None:
            steps.append(dict(tier=1, name=f'{m} graph', skip=f'no src/argus_nav_{m}.qc.json'))
            continue
        if bsp:
            steps.append(dict(tier=1, name=f'{m} navmesh audit', audit=(str(bsp), str(root / 'src' / f'argus_nav_{m}.qc.json'))))
            steps.append(dict(tier=1, name=f'{m} directed reach', cmd=[py, 'tools/argus_reach.py', m],
                              env={'ARGUS_MAPS': str(bsp.parent)}))
        else:
            for name in ('navmesh audit', 'directed reach'):
                steps.append(dict(tier=1, name=f'{m} {name}', skip='no BSP (set ARGUS_MAPS or keep maps_local/)'))
    if through >= 2:
        for suite in sorted((root / 'benchmarks').glob('*.json')):
            doc = read_json(suite)
            if doc.get('map') not in maps:
                continue
            g = graph(root, doc['map'])
            if g is None or doc.get('graph_md5') != g['md5']:
                steps.append(dict(tier=2, name=f'benchmark {suite.name}', skip='suite pins a graph that is no longer shipped', blocks=True))
            elif not lab:
                steps.append(dict(tier=2, name=f'benchmark {suite.name}', skip='no argus-mcp binary (set ARGUS_LAB)'))
            else:
                steps.append(dict(tier=2, name=f'benchmark {suite.name}', cmd=[lab, 'benchmark', str(suite), '--no-compile'],
                                  judge='benchmark', graph_md5=g['md5']))
    if through >= 4:
        lim = limits(root, obj)
        for m in maps:
            for metric in ('stalls', 'engages', 'lava_deaths'):
                row = lim.get(m, {}).get(metric)
                if not row:
                    continue
                n = tapes_needed(row['sigma'], row['mean'] * effect_pct / 100, obj.get('mde_z', 2.8))
                steps.append(dict(tier=4, name=f'{m} ladder for {metric}',
                                  plan=f'{n} listen-class tapes a side see a {effect_pct:.0f}% change in {metric} '
                                       f'(sigma {row["sigma"]}, mean {row["mean"]}); run with experiment or argus-mcp match'))
    return [s for s in steps if s['tier'] <= through]


def benchmark_report(stdout):
    """The JSON report argus-mcp benchmark prints after its progress lines, or None."""
    start = stdout.find('\n{')
    start = 0 if stdout.startswith('{') else (start + 1 if start >= 0 else -1)
    if start < 0:
        return None
    try:
        return json.loads(stdout[start:])
    except ValueError:
        return None


def previous_completions(root, name, graph_md5):
    """Tasks a passing earlier run of this suite completed on this graph: the bar a new run must hold."""
    for path in sorted((root / 'runs' / 'lab').glob('pyramid-*.json'), reverse=True):
        try:
            steps = read_json(path).get('steps', [])
        except (OSError, ValueError):
            continue
        for s in steps:
            if s.get('name') == name and s.get('graph_md5') == graph_md5 and s.get('completed') is not None:
                return set(s['completed']), path.name
    return None, None


def judge_benchmark(root, step, stdout):
    """Pass unless a task the graph used to finish no longer finishes; the first run sets the bar."""
    report = benchmark_report(stdout)
    if report is None:
        return False, 'no benchmark report in the output', None
    done = sorted(r['name'] for r in report.get('results', []) if r.get('completed'))
    total = len(report.get('results', []))
    before, receipt = previous_completions(root, step['name'], step['graph_md5'])
    summary = f'{len(done)} of {total} tasks completed'
    if before is None:
        return True, summary + '; the first run on this graph sets the bar', done
    lost = sorted(before - set(done))
    if lost:
        return False, summary + f'; no longer completes {", ".join(lost)} (completed in {receipt})', done
    gained = sorted(set(done) - before)
    return True, summary + (f'; newly completes {", ".join(gained)}' if gained else '; holds the bar'), done


def run_audit(bsp, nav):
    import argus_navmesh
    mesh_bsp, frags, _ = argus_navmesh.load_mesh(bsp)
    r = argus_navmesh.audit(mesh_bsp, frags, read_json(nav))
    bad = dict(liquid_entries=len(r['liquid_entries']), vertical_walks=len(r['vertical_walks']))
    return all(v == 0 for v in bad.values()), bad


def run_step(root, s, dry_run=False):
    """Run one tier step and return its result row: pass, fail, skipped, blocked, planned or dry run."""
    if 'skip' in s:
        return dict(s, status='blocked' if s.get('blocks') else 'skipped', detail=s['skip'])
    if 'plan' in s:
        return dict(s, status='planned', detail=s['plan'])
    if dry_run:
        what = ' '.join(s['cmd']) if 'cmd' in s else f'navmesh audit of {s["audit"][0]}'
        return dict(s, status='dry run', detail=f'would run {what}')
    if 'audit' in s:
        ok, detail = run_audit(*s['audit'])
        return dict(s, status='pass' if ok else 'fail', detail=detail)
    env = lab_env(root) if s['cmd'][0] == lab_binary(root) else dict(os.environ)
    env.update(s.get('env', {}))
    res = subprocess.run(s['cmd'], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    tail = (res.stdout + res.stderr).strip().splitlines()[-3:]
    row = dict(s, status='pass' if res.returncode == 0 else 'fail', returncode=res.returncode,
               detail=' | '.join(tail) if res.returncode else '')
    if res.returncode == 0 and s.get('judge') == 'benchmark':
        ok, detail, done = judge_benchmark(root, s, res.stdout)
        row.update(status='pass' if ok else 'fail', detail=detail, completed=done if ok else None)
    return row


def show_step(row, out):
    label = f'tier {row["tier"]} {row["name"]}'
    status = {'pass': 'pass', 'fail': 'FAIL'}.get(row['status'], row['status'])
    detail = row.get('detail')
    if row['status'] in ('skipped', 'blocked'):
        print(f'- {label}: {status} ({detail})', file=out)
    elif row['status'] in ('planned', 'dry run'):
        print(f'- {label}: {detail}', file=out)
    else:
        print(f'- {label}: {status}' + (f', {detail}' if detail else ''), file=out)


def write_receipt(root, kind, body):
    folder = root / 'runs' / 'lab'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = folder / f'{kind}-{stamp}.json'
    body = dict(head=(git(root, 'rev-parse', 'HEAD') or '').strip(), **body)
    path.write_text(json.dumps(body, indent=1, default=str), encoding='utf-8')
    return path


def pyramid(root, maps, through=2, dry_run=False, out=None, receipt=True):
    """Climb the tiers for one change and stop at the first that refutes it."""
    out = out or sys.stdout
    steps = pyramid_plan(root, maps, through, objective(root))
    results = []
    stopped = None
    for s in steps:
        row = run_step(root, s, dry_run)
        results.append(row)
        show_step(row, out)
        if row['status'] == 'fail':
            stopped = s['tier']
            print(f'Stopped at tier {stopped}: a cheaper tier refuted the change, so nothing above it runs.', file=out)
            break
    blocked = [r for r in results if r['status'] == 'blocked']
    if blocked and stopped is None:
        print(f'{plural(len(blocked), "step")} blocked by stale artefacts; see `argus_lab.py stale`.', file=out)
    if receipt and not dry_run:
        path = write_receipt(root, 'pyramid', dict(maps=maps, through=through, stopped=stopped, steps=results))
        print(f'Receipt: {path.relative_to(root)}', file=out)
    return 1 if stopped else 0


# ---------------------------------------------------------------- the nightly sweep

def registered_maps(root):
    """Maps whose graph is compiled in: argus_nav_<map>.qc named in src/progs.src."""
    text = read_text(root / 'src' / 'progs.src')
    return sorted(m for m in re.findall(r'^\s*argus_nav_(\w+)\.qc\b', text, re.M) if m != 'dispatch')


def last_receipt(root, kind):
    for path in reversed(sorted((root / 'runs' / 'lab').glob(f'{kind}-*.json'))):
        try:
            return read_json(path), path.name
        except (OSError, ValueError):
            continue
    return None, None


def night(root, maps=None, engine=False, out=None):
    """The unattended census: every registered map through the cheap tiers, every new tape triaged, and staleness.

    Unlike pyramid, nothing stops at a failure: a census reports every map.
    It alerts (exit 1) only on what changed since the last sweep: a step that
    passed then and fails now, a regression at a fixed claim's cell on a new
    tape, or a void artefact that was not void before. Known failures are
    listed as still failing. Engines start only with engine=True.
    """
    out = out or sys.stdout
    previous, previous_name = last_receipt(root, 'night')
    if previous:
        since = previous.get('date', '')
    else:
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime('%Y-%m-%d')
    maps = maps or registered_maps(root)
    obj = objective(root)
    seen, steps = set(), []
    for s in pyramid_plan(root, maps, 2 if engine else 1, obj):
        if s['name'] not in seen:
            seen.add(s['name'])
            steps.append(s)
    results = [run_step(root, s) for s in steps]
    before = {r['name']: r['status'] for r in (previous or {}).get('steps', [])}
    newly_failing = [r['name'] for r in results if r['status'] == 'fail' and before.get(r['name']) == 'pass']
    still_failing = [r['name'] for r in results if r['status'] == 'fail' and r['name'] not in newly_failing]

    # New tapes, by each tape's own header date: a fresh clone stamps every
    # file with the checkout time. The first sweep looks back a week.
    fresh = sorted(p for p in (root / 'runs').glob('*.log') if (tape_date(p) or '') >= since
                   and b'ARGLOG ' in p.read_bytes()[:200000])

    def freezes(c):
        return c['kinds'].get('freeze', 0) + c['kinds'].get('freeze under fire', 0)

    tape_rows = []
    for p in fresh:
        rep = triage(root, p)
        flagged = [c for c in rep['clusters'] if c['flag'].startswith('regression')
                   or (c['flag'] == 'new' and (freezes(c) or c['count'] >= REGRESSION_COUNT))]
        if flagged:
            tape_rows.append(dict(tape=p.name, clusters=flagged))
    findings = stale_findings(root, obj)
    void_now = {f'{f["area"]}: {f["item"]}' for f in findings if f['severity'] == 'void'}
    void_before = set((previous or {}).get('void', []))
    newly_void = sorted(void_now - void_before) if previous else []

    alerts = [f'newly failing: {n}' for n in newly_failing] + [f'newly void: {v}' for v in newly_void]
    alerts += [f'regression at a fixed cell in {t["tape"]} at {" ".join(map(str, c["centre"]))}'
               for t in tape_rows for c in t['clusters'] if c['flag'].startswith('regression')]
    today = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
    head = (git(root, 'log', '-1', '--format=%h %s') or '?').strip()
    buf = io.StringIO()
    print(f'# Argus nightly sweep, {today}', file=buf)
    print(file=buf)
    print(f'At {head}. Maps: {", ".join(maps)}. Engines: {"yes" if engine else "no"}. Tapes recorded since {since}. '
          + (f'Compared with {previous_name}.' if previous else 'First sweep: nothing to compare with.'), file=buf)
    print(file=buf)
    print('## What changed', file=buf)
    print(file=buf)
    for line in alerts or ['Nothing got worse.']:
        print(f'- {line}', file=buf)
    print(file=buf)
    print('## Evidence tiers', file=buf)
    print(file=buf)
    for row in results:
        show_step(row, buf)
    if still_failing:
        print(file=buf)
        print(f'Still failing, not an alert: {", ".join(still_failing)}.', file=buf)
    print(file=buf)
    print('## New tapes', file=buf)
    print(file=buf)
    print(f'{plural(len(fresh), "tape")} recorded since {since}; '
          f'{plural(len(tape_rows), "tape")} with a cluster worth a look.', file=buf)
    for t in tape_rows:
        print(file=buf)
        print(f'### {t["tape"]}', file=buf)
        print(file=buf)
        for c in t['clusters']:
            what = ', '.join(f'{k} {v}' for k, v in sorted(c['kinds'].items()))
            print(f'- {c["flag"]} at {" ".join(map(str, c["centre"]))}: {what}', file=buf)
    print(file=buf)
    print('## Stale artefacts', file=buf)
    print(file=buf)
    print_findings(findings, buf)

    receipt = write_receipt(root, 'night', dict(date=today, maps=maps, engine=engine, steps=results,
                                                void=sorted(void_now), tapes=tape_rows, alerts=alerts))
    report = receipt.with_suffix('.md')
    report.write_text(buf.getvalue(), encoding='utf-8')
    print(f'{report.relative_to(root)}: {plural(len(alerts), "alert")}, '
          f'{plural(len(still_failing), "known failure")}, {plural(len(fresh), "new tape")}', file=out)
    return 1 if alerts else 0


# ---------------------------------------------------------------- command line

def main(argv=None):
    ap = argparse.ArgumentParser(prog='argus_lab.py', description='Argus lab spine')
    ap.add_argument('--root', default=str(ROOT))
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('state')
    p.add_argument('--write')
    p = sub.add_parser('stale')
    p.add_argument('--json', action='store_true')
    p.add_argument('--strict', action='store_true', help='exit 1 on any void or stale finding')
    p = sub.add_parser('session')
    p.add_argument('tapes', nargs='*')
    p.add_argument('--last', type=int)
    p.add_argument('--json', action='store_true')
    p = sub.add_parser('skeptic')
    p.add_argument('arm_a', nargs='+')
    p.add_argument('--vs', nargs='+', required=True, dest='arm_b')
    p.add_argument('--metric', action='append')
    p.add_argument('--json', action='store_true')
    p = sub.add_parser('triage')
    p.add_argument('tape')
    p.add_argument('--json', action='store_true')
    p.add_argument('--min', type=int, default=3)
    p = sub.add_parser('review')
    p.add_argument('tape')
    p = sub.add_parser('claims')
    p.add_argument('--status', choices=STATUSES)
    p.add_argument('--check', action='store_true')
    p = sub.add_parser('ledger')
    p.add_argument('--write')
    p = sub.add_parser('night')
    p.add_argument('--maps')
    p.add_argument('--engine', action='store_true', help='also run the benchmark tier, which starts engines')
    p = sub.add_parser('pyramid')
    p.add_argument('--maps', required=True)
    p.add_argument('--through', type=int, default=2, choices=(1, 2, 4))
    p.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()

    if a.cmd == 'claims':
        if a.check:
            errors = validate(root)
            for e in errors:
                print(e)
            print(f'{len(errors)} error(s) in the objective and claims' if errors else 'objective and claims: ok')
            return 1 if errors else 0
        claims = all_claims(root)
        print_claims([c for c in claims if not a.status or c['status'] == a.status])
        return 0
    if a.cmd == 'state':
        if a.write:
            with open(a.write, 'w', encoding='utf-8', newline='\n') as fh:
                state(root, fh)
            print(f'wrote {a.write}')
        else:
            state(root)
        return 0
    if a.cmd == 'stale':
        findings = stale_findings(root, objective(root))
        if a.json:
            print(json.dumps(findings, indent=1))
        else:
            print_findings(findings)
        return 1 if a.strict and any(f['severity'] in ('void', 'stale') for f in findings) else 0
    if a.cmd == 'session':
        sessions, verdicts = sessions_report(root, objective(root), files=a.tapes or None,
                                             last=a.last if a.last or a.tapes else 5)
        if a.json:
            print(json.dumps(dict(sessions=sessions, verdicts=verdicts), indent=1, default=str))
        else:
            print_sessions(sessions, verdicts)
        return 0
    if a.cmd == 'skeptic':
        rep = skeptic(root, a.arm_a, a.arm_b, a.metric)
        if a.json:
            print(json.dumps(rep, indent=1, default=str))
        else:
            print_skeptic(rep)
        return 0
    if a.cmd in ('triage', 'review'):
        path = Path(a.tape)
        if not path.is_file():
            path = root / 'runs' / (a.tape if a.tape.endswith('.log') else a.tape + '.log')
        if not path.is_file():
            print(f'no tape {a.tape}', file=sys.stderr)
            return 2
        if a.cmd == 'review':
            review(root, path)
            return 0
        rep = triage(root, path)
        if a.json:
            print(json.dumps(rep, indent=1))
        else:
            print_triage(rep, a.min)
        return 0
    if a.cmd == 'ledger':
        doc = json.dumps(ledger(root), indent=1, default=str)
        if a.write:
            Path(a.write).parent.mkdir(parents=True, exist_ok=True)
            Path(a.write).write_text(doc + '\n', encoding='utf-8')
            print(f'wrote {a.write}')
        else:
            print(doc)
        return 0
    if a.cmd == 'pyramid':
        maps = [m for m in a.maps.split(',') if m]
        return pyramid(root, maps, a.through, a.dry_run)
    if a.cmd == 'night':
        maps = [m for m in a.maps.split(',') if m] if a.maps else None
        return night(root, maps, a.engine)
    return 2


if __name__ == '__main__':
    sys.exit(main())
