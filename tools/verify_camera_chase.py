"""Run a private production camera check with all eight real brush rays blocked."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

from argus_fixture_harness import new_output, stage_fixture, private_game, read_tape, check_tape, frame_ms, run_match
from argus_source import source_identity
from argus_validation import require
from run_behaviour_equivalence import lab_executable, finish_lab
from run_map_intelligence import ROOT, Lab, digest, write


def instrument_camera(text):
    needle = '                    traceline (bot.origin + \'0 0 22\', cand, FALSE, bot);'
    require(text.count(needle) == 1 and 'CameraChaseCandidate' not in text, 'camera sweep changed')
    return ('void(float fraction) CameraChaseCandidate;\n' + text.replace(needle,
        needle + '\n                    CameraChaseCandidate (trace_fraction);'))


def stage(root, output, source=None):
    fixture = (root/'tools/fixtures/camera_chase.qc').read_text(encoding='utf-8')
    callback = fixture.split('CameraChaseCandidate =',1)[1].split('\n};',1)[0]
    require(not re.search(r'\b(?:trace_\w+|v_forward|v_right|v_up|\w+\.\w+)\s*=(?!=)', callback),
            'camera observer changes production state')
    require(not re.search(r'\b(?:makevectors|traceline|Argus\w*)\s*\(', callback),
            'camera observer steers or replaces collision')
    return stage_fixture(root, output, source, fixtures={'camera_chase_fixture.qc': fixture},
        frame_wrap='Argus_FrameAll ();\n    CameraChaseFixture ();',
        edits={'argus_cam.qc': instrument_camera})


def inspect_fixture(text, ticrate):
    check_tape(text, 'e1m6')
    require(text.count('BHVRPL begin camera_chase') == 1, 'missing camera quarantine')
    ms = frame_ms(text, 'CAMFIX', ticrate)
    require(len(re.findall(r'^CAMFIX begin dt_ms\s+[\d.]+ layout 1\r?$',text,re.M)) == 1,
            'wrong camera proof layout')
    rows = re.findall(r"^CAMFIX result candidates (\d+) blocked (\d+) basis_error\s+([\d.]+) position_error\s+([\d.]+) distance\s+([\d.]+) position '([^']+)' expected '([^']+)'\r?$", text, re.M)
    require(len(rows) == 1, 'missing or repeated camera result')
    r = rows[0]
    require(r[:2] == ('8','8'), 'camera did not exhaust eight blocked candidates')
    require(float(r[2]) < .01, 'failed sweep leaked probe basis')
    require(float(r[3]) < .1, 'chase position overshot its bounded blend')
    require(16 <= float(r[4]) <= 40, 'chase was not pinched')
    return dict(fixture_layout='camera-chase-v1', frame_ms=ms,
        candidates=int(r[0]), blocked=int(r[1]), basis_error=float(r[2]),
        position_error=float(r[3]), distance=float(r[4]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prefix', required=True)
    p.add_argument('--source', type=Path, default=ROOT/'src')
    p.add_argument('--ticrate', type=float, choices=(.0139,.1), default=.0139)
    p.add_argument('--port', type=int, default=26003)
    args = p.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix) and 1024 <= args.port <= 65535)
    output = new_output(args.output, root=ROOT, create=False); stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'cameracheck') as folder:
        env = dict(ARGUS_SRC=str(output/'src'), ARGUS_PROGS=str(output/'lq1/progs.dat'),
            ARGUS_RUNS=str(output/'runs'), ARGUS_GAME=folder.name,
            ARGUS_PYTHON=sys.executable, ARGUS_TICRATE=str(args.ticrate))
        with (output/'lab.stderr').open('w', encoding='utf-8') as err:
            lab = Lab(err, env, exe=lab_executable(), timeout=45)
            try:
                project = lab.call('see', what='project')
                require(project['lab_identity']['authoritative'], 'stale lab')
                compiled = lab.call('compile_qc', install=False); write(output/'compile.json', compiled)
                require(compiled['ok'], compiled)
                shutil.copy2(output/'lq1/progs.dat', folder/'progs.dat')
                run_match(lab, 'e1m6', 10, args.prefix, port=args.port, timeout=25,
                    environment=env, stderr_path=output/'match.stderr')
                raw, text = read_tape(output, args.prefix, 'e1m6')
                identity = dict(source_sha256=source_identity(output/'src'),
                    fixture_sha256=digest(output/'src/camera_chase_fixture.qc'),
                    binary_sha256=digest(folder/'progs.dat'), raw_sha256=digest(raw),
                    raw=raw.relative_to(ROOT).as_posix(), ticrate=args.ticrate)
                write(output/'identity.json', identity)
                row = dict(identity, **inspect_fixture(text, args.ticrate))
                write(output/'receipt.json', row); print(json.dumps(row), flush=True)
            finally:
                finish_lab(lab)


if __name__ == '__main__': main()
