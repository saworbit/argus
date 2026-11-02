"""Fixed real-engine mover tasks, with route retention and actual landing checks."""

from argus_validation import require
from argus_source import source_identity
from argus_fixture_harness import (new_output, stage_fixture, private_game,
    read_tape, check_tape, frame_ms as measured_frame_ms, run_match)

from run_behaviour_equivalence import lab_executable
import argparse
import math
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
    for name in ('MoverTransferWillConsume', 'MoverTransferConsumed', 'MoverTransferHandoffOK'):
        body = text.split(name + ' =', 1)[1].split('\n};', 1)[0]
        require(not re.search(r'\b\w+\.\w+\s*=(?!=)', body), 'route observer mutates actor/world')
        require(not re.search(r'\b(setorigin|setsize|walkmove|droptofloor|remove|spawn|Argus_\w+)\s*\(', body), 'route observer steers or changes world')
    require((text.count('setorigin (self, mv_start)') == 1))
    require((text.count('BHVRPL begin mover_transfer') == 1))


def instrument_arrival(text):
    needle = '                oldnode = self.ar_node;\n                self.ar_node = Argus_GetNext (self.ar_node, self);\n                Argus_PlanObserve (FALSE, oldnode);'
    require(text.count(needle) == 1, 'production arrival branch changed')
    replacement = ('                oldnode = self.ar_node;\n'
                   '                MoverTransferWillConsume (oldnode);\n'
                   '                self.ar_node = Argus_GetNext (self.ar_node, self);\n'
                   '                Argus_PlanObserve (FALSE, oldnode);\n'
                   '                MoverTransferConsumed (oldnode, self.ar_node);')
    corner = ('                            Argus_PlanObserve (FALSE, self.ar_node);\n'
              '                            self.ar_node = nx;')
    require(text.count(corner) == 1, 'production corner-consumption branch changed')
    corner_observed = ('                            oldnode = self.ar_node;\n'
                       '                            MoverTransferWillConsume (oldnode);\n' + corner + '\n'
                       '                            MoverTransferConsumed (oldnode, self.ar_node);')
    return ('void(entity consumed) MoverTransferWillConsume;\n'
            'void(entity consumed, entity successor) MoverTransferConsumed;\n' +
            text.replace(needle, replacement).replace(corner, corner_observed))


def stage(root, output, source=None):
    fixture = (root / 'tools/fixtures/mover_transfer.qc').read_text(encoding='utf-8')
    audit_fixture(fixture)
    stage_fixture(root, output, source, fixtures={'mover_transfer_fixture.qc': fixture},
                  frame_wrap='MoverTransferBefore ();\n    if (!mv_done) Argus_FrameAll ();\n    MoverTransferAfter ();',
                  edits={'argus.qc': instrument_arrival})


