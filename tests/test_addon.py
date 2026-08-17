"""Tests for the Anki UI glue layer (ankiminder.addon).

These tests inject fake main-window/task-manager objects so the dispatch
logic can be exercised without a real aqt/Anki runtime (which is not
available in this test environment) and without ever touching the network.
"""

import threading
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

import ankiminder.addon as addon_module
from ankiminder.addon import AddonApp
from ankiminder.exceptions import BeeminderError
from ankiminder.mocks.mock_client import MockBeeminderClient
from ankiminder.services.review_count_service import ReviewCountSyncService


class FakeAddonManager:
    """Minimal stand-in for Anki's addon config manager."""

    def __init__(self, config_dict: dict) -> None:
        self._config = dict(config_dict)
        self.saved: dict | None = None

    def getConfig(self, _name: str) -> dict:
        return dict(self._config)

    def writeConfig(self, _name: str, data: dict) -> None:
        self.saved = data
        self._config = dict(data)


class FakeDb:
    """Minimal stand-in for Anki's collection db, matching AnkiReviewCountSource."""

    def __init__(self, result: int = 0) -> None:
        self.result = result

    def scalar(self, _query: str, *_params: int) -> int:
        return self.result


class FakeTaskManager:
    """Records dispatched background work instead of running it inline.

    Recording (rather than immediately executing) `task`/`on_done` lets
    tests assert that work was *deferred* to the background instead of
    blocking the caller -- the exact bug this refactor fixes.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def run_in_background(self, task, on_done) -> None:
        self.calls.append((task, on_done))


class FakeFuture:
    """Minimal stand-in for the Future aqt's taskman hands to on_done."""

    def __init__(self, value=None, exc: Exception | None = None) -> None:
        self._value = value
        self._exc = exc

    def result(self):
        if self._exc is not None:
            raise self._exc
        return self._value


def make_config_dict(**overrides) -> dict:
    base = {
        "beeminder_username": "alice",
        "beeminder_auth_token": "token",
        "review_count_goal_slug": "anki-reviews",
        "dry_run": True,
        "historical_lookback_days": 1,
    }
    base.update(overrides)
    return base


def make_main_window(config_dict: dict, db_result: int = 3, has_collection: bool = True):
    col = SimpleNamespace(db=FakeDb(result=db_result)) if has_collection else None
    return SimpleNamespace(addonManager=FakeAddonManager(config_dict), col=col)


class TestAddonAppLayering(unittest.TestCase):
    def test_addon_module_never_imports_beeminder_client_directly(self) -> None:
        """UI code must go through the services layer, never the client layer."""
        self.assertNotIn("BeeminderClient", vars(addon_module))


class TestAddonAppDispatch(unittest.TestCase):
    def test_run_review_sync_dispatches_to_task_manager_without_blocking(self) -> None:
        fake_mw = make_main_window(make_config_dict())
        task_manager = FakeTaskManager()
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=task_manager)

        with mock.patch("ankiminder.addon.tooltip") as fake_tooltip:
            app._run_review_sync(is_automation=False)

            # The sync must be handed to the task manager, not executed
            # inline on the calling (main) thread.
            self.assertEqual(len(task_manager.calls), 1)
            fake_tooltip.assert_not_called()

            task, on_done = task_manager.calls[0]
            outcome = task()
            self.assertFalse(outcome.is_error)
            self.assertIn("total reviews", outcome.message)
            on_done(FakeFuture(value=outcome))

        fake_tooltip.assert_called_once()
        message = fake_tooltip.call_args.args[0]
        self.assertIn("total reviews", message)
        self.assertIn("Beeminder sync", message)

    def test_run_review_sync_falls_back_to_synchronous_without_task_manager(self) -> None:
        fake_mw = make_main_window(make_config_dict())
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=None)

        with mock.patch("ankiminder.addon.tooltip") as fake_tooltip:
            app._run_review_sync(is_automation=True)

        fake_tooltip.assert_called_once()
        message = fake_tooltip.call_args.args[0]
        self.assertIn("Beeminder auto-sync", message)

    def test_dispatch_surfaces_unexpected_future_errors(self) -> None:
        fake_mw = make_main_window(make_config_dict())
        task_manager = FakeTaskManager()
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=task_manager)

        received = []
        app._dispatch(lambda: None, lambda outcome: received.append(outcome))

        self.assertEqual(len(task_manager.calls), 1)
        _task, on_done = task_manager.calls[0]
        on_done(FakeFuture(exc=RuntimeError("boom")))

        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].is_error)
        self.assertIn("boom", received[0].message)

    def test_dispatch_fallback_without_task_manager_catches_unexpected_errors(self) -> None:
        """The no-task-manager fallback path must not let exceptions escape.

        Before the fix, `_dispatch` only caught unexpected errors on the
        background-thread (`future.result()`) path; the fallback path called
        `task()` directly, so a bug in `_perform_review_sync` would crash the
        caller instead of surfacing a tooltip.
        """
        fake_mw = make_main_window(make_config_dict())
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=None)

        def failing_task():
            raise RuntimeError("kaboom")

        received = []
        app._dispatch(failing_task, lambda outcome: received.append(outcome))

        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].is_error)
        self.assertIn("kaboom", received[0].message)

    def test_install_hooks_runs_startup_automation_through_task_manager(self) -> None:
        config_dict = make_config_dict(automation_enabled=True, automation_triggers=["startup"])
        fake_mw = make_main_window(config_dict)
        task_manager = FakeTaskManager()
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=task_manager)

        fake_gui_hooks = SimpleNamespace(
            sync_did_finish=SimpleNamespace(append=lambda *_a, **_k: None)
        )
        with mock.patch("ankiminder.addon.gui_hooks", fake_gui_hooks):
            app.install_hooks()

        # Startup automation must be dispatched to the background rather
        # than blocking add-on load on a synchronous Beeminder sync.
        self.assertEqual(len(task_manager.calls), 1)


