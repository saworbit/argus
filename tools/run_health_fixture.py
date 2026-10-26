"""Private controlled-input observation trials through the native lab only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from run_behaviour_equivalence import ROOT, EXE, Lab, identity
from check_perception_fixture import check
from check_health_fixture import check as health_check

INPUTS = '''// PRIVATE controlled-input fixture, never in production progs.src.
float() random =
{
    ar_pf_rngcalls = ar_pf_rngcalls + 1;
    return 0.5;
};
'''


def body(source, name):
    pattern = r'^[^\n]*\b' + re.escape(name) + r'\s*=\s*\n\{\n.*?^\};'
    match = re.search(pattern, source, re.M | re.S)
    assert match, name
    return pattern, match[0]


def prepare(output, legacy):
    assert not output.exists(), 'retain previous build and use a fresh output directory'
    shutil.copytree(ROOT / 'src', output / 'src')
    (output / 'lq1').mkdir()
    source = output / 'src'
    path = source / 'defs.qc'
    original = path.read_text()
    changed, count = re.subn(r'float\(\) random\s*= #7;[^\n]*',
                            'float() random; // PRIVATE controlled input', original)
    assert count == 1
    path.write_text(changed, newline='\r\n')
    path = source / 'progs.src'
    path.write_text(path.read_text().replace('localized_text.qc',
                    'perception_inputs.qc\nlocalized_text.qc'), newline='\r\n')
    (source / 'perception_inputs.qc').write_text(INPUTS, newline='\r\n')
    path = source / 'world.qc'
    original = path.read_text()
    assert original.count('Argus_CountSlots ();') == 1
    path.write_text(original.replace('Argus_CountSlots ();',
        'Argus_CountSlots ();\n    ar_pf_inputfixed = 1;\n    dprint ("BHVRPL begin perception_inputs\\n");'), newline='\r\n')
    if legacy:
        # Positive control: restore the exact previous combat, acquisition and hunch bodies
        # in this PRIVATE copy. New observation helpers and fixture stay intact.
        original = (ROOT / 'backups/perception-step1b/control-src/argus.qc').read_text()
        path = source / 'argus.qc'
        changed = path.read_text()
        for name in ('Argus_Combat', 'Argus_Perceive', 'Argus_Hunch'):
            pattern, old = body(original, name)
            changed, count = re.subn(pattern, lambda _: old, changed, flags=re.M | re.S)
            assert count == 1
        path.write_text(changed, newline='\r\n')
    return dict(ARGUS_SRC=str(source), ARGUS_PROGS=str(output / 'lq1/progs.dat'))


def audit_private(output, legacy):
    src = output / 'src'
    paths = {p.relative_to(ROOT / 'src') for p in (ROOT / 'src').rglob('*') if p.is_file()}
    assert {p.relative_to(src) for p in src.rglob('*') if p.is_file()} == paths | {Path('perception_inputs.qc')}
    assert (src / 'perception_inputs.qc').read_text() == INPUTS
    for path in paths:
        original = (ROOT / 'src' / path).read_text(errors='replace')
        changed = (src / path).read_text(errors='replace')
        if path == Path('defs.qc'):
            declaration = re.search(r'float\(\) random\s*= #7;[^\n]*', original)[0]
            changed = changed.replace('float() random; // PRIVATE controlled input', declaration)
        if path == Path('progs.src'):
            changed = changed.replace('perception_inputs.qc\n', '')
        if path == Path('world.qc'):
            changed = changed.replace('\n    ar_pf_inputfixed = 1;\n    dprint ("BHVRPL begin perception_inputs\\n");', '')
        if path == Path('argus.qc') and legacy:
            baseline = (ROOT / 'backups/perception-step1b/control-src/argus.qc').read_text()
            for name in ('Argus_Combat', 'Argus_Perceive', 'Argus_Hunch'):
                pattern, current = body(original, name)
                assert body(changed, name)[1] == body(baseline, name)[1], 'legacy control is not the exact saved body'
                changed = re.sub(pattern, lambda _: current, changed, flags=re.M | re.S)
        assert original == changed, 'unexpected private source change ' + str(path)
    assert 'perception_inputs.qc' not in (ROOT / 'src/progs.src').read_text()
    assert re.search(r'float\(\) random\s*= #7;', (ROOT / 'src/defs.qc').read_text())
    return dict(source_files_restored=len(paths), production_rng_builtin7=True,
                legacy_bodies_only=legacy)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--prefix', required=True)
    ap.add_argument('--legacy', action='store_true')
    ap.add_argument('--maps', default='dm2,dm4')
    ap.add_argument('--steps', default='played,slow')
    ap.add_argument('--rings', default='0,1')
    ap.add_argument('--repeats', type=int, default=2)
    args = ap.parse_args()
    assert re.fullmatch(r'[a-z0-9_]+', args.prefix) and 1 <= args.repeats <= 3
    maps = args.maps.split(','); steps = args.steps.split(','); rings = list(map(int, args.rings.split(',')))
    assert set(maps) <= {'dm2', 'dm4'} and set(steps) <= {'played', 'slow'} and set(rings) <= {0, 1}
    output = args.output.resolve()
    environment = prepare(output, args.legacy)
    source_audit = audit_private(output, args.legacy)
    results = []
    lab_binary = ROOT / 'engine/argus/progs.dat'
    shipped = ROOT / 'backups/perception-step1b/shipped-engine.dat'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(lab_binary) == digest(shipped), 'unknown lab binary; preserve it'
    with (output / 'lab.stderr').open('w') as err:
        lab = Lab(err, environment)
        active = False
        try:
            compile_result = lab.call('compile_qc', install=False)
            (output / 'compile.json').write_text(json.dumps(compile_result, indent=2))
            assert compile_result['ok'], compile_result
            shutil.copy2(output / 'lq1/progs.dat', lab_binary)
            pinned = identity('dm2')
            smoke = lab.call('experiment', map=maps[0], duration_sec=10, skill=1, compile=False,
                             repeats=1, primary='engagements', run_name=args.prefix + '_private_smoke')
            (output / 'smoke.json').write_text(json.dumps(smoke, indent=2))
            for map_name in maps:
                for step in steps:
                    for ring in rings:
                        name = f'{args.prefix}_{map_name}_{step}_ring{ring}'
                        assert not (ROOT / f'runs/{name}.log').exists()
                        start = lab.call('match_start', map=map_name, duration_sec=90, skill=1,
                                         run_name=name, dedicated_slots=8)
                        active = True
                        deadline = time.monotonic() + 10
                        while True:
                            status = lab.call('match_status')
                            if 'ARGLOG ' in json.dumps(status): break
                            assert status.get('running') and time.monotonic() < deadline, 'server did not become healthy'
                            time.sleep(.05)
                        lab.call('match_command', command=f'sys_ticrate {0.1 if step == "slow" else 0.0139}; developer 1; scratch1 593; scratch2 {ring}; scratch3 1; scratch4 594')
                        # One real-client invocation per trial: server changes
                        # the ID first; impulse transport owns its own seat.
                        for trial in range(1, args.repeats + 1):
                            lab.call('tune', command=f'scratch3 {trial}')
                            client = subprocess.run([str(EXE), 'client', 'impulse', '219', '0.6'], cwd=ROOT,
                                env=dict(os.environ, ARGUS_ROOT=str(ROOT)), capture_output=True, text=True, encoding='utf-8', timeout=20)
                            assert client.returncode == 0, client.stderr
                        stop = lab.call('match_stop'); active = False
                        text = (ROOT / f'runs/{name}.log').read_text(errors='replace')
                        assert 'BHVRPL begin perception_inputs' in text
                        row = dict(name=name, map=map_name, step=step, ring=ring, legacy=args.legacy,
                                   identity=identity(map_name), start=start, stop=stop,
                                   raw_sha256=digest(ROOT / f'runs/{name}.log'))
                        try:
                            row['trials'] = check(text, map_name, ring, list(range(1, args.repeats + 1)))
                            assert all((90 <= t['dt_ms'] <= 101) if step == 'slow'
                                       else (10 <= t['dt_ms'] <= 30) for t in row['trials']), 'wrong measured cadence'
                            row['health_trials'] = health_check(text, map_name, list(range(1,args.repeats+1)), allow_failed=args.legacy)
                            row['accepted'] = all(not t['failures'] for t in row['health_trials'])
                        except AssertionError as error:
                            row.update(accepted=False, rejection=str(error))
                        results.append(row)
                        (output / 'results.json').write_text(json.dumps(dict(audit=source_audit, rows=results), indent=2))
                        print(json.dumps(dict(name=name, accepted=row['accepted'], rejection=row.get('rejection'))), flush=True)
                        if not args.legacy:
                            assert row['accepted'], row.get('rejection', row.get('health_trials'))
            assert identity('dm2') == pinned, 'production inputs changed during fixture matrix'
            audit_private(output, args.legacy)
        finally:
            if active: lab.call('match_stop')
            lab.close()
            shutil.copy2(shipped, lab_binary)


if __name__ == '__main__':
    main()
