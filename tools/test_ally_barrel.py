"""Validate physical firing witnesses, including padded ftos and failed controls."""
import hashlib
import json
import re
from pathlib import Path
import unittest
from verify_ally_barrel import LABELS,inspect_fixture


def tape():
    return ('BHVRPL begin ally_barrel\nABFIX begin dt_ms 14 layout 1\n'+
        ''.join(f'ABFIX check {n} 1\n' for n in LABELS)+
        'ABFIX shot lagged_barrel_hold ammo 0 ally_damage 0 enemy_damage 0 aim_ally 0 barrel_ally 1 owned 1\n'
        'ABFIX shot aligned_shot ammo 1 ally_damage 0 enemy_damage 24 aim_ally 0 barrel_ally 0 owned 1\n'
        'ABFIX shot aim_only_ally ammo 1 ally_damage 0 enemy_damage 0 aim_ally 1 barrel_ally 0 owned 1\n'
        'ABFIX prefire coop_prefire_hold ammo 0 rockets 0 turn 1 limit   2.4 owned 1\n'
        'ABFIX prefire prefire_turn_hold ammo 0 rockets 0 turn   2.4 limit   2.4 owned 1\n'
        'ABFIX prefire aligned_prefire ammo 1 rockets 1 turn 1 limit   2.4 owned 1\n'
        'ABFIX end checks 8 failures 0\n')


class AllyBarrel(unittest.TestCase):
    def test_padded_turn_budgets_and_actual_emission(self):
        self.assertEqual(inspect_fixture(tape(),.0139)['failures'],[])

    def test_damage_cannot_be_hidden_by_a_success_marker(self):
        raw=tape().replace('lagged_barrel_hold ammo 0 ally_damage 0','lagged_barrel_hold ammo 1 ally_damage 24')
        with self.assertRaises(AssertionError):inspect_fixture(raw,.0139)
        raw=raw.replace('check lagged_barrel_hold 1','check lagged_barrel_hold 0').replace('failures 0','failures 1')
        self.assertEqual(inspect_fixture(raw,.0139)['failures'],['lagged_barrel_hold'])

    def test_invalid_premises_missing_witnesses_and_false_turn_budgets_rejected(self):
        good=tape()
        for raw in (good+good,good.replace('layout 1','layout 2'),
                good.replace('owned 1','owned 0'),good.replace('barrel_ally 1','barrel_ally 0'),
                good.replace('limit   2.4','limit 1000'),good.replace('ABFIX prefire aligned_prefire','missing'),
                good.replace('ABFIX check cleanup 1\n','')):
            with self.assertRaises(AssertionError):inspect_fixture(raw,.0139)

    def test_committed_physical_and_ordinary_identities(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/ally-barrel-v1.results.json').read_text(encoding='utf-8'))
        for artifact in proof['artifacts']:
            self.assertEqual(hashlib.sha256((root/artifact['path']).read_bytes()).hexdigest(),artifact['sha256'])
        for row in proof['physical']:
            result=inspect_fixture((root/row['raw']).read_text(encoding='utf-8'),row['ticrate'])
            self.assertEqual(result['failures'],row['failures'])
            self.assertEqual(bool(result['failures']),row['failed_control'])
        self.assertEqual(len(proof['ordinary']),12)
        for map_name in ('dm2','dm4'):
            for arm in ('control','candidate'):
                self.assertEqual(sorted(r['repeat'] for r in proof['ordinary']
                    if r['map']==map_name and r['arm']==arm),[1,2,3])
        for row in proof['ordinary']:
            self.assertEqual(row['source_sha256'],proof['protocol']['arms'][row['arm']]['source_sha256'])
            self.assertEqual(row['binary_sha256'],proof['protocol']['arms'][row['arm']]['binary_sha256'])
            initial={}
            text=(root/row['raw']).read_text(encoding='utf-8')
            for match in re.finditer(r'^ARGUS difficulty (.+?) t\s+[\d.]+ base\s+([\d.]+) cognition\s+([\d.]+)',text,re.M):
                initial.setdefault(match[1],(float(match[2]),float(match[3])))
            self.assertEqual(len(initial),3)
            self.assertEqual(set(initial.values()),{(2,2)})


if __name__=='__main__':unittest.main()
