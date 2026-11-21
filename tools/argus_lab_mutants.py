#!/usr/bin/env python3
"""Mutation check for the lab spine (#824): does a test fail when a guard breaks?

usage:
  argus_lab_mutants.py [--jobs N] [--timeout SEC] [--only LABEL ...]
  argus_lab_mutants.py --list | --check
  argus_lab_mutants.py --table FILE [--suite FILE]    a table of your own, for tests

Each row of MUTANTS names one guard in tools/argus_lab.py (a condition that
refuses, flags or classifies) with its original text and the smallest edit
that disables it. For every row the script runs tools/test_argus_lab.py
against the spine with that one edit applied and reports the guard caught
(the suite fails) or missed (the suite still passes).

The broken spine never touches the disk. Each mutant runs in its own Python
process, which compiles the edited source into a module object, registers it
as argus_lab in sys.modules and only then imports the test suite, so the
suite's own `import argus_lab` finds the broken copy.

Every original text must occur exactly once in the spine. A row whose text
has moved, been reworded or become ambiguous stops the run before any suite
starts (exit 2), so a refactor cannot leave a row silently testing nothing:
update the row instead. The unbroken suite runs first; if it fails, no mutant
result means anything (exit 3).

Exit codes: 0 every guard caught, 1 a guard missed or a mutant timed out or
would not load, 2 the table does not match the spine (nothing ran), 3 the
unbroken suite fails.

A full run takes a few minutes on four workers, so fast CI runs only
test_argus_lab_mutants.py, which checks the table against the spine and the
harness on one mutant. Run the whole table before a change to the spine or
its tests merges (docs/lab-spine.md).
"""
import argparse
import concurrent.futures
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import types
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
TARGET = TOOLS / 'argus_lab.py'
SUITE = TOOLS / 'test_argus_lab.py'
MODULE = 'argus_lab'
RESULT = 'MUTANT-RESULT '

