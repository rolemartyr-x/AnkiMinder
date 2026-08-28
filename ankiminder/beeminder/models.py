"""Data models for Beeminder API requests and responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CreateDatapointRequest:
    """Request payload for creating a Beeminder datapoint."""

    value: float
    timestamp: int | None = None
    daystamp: str = ""
    comment: str = ""
    requestid: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"value": self.value}
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        if self.daystamp:
            payload["daystamp"] = self.daystamp
        if self.comment:
            payload["comment"] = self.comment
        if self.requestid:
            payload["requestid"] = self.requestid
        return payload


@dataclass
class DatapointResponse:
    """Subset of Beeminder datapoint response fields."""

    id: str
    value: float
    timestamp: int
    comment: str = ""
    requestid: str = ""
    daystamp: str = ""
    fulltext: str = ""

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "DatapointResponse":
        return cls(
            id=str(raw.get("id", "")),
            value=float(raw.get("value", 0.0)),
            timestamp=int(raw.get("timestamp", 0)),
            comment=str(raw.get("comment", "")),
            # `or ""` (not `str(raw.get("requestid", ""))`) so an explicit
            # JSON `null` normalizes to "" the same as a missing key --
            # `str(None)` would otherwise produce the literal "None".
            requestid=str(raw.get("requestid") or ""),
            daystamp=str(raw.get("daystamp", "")),
            fulltext=str(raw.get("fulltext", "")),
        )


@dataclass
class UserResponse:
    """Minimal response model for user endpoint."""

    username: str
    timezone: str = ""

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "UserResponse":
        return cls(
            username=str(raw.get("username", "")),
            timezone=str(raw.get("timezone", "")),
        )

