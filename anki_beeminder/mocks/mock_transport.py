"""Mock HTTP transport for tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..beeminder.transport import HttpResponse


@dataclass
class RecordedRequest:
    method: str
    url: str
    params: Dict[str, Any]
    data: Dict[str, Any]
    timeout_seconds: int


@dataclass
class MockTransport:
    """Queue-based transport stub that records calls."""

    queued_responses: List[HttpResponse] = field(default_factory=list)
    requests: List[RecordedRequest] = field(default_factory=list)

    def queue_json(self, status_code: int, payload: Any) -> None:
        self.queued_responses.append(
            HttpResponse(status_code=status_code, body=json.dumps(payload), headers={})
        )

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 10,
    ) -> HttpResponse:
        self.requests.append(
            RecordedRequest(
                method=method,
                url=url,
                params=params or {},
                data=data or {},
                timeout_seconds=timeout_seconds,
            )
        )
        if not self.queued_responses:
            return HttpResponse(status_code=500, body='{"error":"No queued response"}', headers={})
        return self.queued_responses.pop(0)

