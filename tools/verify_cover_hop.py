"""Verify the production cover-hop predicate in a private native match."""
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


LABELS = ('missing_source','missing_hop','unlinked','reverse_only','ordinary_walk',
    'jump','sprint','rocket','lift','swim','train','door','step_down','deliberate_drop','ordinary_stairs')


def stage(root, output, source=None):
    fixture = (root/'tools/fixtures/cover_hop.qc').read_text(encoding='utf-8')
    return stage_fixture(root, output, source, fixtures={'cover_hop_fixture.qc': fixture},
        frame_wrap='CoverHopFixture ();\n    Argus_FrameAll ();')


def inspect_fixture(text, ticrate, map_name='dm4'):
    check_tape(text,map_name)
    require(text.count('BHVRPL begin cover_hop') == 1,'missing cover quarantine')
    ms=frame_ms(text,'CHFIX',ticrate)
    require(len(re.findall(r'^CHFIX begin dt_ms\s+[\d.]+ layout 1\r?$',text,re.M))==1,'wrong cover proof layout')
    rows=re.findall(r'^CHFIX check (\w+) ([01])\r?$',text,re.M)
    require(tuple(r[0] for r in rows)==LABELS,'missing or repeated cover controls')
    require(all(r[1]=='1' for r in rows),'cover predicate control failed: '+str(rows))
    require(re.findall(r'^CHFIX end checks (\d+) failures (\d+)\r?$',text,re.M)==[(str(len(LABELS)),'0')],'incomplete cover controls')
    return dict(fixture_layout='cover-hop-v1',frame_ms=ms,checks=len(rows))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prefix', required=True)
    p.add_argument('--source', type=Path, default=ROOT/'src')
    p.add_argument('--map', choices=('dm4','dm2'), default='dm4')
    p.add_argument('--ticrate', type=float, choices=(.0139,.1), default=.0139)
    p.add_argument('--port', type=int, default=26003)
    args = p.parse_args()
    require(re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix) and 1024 <= args.port <= 65535)
    output = new_output(args.output, root=ROOT, create=False); stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'covercheck') as folder:
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
                run_match(lab, args.map, 10, args.prefix, port=args.port, timeout=25,
                    environment=env, stderr_path=output/'match.stderr')
                raw, text = read_tape(output, args.prefix, args.map)
                identity = dict(source_sha256=source_identity(output/'src'),
                    fixture_sha256=digest(output/'src/cover_hop_fixture.qc'),
                    binary_sha256=digest(folder/'progs.dat'), raw_sha256=digest(raw),
                    raw=raw.relative_to(ROOT).as_posix(), ticrate=args.ticrate, map=args.map)
                write(output/'identity.json', identity)
                row = dict(identity, **inspect_fixture(text, args.ticrate, args.map))
                write(output/'receipt.json', row); print(json.dumps(row), flush=True)
            finally:
                finish_lab(lab)


if __name__ == '__main__': main()
