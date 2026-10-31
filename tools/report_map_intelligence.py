"""Summarise native multi-map receipts without reconstructing tape metrics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
from run_map_intelligence import lab_executable
from argus_registration import registration

ROOT = Path(__file__).resolve().parents[1]

METRICS = ('stalls', 'engages', 'goals', 'grabs', 'weapons', 'frags',
           'freezes', 'freeze_underfire', 'world_deaths', 'lava_deaths', 'routefails',
           'unstick_warps')


def metric(row, name):
    if name == 'unstick_warps':
        return row['brief']['events'].get('unstick', 0)
    return row['brief']['totals'].get(name, 0)


def coverage(rows):
    values = [r['brief'].get('nav_coverage', {}).get('pct') for r in rows
              if r.get('compiled_navigation') is not False]
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else None


def load(folder):
    protocol = json.loads((folder / 'protocol.json').read_text())
    rows = json.loads((folder / 'results.json').read_text())
    source_list = folder / 'src/progs.src'
    dispatcher = folder / 'src/argus_nav_dispatch.qc'
    for row in rows:
        assert row['binary_sha256'] == protocol['binary_sha256']
        raw = ROOT / 'runs' / (row['name'] + '.log')
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == row['raw_sha256']
        if source_list.is_file() and dispatcher.is_file():
            dispatched, included = registration(dispatcher.read_text(), source_list.read_text(), row['map'])
            row['compiled_navigation'] = dispatched and included
        else:
            row['compiled_navigation'] = None
    return protocol, rows


def compare(control_dir, candidate_dir):
    control, rows_a = load(control_dir)
    candidate, rows_b = load(candidate_dir)
    assert control['maps'] == candidate['maps']
    assert control['seconds'] == candidate['seconds'] and control['skill'] == candidate['skill']
    assert control.get('primary', 'stall_parity') == candidate.get('primary', 'stall_parity')
    rows = []
    for map_name in control['maps']:
        a = [r for r in rows_a if r['map'] == map_name]
        b = [r for r in rows_b if r['map'] == map_name]
        assert a and b
        assert len({r['brief']['totals']['tick_class'] for r in a + b}) == 1
        rows.append(dict(map=map_name, control_n=len(a), candidate_n=len(b),
            compiled_navigation=dict(control=a[0].get('compiled_navigation'),
                                     candidate=b[0].get('compiled_navigation')),
            control_coverage=coverage(a),
            candidate_coverage=coverage(b),
            flags=sorted({flag for r in a + b for flag in r['brief']['flags']}),
            metrics={m: dict(control=statistics.mean(metric(r, m) for r in a),
                             candidate=statistics.mean(metric(r, m) for r in b))
                     for m in METRICS}))
    return dict(control_protocol=control, candidate_protocol=candidate, maps=rows,
                tapes={r['name']: r['raw_sha256'] for r in rows_a + rows_b},
                complete=len(rows_a) == len(control['maps']) * control['repeats']
                and len(rows_b) == len(candidate['maps']) * candidate['repeats'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('control', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native-gates', type=Path, help='new directory for native band gate cards')
    parser.add_argument('--lab', type=Path, default=lab_executable())
    args = parser.parse_args()
    result = compare(args.control.resolve(), args.candidate.resolve())
    if args.native_gates:
        assert result['complete'], 'complete both arms before judging bands'
        assert not args.native_gates.exists()
        args.native_gates.mkdir(parents=True)
        executable = args.lab.resolve()
        result['analysis_lab_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
        arms = [json.loads((p / 'results.json').read_text()) for p in (args.control, args.candidate)]
        for row in result['maps']:
            names = [','.join(r['name'] for r in rows if r['map'] == row['map']) for rows in arms]
            response = subprocess.run([str(executable), 'compare', names[1], names[0],
                '--primary', result['candidate_protocol'].get('primary', 'stall_parity')], cwd=ROOT,
                env=dict(os.environ, ARGUS_ROOT=str(ROOT)), capture_output=True,
                text=True, encoding='utf-8', timeout=30)
            assert response.returncode == 0, response.stderr
            (args.native_gates / (row['map'] + '.txt')).write_text(response.stdout, encoding='utf-8')
            row['native_gate_card'] = response.stdout
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('map,n A/B,stalls A/B,engages A/B,pickups A/B,freezes A/B,under fire A/B,warps A/B,world deaths A/B')
    for row in result['maps']:
        cells = [row['map'], f"{row['control_n']}/{row['candidate_n']}"]
        for name in ('stalls', 'engages', 'goals', 'freezes', 'freeze_underfire', 'unstick_warps', 'world_deaths'):
            m = row['metrics'][name]
            cells.append(f"{m['control']:g}/{m['candidate']:g}")
        print(','.join(cells))
    print('Complete:', result['complete'])
    unmapped = [r['map'] for r in result['maps'] if False in r['compiled_navigation'].values()]
    if unmapped:
        print('No compiled navigation; spatial graph coverage is not a runtime navigation score:', ','.join(unmapped))


if __name__ == '__main__':
    main()
