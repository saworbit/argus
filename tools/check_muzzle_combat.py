"""Strict actual-combat-trigger receipts, separate from gameplay evidence."""
import re
import math
from argus_validation import require

LABELS=['geometry','combat_blocked','combat_clear','combat_backdrop','embedded_contract','cleanup']


def check(text):
    require('BHVRPL begin muzzle_combat' in text)
    require(not any(s in text for s in ('Host_Error','Program error','runaway loop')))
    lines=[s for s in text.splitlines() if s.startswith('MCFIX ')]
    require(len(lines)==12 and lines[0]=='MCFIX begin dm4','incomplete/duplicate combat receipt')
    checks=re.findall(r'^MCFIX check (\w+) ([01])$',text,re.M)
    require([k for k,_ in checks]==LABELS,'missing/reordered combat coverage')
    failures=[k for k,v in checks if v=='0']
    require(lines[-1]==f'MCFIX end checks 6 ok {int(not failures)}')
    outcomes=re.findall(r'^MCFIX outcome (\w+) gates (\d+) ammo (\d+) rockets (\d+) motor ([\d.-]+)$',text,re.M)
    require([r[0] for r in outcomes]==LABELS[1:4])
    require(all(r[1]=='1' for r in outcomes),'did not reach the actual trigger')
    require(all(math.isfinite(float(r[4])) for r in outcomes),'invalid movement request')
    for label,_,ammo,rockets,_ in outcomes:
        expected='0' if label=='combat_blocked' else '1'
        if ammo!=expected or rockets!=expected:
            require(label in failures,'check contradicts emitted ammo/projectile evidence')
    embedded=re.findall(r'^MCFIX embedded fraction ([\d.]+) startsolid ([01]) allsolid ([01]) allowed ([01])$',text,re.M)
    require(len(embedded)==1 and embedded[0][1]=='1','missing embedded-muzzle observation')
    return dict(failures=failures,outcomes=outcomes,embedded=embedded[0])
