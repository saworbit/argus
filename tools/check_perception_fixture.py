"""Independent oracle for controlled-input PERFIX; never parses ARGLOG metrics."""
from argus_validation import require
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LABELS = ['clock', 'initial_observation'] + ['hidden_pair'] * 6 + [
    'reacquired', 'prediction_bound', 'unseen_pain', 'unseen_pain_trace', 'visible_pain', 'visible_pain_trace',
    'secondary_observed', 'secondary_hidden', 'target_switch', 'target_death', 'observer_respawn', 'roster_removal']


def function(source, name):
    match = re.search(r'^[^\n]*\b' + re.escape(name) + r'\s*=\s*\n\{\n(.*?)^\};', source, re.M | re.S)
    require((match), 'missing function ' + name)
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', match[1], flags=re.S)


def audit(source):
    combat = function(source, 'Argus_Combat')
    forbidden = r'\be\.(?:(?:origin|velocity)(?:_[xyz])?|flags|waterlevel|movetype|invisible_finished|super_damage_finished|invincible_finished)\b'
    require((not re.search(forbidden, combat)), 'combat reads hidden live state')
    for helper in ('Argus_EnemyPosition', 'Argus_EnemyVelocity', 'Argus_EnemyPowerThreat'):
        code = function(source, helper)
        require((not re.search(r'\bar_enemy\.(?:(?:origin|velocity)(?:_[xyz])?|flags|weapon|\w+_finished)\b', code)), 'cache helper reads live state')
        require((not re.search(r'\b(?:random|traceline|makevectors)\s*\(', code)), 'cache helper changes observation inputs')
    require((not re.search(r'\bthreat\.origin\b', function(source, 'Argus_ThreatCovered'))))
    require((not re.search(r'\bvictim\.origin\b', function(source, 'Argus_SplashSafe'))))
    require((len(re.findall(r'self\.ar_seen\s*=\s*time\s*;', source)) == 1), 'visual stamp has another producer')
    require(('self.ar_seen = time;' in function(source, 'Argus_ObserveEnemy')))
    visibility = function(source, 'Argus_CanSee')
    require(('trace_fraction != 1' in visibility), 'missing world occlusion gate')
    require((visibility.index('trace_fraction != 1') < visibility.index('e.invisible_finished')), 'hidden actor consumes glimpse RNG')
    pain = function(source, 'Argus_Pain')
    require((re.search(r'Argus_PainCanSee\s*\(attacker\).*?Argus_ObserveEnemy\s*\(attacker\)', pain, re.S)), 'damage promotes unseen attacker')
    callback = function(source, 'Argus_PainCanSee')
    for field in ('fraction','allsolid','startsolid','plane_dist','endpos','plane_normal','inopen','inwater','ent'):
        require((re.search(r'\btrace_' + field + r'\s*=', callback)), 'callback does not restore trace_' + field)
    require(('Argus_ObservationReset ();' in function(source, 'Argus_Die')))
    require(('Argus_ObservationReset ();' in function(source, 'Argus_BaseStats')))
    require(('Argus_ObservationRemoved (b);' in function(source, 'Argus_RemoveBot')))
    return dict(single_visual_stamp_producer=True, primary_live_reads_removed=True,
                health_and_inventory_follow_up_separate=True)


def check(text, map_name, ring, expected_ids):
    require(('BHVFIX begin perception' in text), 'missing native fixture quarantine marker')
    require((not any(x in text for x in ('Host_Error', 'Program error', 'runaway loop error'))), 'engine error')
    active = None
    completed = []
    for line in text.splitlines():
        if not line.startswith('PERFIX '):
            continue
        words = line.split()
        kind = words[1]
        if kind == 'begin':
            require((active is None and len(words) == 7 and words[2] == map_name))
            require((words[3] == 'id' and words[5:] == ['ring', str(ring)]))
            trial = int(words[4]); require((trial > 0))
            active = dict(id=trial, labels=[], ended=False, clean=False)
        elif kind == 'check':
            require((active and not active['ended'] and len(words) == 5))
            require((int(words[2]) == active['id'] and words[4] == '1'), 'failed/wrong trial check: ' + line)
            active['labels'].append(words[3])
        elif kind == 'end':
            require((active and not active['ended']))
            require((len(words) == 14 and int(words[2]) == active['id']))
            require((words[3:7] == ['checks', str(len(LABELS)), 'ok', '1']))
            require((words[7] == 'frames' and words[9] == 'seconds' and words[11] == 'dt_ms'))
            require((words[13] == 'controlled'), 'missing controlled-input acknowledgement')
            require((active['labels'] == LABELS), 'missing, duplicate or reordered coverage')
            frames, seconds, dt_ms = int(words[8]), float(words[10]), float(words[12])
            require((frames >= 2 and .19 <= seconds <= .4 and 0 < dt_ms <= 101))
            active.update(ended=True, frames=frames, seconds=seconds, dt_ms=dt_ms)
        elif kind == 'cleanup':
            require((active and active['ended'] and not active['clean']))
            require((words[2:] == [str(active['id']), 'restored', '1']), 'cleanup failed')
            active['clean'] = True
        elif kind == 'done':
            require((active and active['clean'] and words[2:] == [str(active['id'])]))
            require((active['id'] not in [r['id'] for r in completed]), 'duplicate trial ID')
            completed.append(active); active = None
        else:
            raise AssertionError('refused, overlapping or unknown fixture record: ' + line)
    require((active is None and [r['id'] for r in completed] == expected_ids), 'incomplete trials')
    return completed


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log', type=Path, nargs='?')
    ap.add_argument('--map', choices=('dm2', 'dm4'))
    ap.add_argument('--ring', type=int, choices=(0, 1))
    ap.add_argument('--ids', default='1')
    args = ap.parse_args()
    print(json.dumps(audit((ROOT / 'src/argus.qc').read_text())))
    if args.log:
        require((args.map and args.ring is not None))
        print(json.dumps(check(args.log.read_text(), args.map, args.ring,
                               list(map(int, args.ids.split(',')))), indent=2))
