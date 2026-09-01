"""Beeminder API client."""

from __future__ import annotations

from urllib.parse import quote

from ..exceptions import BeeminderAuthError, BeeminderRequestError
from .models import (
    CreateDatapointRequest,
    DatapointResponse,
    UserResponse,
)
from .transport import (
    DEFAULT_TIMEOUT_SECONDS,
    HttpResponse,
    Transport,
    UrllibTransport,
    parse_json_body,
    parse_json_object,
)

DEFAULT_BASE_URL = "https://www.beeminder.com/api/v1"


class BeeminderClient:
    """Thin wrapper around Beeminder v1 API endpoints."""

    def __init__(
        self,
        auth_token: str,
        transport: Transport | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self._auth_token = auth_token.strip()
        self._transport = transport or UrllibTransport()
        self._base_url = base_url.rstrip("/")

    def get_user(self, username: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> UserResponse:
        response = self._transport.request(
            method="GET",
            url=f"{self._base_url}/users/{quote(username, safe='')}.json",
            params={"auth_token": self._auth_token},
            timeout_seconds=timeout_seconds,
        )
        payload = self._parse_and_raise(response.status_code, response)
        return UserResponse.from_json(payload)

    def create_datapoint(
        self,
        username: str,
        goal_slug: str,
        request: CreateDatapointRequest,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> DatapointResponse:
        response = self._transport.request(
            method="POST",
            url=(
                f"{self._base_url}/users/{quote(username, safe='')}"
                f"/goals/{quote(goal_slug, safe='')}/datapoints.json"
            ),
            data={"auth_token": self._auth_token, **request.to_payload()},
            timeout_seconds=timeout_seconds,
        )
        payload = self._parse_and_raise(response.status_code, response)
        return DatapointResponse.from_json(payload)

    def list_datapoints(
        self,
        username: str,
        goal_slug: str,
        count: int = 7,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> list[DatapointResponse]:
        response = self._transport.request(
            method="GET",
            url=(
                f"{self._base_url}/users/{quote(username, safe='')}"
                f"/goals/{quote(goal_slug, safe='')}/datapoints.json"
            ),
            params={"auth_token": self._auth_token, "count": count},
            timeout_seconds=timeout_seconds,
        )
        if response.status_code >= 400:
            self._parse_and_raise(response.status_code, response)
        payload = parse_json_body(response)
        if not isinstance(payload, list):
            raise BeeminderRequestError("Expected a list of datapoints from Beeminder.")
        return [DatapointResponse.from_json(item) for item in payload if isinstance(item, dict)]

    def update_datapoint(
        self,
        username: str,
        goal_slug: str,
        datapoint_id: str,
        request: CreateDatapointRequest,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> DatapointResponse:
        response = self._transport.request(
            method="PUT",
            url=(
                f"{self._base_url}/users/{quote(username, safe='')}"
                f"/goals/{quote(goal_slug, safe='')}"
                f"/datapoints/{quote(datapoint_id, safe='')}.json"
            ),
            data={"auth_token": self._auth_token, **request.to_payload()},
            timeout_seconds=timeout_seconds,
        )
        payload = self._parse_and_raise(response.status_code, response)
        return DatapointResponse.from_json(payload)

    @staticmethod
    def _parse_and_raise(status_code: int, response: HttpResponse) -> dict:
        payload = parse_json_object(response)
        if status_code < 400:
            return payload
        message = str(payload.get("errors") or payload.get("error") or "Unknown Beeminder error")
        if status_code in (401, 403):
            raise BeeminderAuthError(message)
        raise BeeminderRequestError(message)
