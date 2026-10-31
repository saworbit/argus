"""Decision receipts must retain controls, visibility and cadence guards."""
import unittest
from pathlib import Path

from check_health_fixture import audit as audit_health
from verify_target_attention import LABELS, LEGACY_FAILURES, inspect_fixture, audit_target_value


def receipt(legacy=False, ms=14):
    failures = LEGACY_FAILURES if legacy else set()
    return ('ARGUS init on dm6\nBHVRPL begin target_attention\n'
        + f'ATFIX begin dt_ms {ms}\n'
        + ''.join(f'ATFIX check {name} {int(name not in failures)}\n' for name in LABELS)
        + f'ATFIX end checks {len(LABELS)} failures {len(failures)}\n')


class AttentionContracts(unittest.TestCase):
    def test_candidate_and_declared_negative_control_at_both_rates(self):
        for legacy in (False, True):
            for rate, ms in ((.0139, 14), (.1, 100)):
                row = inspect_fixture(receipt(legacy, ms), 'dm6', rate, legacy)
                self.assertEqual(set(row['failures']), LEGACY_FAILURES if legacy else set())

    def test_missing_duplicate_quarantine_and_rate_cannot_pass(self):
        good = receipt()
        for text in (good + good, good.replace('BHVRPL begin target_attention', ''),
                     good.replace('ATFIX check hidden_attacker_not_seen 1\n', ''),
                     good.replace('secondary_is_not_primary', 'goal_retained'),
                     receipt(ms=100), good + 'Program error\n'):
            with self.subTest(text=text):
                with self.assertRaises(AssertionError):
                    inspect_fixture(text, 'dm6', .0139)

    def test_partial_or_unexpected_control_failure_cannot_pass(self):
        for text in (receipt(), receipt(True).replace('goal_retained 1', 'goal_retained 0'),
                     receipt(True).replace('failures 3', 'failures 0')):
            with self.assertRaises(AssertionError):
                inspect_fixture(text, 'dm6', .0139, True)

    def test_target_utility_has_no_live_opponent_fields_or_randomness(self):
        source = (Path(__file__).resolve().parents[1] / 'src/argus.qc').read_text()
        audit_health(source)
        self.assertTrue(audit_target_value(source)['utility_deterministic'])
        # A hidden-opponent read is rejected even if a later edit moves it
        # into the new helper instead of the older perception body.
        leaked = source.replace('value = 2500 - distance;',
                                'value = 2500 - distance + foe.health;')
        with self.assertRaisesRegex(AssertionError, 'live opponent fields'):
            audit_target_value(leaked)


if __name__ == '__main__':
    unittest.main()
