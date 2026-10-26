"""Run a frozen native-lab cohort, retaining all attempts and restoring lab bytes."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import time
import traceback

from report_perception_cohort import digest, schedule
from run_behaviour_equivalence import ROOT, Lab, identity, timing, cpu_seconds


def source_digest(path):
    import hashlib
    h = hashlib.sha256()
    for file in sorted([*path.rglob('*.qc'), *path.rglob('*.src')]):
        h.update(('src/' + file.relative_to(path).as_posix()).encode())
        h.update(b'\0'); h.update(file.read_bytes())
    return h.hexdigest()


def write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)


def validate(p, path, expected):
    assert digest(path) == expected, 'protocol changed'
    assert p['pairs'] == 128 and p['seconds'] == 60 and p['skill'] == 1
    for relative, sha in {**p['code_sha256'], **p['resources_sha256']}.items():
        assert digest(ROOT / relative) == sha, 'frozen file changed: ' + relative
    for arm in p['binaries'].values():
        assert digest(ROOT / arm['path']) == arm['sha256']
        assert source_digest(ROOT / arm['source_path']) == arm['source_sha256']
    current = identity('dm2')
    assert {k: v for k, v in current.items() if k != 'binary_sha256'} == p['identity']
    for relative in ('game/argus/progs.dat', 'lq1/progs.dat'):
        assert digest(ROOT / relative) == p['shipped_sha256']


def valid_tape(brief, text):
    assert brief['map'] == 'dm2' and brief['totals']['tick_class'] == 'listen'
    assert 58 <= brief['totals']['duration_sec'] <= 64, 'invalid native exposure'
    assert not any('WRONG MAP' in f or 'CONTROLLED FIXTURE' in f for f in brief['flags'])
    assert not any(s in text for s in ('BHVFIX ', 'PERFIX ', 'TACFIX begin', 'BHVRPL ', 'BHVDBG ', 'Host_Error', 'Program error', 'runaway loop error'))
    windows = timing(text)
    assert len(windows) >= 9
    return windows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('protocol', type=Path)
    ap.add_argument('--preflight', action='store_true')
    args = ap.parse_args()
    path = args.protocol.resolve(); p = json.loads(path.read_text()); sha = digest(path)
    validate(p, path, sha)
    out = ROOT / p['output']; out.mkdir(exist_ok=True, parents=True)
    engine = ROOT / 'engine/argus/progs.dat'
    assert digest(engine) == p['shipped_sha256'], 'unexpected installed lab binary'
    restore = out / 'restore-progs.dat'
    if not restore.exists(): shutil.copy2(engine, restore)
    assert digest(restore) == p['shipped_sha256']
    with (out / 'preflight.stderr').open('a') as err:
        lab = Lab(err)
        try:
            assert not lab.call('match_status')['running'], 'another lab match is active'
        finally: lab.close()
    if args.preflight:
        print('Preflight passed; no engine launched.'); return
    pin = out / 'protocol.sha256'
    if pin.exists(): assert pin.read_text().strip() == sha
    else: pin.write_text(sha + '\n')
    receipts = out / 'receipts.json'
    rows = json.loads(receipts.read_text()) if receipts.exists() else []
    plan = schedule(p['prefix'])
    assert [(r['name'], r['mode'], r['repeat']) for r in rows] == plan[:len(rows)]
    for row in rows:
        assert row['protocol_sha256'] == sha
        assert digest(ROOT / f"runs/{row['name']}.log") == row['raw_sha256']
    state = dict(protocol_sha256=sha, status='running', completed=len(rows),
        resumed_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    state_path = out / 'execution.json'
    write(state_path, state)
    try:
        for name, mode, repeat in plan[len(rows):]:
            assert not (ROOT / f'runs/{name}.log').exists(), 'orphan tape; investigate before resuming'
            validate(p, path, sha)
            shutil.copy2(ROOT / p['binaries'][mode]['path'], engine)
            expected_identity = dict(p['identity'], binary_sha256=p['binaries'][mode]['sha256'])
            assert identity('dm2') == expected_identity
            active = False
            attempt = dict(name=name, mode=mode, repeat=repeat, protocol_sha256=sha,
                identity=expected_identity, started_utc=dt.datetime.now(dt.timezone.utc).isoformat())
            attempt_path = out / f'{name}.attempt.json'
            assert not attempt_path.exists(), 'retained attempt requires investigation'
            write(attempt_path, attempt)
            with (out / f'{name}.stderr').open('w') as err:
                lab = Lab(err)
                try:
                    start = lab.call('match_start', map='dm2', duration_sec=80, skill=1, run_name=name)
                    active = True; attempt['start'] = start
                    write(attempt_path, attempt)
                    deadline = time.monotonic() + 10
                    while True:
                        status = lab.call('match_status')
                        if 'ARGLOG ' in json.dumps(status): break
                        assert status.get('running') and time.monotonic() < deadline
                        time.sleep(.1)
                    lab.call('match_command', command='scratch1 591; scratch4 0')
                    cpu_start = cpu_seconds(start['pid']); wall_start = time.monotonic()
                    time.sleep(60)
                    wall = time.monotonic() - wall_start
                    cpu = cpu_seconds(start['pid']) - cpu_start
                    stop = lab.call('match_stop'); active = False; attempt['stop'] = stop
                    brief = lab.call('brief_run', log=name, map='dm2'); attempt['brief'] = brief
                    raw = ROOT / f'runs/{name}.log'; text = raw.read_text(errors='replace')
                    attempt.update(raw_sha256=digest(raw), stopped_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                        wall_seconds=wall, cpu_seconds=cpu, bytes=raw.stat().st_size)
                    write(attempt_path, attempt)  # retain even when validity fails
                    windows = valid_tape(brief, text)
                    validate(p, path, sha)
                    assert identity('dm2') == expected_identity
                    row = dict(attempt, map='dm2', timing=windows, valid=True,
                        executed_source_sha256=p['binaries'][mode]['source_sha256'])
                    rows.append(row); write(receipts, rows)
                    state['completed'] = len(rows); write(state_path, state)
                    print(json.dumps(dict(completed=len(rows), total=len(plan), name=name,
                        status='valid; no interim outcome analysis')), flush=True)
                except BaseException:
                    attempt['error'] = traceback.format_exc(); write(attempt_path, attempt)
                    raise
                finally:
                    if active: lab.call('match_stop')
                    lab.close()
                    shutil.copy2(restore, engine)
        state['status'] = 'complete'
    except BaseException:
        state['status'] = 'interrupted'; state['error'] = traceback.format_exc()
        raise
    finally:
        shutil.copy2(restore, engine)
        state.update(restored_sha256=digest(engine), stopped_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        write(state_path, state)
        assert state['restored_sha256'] == p['shipped_sha256']


if __name__ == '__main__':
    main()
