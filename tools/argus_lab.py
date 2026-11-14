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
    """Commits that changed the shipped binary, newest first, with commit time in this machine's local time.

    Tape headers are written in local time without a zone, so commit times
    are converted to the same clock before any comparison.
    """
    out = []
    for line in (git(root, 'log', '--format=%H %cI %s', '--', 'game/argus/progs.dat') or '').splitlines():
        sha, stamp, subject = (line.split(' ', 2) + ['', ''])[:3]
        try:
            local = dt.datetime.fromisoformat(stamp).astimezone().replace(tzinfo=None)
        except ValueError:
            continue
        out.append(dict(commit=sha, when=local.strftime('%Y-%m-%d %H:%M:%S'), date=local.strftime('%Y-%m-%d'),
                        subject=subject))
    return out


def build_on(when, history):
    """The install in force at a local 'YYYY-MM-DD HH:MM:SS' (or a bare date, read as its end), or None.

    This is the merge commit that changed the shipped binary. A binary copied
    to a machine before its merge (as #793 was) is attributed to the previous
    build until the merge lands.
    """
    if not when:
        return None
    when = when if len(when) > 10 else when + ' 23:59:59'
    for row in history:
        if row.get('when', row['date'] + ' 00:00:00') <= when:
            return row
    return None


QC_ARGNAV = re.compile(r'"ARGNAV (\d+) nodes, (\d+) links')


def nav_banner(root, mapname):
    """The ARGNAV (nodes, links) the shipped graph prints at runtime, read from the dprint in its generated QC."""
    m = QC_ARGNAV.search(read_text(root / 'src' / f'argus_nav_{mapname}.qc'))
    return (int(m.group(1)), int(m.group(2))) if m else None


def graph(root, mapname):
    path = root / 'src' / f'argus_nav_{mapname}.qc.json'
    if not path.is_file():
        return None
    doc = read_json(path)
    return dict(md5=md5(path), nodes=len(doc.get('nodes', [])), doc=doc, banner=nav_banner(root, mapname))


LOG_STARTED = re.compile(r'^LOG started on: (\d{2})/(\d{2})/(\d{4})(?: (\d{2}:\d{2}:\d{2}))?', re.M)


def tape_when(path, text=None):
    """Local 'YYYY-MM-DD HH:MM:SS' from the tape's own header, else the date in its file name, else None."""
    m = LOG_STARTED.search(text if text is not None else read_text(path)[:400])
    if m:
        return f'{m.group(3)}-{m.group(1)}-{m.group(2)}' + (f' {m.group(4)}' if m.group(4) else '')
    m = DATE.search(Path(path).name)
    return m.group(1) if m else None


def tape_date(path, text=None):
    """YYYY-MM-DD from the tape's own header, else from its file name; the header is what a clone keeps."""
    when = tape_when(path, text)
    return when[:10] if when else None


def argnav(text):
    m = ARGNAV.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def banner_text(banner):
    if not banner:
        return 'no banner'
    return f'{banner[0]} nodes' + (f', {banner[1]} links' if banner[1] is not None else '')


def run_name(name):
    """A run as given on the command line (x, x.log or runs/x.log) reduced to its stem."""
    return Path(str(name)).name[:-4] if str(name).endswith('.log') else Path(str(name)).name


def known_maps(root):
    return {p.name[len('argus_nav_'):-len('.qc.json')] for p in (root / 'src').glob('argus_nav_*.qc.json')}


def map_from_name(root, name):
    """The map a run name mentions (ab_dm4_x, nm_ctl_dm4_1, rep_cand_e1m7_3), or None."""
    maps = known_maps(root)
    return next((t for t in run_name(name).split('_') if t in maps), None)


def jsonable(value):
    """Infinity and NaN as strings, so --json output parses everywhere, not only in Python."""
    if isinstance(value, float) and not math.isfinite(value):
        return 'inf' if value > 0 else ('-inf' if value < 0 else None)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


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
    # The corpus answers one kind at a time and defaults to bot tapes, so a
    # human or fixture tape is asked for by kind before it is called missing.
    for kind in ('bot', 'human', 'fixture'):
        if not missing or not lab:
            break
        cmd = [lab, 'corpus', '--kind', kind] + (['--map', mapname] if mapname else [])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                 env=lab_env(root), timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            res = None
        if res is None or res.returncode != 0:
            continue
        lines = res.stdout.strip().splitlines()
        head = lines[0].split(',') if lines else []
        for line in lines[1:]:
            cells = line.split(',')
            if len(cells) != len(head):
                continue  # a run name with a comma in it cannot be read back safely
            row = dict(zip(head, cells))
            if row.get('run') in missing:
                rows[row['run']] = row
                source[row['run']] = 'parsed by argus-mcp corpus'
        missing = [n for n in missing if n not in rows]
    return rows, source