# (label, original text, broken text). The label names what the guard
# protects; the broken text is the smallest edit that switches it off.
MUTANTS = [
    # the objective
    ('a signed objective names its signer',
     "if obj.get('status') == 'signed' and not obj.get('signed_off'):",
     "if obj.get('status') == 'signed' and obj.get('signed_off'):"),
    ('a gate gives exactly one bound',
     "if len(bounds) != 1:",
     "if len(bounds) > 1:"),
    ('a goal target has low at most high',
     "and target['low'] <= target['high']):",
     "):"),
    ('mde_z lies between 1 and 5',
     "1.0 <= obj['mde_z'] <= 5.0",
     "0.0 <= obj['mde_z'] <= 5.0"),

    # the claims
    ('a claim id is not repeated',
     "ids.add(cid)",
     "ids.discard(cid)"),
    ('a claim status is one of the statuses',
     "if c.get('status') not in STATUSES:",
     "if c.get('status') is None:"),
    ('a claim kind is one of the kinds',
     "if c.get('kind') not in KINDS:",
     "if c.get('kind') is None:"),
    ('a fixed claim says when',
     r"re.fullmatch(r'\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?', str(c.get('fixed_on', '')))",
     r"re.fullmatch(r'.*', str(c.get('fixed_on', '')))"),
    ('a graveyard entry is refuted or parked',
     "if c.get('kind') == 'graveyard' and c.get('status') not in ('refuted', 'parked'):",
     "if c.get('kind') == 'grave' and c.get('status') not in ('refuted', 'parked'):"),
    ('an open hypothesis says what would refute it',
     "c.get('status') == 'open' and not c.get('refute_by'):",
     "c.get('status') == 'open' and c.get('refute_by'):"),
    ('regression kinds come from the trouble kinds',
     "and set(allowance.get('kinds', [])) <= set(TROUBLE_KINDS))):",
     "or set(allowance.get('kinds', [])) <= set(TROUBLE_KINDS))):"),

    # values and evidence
    ('a number is never a boolean',
     "return isinstance(value, (int, float)) and not isinstance(value, bool)",
     "return isinstance(value, (int, float))"),
    ('evidence stays inside the checkout',
     "        path.relative_to(root)\n",
     "        path.relative_to(path.anchor)\n"),

    # builds and graphs
    ('a stamp no install carries is an unshipped build',
     "if r.get('stamp') == stamp]",
     "if r.get('stamp')]"),
    ("profile arguments are not part of a graph's identity",
     r"NAV_LINK = re.compile(r'(Argus_NavLink[A-Za-z]*)\s*\(\s*(n\d+)\s*,\s*(n\d+)')",
     r"NAV_LINK = re.compile(r'(Argus_NavLink[A-Za-z]*)\s*\(\s*(n\d+)\s*,\s*(n\d+)([^)]*)')"),
    ('a banner no revision prints is an uncommitted graph',
     "run = later[-1:] or [r for r in history if r['banner'] == banner][:1]",
     "run = later[-1:] or history[:1]"),

    # staleness
    ('a missing baseline tape is void',
     "                missing.append(name)\n",
     "                pass\n"),
    ('a baseline at another tick rate is void',
     "elif row.get('tick_class') != 'listen':",
     "elif row.get('tick_class') is None:"),
    ('a baseline that ran another graph is stale',
     "if shipped and ran and shipped['id'] not in ran['ids']:",
     "if shipped and ran and shipped['id'] in ran['ids']:"),
    ('a suite pinned to an old graph is stale',
     "elif not benchmark_graph_matches(doc, g):",
     "elif doc.get('graph_md5') is None:"),
    ('a refused jump link still shipped is stale',
     "if ia is not None and ib is not None and (ia, ib) in jumps:",
     "if ia is not None and ib is not None and (ia, ib) not in jumps:"),
    ('the limits age from the date the doc was generated',
     r"m = re.search(r'Generated by `?argus-mcp measure`? on (\d{4}-\d{2}-\d{2})', doc_text) or DATE.search(obj['limits_doc'])",
     "m = DATE.search(obj['limits_doc'])"),

    # the skeptic
    ('a tape twice in one arm is void',
     "twice = sorted({n for n in arm if arm.count(n) > 1})",
     "twice = sorted({n for n in arm if arm.count(n) > len(arm)})"),
    ('the same tape in both arms is void',
     "overlap = sorted(set(arm_a) & set(arm_b))",
     "overlap = []"),
    ('arms on two maps are void',
     "if len(maps) > 1:",
     "if len(maps) > 2:"),
    ('only bot tapes enter a comparison',
     "if kinds != ['bot']:",
     "if 'bot' not in kinds:"),
    ('arms at different tick classes are void',
     "elif len(ticks) > 1:",
     "elif len(ticks) > 2:"),
    ('arms on different graphs are a confound',
     "elif ids_a and ids_b and not ids_a & ids_b:",
     "elif ids_a and ids_b and ids_a & ids_b:"),
    ('graphs differing inside an arm are a confound',
     "if ids_a == frozenset() or ids_b == frozenset():",
     "if ids_a == frozenset() and ids_b == frozenset():"),
    ('different skill tiers are a confound',
     "if skills_a and skills_b and skills_a != skills_b:",
     "if skills_a and skills_b and skills_a == skills_b:"),
    ('builds differing inside an arm are a confound',
     "if len(b) > 1]",
     "if len(b) > 2]"),
    ('a clock mix inside the arms is a confound',
     "if clocks_a != clocks_b or len(clocks_a) > 1:",
     "if clocks_a != clocks_b:"),
    ('the larger spread sets the detection limit',
     "sigma, source = max(candidates) if candidates else (None, 'unknown')",
     "sigma, source = min(candidates) if candidates else (None, 'unknown')"),
    ('the doc spread applies only to tapes of its length',
     "abs(d - DOC_TAPE_SEC) <= 0.1 * DOC_TAPE_SEC",
     "abs(d - DOC_TAPE_SEC) <= 1.0 * DOC_TAPE_SEC"),
    ('a change beyond the limit reads moved',
     "elif abs(delta) > limit:",
     "elif abs(delta) > 2 * limit:"),
    ('lava is recounted 24 units below the death too',
     "and death_is_lava(contents, x, y, z):",
     "and contents(x, y, z) in argus_longi.HAZARD:"),

    # metric boundaries
    ("a tape on a boundary's day already carries the new metric",
     "and lo < b['date'] <= hi]",
     "and lo <= b['date'] <= hi]"),
    ('parser boundaries are not confounds',
     "b.get('source', 'emission') == 'emission'",
     "b.get('source', 'emission') in ('emission', 'parser')"),

    # triage
    ('a cell bounds height',
     "return math.hypot(dx, dy) <= cell['radius'] and abs(dz) <= cell.get('dz', CELL_DZ)",
     "return math.hypot(dx, dy) <= cell['radius']"),
    ('an unforced death breaks the deaths allowance',
     "> tolerate.get('deaths', 0):",
     "> tolerate.get('deaths', 1):"),
    ('a freeze breaks the freeze allowance',
     "p.get('dur', 0) > limit for p in points",
     "p.get('dur', 0) > limit * 2 for p in points"),
    ('a claim counts only the kinds its fix addressed',
     "points = [p for p in points if p['kind'] in tolerate['kinds']]",
     "points = list(points)"),
    ('three events are notable',
     "return sum(kinds.values()) >= NEW_COUNT",
     "return sum(kinds.values()) > NEW_COUNT"),
    ('clusters merge until no two centres are close',
     "if math.dist(clusters[i]['centre'], clusters[j]['centre']) <= radius:",
     "if math.dist(clusters[i]['centre'], clusters[j]['centre']) <= radius / 10:"),
    ('a regression needs a tape after the fix',
     "row['regression'] = row['heavy'] and row['phase'] in ('after', 'undated')",
     "row['regression'] = row['heavy']"),
    ('an open claim explains every kind in its cell',
     "explains.append(set(named) if named else None)",
     "explains.append(set(named) if named else set())"),
    ('trouble on the fix day reads on the fix day',
     "elif any(v['phase'] == 'same day' for v in verdicts):",
     "elif any(v['phase'] == 'never' for v in verdicts):"),

    # review and marks
    ('review lists new trouble no claim covers',
     "or (c['flag'] == 'new' and notable(c['unexplained']))]",
     "or (c['flag'] == 'known' and notable(c['unexplained']))]"),
    ("a mark's events reach six seconds back",
     "MARK_BEFORE, MARK_AFTER, MARK_NEAR = 6.0, 2.0, 192.0",
     "MARK_BEFORE, MARK_AFTER, MARK_NEAR = 1.0, 2.0, 192.0"),

    # sessions
    ('a statue of ten seconds fails its gate',
     "value < g['below']",
     "value <= g['below']"),
    ('no bot kills on the human is an infinite ratio',
     "(math.inf if hk else None)",
     "(None if hk else None)"),
    ('a session off a goal map does not count',
     "if row.get('map') not in cal['goal_maps']:",
     "if row.get('map') is None:"),
    ('a tape mixing skill tiers does not count',
     "elif skill != [cal['skill']]:",
     "elif cal['skill'] not in skill:"),
    ('a goal verdict counts only the installed build',
     "on_build = [s for s in mine if s['build'] == current]",
     "on_build = mine"),

    # the pyramid and the instruments
    ('a suite pinned to an old graph blocks its tier',
     "skip='suite pins a graph that is no longer shipped', blocks=True))",
     "skip='suite pins a graph that is no longer shipped', blocks=False))"),
    ('the stand-in rung needs a passed dose response',
     "if row and row.get('dose_response'):",
     "if row:"),
    ('the fixed clock screens only metrics that read equivalent',
     "if reading != 'equivalent':",
     "if reading == 'different':"),
    ('an accepted map cannot read different',
     "elif row.get('accepted') and 'different' in readings.values():",
     "elif row.get('accepted') and 'different' in readings:"),
    ('instrument readings come from the vocabulary',
     "any(v not in INSTRUMENT_READINGS for v in readings.values())",
     "any(v is None for v in readings.values())"),

    # the nightly sweep and receipts
    ('a failure is known only once a later sweep finds it failing',
     "if r.get('status') == 'fail' and not r.get('newly_failing')}",
     "if r.get('status') == 'fail'}"),
    ('a known failure that grows is not known',
     "return all(detail.get(k, 0) <= known.get(k, 0) for k in detail)",
     "return all(detail.get(k, 0) >= 0 for k in detail)"),
    ('a failure the last sweep did not see failing alerts',
     "if previous and (not was or was.get('status') != 'fail'):",
     "if previous and not was:"),
    ('a sweep alerts on a failure that got worse',
     "            worse.append(r['name'])\n",
     "            pass\n"),
    ('a failing tier stops the climb',
     "failed_here = failed_here or row['status'] == 'fail'",
     "failed_here = failed_here or row['status'] == 'FAIL'"),
    ('a tape is triaged once by name and size',
     "seen_before = {tuple(t) for t in previous['triaged']}",
     "seen_before = set()"),
    ('a void is new only when its key is',
     "for k in sorted(set(void_now) - set(previous['void_keys']))]",
     "for k in sorted(set(void_now))]"),
    ('a benchmark bar is held per graph and binary',
     "if s.get('name') == name and s.get('key') == key and s.get('completed') is not None:",
     "if s.get('name') == name and s.get('completed') is not None:"),
]


