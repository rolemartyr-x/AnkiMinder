"""Anki runtime integration (menus/hooks)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from .beeminder.client import BeeminderClient
from .config import ConfigRepository
from .exceptions import BeeminderError
from .services.review_count_service import (
    AnkiReviewCountSource,
    ReviewCountSyncService,
)
from .services.sync_service import SyncService

try:
    from aqt import mw
    from aqt.qt import QAction
    from aqt.utils import showInfo, showWarning
except ImportError:  # pragma: no cover - available inside Anki only
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

    def install_menu(self) -> None:
        if QAction is None or mw is None:
            return
        send_reviews_action = QAction("Send Today's Review Count to Beeminder", mw)
        send_reviews_action.triggered.connect(self._send_todays_review_count)
        mw.form.menuTools.addAction(send_reviews_action)

    def _send_todays_review_count(self) -> None:
        config = self._config_repo.load()
        sync_day = date.today()

        goal_slug = config.review_count_goal_slug or config.default_goal_slug
        try:
            client = BeeminderClient(auth_token=config.beeminder_auth_token)
            sync_service = SyncService(config=config, client=client)
            count_source = AnkiReviewCountSource(mw.col.db)
            review_sync = ReviewCountSyncService(
                sync_service=sync_service,
                review_count_source=count_source,
            )
            result = review_sync.sync_day(day=sync_day, goal_slug=goal_slug)
            if result.posted:
                showInfo(result.message)
            else:
                showWarning(result.message)
        except BeeminderError as error:
            showWarning(f"Beeminder sync failed: {error}")


APP_INSTANCE: Optional[AddonApp] = None


def initialize_addon(addon_module_name: str) -> None:
    """Entrypoint called from add-on root __init__.py."""

    global APP_INSTANCE
    if mw is None:
        return
    APP_INSTANCE = AddonApp(addon_module_name)
    APP_INSTANCE.install_menu()