# ---------------------------------------------------------------- validation

def is_number(value):
    """A real number: JSON true and false are ints to Python, and a quoted "0" is a string."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(root):
    """Schema and reference errors in the objective and the claims; empty when sound.

    Every rule here exists because a malformed value would otherwise
    validate and then crash or mislead a later command.
    """
    errors = []
    try:
        obj = objective(root)
    except (OSError, ValueError) as exc:
        return [f'lab_objective.json: {exc}']
    if not isinstance(obj, dict):
        return ['lab_objective.json: the top level must be an object']
    for key in ('schema', 'status', 'tiers', 'calibration', 'hard_gates', 'goal_targets', 'labels',
                'metric_boundaries', 'limits_doc'):
        if key not in obj:
            errors.append(f'lab_objective.json: missing {key}')
    if obj.get('status') not in ('draft', 'signed'):
        errors.append('lab_objective.json: status must be draft or signed')
    if obj.get('status') == 'signed' and not obj.get('signed_off'):
        errors.append('lab_objective.json: a signed objective names who signed it and when in signed_off')
    cal = obj.get('calibration')
    if not isinstance(cal, dict):
        errors.append('lab_objective.json: calibration must be an object')
    else:
        if not (is_number(cal.get('skill')) and int(cal['skill']) == cal['skill']):
            errors.append('calibration: skill must be a whole number')
        if not (isinstance(cal.get('goal_maps'), list) and cal['goal_maps']
                and all(isinstance(m, str) and m for m in cal['goal_maps'])):
            errors.append('calibration: goal_maps must be a non-empty list of map names')
        if not (is_number(cal.get('sessions_per_verdict')) and cal['sessions_per_verdict'] >= 1
                and int(cal['sessions_per_verdict']) == cal['sessions_per_verdict']):
            errors.append('calibration: sessions_per_verdict must be a whole number of at least 1')
        if not (is_number(cal.get('min_session_sec')) and cal['min_session_sec'] >= 0):
            errors.append('calibration: min_session_sec must be a number of seconds')
    header = set()
    card = root / 'runs' / 'human_scorecard.tsv'
    if card.is_file():
        first = read_text(card).splitlines()[:1]
        header = set(first[0].split('\t')) if first else set()
    gate_ids = set()
    gates = obj.get('hard_gates', [])
    for g in gates if isinstance(gates, list) else []:
        if not isinstance(g, dict):
            errors.append(f'hard gate {g!r}: must be an object')
            continue
        gid = g.get('id', '?')
        if gid in gate_ids:
            errors.append(f'lab_objective.json: duplicate gate {gid}')
        gate_ids.add(gid)
        if 'scan' in g:
            if not isinstance(g['scan'], list) or not g['scan'] or not all(isinstance(p, str) and p for p in g['scan']):
                errors.append(f'gate {gid}: scan must be a list of non-empty strings')
        elif 'column' in g:
            bounds = [k for k in ('max', 'below') if k in g]
            if len(bounds) != 1:
                errors.append(f'gate {gid}: give exactly one of max or below')
            elif not is_number(g[bounds[0]]):
                errors.append(f'gate {gid}: {bounds[0]} must be a number, not {g[bounds[0]]!r}')
            if header and g['column'] not in header:
                errors.append(f'gate {gid}: column {g["column"]} is not in runs/human_scorecard.tsv')
        else:
            errors.append(f'gate {gid}: needs scan or column')
    targets = obj.get('goal_targets', {})
    for key in ('bot_kills_human_pm', 'kill_ratio'):
        if isinstance(targets, dict) and key not in targets:
            errors.append(f'goal_targets: missing {key}')
    for key, target in (targets.items() if isinstance(targets, dict) else []):
        if not (isinstance(target, dict) and is_number(target.get('low')) and is_number(target.get('high'))
                and target['low'] <= target['high']):
            errors.append(f'goal target {key}: needs numeric low <= high')
    for b in obj.get('metric_boundaries', []):
        if (not isinstance(b, dict) or not DATE.fullmatch(str(b.get('date', ''))) or not b.get('metrics')
                or b.get('source') not in ('emission', 'parser')):
            errors.append(f'metric boundary {b}: needs a YYYY-MM-DD date, metrics, and source emission or parser')
    if not (root / str(obj.get('limits_doc', ''))).is_file():
        errors.append(f'lab_objective.json: limits_doc {obj.get("limits_doc")} does not exist')
    try:
        claims = own_claims(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return errors + [f'lab_claims.json: {exc}']
    ids = set()
    registry = set()
    reg = root / 'tools' / 'refuted_claims.json'
    if reg.is_file():
        registry = {c['id'] for c in read_json(reg)['claims']}
    for c in claims:
        if not isinstance(c, dict):
            errors.append(f'claim {c!r}: must be an object')
            continue
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
        if c.get('tier') not in (None, 1, 2, 3, 4) or isinstance(c.get('tier'), bool):
            errors.append(f'{where}: tier must be 1 to 4 or null')
        if 'cheapest_tier' in c and (c['cheapest_tier'] not in TIERS or isinstance(c['cheapest_tier'], bool)):
            errors.append(f'{where}: cheapest_tier must be 1 to 5')
        if c.get('status') == 'fixed' and not DATE.fullmatch(str(c.get('fixed_on', ''))):
            errors.append(f'{where}: a fixed claim says when, as fixed_on YYYY-MM-DD')
        if c.get('kind') == 'graveyard' and c.get('status') not in ('refuted', 'parked'):
            errors.append(f'{where}: a graveyard entry is refuted or parked')
        if c.get('do_not_retry') and c.get('next'):
            errors.append(f'{where}: do_not_retry contradicts a next step; park it instead')
        if c.get('kind') == 'hypothesis' and c.get('status') == 'open' and not c.get('refute_by'):
            errors.append(f'{where}: an open hypothesis says what would refute it (refute_by)')
        tolerate = c.get('regression', {})
        if tolerate and not (isinstance(tolerate, dict) and set(tolerate) <= {'events', 'freeze_sec'}
                             and all(is_number(v) and v >= 0 for v in tolerate.values())):
            errors.append(f'{where}: regression takes events and freeze_sec, both non-negative numbers')
        for cell in c.get('cells', []):
            at = cell.get('at') if isinstance(cell, dict) else None
            if (not isinstance(cell, dict) or not isinstance(cell.get('map'), str) or not isinstance(at, list)
                    or len(at) != 3 or not all(is_number(v) for v in at)
                    or not is_number(cell.get('radius')) or cell['radius'] <= 0
                    or ('dz' in cell and not (is_number(cell['dz']) and cell['dz'] > 0))):
                errors.append(f'{where}: a cell is {{map, at: [x, y, z], radius > 0, optional dz > 0}}')
            elif cell['map'] not in c.get('maps', []):
                errors.append(f'{where}: cell map {cell["map"]} is not in maps')
        for ref in c.get('evidence', []):
            if not evidence_resolves(root, ref):
                errors.append(f'{where}: evidence {ref} does not resolve (a file in the repo, #n or a run in runs/)')
    return errors


def evidence_resolves(root, ref):
    """An issue or PR as #n, a file inside this checkout, or a run name in runs/."""
    ref = str(ref)
    if ISSUE.match(ref):
        return True
    root = Path(root).resolve()
    try:
        path = (root / ref).resolve()
        path.relative_to(root)
    except (ValueError, OSError):
        return False
    if path.is_file():
        return True
    return re.fullmatch(r'[\w.-]+', ref) is not None and (root / 'runs' / f'{ref}.log').is_file()


