"""Check both stock lqdm2 health approaches and an upper-floor control."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from argus_bsp import Bsp, CONTENTS_EMPTY, CONTENTS_SOLID
from argus_fixture_harness import (frame_ms, new_output, private_game, read_tape,
                                  run_match, stage_fixture, write_text)
from argus_lab_client import ROOT, Lab, finish_lab, lab_executable
from argus_paths import bsp_path
from argus_validation import require

PIN = (-272, 207.75, 216)
FIRST_PACK = (-248, 264, 224)
SECOND_PACK = (-200, 312, 224)
CASES = ((PIN, FIRST_PACK), (PIN, SECOND_PACK), ((-239, 209, 248), SECOND_PACK),
         ((-264, 200, 216), SECOND_PACK))


def check_case(tape, case, seat, pack):
    start = re.search(r"^HA start (\d+) pos '([^']+)' target '([^']+)' support world$", tape, re.M)
    require(start is not None and int(start[1]) == case, 'wrong fixture start')
    placed, target = (tuple(map(float, start[i].split())) for i in (2, 3))
    require(len(placed) == 3 and all(abs(a - b) <= .1 for a, b in zip(placed, seat))
            and target == pack, 'wrong stock seat or target')
    begin, end = start.end(), tape.index('HA end ', start.end())
    route = tape[begin:end]
    outcomes = re.findall(r'^HA end elapsed\s+([\d.]+) taken 1 hp\s+([\d.]+)$', tape, re.M)
    require(len(outcomes) == 1 and 0 < float(outcomes[0][0]) < 6
            and float(outcomes[0][1]) >= 75, 'stock health pickup failed')
    require(re.search(r'^ARGEVT \S+ goal_pickup_v1 item_health$', route, re.M),
            'missing accepted goal pickup')
    require(' unstick ' not in route, 'unstick warp during approach')
    if case == 2:
        require(re.search(r"^HA mode 2 node '\s*-271\.0\s+209\.0\s+248\.0' pos '[^']+216\.0'$",
                          route, re.M), 'the route skipped the climb seat from below')
    if case == 3:
        require("HA mode 1 node " in route, 'upper-floor direct approach was lost')
    return dict(case=case, seconds=float(outcomes[0][0]), start=placed, pack=target,
                frame_ms=frame_ms(tape, 'HA', .0139))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--lab', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--port', type=int, default=26120)
    args = parser.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,35}', args.prefix), 'invalid private prefix')
    require(1024 <= args.port <= 65532, 'invalid engine ports')
    bsp = bsp_path(ROOT, 'lqdm2')
    require(bsp is not None, 'stock lqdm2 BSP required')
    stock = Bsp(bsp)
    for (x, y, z), _ in CASES:
        require(stock.h1(x, y, z) == CONTENTS_EMPTY
                and stock.h1(x, y, z - .25) == CONTENTS_SOLID
                and stock.check_bottom(x, y, z), 'fixture seat has no dry support')
    bsp_sha = hashlib.sha256(bsp.read_bytes()).hexdigest()
    output = new_output(args.output, root=ROOT, create=False)
    fixture = (ROOT / 'tools/fixtures/lqdm2_health_approach.qc').read_text(encoding='utf-8')
    source = stage_fixture(ROOT, output, args.source, fixtures={'health_approach_fixture.qc': fixture},
                           frame_wrap='HealthApproachBefore ();\n    Argus_FrameAll ();\n    HealthApproachAfter ();')
    program = output / 'lq1/progs.dat'
    env = dict(ARGUS_SRC=str(source), ARGUS_PROGS=str(program), ARGUS_PYTHON=sys.executable)
    exe = lab_executable(args.lab)
    with (output / 'lab.stderr').open('w', encoding='utf-8') as stderr:
        lab = Lab(stderr, env, exe=exe, timeout=45)
        try:
            lab.call('see', what='project')
            compiled = lab.call('compile_qc', install=False)
            write_text(output / 'compile.json', json.dumps(compiled, indent=2))
            require(compiled['ok'] and not compiled['installed_to'], compiled)

            def replay(entry):
                case, (seat, pack) = entry
                name = f'{args.prefix}_{case}'
                run = output / name
                (run / 'runs').mkdir(parents=True)
                autoexec = f'sv_protocol 15\nmax_edicts 600\nscratch2 {case}\n'
                with private_game(ROOT, name, 'healthapproach', autoexec=autoexec) as game:
                    (game / 'maps').mkdir(exist_ok=True)
                    shutil.copyfile(bsp, game / 'maps/lqdm2.bsp')
                    shutil.copyfile(program, game / 'progs.dat')
                    run_env = dict(env, ARGUS_RUNS=str(run / 'runs'), ARGUS_GAME=game.name,
                                   ARGUS_TICRATE='.0139')
                    run_match(lab, 'lqdm2', 10, name, port=args.port+case-1, skill=3, timeout=30,
                              environment=run_env, stderr_path=run / 'match.stderr')
                raw, tape = read_tape(run, name, 'lqdm2')
                require(f"ARGUS build {compiled['build']}" in tape.splitlines(), 'wrong fixture build')
                require(tape.count('BHVRPL begin lqdm2_health_approach') == 1, 'wrong fixture')
                row = dict(build=compiled['build'], bsp_sha256=bsp_sha,
                           tape_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                           **check_case(tape, case, seat, pack))
                write_text(run / 'receipt.json', json.dumps(row, indent=2))
                return row

            with ThreadPoolExecutor(max_workers=2) as workers:
                for row in workers.map(replay, enumerate(CASES, 1)):
                    print(f"Case {row['case']}: stock health pickup in {row['seconds']} seconds", flush=True)
        finally:
            finish_lab(lab, active=False)


if __name__ == '__main__':
    main()
