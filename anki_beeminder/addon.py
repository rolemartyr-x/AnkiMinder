"""Anki runtime integration (menus/hooks)."""

from __future__ import annotations

from typing import Optional

from anki_beeminder.beeminder.client import BeeminderClient
from anki_beeminder.config import ConfigRepository
from anki_beeminder.exceptions import BeeminderError
from anki_beeminder.services.sync_service import SyncService

try:
    from aqt import mw
    from aqt.qt import QAction, QInputDialog
    from aqt.utils import showInfo, showWarning
except ImportError:  # pragma: no cover - available inside Anki only
    mw = None
    QAction = None
    QInputDialog = None
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
        action = QAction("Send Value to Beeminder...", mw)
        action.triggered.connect(self._send_value_prompt)
        mw.form.menuTools.addAction(action)

    def _send_value_prompt(self) -> None:
        config = self._config_repo.load()
        value, accepted = QInputDialog.getDouble(
            mw,
            "Beeminder Sync",
            "Value to send:",
            1.0,
            -1_000_000.0,
            1_000_000.0,
            2,
        )
        if not accepted:
            return

        try:
            client = BeeminderClient(auth_token=config.beeminder_auth_token)
            service = SyncService(config=config, client=client)
            result = service.send_value(value=value, comment="Manual sync from Anki add-on")
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

