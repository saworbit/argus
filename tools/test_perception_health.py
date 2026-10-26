import tempfile
from pathlib import Path
import unittest
import hashlib

from check_health_fixture import audit, check, LABELS
from run_health_fixture import prepare, audit_private, body
from health_inventory_parked import candidate_source, parked_source

ROOT=Path(__file__).resolve().parents[1]


def tape(failed=False):
    lines=['BHVRPL begin perception_inputs','BHVFIX begin perception','HIFIX begin dm2 id 1']
    lines += [f'HIFIX check 1 {label} {int(not(failed and i==0))}' for i,label in enumerate(LABELS)]
    lines += [f'HIFIX end 1 checks 22 ok {int(not failed)}','HIFIX cleanup 1 restored 1','HIFIX done 1']
    return '\n'.join(lines)


class HealthTests(unittest.TestCase):
    def test_complete_and_old_code_failure_records(self):
        self.assertEqual(len(check(tape(),'dm2',[1])[0]['labels']),22)
        with self.assertRaises(AssertionError):check(tape(True),'dm2',[1])
        self.assertEqual(check(tape(True),'dm2',[1],allow_failed=True)[0]['failures'],['hidden_enter'])

    def test_incomplete_duplicate_reordered_or_dishonest_records_rejected(self):
        line='HIFIX check 1 hidden_enter 1'
        for bad in [tape().replace(line,''),tape().replace(line,line+'\n'+line),
                    tape().replace('own_stack','visible_weapon_family'),tape().replace('done 1','done 2'),
                    tape().replace('restored 1','restored 0'),tape().replace('HIFIX done 1',''),
                    tape(True).replace('checks 22 ok 0','checks 22 ok 1')]:
            with self.assertRaises(AssertionError):check(bad,'dm2',[1])
        with self.assertRaises(AssertionError):check(tape(),'dm4',[1])
        with self.assertRaises(AssertionError):check(tape(),'dm2',[1,2])

    def test_parked_candidate_boundary_and_mutations(self):
        source,_=candidate_source();self.assertTrue(audit(source,source)['combat_private_reads_removed'])
        for altered in [source.replace('if (ceff > 90','if (ceff > 90 || e.health < 30'),
                        source.replace('if (ceff > 90','if (ceff > 90 || self.ar_enemy.health < 30'),
                        source.replace('d = 2500 - d;', 'd = 2500 - d + b.health;'),
                        source.replace('v = Argus_HunchValue (it, cls, family);','self = foe; v = Argus_ItemValue (it, cls);'),
                        source.replace('if (c == "weapon_rocketlauncher") return 35;','if (it.ammo_rockets) return 35;')]:
            with self.assertRaises(AssertionError):audit(altered)

    def test_active_source_matches_declared_parked_state(self):
        _,manifest=candidate_source()
        source,_=parked_source()
        for name,expected in manifest['parked_functions'].items():
            self.assertEqual(hashlib.sha256(body(source,name)[1].encode()).hexdigest(),expected)

    def test_private_copy_inverse_and_production_rng(self):
        scratch=ROOT/'backups';scratch.mkdir(exist_ok=True)
        original=(ROOT/'src/defs.qc').read_bytes()
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            path=Path(folder)/'private';prepare(path,False)
            self.assertTrue(audit_private(path,False)['production_rng_builtin7'])
            with (path/'src/argus.qc').open('a') as f:f.write('\nfloat unintended_fixture_mutation;\n')
            with self.assertRaises(AssertionError):audit_private(path,False)
        self.assertEqual((ROOT/'src/defs.qc').read_bytes(),original)


if __name__=='__main__':unittest.main()
