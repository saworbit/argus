"""Evaluate a private two-leg pursuit search with stock movement and matched matches."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from math import dist
from pathlib import Path
import re
import shutil
from statistics import median
import sys

from argus_fixture_harness import (frame_ms, new_output, private_game, read_tape,
                                  run_match, stage_fixture, write_text)
from argus_guard_replica import read_tape as motion_tracks
from argus_source import source_identity
from argus_validation import require
from argus_wishflips import scan
from run_behaviour_equivalence import ROOT, Lab, finish_lab, lab_executable

FRAME = re.compile(r"^PL frame\s+(\d+) active ([01]) pos '([^']+)' feet (-?\d+) "
                   r"speed\s+([\d.]+) age\s+([\d.]+) goal ([01]) before\s+([-\d.]+) after\s+([-\d.]+)$", re.M)
USE = re.compile(r"^P2USE (.+) ms\s+(\d+) pos '([^']+)' hop '([^']+)' cue '([^']+)'$", re.M)


def stage(output, played):
    folder = ROOT / 'tools/fixtures'
    probe = (folder / 'pursuit_two_leg_probe.qc').read_text(encoding='utf-8')

    def insert_probe(source):
        signature = 'entity(vector sighting) Argus_PursuitHop =\n'
        require(source.count(signature) == 1, 'pursuit entry changed')
        before, body = source.split(signature)
        function, after = body.split('\n};', 1)
        require(function.count('    return best;') == 1, 'pursuit return changed')
        fallback = r'''    if (best == world && cvar ("scratch3") == 1)
    {
        best = PursuitProbeTwoLeg (seat, sighting);
        if (best != world)
        {
            dprint ("P2USE "); dprint (self.netname); dprint (" ms ");
            dprint (ftos (floor (time * 1000))); dprint (" pos ");
            dprint (vtos (self.origin)); dprint (" hop "); dprint (vtos (best.origin));
            dprint (" cue "); dprint (vtos (sighting)); dprint ("\n");
        }
    }
    return best;'''
        return before + probe + '\n' + signature + function.replace('    return best;', fallback) + '\n};' + after

    fixtures, wrap = {}, None
    if not played:
        fixtures['pursuit_live_fixture.qc'] = (folder / 'pursuit_two_leg.qc').read_text(encoding='utf-8')
        wrap = 'PursuitLiveFrame ();'
    return stage_fixture(ROOT, output, fixtures=fixtures, frame_wrap=wrap,
                         edits={'argus.qc': insert_probe})


def inspect_fixture(raw, map_name, candidate):
    lines = raw.splitlines()
    require(lines.count('BHVRPL begin live_pursuit') == 1, 'wrong fixture')
    require(all(lines.count('PL ' + gate + ' 0') == 1 for gate in ('expired', 'committed', 'novice')),
            'an ineligible cue took steering')
    rows = FRAME.findall(raw)
    require(len(rows) == sum(line.startswith('PL frame ') for line in lines), 'malformed motion receipt')
    require(rows and rows[0][0] == '0' and rows[-1][1] == '0', 'missing steering release')
    require(all(int(a[0]) < int(b[0]) for a, b in zip(rows, rows[1:])), 'non-increasing frame times')
    require(all(row[1] == '1' for row in rows[:-1]), 'reacquired a released cue')
    require(all(row[3] == '-1' and row[6] == '1' for row in rows), 'lost dry travel or route owner')
    require(rows[-1][7] == rows[-1][8], 'released cue still changed yaw')
    reached = bool(candidate) and map_name == 'dm2'
    require(reached == (len(rows) > 1), 'unexpected steering decision')
    point = tuple(map(float, rows[-1][2].split()))
    cue = (1441, -375) if map_name == 'dm2' else (337, -599)
    distance = dist(point[:2], cue)
    if reached:
        require(distance <= 80.2 and float(rows[-1][5]) < 3, 'bounded pursuit did not reach the cue')
    return dict(frame_ms=frame_ms(raw, 'PL', .0139), frames=len(rows), arrival_distance=distance,
                steering_ms=int(rows[-1][0]), reached=reached)


def inspect_match(tape, raw, candidate):
    require('BHVRPL begin' not in raw, 'fixture leaked into an ordinary match')
    frames = motion_tracks(tape)
    intervals = [b[0] - a[0] for points in frames.values() for a, b in zip(points, points[1:])
                 if 0 < b[0] - a[0] < 100]
    require(intervals and 11 <= median(intervals) <= 20, 'wrong played cadence')
    flips, _ = scan(tape)
    uses = []
    for bot, when, start, hop, cue in USE.findall(raw):
        now = int(when) / 1000
        nearby = [row for row in flips['bots'].get(bot, []) if now - .05 <= row['t'] <= now + 1.25]
        uses.append(dict(bot=bot, seconds=now, start=start, hop=hop, cue=cue, rapid_flips=nearby))
    require(len(uses) == sum(line.startswith('P2USE ') for line in raw.splitlines()), 'malformed search receipt')
    require(candidate or not uses, 'control used the private search')
    return dict(frame_ms=median(intervals), uses=uses, flip_runs=flips['runs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--lab', type=Path)
    parser.add_argument('--played', action='store_true', help='record two 90-second pairs per map')
    args = parser.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,35}', args.prefix), 'invalid run prefix')
    output = new_output(args.output, root=ROOT, create=False)
    src = stage(output, args.played)
    exe = lab_executable(args.lab)
    binary = output / 'lq1/progs.dat'
    env = dict(ARGUS_SRC=str(src), ARGUS_PROGS=str(binary), ARGUS_RUNS=str(output / 'runs'),
               ARGUS_PYTHON=sys.executable, ARGUS_TICRATE='.0139')
    with (output / 'compile.stderr').open('w', encoding='utf-8') as errors:
        lab = Lab(errors, env, exe=exe, timeout=45)
        try:
            lab.call('see', what='project')
            compiled = lab.call('compile_qc', install=False)
            write_text(output / 'compile.json', json.dumps(compiled, indent=2))
            require(compiled['ok'] and not compiled['installed_to'], compiled)
        finally:
            finish_lab(lab)

    def run(spec):
        index, (map_name, arm, repeat) = spec
        name = f'{args.prefix}_{map_name}_{arm}_{repeat}'
        autoexec = f'sv_protocol 15\nmax_edicts 600\nscratch3 {arm}\n'
        if args.played:
            autoexec += 'scratch1 697\n'
        with private_game(ROOT, name, 'pursuitcheck', autoexec=autoexec) as game:
            shutil.copy2(binary, game / 'progs.dat')
            active = dict(env, ARGUS_GAME=game.name)
            with (output / f'{name}.stderr').open('w', encoding='utf-8') as errors:
                lab = Lab(errors, active, exe=exe, timeout=115)
                try:
                    lab.call('see', what='project')
                    run_match(lab, map_name, 90 if args.played else 10, name, port=26390 + index,
                              timeout=108 if args.played else 25, environment=active,
                              stderr_path=output / f'{name}.match.stderr')
                finally:
                    finish_lab(lab)
        tape, raw = read_tape(output, name, map_name)
        require(f'ARGUS build {compiled["build"]}' in raw.splitlines(), 'wrong build')
        result = inspect_match(tape, raw, arm) if args.played else inspect_fixture(raw, map_name, arm)
        return dict(run=name, map=map_name, arm=arm, tape_sha256=hashlib.sha256(tape.read_bytes()).hexdigest(),
                    **result)

    cases = [(m, arm, repeat) for m in ('dm2', 'dm4') for repeat in range(1, 3 if args.played else 2)
             for arm in (0, 1)]
    with ThreadPoolExecutor(max_workers=4 if args.played else 2) as pool:
        runs = list(pool.map(run, enumerate(cases)))
    receipt = dict(build=compiled['build'], source_sha256=source_identity(src),
                   binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), runs=runs)
    write_text(output / 'receipt.json', json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
