import unittest
from datetime import date

from anki_beeminder.config import AddonConfig
from anki_beeminder.mocks.mock_client import MockBeeminderClient
from anki_beeminder.services.review_count_service import (
    AnkiReviewCountSource,
    ReviewCountSyncService,
    day_bounds_epoch_millis,
)
from anki_beeminder.services.sync_service import SyncService


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

    def test_sync_day_sends_review_count_as_datapoint(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            default_goal_slug="fallback-goal",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        sync_service = SyncService(config=config, client=client)
        service = ReviewCountSyncService(
            sync_service=sync_service,
            review_count_source=FakeReviewCountSource(count=42),
        )
        result = service.sync_day(day=date(2026, 2, 2), goal_slug=config.review_count_goal_slug)
        self.assertTrue(result.posted)
        self.assertEqual(client.calls[0][1], "anki-reviews")
        self.assertEqual(client.calls[0][2].value, 42.0)


if __name__ == "__main__":
    unittest.main()

