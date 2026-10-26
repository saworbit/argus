import tempfile
import unittest
from pathlib import Path

from run_behaviour_replay import ROOT, audit_private, compare, extract, prepare


TAPE = '''BHVRPL begin dm2 seed 113
ARGEVT Test spawned
ARGLOG Test t 61 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 1 hp 100 frg 0
BHVRPL end frames 3842 calls 100
BHVRPL dump_begin
2 entities
EDICT 0:
bhvrng_calls 100
bhvrng_state 200
EDICT 1:
ar_goals 1
ar_bd_valid 1
BHVRPL dump_end
'''


class ReplayTests(unittest.TestCase):
    def test_only_diagnostic_entity_fields_are_excluded(self):
        original = extract(TAPE, 'dm2', 113)
        compare(original, extract(TAPE.replace('ar_bd_valid 1', 'ar_bd_valid 0'), 'dm2', 113))
        compare(original, extract(TAPE.replace('dump_begin\n', 'dump_begin \n').replace('dump_end\n', 'dump_end \n'), 'dm2', 113))
        for old, new in [('gl 1', 'gl 0'), ('ar_goals 1', 'ar_goals 0'),
                         ('ar_goals 1', ''),
                         ('bhvrng_state 200', 'bhvrng_state 201')]:
            with self.subTest(new=new), self.assertRaises(AssertionError):
                compare(original, extract(TAPE.replace(old, new), 'dm2', 113))

    def test_missing_wrong_and_incomplete_replays_fail(self):
        for text in (TAPE.replace('frames 3842', 'frames 3841'),
                     TAPE.replace('seed 113', 'seed 114'),
                     TAPE.replace('seed 113', 'seed 1130'),
                     TAPE.replace('BHVRPL dump_end', ''),
                     TAPE.replace('bhvrng_calls 100', ''),
                     TAPE.replace('2 entities', '601 entities'),
                     TAPE + 'Host_Error: Program error\n',
                     TAPE + 'BHVRPL end frames 3842 calls 100\n',
                     TAPE + 'BHVRPL dump_end\n',
                     TAPE + 'BHVRPL begin dm2 seed 114\n'):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                extract(text, 'dm2', 113)

    def test_private_fixture_never_edits_production_source(self):
        paths = ('defs.qc', 'progs.src', 'argus.qc', 'world.qc')
        before = {p: (ROOT / 'src' / p).read_bytes() for p in paths}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'private'
            prepare(folder)
            audit_private(folder, ROOT / 'src')
            self.assertIn('behaviour_replay_inputs.qc', (folder / 'src/progs.src').read_text())
            self.assertNotIn('= #7;', (folder / 'src/defs.qc').read_text())
            path = folder / 'src/argus.qc'
            path.write_text(path.read_text() + '\n// unexpected edit\n')
            with self.assertRaises(AssertionError):
                audit_private(folder, ROOT / 'src')
        self.assertEqual(before, {p: (ROOT / 'src' / p).read_bytes() for p in paths})
        self.assertNotIn('behaviour_replay_inputs.qc', (ROOT / 'src/progs.src').read_text())


if __name__ == '__main__':
    unittest.main()
