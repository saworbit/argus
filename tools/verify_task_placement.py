"""Check exact fixed-task placement and a fresh lift ride on stock e1m8."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import new_output, private_game, read_tape, run_match, stage_fixture
from argus_source import source_identity
from argus_validation import require
from argus_lab_client import ROOT, Lab, finish_lab, lab_executable


def stage(root, output, source):
    text = (root / 'tools/fixtures/task_placement.qc').read_text(encoding='utf-8')
    return stage_fixture(root, output, source, fixtures={'task_placement.qc': text},
                         frame_wrap='TaskPlacementFixture ();\n    if (!task_fixture_phase) Argus_FrameAll ();')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--lab', type=Path)
    parser.add_argument('--port', type=int, default=26007)
    args = parser.parse_args()
    executable = lab_executable(args.lab)
    output = new_output(args.output, root=ROOT, create=False)
    src = stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'taskcheck') as game:
        binary = output / 'lq1/progs.dat'
        env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(binary), ARGUS_GAME=game.name,
                   ARGUS_RUNS=str(output / 'runs'), ARGUS_PYTHON=sys.executable)
        with (output / 'lab.stderr').open('w') as err:
            lab = Lab(err, env, exe=executable, timeout=30)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False)
                (output / 'compile.json').write_text(json.dumps(compiled, indent=2), encoding='utf-8')
                require(compiled['ok'] and not compiled['installed_to'], compiled)
                shutil.copy2(binary, game / 'progs.dat')
                run_match(lab, 'e1m8', 10, args.prefix, port=args.port, timeout=25,
                          environment=env, stderr_path=output / 'match.stderr')
            finally:
                finish_lab(lab)
        tape, raw = read_tape(output, args.prefix, 'e1m8')
        checks = [line for line in raw.splitlines() if line.startswith('TASKFIX ')]
        receipt = dict(checks=checks, source_sha256=source_identity(src),
                       binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                       raw_sha256=hashlib.sha256(tape.read_bytes()).hexdigest())
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        require(raw.count('BHVRPL begin task_placement') == 1, 'missing fixture quarantine')
        starts = re.findall(r"^ARGTASK \d+ start '([^']+)' goal", raw, re.M)
        require(starts == ['673.0 321.0 -712.0', '1248.0 -704.0 -703.9'], starts)
        require(len(checks) == 3, checks)
        require(checks[0] == 'TASKFIX released lift 0 boarded 0 door 0 ground 0 pending 1', checks)
        require(checks[1] == 'TASKFIX acquired lift 0 boarded 0 door 0 ground 1 pending 1', checks)
        ride = re.fullmatch(r'TASKFIX ride ([\d.]+) ground 1', checks[2])
        require(ride is not None and float(ride[1]) > 8, checks)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
