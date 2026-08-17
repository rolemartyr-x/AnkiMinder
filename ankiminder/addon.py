"""Anki runtime integration (menus/hooks)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

from .config import AddonConfig, ConfigRepository
from .exceptions import BeeminderError
from .services.automation_service import AutomationService, TRIGGER_STARTUP, TRIGGER_SYNC
from .services.review_count_service import (
    AnkiReviewCountSource,
    DateRangeSyncResult,
    ReviewCountSyncService,
    dates_between,
)

try:
    from aqt import gui_hooks, mw
    from aqt.qt import QAction
    from aqt.utils import tooltip
except ImportError:  # pragma: no cover - available inside Anki only
    gui_hooks = None
    mw = None
    QAction = None

    def tooltip(message: str, period: int = 0, parent=None) -> None:  # type: ignore[no-redef]
        _ = (period, parent)
        print(message)


# Tooltip display durations, in milliseconds.
ERROR_TOOLTIP_MS = 6000
INFO_TOOLTIP_MS = 4000


@dataclass
class _SyncOutcome:
    """Result of a review-count sync, ready to hand back to the UI thread."""

    message: str
    is_error: bool


class AddonApp:
    """Wires menu actions to service behavior."""

    def __init__(
        self,
        addon_module_name: str,
        main_window: Any = None,
        task_manager: Any = None,
    ) -> None:
        window = main_window if main_window is not None else mw
        if window is None:
            raise RuntimeError("Anki main window is unavailable.")

        self._mw = window
        # Prefer an explicitly injected task manager (tests); otherwise use
        # the real main window's, if present.
        self._task_manager = (
            task_manager if task_manager is not None else getattr(window, "taskman", None)
        )
        self._config_repo = ConfigRepository(window.addonManager, addon_module_name)
        self._automation = AutomationService()
        # Guards `_perform_review_sync`'s config load-modify-save section: an
        # automation trigger and a manual sync can now run concurrently on
        # separate background threads, and without this lock a slower sync
        # could overwrite a faster one's saved config with stale values.
        self._sync_lock = threading.Lock()

    def install_menu(self) -> None:
        if QAction is None or self._mw is None:
            return
        send_reviews_action = QAction("Sync Review Counts to Beeminder", self._mw)
        send_reviews_action.triggered.connect(self._send_review_counts)
        self._mw.form.menuTools.addAction(send_reviews_action)

    def install_hooks(self) -> None:
        if gui_hooks is None:
            return
        gui_hooks.sync_did_finish.append(self._on_sync_did_finish)
        self._run_automation(trigger=TRIGGER_STARTUP)

    def _on_sync_did_finish(self, *_args, **_kwargs) -> None:
        self._run_automation(trigger=TRIGGER_SYNC)

    def _send_review_counts(self) -> None:
        self._run_review_sync(is_automation=False)

    def _run_automation(self, trigger: str) -> None:
        config = self._config_repo.load()
        today = date.today()
        decision = self._automation.should_run(config=config, trigger=trigger, day=today)
        if not decision.should_run:
            return
        self._run_review_sync(is_automation=True)

    def _run_review_sync(self, is_automation: bool) -> None:
        """Dispatch the (network-bound) review-count sync off the main thread.

        Beeminder calls are real HTTP requests. Running them inline here
        would block Anki's UI thread for the whole sync -- this previously
        happened on every startup and post-sync automation run, since
        ``install_hooks``/``_on_sync_did_finish`` call this synchronously
        from the main thread. The actual work happens in
        ``_perform_review_sync``, dispatched to ``mw.taskman`` to run on a
        background thread; only the final tooltip notification is marshaled
        back onto the main thread.
        """

        def task() -> _SyncOutcome:
            return self._perform_review_sync()

        def on_done(outcome: _SyncOutcome) -> None:
            self._notify(outcome.message, is_automation=is_automation, is_error=outcome.is_error)

        self._dispatch(task, on_done)

    def _dispatch(
        self,
        task: Callable[[], _SyncOutcome],
        on_done: Callable[[_SyncOutcome], None],
    ) -> None:
        """Run ``task`` via the task manager (if any) and hand its result to ``on_done``."""

        def _run_safely() -> _SyncOutcome:
            try:
                return task()
            except Exception as exc:  # unexpected error, must not crash the caller
                return _SyncOutcome(f"Unexpected error: {exc}", True)

        if self._task_manager is None:
            # No task manager available (e.g. used outside a live Anki
            # session); fall back to running synchronously rather than
            # dropping the work.
            on_done(_run_safely())
            return

        def _on_future_done(future: Any) -> None:
            try:
                outcome = future.result()
            except Exception as exc:  # unexpected error surfaced from the background thread
                outcome = _SyncOutcome(f"Unexpected error: {exc}", True)
            on_done(outcome)

        self._task_manager.run_in_background(_run_safely, _on_future_done)

    def _perform_review_sync(self) -> _SyncOutcome:
        """Run the Beeminder sync. Safe to call from a background thread.

        Holds `_sync_lock` for the whole load-modify-save section so an
        automation trigger and a manual sync running concurrently on
        separate background threads can't race and silently drop each
        other's saved config state.
        """
        with self._sync_lock:
            config = self._config_repo.load()
            if getattr(self._mw, "col", None) is None:
                return _SyncOutcome("Anki collection is not available.", True)

            goal_slug = config.review_count_goal_slug or config.default_goal_slug
            today = date.today()
            start = self._compute_sync_start(config, today)

            count_source = AnkiReviewCountSource(self._mw.col.db)
            review_sync = ReviewCountSyncService.from_config(
                config=config,
                review_count_source=count_source,
            )
            # Both the numeric and completion syncs cover the identical date
            # range; computing each day's revlog count once here and handing
            # it to both avoids querying the same day twice when completion
            # sync is enabled.
            review_counts = {
                day: count_source.count_reviews_for_day(day)
                for day in dates_between(start, today)
            }

            try:
                result: DateRangeSyncResult = review_sync.sync_date_range(
                    start=start,
                    end=today,
                    goal_slug=goal_slug,
                    precomputed_counts=review_counts,
                )
            except BeeminderError as error:
                return _SyncOutcome(f"Beeminder sync failed: {error}", True)

            should_save = False
            if result.last_successful_datapoint is not None:
                config.last_review_count_value = int(result.last_successful_datapoint.value)
                config.last_review_count_datapoint_id = result.last_successful_datapoint.id
            if result.days_synced > 0 or result.days_skipped > 0:
                config.last_review_count_sync_date = today.isoformat()
                should_save = True

            completion_message = ""
            completion_failed = False
            if config.review_completion_sync_enabled and config.review_completion_goal_slug:
                # Guarded independently of the numeric sync above: a failure
                # here (bad completion goal slug, a transient network error
                # during the completion prefetch, etc.) must not discard the
                # numeric phase's already-earned config save below.
                completion_result: DateRangeSyncResult | None
                try:
                    completion_result = review_sync.sync_completion_date_range(
                        start=start,
                        end=today,
                        goal_slug=config.review_completion_goal_slug,
                        precomputed_counts=review_counts,
                    )
                except BeeminderError as error:
                    completion_result = None
                    completion_message = f"completion sync failed: {error}"
                    completion_failed = True

                if completion_result is not None:
                    if completion_result.last_successful_datapoint is not None:
                        config.last_review_completion_value = int(
                            completion_result.last_successful_datapoint.value
                        )
                        config.last_review_completion_datapoint_id = (
                            completion_result.last_successful_datapoint.id
                        )
                    if completion_result.days_synced > 0 or completion_result.days_skipped > 0:
                        config.last_review_completion_sync_date = today.isoformat()
                        should_save = True
                    completion_message = completion_result.message
                    completion_failed = completion_result.days_failed > 0

            if should_save:
                self._config_repo.save(config)

            combined_message = (
                result.message
                if not completion_message
                else f"{result.message} Completion: {completion_message}"
            )
            is_error = result.days_failed > 0 or completion_failed
            return _SyncOutcome(combined_message, is_error)

    @staticmethod
    def _compute_sync_start(config: AddonConfig, today: date) -> date:
        """Determine the earliest date to sync."""
        max_lookback = config.historical_lookback_days
        earliest_allowed = today - timedelta(days=max_lookback)
        return earliest_allowed

    def _notify(self, message: str, is_automation: bool, is_error: bool = False) -> None:
        prefix = "Beeminder auto-sync" if is_automation else "Beeminder sync"
        full = f"{prefix}: {message}"
        period = ERROR_TOOLTIP_MS if is_error else INFO_TOOLTIP_MS
        tooltip(full, period=period, parent=self._mw)


APP_INSTANCE: AddonApp | None = None


def initialize_addon(addon_module_name: str) -> None:
    """Entrypoint called from add-on root __init__.py."""

    global APP_INSTANCE
    if mw is None:
        return
    APP_INSTANCE = AddonApp(addon_module_name)
    APP_INSTANCE.install_menu()
    APP_INSTANCE.install_hooks()
