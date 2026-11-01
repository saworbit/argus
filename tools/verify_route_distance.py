"""Compile and exercise routing contracts in private assets via the native lab."""

from argus_source import source_identity

from run_behaviour_equivalence import lab_executable, lab_cli
import argparse
import json
from pathlib import Path
import re
import shutil
import os
import subprocess
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--compile-only', action='store_true')
    parser.add_argument('--port', type=int)
    parser.add_argument('--lab', type=Path, default=lab_executable())
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_]+', args.prefix)
    output = args.output.resolve()
    assert not output.exists()
    shutil.copytree(args.source, output / 'src')
    (output / 'lq1').mkdir()
    (output / 'runs').mkdir()
    src = output / 'src'
    shutil.copy2(ROOT / 'tools/fixtures/route_distance.qc', src / 'route_distance.qc')
    path = src / 'progs.src'
    text = path.read_text(); assert text.count('\nworld.qc\n') == 1
    path.write_text(text.replace('\nworld.qc\n', '\nroute_distance.qc\nworld.qc\n'))
    path = src / 'world.qc'
    text = path.read_text(); assert text.count('Argus_FrameAll ();') == 1
    path.write_text(text.replace('Argus_FrameAll ();',
                    'RouteDistanceFixture ();\n    if (!rd_done) Argus_FrameAll ();'))
    game = 'routecheck_' + args.prefix
    folder = ROOT / 'engine' / game
    assert not folder.exists(); folder.mkdir()
    for name in ('progs', 'maps', 'sound', 'gfx'):
        original = ROOT / 'engine/argus' / name
        if original.exists(): shutil.copytree(original, folder / name)
    shutil.copy2(ROOT / 'game/argus/autoexec.cfg', folder / 'autoexec.cfg')
    executable = lab_executable(args.lab)
    env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
               ARGUS_RUNS=str(output / 'runs'), ARGUS_GAME=game,
               ARGUS_PYTHON=sys.executable, ARGUS_TICRATE=str(args.ticrate))
    with (output / 'lab.stderr').open('w') as err:
        lab = Lab(err, env, exe=executable, timeout=900)
        try:
            lab.call('see', what='project')
            compiled = lab.call('compile_qc', install=False)
            write(output / 'compile.json', compiled)
            assert compiled['ok'], compiled
            shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
            if args.compile_only:
                print('Private routing fixture compiled; no engine launched.', flush=True)
                return
            if args.port:
                assert 1024 <= args.port <= 65535
                result = lab_cli(executable, 'match', 'dm6', '10', args.prefix, '--skill', '2', '--port', str(args.port), cwd=ROOT, environment=dict(os.environ, ARGUS_ROOT=str(ROOT), **env), timeout=30)
                (output / 'match.stderr').write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                smoke = json.loads(result.stdout)
            else:
                smoke = lab.call('experiment', map='dm6', duration_sec=10, skill=2,
                    compile=False, repeats=1, run_name=args.prefix, primary='stall_parity')
            write(output / 'experiment.json', smoke)
            raw = next((output / 'runs').glob('*.log'))
            text = raw.read_text(errors='replace')
            assert not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error'))
            checks = re.findall(r'^RDFIX check (\w+)\s+([01])$', text, re.M)
            assert len(checks) == 29 and text.count('RDFIX begin') == 1, checks
            cadence = re.search(r'^RDFIX begin dt_ms\s+([\d.]+)$', text, re.M)
            assert cadence, 'missing measured cadence'
            frame_ms = float(cadence[1])
            assert (90 <= frame_ms <= 110) if args.ticrate == .1 else (10 <= frame_ms <= 30)
            failures = [label for label, ok in checks if ok == '0']
            assert f'RDFIX end checks 29 failures {len(failures)}' in text
            receipt = dict(checks=checks, failures=failures,
                frame_ms=frame_ms, requested_ticrate=args.ticrate,
                source_sha256=source_identity(src), raw_sha256=digest(raw),
                binary_sha256=digest(folder / 'progs.dat'))
            write(output / 'receipt.json', receipt)
            assert bool(failures) == args.expect_failure, failures
            print(json.dumps(receipt), flush=True)
        finally:
            lab.call('match_stop')
            lab.close()


if __name__ == '__main__':
    main()
