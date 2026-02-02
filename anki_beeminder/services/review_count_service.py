"""Review-count collection and sync helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import Any, Protocol, Tuple

from .sync_service import SyncResult, SyncService


def day_bounds_epoch_millis(day: date_type) -> Tuple[int, int]:
    """Return inclusive/exclusive local-day bounds in epoch milliseconds."""

    start = datetime.combine(day, time.min).astimezone()
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


class ReviewCountSource(Protocol):
    """Abstraction for retrieving review counts from a backing store."""

    def count_reviews_for_day(self, day: date_type) -> int:
        ...


@dataclass
class AnkiReviewCountSource:
    """Reads review counts from the Anki revlog table."""

    db: Any

    def count_reviews_for_day(self, day: date_type) -> int:
        start_ms, end_ms = day_bounds_epoch_millis(day)
        query = "SELECT COUNT(*) FROM revlog WHERE id >= ? AND id < ?"
        count = self.db.scalar(query, start_ms, end_ms)
        return int(count or 0)


@dataclass
class ReviewCountSyncService:
    """Sends one datapoint to Beeminder for a day's review count."""

    sync_service: SyncService
    review_count_source: ReviewCountSource

    def sync_day(self, day: date_type, goal_slug: str = "") -> SyncResult:
        review_count = self.review_count_source.count_reviews_for_day(day)
        comment = f"Anki reviews for {day.isoformat()}: {review_count}"
        return self.sync_service.send_value(
            value=float(review_count),
            comment=comment,
            goal_slug=goal_slug,
        )
