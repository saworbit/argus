"""Observe real water-route execution in private native lab assets."""

from argus_source import source_identity
from argus_fixture_harness import (new_output, stage_fixture, private_game,
    read_tape, check_tape, frame_ms as measured_frame_ms, run_match)

from run_behaviour_equivalence import lab_executable
from argus_validation import require
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys

import run_behaviour_equivalence as native
from run_map_intelligence import ROOT, Lab, digest, write

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
        require((not re.search(r'^RDEC ', text, re.M)))
        return 0
    require((re.findall(r'^RDEC begin checks (\d+)$', text, re.M) == [(str(len(DECISION_LABELS)))]))
    rows=re.findall(r'^RDEC check (\w+) ([01])$', text, re.M)
    require((tuple(k for k,_ in rows) == DECISION_LABELS))
    require((all(ok=='1' for _,ok in rows)), rows)
    require((re.findall(r'^RDEC end checks (\d+) failures (\d+)$', text, re.M) == [(str(len(DECISION_LABELS)),'0')]))
    require((len(re.findall(r'^RDEC ', text, re.M)) == len(DECISION_LABELS)+2))
    return len(rows)


def audit_fixture(text):
    """The observer cannot steer, move actors or modify the world after setup."""
    after = text.split('    wr_frames = wr_frames + 1;', 1)[1]
    observe, terminal = after.split('    if (completed || time > wr_begin + wr_limit || wr_bot.health <= 0)', 1)
    require((not re.search(r'\b(setorigin|setsize|walkmove|droptofloor|Argus_\w+)\s*\(', observe)))
    require((not re.search(r'\b\w+\.\w+\s*=(?!=)', observe)), 'observer mutates actor/world')
    require((terminal.count('wr_bot.velocity =') == terminal.count('wr_bot.movetype =') == 1))
    require((set(re.findall(r'\b(\w+\.\w+)\s*=(?!=)', terminal)) == {'wr_bot.velocity','wr_bot.movetype','wr_bot.think','wr_bot.nextthink'}))
    require((not re.search(r'\b(setorigin|setsize|walkmove|Argus_\w+)\s*\(', terminal)))
    require((text.count('setorigin (self, wr_seed)') == 1))
    require(('BHVRPL begin water_route' in text))


def stage(root, output, source=None):
    base = Path(source or root / 'src')
    fixture = (root / 'tools/fixtures/water_route.qc').read_text(encoding='utf-8')
    audit_fixture(fixture)
    components = 'Argus_GaitApproachAction =' in (base / 'argus.qc').read_text(encoding='utf-8')
    contracts = (root / 'tools/fixtures/route_decisions.qc').read_text(encoding='utf-8')
    if components:
        fixture = '#define ROUTE_ACTION_COMPONENTS\n' + fixture
        contracts = '#define ROUTE_DECISION_COMPONENTS\n' + contracts
    stage_fixture(root, output, source,
                  fixtures={'route_decisions_fixture.qc': contracts, 'water_route_fixture.qc': fixture},
                  frame_wrap='WaterRouteBefore ();\n    if (!wr_done) Argus_FrameAll ();\n    WaterRouteAfter ();')
    return components


