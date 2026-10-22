import unittest

from tactic_review import review


class TestTacticReview(unittest.TestCase):
    def test_legacy_zero_phases_does_not_mean_zero_opportunities(self):
        result = review('ARGUS init on dm4\nARGEVT Romero spawned\n')
        self.assertEqual(result['map'], 'dm4')
        self.assertEqual(result['bots'], {})

    def test_ticks_are_separate_from_phases_and_hits(self):
        result = review('ARGUS init on dm2\nARGEVT Mr Elusive spawned\n'
                        'TACTICCHECK Mr Elusive t 1.2 stage evaluated\n'
                        'TACTICCHECK Mr Elusive t 1.2 stage eligible\n'
                        'TACTICCHECK Mr Elusive t 1.2 stage outside_start\n'
                        'ARGEVT Mr Elusive tactic prepare\n'
                        'ARGEVT Mr Elusive tactic returnshot\n')
        bot = result['bots']['Mr Elusive']
        self.assertEqual(bot['evaluation_ticks']['eligible'], 1)
        self.assertEqual(bot['phases']['returnshot'], 1)
        self.assertIsNone(bot['return_hits'])

    def test_actual_difficulty_and_aim_share_are_recorded(self):
        result = review('ARGUS init on dm4\n'
                        'ARGUS difficulty Romero t 12.5 base 1 cognition 2 aim 1.4 offset 0 drift 1 adaptive 1 aimshare_pct 35\n')
        self.assertEqual(result['difficulty'][0]['aimshare_pct'], 35)
        self.assertEqual(result['difficulty'][0]['aim'], 1.4)
        self.assertTrue(result['difficulty'][0]['adaptive'])


if __name__ == '__main__':
    unittest.main()
