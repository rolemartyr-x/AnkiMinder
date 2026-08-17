import unittest
from datetime import date

from ankiminder.beeminder.client import BeeminderClient
from ankiminder.beeminder.models import CreateDatapointRequest
from ankiminder.config import AddonConfig
from ankiminder.exceptions import BeeminderError
from ankiminder.mocks.mock_client import MockBeeminderClient
from ankiminder.services.review_count_service import (
    AnkiReviewCountSource,
    DateRangeSyncResult,
    ReviewCountSyncService,
    day_bounds_epoch_millis,
    request_id_for_completion_day,
    request_id_for_day,
)


class FakeDb:
    def __init__(self, result=None, list_result=None):
        self.result = result
        self.list_result = list_result or []
        self.last_query = None
        self.last_params = None

    def scalar(self, query, *params):
        self.last_query = query
        self.last_params = params
        return self.result

    def list(self, query, *params):
        self.last_query = query
        self.last_params = params
        return self.list_result


class FakeReviewCountSource:
    def __init__(self, count):
        self.count = count

    def count_reviews_for_day(self, _day):
        return self.count


class FakeReviewCountSourceWithHistory:
    """Fake source returning explicit counts by date."""

    def __init__(self, counts_by_date):
        self.counts_by_date = counts_by_date

    def count_reviews_for_day(self, day):
        return self.counts_by_date.get(day, 0)


class TestReviewCountService(unittest.TestCase):
    def test_day_bounds_epoch_millis_is_ordered(self) -> None:
        start_ms, end_ms = day_bounds_epoch_millis(date(2026, 2, 2))
        self.assertLess(start_ms, end_ms)
        self.assertEqual(end_ms - start_ms, 86_400_000)

    def test_anki_review_count_source_queries_revlog(self) -> None:
        fake_db = FakeDb(result=17)
        source = AnkiReviewCountSource(db=fake_db)
        count = source.count_reviews_for_day(date(2026, 2, 2))
        self.assertEqual(count, 17)
        self.assertIn("FROM revlog", fake_db.last_query)
        self.assertEqual(len(fake_db.last_params), 2)

    def test_sync_day_creates_datapoint_when_missing(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=FakeReviewCountSource(count=42),
        )
        result = service.sync_day_total(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            client.calls[0][2].requestid,
            request_id_for_day(date(2026, 2, 2), "anki-reviews"),
        )

    def test_sync_day_updates_existing_datapoint(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        existing = client.create_datapoint(
            username="alice",
            goal_slug="anki-reviews",
            request=CreateDatapointRequest(value=10.0, comment="existing"),
        )
        existing.daystamp = "20260202"
        existing.timestamp = 1738454400
        existing.requestid = request_id_for_day(date(2026, 2, 2), "anki-reviews")
        client.stored[existing.id] = existing
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=FakeReviewCountSource(count=14),
        )
        result = service.sync_day_total(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.updated_calls), 1)
        self.assertEqual(client.updated_calls[0][2], existing.id)
        self.assertEqual(client.updated_calls[0][3].value, 14.0)

    def test_sync_day_skips_when_todays_beeminder_value_matches(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        existing = client.create_datapoint(
            username="alice",
            goal_slug="anki-reviews",
            request=CreateDatapointRequest(value=42.0, comment="existing"),
        )
        existing.daystamp = "20260202"
        existing.timestamp = 1738454400
        existing.value = 42.0
        existing.requestid = request_id_for_day(date(2026, 2, 2), "anki-reviews")
        client.stored[existing.id] = existing
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=FakeReviewCountSource(count=42),
        )
        result = service.sync_day_total(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(client.updated_calls), 0)

    def test_sync_day_creates_when_local_cache_exists_but_beeminder_missing(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            last_review_count_sync_date="2026-02-02",
            last_review_count_value=42,
            last_review_count_datapoint_id="deleted-remote-id",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=FakeReviewCountSource(count=42),
        )
        result = service.sync_day_total(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(client.updated_calls), 0)


class TestFromConfig(unittest.TestCase):
    def test_builds_client_from_config_auth_token(self) -> None:
        """``from_config`` must be the only place addon.py needs to build a client."""
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="  secret-token  ",
            review_count_goal_slug="anki-reviews",
        )
        source = FakeReviewCountSource(count=0)
        service = ReviewCountSyncService.from_config(config=config, review_count_source=source)

        self.assertIsInstance(service.client, BeeminderClient)
        self.assertEqual(service.client._auth_token, "secret-token")
        self.assertEqual(service.config, config)
        self.assertIs(service.review_count_source, source)