# ---------------------------------------------------------------- sessions

def session_when(root, row, index):
    """Local start time of a session tape, from its header, else the corpus index, else its name."""
    when = tape_when(root / 'runs' / row.get('file', ''))
    if when and len(when) > 10:
        return when
    started = index.get(Path(row.get('file', '')).stem, {}).get('started', '')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', started):
        return started
    return when or (started[:10] if DATE.fullmatch(started[:10]) else None)


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
    when = session_when(root, row, index)
    date = when[:10] if when else None
    build = build_on(when, history)
    reasons = []
    if row.get('map') not in cal['goal_maps']:
        reasons.append(f'map {row.get("map")} is not a goal map')
    if dur < cal['min_session_sec']:
        reasons.append(f'{dur:.0f} s is under {cal["min_session_sec"]} s')
    if skill is None:
        reasons.append('the tape does not name its skill tier')
    elif skill != [cal['skill']]:
        reasons.append(f'skill {",".join(map(str, skill))}, not {cal["skill"]}')
    if row.get('human', '-') in ('', '-') and 'human' in row:
        reasons.append('no human in the tape')
    elif bk_pm is None:
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

def match_tapes_paths(runs):
    """Every match tape in runs/: a .log whose opening carries ARGLOG samples."""
    out = []
    for p in sorted(runs.glob('*.log')):
        try:
            with open(p, 'rb') as fh:
                if b'ARGLOG ' in fh.read(200000):
                    out.append(p)
        except OSError:
            continue
    return out


