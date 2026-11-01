"""Bounded multi-map evaluation through the native lab, with frozen sources.

Uses a separate game directory and never installs over the playable build.
Receipts retain native briefs, input identities and every named tape.
"""
from argus_validation import require
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import run_behaviour_equivalence as native

ROOT = native.ROOT


def lab_executable():
    suffix = '.exe' if os.name == 'nt' else ''
    return ROOT / ('tools/argus_mcp/target-stage/release/argus-mcp' + suffix)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


SUPPORTED_PRIMARIES = ('stall_parity', 'engagements', 'lava_deaths', 'freezes')
COMPARISON_FIELDS = ('maps', 'seconds', 'skill', 'requested_ticrate', 'primary', 'cli_sha256')


def comparison_primary(control, candidate):
    """Validate frozen study compatibility and return its registered primary."""
    for key in COMPARISON_FIELDS:
        require((key in control and key in candidate), 'missing comparison protocol field: ' + key)
        require((control[key] == candidate[key]), 'comparison protocol mismatch: ' + key)
    require((candidate['primary'] in SUPPORTED_PRIMARIES), 'unsupported registered primary')
    return candidate['primary']


def load_comparison_baseline(folder, candidate):
    """Refuse incompatible or empty baselines before creating a study output."""
    control = json.loads((folder / 'protocol.json').read_text())
    rows = json.loads((folder / 'results.json').read_text())
    comparison_primary(control, candidate)
    require((rows), 'empty baseline results')
    return control, rows