class TestSyncDateRange(unittest.TestCase):

    def _make_service(self, counts_by_date, dry_run=False):
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=dry_run,
        )
        client = MockBeeminderClient()
        source = FakeReviewCountSourceWithHistory(counts_by_date)
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=source,
        )
        return service, client

    def test_sync_date_range_creates_only_days_with_reviews(self) -> None:
        counts = {
            date(2026, 2, 1): 10,
            date(2026, 2, 3): 25,
            date(2026, 2, 5): 7,
        }
        service, client = self._make_service(counts)
        result = service.sync_date_range(
            start=date(2026, 1, 30),
            end=date(2026, 2, 6),
        )
        self.assertEqual(result.days_synced, 3)
        self.assertEqual(result.days_skipped, 5)
        self.assertEqual(result.days_failed, 0)
        self.assertEqual(result.total_reviews, 42)
        self.assertEqual(result.last_successful_date, date(2026, 2, 5))
        self.assertEqual(len(client.calls), 3)

    def test_sync_date_range_skips_zero_day(self) -> None:
        counts = {
            date(2026, 2, 1): 10,
        }
        service, client = self._make_service(counts)
        result = service.sync_date_range(
            start=date(2026, 2, 1),
            end=date(2026, 2, 3),
        )
        self.assertEqual(result.days_synced, 1)
        self.assertEqual(len(result.per_day_results), 3)
        self.assertIn("2026-02-01", result.per_day_results)
        self.assertIn("2026-02-02", result.per_day_results)
        self.assertIn("2026-02-03", result.per_day_results)
        self.assertIn("No reviews on 2026-02-02", result.per_day_results["2026-02-02"].message)
        self.assertEqual(len(client.calls), 1)

    def test_sync_date_range_all_zero_reviews_skips_all(self) -> None:
        service, client = self._make_service({})
        result = service.sync_date_range(
            start=date(2026, 2, 1),
            end=date(2026, 2, 6),
        )
        self.assertEqual(result.days_synced, 0)
        self.assertEqual(result.days_skipped, 6)
        self.assertEqual(result.total_reviews, 0)
        self.assertEqual(len(client.calls), 0)

    def test_sync_date_range_skips_already_synced(self) -> None:
        counts = {date(2026, 2, 1): 10}
        service, client = self._make_service(counts)
        # Pre-populate a matching datapoint in the mock client.
        existing = client.create_datapoint(
            username="alice",
            goal_slug="anki-reviews",
            request=CreateDatapointRequest(value=10.0, comment="existing"),
        )
        existing.daystamp = "20260201"
        existing.requestid = request_id_for_day(date(2026, 2, 1), "anki-reviews")
        client.stored[existing.id] = existing

        result = service.sync_date_range(
            start=date(2026, 2, 1),
            end=date(2026, 2, 1),
        )
        self.assertEqual(result.days_synced, 0)
        self.assertEqual(result.days_skipped, 1)

    def test_sync_date_range_missing_config(self) -> None:
        config = AddonConfig(beeminder_username="", dry_run=False)
        client = MockBeeminderClient()
        source = FakeReviewCountSourceWithHistory({})
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)
        result = service.sync_date_range(start=date(2026, 2, 1), end=date(2026, 2, 6))
        self.assertEqual(result.days_synced, 0)
        self.assertIn("required", result.message)

    def test_sync_date_range_dry_run(self) -> None:
        counts = {date(2026, 2, 1): 10, date(2026, 2, 2): 5}
        service, client = self._make_service(counts, dry_run=True)
        result = service.sync_date_range(start=date(2026, 2, 1), end=date(2026, 2, 3))
        # dry_run: nothing posted
        self.assertEqual(result.days_synced, 0)
        self.assertEqual(result.days_skipped, 3)
        self.assertEqual(result.total_reviews, 15)
        self.assertEqual(len(client.calls), 0)

    def test_sync_date_range_updates_changed_values(self) -> None:
        counts = {date(2026, 2, 1): 20}
        service, client = self._make_service(counts)
        # Pre-populate with old value
        existing = client.create_datapoint(
            username="alice",
            goal_slug="anki-reviews",
            request=CreateDatapointRequest(value=10.0, comment="old"),
        )
        existing.daystamp = "20260201"
        existing.requestid = request_id_for_day(date(2026, 2, 1), "anki-reviews")
        client.stored[existing.id] = existing

        result = service.sync_date_range(
            start=date(2026, 2, 1),
            end=date(2026, 2, 1),
        )
        self.assertEqual(result.days_synced, 1)
        self.assertEqual(result.days_skipped, 0)
        self.assertEqual(len(client.updated_calls), 1)
        self.assertEqual(client.updated_calls[0][3].value, 20.0)


