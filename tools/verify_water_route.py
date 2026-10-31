"""Observe real water-route execution in private native lab assets."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write, lab_executable

DECISION_LABELS = ('walk_chain','typed_jump','typed_sprint','typed_rocket','typed_swim',
    'typed_lift','typed_train','typed_door','height_change','active_action',
    'swimming_keeps_depth','no_route','cycle_is_bounded','action_without_rockets',
    'rocket_only_requires_gear','rocket_only_with_gear','sprint_requires_skill',
    'impossible_jump_rejected','jump_waits_for_seat','jump_ready_on_seat',
    'bank_waits_for_ground','bank_waits_for_height','wading_bank_is_support',
    'action_starts_clock','action_times_out','action_approach_renews',
    'action_oscillation_not_progress','action_pause_suspends','action_contact_does_not_renew','action_new_seat_resets',
    'action_new_goal_resets','action_direct_held','action_task_preserved','action_goal_shelved',
    'action_dry_wait_owned','action_dry_airborne_wait_unowned','action_floating_wait_unowned','action_wading_wait_unowned',
    'action_rider_must_progress','action_stale_contact_unowned','action_no_wait_unowned',
    'noise_walk_allowed','noise_jump_held','noise_swim_held','noise_lift_held',
    'noise_train_held','noise_rocket_held','noise_door_held','noise_runup_held','noise_tactic_held',
    'gait_plain_route_allowed','gait_immediate_action','gait_second_action',
    'gait_distant_action_allowed','gait_action_releases_hold','gait_plain_hold_kept')


def inspect_decisions(text, required):
    if not required:
        assert not re.search(r'^RDEC ', text, re.M)
        return 0
    assert re.findall(r'^RDEC begin checks (\d+)$', text, re.M) == [(str(len(DECISION_LABELS)))]
    rows=re.findall(r'^RDEC check (\w+) ([01])$', text, re.M)
    assert tuple(k for k,_ in rows) == DECISION_LABELS
    assert all(ok=='1' for _,ok in rows), rows
    assert re.findall(r'^RDEC end checks (\d+) failures (\d+)$', text, re.M) == [(str(len(DECISION_LABELS)),'0')]
    assert len(re.findall(r'^RDEC ', text, re.M)) == len(DECISION_LABELS)+2
    return len(rows)


def audit_fixture(text):
    """The observer cannot steer, move actors or modify the world after setup."""
    after = text.split('    wr_frames = wr_frames + 1;', 1)[1]
    observe, terminal = after.split('    if (completed || time > wr_begin + wr_limit || wr_bot.health <= 0)', 1)
    assert not re.search(r'\b(setorigin|setsize|walkmove|droptofloor|Argus_\w+)\s*\(', observe)
    assert not re.search(r'\b\w+\.\w+\s*=(?!=)', observe), 'observer mutates actor/world'
    assert terminal.count('wr_bot.velocity =') == terminal.count('wr_bot.movetype =') == 1
    assert set(re.findall(r'\b(\w+\.\w+)\s*=(?!=)', terminal)) == {'wr_bot.velocity','wr_bot.movetype','wr_bot.think','wr_bot.nextthink'}
    assert not re.search(r'\b(setorigin|setsize|walkmove|Argus_\w+)\s*\(', terminal)
    assert text.count('setorigin (self, wr_seed)') == 1
    assert 'BHVRPL begin water_route' in text


def stage(root, output, source=None):
    shutil.copytree(source or root / 'src', output / 'src')
    (output / 'lq1').mkdir(); (output / 'runs').mkdir()
    src = output / 'src'
    fixture = (root / 'tools/fixtures/water_route.qc').read_text()
    audit_fixture(fixture)
    (src / 'water_route_fixture.qc').write_text(fixture)
    components = 'Argus_GaitApproachAction =' in (src/'argus.qc').read_text()
    if components: (src/'water_route_fixture.qc').write_text('#define ROUTE_ACTION_COMPONENTS\n'+fixture)
    contracts=(root/'tools/fixtures/route_decisions.qc').read_text()
    if components: contracts='#define ROUTE_DECISION_COMPONENTS\n'+contracts
    (src/'route_decisions_fixture.qc').write_text(contracts)
    path = src / 'progs.src'; text = path.read_text()
    assert text.count('\nworld.qc\n') == 1
    path.write_text(text.replace('\nworld.qc\n', '\nroute_decisions_fixture.qc\nwater_route_fixture.qc\nworld.qc\n'))
    path = src / 'world.qc'; text = path.read_text()
    assert text.count('Argus_FrameAll ();') == 1
    path.write_text(text.replace('Argus_FrameAll ();',
        'WaterRouteBefore ();\n    if (!wr_done) Argus_FrameAll ();\n    WaterRouteAfter ();'))
    return components


def inspect_fixture(text, map_name, ticrate, case=1):
    assert not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error'))
    assert re.findall(r'^ARGUS init on (\S+)$', text, re.M) == [map_name]
    assert text.count('BHVRPL begin water_route') == 1
    starts = re.findall(r"^WRFIX begin dt_ms\s+([\d.]+) case (\d+) start '([^']+)' goal '([^']+)'$", text, re.M)
    ends = re.findall(r"^WRFIX end completed\s+([01]) seconds\s+([\d.]+) handoffs\s+(\d+) active\s+([01]) pos '([^']+)' hp ([\d.]+) frames (\d+) grounded ([01]) feet (-?\d+)$", text, re.M)
    assert len(starts) == len(ends) == 1
    ms = float(starts[0][0]); assert int(starts[0][1]) == case, 'wrong fixture case'
    assert (90 <= ms <= 110) if ticrate == .1 else (10 <= ms <= 30)
    samples = re.findall(r"^WRFIX sample t\s+([\d.]+) pos '([^']+)' node '([^']+)' grounded ([01]) wet ([0-3]) feet (-?\d+) handoffs (\d+) active ([01]) hp ([\d.]+) frames (\d+)$", text, re.M)
    assert len(samples) >= 2
    assert len([s for s in text.splitlines() if s.startswith('WRFIX')]) == len(samples) + 2
    start = tuple(map(float, starts[0][2].split())); target = tuple(map(float, starts[0][3].split()))
    expected_start = (-279,425,8) if map_name == 'e1m5' else (1093,-159,-336)
    if case == 2 and map_name == 'e1m5': expected_start = (-791,233,8)
    expected_target = (-183,73,80) if map_name == 'e1m5' else (1349,545,-392)
    if 3 <= case <= 9:
        assert map_name == 'e1m5'
        expected_start=(20,889,105) if case == 5 else (41,713,47)
        expected_target=(20,889,104) if case == 4 else (-87,809,111)
    if case in (8,9):
        expected_start=(-279,425,8)
        expected_target=(-535,1353,152) if case == 8 else (-87,809,111)
    if case == 10: expected_start=(823.9,496,-257.9); expected_target=(1201,961,-256)
    if case in (11,12): expected_start=(810.5,505.1,-223.5); expected_target=(689,481,104)
    assert start == expected_start and target == expected_target, 'wrong task geometry'
    vector = lambda s: tuple(map(float, s.split()))
    assert float(samples[0][0]) == 0 and math.dist(vector(samples[0][1]), start) < .2
    for a, b in zip(samples, samples[1:]):
        assert 0 < float(b[0]) - float(a[0]) <= .7 and int(b[-1]) > int(a[-1])
        assert math.dist(vector(a[1]), vector(b[1])) < 240, 'discontinuous trajectory'
    # Reaching e1m5's dry checkpoint can legitimately collect the real mega.
    # Require no injury; never mistake that pickup for fixture health repair.
    assert all(float(s[-2]) >= 100 and (s[-3] == '1' or math.dist(vector(s[1]),target)<32) for s in samples), 'health/goal ownership lost'
    end = ends[0]; final = vector(end[4]); elapsed = float(end[1])
    assert all(len(v)==3 and all(math.isfinite(x) for x in v) for v in (start,target,final,*[vector(s[1]) for s in samples]))
    assert float(samples[-1][0]) <= elapsed <= float(samples[-1][0]) + .7
    assert int(end[6]) >= int(samples[-1][-1]) and float(end[5]) >= 100
    assert end[3] == '1' or (end[0] == '1' and math.dist(final,target)<32), 'goal released before task completion'
    assert math.dist(final, vector(samples[-1][1])) < 240
    at_target = math.dist(final, target) < 48
    if case in (11,12): at_target = math.dist(final[:2],start[:2]) >= 64
    if 3 <= case <= 9: at_target = at_target and end[7] == '1' and end[8] != '-3' and abs(final[2]-target[2]) <= 18
    assert (end[0] == '1') == at_target, 'unproved completion'
    assert 0 < elapsed <= (30.2 if case in (8,9) else 18.2)
    fps = (int(end[6]) - 1) / elapsed
    assert (8 <= fps <= 12) if ticrate == .1 else (60 <= fps <= 90), 'cadence disagrees with observed frame count'
    return dict(completed=ends[0][0] == '1', seconds=float(ends[0][1]),
        handoffs=int(ends[0][2]), active=ends[0][3] == '1', frame_ms=ms,
        start=start, target=target, final_position=final, measured_fps=fps,
        grounded=end[7]=='1', feet_contents=int(end[8]),
        samples=samples)


def require_outcome(row, control):
    if row.get('case') == 11:
        assert not control, 'cold ride is not a negative pin reproduction'
        assert row['completed'] and row['seconds'] < 6, 'ordinary ride failed'
    elif row.get('case') == 12:
        assert row['completed'], 'lift pin never escaped'
        assert row['seconds'] >= 7 if control else row['seconds'] < 6, 'unsupported-wait recovery bound failed'
    elif control:
        assert not row['completed'] and row['handoffs'] == 0 and row['seconds'] >= 18, 'control did not reproduce the blocked entry'
    else:
        assert row['completed'] and row['handoffs'] > 0, 'candidate did not complete the real route'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--maps', default='e1m5,dm3')
    parser.add_argument('--ticrate', type=float, choices=(.0139, .1), default=.0139)
    parser.add_argument('--port', type=int, default=26005)
    parser.add_argument('--case', type=int, choices=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12), default=1)
    parser.add_argument('--control', action='store_true', help='require the original blocked entry (cases 1/2) or raised-platform delay (case 12)')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_]+', args.prefix)
    maps = args.maps.split(','); assert maps and len(set(maps)) == len(maps)
    assert set(maps) <= {'e1m5', 'dm3','e1m1'} and 1024 <= args.port <= 65535
    assert args.case < 3 or maps == (['e1m1'] if args.case in (10,11,12) else ['e1m5'])
    assert not args.control or args.case in (1,2,12), 'this case has no declared negative outcome'
    output = args.output.resolve(); assert not output.exists()
    assert output.is_relative_to((ROOT / 'backups').resolve())
    protected = {p: digest(ROOT / p) for p in ('game/argus/progs.dat', 'engine/argus/progs.dat')}
    components=stage(ROOT, output, args.source)
    game = 'watercheck_' + args.prefix; folder = ROOT / 'engine' / game
    assert not folder.exists(); folder.mkdir()
    for name in ('progs', 'maps', 'sound', 'gfx'):
        original = ROOT / 'engine/argus' / name
        if original.exists(): shutil.copytree(original, folder / name)
    (folder / 'autoexec.cfg').write_text(f'sv_protocol 15\nmax_edicts 600\nscratch2 {args.case}\n')
    native.EXE = lab_executable()
    env = dict(ARGUS_SRC=str(output / 'src'), ARGUS_PROGS=str(output / 'lq1/progs.dat'),
        ARGUS_RUNS=str(output / 'runs'), ARGUS_GAME=game, ARGUS_PYTHON=sys.executable,
        ARGUS_TICRATE=str(args.ticrate))
    rows = []
    with (output / 'lab.stderr').open('w') as err:
        lab = Lab(err, env)
        try:
            lab.call('see', what='project')
            compiled = lab.call('compile_qc', install=False); write(output / 'compile.json', compiled)
            assert compiled['ok'], compiled
            shutil.copy2(output / 'lq1/progs.dat', folder / 'progs.dat')
            for map_name in maps:
                name = args.prefix + '_' + map_name
                result = subprocess.run([str(native.EXE), 'match', map_name, '36' if args.case in (8,9) else '24', name,
                    '--skill', '2', '--port', str(args.port)], cwd=ROOT,
                    env=dict(os.environ, ARGUS_ROOT=str(ROOT), **env), capture_output=True,
                    text=True, encoding='utf-8', timeout=65)
                (output / (map_name + '.stderr')).write_text(result.stderr)
                assert result.returncode == 0, result.stderr
                raw = output / 'runs' / (name + '.log')
                row = dict(map=map_name, case=args.case, control=args.control,
                    source_sha256=digest(output / 'src/argus.qc'),
                    fixture_sha256=digest(output / 'src/water_route_fixture.qc'),
                    binary_sha256=digest(folder / 'progs.dat'), raw_sha256=digest(raw),
                    raw=str(raw.relative_to(ROOT)))
                write(output / (map_name + '.identity.json'), row)
                brief = lab.call('brief_run', log=str(raw), map=map_name, detail='full')
                write(output / (map_name + '.brief.json'), brief)
                try:
                    row.update(inspect_fixture(raw.read_text(errors='replace'), map_name, args.ticrate, args.case))
                    row['decision_checks']=inspect_decisions(raw.read_text(errors='replace'),components)
                    assert not brief['events'].get('unstick', 0), 'forced relocation is not route completion'
                    require_outcome(row, args.control)
                    row['accepted'] = True
                except AssertionError as error:
                    row.update(accepted=False, rejection=str(error))
                rows.append(row); write(output / 'receipt.json', rows)
                print(json.dumps({k:v for k,v in row.items() if k!='samples'}), flush=True)
                assert row['accepted'], row['rejection']
        finally:
            lab.call('match_stop'); lab.close()
            assert protected == {p: digest(ROOT / p) for p in protected}


if __name__ == '__main__':
    main()
