"""Regression cases for misleading tactical acceptance tapes."""
import unittest

from check_tactic_fixture import check, require_sequence


def sample(t, *, z=-104, hidden=0, rockets=20, hp=5000, state=0):
    # The return point changes the opponent's view by more than 30 degrees.
    y = -151 if t >= 0.5 else -279
    return (f"TACFIX sample {t} pos '465 {y} {z}' hidden {hidden} "
            f"rockets {rockets} targethp {hp} hp 100 state {state}\n")


def stationary(*, return_hit=False, later_hit=False, third_at=1.4):
    events = "".join(f"ARGEVT Romero tactic {e}\n" for e in
                     ("prepare", "opening", "covered", "reappear", "returnshot"))
    return ("TACFIX begin dm4 case 0\n" + events
            + sample(0.0, state=1)
            + sample(0.1, rockets=19, state=2)
            + sample(0.3, hidden=1, rockets=19, state=3)
            + sample(0.5, rockets=19, state=4)
            + sample(0.6, rockets=18)
            + sample(0.8, rockets=18, hp=4900 if return_hit else 5000)
            + sample(third_at, rockets=17)
            + sample(third_at + 0.1, rockets=17, hp=4800 if later_hit else 5000)
            + sample(max(1.2, third_at + 0.2), rockets=17, hp=4800 if later_hit else 5000)
            + "TACFIX end\n")