class FlakyClient(MockBeeminderClient):
    """MockBeeminderClient that raises BeeminderError for specific days.

    Failures are keyed off the requestid (which embeds the day) since the
    day itself isn't passed to ``create_datapoint``/``update_datapoint``.
    """

    def __init__(self, fail_on_dates: set[date]) -> None:
        super().__init__()
        self.fail_on_dates = fail_on_dates

    def create_datapoint(self, username, goal_slug, request, timeout_seconds=10):
        if any(day.isoformat() in request.requestid for day in self.fail_on_dates):
            raise BeeminderError("simulated failure")
        return super().create_datapoint(username, goal_slug, request, timeout_seconds)


class TestSyncDayCompletion(unittest.TestCase):
    def _make_service(self, count, dry_run=False, goal_slug="anki-completion"):
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_completion_goal_slug=goal_slug,
            dry_run=dry_run,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=FakeReviewCountSource(count=count),
        )
        return service, client

    def test_zero_review_day_posts_value_zero_not_skipped(self) -> None:
        service, client = self._make_service(count=0)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][2].value, 0.0)

    def test_nonzero_review_day_posts_value_one(self) -> None:
        service, client = self._make_service(count=5)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][2].value, 1.0)

    def _seed_existing(self, client, day, value):
        existing = client.create_datapoint(
            username="alice",
            goal_slug="anki-completion",
            request=CreateDatapointRequest(value=float(value), comment="existing"),
        )
        existing.daystamp = day.strftime("%Y%m%d")
        existing.timestamp = 1738454400
        existing.requestid = request_id_for_completion_day(day, "anki-completion")
        client.stored[existing.id] = existing
        return existing

    def test_idempotent_no_op_when_existing_matches_zero(self) -> None:
        service, client = self._make_service(count=0)
        self._seed_existing(client, date(2026, 2, 2), value=0)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("no update needed", result.message)
        self.assertEqual(len(client.updated_calls), 0)

    def test_idempotent_no_op_when_existing_matches_one(self) -> None:
        service, client = self._make_service(count=3)
        self._seed_existing(client, date(2026, 2, 2), value=1)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("no update needed", result.message)
        self.assertEqual(len(client.updated_calls), 0)

    def test_flip_zero_to_one_updates_datapoint(self) -> None:
        service, client = self._make_service(count=4)
        self._seed_existing(client, date(2026, 2, 2), value=0)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.updated_calls), 1)
        self.assertEqual(client.updated_calls[0][3].value, 1.0)

    def test_flip_one_to_zero_updates_datapoint(self) -> None:
        """Un-completing a day: the datapoint must be flipped back to 0."""
        service, client = self._make_service(count=0)
        self._seed_existing(client, date(2026, 2, 2), value=1)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.updated_calls), 1)
        self.assertEqual(client.updated_calls[0][3].value, 0.0)

    def test_missing_username_returns_required_fields_message(self) -> None:
        config = AddonConfig(
            beeminder_username="",
            beeminder_auth_token="token",
            review_completion_goal_slug="anki-completion",
            default_goal_slug="anki-default",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=1)
        )
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("required", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_missing_completion_goal_slug_does_not_fall_back(self) -> None:
        """No fallback to default_goal_slug/review_count_goal_slug is deliberate."""
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_completion_goal_slug="",
            default_goal_slug="anki-default",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=1)
        )
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("required", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_dry_run_posts_nothing_and_makes_no_client_calls(self) -> None:
        service, client = self._make_service(count=3, dry_run=True)
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("Dry run", result.message)
        self.assertEqual(len(client.calls), 0)
        self.assertEqual(len(client.updated_calls), 0)


class TestRequestIdForCompletionDay(unittest.TestCase):
    def test_format_and_difference_from_count_request_id(self) -> None:
        day = date(2026, 2, 2)
        completion_id = request_id_for_completion_day(day, "anki-completion")
        self.assertEqual(completion_id, "anki-review-complete-anki-completion-2026-02-02")

        count_id = request_id_for_day(day, "anki-completion")
        self.assertNotEqual(completion_id, count_id)


class TestSyncCompletionDateRange(unittest.TestCase):
    def _make_service(self, counts_by_date, dry_run=False, goal_slug="anki-completion"):
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_completion_goal_slug=goal_slug,
            dry_run=dry_run,
        )
        client = MockBeeminderClient()
        source = FakeReviewCountSourceWithHistory(counts_by_date)
        service = ReviewCountSyncService(
            config=config,
            client=client,
            review_count_source=source,
        )
        return service, client

    def test_mixed_zero_and_nonzero_days_none_skipped(self) -> None:
        counts = {
            date(2026, 2, 1): 10,
            date(2026, 2, 3): 0,
            date(2026, 2, 5): 7,
        }
        service, client = self._make_service(counts)
        result = service.sync_completion_date_range(
            start=date(2026, 2, 1),
            end=date(2026, 2, 5),
        )
        self.assertEqual(result.days_synced, 5)
        self.assertEqual(result.days_skipped, 0)
        self.assertEqual(result.days_failed, 0)
        self.assertEqual(len(client.calls), 5)
        for offset in range(5):
            day = date(2026, 2, 1 + offset)
            self.assertIn(day.isoformat(), result.per_day_results)
            self.assertTrue(result.per_day_results[day.isoformat()].posted)

    def test_invalid_range_returns_empty_result_error_message(self) -> None:
        service, client = self._make_service({})
        result = service.sync_completion_date_range(
            start=date(2026, 2, 6),
            end=date(2026, 2, 1),
        )
        self.assertEqual(result.days_synced, 0)
        self.assertEqual(result.days_failed, 0)
        self.assertIn("Invalid date range", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_missing_config_returns_empty_result_without_listing_datapoints(self) -> None:
        config = AddonConfig(beeminder_username="", review_completion_goal_slug="", dry_run=False)
        client = MockBeeminderClient()
        source = FakeReviewCountSourceWithHistory({})
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)
        result = service.sync_completion_date_range(start=date(2026, 2, 1), end=date(2026, 2, 3))
        self.assertEqual(result.days_synced, 0)
        self.assertIn("required", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_both_goals_enabled_simultaneously_use_different_requestids(self) -> None:
        counts = {date(2026, 2, 1): 5}
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            review_completion_goal_slug="anki-completion",
            dry_run=False,
        )
        client = MockBeeminderClient()
        source = FakeReviewCountSourceWithHistory(counts)
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)

        count_result = service.sync_date_range(start=date(2026, 2, 1), end=date(2026, 2, 1))
        completion_result = service.sync_completion_date_range(
            start=date(2026, 2, 1), end=date(2026, 2, 1)
        )

        self.assertEqual(count_result.days_synced, 1)
        self.assertEqual(completion_result.days_synced, 1)
        self.assertEqual(len(client.calls), 2)

        count_requestid = client.calls[0][2].requestid
        completion_requestid = client.calls[1][2].requestid
        self.assertNotEqual(count_requestid, completion_requestid)
        self.assertEqual(client.calls[0][1], "anki-reviews")
        self.assertEqual(client.calls[1][1], "anki-completion")
        self.assertEqual(client.calls[0][2].value, 5.0)
        self.assertEqual(client.calls[1][2].value, 1.0)

    def test_beeminder_error_caught_per_day_others_still_process(self) -> None:
        counts = {
            date(2026, 2, 1): 1,
            date(2026, 2, 2): 2,
            date(2026, 2, 3): 3,
        }
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_completion_goal_slug="anki-completion",
            dry_run=False,
        )
        client = FlakyClient(fail_on_dates={date(2026, 2, 2)})
        source = FakeReviewCountSourceWithHistory(counts)
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)

        result = service.sync_completion_date_range(start=date(2026, 2, 1), end=date(2026, 2, 3))

        self.assertEqual(result.days_failed, 1)
        self.assertEqual(result.days_synced, 2)
        self.assertIn("Failed to sync 2026-02-02", result.per_day_results["2026-02-02"].message)
        self.assertTrue(result.per_day_results["2026-02-01"].posted)
        self.assertTrue(result.per_day_results["2026-02-03"].posted)


if __name__ == "__main__":
    unittest.main()
