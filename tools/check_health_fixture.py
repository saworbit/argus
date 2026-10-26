"""Opponent-private-state boundary and strict HIFIX engine oracle."""
import json
import re
from pathlib import Path

from check_perception_fixture import function

LABELS = ['hidden_enter','hidden_stay','hidden_power_enter','hidden_power_stay',
          'visible_enter','visible_stay','visible_power_enter','visible_power_stay',
          'own_stack','coop_hold_fire','acquire_low_near','acquire_low_far','hunch_health','hunch_weapons',
          'hunch_ammo','hunch_armor','hunch_pack','hunch_inputs_isolated','hidden_weapon_family',
          'visible_weapon_family','hunch_cooldown','identity_and_rng']


def audit(source, control=None):
    combat = function(source, 'Argus_Combat')
    assert not re.search(r'(?:\be|self\.ar_enemy)\.(?:health|max_health|items|armorvalue|armortype|ammo_\w+|currentammo)\b',combat), 'combat reads opponent private state'
    perceive = function(source, 'Argus_Perceive')
    health = re.findall(r'\bb\.health\s*[^\n)]*',perceive)
    assert health == ['b.health > 0'], 'acquisition uses exact health beyond alive/dead'
    assert not re.search(r'\bb\.(?:max_health|items|armorvalue|armortype|ammo_\w+|currentammo)\b',perceive)
    assert perceive.index('if (ok && Argus_CanSee (b))') < perceive.index('b.super_damage_finished'), 'private cues affect pre-observation ordering'
    hunch = function(source,'Argus_Hunch')
    assert 'self = foe' not in hunch and 'Argus_ItemValue' not in hunch
    assert re.findall(r'\bfoe\.health\s*[^\n|]*',hunch) == ['foe.health <= 0 ']
    assert not re.search(r'\bfoe\.(?:items|armorvalue|armortype|ammo_\w+|currentammo|max_health|weapon)\b',hunch)
    assert 'self.ar_obsenemy == foe' in hunch and 'family = self.ar_threatclass;' in hunch
    assert 'sc = v * 320 / (vlen (d) + 160);' in hunch and 'bsc = 22;' in hunch
    value = function(source,'Argus_HunchValue')
    assert not re.search(r'\.(?:health|max_health|items|armorvalue|armortype|ammo_\w+|currentammo|weapon)\b',value)
    assert not re.search(r'\b(?:random|traceline|Argus_ItemValue)\s*\(',value)
    assert 'self.' not in value and 'foe.' not in value
    if control is not None:
        assert function(source,'Argus_DodgeScan') == function(control,'Argus_DodgeScan'), 'projectile recognition changed'
        assert function(source,'Argus_ItemValue') == function(control,'Argus_ItemValue'), 'own-item valuation changed'
    return dict(enemy_health_only_alive_dead=True,combat_private_reads_removed=True,
        hunch_uses_fixed_priors_and_observed_family=True,projectile_and_own_item_logic_unchanged=control is not None)


def check(text, map_name, ids, allow_failed=False):
    assert 'BHVRPL begin perception_inputs' in text and 'BHVFIX begin perception' in text
    active=None; rows=[]
    for line in text.splitlines():
        if not line.startswith('HIFIX '):continue
        w=line.split();kind=w[1]
        if kind=='begin':
            assert active is None and w[2:4]==[map_name,'id'] and len(w)==5
            active=dict(id=int(w[4]),labels=[],failures=[],ended=False,clean=False)
        elif kind=='check':
            assert active and not active['ended'] and len(w)==5 and int(w[2])==active['id'] and w[4] in ('0','1')
            active['labels'].append(w[3])
            if w[4]=='0':active['failures'].append(w[3])
        elif kind=='end':
            assert active and not active['ended'] and int(w[2])==active['id']
            assert len(w)==7 and w[3:6]==['checks',str(len(LABELS)),'ok']
            assert active['labels']==LABELS and w[6]==str(int(not active['failures']))
            active['ended']=True
        elif kind=='cleanup':
            assert active and active['ended'] and not active['clean']
            assert w[2:]==[str(active['id']),'restored','1'];active['clean']=True
        elif kind=='done':
            assert active and active['clean'] and w[2:]==[str(active['id'])]
            rows.append(active);active=None
        else:raise AssertionError('unknown health fixture record: '+line)
    assert active is None and [r['id'] for r in rows]==ids, 'missing/duplicate HIFIX trial'
    assert allow_failed or all(not r['failures'] for r in rows), 'HIFIX failed: '+str([r['failures'] for r in rows])
    return rows


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(audit((root/'src/argus.qc').read_text(),(root/'backups/perception-step1b/control-src/argus.qc').read_text())))
