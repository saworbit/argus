"""Compile and exercise routing contracts in private assets via the native lab."""

from argus_validation import require
from argus_source import source_identity
from argus_fixture_harness import (new_output, stage_fixture, private_game,
    read_tape, frame_ms as measured_frame_ms, run_match)

from run_behaviour_equivalence import lab_executable
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write


def stage(root, output, source=None):
    fixture = (root / 'tools/fixtures/route_distance.qc').read_text(encoding='utf-8')
    return stage_fixture(root, output, source, fixtures={'route_distance.qc': fixture},
                         frame_wrap='RouteDistanceFixture ();\n    if (!rd_done) Argus_FrameAll ();')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--compile-only', action='store_true')
    parser.add_argument('--port', type=int, default=26007)
    parser.add_argument('--lab', type=Path, default=lab_executable())
    args = parser.parse_args()
    require((re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix)))
    require(1024 <= args.port <= 65535, 'invalid fixture port')
    output = new_output(args.output, root=ROOT, create=False)
    src = stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'routecheck') as folder:
        game = folder.name
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
                require((compiled['ok']), compiled)
                shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
                if args.compile_only:
                    print('Private routing fixture compiled; no engine launched.', flush=True)
                    return
                smoke = run_match(lab, 'dm6', 10, args.prefix, port=args.port,
                                  timeout=30, environment=env, stderr_path=output / 'match.stderr')
                write(output / 'experiment.json', smoke)
                raw, text = read_tape(output, args.prefix, 'dm6')
                checks = re.findall(r'^RDFIX check (\w+)\s+([01])$', text, re.M)
                require((len(checks) == 29 and text.count('RDFIX begin') == 1), checks)
                frame_ms = measured_frame_ms(text, 'RDFIX', args.ticrate)
                failures = [label for label, ok in checks if ok == '0']
                require((f'RDFIX end checks 29 failures {len(failures)}' in text))
                receipt = dict(checks=checks, failures=failures,
                    frame_ms=frame_ms, requested_ticrate=args.ticrate,
                    source_sha256=source_identity(src), raw_sha256=digest(raw),
                    binary_sha256=digest(folder / 'progs.dat'))
                write(output / 'receipt.json', receipt)
                require((bool(failures) == args.expect_failure), failures)
                print(json.dumps(receipt), flush=True)
            finally:
                native.finish_lab(lab)


if __name__ == '__main__':
    main()
