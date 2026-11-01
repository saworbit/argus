"""Run blocked-walk regressions in real engine physics using the native lab."""

from argus_validation import require
from argus_source import source_identity
from argus_fixture_harness import (new_output, stage_fixture, private_game,
    read_tape, check_tape, frame_ms as measured_frame_ms, run_match)

from run_behaviour_equivalence import lab_executable
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write

CORE_LABELS = ('walks_out_before_freeze', 'continuous_motion', 'still_shoots',
               'goal_preserved', 'pain_exercised', 'alive_and_dry')
GUARD_LABELS = ('clear_exit_armed', 'live_body_cancels_exit', 'mover_wait_held',
                'mover_rescue_held', 'typed_jump_held', 'swim_held', 'task_held', 'chosen_pause_held',
                'airborne_held', 'respawn_clears_recovery')


def stage(root, output, source=None, seat='original'):
    base = Path(source or root / 'src')
    candidate = 'Argus_RecoveryWalk' in (base / 'argus.qc').read_text(encoding='utf-8')
    fixture = (root / 'tools/fixtures/freeze_recovery.qc').read_text(encoding='utf-8')
    if candidate: fixture = '#define RECOVERY_CANDIDATE\n' + fixture
    require(seat in ('original', 'corner', 'south'), 'invalid recovery seat')
    if seat != 'original': fixture = '#define FR_' + seat.upper() + '_SEAT\n' + fixture
    stage_fixture(root, output, source, fixtures={'freeze_recovery.qc': fixture},
                  frame_wrap='if (time < 2) Argus_FrameAll ();\n    FreezeRecoveryFixture ();')
    return candidate


def inspect_fixture(text, candidate, ticrate, rescue=False):
    check_tape(text)
    checks = re.findall(r'^FRFIX check (\w+)\s+([01])$', text, re.M)
    expected = list(CORE_LABELS) + (list(GUARD_LABELS) if candidate else [])
    if not candidate:
        expected[0] = 'control_reproduces_pin'
    elif rescue:
        expected[:2] = ['rescues_pin_before_freeze', 'bounded_rescue_count']
    if rescue:
        expected[2] = 'fire_when_visible'
    require(([label for label, _ in checks] == expected), 'missing, duplicate or reordered checks')
    require((text.count('FRFIX begin') == 1), 'missing or repeated fixture')
    frame_ms = measured_frame_ms(text, 'FRFIX', ticrate)
    failures = [label for label, ok in checks if ok == '0']
    require((f'FRFIX end checks {len(checks)} failures {len(failures)}' in text))
    outcome = re.findall(r'^FRFIX result .+$', text, re.M)
    require((len(outcome) == 1), 'missing or repeated physical result')
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
    require((re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix)))
    maps = args.maps.split(',')
    require((set(maps) <= {'e1m7', 'dm6', 'lqdm2', 'e1m1'} and maps and len(set(maps)) == len(maps)))
    require((1024 <= args.port <= 65535))
    output = new_output(args.output, root=ROOT, create=False)
    candidate = stage(ROOT, output, args.source, args.seat)
    src = output / 'src'
    with private_game(ROOT, args.prefix, 'freezecheck') as folder:
        game = folder.name
        executable = lab_executable()
        env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
                   ARGUS_RUNS=str(output / 'runs'), ARGUS_GAME=game,
                   ARGUS_PYTHON=sys.executable, ARGUS_TICRATE=str(args.ticrate))
        receipts = []
        with (output / 'lab.stderr').open('w') as err:
            lab = Lab(err, env, exe=executable, timeout=900)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False)
                write(output / 'compile.json', compiled)
                require((compiled['ok']), compiled)
                shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
                for map_name in maps:
                    result = run_match(lab, map_name, 10, args.prefix + '_' + map_name, port=args.port, timeout=40, environment=env, stderr_path=output / (map_name + '.stderr'))
                    write(output / (map_name + '.match.json'), result)
                    raw, text = read_tape(output, args.prefix + '_' + map_name, map_name)

                    receipt = dict(map=map_name, candidate=candidate, seat=args.seat,
                        **inspect_fixture(text, candidate, args.ticrate,
                                          map_name in ('lqdm2', 'e1m1') or args.seat == 'corner'),
                        source_sha256=source_identity(src), raw_sha256=digest(raw),
                        source_files={p.relative_to(src).as_posix(): digest(p)
                                      for p in sorted(src.rglob('*')) if p.is_file()
                                      and p.suffix in ('.qc', '.src', '.json')},
                        binary_sha256=digest(folder / 'progs.dat'))
                    receipts.append(receipt); write(output / 'receipt.json', receipts)
                    print(json.dumps({k: v for k, v in receipt.items() if k != 'source_files'}), flush=True)
                require((all(not r['failures'] for r in receipts)), [
                    (r['map'], r['failures']) for r in receipts])
            finally:
                native.finish_lab(lab)


if __name__ == '__main__':
    main()
