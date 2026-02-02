"""Mock Beeminder client for higher-level tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from anki_beeminder.beeminder.models import CreateDatapointRequest, DatapointResponse


@dataclass
class MockBeeminderClient:
    """In-memory fake client that records datapoint calls."""

    created: List[DatapointResponse] = field(default_factory=list)
    calls: List[tuple[str, str, CreateDatapointRequest, int]] = field(default_factory=list)

    def create_datapoint(
        self,
        username: str,
        goal_slug: str,
        request: CreateDatapointRequest,
        timeout_seconds: int = 10,
    ) -> DatapointResponse:
        self.calls.append((username, goal_slug, request, timeout_seconds))
        datapoint = DatapointResponse(
            id=f"mock-{len(self.calls)}",
            value=request.value,
            timestamp=request.timestamp or 0,
            comment=request.comment,
        )
        self.created.append(datapoint)
        return datapoint

