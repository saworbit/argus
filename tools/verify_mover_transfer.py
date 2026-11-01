"""Fixed real-engine mover tasks, with route retention and actual landing checks."""

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


def audit_fixture(text):
    """Only the real controller may move the bot after initial placement."""
    after = text.split('void() MoverTransferAfter =', 1)[1]
    observe, terminal = after.split('    if (mv_completed || time > mv_when + 18 || mv_bot.health <= 0)', 1)
    require((not re.search(r'\b(setorigin|setsize|walkmove|droptofloor|Argus_\w+)\s*\(', observe)))
    require((not re.search(r'\b\w+\.\w+\s*=(?!=)', observe)), 'observer mutates actor/world')
    require((set(re.findall(r'\b(\w+\.\w+)\s*=(?!=)', terminal)) == {
        'mv_bot.velocity', 'mv_bot.movetype', 'mv_bot.think', 'mv_bot.nextthink'}))
    require((not re.search(r'\b(setorigin|setsize|walkmove|Argus_\w+)\s*\(', terminal)))
    require((text.count('setorigin (self, mv_start)') == 1))
    require((text.count('BHVRPL begin mover_transfer') == 1))


def stage(root, output, source=None):
    fixture = (root / 'tools/fixtures/mover_transfer.qc').read_text(encoding='utf-8')
    audit_fixture(fixture)
    stage_fixture(root, output, source, fixtures={'mover_transfer_fixture.qc': fixture},
                  frame_wrap='MoverTransferBefore ();\n    if (!mv_done) Argus_FrameAll ();\n    MoverTransferAfter ();')


def inspect_fixture(text, map_name, ticrate):
    """Reject incomplete, duplicated, wrong-map or wrong-rate measurements."""
    check_tape(text, map_name)
    require((text.count('BHVRPL begin mover_transfer') == 1))
    matches = re.findall(r'^MVFIX result completed\s+([01]) seconds\s+([\d.]+) boarded\s+([01]) route_retained\s+([01]) dry\s+([01]) alive\s+([01]) launches\s+(\d+) bad_launch\s+([01]) landed\s+([01]) handoff\s+([01]) pos .+$', text, re.M)
    require(len(matches) == 1)
    ms = measured_frame_ms(text, 'MVFIX', ticrate)
    values = matches[0]
    if values[0] == '1':
        require((all(values[i] == '1' for i in (2, 3, 4, 5, 8, 9))), 'inconsistent completion')
    return dict(completed=values[0] == '1', seconds=float(values[1]),
        boarded=values[2] == '1', route_retained=values[3] == '1', dry=values[4] == '1',
        alive=values[5] == '1', launches=int(values[6]), bad_launch=values[7] == '1',
        landed=values[8] == '1', handoff=values[9] == '1', frame_ms=ms)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--maps', default='e1m6,dm3')
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--port', type=int, default=26003)
    parser.add_argument('--control', action='store_true', help='retain baseline outcomes without requiring completion')
    args = parser.parse_args()
    require((re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix)))
    maps = args.maps.split(','); require((maps and set(maps) <= {'e1m6', 'dm3'}))
    require((len(set(maps)) == len(maps) and 1024 <= args.port <= 65535))
    output = new_output(args.output, root=ROOT, create=False)
    stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'movercheck') as folder:
        game = folder.name
        executable = lab_executable()
        env = dict(ARGUS_SRC=str(output / 'src'), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
            ARGUS_RUNS=str(output / 'runs'), ARGUS_GAME=game, ARGUS_PYTHON=sys.executable,
            ARGUS_TICRATE=str(args.ticrate))
        rows = []
        with (output / 'lab.stderr').open('w') as err:
            lab = Lab(err, env, exe=executable, timeout=900)
            try:
                lab.call('see', what='project')
                compiled = lab.call('compile_qc', install=False); write(output / 'compile.json', compiled)
                require((compiled['ok']), compiled)
                shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
                for map_name in maps:
                    name = args.prefix + '_' + map_name
                    result = run_match(lab, map_name, 24, name, port=args.port, timeout=50, environment=env, stderr_path=output / (map_name + '.stderr'))
                    raw, text = read_tape(output, name, map_name)
                    measurement = inspect_fixture(text, map_name, args.ticrate)
                    brief = lab.call('brief_run', log=str(raw), map=map_name, detail='full')
                    write(output / (map_name + '.brief.json'), brief)
                    row = dict(map=map_name, **measurement,
                        unstick_warps=brief['events'].get('unstick', 0),
                        source_sha256=source_identity(output / 'src'), graph_sha256=digest(output / 'src' / ('argus_nav_' + map_name + '.qc.json')),
                        fixture_sha256=digest(output / 'src/mover_transfer_fixture.qc'), binary_sha256=digest(folder / 'progs.dat'),
                        raw_sha256=digest(raw), raw=str(raw.relative_to(ROOT)), control=args.control)
                    rows.append(row); write(output / 'receipt.json', rows); print(json.dumps(row), flush=True)
                if not args.control:
                    require((all(r['completed'] and r['route_retained'] and r['dry'] and r['alive']
                        and not r['bad_launch'] and not r['unstick_warps'] for r in rows)), rows)
            finally:
                native.finish_lab(lab)


if __name__ == '__main__':
    main()
