"""Automation policy for running daily review-count sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type

from ..config import AddonConfig

TRIGGER_SYNC = "sync"
TRIGGER_STARTUP = "startup"


@dataclass
class AutomationDecision:
    """Represents whether automation should run for this trigger."""

    should_run: bool
    reason: str


class AutomationService:
    """Evaluates trigger policy and updates sync metadata."""

    def should_run(self, config: AddonConfig, trigger: str, day: date_type) -> AutomationDecision:
        if not config.automation_enabled:
            return AutomationDecision(False, "Automation is disabled.")

        normalized_trigger = trigger.strip().lower()
        configured_triggers = {item.strip().lower() for item in (config.automation_triggers or [])}
        if normalized_trigger not in configured_triggers:
            return AutomationDecision(
                False,
                f"Trigger '{normalized_trigger}' is not enabled in automation_triggers.",
            )

        return AutomationDecision(True, "Ready to run.")

    def mark_ran(self, config: AddonConfig, day: date_type) -> AddonConfig:
        config.last_automation_sync_date = day.isoformat()
        return config