def stale_findings(root, obj):
    out = []
    index = tape_index(root)
    runs = root / 'runs'

    # Tapes the corpus cache has not persisted: every query parses them again.
    match_tapes = [p.stem for p in match_tapes_paths(runs)]
    unindexed = sorted(t for t in match_tapes if t not in index)
    if unindexed:
        out.append(finding('tape index', 'info', 'runs/tape_index.tsv',
                           f'{len(unindexed)} match tapes are parsed on demand by every corpus query, '
                           f'e.g. {", ".join(unindexed[:3])}',
                           'argus-mcp corpus --write persists them and makes queries fast'))

    # Baselines: a verdict is only as current as the tapes it is measured
    # against. One finding per map and reason, naming the tapes.
    path = runs / 'baselines.json'
    baselines = read_json(path) if path.is_file() else {}
    for mapname, names in sorted(baselines.items()):
        names = [names] if isinstance(names, str) else list(names)
        g = graph(root, mapname)
        shipped = g['banner'] if g and g.get('banner') else ((g['nodes'], None) if g else None)
        missing, unindexed, slow, banners = [], [], collections.defaultdict(list), collections.defaultdict(list)
        for name in names:
            if not (runs / f'{name}.log').is_file():
                missing.append(name)
                continue
            row = index.get(name)
            if row is None:
                unindexed.append(name)
            elif row.get('tick_class') != 'listen':
                slow[row.get('tick_class') or 'an unknown rate'].append(name)
            banner = argnav(read_text(runs / f'{name}.log'))
            if shipped and banner and (banner[0] != shipped[0] or (shipped[1] is not None and banner[1] != shipped[1])):
                banners[banner].append(name)
        item = f'{mapname} baseline'
        if missing:
            out.append(finding('baseline', 'void', item, f'{plural(len(missing), "tape")} missing: {", ".join(missing)}',
                               f'pick a new baseline with baseline_set for {mapname}'))
        for tick, which in sorted(slow.items()):
            out.append(finding('baseline', 'void', item,
                               f'recorded at {tick}, not the played rate, so verdicts against it are void '
                               f'({", ".join(which)})',
                               f'record three listen-class tapes and point baselines.json {mapname} at them'))
        for banner, which in sorted(banners.items()):
            out.append(finding('baseline', 'stale', item,
                               f'ran {banner_text(banner)}; the shipped graph prints {banner_text(shipped)} '
                               f'({", ".join(which)})',
                               're-baseline on the current graph'))
        if unindexed:
            out.append(finding('baseline', 'info', item,
                               f'tick class unknown until indexed: {", ".join(unindexed)}',
                               'argus-mcp corpus --write'))

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
            # navgen's own rule for consuming a verdict: within 24u on each axis.
            for i, n in enumerate(nodes):
                if len(p) == 3 and all(abs(a - b) <= 24.0 for a, b in zip(n, p)):
                    return i
            return None

        walks = {tuple(l[:2]) for l in doc.get('links', [])}
        typed = {tuple(l[:2]) for key in ('jlinks', 'doorlinks', 'rjlinks', 'sprintlinks') for l in doc.get(key, [])}
        verdicts = read_json(side)
        # A sweep stamps its server mode, and the modes disagree (#310): a
        # conviction from a co-op sweep says nothing about deathmatch.
        modes = verdicts.get('modes') or {'unstamped': {'failed': verdicts.get('failed', [])}}
        jumps = {tuple(l[:2]) for l in doc.get('jlinks', [])}
        typed_shipped = []
        for t in verdicts.get('typed_failed', []):
            if t.get('kind') == 'jump':
                ia, ib = node_at(t.get('from', [])), node_at(t.get('to', []))
                if ia is not None and ib is not None and (ia, ib) in jumps:
                    typed_shipped.append(f'n{ia}->n{ib}')
        if typed_shipped:
            out.append(finding('verdicts', 'stale', f'{side.name} (jump sweep)',
                               f'{plural(len(typed_shipped), "jump link")} the puppet refused still shipped, '
                               f'e.g. {", ".join(typed_shipped[:3])}',
                               f'regenerate {mapname}; navgen removes refused jump links outright'))
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
    # The date is the one the doc says it was generated on, which a rerun of
    # measure rewrites; the index is a cache, so tapes are dated by header.
    doc_text = read_text(root / obj['limits_doc'])
    m = re.search(r'Generated by `?argus-mcp measure`? on (\d{4}-\d{2}-\d{2})', doc_text) or DATE.search(obj['limits_doc'])
    if m:
        generated = m.group(1)
        newer = [p for p in match_tapes_paths(runs) if (tape_date(p) or '') > generated
                 and not p.name.startswith('shane_')
                 and index.get(p.stem, {}).get('kind', 'bot') == 'bot']
        listen = sum(1 for p in newer if index.get(p.stem, {}).get('tick_class') == 'listen')
        if len(newer) >= 10:
            out.append(finding('limits', 'stale', obj['limits_doc'],
                               f'generated {generated}; {plural(len(newer), "bot tape")} recorded since '
                               f'({listen} of them listen-class in the index, the rest unindexed)',
                               'argus-mcp measure --write ' + obj['limits_doc']))

    # The installed binary against the source it was built from.
    history = installs(root)
    if history:
        since = (git(root, 'log', '--format=%h %s', f'{history[0]["commit"]}..HEAD', '--', 'src') or '').splitlines()
        if since:
            out.append(finding('install', 'info', 'game/argus/progs.dat',
                               f'installed on {history[0]["date"]}; {plural(len(since), "commit")} changed src/ since: '
                               + '; '.join(since[:3]),
                               'compile and install when a human session should test them; '
                               'a comment-only change compiles to the same bytes'))

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
    """Emission boundaries for this metric that fall inside the arms' date range.

    A tape recorded on the boundary day already carries the new metric. Parser
    boundaries are not confounds for corpus data: the corpus re-parses every
    tape with the current parser.
    """
    dates = [d for d in dates if d]
    if not dates:
        return []
    lo, hi = min(dates), max(dates)
    return [b for b in obj['metric_boundaries']
            if metric in b['metrics'] and b.get('source', 'emission') == 'emission' and lo < b['date'] <= hi]


