"""Review-count collection and sync helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import Any, Protocol

from ..beeminder.client import BeeminderClient
from ..beeminder.models import CreateDatapointRequest, DatapointResponse
from ..config import AddonConfig
from ..exceptions import BeeminderError
from .sync_service import SyncResult

REQUEST_ID_PREFIX = "anki-review-count"

# Fallback lookup window used when no prefetched datapoints are available for
# a single-day sync (see ``_find_datapoint_for_day``).
FALLBACK_DATAPOINT_LOOKUP_COUNT = 30

# Minimum number of recent datapoints to prefetch for a date-range sync, plus
# a small buffer above the range length itself so recently created/renamed
# datapoints near the boundary are still visible.
MIN_PREFETCH_COUNT = 7
PREFETCH_BUFFER_DAYS = 5


def day_bounds_epoch_millis(day: date_type) -> tuple[int, int]:
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
class DateRangeSyncResult:
    """Aggregate result from syncing a range of dates."""

    days_synced: int
    days_skipped: int
    days_failed: int
    total_reviews: int
    last_successful_date: date_type | None
    last_successful_datapoint: DatapointResponse | None
    per_day_results: dict[str, SyncResult] = field(default_factory=dict)
    message: str = ""


def _empty_date_range_result(message: str) -> DateRangeSyncResult:
    """Build a zeroed-out result for early-exit validation failures."""

    return DateRangeSyncResult(
        days_synced=0,
        days_skipped=0,
        days_failed=0,
        total_reviews=0,
        last_successful_date=None,
        last_successful_datapoint=None,
        message=message,
    )


@dataclass
class ReviewCountSyncService:
    """Upserts Beeminder datapoints for review counts."""

    config: AddonConfig
    client: BeeminderClient
    review_count_source: ReviewCountSource

    @classmethod
    def from_config(
        cls,
        config: AddonConfig,
        review_count_source: ReviewCountSource,
    ) -> "ReviewCountSyncService":
        """Build a service with a Beeminder client constructed from ``config``.

        Keeps ``BeeminderClient`` construction inside the services layer so
        callers such as ``addon.py`` never need to import the client layer
        directly (dependencies flow downward only: UI -> services -> client).
        """

        client = BeeminderClient(auth_token=config.beeminder_auth_token)
        return cls(config=config, client=client, review_count_source=review_count_source)

    def sync_day_total(
        self,
        day: date_type,
        goal_slug: str = "",
        prefetched_datapoints: list[DatapointResponse] | None = None,
    ) -> SyncResult:
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

        if review_count == 0:
            return SyncResult(
                posted=False,
                message=f"No reviews on {day.isoformat()}; skipping sync.",
            )

        if self.config.dry_run:
            return SyncResult(
                posted=False,
                message=(
                    "Dry run enabled: would upsert "
                    f"value={review_count} to {resolved_goal_slug} for {day.isoformat()}."
                ),
            )

        request = CreateDatapointRequest(
            value=float(review_count),
            daystamp=daystamp(day),
            comment=comment,
            requestid=requestid,
        )
        existing = self._find_datapoint_for_day(
            username=username,
            goal_slug=resolved_goal_slug,
            day=day,
            requestid=requestid,
            prefetched_datapoints=prefetched_datapoints,
        )

        if existing is not None:
            if int(existing.value) == review_count:
                return SyncResult(
                    posted=False,
                    message=f"Beeminder already has {day.isoformat()} total ({review_count}); no update needed.",
                    datapoint=existing,
                )
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

    def sync_date_range(
        self,
        start: date_type,
        end: date_type,
        goal_slug: str = "",
    ) -> DateRangeSyncResult:
        """Sync review counts for all dates in [start, end], including zero-review days."""
        username = self.config.beeminder_username
        resolved_goal_slug = (
            goal_slug or self.config.review_count_goal_slug or self.config.default_goal_slug
        )
        if not username or not resolved_goal_slug:
            return _empty_date_range_result(
                "Beeminder username and goal slug are required before syncing."
            )

        days = (end - start).days
        if days < 0:
            return _empty_date_range_result("Invalid date range: start must be on or before end.")
        dates_to_sync = [start + timedelta(days=offset) for offset in range(days + 1)]

        # Pre-fetch Beeminder datapoints once for the whole range.
        prefetched: list[DatapointResponse] | None = None
        if not self.config.dry_run:
            fetch_count = max(days + PREFETCH_BUFFER_DAYS, MIN_PREFETCH_COUNT)
            prefetched = self.client.list_datapoints(
                username=username,
                goal_slug=resolved_goal_slug,
                count=fetch_count,
                timeout_seconds=self.config.request_timeout_seconds,
            )

        days_synced = 0
        days_skipped = 0
        days_failed = 0
        total_reviews = 0
        last_successful_date: date_type | None = None
        last_successful_datapoint: DatapointResponse | None = None
        per_day_results: dict[str, SyncResult] = {}

        for day in dates_to_sync:
            try:
                result = self.sync_day_total(
                    day=day,
                    goal_slug=resolved_goal_slug,
                    prefetched_datapoints=prefetched,
                )
                per_day_results[day.isoformat()] = result

                if result.datapoint is not None:
                    total_reviews += int(result.datapoint.value)
                elif self.config.dry_run:
                    total_reviews += self.review_count_source.count_reviews_for_day(day)

                if result.posted:
                    days_synced += 1
                    last_successful_date = day
                    if result.datapoint is not None:
                        last_successful_datapoint = result.datapoint
                    # Add newly created datapoint to prefetched list so
                    # subsequent days can see it.
                    if prefetched is not None and result.datapoint is not None:
                        prefetched.append(result.datapoint)
                else:
                    days_skipped += 1
                    if result.datapoint is not None:
                        last_successful_date = day
                        last_successful_datapoint = result.datapoint
            except BeeminderError as exc:
                days_failed += 1
                per_day_results[day.isoformat()] = SyncResult(
                    posted=False,
                    message=f"Failed to sync {day.isoformat()}: {exc}",
                )

        parts: list[str] = []
        if days_synced > 0:
            parts.append(f"Synced {days_synced} day(s)")
        if days_skipped > 0:
            parts.append(f"{days_skipped} already up-to-date")
        if days_failed > 0:
            parts.append(f"{days_failed} failed")
        parts.append(f"{total_reviews} total reviews")
        message = "; ".join(parts) + "."

        return DateRangeSyncResult(
            days_synced=days_synced,
            days_skipped=days_skipped,
            days_failed=days_failed,
            total_reviews=total_reviews,
            last_successful_date=last_successful_date,
            last_successful_datapoint=last_successful_datapoint,
            per_day_results=per_day_results,
            message=message,
        )

    def _find_datapoint_for_day(
        self,
        username: str,
        goal_slug: str,
        day: date_type,
        requestid: str,
        prefetched_datapoints: list[DatapointResponse] | None = None,
    ) -> DatapointResponse | None:
        if prefetched_datapoints is not None:
            recent = prefetched_datapoints
        else:
            recent = self.client.list_datapoints(
                username=username,
                goal_slug=goal_slug,
                count=FALLBACK_DATAPOINT_LOOKUP_COUNT,
                timeout_seconds=self.config.request_timeout_seconds,
            )
        target_daystamp = daystamp(day)
        matches = [item for item in recent if item.daystamp == target_daystamp or item.requestid == requestid]
        if not matches:
            return None
        matches.sort(key=lambda item: item.timestamp, reverse=True)
        return matches[0]
