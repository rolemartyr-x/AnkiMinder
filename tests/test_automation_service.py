import unittest
from datetime import date

from ankiminder.config import AddonConfig
from ankiminder.services.automation_service import (
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


if __name__ == "__main__":
    unittest.main()
