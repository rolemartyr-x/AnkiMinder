import unittest

from anki_beeminder.config import AddonConfig


class TestConfig(unittest.TestCase):
    def test_automation_defaults(self) -> None:
        config = AddonConfig.from_dict({})
        self.assertFalse(config.automation_enabled)
        self.assertEqual(config.automation_triggers, ["sync"])
        self.assertFalse(config.automation_only_once_per_day)

    def test_triggers_accept_string(self) -> None:
        config = AddonConfig.from_dict({"automation_triggers": "startup"})
        self.assertEqual(config.automation_triggers, ["startup"])


if __name__ == "__main__":
    unittest.main()
