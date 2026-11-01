"""Bounded control/candidate perception smoke cohort using native lab metrics.

Eight counterbalanced pairs per map; not a powered gameplay equivalence test.
"""

from run_behaviour_equivalence import lab_executable, lab_cli
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from run_behaviour_equivalence import finish_lab, ROOT, Lab, identity, timing, cpu_seconds

OUT = ROOT / 'backups/perception-step1b'


def source_digest(path):
    h = hashlib.sha256()
    for file in sorted([*path.rglob('*.qc'), *path.rglob('*.src')]):
        h.update(('src/' + file.relative_to(path).as_posix()).encode())
        h.update(b'\0'); h.update(file.read_bytes())
    return h.hexdigest()


def write_comparisons(rows, executable=None):
    executable = lab_executable(executable)
    assert len(rows) == 32, 'complete the fixed cohort before comparison'
    comparisons = {}
    for map_name in ('dm2', 'dm4'):
        names = {}
        for mode in ('control', 'candidate'):
            arm = [r for r in rows if r['map'] == map_name and r['mode'] == mode]
            assert sorted(r['repeat'] for r in arm) == list(range(1, 9))
            for row in arm:
                path = ROOT / f"runs/{row['name']}.log"
                assert hashlib.sha256(path.read_bytes()).hexdigest() == row['raw_sha256']
            names[mode] = ','.join(r['name'] for r in arm)
        command = [str(executable), 'compare', names['candidate'], names['control'], '--primary', 'lava_deaths']
        run = lab_cli(executable, *command[1:], cwd=ROOT, environment=dict(os.environ, ARGUS_ROOT=str(ROOT)), timeout=60)
        assert run.returncode == 0, run.stderr
        # Native compare emits a UTF-8 gate card and findings, not JSON.
        comparisons[map_name] = dict(command=command, returncode=run.returncode,
            stdout=run.stdout, stderr=run.stderr, primary='lava_deaths')
    (OUT / 'balance-native-comparisons.json').write_text(json.dumps(comparisons, indent=2))


def main():
    executable = lab_executable()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compare-only', action='store_true', help='export the completed cohort without launching engines')
    args = ap.parse_args()
    if args.compare_only:
        write_comparisons(json.loads((OUT / 'balance-results.json').read_text()))
        return
    protocol = json.loads((OUT / 'validation-plan.json').read_text())
    assert 'Eight adjacent counterbalanced' in protocol['ordinary']
    binaries = {mode: OUT / file for mode, file in [
        ('control', 'control-progs.dat'), ('candidate', 'candidate-final-progs.dat')]}
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    binary_hashes = {mode:digest(path) for mode,path in binaries.items()}
    sources = dict(control=source_digest(OUT / 'control-src'), candidate=source_digest(ROOT / 'src'))
    engine = ROOT / 'engine/argus/progs.dat'; shipped = OUT / 'shipped-engine.dat'
    assert engine.read_bytes() == shipped.read_bytes(), 'unknown installed lab binary'
    result_path = OUT / 'balance-results.json'
    assert not result_path.exists(), 'retain old cohort and use a new registration for more tapes'
    rows = []
    base_identity = {map_name:identity(map_name) for map_name in ('dm2','dm4')}
    (OUT / 'balance-pins.json').write_text(json.dumps(dict(source=sources,binary=binary_hashes,base_identity=base_identity),indent=2))
    try:
        for repeat in range(1, 9):
            for map_name in ('dm2', 'dm4') if repeat % 2 else ('dm4', 'dm2'):
                for mode in ('control', 'candidate') if repeat % 2 else ('candidate', 'control'):
                    name = f'hi1_balance_{map_name}_{mode}{repeat}'
                    assert not (ROOT / f'runs/{name}.log').exists()
                    assert digest(binaries[mode]) == binary_hashes[mode]
                    assert source_digest(ROOT / 'src') == sources['candidate']
                    assert source_digest(OUT / 'control-src') == sources['control']
                    shutil.copy2(binaries[mode], engine)
                    before = identity(map_name)
                    assert before == dict(base_identity[map_name],binary_sha256=binary_hashes[mode])
                    active = False
                    with (OUT / f'{name}.stderr').open('w') as err:
                        lab = Lab(err, exe=executable)
                        try:
                            start = lab.call('match_start', map=map_name, duration_sec=80, skill=1, run_name=name)
                            active = True
                            deadline = time.monotonic() + 10
                            while True:
                                status = lab.call('match_status')
                                if 'ARGLOG ' in json.dumps(status): break
                                assert status.get('running') and time.monotonic() < deadline
                                time.sleep(.05)
                            lab.call('match_command', command='scratch1 591; scratch4 0')
                            cpu_start = cpu_seconds(start['pid']); wall_start = time.monotonic()
                            time.sleep(60)
                            wall = time.monotonic() - wall_start
                            cpu = cpu_seconds(start['pid']) - cpu_start
                            stop = lab.call('match_stop'); active = False
                            brief = lab.call('brief_run', log=name, map=map_name)
                            path = ROOT / f'runs/{name}.log'; text = path.read_text(errors='replace')
                            (OUT / f'{name}.attempt.json').write_text(json.dumps(dict(name=name,map=map_name,mode=mode,repeat=repeat,identity=before,start=start,stop=stop,brief=brief,raw_sha256=digest(path)),indent=2))
                            assert not any(tag in text for tag in ('BHVFIX ', 'PERFIX ', 'HIFIX ', 'BHVRPL ', 'BHVDBG ', 'TACFIX begin', 'Host_Error', 'Program error'))
                            assert not any('WRONG MAP' in flag or 'CONTROLLED FIXTURE' in flag for flag in brief['flags'])
                            assert brief['map'] == map_name and brief['totals']['tick_class'] == 'listen'
                            assert identity(map_name) == before
                            assert 58 <= brief['totals']['duration_sec'] <= 64
                            row = dict(name=name, map=map_name, mode=mode, repeat=repeat,
                                identity=before, executed_source_sha256=sources[mode],
                                inspected_candidate_source_sha256=before['source_sha256'],
                                cpu_seconds=cpu, wall_seconds=wall, timing=timing(text),
                                start=start, stop=stop, brief=brief, raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                            rows.append(row); result_path.write_text(json.dumps(rows, indent=2))
                            print(json.dumps(dict(name=name, completed=len(rows), goals=brief['totals']['goals'],
                                frags=brief['totals']['frags'], deaths=brief['totals']['deaths'])), flush=True)
                        finally:
                            finish_lab(lab, active)
        write_comparisons(rows)
    finally:
        shutil.copy2(shipped, engine)


if __name__ == '__main__':
    main()
