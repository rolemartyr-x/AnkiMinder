import unittest

from ankiminder.config import AddonConfig


class TestConfig(unittest.TestCase):
    def test_automation_defaults(self) -> None:
        config = AddonConfig.from_dict({})
        self.assertFalse(config.automation_enabled)
        self.assertEqual(config.automation_triggers, ["sync"])

    def test_triggers_accept_string(self) -> None:
        config = AddonConfig.from_dict({"automation_triggers": "startup"})
        self.assertEqual(config.automation_triggers, ["startup"])

    def test_non_numeric_timeout_falls_back_to_default(self) -> None:
        """A corrupted/hand-edited config must not crash add-on load."""
        config = AddonConfig.from_dict({"request_timeout_seconds": "not-a-number"})
        self.assertEqual(config.request_timeout_seconds, 10)

    def test_non_positive_timeout_falls_back_to_default(self) -> None:
        config = AddonConfig.from_dict({"request_timeout_seconds": 0})
        self.assertEqual(config.request_timeout_seconds, 10)
        config = AddonConfig.from_dict({"request_timeout_seconds": -5})
        self.assertEqual(config.request_timeout_seconds, 10)

    def test_non_numeric_lookback_days_falls_back_to_default(self) -> None:
        config = AddonConfig.from_dict({"historical_lookback_days": None})
        self.assertEqual(config.historical_lookback_days, 7)

    def test_negative_lookback_days_falls_back_to_default(self) -> None:
        config = AddonConfig.from_dict({"historical_lookback_days": -3})
        self.assertEqual(config.historical_lookback_days, 7)

    def test_non_numeric_last_review_count_value_falls_back_to_default(self) -> None:
        config = AddonConfig.from_dict({"last_review_count_value": "bogus"})
        self.assertEqual(config.last_review_count_value, -1)

    def test_string_false_is_parsed_as_false(self) -> None:
        """``bool("false")`` is True in plain Python -- config parsing must not do that."""
        config = AddonConfig.from_dict({"dry_run": "false", "automation_enabled": "false"})
        self.assertFalse(config.dry_run)
        self.assertFalse(config.automation_enabled)

    def test_string_true_is_parsed_as_true(self) -> None:
        config = AddonConfig.from_dict({"dry_run": "true", "automation_enabled": "true"})
        self.assertTrue(config.dry_run)
        self.assertTrue(config.automation_enabled)

    def test_real_bool_values_are_unaffected(self) -> None:
        config = AddonConfig.from_dict({"dry_run": False, "automation_enabled": True})
        self.assertFalse(config.dry_run)
        self.assertTrue(config.automation_enabled)


if __name__ == "__main__":
    unittest.main()
