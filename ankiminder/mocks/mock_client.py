"""Mock Beeminder client for higher-level tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..beeminder.models import CreateDatapointRequest, DatapointResponse


@dataclass
class MockBeeminderClient:
    """In-memory fake client that records datapoint calls."""

    created: List[DatapointResponse] = field(default_factory=list)
    calls: List[tuple[str, str, CreateDatapointRequest, int]] = field(default_factory=list)
    updated_calls: List[tuple[str, str, str, CreateDatapointRequest, int]] = field(default_factory=list)
    stored: Dict[str, DatapointResponse] = field(default_factory=dict)

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
            requestid=request.requestid,
        )
        self.created.append(datapoint)
        self.stored[datapoint.id] = datapoint
        return datapoint

    def update_datapoint(
        self,
        username: str,
        goal_slug: str,
        datapoint_id: str,
        request: CreateDatapointRequest,
        timeout_seconds: int = 10,
    ) -> DatapointResponse:
        self.updated_calls.append((username, goal_slug, datapoint_id, request, timeout_seconds))
        datapoint = DatapointResponse(
            id=datapoint_id,
            value=request.value,
            timestamp=request.timestamp or 0,
            comment=request.comment,
            requestid=request.requestid,
        )
        self.stored[datapoint_id] = datapoint
        return datapoint

    def list_datapoints(
        self,
        username: str,
        goal_slug: str,
        count: int = 7,
        timeout_seconds: int = 10,
    ) -> List[DatapointResponse]:
        _ = (username, goal_slug, count, timeout_seconds)
        return list(self.stored.values())

