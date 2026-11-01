"""Run blocked-walk regressions in real engine physics using the native lab."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write, lab_executable

CORE_LABELS = ('walks_out_before_freeze', 'continuous_motion', 'still_shoots',
               'goal_preserved', 'pain_exercised', 'alive_and_dry')
GUARD_LABELS = ('clear_exit_armed', 'live_body_cancels_exit', 'mover_wait_held',
                'mover_rescue_held', 'typed_jump_held', 'swim_held', 'task_held', 'chosen_pause_held',
                'airborne_held', 'respawn_clears_recovery')


def stage(root, output, source=None, seat='original'):
    """Stage the native fixture without requiring game assets or an engine."""
    shutil.copytree(source or root / 'src', output / 'src')
    (output / 'lq1').mkdir(); (output / 'runs').mkdir()
    src = output / 'src'
    candidate = 'Argus_RecoveryWalk' in (src / 'argus.qc').read_text()
    fixture = (root / 'tools/fixtures/freeze_recovery.qc').read_text()
    if candidate:
        fixture = '#define RECOVERY_CANDIDATE\n' + fixture
    if seat != 'original':
        assert seat in ('corner', 'south')
        fixture = '#define FR_' + seat.upper() + '_SEAT\n' + fixture
    (src / 'freeze_recovery.qc').write_text(fixture)
    path = src / 'progs.src'
    text = path.read_text(); assert text.count('\nworld.qc\n') == 1
    path.write_text(text.replace('\nworld.qc\n', '\nfreeze_recovery.qc\nworld.qc\n'))
    path = src / 'world.qc'
    text = path.read_text(); assert text.count('Argus_FrameAll ();') == 1
    path.write_text(text.replace('Argus_FrameAll ();',
        'if (time < 2) Argus_FrameAll ();\n    FreezeRecoveryFixture ();'))
    return candidate


def inspect_fixture(text, candidate, ticrate, rescue=False):
    assert not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error'))
    checks = re.findall(r'^FRFIX check (\w+)\s+([01])$', text, re.M)
    expected = list(CORE_LABELS) + (list(GUARD_LABELS) if candidate else [])
    if not candidate:
        expected[0] = 'control_reproduces_pin'
    elif rescue:
        expected[:2] = ['rescues_pin_before_freeze', 'bounded_rescue_count']
    if rescue:
        expected[2] = 'fire_when_visible'
    assert [label for label, _ in checks] == expected, 'missing, duplicate or reordered checks'
    assert text.count('FRFIX begin') == 1, 'missing or repeated fixture'
    cadence = re.search(r'^FRFIX begin dt_ms\s+([\d.]+)$', text, re.M)
    assert cadence, 'missing measured cadence'
    frame_ms = float(cadence[1])
    assert (90 <= frame_ms <= 110) if ticrate == .1 else (10 <= frame_ms <= 30)
    failures = [label for label, ok in checks if ok == '0']
    assert f'FRFIX end checks {len(checks)} failures {len(failures)}' in text
    outcome = re.findall(r'^FRFIX result .+$', text, re.M)
    assert len(outcome) == 1, 'missing or repeated physical result'
    return dict(checks=checks, failures=failures, frame_ms=frame_ms, result=outcome)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--port', type=int, default=26004)
    parser.add_argument('--maps', default='e1m7,dm6,e1m1')
    parser.add_argument('--seat', choices=('original', 'corner', 'south'), default='original')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_]+', args.prefix)
    maps = args.maps.split(',')
    assert set(maps) <= {'e1m7', 'dm6', 'lqdm2', 'e1m1'} and maps and len(set(maps)) == len(maps)
    assert 1024 <= args.port <= 65535
    output = args.output.resolve()
    assert output.is_relative_to((ROOT / 'backups').resolve())
    assert not output.exists()
    candidate = stage(ROOT, output, args.source, args.seat)
    src = output / 'src'
    game = 'freezecheck_' + args.prefix
    folder = ROOT / 'engine' / game
    assert not folder.exists(); folder.mkdir()
    for name in ('progs', 'maps', 'sound', 'gfx'):
        original = ROOT / 'engine/argus' / name
        if original.exists(): shutil.copytree(original, folder / name)
    shutil.copy2(ROOT / 'game/argus/autoexec.cfg', folder / 'autoexec.cfg')
    native.EXE = lab_executable()
    env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
               ARGUS_RUNS=str(output / 'runs'), ARGUS_GAME=game,
               ARGUS_PYTHON=sys.executable, ARGUS_TICRATE=str(args.ticrate))
    receipts = []
    with (output / 'lab.stderr').open('w') as err:
        lab = Lab(err, env)
        try:
            lab.call('see', what='project')
            compiled = lab.call('compile_qc', install=False)
            write(output / 'compile.json', compiled)
            assert compiled['ok'], compiled
            shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
            for map_name in maps:
                result = subprocess.run([str(native.EXE), 'match', map_name, '10',
                    args.prefix + '_' + map_name, '--skill', '2', '--port', str(args.port)],
                    cwd=ROOT, env=dict(os.environ, ARGUS_ROOT=str(ROOT), **env),
                    capture_output=True, text=True, encoding='utf-8', timeout=40)
                (output / (map_name + '.stderr')).write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                write(output / (map_name + '.match.json'), json.loads(result.stdout))
                raw = output / 'runs' / (args.prefix + '_' + map_name + '.log')
                text = raw.read_text(errors='replace')
                assert f'ARGUS init on {map_name}\n' in text, 'wrong map'
                receipt = dict(map=map_name, candidate=candidate, seat=args.seat,
                    **inspect_fixture(text, candidate, args.ticrate,
                                      map_name in ('lqdm2', 'e1m1') or args.seat == 'corner'),
                    source_sha256=digest(src / 'argus.qc'), raw_sha256=digest(raw),
                    source_files={p.relative_to(src).as_posix(): digest(p)
                                  for p in sorted(src.rglob('*')) if p.is_file()
                                  and p.suffix in ('.qc', '.src', '.json')},
                    binary_sha256=digest(folder / 'progs.dat'))
                receipts.append(receipt); write(output / 'receipt.json', receipts)
                print(json.dumps({k: v for k, v in receipt.items() if k != 'source_files'}), flush=True)
            assert all(not r['failures'] for r in receipts), [
                (r['map'], r['failures']) for r in receipts]
        finally:
            native.finish_lab(lab)


if __name__ == '__main__':
    main()