# ---------------------------------------------------------------- the table

def read_table(path):
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    return [tuple(row) for row in rows]


def table_problems(table, source):
    """Every reason a row cannot test its guard; empty when the table matches the source."""
    problems = []
    labels = [row[0] for row in table]
    for label in sorted({x for x in labels if labels.count(x) > 1}):
        problems.append(f'{label!r}: the label is used more than once')
    for label, original, broken in table:
        count = source.count(original)
        if not original or original == broken:
            problems.append(f'{label!r}: the broken text must differ from a non-empty original')
        elif count == 0:
            problems.append(f'{label!r}: the original text is no longer in the spine; '
                            'find where the guard went and update its row')
        elif count > 1:
            problems.append(f'{label!r}: the original text appears {count} times; '
                            'give it enough context to name one place')
        else:
            try:
                compile(source.replace(original, broken, 1), str(TARGET), 'exec')
            except SyntaxError as exc:
                problems.append(f'{label!r}: the broken text does not compile: {exc.msg} at line {exc.lineno}')
    return problems


# ---------------------------------------------------------------- one mutant, in its own process

def worker():
    """Run the suite against the spine with one edit applied in memory; the job arrives on stdin."""
    job = json.loads(sys.stdin.read())
    if hasattr(os, 'nice'):
        os.nice(5)
    target, suite = Path(job['target']), Path(job['suite'])
    source = target.read_text(encoding='utf-8')
    if job['original']:
        if source.count(job['original']) != 1:
            print(RESULT + json.dumps(dict(error='the original text is not in the spine exactly once')))
            return 2
        source = source.replace(job['original'], job['broken'], 1)
    sys.path.insert(0, str(target.parent))
    sys.path.insert(0, str(suite.parent))
    module = types.ModuleType(MODULE)
    module.__file__ = str(target)
    sys.modules[MODULE] = module
    try:
        exec(compile(source, str(target), 'exec'), module.__dict__)
        spec = importlib.util.spec_from_file_location(suite.stem, suite)
        tests = importlib.util.module_from_spec(spec)
        sys.modules[suite.stem] = tests
        spec.loader.exec_module(tests)
    except Exception as exc:  # noqa: BLE001 (a load failure is reported, not raised)
        print(RESULT + json.dumps(dict(error=f'{type(exc).__name__}: {exc}')))
        return 2
    loaded = unittest.defaultTestLoader.loadTestsFromModule(tests)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, failfast=True).run(loaded)
    if result.wasSuccessful():
        print(RESULT + json.dumps(dict(ran=result.testsRun)))
        return 0
    first = (result.failures + result.errors)[0][0]
    print(RESULT + json.dumps(dict(ran=result.testsRun, failed=first.id().split('.', 1)[-1])))
    return 1


