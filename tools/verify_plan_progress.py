"""Bounded native plan fixtures in a new private directory; never installs a mod.

Run from the repository: python tools/verify_plan_progress.py --output backups/plan-check-1
Requires the matching source-built lab CLI and configured local Quake assets.
"""
import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from check_plan_progress import check_contract, check_physical, check_physical_edges, audit_physical_edges
from run_behaviour_equivalence import Lab, ROOT


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PhysicalLab(Lab):
    """Allow the explicitly bounded 40/45-second native tools to finish."""
    def request(self, method, params):
        self.serial += 1
        self.p.stdin.write(json.dumps(dict(jsonrpc='2.0', id=self.serial, method=method, params=params)) + '\n')
        self.p.stdin.flush()
        deadline = time.monotonic() + 90
        while True:
            response = self.records.get(timeout=max(.01, deadline - time.monotonic()))
            assert response is not None, 'lab exited'
            if response.get('id') == self.serial:
                return response


def prepare(folder, legacy=False, deadline_control=False):
    """Copy sources; optional legacy-reset/deadline controls stay private."""
    assert not folder.exists(), 'retain previous build'
    shutil.copytree(ROOT / 'src', folder / 'src')
    (folder / 'lq1').mkdir()
    (folder / 'runs').mkdir()
    src = folder / 'src'
    path = src / 'argus.qc'
    source = path.read_text()
    assert not (legacy and deadline_control)
    if legacy:
        pattern = r'void\(float paused, entity reached\) Argus_PlanObserve =\n\{.*?^\};'
        source, count = re.subn(pattern, 'void(float paused, entity reached) Argus_PlanObserve = {};', source, flags=re.M | re.S)
        assert count == 1
        anchor = '        self.ar_lastpos = self.origin;'
        assert source.count(anchor) == 1
        source = source.replace(anchor, '        else if (vlen (self.origin - self.ar_lastpos) >= 12)\n            self.ar_stallrun = 0;\n' + anchor)
        path.write_text(source)
    if deadline_control:
        anchor = '        if (self.ar_taskgoal == world) self.ar_goalstart = time;'
        assert source.count(anchor) == 1
        source = source.replace(anchor, '        // PRIVATE negative control: retain the original goal deadline.')
        path.write_text(source)
    block = source.split('    // ---- stall detection ----', 1)[1].split('    if (time > self.ar_nextlog)', 1)[0]
    wrapper = 'void() PlanDecision =\n{\n    local vector gp;\n    local float fighting;\n    fighting = plan_fighting;\n' + block + '};\n'
    fixture = (ROOT / 'tools/fixtures/plan_progress.qc').read_text()
    assert fixture.count('// INSERT_DECISION') == 1
    (src / 'plan_progress.qc').write_text('float() random = { return 0.5; };\nvoid() PlanEdgeCases;\n' + fixture.replace('// INSERT_DECISION', wrapper))
    shutil.copy2(ROOT / 'tools/fixtures/plan_escape.qc', src / 'plan_escape.qc')
    physical_source = ROOT / 'tools/fixtures/plan_physical_edges.qc'
    audit_physical_edges(physical_source.read_text())
    shutil.copy2(physical_source, src / 'plan_physical_edges.qc')
    edges = (ROOT / 'tools/fixtures/plan_edges.qc').read_text()
    epoch = '' if re.search(r'\bfloat\s+argus_plan_serial\s*;', source) else 'float argus_plan_serial;'
    (src / 'plan_edges.qc').write_text(edges.replace('// INSERT_EPOCH_DECLARATION', epoch))
    path = src / 'defs.qc'
    changed, count = re.subn(r'float\(\) random\s*= #7;[^\n]*', 'float() random; // PRIVATE fixed test input', path.read_text())
    assert count == 1
    path.write_text(changed)
    path = src / 'progs.src'
    source_list = path.read_text()
    assert source_list.count('\nworld.qc\n') == 1
    path.write_text(source_list.replace('\nworld.qc\n', '\nplan_progress.qc\nplan_escape.qc\nplan_edges.qc\nplan_physical_edges.qc\nworld.qc\n'))
    path = src / 'world.qc'
    world = path.read_text()
    assert world.count('Argus_FrameAll ();') == world.count('Argus_CountSlots ();') == 1
    world = world.replace('Argus_FrameAll ();', 'Argus_FrameAll ();\n    if (cvar ("scratch2") >= 3) PlanPhysicalEdges ();\n    else if (cvar ("scratch2") == 0) PlanFixture ();\n    else PlanEscapeFixture ();')
    path.write_text(world.replace('Argus_CountSlots ();', 'Argus_CountSlots ();\n    dprint ("BHVRPL begin plan_fixture\\n");'))
    build_tree = hashlib.sha256()
    for item in sorted(src.rglob('*')):
        if item.is_file() and item.suffix in {'.qc', '.src'}:
            build_tree.update(item.relative_to(src).as_posix().encode() + b'\0' + item.read_bytes())
    save(folder / 'source-receipt.json', dict(legacy_reset=legacy, deadline_control=deadline_control,
        production_sha256=sha(ROOT / 'src/argus.qc'), build_sha256=sha(src / 'argus.qc'),
        build_tree_sha256=build_tree.hexdigest(),
        fixture_sha256={name: sha(src / name) for name in
                        ('plan_progress.qc', 'plan_escape.qc', 'plan_edges.qc', 'plan_physical_edges.qc')},
        decision_sha256=hashlib.sha256(block.encode()).hexdigest()))
    # All generated nav, perception, weapons and other sources stay exact.
    for original in (ROOT / 'src').rglob('*'):
        relative = original.relative_to(ROOT / 'src')
        if original.is_file() and relative.as_posix() not in {'argus.qc', 'defs.qc', 'progs.src', 'world.qc'}:
            assert original.read_bytes() == (src / relative).read_bytes()
    if not legacy and not deadline_control:
        assert (src / 'argus.qc').read_bytes() == (ROOT / 'src/argus.qc').read_bytes()