def hull0_lava(root, name, mapname):
    """Bot lava and slime deaths in one tape, judged by hull-0 contents at the death origin and 24u below.

    The quality bar's definition. The corpus index counts deaths below z -300
    instead, which misses dm2's and e1m7's lava entirely. None without a BSP.
    """
    bsp = bsp_path(root, mapname) if mapname else None
    contents = argus_longi._classifier(str(bsp)) if bsp else None
    if contents is None:
        return None
    tape = argus_tape.read_tape(str(root / 'runs' / f'{name}.log'))
    bots = set(argus_tape.track_names(tape.samples, tape.events)[0])
    count = 0
    for _, victim, killer, x, y, z in argus_tape.deaths(tape.events):
        if victim in bots and killer == 'world' and (contents(x, y, z) in argus_longi.HAZARD
                                                      or contents(x, y, z - 24) in argus_longi.HAZARD):
            count += 1
    return count


def skeptic(root, arm_a, arm_b, metrics=None, obj=None):
    """Every reason the comparison of arm_a (control) with arm_b cannot be read at face value."""
    obj = obj or objective(root)
    void, confounds, notes = [], [], []
    arm_a, arm_b = [run_name(n) for n in arm_a], [run_name(n) for n in arm_b]
    for label, arm in (('control', arm_a), ('candidate', arm_b)):
        twice = sorted({n for n in arm if arm.count(n) > 1})
        if twice:
            void.append(f'the {label} arm names {", ".join(twice)} more than once, which would inflate n')
    names = list(dict.fromkeys(arm_a + arm_b))
    overlap = sorted(set(arm_a) & set(arm_b))
    if overlap:
        void.append(f'the same tape is in both arms: {", ".join(overlap)}')
    known = tape_index(root)
    guess = next((known[n]['map'] for n in names if n in known), None) or next(
        (m for m in (map_from_name(root, n) for n in names) if m), None)
    found, source = corpus_rows(root, names, guess)
    missing = [n for n in names if n not in found]
    for n in missing:
        if not (root / 'runs' / f'{n}.log').is_file():
            void.append(f'{n} is not in runs/')
        else:
            void.append(f'{n} has no corpus row: the index lacks it and argus-mcp could not parse it'
                        + ('' if lab_binary(root) else ' (no argus-mcp binary; set ARGUS_LAB)'))
    parsed = [n for n, s in source.items() if s != 'index']
    if parsed:
        notes.append(f'{plural(len(parsed), "tape")} not in the index, parsed by argus-mcp corpus')
    rows_a = [found[r] for r in arm_a if r in found]
    rows_b = [found[r] for r in arm_b if r in found]
    rows = rows_a + rows_b
    if not rows_a or not rows_b:
        void.append('one arm has no tape with a corpus row')
        return dict(verdict='void', void=void, confounds=confounds, notes=notes, metrics={})
    maps = sorted({r['map'] for r in rows})
    if len(maps) > 1:
        void.append(f'the arms span maps {", ".join(maps)}')
    kinds = sorted({r.get('kind') for r in rows})
    if kinds != ['bot']:
        void.append(f'tape kinds {", ".join(map(str, kinds))}: human and fixture tapes never enter a bot comparison')
    ticks = sorted({r.get('tick_class') or '' for r in rows})
    if '' in ticks:
        void.append('a tape has no tick class, so a frame-rate change cannot be ruled out: '
                    + ', '.join(r['run'] for r in rows if not r.get('tick_class')))
    elif len(ticks) > 1:
        void.append(f'tick classes differ ({", ".join(ticks)}): a rate change before it is a behaviour change')
    elif ticks != ['listen']:
        notes.append(f'recorded at {ticks[0]}, not the played rate')
    stubs = [r['run'] for r in rows if not (num(r.get('duration_sec')) or 0) > 0]
    if stubs:
        void.append(f'no duration, a stub tape: {", ".join(stubs)}')

    def per_arm(arm, reader):
        return {n: reader(read_text(root / 'runs' / f'{n}.log')) for n in arm}

    banners_a, banners_b = per_arm(arm_a, argnav), per_arm(arm_b, argnav)
    set_a, set_b = set(banners_a.values()) - {None}, set(banners_b.values()) - {None}
    if len(set_a) > 1 or len(set_b) > 1:
        confounds.append('graphs differ inside an arm: ' + '; '.join(
            f'{n} {banner_text(b)}' for n, b in {**banners_a, **banners_b}.items() if b))
    elif set_a and set_b and set_a != set_b:
        confounds.append(f'the arms ran different graphs ({banner_text(next(iter(set_a)))} against '
                         f'{banner_text(next(iter(set_b)))}); only a graph change may differ this way')
    skills_a = {tuple(s) for s in per_arm(arm_a, skill_of).values() if s}
    skills_b = {tuple(s) for s in per_arm(arm_b, skill_of).values() if s}
    if skills_a and skills_b and skills_a != skills_b:
        confounds.append(f'skill tiers differ: {sorted(skills_a)} against {sorted(skills_b)}')
    durs = [num(r.get('duration_sec')) or 0 for r in rows]
    rates = not stubs and max(durs) / min(durs) > 1.1
    if rates:
        notes.append(f'durations run {min(durs):.0f} to {max(durs):.0f} s; per-minute rates are compared, '
                     'with spread taken from these arms because the limits doc is per tape')
    if len(arm_a) < 2 or len(arm_b) < 2:
        notes.append('one tape a side: no spread to measure, and the stall band floor is zero')

    mapname = maps[0] if len(maps) == 1 else None
    lim = limits(root, obj).get(mapname, {}) if mapname else {}
    dates = [r.get('started', '')[:10] for r in rows]
    lava = {}
    if 'lava_deaths' in (metrics or LIMIT_METRICS) and mapname and not void:
        lava = {r['run']: hull0_lava(root, r['run'], mapname) for r in rows}
        if all(v is not None for v in lava.values()):
            notes.append('lava_deaths recounted from hull-0 contents at each death (the corpus counts z below -300)')
        else:
            lava = {}
            notes.append('lava_deaths is the corpus z-below-300 count; without the BSP it misses lava above that')
    results = {}
    for metric in metrics or LIMIT_METRICS:
        if metric == 'lava_deaths' and lava:
            va, vb = [float(lava[r['run']]) for r in rows_a], [float(lava[r['run']]) for r in rows_b]
        else:
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
        # The detection limit uses the larger of the instrument's committed
        # spread and the spread these arms show: the doc's sigma is a pooled
        # average, and a noisier pair than average must not read "moved" on
        # the average's strength. A zero in the doc means it saw no spread.
        doc_sigma = None if rates else (lim.get(metric, {}).get('sigma') or None)
        arm_sigma = None
        if len(va) >= 2 and len(vb) >= 2:
            arm_sigma = math.sqrt((statistics.variance(va) * (len(va) - 1) + statistics.variance(vb) * (len(vb) - 1))
                                  / (len(va) + len(vb) - 2))
        candidates = [(s, label) for s, label in ((doc_sigma, 'limits doc'), (arm_sigma, 'these arms'))
                      if s is not None]
        sigma, source = max(candidates) if candidates else (None, 'unknown')
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
                map=mapname, arm_a=arm_a, arm_b=arm_b)


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