class TestTacticFixture(unittest.TestCase):
    def test_hidden_departure_reads_only_independent_samples(self):
        text = ("TACFIX begin dm2 case 2\nTACFIX target_moved\n"
                "BHVDBG Carmack memory '0 0 0'\nARGEVT Romero tactic abort sight\n"
                + sample(0.1).rstrip() + " memory '2433 -183 24'\n"
                + "TACFIX end frames 60 seconds 6\n")
        self.assertTrue(check(text)[0]['interrupted'])
        with self.assertRaisesRegex(AssertionError, 'tracked a hidden departure'):
            check(text.replace("memory '2433 -183 24'", "memory '2209 -1687 24'"))

    def test_unlimited_ammo_uses_actual_projectile_counts(self):
        tape = stationary(return_hit=True)
        import re
        tape = re.sub(r"rockets (\d+)(.*?)state (\d+)",
                      lambda m: f"rockets 20{m[2]}state {m[3]} launches {20-int(m[1])}", tape)
        self.assertTrue(check(tape)[0]["return_damage"])

    def test_ammo_loss_without_projectile_cannot_credit_a_shot(self):
        tape = stationary(return_hit=True)
        import re
        tape = re.sub(r"state (\d+)", r"state \1 launches 0", tape)
        with self.assertRaisesRegex(AssertionError, "no actual opening rocket"):
            check(tape)

    def test_sequence_rejects_missing_duplicate_and_reordered_cases(self):
        for cases in ([0, 0, 1], [0, 0, 0, 1, 1, 2], [0, 0, 0, 2, 1]):
            with self.assertRaisesRegex(AssertionError, "case sequence mismatch"):
                require_sequence([{"case": str(c)} for c in cases], [0, 0, 0, 1, 2])

    def test_life_veto_result_belongs_to_its_own_trial(self):
        tape = "TACFIX begin dm4 case 14\nTACFIX lifeaccepted 1\n" + sample(0.1) + "TACFIX end\n"
        self.assertTrue(check(tape)[0]["lifeveto_checks"])
        bad = tape.replace("lifeaccepted 1", "lifeaccepted 0")
        with self.assertRaisesRegex(AssertionError, "failed-life GOAP"):
            check(tape + bad)

    def test_actual_return_damage(self):
        self.assertTrue(check(stationary(return_hit=True))[0]["return_damage"])

    def test_hull_control_is_nominal_and_requires_its_own_geometry_proof(self):
        hull = stationary(return_hit=True).replace('case 0', 'case 13')
        self.assertTrue(check('TACFIX hull ok\n' + hull)[0]['return_damage'])
        for bad in (hull, 'TACFIX hull FAILED\n' + hull, 'TACFIX hull ok\n' + hull + hull):
            with self.assertRaisesRegex(AssertionError, 'asymmetric hull proof'):
                check(bad)

    def test_stationary_dummy_cannot_retain_knockback(self):
        tape = stationary(return_hit=True).replace("state 1\n", "state 1 targetvel '180 0 0'\n")
        with self.assertRaisesRegex(AssertionError, "retained knockback velocity"):
            check(tape)

    def test_normal_combat_hit_cannot_rescue_return_miss(self):
        self.assertFalse(check(stationary(later_hit=True))[0]["return_damage"])

    def test_third_rocket_ends_damage_window(self):
        self.assertFalse(check(stationary(later_hit=True, third_at=0.9))[0]["return_damage"])

    def test_post_abort_fall_is_rejected(self):
        tape = ("TACFIX begin dm4 case 6\nARGEVT Romero tactic prepare\n"
                + sample(0.0, state=1) + sample(0.1, state=1)
                + "ARGEVT Romero tactic abort route\n"
                + sample(0.2, z=-106) + sample(0.6, z=-296)
                + sample(0.8, z=-296) + "TACFIX end\n")
        with self.assertRaisesRegex(AssertionError, "fell during or after"):
            check(tape)

    def test_safe_entry_rejection_is_valid(self):
        tape = ("TACFIX begin dm4 case 6\n" + sample(0.0)
                + sample(0.5) + sample(0.7) + "TACFIX end\n")
        self.assertTrue(check(tape)[0]["entry_rejected"])

    def test_refused_entry_allows_normal_upward_knockback(self):
        tape = ("TACFIX begin dm4 case 6\n" + sample(0.0)
                + sample(0.5, z=-92) + sample(0.7) + "TACFIX end\n")
        self.assertTrue(check(tape)[0]["entry_rejected"])

    def test_refused_entry_reports_ordinary_drop_without_a_safety_claim(self):
        tape = ("TACFIX begin dm4 case 6\n" + sample(0.0)
                + sample(0.5, z=-296) + sample(0.7) + "TACFIX end\n")
        result = check(tape)[0]
        self.assertTrue(result["ordinary_drop_after_rejection"])
        self.assertNotIn("moving_entry_safe", result)

    def test_unsampled_prepare_abort_cannot_count_as_refusal(self):
        tape = ("TACFIX begin dm4 case 6\nARGEVT Romero tactic prepare\n"
                + "ARGEVT Romero tactic abort route\n" + sample(0.1, z=-106)
                + sample(0.5, z=-296) + sample(0.7) + "TACFIX end\n")
        with self.assertRaisesRegex(AssertionError, "unobserved tactical ownership"):
            check(tape)

    def test_post_return_fall_is_rejected(self):
        tape = stationary().replace("pos '465 -151 -104' hidden 0 rockets 18",
                                    "pos '465 -151 -296' hidden 0 rockets 18")
        with self.assertRaisesRegex(AssertionError, "left walking surface"):
            check(tape)

    def test_incomplete_settling_window_is_rejected(self):
        tape = ("TACFIX begin dm4 case 6\n" + sample(0.0, state=1)
                + "ARGEVT Romero tactic abort route\n"
                + sample(0.2) + "TACFIX end\n")
        with self.assertRaisesRegex(AssertionError, "post-tactic observation"):
            check(tape)

    def test_missing_first_post_abort_sample_is_rejected(self):
        tape = ("TACFIX begin dm4 case 6\n" + sample(0.0, state=1)
                + sample(0.8, state=1) + "ARGEVT Romero tactic abort route\n"
                + "TACFIX end\n")
        with self.assertRaisesRegex(AssertionError, "post-tactic observation"):
            check(tape)


if __name__ == "__main__":
    unittest.main()
