"""Fixed real-engine mover tasks, with route retention and actual landing checks."""

from run_behaviour_equivalence import lab_executable, lab_cli
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write


def audit_fixture(text):
    """Only the real controller may move the bot after initial placement."""
    after = text.split('void() MoverTransferAfter =', 1)[1]
    observe, terminal = after.split('    if (mv_completed || time > mv_when + 18 || mv_bot.health <= 0)', 1)
    assert not re.search(r'\b(setorigin|setsize|walkmove|droptofloor|Argus_\w+)\s*\(', observe)
    assert not re.search(r'\b\w+\.\w+\s*=(?!=)', observe), 'observer mutates actor/world'
    assert set(re.findall(r'\b(\w+\.\w+)\s*=(?!=)', terminal)) == {
        'mv_bot.velocity', 'mv_bot.movetype', 'mv_bot.think', 'mv_bot.nextthink'}
    assert not re.search(r'\b(setorigin|setsize|walkmove|Argus_\w+)\s*\(', terminal)
    assert text.count('setorigin (self, mv_start)') == 1
    assert text.count('BHVRPL begin mover_transfer') == 1


def stage(root, output, source=None):
    shutil.copytree(source or root / 'src', output / 'src')
    (output / 'lq1').mkdir(); (output / 'runs').mkdir()
    src = output / 'src'
    fixture = (root / 'tools/fixtures/mover_transfer.qc').read_text(encoding='utf-8')
    audit_fixture(fixture)
    (src / 'mover_transfer_fixture.qc').write_text(fixture, encoding='utf-8', newline='\n')
    path = src / 'progs.src'; text = path.read_text()
    assert text.count('\nworld.qc\n') == 1
    path.write_text(text.replace('\nworld.qc\n', '\nmover_transfer_fixture.qc\nworld.qc\n'))
    path = src / 'world.qc'; text = path.read_text()
    assert text.count('Argus_FrameAll ();') == 1
    path.write_text(text.replace('Argus_FrameAll ();',
        'MoverTransferBefore ();\n    if (!mv_done) Argus_FrameAll ();\n    MoverTransferAfter ();'))


def inspect_fixture(text, map_name, ticrate):
    """Reject incomplete, duplicated, wrong-map or wrong-rate measurements."""
    assert not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error'))
    assert re.findall(r'^ARGUS init on (\S+)$', text, re.M) == [map_name]
    assert text.count('BHVRPL begin mover_transfer') == 1
    starts = re.findall(r'^MVFIX begin dt_ms\s+([\d.]+)$', text, re.M)
    matches = re.findall(r'^MVFIX result completed\s+([01]) seconds\s+([\d.]+) boarded\s+([01]) route_retained\s+([01]) dry\s+([01]) alive\s+([01]) launches\s+(\d+) bad_launch\s+([01]) landed\s+([01]) handoff\s+([01]) pos .+$', text, re.M)
    assert len(starts) == len(matches) == 1
    ms = float(starts[0])
    assert (90 <= ms <= 110) if ticrate == .1 else (10 <= ms <= 30)
    values = matches[0]
    if values[0] == '1':
        assert all(values[i] == '1' for i in (2, 3, 4, 5, 8, 9)), 'inconsistent completion'
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
    assert re.fullmatch(r'[a-z0-9_]+', args.prefix)
    maps = args.maps.split(','); assert maps and set(maps) <= {'e1m6', 'dm3'}
    assert len(set(maps)) == len(maps) and 1024 <= args.port <= 65535
    output = args.output.resolve(); assert not output.exists()
    assert output.is_relative_to((ROOT / 'backups').resolve())
    stage(ROOT, output, args.source)
    game = 'movercheck_' + args.prefix; folder = ROOT / 'engine' / game
    assert not folder.exists(); folder.mkdir()
    for name in ('progs', 'maps', 'sound', 'gfx'):
        original = ROOT / 'engine/argus' / name
        if original.exists(): shutil.copytree(original, folder / name)
    shutil.copy2(ROOT / 'game/argus/autoexec.cfg', folder / 'autoexec.cfg')
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
            assert compiled['ok'], compiled
            shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
            for map_name in maps:
                name = args.prefix + '_' + map_name
                result = lab_cli(executable, 'match', map_name, '24', name, '--skill', '2', '--port', str(args.port), cwd=ROOT, environment=dict(os.environ, ARGUS_ROOT=str(ROOT), **env), timeout=50)
                (output / (map_name + '.stderr')).write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                raw = output / 'runs' / (name + '.log'); text = raw.read_text(errors='replace')
                measurement = inspect_fixture(text, map_name, args.ticrate)
                brief = lab.call('brief_run', log=str(raw), map=map_name, detail='full')
                write(output / (map_name + '.brief.json'), brief)
                row = dict(map=map_name, **measurement,
                    unstick_warps=brief['events'].get('unstick', 0),
                    source_sha256=digest(output / 'src/argus.qc'), graph_sha256=digest(output / 'src' / ('argus_nav_' + map_name + '.qc.json')),
                    fixture_sha256=digest(output / 'src/mover_transfer_fixture.qc'), binary_sha256=digest(folder / 'progs.dat'),
                    raw_sha256=digest(raw), raw=str(raw.relative_to(ROOT)), control=args.control)
                rows.append(row); write(output / 'receipt.json', rows); print(json.dumps(row), flush=True)
            if not args.control:
                assert all(r['completed'] and r['route_retained'] and r['dry'] and r['alive']
                    and not r['bad_launch'] and not r['unstick_warps'] for r in rows), rows
        finally:
            native.finish_lab(lab)


if __name__ == '__main__':
    main()
