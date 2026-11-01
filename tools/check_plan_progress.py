"""Independent decision/physical oracles; do not reconstruct ARGLOG metrics."""
from argus_validation import require
import math
import re


def audit_physical_edges(source):
    """Keep the observer from moving the actor or awarding plan progress."""
    code = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    contact = code.split('void() PlanPhysicalContact =', 1)[1].split('\n};', 1)[0]
    require((len(re.findall(r'\bpm_contact\s*=(?!=)', code)) == 1), 'contact awarded outside touch')
    require((re.search(r'\bpm_contact\s*=\s*time;', contact)), 'missing real touch clock')
    require((not re.search(r'\b(?:other|pm_bot)\.\w+\s*=(?!=)', contact)), 'touch moves/changes actor')
    require((not re.search(r'\b(?:walkmove|Argus_AI|Argus_Physics|Argus_PlanObserve|Argus_SetNext)\s*\(', code)), 'scripted movement/progress')
    require((len(re.findall(r'setorigin\s*\(self,\s*pm_start\)', code)) == 1), 'missing initial placement')
    require((len(re.findall(r'setorigin\s*\((?:self|pm_bot|other)\b', code)) == 1), 'actor repositioned')
    observing = code.split('    pm_frames = pm_frames + 1;', 1)[1].split('    if (pm_contact || lost', 1)[0]
    require((not re.search(r'\b(?:self|pm_bot|pm_door)\.\w+\s*=(?!=)', observing)), 'observer writes actor/mover state')
    calls = set(re.findall(r'\b(\w+)\s*\(', observing))
    require((calls <= {'if', 'dprint', 'ftos', 'vtos', 'remove', 'Argus_GoalTopKind', 'Argus_GoalTopSubj'}), 'observer calls a gameplay mutator')

LABELS = """sideways_retains_failure failed_plan_released small_gain_not_success
partial_gain_accumulates useful_progress_resets new_goal_fresh_attempt
route_rebuild_not_success reached_waypoint_counts same_waypoint_not_new_evidence
combat_ownership_pauses resume_has_fresh_attempt mover_wait_not_failure
typed_link_pause healthy_wait_no_timeout blocked_wait_reconsiders
new_life_fresh_attempt real_goal_failure_released alternative_selected""".split()

EDGE_LABELS = """fetch_stall_rests fetch_stack_kept fetch_peer_independent
fetch_retry_after_rest fetch_retry_gets_fresh_deadline fetch_combat_preserves_deadline
fetch_routefail_rests fetch_new_subject_allowed
fetch_timeout_rests detour_renews_deadline detour_survives_old_deadline
long_unique_detour fixed_task_deadline_preserved two_node_cycle_not_progress cycle_best_stays_monotonic
multi_node_cycle_not_progress cycle_eventually_reconsiders
new_goal_gets_new_visits visit_marks_per_bot peer_revisit_not_progress epoch_rollover""".split()


def common(text):
    require(('BHVRPL begin plan_fixture' in text), 'missing fixture quarantine')
    require((not any(t in text for t in ('Host_Error', 'Program error', 'runaway loop error'))), 'engine error')


def check_contract(text, map_name, edges=False):
    common(text)
    labels = LABELS[:-2] + EDGE_LABELS + LABELS[-2:] if edges else LABELS
    records = [line for line in text.splitlines() if line.startswith('PLANFIX ')]
    require((len(records) == len(labels) + 4), 'missing/extra records')
    require((records[0] == f'PLANFIX begin {map_name}'), 'wrong/missing begin')
    failed = []
    for line, label in zip(records[1:len(labels) + 1], labels):
        require((line in (f'PLANFIX check {label} 0', f'PLANFIX check {label} 1')), 'missing/duplicate/reordered check')
        if line.endswith(' 0'):
            failed.append(label)
    require((re.fullmatch(r'PLANFIX alternative \S+ elapsed\s+[\d.]+', records[-3])), 'missing alternative receipt')
    require((records[-2] == f'PLANFIX end checks {len(labels)} ok {int(not failed)}'), 'contradictory end')
    require((records[-1] == 'PLANFIX cleanup owned_engine_pending_stop'), 'missing cleanup')
    return dict(checks=len(labels), failures=failed)


