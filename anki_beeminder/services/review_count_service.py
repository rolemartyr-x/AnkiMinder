"""Review-count collection and sync helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import Any, Protocol, Tuple

from ..beeminder.client import BeeminderClient
from ..beeminder.models import CreateDatapointRequest, DatapointResponse
from ..config import AddonConfig
from .sync_service import SyncResult

REQUEST_ID_PREFIX = "anki-review-count"


def day_bounds_epoch_millis(day: date_type) -> Tuple[int, int]:
    """Return inclusive/exclusive local-day bounds in epoch milliseconds."""

    start = datetime.combine(day, time.min).astimezone()
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def daystamp(day: date_type) -> str:
    """Return Beeminder-style YYYYMMDD daystamp string."""

    return day.strftime("%Y%m%d")


def request_id_for_day(day: date_type, goal_slug: str) -> str:
    """Deterministic requestid so one day maps to one datapoint."""

    return f"{REQUEST_ID_PREFIX}-{goal_slug}-{day.isoformat()}"


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
    """Upserts one Beeminder datapoint for a day's total review count."""

    config: AddonConfig
    client: BeeminderClient
    review_count_source: ReviewCountSource

    def sync_day_total(self, day: date_type, goal_slug: str = "") -> SyncResult:
        username = self.config.beeminder_username
        resolved_goal_slug = goal_slug or self.config.review_count_goal_slug or self.config.default_goal_slug
        if not username or not resolved_goal_slug:
            return SyncResult(
                posted=False,
                message="Beeminder username and goal slug are required before syncing.",
            )

        review_count = self.review_count_source.count_reviews_for_day(day)
        requestid = request_id_for_day(day, resolved_goal_slug)
        comment = f"Anki reviews total for {day.isoformat()}: {review_count}"

        if self.config.dry_run:
            return SyncResult(
                posted=False,
                message=(
                    "Dry run enabled: would upsert "
                    f"value={review_count} to {resolved_goal_slug} for {day.isoformat()}."
                ),
            )

        if (
            self.config.last_review_count_sync_date == day.isoformat()
            and self.config.last_review_count_value == review_count
        ):
            return SyncResult(
                posted=False,
                message=f"Review count unchanged for {day.isoformat()} ({review_count}); no update needed.",
            )

        request = CreateDatapointRequest(value=float(review_count), comment=comment, requestid=requestid)
        existing = self._find_existing_datapoint(
            username=username,
            goal_slug=resolved_goal_slug,
            day=day,
            requestid=requestid,
        )

        if existing is not None:
            updated = self.client.update_datapoint(
                username=username,
                goal_slug=resolved_goal_slug,
                datapoint_id=existing.id,
                request=request,
                timeout_seconds=self.config.request_timeout_seconds,
            )
            return SyncResult(
                posted=True,
                message=f"Updated Beeminder total for {day.isoformat()} to {review_count}.",
                datapoint=updated,
            )

        created = self.client.create_datapoint(
            username=username,
            goal_slug=resolved_goal_slug,
            request=request,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        return SyncResult(
            posted=True,
            message=f"Created Beeminder total for {day.isoformat()} with value {review_count}.",
            datapoint=created,
        )

    def _find_existing_datapoint(
        self,
        username: str,
        goal_slug: str,
        day: date_type,
        requestid: str,
    ) -> DatapointResponse | None:
        if (
            self.config.last_review_count_sync_date == day.isoformat()
            and self.config.last_review_count_datapoint_id
        ):
            return DatapointResponse(
                id=self.config.last_review_count_datapoint_id,
                value=float(self.config.last_review_count_value),
                timestamp=0,
                requestid=requestid,
                daystamp=daystamp(day),
            )

        recent = self.client.list_datapoints(
            username=username,
            goal_slug=goal_slug,
            count=30,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        for item in recent:
            if item.requestid == requestid:
                return item
        target_daystamp = daystamp(day)
        for item in recent:
            if item.daystamp == target_daystamp and REQUEST_ID_PREFIX in item.requestid:
                return item
        return None