def run_one(label, original, broken, suite, timeout):
    """Start one worker and classify what it says: caught, missed, timeout or error."""
    job = json.dumps(dict(target=str(TARGET), suite=str(suite), original=original, broken=broken))
    flags = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
    start = time.monotonic()
    try:
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'], input=job,
                             capture_output=True, text=True, encoding='utf-8', errors='replace',
                             cwd=str(ROOT), timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        return dict(label=label, status='timeout', detail=f'no verdict in {timeout:.0f} s',
                    sec=time.monotonic() - start)
    sec = time.monotonic() - start
    line = next((l for l in reversed(res.stdout.splitlines()) if l.startswith(RESULT)), None)
    body = json.loads(line[len(RESULT):]) if line else {}
    if res.returncode == 0 and line:
        return dict(label=label, status='missed', detail=f'the suite still passes ({body["ran"]} tests)', sec=sec)
    if res.returncode == 1 and line:
        return dict(label=label, status='caught', detail=body['failed'], sec=sec)
    tail = ' | '.join((res.stderr or res.stdout).strip().splitlines()[-2:])
    return dict(label=label, status='error', detail=body.get('error') or tail or f'exit {res.returncode}', sec=sec)


# ---------------------------------------------------------------- the run

def minutes(sec):
    return f'{sec:.0f} s' if sec < 90 else f'{int(sec // 60)} min {sec % 60:.0f} s'


