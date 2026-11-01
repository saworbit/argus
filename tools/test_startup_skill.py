"""Keep native initial-difficulty witnesses distinct from invalid old inputs."""
import hashlib
import json
from pathlib import Path
import re
import unittest


class StartupSkillEvidence(unittest.TestCase):
    def test_native_initial_roster_matches_declared_result(self):
        root=Path(__file__).resolve().parents[1]
        proof=json.loads((root/'runs/startup-skill-v1.results.json').read_text(encoding='utf-8'))
        self.assertEqual(len(proof['cases']),4)
        for row in proof['cases']:
            raw=(root/row['raw']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['raw_sha256'])
            initial={}
            for match in re.finditer(r'^ARGUS difficulty (.+?) t\s+[\d.]+ base\s+([\d.]+) cognition\s+([\d.]+) aim\s+([\d.]+)',raw.decode('utf-8'),re.M):
                initial.setdefault(match[1],tuple(float(match[i]) for i in (2,3,4)))
            self.assertEqual(set(initial),{'Carmack','Romero','Joe Rogan'})
            matches=all(v==(row['requested_skill'],)*3 for v in initial.values())
            self.assertEqual(matches,not row['invalid_control'])


if __name__=='__main__':unittest.main()
