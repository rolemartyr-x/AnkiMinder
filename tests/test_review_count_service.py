import unittest
from datetime import date

from anki_beeminder.beeminder.models import CreateDatapointRequest
from anki_beeminder.config import AddonConfig
from anki_beeminder.mocks.mock_client import MockBeeminderClient
from anki_beeminder.services.review_count_service import (
    AnkiReviewCountSource,
    ReviewCountSyncService,
    day_bounds_epoch_millis,
    request_id_for_day,
)


class FakeDb:
    def __init__(self, result):
        self.result = result
        self.last_query = None
        self.last_params = None

    def scalar(self, query, *params):
        self.last_query = query
        self.last_params = params
        return self.result


class FakeReviewCountSource:
    def __init__(self, count):
        self.count = count

    def count_reviews_for_day(self, _day):
        return self.count


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


if __name__ == "__main__":
    unittest.main()
