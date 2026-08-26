"""Service layer for syncing Anki-derived values to Beeminder."""

from __future__ import annotations

from dataclasses import dataclass

from ..beeminder.client import BeeminderClient
from ..beeminder.models import CreateDatapointRequest, DatapointResponse
from ..config import AddonConfig


@dataclass
class SyncResult:
    """Return value for sync operations."""

    posted: bool
    message: str
    datapoint: DatapointResponse | None = None
    # True when a guard (e.g. a goal-slug collision) refused to run at all,
    # as distinct from an ordinary non-post outcome (skip/no-op/dry-run).
    # Mirrors ``DateRangeSyncResult.blocked``.
    blocked: bool = False


class SyncService:
    """Coordinates config + Beeminder client usage."""

    def __init__(self, config: AddonConfig, client: BeeminderClient):
        self._config = config
        self._client = client

    def send_value(
        self,
        value: float,
        comment: str = "",
        goal_slug: str = "",
    ) -> SyncResult:
        username = self._config.beeminder_username
        resolved_goal_slug = goal_slug or self._config.default_goal_slug
        if not username or not resolved_goal_slug:
            return SyncResult(
                posted=False,
                message="Beeminder username and goal slug are required before syncing.",
            )
        if self._config.dry_run:
            return SyncResult(
                posted=False,
                message=f"Dry run enabled: would send value={value} to {resolved_goal_slug}.",
            )

        request = CreateDatapointRequest(value=value, comment=comment)
        datapoint = self._client.create_datapoint(
            username=username,
            goal_slug=resolved_goal_slug,
            request=request,
            timeout_seconds=self._config.request_timeout_seconds,
        )
        return SyncResult(
            posted=True,
            message=f"Sent value={value} to Beeminder goal '{resolved_goal_slug}'.",
            datapoint=datapoint,
        )

