"""test_playbook_sim.py — Unit tests for the HRP Playbook Simulation Engine."""

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = REPO_ROOT / "scripts" / "playbook_engine.py"


def load_engine():
    spec = importlib.util.spec_from_file_location("playbook_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module at {ENGINE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestActionEffectsTable(unittest.TestCase):
    """Verify the action effects table is well-formed."""

    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_all_actions_have_required_keys(self):
        for key, fx in self.eng.ALL_ACTIONS.items():
            self.assertIn("cond", fx, f"{key} missing 'cond'")
            self.assertIn("stam", fx, f"{key} missing 'stam'")
            self.assertIn("label", fx, f"{key} missing 'label'")

    def test_training_actions_exist(self):
        self.assertIn("TRAIN_STD", self.eng.TRAIN_ACTIONS)
        self.assertIn("TRAIN_HVY", self.eng.TRAIN_ACTIONS)
        self.assertEqual(len(self.eng.TRAIN_ACTIONS), 6)

    def test_work_actions_exist(self):
        self.assertIn("WORK_5F_B", self.eng.WORK_ACTIONS)
        self.assertIn("WORK_5F_H", self.eng.WORK_ACTIONS)
        self.assertEqual(len(self.eng.WORK_ACTIONS), 10)

    def test_race_effects_exist(self):
        self.assertIn("RACE_5F", self.eng.RACE_EFFECTS)
        self.assertIn("RACE_1M", self.eng.RACE_EFFECTS)


class TestDecayForAge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_2yo_decay(self):
        self.assertEqual(self.eng.decay_for_age("2"), 4.5)

    def test_3yo_decay(self):
        self.assertEqual(self.eng.decay_for_age("3"), 3.5)

    def test_4plus_decay(self):
        self.assertEqual(self.eng.decay_for_age("5"), 2.5)

    def test_string_with_yo(self):
        self.assertEqual(self.eng.decay_for_age("3yo"), 3.5)

    def test_bad_input_defaults_to_3(self):
        self.assertEqual(self.eng.decay_for_age("unknown"), 3.5)


class TestSimulate(unittest.TestCase):
    """Test the forward simulation engine."""

    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_rest_only_condition_drops(self):
        """With no actions, condition should drop over days."""
        fc, fs = self.eng.simulate(100.0, 100.0, 3.5, 5, {})
        self.assertLess(fc, 100.0, "Condition should drop with rest only")
        self.assertGreater(fs, 100.0, "Stamina should rise with rest only")

    def test_rest_only_math(self):
        """5 days rest for 3yo: C drops 3.5/day, S rises 10/day."""
        fc, fs = self.eng.simulate(100.0, 80.0, 3.5, 5, {})
        expected_c = 100.0 - (3.5 * 5)  # 82.5
        expected_s = min(110.0, 80.0 + (10.0 * 5))  # 110 capped
        self.assertAlmostEqual(fc, expected_c, places=1)
        self.assertAlmostEqual(fs, expected_s, places=1)

    def test_work_boosts_condition(self):
        """A 5f breeze on day 0 should boost condition."""
        fc_rest, _ = self.eng.simulate(90.0, 100.0, 3.5, 1, {})
        fc_work, _ = self.eng.simulate(90.0, 100.0, 3.5, 1, {0: "WORK_5F_B"})
        self.assertGreater(fc_work, fc_rest, "Work should boost condition vs rest")

    def test_work_costs_stamina(self):
        """A 5f breeze should drain stamina."""
        _, fs_rest = self.eng.simulate(100.0, 100.0, 3.5, 1, {})
        _, fs_work = self.eng.simulate(100.0, 100.0, 3.5, 1, {0: "WORK_5F_B"})
        self.assertLess(fs_work, fs_rest, "Work should cost stamina vs rest")

    def test_meters_capped_at_110(self):
        """Meters should never exceed 110."""
        fc, fs = self.eng.simulate(108.0, 108.0, 0.5, 1, {0: "TRAIN_HVY"})
        self.assertLessEqual(fc, 110.0)
        # Stamina could drop from heavy training
        self.assertGreaterEqual(fs, 0.0)

    def test_meters_floor_at_0(self):
        """Meters should never go below 0."""
        fc, fs = self.eng.simulate(5.0, 5.0, 10.0, 3, {})
        self.assertGreaterEqual(fc, 0.0)
        self.assertGreaterEqual(fs, 0.0)

    def test_training_actions_apply(self):
        """Standard training should boost condition."""
        fc, fs = self.eng.simulate(90.0, 100.0, 3.5, 1, {0: "TRAIN_STD"})
        # TRAIN_STD: cond +12, stam -10, then nightly: -3.5 cond, +10 stam
        expected_c = 90.0 + 12.0 - 3.5  # 98.5
        expected_s = 100.0 - 10.0 + 10.0  # 100.0
        self.assertAlmostEqual(fc, expected_c, places=1)
        self.assertAlmostEqual(fs, expected_s, places=1)


class TestSimulateDaily(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_returns_correct_days(self):
        daily = self.eng.simulate_daily(100.0, 100.0, 3.5, 5, {})
        self.assertEqual(len(daily), 5)
        for i, d in enumerate(daily):
            self.assertEqual(d["day"], i)

    def test_daily_has_action_label(self):
        daily = self.eng.simulate_daily(100.0, 100.0, 3.5, 3, {1: "WORK_5F_B"})
        self.assertEqual(daily[0]["action_label"], "Rest")
        self.assertEqual(daily[1]["action_label"], "5f Breeze")
        self.assertEqual(daily[2]["action_label"], "Rest")


class TestFindOptimalSchedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_returns_schedule_dict(self):
        schedule, fc, fs = self.eng.find_optimal_schedule(
            100.0, 100.0, 3.5, 5, "BEL"
        )
        self.assertIsInstance(schedule, dict)
        self.assertIsInstance(fc, float)
        self.assertIsInstance(fs, float)

    def test_zero_days_returns_empty(self):
        schedule, fc, fs = self.eng.find_optimal_schedule(
            100.0, 100.0, 3.5, 0, "BEL"
        )
        self.assertEqual(len(schedule), 0)

    def test_optimizer_finds_reasonable_solution(self):
        """Given 90 C / 100 S with 5 days, should find a plan
        that keeps meters in or near the 95-105 range."""
        schedule, fc, fs = self.eng.find_optimal_schedule(
            90.0, 100.0, 3.5, 5, "BEL"
        )
        # Should be above scratch threshold at minimum
        self.assertGreaterEqual(fc, 75.0)
        self.assertGreaterEqual(fs, 75.0)

    def test_farm_gets_training_actions(self):
        """Farm locations should produce training actions, not works."""
        schedule, _, _ = self.eng.find_optimal_schedule(
            85.0, 100.0, 3.5, 5, "MouWV"
        )
        for day, action in schedule.items():
            self.assertTrue(
                action.startswith("TRAIN_"),
                f"Farm action should be TRAIN_*, got {action}"
            )

    def test_track_gets_work_or_train_actions(self):
        """Track locations can produce both work and training actions."""
        schedule, _, _ = self.eng.find_optimal_schedule(
            85.0, 100.0, 3.5, 5, "BEL"
        )
        for day, action in schedule.items():
            self.assertTrue(
                action.startswith("WORK_") or action.startswith("TRAIN_"),
                f"Track action should be WORK_* or TRAIN_*, got {action}"
            )


class TestIsFarm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_farm_locations(self):
        self.assertTrue(self.eng.is_farm("MouWV"))
        self.assertTrue(self.eng.is_farm("Farm A"))

    def test_track_locations(self):
        self.assertFalse(self.eng.is_farm("BEL"))
        self.assertFalse(self.eng.is_farm("SAR"))
        self.assertFalse(self.eng.is_farm("TUP(CT)"))


class TestConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = load_engine()

    def test_good_range(self):
        total, note = self.eng.assess_consistency(1, 2)
        self.assertIn("good", note)

    def test_too_few(self):
        total, note = self.eng.assess_consistency(0, 0)
        self.assertIn("add", note)

    def test_too_many(self):
        total, note = self.eng.assess_consistency(5, 3)
        self.assertIn("too many", note)

    def test_no_change(self):
        total, note = self.eng.assess_consistency(3, 2)
        self.assertIn("no change", note)


if __name__ == "__main__":
    unittest.main()
