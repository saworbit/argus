import re
from check_perception_fixture import function

LABELS=['wall_geometry','clear_geometry','overhang_geometry','ordinary_wall',
    'ordinary_overhang','ordinary_clear','wall_behind_target','shotgun_unchanged',
    'grenade_unchanged','tactical_full_reach','tactical_settle','tactical_abort',
    'tactical_clear','cleanup']

def check(text):
    assert 'BHVRPL begin muzzle_fixture' in text
    assert sum(line.startswith('MFIX ') for line in text.splitlines())==len(LABELS)+2
    assert len(re.findall(r'^MFIX begin dm4 dt_ms [\d.]+$',text,re.M))==1
    checks=re.findall(r'^MFIX check (\w+) ([01])$',text,re.M)
    assert [label for label,_ in checks]==LABELS,'missing/duplicate/reordered fixture checks'
    failures=[label for label,ok in checks if ok=='0']
    assert re.findall(r'^MFIX end checks 14 ok ([01])$',text,re.M)==[str(int(not failures))]
    return failures

def audit(source):
    combat=function(source,'Argus_Combat')
    assert combat.count('if (!Argus_MuzzleClear (aimpt))\n            return TRUE;')==1
    # Prefire has its own planned-line and barrel gates. Check the ordinary
    # trigger locally so an earlier facing assignment cannot satisfy its order.
    trigger=combat.split('if (self.ar_tactic == 2 || self.ar_tactic == 3)',1)[1]
    assert trigger.index('self.v_angle_y = self.angles_y;')<trigger.index('Argus_MuzzleClear (aimpt)')<trigger.index('Argus_TriggerReady ()')<trigger.rindex('W_Attack ();')
    helper=function(source,'Argus_MuzzleClear')
    assert 'if (!self.ar_tactic && self.weapon != IT_ROCKET_LAUNCHER)' in helper
    assert 'targetdist = vlen (aimpt - src);' in helper
    assert 'if (targetdist < reach) reach = targetdist;' in helper
    assert 'self.ar_tactic == 4 && time > self.ar_tactic_progress + 0.4' in helper
    assert 'Argus_TacticAbort ("abort muzzle")' in helper
    assert not re.search(r'(?:velocity|ar_moveyaw|ammo_\w+|health)\s*=',helper)
    return True
