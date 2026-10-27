"""Strict native opener-chain contract receipts."""
import re
from check_perception_fixture import function

LABELS=['direct_button','button_needs_activation','moving_button_acknowledged',
        'latched_button_acknowledged','trigger_overlap_preserved',
        'touch_point_premise','direct_touch_trigger','notouch_is_not_a_touch_target',
        'ceiling_relay_uses_floor_button','logical_relay_uses_button','two_relays',
        'shoot_button_preserved','cycle_is_bounded','range_cap','ownership_unchanged','cleanup']
DIRECT_ONLY_FAILURES=['ceiling_relay_uses_floor_button','logical_relay_uses_button',
                      'two_relays','shoot_button_preserved']


def check(text,map_name):
    assert 'BHVRPL begin door_actuator' in text
    assert not any(s in text for s in ('Host_Error','Program error','runaway loop'))
    rows=[s for s in text.splitlines() if s.startswith('DAFIX ')]
    assert len(rows)==len(LABELS)+2 and rows[0]==f'DAFIX begin {map_name}'
    checks=re.findall(r'^DAFIX check (\w+) ([01])$',text,re.M)
    assert [label for label,_ in checks]==LABELS
    failures=[label for label,ok in checks if ok=='0']
    assert rows[-1]==f'DAFIX end checks {len(LABELS)} ok {int(not failures)}'
    return failures


def audit(source):
    helper=function(source,'Argus_DoorOpener')
    assert not re.search(r'\b(?:self|d|b|candidate)\.\w+\s*=(?!=)',helper),'opener lookup mutates gameplay fields'
    assert not re.search(r'\b(?:spawn|remove|walkmove|setorigin|random)\s*\(',helper)
    assert 'depth > 4' in helper and 'argus_door_search_budget <= 0' in helper
    assert 'argus_door_search_budget = argus_door_search_budget - 1;' in helper
    assert 'bd = 1024;' in helper and 'UseStandPoint (d)' in helper
    assert 'argus_door_search_budget = 32;' in function(source,'Argus_TakeDoor')
    assert 'b.state == STATE_BOTTOM' in function(source,'Argus_DoorPressed')
    assert 'if (!Argus_DoorPressed (self.ar_doorbtn))' in source
    return True
