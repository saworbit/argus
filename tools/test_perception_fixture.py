import unittest
from pathlib import Path
import tempfile

from run_perception_fixture import prepare, audit_private

from check_perception_fixture import audit, check, LABELS


def tape():
    records = ['BHVFIX begin perception', 'PERFIX begin dm4 id 1 ring 0']
    records += [f'PERFIX check 1 {label} 1' for label in LABELS]
    records += ['PERFIX end 1 checks 20 ok 1 frames 13 seconds 0.2 dt_ms 16 controlled',
                'PERFIX cleanup 1 restored 1', 'PERFIX done 1']
    return '\n'.join(records) + '\n'


class PerceptionTests(unittest.TestCase):
    def test_complete_directed_coverage(self):
        result = check(tape(), 'dm4', 0, [1])
        self.assertEqual(result[0]['dt_ms'], 16)
        self.assertEqual(len(result[0]['labels']), 20)

    def test_missing_duplicate_reordered_or_failed_checks_are_rejected(self):
        line = 'PERFIX check 1 hidden_pair 1\n'
        cases = [tape().replace(line, '', 1), tape().replace(line, line * 2, 1),
                 tape().replace('clock 1', 'clock 0'),
                 tape().replace('initial_observation 1', 'reacquired 1'),
                 tape().replace('PERFIX done 1', 'PERFIX done 2'),
                 tape().replace('PERFIX cleanup 1 restored 1', ''),
                 tape().replace('BHVFIX begin perception', ''),
                 tape().replace('dt_ms 16 controlled', 'dt_ms 0 controlled')]
        for bad in cases:
            with self.assertRaises(AssertionError):
                check(bad, 'dm4', 0, [1])
        for map_name, ring, ids in [('dm2', 0, [1]), ('dm4', 1, [1]), ('dm4', 0, [1, 2])]:
            with self.assertRaises(AssertionError):
                check(tape(), map_name, ring, ids)

    def test_production_observation_boundary(self):
        source = (Path(__file__).resolve().parents[1] / 'src/argus.qc').read_text()
        self.assertTrue(audit(source)['primary_live_reads_removed'])
        for altered in [source.replace('epos = Argus_EnemyPosition ();', 'epos = e.origin;'),
                        source.replace('aimpt_z = epos_z - 16;', 'aimpt_z = e.origin_z - 16;'),
                        source.replace('return self.ar_obsvelocity;', 'return self.ar_enemy.velocity;'),
                        source.replace('trace_ent = hit;', ''),
                        source.replace('// Occluded actors supply no cue,', 'if (e.invisible_finished > time) random ();\n    // Occluded actors supply no cue,'),
                        source.replace('self.ar_enemy = attacker;', 'self.ar_seen = time; self.ar_enemy = attacker;')]:
            with self.assertRaises(AssertionError):
                audit(altered)

    def test_private_inputs_never_change_production_rng_or_source(self):
        root = Path(__file__).resolve().parents[1]
        scratch = root / 'backups'; scratch.mkdir(exist_ok=True)
        original = (root / 'src/defs.qc').read_bytes()
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            path = Path(folder) / 'private'
            prepare(path, False)
            self.assertTrue(audit_private(path, False)['production_rng_builtin7'])
            with (path / 'src/argus.qc').open('a') as stream:
                stream.write('\nfloat unapproved_test_change;\n')
            with self.assertRaises(AssertionError):
                audit_private(path, False)
        self.assertEqual((root / 'src/defs.qc').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