CELL_DZ = 56.0


def in_cell(point, cell):
    """Inside a claim cell: within its radius across the floor and its dz (default 56u, about a storey) up or down."""
    dx, dy, dz = (point[i] - cell['at'][i] for i in range(3))
    return math.hypot(dx, dy) <= cell['radius'] and abs(dz) <= cell.get('dz', CELL_DZ)


def regressed(cluster, tolerate):
    """Trouble at a fixed cell heavy enough to call a regression, given what the claim says it tolerates.

    Unforced deaths always count. Freezes count when longer than freeze_sec
    (a fix that bounds a pin at 8 s still leaves 6 to 8 s freezes). Other
    events count past the claim's events allowance, REGRESSION_COUNT by default.
    """
    if any(p['kind'] == 'unforced death' for p in cluster['points']):
        return True
    limit = tolerate.get('freeze_sec', 0)
    if any(p['kind'].startswith('freeze') and p.get('dur', 0) > limit for p in cluster['points']):
        return True
    return len(cluster['points']) > tolerate.get('events', REGRESSION_COUNT - 1)


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
            points.append(dict(kind=kind, bot=name, x=f.start['x'], y=f.start['y'], z=f.start['z'], dur=f.dur))

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
                if cell['map'] == mapname and in_cell(c['centre'], cell):
                    matches.append(dict(id=cl['id'], status=cl['status'], fixed_on=cl.get('fixed_on'),
                                        regression=cl.get('regression', {})))
                    break
        severe = kinds['freeze under fire'] + kinds['unforced death'] + kinds['freeze']
        flag = 'new'
        if matches:
            flag = 'known'
            fixed = [m for m in matches if m['status'] == 'fixed']
            if fixed and len(matches) == len(fixed):
                # Trouble at a fixed cell is a regression only on a tape recorded after the fix.
                # A stall or two can recur at any cell; a regression needs a freeze,
                # an unforced death, or more events than the claim tolerates.
                heavy = any(regressed(c, m['regression']) for m in fixed)
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