class TestPerformReviewSync(unittest.TestCase):
    def test_reports_missing_collection(self) -> None:
        fake_mw = make_main_window(make_config_dict(), has_collection=False)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        outcome = app._perform_review_sync()

        self.assertTrue(outcome.is_error)
        self.assertIn("collection is not available", outcome.message)

    def test_dry_run_completes_without_error_or_network(self) -> None:
        """Dry run must never reach the Beeminder client (no `posted` results)."""
        fake_mw = make_main_window(make_config_dict(dry_run=True))
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        outcome = app._perform_review_sync()

        self.assertFalse(outcome.is_error)
        self.assertIn("total reviews", outcome.message)

    def test_concurrent_syncs_do_not_race_on_config(self) -> None:
        """Two syncs running on separate background threads must not race.

        Both threads call ``_perform_review_sync``, which loads, mutates,
        and saves the same config. Without a lock around that section, an
        automation trigger and a manual sync could interleave and one
        thread's saved config would silently clobber the other's. This
        instruments `ReviewCountSyncService.sync_date_range` to detect
        overlapping calls; without the fix, `max_active` would be 2.
        """
        fake_mw = make_main_window(make_config_dict(dry_run=True))
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        active = 0
        max_active = 0
        guard = threading.Lock()
        real_sync_date_range = ReviewCountSyncService.sync_date_range

        def instrumented_sync_date_range(self, *args, **kwargs):
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(max_active, active)
            try:
                return real_sync_date_range(self, *args, **kwargs)
            finally:
                with guard:
                    active -= 1

        with mock.patch.object(
            ReviewCountSyncService, "sync_date_range", instrumented_sync_date_range
        ):
            threads = [threading.Thread(target=app._perform_review_sync) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(max_active, 1)


class TestPerformReviewSyncCompletion(unittest.TestCase):
    def test_completion_disabled_by_default_only_numeric_sync_runs(self) -> None:
        fake_mw = make_main_window(make_config_dict(dry_run=True))
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        with mock.patch.object(
            ReviewCountSyncService, "sync_completion_date_range"
        ) as fake_completion_sync:
            outcome = app._perform_review_sync()

        fake_completion_sync.assert_not_called()
        self.assertFalse(outcome.is_error)
        self.assertNotIn("Completion:", outcome.message)

    def test_completion_enabled_with_goal_slug_runs_both_syncs_once(self) -> None:
        """Both syncs run and share a single config save -- no live network calls.

        ``ReviewCountSyncService.from_config`` normally builds a real
        ``BeeminderClient`` (real HTTP); it's patched here to build the
        service around ``MockBeeminderClient`` instead so this test never
        touches the network, per this repo's mocking rules.
        """
        config_dict = make_config_dict(
            dry_run=False,
            review_completion_sync_enabled=True,
            review_completion_goal_slug="anki-completion",
        )
        fake_mw = make_main_window(config_dict, db_result=1)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        mock_client = MockBeeminderClient()

        def fake_from_config(config, review_count_source):
            return ReviewCountSyncService(
                config=config, client=mock_client, review_count_source=review_count_source
            )

        with mock.patch.object(
            ReviewCountSyncService, "from_config", side_effect=fake_from_config
        ):
            outcome = app._perform_review_sync()

        self.assertFalse(outcome.is_error)
        self.assertIn("Completion:", outcome.message)

        goal_slugs_called = {call[1] for call in mock_client.calls}
        self.assertIn("anki-reviews", goal_slugs_called)
        self.assertIn("anki-completion", goal_slugs_called)

        saved = fake_mw.addonManager.saved
        self.assertIsNotNone(saved)
        self.assertEqual(saved["last_review_count_sync_date"], date.today().isoformat())
        self.assertEqual(saved["last_review_completion_sync_date"], date.today().isoformat())
        self.assertIn("last_review_completion_value", saved)
        self.assertIn("last_review_completion_datapoint_id", saved)

    def test_completion_enabled_but_goal_slug_empty_skips_completion(self) -> None:
        config_dict = make_config_dict(
            dry_run=True,
            review_completion_sync_enabled=True,
            review_completion_goal_slug="",
        )
        fake_mw = make_main_window(config_dict)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        with mock.patch.object(
            ReviewCountSyncService, "sync_completion_date_range"
        ) as fake_completion_sync:
            outcome = app._perform_review_sync()

        fake_completion_sync.assert_not_called()
        self.assertFalse(outcome.is_error)
        self.assertNotIn("Completion:", outcome.message)

    def test_completion_failure_surfaces_is_error_even_if_numeric_succeeds(self) -> None:
        """Numeric sync stays in dry-run (always "succeeds") so this test can
        exercise only the completion failure path without touching the
        network -- ``sync_completion_date_range`` is mocked directly below.
        """
        config_dict = make_config_dict(
            dry_run=True,
            review_completion_sync_enabled=True,
            review_completion_goal_slug="anki-completion",
        )
        fake_mw = make_main_window(config_dict, db_result=1)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        from ankiminder.services.review_count_service import DateRangeSyncResult

        failing_completion_result = DateRangeSyncResult(
            days_synced=0,
            days_skipped=0,
            days_failed=1,
            total_reviews=0,
            last_successful_date=None,
            last_successful_datapoint=None,
            message="1 failed.",
        )

        with mock.patch.object(
            ReviewCountSyncService,
            "sync_completion_date_range",
            return_value=failing_completion_result,
        ):
            outcome = app._perform_review_sync()

        self.assertTrue(outcome.is_error)

    def test_completion_beeminder_error_does_not_discard_numeric_config_save(self) -> None:
        """A ``BeeminderError`` *raised* by the completion phase (e.g. its
        unguarded prefetch call inside ``sync_completion_date_range``) must
        not propagate past the numeric phase's already-earned config save.

        Distinct from ``test_completion_failure_surfaces_is_error_even_if_numeric_succeeds``
        above, which only covers a *returned* failing result -- this covers
        an *exception* escaping the completion call, which previously
        propagated straight past ``if should_save: self._config_repo.save(config)``
        and silently discarded the numeric phase's save.
        """
        config_dict = make_config_dict(
            dry_run=True,
            review_completion_sync_enabled=True,
            review_completion_goal_slug="anki-completion",
        )
        fake_mw = make_main_window(config_dict, db_result=1)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        with mock.patch.object(
            ReviewCountSyncService,
            "sync_completion_date_range",
            side_effect=BeeminderError("bad completion goal slug"),
        ):
            outcome = app._perform_review_sync()

        self.assertTrue(outcome.is_error)
        self.assertIn("completion sync failed", outcome.message)

        # The numeric phase's own save must still have happened despite the
        # completion phase blowing up with an exception, not just a failing
        # result.
        saved = fake_mw.addonManager.saved
        self.assertIsNotNone(saved)
        self.assertEqual(saved["last_review_count_sync_date"], date.today().isoformat())
        # The completion phase never completed, so its metadata is untouched.
        self.assertEqual(saved["last_review_completion_sync_date"], "")


class TestShouldSaveGating(unittest.TestCase):
    """Regression coverage for `_perform_review_sync`'s two independent
    `should_save = True` triggers (numeric branch, completion branch).

    Verified manually: deleting either `should_save = True` line let all 75
    pre-existing tests pass -- neither branch's save trigger had any
    dedicated coverage. These tests fail if either trigger is removed.
    """

    def test_numeric_only_save_persists_numeric_fields(self) -> None:
        """Completion disabled; numeric sync produces skipped days.

        `.saved` must be populated with the numeric-phase fields -- this
        fails if the numeric branch's `should_save = True` is removed.
        """
        config_dict = make_config_dict(dry_run=True)
        fake_mw = make_main_window(config_dict, db_result=1)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        outcome = app._perform_review_sync()

        self.assertFalse(outcome.is_error)
        saved = fake_mw.addonManager.saved
        self.assertIsNotNone(saved)
        self.assertEqual(saved["last_review_count_sync_date"], date.today().isoformat())

    def test_completion_only_save_persists_when_numeric_sync_has_no_days(self) -> None:
        """Numeric goal slug unset so ``sync_date_range`` short-circuits with
        zero ``days_synced``/``days_skipped``, while completion sync (its own
        distinct goal slug) still runs and skips days in dry-run mode.

        `.saved` must still be populated with the completion-phase fields --
        this fails if the completion branch's `should_save = True` is
        removed, and proves the two triggers are genuinely independent
        rather than accidentally ANDed together.
        """
        config_dict = make_config_dict(
            dry_run=True,
            review_count_goal_slug="",
            default_goal_slug="",
            review_completion_sync_enabled=True,
            review_completion_goal_slug="anki-completion",
        )
        fake_mw = make_main_window(config_dict, db_result=1)
        app = AddonApp("ankiminder", main_window=fake_mw, task_manager=FakeTaskManager())

        outcome = app._perform_review_sync()

        self.assertFalse(outcome.is_error)
        saved = fake_mw.addonManager.saved
        self.assertIsNotNone(saved)
        self.assertEqual(saved["last_review_completion_sync_date"], date.today().isoformat())
        # The numeric phase never ran (no goal slug available), so its own
        # metadata must stay untouched.
        self.assertEqual(saved["last_review_count_sync_date"], "")


if __name__ == "__main__":
    unittest.main()
