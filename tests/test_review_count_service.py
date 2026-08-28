import sqlite3
import unittest
from datetime import date

from ankiminder.beeminder.client import BeeminderClient
from ankiminder.beeminder.models import CreateDatapointRequest
from ankiminder.config import AddonConfig
from ankiminder.exceptions import BeeminderError
from ankiminder.mocks.mock_client import MockBeeminderClient
from ankiminder.services.review_count_service import (
    REQUEST_ID_PREFIX_COMPLETION,
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
        self.assertIn("type NOT IN", fake_db.last_query)
        # 2 day-bound params + 2 excluded revlog.type values (Manual, Rescheduled).
        self.assertEqual(len(fake_db.last_params), 4)

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


class SqliteDb:
    """Thin `.scalar()` wrapper over a real sqlite3 connection.

    Mirrors the subset of Anki's real `col.db` interface that
    ``AnkiReviewCountSource`` actually uses, so the revlog-type filter in
    ``count_reviews_for_day`` is exercised against real SQL execution rather
    than a query-string assertion against ``FakeDb``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def scalar(self, query, *params):
        row = self._conn.execute(query, params).fetchone()
        return row[0] if row else None


def _make_sqlite_revlog(rows: list[tuple[int, int]]) -> SqliteDb:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE revlog (id INTEGER PRIMARY KEY, type INTEGER)")
    conn.executemany("INSERT INTO revlog (id, type) VALUES (?, ?)", rows)
    conn.commit()
    return SqliteDb(conn)


class TestRevlogTypeFiltering(unittest.TestCase):
    """Regression coverage for excluding non-review revlog rows (issue #7).

    Anki's revlog.type: 0=Learning, 1=Review, 2=Relearning, 3=Filtered are
    real review events; 4=Manual and 5=Rescheduled are administrative
    reset/reschedule actions with no review performed, and must not count.
    """

    def test_manual_and_rescheduled_rows_excluded_from_count(self) -> None:
        day = date(2026, 2, 2)
        start_ms, _end_ms = day_bounds_epoch_millis(day)
        rows = [
            (start_ms + 1, 0),  # Learning -- counts
            (start_ms + 2, 1),  # Review -- counts
            (start_ms + 3, 2),  # Relearning -- counts
            (start_ms + 4, 3),  # Filtered/cram -- counts
            (start_ms + 5, 4),  # Manual reset/reschedule -- must NOT count
            (start_ms + 6, 5),  # Rescheduled -- must NOT count
        ]
        db = _make_sqlite_revlog(rows)
        source = AnkiReviewCountSource(db=db)
        self.assertEqual(source.count_reviews_for_day(day), 4)

    def test_day_with_only_manual_reschedule_counts_as_zero(self) -> None:
        """The scenario that made this a false positive for the completion signal."""
        day = date(2026, 2, 2)
        start_ms, _end_ms = day_bounds_epoch_millis(day)
        db = _make_sqlite_revlog([(start_ms + 1, 4)])
        source = AnkiReviewCountSource(db=db)
        self.assertEqual(source.count_reviews_for_day(day), 0)


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
        # Days not present in `counts` implicitly have a review count of 0
        # (see FakeReviewCountSourceWithHistory.count_reviews_for_day).
        expected_values = {
            date(2026, 2, 1): 1.0,  # 10 reviews -> completed
            date(2026, 2, 2): 0.0,  # not in counts -> 0 reviews -> not completed
            date(2026, 2, 3): 0.0,  # 0 reviews -> not completed
            date(2026, 2, 4): 0.0,  # not in counts -> 0 reviews -> not completed
            date(2026, 2, 5): 1.0,  # 7 reviews -> completed
        }
        for offset in range(5):
            day = date(2026, 2, 1 + offset)
            self.assertIn(day.isoformat(), result.per_day_results)
            self.assertTrue(result.per_day_results[day.isoformat()].posted)
            self.assertEqual(client.calls[offset][2].value, expected_values[day])

    def test_dry_run_range_posts_nothing_and_reports_days_completed(self) -> None:
        """Range-level dry-run contract for the completion signal.

        The day-level ``sync_day_completion`` dry-run path is covered
        elsewhere; this locks the range-level method's own message/behavior
        contract (nothing posted, "days completed" label, not a raw review
        count) since it's a public method exercised only indirectly before.
        """
        counts = {date(2026, 2, 1): 5, date(2026, 2, 2): 0}
        service, client = self._make_service(counts, dry_run=True)
        result = service.sync_completion_date_range(start=date(2026, 2, 1), end=date(2026, 2, 2))
        self.assertEqual(result.days_synced, 0)
        self.assertEqual(result.days_skipped, 2)
        self.assertEqual(len(client.calls), 0)
        self.assertIn("days completed", result.message)
        # One of the two days had reviews -> 1 "day completed", not a
        # review-count total (which would be 5).
        self.assertEqual(result.total_reviews, 1)

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


class TestGoalSlugCollisionGuard(unittest.TestCase):
    """Regression coverage for the goal-slug-collision datapoint corruption bug.

    When ``review_completion_goal_slug`` is (mis)configured to match
    ``review_count_goal_slug``/``default_goal_slug``, both sync loops used to
    upsert against the same underlying set of Beeminder datapoints via
    ``_find_datapoint_for_day``'s daystamp fallback, letting the completion
    sync silently overwrite a live numeric datapoint's value (or vice
    versa). These tests must fail against the pre-fix code (no config guard,
    no requestid-family-aware fallback matching) and pass after the fix.
    """

    def test_completion_range_refuses_and_does_not_touch_numeric_datapoint(self) -> None:
        shared_slug = "anki-shared"
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug=shared_slug,
            review_completion_goal_slug=shared_slug,
            review_completion_sync_enabled=True,
            dry_run=False,
        )
        client = MockBeeminderClient()
        target_day = date(2026, 2, 2)
        # Seed an existing NUMERIC-count datapoint for the day. Setting
        # `daystamp` on the request (not just on the returned object
        # afterward) exercises the same echo path the real Beeminder API
        # uses -- MockBeeminderClient.create_datapoint propagates it.
        existing = client.create_datapoint(
            username="alice",
            goal_slug=shared_slug,
            request=CreateDatapointRequest(
                value=5.0,
                daystamp=target_day.strftime("%Y%m%d"),
                requestid=request_id_for_day(target_day, shared_slug),
                comment="numeric count",
            ),
        )
        client.stored[existing.id] = existing

        source = FakeReviewCountSourceWithHistory({target_day: 1})
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)

        result = service.sync_completion_date_range(start=target_day, end=target_day)

        self.assertEqual(result.days_synced, 0)
        self.assertEqual(result.days_failed, 0)
        self.assertIn("must differ", result.message)
        # The pre-existing numeric datapoint must be completely untouched:
        # no update call issued, and its stored value/requestid unchanged.
        self.assertEqual(len(client.updated_calls), 0)
        stored = client.stored[existing.id]
        self.assertEqual(stored.value, 5.0)
        self.assertEqual(stored.requestid, request_id_for_day(target_day, shared_slug))

    def test_sync_day_completion_direct_call_also_refuses_matching_slug(self) -> None:
        shared_slug = "anki-shared"
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug=shared_slug,
            review_completion_goal_slug=shared_slug,
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=1)
        )
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("must differ", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_default_goal_slug_fallback_also_triggers_guard(self) -> None:
        """The guard must resolve review_count_goal_slug's own fallback too."""
        shared_slug = "anki-shared"
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="",
            default_goal_slug=shared_slug,
            review_completion_goal_slug=shared_slug,
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=1)
        )
        result = service.sync_completion_date_range(start=date(2026, 2, 2), end=date(2026, 2, 2))
        self.assertEqual(result.days_synced, 0)
        self.assertIn("must differ", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_case_only_collision_is_not_currently_detected(self) -> None:
        """Documents current behavior: the guard compares slugs case-sensitively.

        Not a correctness fix -- Beeminder enforces lowercase-only goal
        slugs at creation, so a mixed-case config value here can't resolve
        to a real colliding goal in practice. This locks in today's
        comparison behavior rather than asserting it's the ideal one;
        whether to case-fold the comparison for clearer misconfiguration
        errors is an open UX question (see issue #10).
        """
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="AnkiReviews",
            review_completion_goal_slug="ankireviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=1)
        )
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertTrue(result.posted)

    def test_distinct_slugs_are_unaffected_by_guard(self) -> None:
        """Sanity check: the normal, non-colliding configuration still works."""
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            review_completion_goal_slug="anki-completion",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=1)
        )
        result = service.sync_day_completion(day=date(2026, 2, 2))
        self.assertTrue(result.posted)