def installed_progs(root):
    """The progs.dat the lab engine loads: ARGUS_BASEDIR/ARGUS_GAME (default argus), as the benchmark runs it."""
    env = lab_env(root)
    base = env.get('ARGUS_BASEDIR')
    path = Path(base) / env.get('ARGUS_GAME', 'argus') / 'progs.dat' if base else None
    return path if path and path.is_file() else None


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
                installed = installed_progs(root)
                key = f'{g["md5"]}:{md5(installed) if installed else "unknown"}'
                steps.append(dict(tier=2, name=f'benchmark {suite.name}', cmd=[lab, 'benchmark', str(suite), '--no-compile'],
                                  judge='benchmark', key=key,
                                  measures=f'the installed build {md5(installed)[:8].upper() if installed else "(unknown)"}'))
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


def previous_completions(root, name, key):
    """Tasks a passing earlier run of this suite completed with the same graph and binary: the bar to hold."""
    for path in sorted((root / 'runs' / 'lab').glob('*-*.json'), key=lambda p: p.name.split('-', 1)[-1], reverse=True):
        try:
            steps = read_json(path).get('steps', [])
        except (OSError, ValueError, AttributeError):
            continue
        for s in steps:
            if s.get('name') == name and s.get('key') == key and s.get('completed') is not None:
                return set(s['completed']), path.name
    return None, None


