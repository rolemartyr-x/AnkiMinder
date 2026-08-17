import unittest

from ankiminder.config import MAX_HISTORICAL_LOOKBACK_DAYS, AddonConfig


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

    def test_excessive_lookback_days_clamped_to_max(self) -> None:
        """A huge one-time-backfill value is clamped, not rejected outright."""
        config = AddonConfig.from_dict({"historical_lookback_days": 10_000})
        self.assertEqual(config.historical_lookback_days, MAX_HISTORICAL_LOOKBACK_DAYS)

    def test_lookback_days_at_max_is_unclamped(self) -> None:
        config = AddonConfig.from_dict({"historical_lookback_days": MAX_HISTORICAL_LOOKBACK_DAYS})
        self.assertEqual(config.historical_lookback_days, MAX_HISTORICAL_LOOKBACK_DAYS)

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

    def test_completion_fields_default_when_absent(self) -> None:
        """Backward compat: pre-upgrade config.json files have none of these keys."""
        config = AddonConfig.from_dict({})
        self.assertEqual(config.review_completion_goal_slug, "")
        self.assertFalse(config.review_completion_sync_enabled)
        self.assertEqual(config.last_review_completion_sync_date, "")
        self.assertEqual(config.last_review_completion_value, -1)
        self.assertEqual(config.last_review_completion_datapoint_id, "")

    def test_non_numeric_last_review_completion_value_falls_back_to_default(self) -> None:
        config = AddonConfig.from_dict({"last_review_completion_value": "bogus"})
        self.assertEqual(config.last_review_completion_value, -1)

    def test_review_completion_sync_enabled_string_false_is_parsed_as_false(self) -> None:
        config = AddonConfig.from_dict({"review_completion_sync_enabled": "false"})
        self.assertFalse(config.review_completion_sync_enabled)

    def test_review_completion_sync_enabled_string_true_is_parsed_as_true(self) -> None:
        config = AddonConfig.from_dict({"review_completion_sync_enabled": "true"})
        self.assertTrue(config.review_completion_sync_enabled)

    def test_review_completion_sync_enabled_real_bool_unaffected(self) -> None:
        config = AddonConfig.from_dict({"review_completion_sync_enabled": True})
        self.assertTrue(config.review_completion_sync_enabled)
        config = AddonConfig.from_dict({"review_completion_sync_enabled": False})
        self.assertFalse(config.review_completion_sync_enabled)

    def test_review_completion_goal_slug_is_stripped(self) -> None:
        config = AddonConfig.from_dict({"review_completion_goal_slug": "  anki-completion  "})
        self.assertEqual(config.review_completion_goal_slug, "anki-completion")

    def test_to_dict_includes_new_completion_fields(self) -> None:
        config = AddonConfig(
            review_completion_goal_slug="anki-completion",
            review_completion_sync_enabled=True,
            last_review_completion_sync_date="2026-02-02",
            last_review_completion_value=1,
            last_review_completion_datapoint_id="dp-1",
        )
        data = config.to_dict()
        self.assertEqual(data["review_completion_goal_slug"], "anki-completion")
        self.assertTrue(data["review_completion_sync_enabled"])
        self.assertEqual(data["last_review_completion_sync_date"], "2026-02-02")
        self.assertEqual(data["last_review_completion_value"], 1)
        self.assertEqual(data["last_review_completion_datapoint_id"], "dp-1")

    def test_round_trip_through_to_dict_and_from_dict_is_stable(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            review_completion_goal_slug="anki-completion",
            review_completion_sync_enabled=True,
            automation_triggers=["sync"],
            last_review_completion_sync_date="2026-02-02",
            last_review_completion_value=1,
            last_review_completion_datapoint_id="dp-1",
        )
        round_tripped = AddonConfig.from_dict(config.to_dict())
        self.assertEqual(round_tripped, config)
        round_tripped_again = AddonConfig.from_dict(round_tripped.to_dict())
        self.assertEqual(round_tripped_again, round_tripped)


if __name__ == "__main__":
    unittest.main()
