"""Keep the navigation compiler's anchor promise aligned with real QC."""
from pathlib import Path
import re
import unittest

from argus_jump_anchor import LIMIT, audit, launch_distance, require_anchor


class JumpAnchor(unittest.TestCase):
    def test_strict_distance_bar_includes_height(self):
        self.assertLess(require_anchor((0, 0, 0), (95.999, 0, 0)), LIMIT)
        for point in [(96, 0, 0), (97, 0, 0), (95, 0, 16), (float('nan'), 0, 0)]:
            with self.subTest(point=point), self.assertRaisesRegex(ValueError, 'runtime requires'):
                require_anchor((0, 0, 0), point)

    def test_distance_uses_the_integer_seat_emitted_to_qc(self):
        self.assertEqual(launch_distance((.49, 0, 0), (96, 0, 0)), 96)
        with self.assertRaises(ValueError):
            require_anchor((.49, 0, 0), (96, 0, 0))

    def test_both_production_launch_sites_use_this_contract(self):
        source = (Path(__file__).resolve().parents[1] / 'src/argus.qc').read_text(encoding='utf-8')
        values = re.findall(r'vlen\s*\(\s*self\.origin\s*-\s*self\.ar_jumpfrom\.origin\s*\)\s*<\s*(\d+(?:\.\d+)?)', source)
        self.assertGreaterEqual(len(values), 2)
        self.assertEqual(set(map(float, values)), {LIMIT})

    def test_audit_distinguishes_refused_profile_from_unmodelled_direct_hop(self):
        nodes = [(0, 0, 0), (200, 0, 0), (0, 0, 100)]
        def gap(a, b):
            return ((96, 0, 0), b, (1, 0), 104) if b == nodes[1] else None
        result = audit(nodes, [(0, 1), (0, 2)], gap)
        self.assertEqual((result['profiled'], result['direct_or_fallback']), (1, 1))
        self.assertEqual(result['violations'][0]['source'], 0)
        self.assertEqual(result['violations'][0]['target'], 1)
        self.assertIsNone(result['links'][1]['admissible'])


if __name__ == '__main__':
    unittest.main()