def main(argv=None):
    ap = argparse.ArgumentParser(prog='argus_lab_mutants.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--jobs', type=int, default=4, help='mutants run at once (default 4)')
    ap.add_argument('--timeout', type=float, default=300.0, help='seconds one mutant may take (default 300)')
    ap.add_argument('--only', action='append', metavar='LABEL', help='run only the row with this label (repeatable)')
    ap.add_argument('--list', action='store_true', help='print the labels and stop')
    ap.add_argument('--check', action='store_true', help='check the table against the spine and stop')
    ap.add_argument('--table', help='a JSON list of [label, original, broken] rows instead of MUTANTS')
    ap.add_argument('--suite', default=str(SUITE), help='the test module to run (default tools/test_argus_lab.py)')
    ap.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.worker:
        return worker()

    table = read_table(a.table) if a.table else list(MUTANTS)
    if a.list:
        for label, _, _ in table:
            print(label)
        return 0
    problems = table_problems(table, TARGET.read_text(encoding='utf-8'))
    if problems:
        print(f'The mutant table does not match {TARGET.relative_to(ROOT).as_posix()}, so nothing ran:')
        for p in problems:
            print(f'- {p}')
        return 2
    if a.only:
        unknown = [x for x in a.only if x not in {row[0] for row in table}]
        if unknown:
            print(f'no row labelled {", ".join(map(repr, unknown))}; --list prints the labels')
            return 2
        table = [row for row in table if row[0] in a.only]
    if a.check:
        print(f'the table matches the spine: {len(table)} guards')
        return 0

    suite = Path(a.suite).resolve()
    jobs = max(1, a.jobs)
    print(f'Mutation check: {len(table)} guards in {TARGET.name} against {suite.name}, {jobs} at a time.', flush=True)
    start = time.monotonic()
    base = run_one('the unbroken suite', '', '', suite, a.timeout)
    if base['status'] != 'missed':
        print(f'The unbroken suite does not pass ({base["status"]}: {base["detail"]}), so no mutant result '
              'means anything. Fix the suite first.')
        return 3
    print(f'unbroken suite passes ({base["sec"]:.0f} s)', flush=True)

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_one, label, original, broken, suite, a.timeout): label
                   for label, original, broken in table}
        width = len(str(len(table)))
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            r = future.result()
            results[r['label']] = r
            mark = r['status'] if r['status'] == 'caught' else r['status'].upper()
            print(f'[{done:>{width}}/{len(table)}] {mark:<7} {r["label"]} ({r["detail"]}, {r["sec"]:.0f} s)', flush=True)

    ordered = [results[label] for label, _, _ in table]
    caught = [r for r in ordered if r['status'] == 'caught']
    print()
    print(f'{len(caught)} of {len(table)} guards caught in {minutes(time.monotonic() - start)}.')
    trouble = [r for r in ordered if r['status'] != 'caught']
    for r in trouble:
        print(f'- {r["status"]}: {r["label"]}: {r["detail"]}')
    if any(r['status'] == 'missed' for r in trouble):
        print('A missed guard is a gap in the suite: add a test named for it that fails when it breaks.')
    return 1 if trouble else 0


if __name__ == '__main__':
    sys.exit(main())
