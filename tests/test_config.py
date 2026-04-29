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

    def test_invalid_review_value_mode_falls_back_to_count(self) -> None:
        config = AddonConfig.from_dict({"review_value_mode": "weird-mode"})
        self.assertEqual(config.review_value_mode, "count")


if __name__ == "__main__":
    unittest.main()