class TestFindDatapointForDayFamilyAwareMatching(unittest.TestCase):
    """Direct coverage of the hardened requestid-family-aware fallback matcher."""

    def _service(self) -> tuple[ReviewCountSyncService, MockBeeminderClient]:
        config = AddonConfig(beeminder_username="alice", beeminder_auth_token="token", dry_run=False)
        client = MockBeeminderClient()
        service = ReviewCountSyncService(
            config=config, client=client, review_count_source=FakeReviewCountSource(count=0)
        )
        return service, client

    def test_daystamp_fallback_ignores_datapoint_from_other_requestid_family(self) -> None:
        service, client = self._service()
        day = date(2026, 2, 2)
        numeric = client.create_datapoint(
            username="alice",
            goal_slug="shared",
            request=CreateDatapointRequest(
                value=5.0,
                daystamp=day.strftime("%Y%m%d"),
                requestid=request_id_for_day(day, "shared"),
            ),
        )
        client.stored[numeric.id] = numeric

        found = service._find_datapoint_for_day(
            username="alice",
            goal_slug="shared",
            day=day,
            requestid=request_id_for_completion_day(day, "shared"),
            requestid_prefix=REQUEST_ID_PREFIX_COMPLETION,
            prefetched_datapoints=list(client.stored.values()),
        )
        self.assertIsNone(found)

    def test_daystamp_fallback_still_matches_legacy_manual_datapoint_without_requestid(self) -> None:
        """A manually-created Beeminder datapoint (no requestid) must still match."""
        service, client = self._service()
        day = date(2026, 2, 2)
        manual = client.create_datapoint(
            username="alice",
            goal_slug="shared",
            request=CreateDatapointRequest(value=1.0, daystamp=day.strftime("%Y%m%d")),
        )
        client.stored[manual.id] = manual

        found = service._find_datapoint_for_day(
            username="alice",
            goal_slug="shared",
            day=day,
            requestid=request_id_for_completion_day(day, "shared"),
            requestid_prefix=REQUEST_ID_PREFIX_COMPLETION,
            prefetched_datapoints=list(client.stored.values()),
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.id, manual.id)


