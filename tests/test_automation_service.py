import unittest
from datetime import date

from anki_beeminder.config import AddonConfig
from anki_beeminder.services.automation_service import (
    AutomationService,
    TRIGGER_STARTUP,
    TRIGGER_SYNC,
)


class TestAutomationService(unittest.TestCase):
    def test_disabled_automation_never_runs(self) -> None:
        config = AddonConfig(automation_enabled=False, automation_triggers=[TRIGGER_SYNC])
        service = AutomationService()
        decision = service.should_run(config=config, trigger=TRIGGER_SYNC, day=date(2026, 2, 2))
        self.assertFalse(decision.should_run)

    def test_enabled_trigger_runs(self) -> None:
        config = AddonConfig(automation_enabled=True, automation_triggers=[TRIGGER_SYNC])
        service = AutomationService()
        decision = service.should_run(config=config, trigger=TRIGGER_SYNC, day=date(2026, 2, 2))
        self.assertTrue(decision.should_run)

    def test_non_configured_trigger_skips(self) -> None:
        config = AddonConfig(automation_enabled=True, automation_triggers=[TRIGGER_SYNC])
        service = AutomationService()
        decision = service.should_run(config=config, trigger=TRIGGER_STARTUP, day=date(2026, 2, 2))
        self.assertFalse(decision.should_run)

    def test_once_per_day_setting_does_not_block_remote_upsert_checks(self) -> None:
        config = AddonConfig(
            automation_enabled=True,
            automation_triggers=[TRIGGER_SYNC],
            automation_only_once_per_day=True,
            last_automation_sync_date="2026-02-02",
        )
        service = AutomationService()
        decision = service.should_run(config=config, trigger=TRIGGER_SYNC, day=date(2026, 2, 2))
        self.assertTrue(decision.should_run)

    def test_mark_ran_updates_config_date(self) -> None:
        config = AddonConfig(automation_enabled=True)
        service = AutomationService()
        updated = service.mark_ran(config=config, day=date(2026, 2, 2))
        self.assertEqual(updated.last_automation_sync_date, "2026-02-02")


if __name__ == "__main__":
    unittest.main()