def compare_registered_tape(executable, control, candidate, baseline_rows, row):
    """Keep the native card verbatim with its primary and frozen input identities."""
    primary = comparison_primary(control, candidate)
    require((row['map'] in candidate['maps']), 'candidate map outside registered protocol')
    controls = [item for item in baseline_rows if item['map'] == row['map']]
    require((controls), 'no same-map control')
    require((row['repeat'] >= 1), 'invalid candidate repeat')
    require((all(item['brief']['totals']['tick_class'] == row['brief']['totals']['tick_class']
               for item in controls)), 'cross-cadence comparison')
    selected = controls[(row['repeat'] - 1) % len(controls)]
    inputs = {}
    for arm, item, protocol in [('control', selected, control), ('candidate', row, candidate)]:
        require((re.fullmatch(r'[a-z0-9_]+', item['name'])), 'invalid comparison run name')
        require((item['binary_sha256'] == protocol['binary_sha256']), arm + ' binary changed')
        require((item['source_sha256'] == protocol['source_sha256']), arm + ' source changed')
        require((digest(ROOT / 'runs' / (item['name'] + '.log')) == item['raw_sha256']), arm + ' tape changed')
        inputs[arm] = {key: item[key] for key in ('name', 'raw_sha256', 'source_sha256', 'binary_sha256')}
    analysis_hash = digest(executable)
    require((analysis_hash == candidate['cli_sha256']), 'comparison executable changed')
    response = subprocess.run([str(executable), 'compare', row['name'], selected['name'],
        '--primary', primary], cwd=ROOT, env=dict(os.environ, ARGUS_ROOT=str(ROOT)),
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    require((response.returncode == 0), response.stderr)
    require((response.stdout.strip()), 'empty native comparison card')
    return dict(schema='registered-native-compare-v1', effective_primary=primary,
                analysis_lab_sha256=analysis_hash, inputs=inputs,
                comparison_protocol={key: candidate[key] for key in COMPARISON_FIELDS},
                native_gate_card=response.stdout)


class Lab(native.Lab):
    def request(self, method, params):
        self.serial += 1
        self.p.stdin.write(json.dumps(dict(jsonrpc='2.0', id=self.serial,
                                         method=method, params=params)) + '\n')
        self.p.stdin.flush()
        deadline = time.monotonic() + 900
        while True:
            response = self.records.get(timeout=max(.01, deadline - time.monotonic()))
            require((response is not None), 'native lab exited')
            if response.get('id') == self.serial:
                return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps', default='dm3,dm6,lqdm2,e1m1,e1m2,e1m5,e1m6,e1m7')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--skill', type=int, default=2)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--ticrate', type=float, default=.0139)
    parser.add_argument('--port', type=int)
    parser.add_argument('--lab', type=Path, default=lab_executable())
    parser.add_argument('--primary', choices=SUPPORTED_PRIMARIES,
                        default='stall_parity')
    args = parser.parse_args()
    maps = args.maps.split(',')
    require((1 <= len(maps) <= 12 and len(set(maps)) == len(maps)))
    require((all(re.fullmatch(r'[a-z0-9_]+', m) for m in maps)))
    require((re.fullmatch(r'[a-z0-9_]+', args.prefix)))
    require((10 <= args.seconds <= 185 and 1 <= args.repeats <= 5 and 0 <= args.skill <= 3))
    require((args.ticrate in (.0139, .1)), 'use the played or 10 Hz profile')
    require((args.port is None or 1024 <= args.port <= 65535))
    output = args.output.resolve()
    require((output.is_relative_to((ROOT / 'backups').resolve())), 'output must be beneath backups/')
    require((not output.exists()), 'retain the previous arm; choose a new output')
    native.EXE = args.lab.resolve()
    require((native.EXE.exists()), 'build the current native lab first')
    comparison_protocol = dict(maps=maps, seconds=args.seconds, skill=args.skill,
                               requested_ticrate=args.ticrate, primary=args.primary,
                               cli_sha256=digest(native.EXE))
    baseline_protocol, baseline_rows = (load_comparison_baseline(args.baseline, comparison_protocol)
                                        if args.baseline else (None, []))
    shutil.copytree(args.source, output / 'src')
    (output / 'lq1').mkdir()
    game = 'maplab_' + args.prefix
    game_dir = ROOT / 'engine' / game
    require((not game_dir.exists()), 'private game already exists')
    game_dir.mkdir()
    for name in ('progs', 'maps', 'sound', 'gfx'):
        source = ROOT / 'engine/argus' / name
        if source.exists():
            shutil.copytree(source, game_dir / name)
    shutil.copy2(ROOT / 'game/argus/autoexec.cfg', game_dir / 'autoexec.cfg')
    inputs = {p.relative_to(output).as_posix(): digest(p)
              for p in sorted((output / 'src').rglob('*')) if p.is_file()}
    environment = dict(ARGUS_SRC=str(output / 'src'), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
                       ARGUS_GAME=game, ARGUS_PYTHON=sys.executable,
                       ARGUS_TICRATE=str(args.ticrate))
    protocol = dict(**comparison_protocol, repeats=args.repeats, port=args.port,
                    source_files=inputs, game=game,
                    tree_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    tree_diff=subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT, text=True),
                    shipped_sha256=digest(ROOT / 'game/argus/progs.dat'))
    protocol['source_sha256'] = hashlib.sha256(
        json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    write(output / 'protocol.json', protocol)
    rows = []
    def run_match(lab, map_name, seconds, name):
        if args.port is None:
            return lab.call('match_run', map=map_name, duration_sec=seconds,
                            skill=args.skill, run_name=name)
        result = subprocess.run([str(native.EXE), 'match', map_name, str(seconds), name,
            '--skill', str(args.skill), '--port', str(args.port)], cwd=ROOT,
            env=dict(os.environ, ARGUS_ROOT=str(ROOT), **environment),
            capture_output=True, text=True, encoding='utf-8', timeout=seconds + 45)
        (output / (name + '.stderr')).write_text(result.stderr)
        require((result.returncode == 0), result.stderr)
        return json.loads(result.stdout)

    with (output / 'lab.stderr').open('w') as errors:
        lab = Lab(errors, environment)
        try:
            lab.call('see', what='project')
            compiled = lab.call('compile_qc', install=False)
            write(output / 'compile.json', compiled)
            require((compiled['ok']), compiled)
            binary = output / 'lq1/progs.dat'
            protocol['binary_sha256'] = digest(binary)
            write(output / 'protocol.json', protocol)
            shutil.copy2(binary, game_dir / 'progs.dat')
            # A native port-isolated match is available while a control arm
            # owns the default port. Run the post-edit experiment separately
            # once that port is free; never make its tape a measured repeat.
            if args.port is None:
                smoke = lab.call('experiment', map=maps[0], duration_sec=10, skill=args.skill,
                                 compile=False, repeats=1, primary=args.primary,
                                 run_name=args.prefix + '_smoke')
            else:
                smoke = run_match(lab, maps[0], 10, args.prefix + '_smoke')
            write(output / 'smoke.json', smoke)
            for repeat in range(1, args.repeats + 1):
                for map_name in maps if repeat % 2 else maps[::-1]:
                    name = f'{args.prefix}_{map_name}_{repeat}'
                    require((not (ROOT / f'runs/{name}.log').exists()), 'retain existing tape')
                    write(output / 'state.json', dict(status='running', completed=len(rows),
                          total=len(maps) * args.repeats, current=name))
                    result = run_match(lab, map_name, args.seconds, name)
                    write(output / (name + '.match.json'), result)
                    brief = lab.call('brief_run', log=name, map=map_name, detail='full')
                    write(output / (name + '.brief.json'), brief)
                    raw = ROOT / f'runs/{name}.log'
                    text = raw.read_text(errors='replace')
                    require((not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error'))))
                    require((brief['map'] == map_name))
                    require((not any('WRONG MAP' in flag for flag in brief['flags'])), brief['flags'])
                    require((args.seconds - 2 <= brief['totals']['duration_sec'] <= args.seconds + 3))
                    if args.ticrate == .0139:
                        require((brief['totals']['tick_class'] == 'listen'), 'wrong measured cadence')
                    row = dict(name=name, map=map_name, repeat=repeat, raw_sha256=digest(raw),
                               source_sha256=protocol['source_sha256'],
                               binary_sha256=digest(game_dir / 'progs.dat'), brief=brief)
                    require((row['binary_sha256'] == protocol['binary_sha256']))
                    if args.baseline:
                        comparison = compare_registered_tape(native.EXE, baseline_protocol,
                            protocol, baseline_rows, row)
                        write(output / (name + '.compare.json'), comparison)
                    rows.append(row)
                    write(output / 'results.json', rows)
                    print(json.dumps(dict(name=name, completed=len(rows),
                          totals=brief['totals'], flags=brief['flags'])), flush=True)
            require(({p.relative_to(output).as_posix(): digest(p)
                    for p in sorted((output / 'src').rglob('*')) if p.is_file()
                    and p.suffix in ('.qc', '.src', '.json')} == {
                    p: h for p, h in inputs.items() if Path(p).suffix in ('.qc', '.src', '.json')}), 'source changed')
            require((digest(ROOT / 'game/argus/progs.dat') == protocol['shipped_sha256']))
            write(output / 'state.json', dict(status='complete', completed=len(rows),
                  total=len(maps) * args.repeats))
        finally:
            native.finish_lab(lab)


if __name__ == '__main__':
    main()
