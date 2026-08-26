"""Review-count collection and sync helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import Any, Callable, Protocol

from ..beeminder.client import BeeminderClient
from ..beeminder.models import CreateDatapointRequest, DatapointResponse
from ..config import AddonConfig
from ..exceptions import BeeminderError
from .sync_service import SyncResult

REQUEST_ID_PREFIX = "anki-review-count"
REQUEST_ID_PREFIX_COMPLETION = "anki-review-complete"

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


def request_id_for_completion_day(day: date_type, goal_slug: str) -> str:
    """Deterministic requestid so one day maps to one completion datapoint.

    Distinct prefix from ``request_id_for_day`` so the numeric-count sync and
    the binary-completion sync can target the same goal slug without ever
    colliding on requestid.
    """

    return f"{REQUEST_ID_PREFIX_COMPLETION}-{goal_slug}-{day.isoformat()}"


def find_datapoint_for_day(
    client: BeeminderClient,
    request_timeout_seconds: int,
    username: str,
    goal_slug: str,
    day: date_type,
    requestid: str,
    requestid_prefix: str,
    prefetched_datapoints: list[DatapointResponse] | None = None,
) -> DatapointResponse | None:
    """Find the existing datapoint (if any) representing ``day``.

    Matches on exact ``requestid`` first. As a fallback (for datapoints
    created before deterministic requestids, or created manually by the
    user directly on Beeminder), also matches on a bare ``daystamp``
    match -- but *only* when the candidate's requestid is empty (the
    legacy/manual case) or belongs to the same signal family as
    ``requestid_prefix``. Without this restriction, a daystamp match
    would happily pair one signal's sync with another signal's datapoint
    whenever both target the same goal slug on the same day, silently
    overwriting one signal's data with the other's (see the goal-slug-
    conflict guards on each sync service, which are the primary defense;
    this keeps the fallback matcher itself safe when multiple signal
    types share this helper).

    Module-level (rather than a ``ReviewCountSyncService`` method) so any
    sync service -- not just the numeric/completion ones -- can reuse this
    matching logic without duplicating it.
    """
    if prefetched_datapoints is not None:
        recent = prefetched_datapoints
    else:
        recent = client.list_datapoints(
            username=username,
            goal_slug=goal_slug,
            count=FALLBACK_DATAPOINT_LOOKUP_COUNT,
            timeout_seconds=request_timeout_seconds,
        )
    target_daystamp = daystamp(day)

    def _is_match(item: DatapointResponse) -> bool:
        if item.requestid == requestid:
            return True
        if item.daystamp != target_daystamp:
            return False
        # Bare daystamp fallback: only accept a candidate with no
        # requestid at all (legacy/manually-created datapoint) or one
        # whose requestid belongs to this same signal family.
        return not item.requestid or item.requestid.startswith(requestid_prefix)

    matches = [item for item in recent if _is_match(item)]
    if not matches:
        return None
    matches.sort(key=lambda item: item.timestamp, reverse=True)
    return matches[0]


def dates_between(start: date_type, end: date_type) -> list[date_type]:
    """Return every date from ``start`` to ``end`` inclusive.

    Returns an empty list if ``start`` is after ``end`` rather than raising,
    so callers can use it directly for range validation.
    """

    days = (end - start).days
    if days < 0:
        return []
    return [start + timedelta(days=offset) for offset in range(days + 1)]


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
    """Aggregate result from syncing a range of dates.

    ``blocked`` is distinct from ``days_failed``: it marks a result where no
    per-day sync was even attempted because a guard refused to run at all
    (e.g. the completion/numeric goal-slug-collision guard), as opposed to a
    range that ran normally but had some per-day failures. Callers must
    treat a blocked result as an error even though days_synced/skipped/failed
    are all zero -- see ``addon.py``'s ``_perform_review_sync``.
    """

    days_synced: int
    days_skipped: int
    days_failed: int
    total_reviews: int
    last_successful_date: date_type | None
    last_successful_datapoint: DatapointResponse | None
    per_day_results: dict[str, SyncResult] = field(default_factory=dict)
    message: str = ""
    blocked: bool = False


def _empty_date_range_result(message: str, blocked: bool = False) -> DateRangeSyncResult:
    """Build a zeroed-out result for early-exit validation failures."""

    return DateRangeSyncResult(
        days_synced=0,
        days_skipped=0,
        days_failed=0,
        total_reviews=0,
        last_successful_date=None,
        last_successful_datapoint=None,
        message=message,
        blocked=blocked,
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

    def _completion_goal_conflicts_with_count_goal(self, resolved_completion_slug: str) -> bool:
        """True if the completion goal slug is also the numeric-count goal slug.

        Both syncs share the same date-lookup helper (``_find_datapoint_for_day``);
        pointing them at the same goal risks one signal's upsert overwriting
        the other's datapoint (see ``_find_datapoint_for_day`` docstring). We
        refuse to run completion sync in that configuration rather than
        silently corrupting data.
        """

        numeric_slug = self.config.review_count_goal_slug or self.config.default_goal_slug
        return bool(numeric_slug) and resolved_completion_slug == numeric_slug

    @staticmethod
    def _goal_slug_conflict_message(resolved_completion_slug: str) -> str:
        return (
            f"review_completion_goal_slug ('{resolved_completion_slug}') must differ from "
            "review_count_goal_slug/default_goal_slug; refusing to sync completion data to "
            "avoid overwriting the numeric goal's datapoints. See config.md."
        )

    def sync_day_total(
        self,
        day: date_type,
        goal_slug: str = "",
        prefetched_datapoints: list[DatapointResponse] | None = None,
        review_count: int | None = None,
    ) -> SyncResult:
        username = self.config.beeminder_username
        resolved_goal_slug = goal_slug or self.config.review_count_goal_slug or self.config.default_goal_slug
        if not username or not resolved_goal_slug:
            return SyncResult(
                posted=False,
                message="Beeminder username and goal slug are required before syncing.",
            )

        if review_count is None:
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
            requestid_prefix=REQUEST_ID_PREFIX,
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

    def sync_day_completion(
        self,
        day: date_type,
        goal_slug: str = "",
        prefetched_datapoints: list[DatapointResponse] | None = None,
        review_count: int | None = None,
    ) -> SyncResult:
        """Upsert a binary (0/1) "did I review today" datapoint.

        Unlike ``sync_day_total``, this never skips zero-review days: posting
        ``value=0.0`` on a day with no reviews is the entire point of the
        completion signal, not a no-op case.
        """
        username = self.config.beeminder_username
        resolved_goal_slug = goal_slug or self.config.review_completion_goal_slug
        if not username or not resolved_goal_slug:
            return SyncResult(
                posted=False,
                message="Beeminder username and completion goal slug are required before syncing.",
            )

        if self._completion_goal_conflicts_with_count_goal(resolved_goal_slug):
            return SyncResult(
                posted=False,
                message=self._goal_slug_conflict_message(resolved_goal_slug),
            )

        if review_count is None:
            review_count = self.review_count_source.count_reviews_for_day(day)
        value = 1.0 if review_count > 0 else 0.0
        requestid = request_id_for_completion_day(day, resolved_goal_slug)
        comment = (
            f"Anki review completion for {day.isoformat()}: "
            f"{'yes' if value else 'no'} ({review_count} review(s))"
        )

        if self.config.dry_run:
            return SyncResult(
                posted=False,
                message=(
                    "Dry run enabled: would upsert "
                    f"value={value} to {resolved_goal_slug} for {day.isoformat()}."
                ),
            )

        request = CreateDatapointRequest(
            value=value,
            daystamp=daystamp(day),
            comment=comment,
            requestid=requestid,
        )
        existing = self._find_datapoint_for_day(
            username=username,
            goal_slug=resolved_goal_slug,
            day=day,
            requestid=requestid,
            requestid_prefix=REQUEST_ID_PREFIX_COMPLETION,
            prefetched_datapoints=prefetched_datapoints,
        )

        if existing is not None:
            if int(existing.value) == int(value):
                return SyncResult(
                    posted=False,
                    message=(
                        f"Beeminder already has {day.isoformat()} completion "
                        f"({int(value)}); no update needed."
                    ),
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
                message=f"Updated Beeminder completion for {day.isoformat()} to {int(value)}.",
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
            message=f"Created Beeminder completion for {day.isoformat()} with value {int(value)}.",
            datapoint=created,
        )

    def sync_date_range(
        self,
        start: date_type,
        end: date_type,
        goal_slug: str = "",
        precomputed_counts: dict[date_type, int] | None = None,
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

        return self._sync_date_range_generic(
            start=start,
            end=end,
            username=username,
            resolved_goal_slug=resolved_goal_slug,
            sync_day=self.sync_day_total,
            dry_run_value_fn=lambda count: count,
            summary_label="total reviews",
            precomputed_counts=precomputed_counts,
        )

    def sync_completion_date_range(
        self,
        start: date_type,
        end: date_type,
        goal_slug: str = "",
        precomputed_counts: dict[date_type, int] | None = None,
    ) -> DateRangeSyncResult:
        """Sync binary completion datapoints for all dates in [start, end].

        Structurally mirrors ``sync_date_range``, but calls
        ``sync_day_completion`` per day. Unlike ``sync_date_range``, this
        must NOT skip zero-review days -- posting ``value=0.0`` on days with
        no reviews is the point of the completion signal. As a result,
        ``total_reviews`` on the returned ``DateRangeSyncResult`` does not
        mean "review count" here; it is the sum of posted 0/1 completion
        values, i.e. the number of days completed within the range.
        """
        username = self.config.beeminder_username
        resolved_goal_slug = goal_slug or self.config.review_completion_goal_slug
        if not username or not resolved_goal_slug:
            return _empty_date_range_result(
                "Beeminder username and completion goal slug are required before syncing."
            )

        if self._completion_goal_conflicts_with_count_goal(resolved_goal_slug):
            return _empty_date_range_result(
                self._goal_slug_conflict_message(resolved_goal_slug), blocked=True
            )

        return self._sync_date_range_generic(
            start=start,
            end=end,
            username=username,
            resolved_goal_slug=resolved_goal_slug,
            sync_day=self.sync_day_completion,
            dry_run_value_fn=lambda count: 1 if count > 0 else 0,
            summary_label="days completed",
            precomputed_counts=precomputed_counts,
        )

    def _sync_date_range_generic(
        self,
        start: date_type,
        end: date_type,
        username: str,
        resolved_goal_slug: str,
        sync_day: Callable[..., SyncResult],
        dry_run_value_fn: Callable[[int], int],
        summary_label: str,
        precomputed_counts: dict[date_type, int] | None,
    ) -> DateRangeSyncResult:
        """Shared range-sync loop for ``sync_date_range``/``sync_completion_date_range``.

        Both callers only differ in which per-day method to call, how a
        dry-run day's review count maps onto the aggregate ``total_reviews``
        tally, and the label for that tally in the summary message -- every
        other piece of range-sync bookkeeping (validation, prefetch sizing,
        the days_synced/skipped/failed loop, per-day error handling, and
        last-successful tracking) lives here once.
        """

        dates_to_sync = dates_between(start, end)
        if not dates_to_sync:
            return _empty_date_range_result("Invalid date range: start must be on or before end.")
        days = len(dates_to_sync) - 1

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
                # Computed once per day and shared with the per-day sync
                # call below (and reused for the dry-run tally) so the
                # revlog isn't queried twice for the same day -- and, when
                # ``precomputed_counts`` is supplied by the caller, not
                # queried again at all for a day already counted by a
                # sibling range-sync covering the same dates.
                review_count = (
                    precomputed_counts[day]
                    if precomputed_counts is not None and day in precomputed_counts
                    else self.review_count_source.count_reviews_for_day(day)
                )
                result = sync_day(
                    day=day,
                    goal_slug=resolved_goal_slug,
                    prefetched_datapoints=prefetched,
                    review_count=review_count,
                )
                per_day_results[day.isoformat()] = result

                if result.datapoint is not None:
                    total_reviews += int(result.datapoint.value)
                elif self.config.dry_run:
                    total_reviews += dry_run_value_fn(review_count)

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
        parts.append(f"{total_reviews} {summary_label}")
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
        requestid_prefix: str,
        prefetched_datapoints: list[DatapointResponse] | None = None,
    ) -> DatapointResponse | None:
        """Thin wrapper around the module-level ``find_datapoint_for_day``.

        Kept as a method (rather than inlining the call at each of this
        class's three call sites) so existing tests that call
        ``service._find_datapoint_for_day(...)`` directly keep working
        unchanged.
        """
        return find_datapoint_for_day(
            client=self.client,
            request_timeout_seconds=self.config.request_timeout_seconds,
            username=username,
            goal_slug=goal_slug,
            day=day,
            requestid=requestid,
            requestid_prefix=requestid_prefix,
            prefetched_datapoints=prefetched_datapoints,
        )