def check_physical(text, case):
    common(text)
    records = [line for line in text.splitlines() if line.startswith('PEFIX ')]
    require((len(records) >= 5), 'missing physical receipts')
    begin = re.fullmatch(r"PEFIX begin dm2 case ([12]) start '?([^']+?)'? solid ([01]) respawn\s+([\d.-]+) actor_solid ([01])", records[0])
    require((begin and int(begin[1]) == case and begin[5] == '0'), 'bad physical premise')
    start = tuple(map(float, begin[2].split()))
    require((len(start) == 3))
    require((int(begin[3]) == (0 if case == 2 else 1)), 'wrong item state')
    if case == 2:
        require((float(begin[4]) > 12), 'item could respawn before observation ends')
    samples = []
    pattern = r"PEFIX sample t\s+([\d.]+) pos '?([^']+?)'? released ([01]) chosen ([01]) escaped ([01]) mode (\d) goal (\S+) hp\s+([\d.-]+) frames (\d+)"
    for line in records[1:-2]:
        m = re.fullmatch(pattern, line)
        require((m), 'malformed physical sample')
        t, pos = float(m[1]), tuple(map(float, m[2].split()))
        require((len(pos) == 3 and float(m[8]) == 100), 'subject damaged or invalid position')
        released, chosen, escaped = map(int, m.group(3, 4, 5))
        require((bool(escaped) == (math.dist(pos[:2], start[:2]) > 220)), 'false escape claim')
        require((not chosen or m[7] != 'worldspawn'), 'empty alternative')
        row = dict(t=t, pos=pos, released=released, chosen=chosen,
                   escaped=escaped, frames=int(m[9]))
        if samples:
            previous = samples[-1]
            require((t > previous['t'] and row['frames'] > previous['frames']), 'reordered samples')
            require((math.dist(pos, previous['pos']) <= 160), 'discontinuous/teleport escape')
        samples.append(row)
    require((len(samples) >= 2 and samples[0]['t'] == 0))
    success = bool(samples[-1]['released'] and samples[-1]['chosen'] and samples[-1]['escaped'])
    require((records[-2] == f'PEFIX end ok {int(success)}'), 'contradictory physical end')
    require((records[-1] == 'PEFIX cleanup owned_engine_pending_stop'), 'missing physical cleanup')
    require((samples[-1]['t'] <= 12.4))
    require((success or samples[-1]['t'] > 12), 'premature failure')
    fps = (samples[-1]['frames'] - samples[0]['frames']) / samples[-1]['t']
    require((5 <= fps <= 100), 'invalid measured cadence')
    return dict(success=success, elapsed=samples[-1]['t'], measured_fps=round(fps, 1),
                release_by=next((s['t'] for s in samples if s['released']), None),
                alternative_by=next((s['t'] for s in samples if s['chosen']), None),
                final_horizontal_distance=round(math.dist(samples[-1]['pos'][:2], start[:2]), 1),
                health=100, samples=len(samples))