def copy_assets(source, destination):
    """Copy independent local asset bytes, excluding user configuration/logs."""
    for path in source.rglob('*'):
        assert not path.is_symlink(), f'symlinked test asset: {path}'
    shutil.copytree(source, destination,
                    ignore=shutil.ignore_patterns('*.cfg', '*.log', '*.dem'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new directory beneath backups/')
    parser.add_argument('--mode', choices=('all', 'contract', 'physical', 'edges', 'physical-edges'), default='all')
    parser.add_argument('--physical-part', choices=('all', 'coop', 'detour', 'normal'), default='all',
                        help='select a fixed part of --mode physical-edges without repeating accepted cases')
    parser.add_argument('--allow-failed', action='store_true', help='retain complete failing decision receipts for a diagnostic control')
    args = parser.parse_args()
    if args.allow_failed and args.mode != 'edges':
        parser.error('--allow-failed is only for diagnostic edge controls')
    if args.physical_part != 'all' and args.mode != 'physical-edges':
        parser.error('--physical-part requires --mode physical-edges')
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'backups').resolve()):
        parser.error('output must be a new directory beneath backups/')
    output.mkdir(parents=True)
    installed = [ROOT / p for p in ('engine/argus/progs.dat', 'game/argus/progs.dat', 'lq1/progs.dat')]
    before = {str(p): sha(p) for p in installed}
    save(output / 'before.json', before)
    with (output / 'config.stderr').open('w') as err:
        lab = Lab(err, {'TOKIO_WORKER_THREADS': '2'})
        try:
            lab.call('see', what='project')
            config = lab.call('config_check')
        finally:
            lab.close()
    assert config['complete'], config
    values = {row['key']: row['value'] for row in config['entries']}
    original_base = Path(values['ARGUS_BASEDIR'])
    assert not any(p.exists() for p in (ROOT / 'qconsole.log', original_base / 'qconsole.log')), 'harvest the pending human session first'
    game = values['ARGUS_GAME']
    assert re.fullmatch(r'[A-Za-z0-9_-]+', game)
    base = output / 'base'
    copy_assets(original_base / 'id1', base / 'id1')
    private_game = base / game
    private_game.mkdir(exist_ok=True)
    for name in ('maps', 'progs', 'gfx', 'sound'):
        source = original_base / game / name
        if source.is_dir():
            copy_assets(source, private_game / name)
    for pak in (original_base / game).glob('*.pak'):
        assert not pak.is_symlink()
        shutil.copy2(pak, private_game / pak.name)
    schedule = []
    if args.mode == 'physical-edges':
        schedule += [('current', 'dm2', 3, 40), ('current', 'e1m2', 4, 45),
                     ('current', 'e1m2', 5, 45), ('deadline_control', 'e1m2', 4, 45)]
        if args.physical_part != 'all':
            cases = {'coop': {3}, 'detour': {4, 5}, 'normal': {5}}[args.physical_part]
            schedule = [row for row in schedule if row[2] in cases]
    elif args.mode == 'edges':
        schedule += [('current', 'dm2', 0, 10), ('current', 'e1m2', 0, 10)]
    elif args.mode != 'physical':
        schedule += [('current', 'dm2', 0, 10), ('current', 'dm4', 0, 10)]
    if args.mode in ('all', 'physical'):
        schedule += [('current', 'dm2', 1, 15), ('current', 'dm2', 2, 15),
                     ('legacy_reset', 'dm2', 2, 15)]
    save(output / 'plan.json', dict(schedule=schedule,
        diagnostic_only=args.allow_failed,
        physical_edge_acceptance=dict(coop='Real 20-second rest, intact request, fresh retry and physical contact within 35 s.',
            detour='Ordinary routing/movement, >20.5 s elapsed at declared pace 160, >=650 horizontal units, >=40 units away from initial goal distance, >=5 distinct reached legs, physical contact by 40 s.',
            normal_pace='Same detour at pace 320, physical contact by 40 s.',
            control='Only deadline renewal removed; must physically travel then lose the goal at 20-21.5 s without contact.') if args.mode == 'physical-edges' else None,
        acceptance='All current contracts and physical cases pass; legacy reset is a negative control, not a shipped baseline or a rate comparison.',
        production_sha256=sha(ROOT / 'src/argus.qc')))
    results = []
    try:
        for variant in dict.fromkeys(row[0] for row in schedule):
            folder = output / variant
            prepare(folder, legacy=variant == 'legacy_reset', deadline_control=variant == 'deadline_control')
            environment = dict(ARGUS_SRC=str(folder / 'src'), ARGUS_PROGS=str(folder / 'lq1/progs.dat'),
                               ARGUS_RUNS=str(folder / 'runs'), ARGUS_BASEDIR=str(base),
                               ARGUS_GAME=game, TOKIO_WORKER_THREADS='2')
            with (folder / 'lab.stderr').open('w') as err:
                lab = PhysicalLab(err, environment) if args.mode == 'physical-edges' else Lab(err, environment)
                try:
                    compiled = lab.call('compile_qc', install=False)
                    save(folder / 'compile.json', compiled)
                    assert compiled['ok'] and not compiled['installed_to']
                    assert compiled['new_errors'] == compiled['new_warnings'] == 0, compiled
                    shutil.copy2(folder / 'lq1/progs.dat', private_game / 'progs.dat')
                    for _, map_name, case, seconds in (s for s in schedule if s[0] == variant):
                        (private_game / 'autoexec.cfg').write_text(f'sv_protocol 15\nmax_edicts 600\nscratch2 {case}\nscratch3 {589 if args.mode == "edges" else 0}\n')
                        stem = f'plan_{variant}_{map_name}_{case}'
                        if case == 3:
                            native = lab.call('campaign_experiment', map=map_name, duration_sec=seconds,
                                              skill=1, compile=False, seat='solo', run_name=stem)
                        else:
                            native = lab.call('experiment', map=map_name, duration_sec=seconds, skill=1,
                                              compile=False, repeats=1, primary='stall_parity', run_name=stem)
                        save(folder / (stem + '.native.json'), native)
                        tape = folder / 'runs' / (stem + '.log')
                        text = tape.read_text(errors='replace')
                        if case >= 3:
                            checked = check_physical_edges(text, case, deadline_control=variant == 'deadline_control')
                        else:
                            checked = check_physical(text, case) if case else check_contract(text, map_name, edges=args.mode == 'edges')
                        row = dict(variant=variant, map=map_name, case=case, **checked,
                                   tape_sha256=sha(tape), binary_sha256=sha(private_game / 'progs.dat'))
                        results.append(row)
                        save(output / 'results.json', results)
                        print(json.dumps(row), flush=True)
                        if variant == 'current':
                            if not args.allow_failed:
                                assert checked.get('success', not checked.get('failures')), row
                        else:
                            assert not checked['success'], 'negative control did not distinguish the failed camp'
                finally:
                    lab.close()
    finally:
        after = {str(p): sha(p) for p in installed}
        save(output / 'after.json', after)
        assert before == after, 'installed game bytes changed'


if __name__ == '__main__':
    main()
