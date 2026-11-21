"""Replay the four-rise e1m3 shelf climb on the stock BSP."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import (frame_ms, new_output, private_game, read_tape,
                                  run_match, stage_fixture, write_text)
from argus_lab_client import ROOT, Lab, finish_lab, lab_executable
from argus_paths import bsp_path
from argus_validation import require

BSP_SHA256 = '5941c37c67267ae11aff572fdba7f813148cc99da3cfc34d01eea81dc23edfd0'
TAKEOFF = re.compile(r"^TREAD takeoff ([1-4]) pos '([^']+)'$", re.M)
LAND = re.compile(r"^TREAD land ([1-4]) pos '([^']+)' bottom ([01])$", re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--lab', type=Path)
    parser.add_argument('--port', type=int, default=26012)
    args = parser.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,40}', args.prefix), 'invalid private prefix')
    require(1024 <= args.port <= 65535, 'invalid engine port')
    bsp = bsp_path(ROOT, 'e1m3')
    require(bsp is not None and hashlib.sha256(bsp.read_bytes()).hexdigest() == BSP_SHA256,
            'stock e1m3 BSP required')
    output = new_output(args.output, root=ROOT, create=False)
    fixture = (ROOT / 'tools/fixtures/e1m3_shelf_treads.qc').read_text(encoding='utf-8')
    source = stage_fixture(ROOT, output, fixtures={'e1m3_shelf_treads.qc': fixture},
                           frame_wrap='if (time < 2) Argus_FrameAll ();\n    ShelfTreadFixture ();')
    program = output / 'lq1/progs.dat'
    with private_game(ROOT, args.prefix, 'shelftreads', autoexec='sv_protocol 15\nmax_edicts 600\n') as game:
        (game / 'maps').mkdir(exist_ok=True)
        shutil.copyfile(bsp, game / 'maps/e1m3.bsp')
        env = dict(ARGUS_SRC=str(source), ARGUS_PROGS=str(program), ARGUS_RUNS=str(output / 'runs'),
                   ARGUS_GAME=game.name, ARGUS_PYTHON=sys.executable)
        with (output / 'lab.stderr').open('w', encoding='utf-8') as stderr:
            lab = Lab(stderr, env, exe=lab_executable(args.lab), timeout=45)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False)
                write_text(output / 'compile.json', json.dumps(compiled, indent=2))
                require(compiled['ok'] and not compiled['installed_to'], compiled)
                shutil.copyfile(program, game / 'progs.dat')
                for label, rate in [('played', .0139), ('slow', .1)]:
                    name = f'{args.prefix}_{label}'
                    run_match(lab, 'e1m3', 12, name, skill=2, port=args.port, timeout=36,
                              environment={**env, 'ARGUS_TICRATE': str(rate)},
                              stderr_path=output / f'{name}.stderr')
                    raw, tape = read_tape(output, name, 'e1m3')
                    require(f"ARGUS build {compiled['build']}" in tape.splitlines(), 'wrong fixture build')
                    require(tape.count('BHVRPL begin e1m3_tread_chain') == 1, 'wrong fixture')
                    takeoffs = TAKEOFF.findall(tape)
                    landings = LAND.findall(tape)
                    receipts = dict(build=compiled['build'], bsp_sha256=BSP_SHA256,
                                    tape_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                                    frame_ms=frame_ms(tape, 'TREAD', rate),
                                    takeoffs=takeoffs, landings=landings)
                    write_text(output / f'{name}.json', json.dumps(receipts, indent=2))
                    require([int(i) for i, _ in takeoffs] == [1, 2, 3, 4], takeoffs)
                    require(tuple(map(float, takeoffs[0][1].split())) == (873, -494, -160), takeoffs[0])
                    require([int(i) for i, _, _ in landings] == [1, 2, 3, 4], landings)
                    require([p for _, p in takeoffs[1:]] == [p for _, p, _ in landings[:-1]],
                            'a takeoff did not start at the preceding landing')
                    require(all(abs(float(pos.split()[2]) - z) <= 2
                                for (_, pos, _), z in zip(landings, (-128, -104, -72, -40))), landings)
                    done = re.findall(r'^TREAD completed\s+([\d.]+)$', tape, re.M)
                    require(len(done) == 1 and 0 < float(done[0]) < 3, 'chain did not finish in three seconds')
                    print(f'{label}: four landings in {done[0]} seconds, {receipts["frame_ms"]} ms frames')
            finally:
                finish_lab(lab, active=False)


if __name__ == '__main__':
    main()