class TestPrecomputedCounts(unittest.TestCase):
    """Coverage for the shared review-count cache (avoids duplicate revlog queries)."""

    def test_precomputed_counts_used_instead_of_recounting(self) -> None:
        class CountingSource:
            def __init__(self, counts: dict) -> None:
                self.counts = counts
                self.call_count = 0

            def count_reviews_for_day(self, day):
                self.call_count += 1
                return self.counts.get(day, 0)

        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        source = CountingSource({date(2026, 2, 1): 5})
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)

        result = service.sync_date_range(
            start=date(2026, 2, 1),
            end=date(2026, 2, 1),
            precomputed_counts={date(2026, 2, 1): 5},
        )
        self.assertEqual(result.days_synced, 1)
        # The count must come entirely from the cache -- the underlying
        # source is never queried when a precomputed value is supplied.
        self.assertEqual(source.call_count, 0)

    def test_standalone_call_without_precomputed_counts_still_works(self) -> None:
        """Default (no cache) behavior must be unchanged for existing callers."""
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        source = FakeReviewCountSourceWithHistory({date(2026, 2, 1): 5})
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)

        result = service.sync_date_range(start=date(2026, 2, 1), end=date(2026, 2, 1))
        self.assertEqual(result.days_synced, 1)
        self.assertEqual(client.calls[0][2].value, 5.0)

    def test_missing_day_in_precomputed_counts_falls_back_to_source_for_that_day_only(self) -> None:
        """A day absent from ``precomputed_counts`` must trigger exactly one
        fresh ``count_reviews_for_day`` call for that day -- days present in
        the dict must never be re-queried.

        Regression coverage for the round-2 finding: mutation testing (a
        temporary swap to ``precomputed_counts.get(day, 0)``, which
        silently treats a missing day as zero reviews instead of falling
        back to the source) left the full suite passing with no test
        catching it. This test's ``queried_days`` assertion fails against
        that mutation, since the missing day would never reach the source
        at all under the ``.get(day, 0)`` version.
        """

        class CountingSource:
            def __init__(self, counts: dict) -> None:
                self.counts = counts
                self.queried_days: list = []

            def count_reviews_for_day(self, day):
                self.queried_days.append(day)
                return self.counts.get(day, 0)

        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        first_day = date(2026, 2, 1)
        middle_day = date(2026, 2, 2)
        last_day = date(2026, 2, 3)
        source = CountingSource({first_day: 3, middle_day: 7, last_day: 2})
        service = ReviewCountSyncService(config=config, client=client, review_count_source=source)

        # middle_day deliberately omitted from the precomputed dict.
        precomputed = {first_day: 3, last_day: 2}

        result = service.sync_date_range(
            start=first_day,
            end=last_day,
            precomputed_counts=precomputed,
        )

        self.assertEqual(result.days_synced, 3)
        # Only the day missing from the precomputed dict reaches the source;
        # the two days already covered by the dict are never re-queried.
        self.assertEqual(source.queried_days, [middle_day])


if __name__ == "__main__":
    unittest.main()
