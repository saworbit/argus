"""Regression cases for misleading tactical acceptance tapes."""
import unittest

from check_tactic_fixture import check


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
    def test_actual_return_damage(self):
        self.assertTrue(check(stationary(return_hit=True))[0]["return_damage"])

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