def check_physical_edges(text, case, deadline_control=False):
    """Accept physical contact/continuous travel, never selections as pickup."""
    require(('BHVRPL begin plan_physical_edges' in text), 'missing physical quarantine')
    require((not any(s in text for s in ('Host_Error', 'Program error', 'runaway loop error'))), 'engine error')
    rows = [line for line in text.splitlines() if line.startswith('PMFIX ')]
    require((len(rows) >= 5), 'truncated physical receipt')
    begin = re.fullmatch(r"PMFIX begin (dm2|e1m2) case ([3456]) coop ([01]) dm ([01]) pace (160|320) start '([^']+)' goal '([^']+)' solid 0", rows[0])
    require((begin and int(begin[2]) == case and begin[1] == ('dm2' if case == 3 else 'e1m2')), 'wrong/missing physical premise')
    require((int(begin[3]) == (case == 3) and int(begin[4]) == (case != 3)), 'wrong actual game mode')
    require((int(begin[5]) == (160 if case == 4 else 320)), 'wrong declared pace')
    vector = lambda s: tuple(map(float, s.split()))
    start, goal = vector(begin[6]), vector(begin[7])
    require((len(start) == len(goal) == 3))
    samples, legs, events, movers = [], [], {}, []
    door = None
    for line in rows[1:-2]:
        m = re.fullmatch(r"PMFIX door model \*27 speed 20 from '([^']+)' to '([^']+)'", line)
        if m:
            require((case == 6 and door is None and not samples), 'unexpected/repeated door premise')
            door = tuple(vector(v) for v in m.groups())
            require((all(len(v) == 3 and all(math.isfinite(x) for x in v) for v in door)))
            require((math.dist(*door) > 32), 'no real door travel')
            continue
        m = re.fullmatch(r"PMFIX mover t\s+([\d.]+) pos '([^']+)' state ([0-3]) speed 20", line)
        if m:
            require((case == 6 and door is not None and len(movers) < len(samples)), 'unpaired mover sample')
            t, pos = float(m[1]), vector(m[2])
            require((len(pos) == 3 and all(math.isfinite(v) for v in (*pos, t))))
            require((t == samples[len(movers)]['t']), 'mover detached from trajectory')
            if movers:
                dt = t - movers[-1]['t']
                require((math.dist(pos, movers[-1]['pos']) <= 20 * (dt + .11) + .3), 'door moved faster than declared')
            movers.append(dict(t=t, pos=pos, state=int(m[3])))
            continue
        m = re.fullmatch(r"PMFIX sample t\s+([\d.]+) pos '([^']+)' active ([01]) stacked ([01]) hp\s+([\d.-]+) frames (\d+)", line)
        if m:
            t, pos = float(m[1]), vector(m[2])
            require((len(pos) == 3 and all(math.isfinite(v) for v in (*pos, t))), 'invalid position/time')
            require((float(m[5]) == 100), 'actor damaged')
            sample = dict(t=t, pos=pos, active=int(m[3]), stacked=int(m[4]), frames=int(m[6]))
            if samples:
                previous = samples[-1]
                require((0 <= t - previous['t'] <= .4 and sample['frames'] > previous['frames']), 'missing/reordered movement')
                require((math.dist(pos, previous['pos']) <= 160), 'discontinuous movement/teleport')
            samples.append(sample)
            continue
        m = re.fullmatch(r"PMFIX leg t\s+([\d.]+) pos '([^']+)' node '([^']+)'", line)
        if m:
            pos, node = vector(m[2]), vector(m[3])
            require((math.dist(pos, node) <= 128), 'unreached waypoint credited')
            legs.append(dict(t=float(m[1]), pos=pos, node=node))
            continue
        patterns = dict(rest=r'PMFIX rest t\s+([\d.]+) until\s+([\d.]+)',
                        gate=r'PMFIX gate t\s+([\d.]+)',
                        retry=r'PMFIX retry t\s+([\d.]+) deadline\s+([\d.]+)',
                        contact=r"PMFIX contact t\s+([\d.]+) pos '([^']+)' active 1")
        for kind, pattern in patterns.items():
            m = re.fullmatch(pattern, line)
            if m:
                require((kind not in events), 'duplicate physical event')
                events[kind] = (float(m[1]), *(m.groups()[1:]))
                break
        else:
            raise AssertionError(f'unknown/malformed physical record: {line}')
    require((len(samples) >= 3 and samples[0]['t'] == 0 and math.dist(samples[0]['pos'], start) < 1), 'missing initial movement sample')
    end = re.fullmatch(r'PMFIX end ok ([01]) lost ([01]) bad 0', rows[-2])
    require((end and rows[-1] == 'PMFIX cleanup owned_engine_pending_stop'), 'missing end/cleanup or ownership violation')
    elapsed = samples[-1]['t']
    path = sum(math.dist(a['pos'][:2], b['pos'][:2]) for a, b in zip(samples, samples[1:]))
    away = max(math.dist(s['pos'], goal) - math.dist(start, goal) for s in samples)
    fps = (samples[-1]['frames'] - samples[0]['frames']) / elapsed
    require((5 <= fps <= 100 and elapsed <= (35.2 if case == 3 else 40.2)), 'bad deadline/cadence')
    contact = events.get('contact')
    if case == 6:
        require((door and len(movers) == len(samples) and movers[0]['state'] == 1), 'missing closed-door premise/samples')
        require((math.dist(movers[0]['pos'], door[0]) < 1), 'door did not start closed')
        require((any(math.dist(m['pos'], door[0]) >= 16 and m['state'] == 2 for m in movers)), 'no engine-driven opening')
    success = bool(contact)
    require((int(end[1]) == success), 'contradictory physical result')
    if success:
        require((end[2] == '0' and math.dist(vector(contact[1]), goal) <= 80), 'false goal contact')
        require((abs(contact[0] - elapsed) <= .2 and math.dist(vector(contact[1]), samples[-1]['pos']) < 20), 'contact detached from trajectory')
        if case == 3:
            require((set(events) == {'rest', 'gate', 'retry', 'contact'}), 'missing co-op retry evidence')
            rest, until = events['rest'][0], float(events['rest'][1])
            retry, fresh = events['retry'][0], float(events['retry'][1])
            require((19.8 <= until - rest <= 20.2), 'wrong real rest interval')
            require((until - .1 <= events['gate'][0] <= retry + .1 and retry >= until - .1), 'early gate/retry')
            require((abs(fresh - retry) <= .2 and retry <= until + .5 and contact[0] >= retry), 'stale/late retry')
            require((all(not s['active'] and s['stacked'] for s in samples if rest + .1 < s['t'] < until - .1)), 'rearmed or discarded request during rest')
            require((math.dist(start[:2], vector(contact[1])[:2]) >= 180), 'no physical goal approach')
        else:
            require((set(events) == {'contact'} and all(s['active'] for s in samples)), 'detour abandoned goal')
            require((path >= 650 and away >= 40 and len(set(l['node'] for l in legs)) >= 5), 'insufficient physical detour')
            if case in (4, 6):
                require((elapsed > 20.5), 'did not test original deadline')
    elif deadline_control:
        require((case in (4, 6) and not events and end[2] == '1'), 'control failed for another reason')
        require((20 <= elapsed <= 21.5 and path >= 300), 'control did not reach old deadline through real travel')
    return dict(success=success, elapsed=elapsed, path_units=round(path, 1), away_units=round(away, 1),
                distinct_legs=len(set(l['node'] for l in legs)), measured_fps=round(fps, 1), events=events,
                lost=bool(int(end[2])), samples=len(samples), health=100)