def judge_benchmark(root, step, stdout):
    """Pass unless a task the graph used to finish no longer finishes; the first run sets the bar."""
    report = benchmark_report(stdout)
    if report is None:
        return False, 'no benchmark report in the output', None
    done = sorted(r['name'] for r in report.get('results', []) if r.get('completed'))
    total = len(report.get('results', []))
    before, receipt = previous_completions(root, step['name'], step['key'])
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
    label = f'tier {row["tier"]} {row["name"]}' + (f' (measures {row["measures"]})' if row.get('measures') else '')
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
    """Climb the tiers for one change: finish each tier, and stop before the next if it refuted the change.

    A step that the last nightly sweep already recorded as failing is a known
    failure: it is reported and does not stop the climb, so an accepted
    condition (e1m8's kept liquid links) does not hide a new one. Exit 1 when
    a tier failed, 3 when a step was blocked by a stale artefact and nothing
    failed (the evidence is incomplete), else 0.
    """
    out = out or sys.stdout
    steps = pyramid_plan(root, maps, through, objective(root))
    last_night, night_name = last_receipt(root, 'night')
    known = {r['name'] for r in (last_night or {}).get('steps', []) if r.get('status') == 'fail'}
    results = []
    stopped = None
    for tier in sorted({s['tier'] for s in steps}):
        failed_here = False
        for s in (s for s in steps if s['tier'] == tier):
            row = run_step(root, s, dry_run)
            if row['status'] == 'fail' and s['name'] in known:
                row['status'] = 'known failure'
                row['detail'] = f'{row.get("detail") or ""} (already failing in {night_name})'.strip()
            results.append(row)
            show_step(row, out)
            failed_here = failed_here or row['status'] == 'fail'
        if failed_here:
            stopped = tier
            print(f'Stopped after tier {tier}: it refuted the change, so nothing above it runs.', file=out)
            break
    blocked = [r for r in results if r['status'] == 'blocked']
    if blocked and stopped is None:
        print(f'{plural(len(blocked), "step")} blocked by stale artefacts, so this evidence is incomplete; '
              'see `argus_lab.py stale`.', file=out)
    if not last_night and not dry_run:
        print('No nightly sweep on record, so every failure counts; `argus_lab.py night` records the known ones.',
              file=out)
    if receipt and not dry_run:
        path = write_receipt(root, 'pyramid', dict(maps=maps, through=through, stopped=stopped, steps=results))
        print(f'Receipt: {path.relative_to(root)}', file=out)
    return 1 if stopped else (3 if blocked else 0)


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
    ap = argparse.ArgumentParser(prog='argus_lab.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
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
    for name in ('lab_objective.json', 'lab_claims.json'):
        if not (root / 'tools' / name).is_file():
            print(f'{root} has no tools/{name}; pass --root with a checkout that carries the lab spine',
                  file=sys.stderr)
            return 2

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
            print(json.dumps(jsonable(dict(sessions=sessions, verdicts=verdicts)), indent=1, default=str))
        else:
            print_sessions(sessions, verdicts)
        return 0
    if a.cmd == 'skeptic':
        rep = skeptic(root, a.arm_a, a.arm_b, a.metric)
        if a.json:
            print(json.dumps(jsonable(rep), indent=1, default=str))
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