def inspect_fixture(text, map_name, ticrate, case=1):
    check_tape(text, map_name)
    require((text.count('BHVRPL begin water_route') == 1))
    starts = re.findall(r"^WRFIX begin dt_ms\s+([\d.]+) case (\d+) start '([^']+)' goal '([^']+)'$", text, re.M)
    ends = re.findall(r"^WRFIX end completed\s+([01]) seconds\s+([\d.]+) handoffs\s+(\d+) active\s+([01]) pos '([^']+)' hp ([\d.]+) frames (\d+) grounded ([01]) feet (-?\d+)$", text, re.M)
    require((len(starts) == len(ends) == 1))
    ms = measured_frame_ms(text, 'WRFIX', ticrate); require((int(starts[0][1]) == case), 'wrong fixture case')
    samples = re.findall(r"^WRFIX sample t\s+([\d.]+) pos '([^']+)' node '([^']+)' grounded ([01]) wet ([0-3]) feet (-?\d+) handoffs (\d+) active ([01]) hp ([\d.]+) frames (\d+)$", text, re.M)
    require((len(samples) >= 2))
    require((len([s for s in text.splitlines() if s.startswith('WRFIX')]) == len(samples) + 2))
    start = tuple(map(float, starts[0][2].split())); target = tuple(map(float, starts[0][3].split()))
    expected_start = (-279,425,8) if map_name == 'e1m5' else (1093,-159,-336)
    if case == 2 and map_name == 'e1m5': expected_start = (-791,233,8)
    expected_target = (-183,73,80) if map_name == 'e1m5' else (1349,545,-392)
    if 3 <= case <= 9:
        require((map_name == 'e1m5'))
        expected_start=(20,889,105) if case == 5 else (41,713,47)
        expected_target=(20,889,104) if case == 4 else (-87,809,111)
    if case in (8,9):
        expected_start=(-279,425,8)
        expected_target=(-535,1353,152) if case == 8 else (-87,809,111)
    if case == 10: expected_start=(823.9,496,-257.9); expected_target=(1201,961,-256)
    if case in (11,12): expected_start=(810.5,505.1,-223.5); expected_target=(689,481,104)
    require((start == expected_start and target == expected_target), 'wrong task geometry')
    vector = lambda s: tuple(map(float, s.split()))
    require((float(samples[0][0]) == 0 and math.dist(vector(samples[0][1]), start) < .2))
    for a, b in zip(samples, samples[1:]):
        require((0 < float(b[0]) - float(a[0]) <= .7 and int(b[-1]) > int(a[-1])))
        require((math.dist(vector(a[1]), vector(b[1])) < 240), 'discontinuous trajectory')
    # Reaching e1m5's dry checkpoint can legitimately collect the real mega.
    # Require no injury; never mistake that pickup for fixture health repair.
    require((all(float(s[-2]) >= 100 and (s[-3] == '1' or math.dist(vector(s[1]),target)<32) for s in samples)), 'health/goal ownership lost')
    end = ends[0]; final = vector(end[4]); elapsed = float(end[1])
    require((all(len(v)==3 and all(math.isfinite(x) for x in v) for v in (start,target,final,*[vector(s[1]) for s in samples]))))
    require((float(samples[-1][0]) <= elapsed <= float(samples[-1][0]) + .7))
    require((int(end[6]) >= int(samples[-1][-1]) and float(end[5]) >= 100))
    require((end[3] == '1' or (end[0] == '1' and math.dist(final,target)<32)), 'goal released before task completion')
    require((math.dist(final, vector(samples[-1][1])) < 240))
    at_target = math.dist(final, target) < 48
    if case in (11,12): at_target = math.dist(final[:2],start[:2]) >= 64
    if 3 <= case <= 9: at_target = at_target and end[7] == '1' and end[8] != '-3' and abs(final[2]-target[2]) <= 18
    require(((end[0] == '1') == at_target), 'unproved completion')
    require((0 < elapsed <= (30.2 if case in (8,9) else 18.2)))
    fps = (int(end[6]) - 1) / elapsed
    require(((8 <= fps <= 12) if ticrate == .1 else (60 <= fps <= 90)), 'cadence disagrees with observed frame count')
    return dict(completed=ends[0][0] == '1', seconds=float(ends[0][1]),
        handoffs=int(ends[0][2]), active=ends[0][3] == '1', frame_ms=ms,
        start=start, target=target, final_position=final, measured_fps=fps,
        grounded=end[7]=='1', feet_contents=int(end[8]),
        samples=samples)


def require_outcome(row, control):
    if row.get('case') == 11:
        require((not control), 'cold ride is not a negative pin reproduction')
        require((row['completed'] and row['seconds'] < 6), 'ordinary ride failed')
    elif row.get('case') == 12:
        require((row['completed']), 'lift pin never escaped')
        require((row['seconds'] >= 7 if control else row['seconds'] < 6), 'unsupported-wait recovery bound failed')
    elif control:
        require((not row['completed'] and row['handoffs'] == 0 and row['seconds'] >= 18), 'control did not reproduce the blocked entry')
    else:
        require((row['completed'] and row['handoffs'] > 0), 'candidate did not complete the real route')


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
    require((re.fullmatch(r'[a-z0-9_]{1,48}', args.prefix)))
    maps = args.maps.split(','); require((maps and len(set(maps)) == len(maps)))
    require((set(maps) <= {'e1m5', 'dm3','e1m1'} and 1024 <= args.port <= 65535))
    require((args.case < 3 or maps == (['e1m1'] if args.case in (10,11,12) else ['e1m5'])))
    require((not args.control or args.case in (1,2,12)), 'this case has no declared negative outcome')
    output = new_output(args.output, root=ROOT, create=False)
    components=stage(ROOT, output, args.source)
    with private_game(ROOT, args.prefix, 'watercheck', autoexec=f'sv_protocol 15\nmax_edicts 600\nscratch2 {args.case}\n') as folder:
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
                    result = run_match(lab, map_name, int('36' if args.case in (8,9) else '24'), name, port=args.port, timeout=65, environment=env, stderr_path=output / (map_name + '.stderr'))
                    raw, text = read_tape(output, name, map_name)
                    row = dict(map=map_name, case=args.case, control=args.control,
                        source_sha256=source_identity(output / 'src'),
                        fixture_sha256=digest(output / 'src/water_route_fixture.qc'),
                        binary_sha256=digest(folder / 'progs.dat'), raw_sha256=digest(raw),
                        raw=str(raw.relative_to(ROOT)))
                    write(output / (map_name + '.identity.json'), row)
                    brief = lab.call('brief_run', log=str(raw), map=map_name, detail='full')
                    write(output / (map_name + '.brief.json'), brief)
                    try:
                        row.update(inspect_fixture(text, map_name, args.ticrate, args.case))
                        row['decision_checks']=inspect_decisions(text,components)
                        require((not brief['events'].get('unstick', 0)), 'forced relocation is not route completion')
                        require_outcome(row, args.control)
                        row['accepted'] = True
                    except AssertionError as error:
                        row.update(accepted=False, rejection=str(error))
                    rows.append(row); write(output / 'receipt.json', rows)
                    print(json.dumps({k:v for k,v in row.items() if k!='samples'}), flush=True)
                    require((row['accepted']), row['rejection'])
            finally:
                native.finish_lab(lab)


if __name__ == '__main__':
    main()
