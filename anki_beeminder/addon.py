"""Anki runtime integration (menus/hooks)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from .beeminder.client import BeeminderClient
from .config import ConfigRepository
from .exceptions import BeeminderError
from .services.automation_service import AutomationService, TRIGGER_STARTUP, TRIGGER_SYNC
from .services.review_count_service import (
    AnkiReviewCountSource,
    ReviewCountSyncService,
)
from .services.sync_service import SyncResult

try:
    from aqt import gui_hooks, mw
    from aqt.qt import QAction
    from aqt.utils import showInfo, showWarning
except ImportError:  # pragma: no cover - available inside Anki only
    gui_hooks = None
    mw = None
    QAction = None
    showInfo = print
    showWarning = print


class AddonApp:
    """Wires menu actions to service behavior."""

    def __init__(self, addon_module_name: str):
        if mw is None:
            raise RuntimeError("Anki main window is unavailable.")

        self._config_repo = ConfigRepository(mw.addonManager, addon_module_name)
        self._automation = AutomationService()

    def install_menu(self) -> None:
        if QAction is None or mw is None:
            return
        send_reviews_action = QAction("Send Today's Review Count to Beeminder", mw)
        send_reviews_action.triggered.connect(self._send_todays_review_count)
        mw.form.menuTools.addAction(send_reviews_action)

    def install_hooks(self) -> None:
        if gui_hooks is None:
            return
        gui_hooks.sync_did_finish.append(self._on_sync_did_finish)
        self._run_automation(trigger=TRIGGER_STARTUP)

    def _on_sync_did_finish(self, *_args, **_kwargs) -> None:
        self._run_automation(trigger=TRIGGER_SYNC)

    def _send_todays_review_count(self) -> None:
        self._run_review_sync(day=date.today(), is_automation=False)

    def _run_automation(self, trigger: str) -> None:
        config = self._config_repo.load()
        today = date.today()
        decision = self._automation.should_run(config=config, trigger=trigger, day=today)
        if not decision.should_run:
            return
        result = self._run_review_sync(day=today, is_automation=True)
        if result is not None and result.posted:
            updated = self._automation.mark_ran(config=self._config_repo.load(), day=today)
            self._config_repo.save(updated)

    def _run_review_sync(self, day: date, is_automation: bool) -> Optional[SyncResult]:
        config = self._config_repo.load()
        if mw is None or getattr(mw, "col", None) is None:
            if not is_automation:
                showWarning("Anki collection is not available.")
            return None

        goal_slug = config.review_count_goal_slug or config.default_goal_slug
        try:
            client = BeeminderClient(auth_token=config.beeminder_auth_token)
            count_source = AnkiReviewCountSource(mw.col.db)
            review_sync = ReviewCountSyncService(
                config=config,
                client=client,
                review_count_source=count_source,
            )
            result = review_sync.sync_day_total(day=day, goal_slug=goal_slug)
            if result.datapoint is not None:
                config.last_review_count_sync_date = day.isoformat()
                config.last_review_count_value = int(result.datapoint.value)
                config.last_review_count_datapoint_id = result.datapoint.id
                self._config_repo.save(config)
            if result.posted:
                if not is_automation:
                    showInfo(result.message)
            else:
                if not is_automation:
                    showWarning(result.message)
            return result
        except BeeminderError as error:
            showWarning(f"Beeminder sync failed: {error}")
        return None


APP_INSTANCE: Optional[AddonApp] = None


def initialize_addon(addon_module_name: str) -> None:
    """Entrypoint called from add-on root __init__.py."""

    global APP_INSTANCE
    if mw is None:
        return
    APP_INSTANCE = AddonApp(addon_module_name)
    APP_INSTANCE.install_menu()
    APP_INSTANCE.install_hooks()

