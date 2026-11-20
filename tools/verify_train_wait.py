"""Check displaced train waits and working boarding on stock dm2."""

import argparse
import hashlib
import json
from math import dist
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import (frame_ms, new_output, private_game, read_tape,
                                  run_match, stage_fixture, write_text)
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import ROOT, Lab, finish_lab, lab_executable

EXIT = (1921, -1047, 344)
START = re.compile(r"^TW start (\d+) support 1 pos '([^']+)' car '([^']+)' carvel '([^']+)'$", re.M)
SAMPLE = re.compile(r"^TW sample (\d+) elapsed\s+([\d.]+) pos '([^']+)' car '[^']+' "
                    r"hold ([01]) hp\s+([\d.]+) goal ([01]) node '([^']+)'$", re.M)
EVENT = re.compile(r'^TW (release|board|replan) (\d+) elapsed\s+([\d.]+)$', re.M)


def point(text):
    result = tuple(map(float, text.split()))
    require(len(result) == 3, 'invalid fixture point')
    return result


def inspect_fixture(raw, control=False):
    require(raw.splitlines().count('BHVRPL begin train_wait') == 1, 'missing fixture marker')
    ms = frame_ms(raw, 'TW', .0139)
    starts = START.findall(raw)
    require([int(row[0]) for row in starts] == list(range(1, 10)), 'missing start or floor support')
    events = {(kind, num): float(sec) for kind, num, sec in EVENT.findall(raw)}
    samples = SAMPLE.findall(raw)
    result = []
    for case, start, car, velocity in starts:
        number = int(case)
        seat = point(start)
        expected = (1375, -714, 344) if number <= 3 else (1375, -729.7, 344)
        if number > 6:
            expected = (1441, -1015, 344)
        require(seat == expected, 'wrong stock position')
        observations = [(float(t), point(p), int(hold), float(hp), int(goal), point(node))
                        for n, t, p, hold, hp, goal, node in samples if n == case]
        require(len(observations) >= 30 and observations[0][0] == 0, 'short case')
        require(dist(observations[0][1], seat) <= 2 and observations[0][-1] == EXIT,
                'case changed the placed seat or train exit')
        released = events.get(('release', case))
        boarded = events.get(('board', case))
        entry = dict(case=number, seat=seat, car=point(car), car_velocity=point(velocity),
                     release_seconds=released, board_seconds=boarded)
        if number <= 6:
            bound = 15 if control else 8
            require(boarded is None and released is not None and bound <= released <= bound + .1,
                    f'case {case} released at {released} s')
            require(all(dist(p, seat) < 2 and hold and hp >= 100 and goal
                        for t, p, hold, hp, goal, _ in observations if t < released),
                    f'case {case} did not reproduce a stationary train hold')
            limit = 18 if control else 10
            moved = any(released <= t < limit and hp >= 100 and dist(p, seat) > 36
                        for t, p, _, hp, _, _ in observations)
            replanned = events.get(('replan', case))
            require(moved and replanned is not None and released <= replanned < limit,
                    f'case {case} did not resume safe movement before the limit')
            entry['replan_seconds'] = replanned
        else:
            entry['reached_exit'] = boarded is not None and any(
                t >= boarded and hp > 0 and p[0] >= EXIT[0]
                and abs(p[1] - EXIT[1]) <= 128 and abs(p[2] - EXIT[2]) <= 18
                for t, p, _, hp, _, _ in observations)
        result.append(entry)
    for offset in (0, 3):
        group = result[offset:offset + 3]
        require(len({round(row['car'][0]) for row in group}) == 3
                and {row['car_velocity'][0] > 0 for row in group} == {False, True},
                'missed cases did not sample both live train directions')
    require(any(row['board_seconds'] is not None and row['reached_exit'] for row in result[6:]),
            'no working stock board and exit control')
    return dict(frame_ms=ms, cases=result)


def observe_route_install(source):
    anchor = '    an_bot.ar_hopdoor = 0;\n'
    require(source.count(anchor) == 1, 'route install changed')
    source = source.replace(anchor, anchor + '    TrainWaitRouteReady (an_bot);\n')
    return 'void(entity routed) TrainWaitRouteReady;\n' + source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--lab', type=Path)
    parser.add_argument('--port', type=int, default=26011)
    parser.add_argument('--control', action='store_true')
    args = parser.parse_args()
    output = new_output(args.output, root=ROOT, create=False)
    production = (args.source / 'argus.qc').read_text(encoding='utf-8')
    has_seat = '.entity ar_trainfrom;' in production
    require(has_seat != args.control, 'source does not match the requested arm')
    fixture = (ROOT / 'tools/fixtures/train_wait.qc').read_text(encoding='utf-8')
    if has_seat:
        fixture = '#define TRAIN_WAIT_HAS_SEAT\n' + fixture
    src = stage_fixture(ROOT, output, args.source, fixtures={'train_wait_fixture.qc': fixture},
                        edits={'argus_nav.qc': observe_route_install},
                        frame_wrap='TrainWaitBefore ();\n    Argus_FrameAll ();\n    TrainWaitAfter ();')
    binary = output / 'lq1/progs.dat'
    autoexec = 'sv_protocol 15\nmax_edicts 600\nscratch2 3003\n'
    with private_game(ROOT, args.prefix, 'traincheck', autoexec=autoexec) as game:
        env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(binary), ARGUS_GAME=game.name,
                   ARGUS_RUNS=str(output / 'runs'), ARGUS_PYTHON=sys.executable)
        with (output / 'lab.stderr').open('w', encoding='utf-8') as err:
            lab = Lab(err, env, exe=lab_executable(args.lab), timeout=210)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False)
                write_text(output / 'compile.json', json.dumps(compiled, indent=2))
                require(compiled['ok'] and not compiled['installed_to'], compiled)
                shutil.copy2(binary, game / 'progs.dat')
                run_match(lab, 'dm2', 170, args.prefix, skill=1, port=args.port, timeout=195,
                          environment=env, stderr_path=output / 'match.stderr')
                tape, raw = read_tape(output, args.prefix, 'dm2')
                require(f'ARGUS build {compiled["build"]}' in raw.splitlines(), 'wrong build')
                identity = dict(build=compiled['build'], source_sha256=source_identity(src),
                                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                                tape_sha256=hashlib.sha256(tape.read_bytes()).hexdigest())
                write_text(output / 'identity.json', json.dumps(identity, indent=2))
                receipt = dict(identity, **inspect_fixture(raw, args.control))
                write_text(output / 'receipt.json', json.dumps(receipt, indent=2))
                print(json.dumps(receipt))
            finally:
                finish_lab(lab)


if __name__ == '__main__':
    main()