def inspect_fixture(text, map_name, ticrate, *, require_current=False):
    """Keep legacy fields readable; v2 proves transition, v3 fixes flag truth."""
    check_tape(text, map_name)
    require(text.count('BHVRPL begin mover_transfer') == 1)
    matches = re.findall(r"^MVFIX result completed\s+([01]) seconds\s+([\d.]+) boarded\s+([01]) route_retained\s+([01]) dry\s+([01]) alive\s+([01]) launches\s+(\d+) bad_launch\s+([01]) landed\s+([01]) handoff\s+([01])(?: exit_consumed ([01]) frames (\d+) node '([^']+)' generation (\d+))? pos '([^']+)'\r?$", text, re.M)
    require(len(matches) == 1)
    ms = measured_frame_ms(text, 'MVFIX', ticrate)
    values = matches[0]
    if values[0] == '1':
        require(all(values[i] == '1' for i in (2, 3, 4, 5, 8, 9)), 'inconsistent completion')
    row = dict(completed=values[0] == '1', seconds=float(values[1]),
        boarded=values[2] == '1', route_retained=values[3] == '1', dry=values[4] == '1',
        alive=values[5] == '1', launches=int(values[6]), bad_launch=values[7] == '1',
        landed=values[8] == '1', handoff=values[9] == '1', frame_ms=ms,
        fixture_layout='mover-transfer-v1', proof='node_difference', forward_proven=False,
        observer_predicates_verified=False)
    starts = re.findall(r"^MVFIX begin dt_ms\s+[\d.]+ layout ([23]) exit '([^']+)'\r?$", text, re.M)
    if not starts:
        require(not require_current, 'legacy mover receipt cannot prove forward handoff')
        require(not values[10] and 'MVFIX expect ' not in text and 'MVFIX consumed ' not in text, 'missing proof layout')
        return row
    require(len(starts) == 1 and bool(values[10]), 'incomplete transition proof layout')
    vector = lambda s: tuple(map(float, s.split()))
    def point(s):
        result = vector(s)
        require(len(result) == 3 and all(math.isfinite(v) for v in result), 'invalid proof position')
        return result
    exit_pos = point(starts[0][1])
    expected_exit = (529,1393,344) if map_name == 'e1m6' else (517,801,216)
    require(exit_pos == expected_exit, 'wrong exit geometry')
    controls = re.findall(r'^MVFIX oracle (\w+) accepted ([01])\r?$', text, re.M)
    require(controls == [('different_node','0'),('expected_without_consumption','0')], 'oracle negative control passed or missing')
    expected = re.findall(r"^MVFIX expect step (\d+) generation (\d+) from '([^']+)' to '([^']+)'\r?$", text, re.M)
    consumed = re.findall(r"^MVFIX consumed step (\d+) generation (\d+) from '([^']+)' to '([^']+)' accepted ([01])\r?$", text, re.M)
    require(len({r[0] for r in expected}) == len(expected) and len({r[0] for r in consumed}) == len(consumed), 'duplicate transition proof')
    plans = {r[0]: r for r in expected}
    witnessed = []
    for event in consumed:
        require(event[0] in plans, 'consumption without prior route expectation')
        plan = plans[event[0]]
        require(text.index('MVFIX expect step ' + plan[0] + ' ') < text.index('MVFIX consumed step ' + event[0] + ' '), 'expectation recorded after consumption')
        if event[4] == '1':
            require(plan == event[:4], 'consumed node is not the expected forward successor')
            require(point(event[2]) == exit_pos and math.dist(point(event[3]), exit_pos) > 1, 'wrong consumed exit/successor')
            witnessed.append(event)
    landings = re.findall(r"^MVFIX landed pos '([^']+)' world ([01]) floor ([01]) dry ([01]) retained ([01])\r?$", text, re.M)
    require(len(landings) <= 1, 'duplicate landing witness')
    if row['landed']:
        require(len(landings) == 1 and all(v == '1' for v in landings[0][1:]), 'missing physical world-floor landing')
        landed_pos = point(landings[0][0])
        require(math.dist(landed_pos[:2], exit_pos[:2]) < 96 and abs(landed_pos[2]-exit_pos[2]) <= 18, 'landing outside exit floor')
    frames = int(values[11]); seconds = row['seconds']
    require(frames > 1 and 0 < seconds <= 18.2, 'invalid measured duration')
    fps = (frames - 1) / seconds
    require((8 <= fps <= 12) if ticrate == .1 else (60 <= fps <= 90), 'frame count disagrees with cadence')
    forward = bool(witnessed and values[9] == values[10] == '1')
    if forward:
        last = witnessed[-1]
        require(point(values[12]) == point(last[3]) and int(values[13]) == int(last[1]), 'final node/generation differs from consumed successor')
    if row['completed']:
        require(forward and row['landed'] and not row['bad_launch'], 'completion lacks forward-consumption proof')
    row.update(fixture_layout='mover-transfer-v'+starts[0][0], proof='observed_exit_consumption',
        observer_predicates_verified=starts[0][0]=='3',
        forward_proven=forward, exit_consumed=values[10] == '1', frames=frames, measured_fps=fps,
        expected_successor=point(witnessed[-1][3]) if witnessed else None, exit_node=exit_pos,
        oracle_controls=dict(controls))
    return row


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
                    measurement = inspect_fixture(text, map_name, args.ticrate, require_current=True)
                    brief = lab.call('brief_run', log=str(raw), map=map_name, detail='full')
                    write(output / (map_name + '.brief.json'), brief)
                    row = dict(map=map_name, **measurement,
                        unstick_warps=brief['events'].get('unstick', 0),
                        source_sha256=source_identity(output / 'src'), graph_sha256=digest(output / 'src' / ('argus_nav_' + map_name + '.qc.json')),
                        fixture_sha256=digest(output / 'src/mover_transfer_fixture.qc'), binary_sha256=digest(folder / 'progs.dat'),
                        raw_sha256=digest(raw), raw=str(raw.relative_to(ROOT)), control=args.control)
                    rows.append(row); write(output / 'receipt.json', rows); print(json.dumps(row), flush=True)
                if not args.control:
                    require((all(r['completed'] and r['forward_proven'] and r['route_retained'] and r['dry'] and r['alive']
                        and not r['bad_launch'] and not r['unstick_warps'] for r in rows)), rows)
            finally:
                native.finish_lab(lab)


if __name__ == '__main__':
    main()
