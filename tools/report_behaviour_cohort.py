"""Audit the complete registered holdout and retain its native-backed results.

Never evaluates a partial cohort. ARGLOG metrics come exclusively from the
authoritative native briefs; raw scanning is confined to timing and validity.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics

from check_behaviour_equivalence import evaluate, frame_interval, frame_mean, interval
from run_behaviour_equivalence import ROOT, TIMING


def audit(protocol_path):
    protocol = json.loads(protocol_path.read_text())
    output = ROOT / protocol['output']
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    protocol_sha = digest(protocol_path)
    assert (output / 'protocol.sha256').read_text().strip() == protocol_sha
    execution = json.loads((output / 'execution.json').read_text())
    assert execution['status'] == 'complete', 'registered cohort is not complete'
    assert execution['protocol_sha256'] == protocol_sha
    assert execution['restored_sha256'] == protocol['shipped_sha256']
    code_audit = {}
    for path, expected in protocol['analysis_code_sha256'].items():
        archived = output / 'registered-code' / Path(path).name
        assert digest(archived) == expected, 'registered snapshot changed'
        current = ROOT / path
        changed = digest(current) != expected
        if changed:
            # After completion, make the scratch-directory test self-contained
            # on clean checkouts. This exact inverse edit changes no analysis,
            # runner or gameplay code; runtime checked the archived test hash.
            assert path == 'tools/test_behaviour_equivalence.py', 'registered code changed'
            old = "        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'backups') as directory:\n"
            new = ("        scratch_root = Path(__file__).resolve().parents[1] / 'backups'\n"
                   "        scratch_root.mkdir(exist_ok=True)\n"
                   "        with tempfile.TemporaryDirectory(dir=scratch_root) as directory:\n")
            assert new in current.read_text() and current.read_text().replace(new, old) == archived.read_text(), 'unexpected test change'
            assert current.stat().st_mtime >= dt.datetime.fromisoformat(execution['stopped_utc']).timestamp()
        code_audit[path] = dict(registered_sha256=expected, current_sha256=digest(current),
                               post_study_test_directory_fix=changed)
    for path in ('engine/argus/progs.dat', 'game/argus/progs.dat', 'lq1/progs.dat'):
        assert digest(ROOT / path) == protocol['shipped_sha256'], 'shipped binary not restored'
    receipts = output / 'confirm-results.json'
    rows = json.loads(receipts.read_text())
    assert len(rows) == protocol['expected_matches'] == 512, 'incomplete cohort'
    schedule = []
    for repeat in range(1, 129):
        for map_name in protocol['maps'] if repeat % 2 else protocol['maps'][::-1]:
            for mode in ('off', 'on') if repeat % 2 else ('on', 'off'):
                schedule.append((f"{protocol['prefix']}_confirm_{map_name}_{mode}{repeat}", map_name, mode, repeat))
    assert [(r['name'], r['map'], r['mode'], r['repeat']) for r in rows] == schedule, 'schedule changed'
    tapes = {}
    tails = {m: {mode: dict(windows=0, frames=0, over20=0, over50=0, max_ms=0,
                           startup_over50=0, startup_windows=0, startup_frames=0)
                 for mode in ('off', 'on')} for m in protocol['maps']}
    registered = dt.datetime.fromisoformat(protocol['registered_utc'])
    for row in rows:
        assert row['protocol_sha256'] == protocol_sha
        assert row['identity'] == protocol['identities'][row['map']]
        assert row['requested_seconds'] == 60 and 58 <= row['brief']['totals']['duration_sec'] <= 64
        assert row['brief']['map'] == row['map']
        assert row['brief']['totals']['tick_class'] == 'listen'
        assert row['brief']['lab_identity']['authoritative']
        assert not any('WRONG MAP' in f or 'CONTROLLED FIXTURE' in f for f in row['brief'].get('flags', []))
        start = dt.datetime.fromisoformat(row['started_utc'])
        stop = dt.datetime.fromisoformat(row['stopped_utc'])
        assert registered < start < stop
        assert math.isfinite(row['cpu_seconds']) and row['cpu_seconds'] >= 0
        assert math.isfinite(row['wall_seconds']) and row['wall_seconds'] >= 60
        path = ROOT / f"runs/{row['name']}.log"
        text = path.read_text(errors='replace')
        assert not any(token in text for token in ('BHVFIX ', 'TACFIX begin', 'BHVRPL begin', 'Host_Error'))
        assert ('BHVDBG ' in text) == (row['mode'] == 'on')
        assert path.stat().st_size == row['bytes']
        windows = [dict(zip(('t', 'frames', 'seconds', 'mean_ms', 'max_ms', 'over20', 'over50'), map(float, record)))
                   for record in TIMING.findall(text)]
        assert len(windows) >= 10 and row['timing'] == windows[1:]
        target = tails[row['map']][row['mode']]
        target['windows'] += len(windows)
        target['startup_windows'] += 1
        target['startup_frames'] += windows[0]['frames']
        target['startup_over50'] += windows[0]['over50']
        for key in ('frames', 'over20', 'over50'):
            target[key] += sum(w[key] for w in windows)
        target['max_ms'] = max(target['max_ms'], *(w['max_ms'] for w in windows))
        tapes[row['name']] = dict(sha256=digest(path), bytes=row['bytes'], started_utc=row['started_utc'])
    result = evaluate(rows, 128)
    for map_name in protocol['maps']:
        result['maps'][map_name]['avg_speed_descriptive'] = {
            mode: statistics.mean(r['brief']['totals']['avg_speed'] for r in rows if r['map'] == map_name and r['mode'] == mode)
            for mode in ('off', 'on')}
    amendments = []
    first_attempts = {r['name']: r for r in rows}
    all_attempt_tails = json.loads(json.dumps(tails))
    for amendment_path in sorted((ROOT / 'docs').glob('behaviour-goal-cohort-amendment-*.json')):
        amendment = json.loads(amendment_path.read_text())
        assert amendment['protocol_sha256'] == protocol_sha
        invalid_path = ROOT / f"runs/{amendment['retained_name']}.log"
        assert digest(invalid_path) == amendment['raw_sha256']
        original = first_attempts[amendment['original_name']]
        assert original is next(r for r in rows if r['name'] == amendment['original_name']), 'multiple replacements need explicit first-attempt accounting'
        text = invalid_path.read_text(errors='replace')
        windows = [dict(zip(('t', 'frames', 'seconds', 'mean_ms', 'max_ms', 'over20', 'over50'), map(float, record)))
                   for record in TIMING.findall(text)]
        first_attempts[amendment['original_name']] = dict(original, brief=amendment['native_brief'], timing=windows[1:])
        target = all_attempt_tails[original['map']][original['mode']]
        target['windows'] += len(windows)
        target['startup_windows'] += 1
        target['startup_frames'] += windows[0]['frames']
        target['startup_over50'] += windows[0]['over50']
        for key in ('frames', 'over20', 'over50'):
            target[key] += sum(w[key] for w in windows)
        target['max_ms'] = max(target['max_ms'], *(w['max_ms'] for w in windows))
        amendments.append(dict(path=str(amendment_path.relative_to(ROOT)), sha256=digest(amendment_path), **amendment))
    sensitivity = {}
    for map_name in protocol['maps']:
        pairs = []
        for repeat in range(1, 129):
            prefix = f"{protocol['prefix']}_confirm_{map_name}_"
            pairs.append((first_attempts[f'{prefix}off{repeat}'], first_attempts[f'{prefix}on{repeat}']))
        native_rate = lambda r: r['brief']['totals']['goals'] * 60 / r['brief']['totals']['duration_sec']
        sensitivity[map_name] = dict(
            goals_per_minute=interval([native_rate(on) - native_rate(off) for off, on in pairs], 2, 128),
            frame_ms=frame_interval([frame_mean(on) - frame_mean(off) for off, on in pairs], 128))
    result.update(protocol_sha256=protocol_sha, protocol=protocol, registered_code_audit=code_audit,
                  native_receipts_sha256=digest(receipts), execution=execution,
                  all_complete_timing_windows=tails, tapes=tapes, technical_amendments=amendments,
                  all_attempt_complete_timing_windows=all_attempt_tails,
                  first_attempt_sensitivity=sensitivity,
                  first_attempt_sensitivity_equivalent=all(
                      s['goals_per_minute']['equivalent'] and s['frame_ms']['equivalent'] for s in sensitivity.values()))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('protocol', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    result = audit(args.protocol)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('tapes', 'protocol')}, indent=2))


if __name__ == '__main__':
    main()
