"""Transport abstraction for HTTP requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..exceptions import BeeminderRequestError


@dataclass
class HttpResponse:
    """Transport response container."""

    status_code: int
    body: str
    headers: Dict[str, str]


class Transport(Protocol):
    """Interface for HTTP transport implementations."""

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 10,
    ) -> HttpResponse:
        ...


class UrllibTransport:
    """Default transport using urllib from Python stdlib."""

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 10,
    ) -> HttpResponse:
        query = urlencode(params or {}, doseq=True)
        url_with_query = f"{url}?{query}" if query else url
        payload = urlencode(data or {}, doseq=True).encode("utf-8") if data else None
        request = Request(url_with_query, data=payload, method=method.upper())
        request.add_header("Accept", "application/json")
        if payload is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return HttpResponse(
                    status_code=int(response.getcode()),
                    body=body,
                    headers={k: v for k, v in response.headers.items()},
                )
        except HTTPError as error:
            body = error.read().decode("utf-8")
            return HttpResponse(
                status_code=int(error.code),
                body=body,
                headers={k: v for k, v in error.headers.items()},
            )
        except URLError as error:
            raise BeeminderRequestError(f"Network error while calling Beeminder: {error}") from error


def parse_json_body(response: HttpResponse) -> Any:
    """Decode a JSON response body."""

    try:
        parsed = json.loads(response.body or "{}")
    except json.JSONDecodeError as error:
        raise BeeminderRequestError("Beeminder returned invalid JSON.") from error
    return parsed


def parse_json_object(response: HttpResponse) -> Dict[str, Any]:
    """Decode JSON and require an object payload."""

    parsed = parse_json_body(response)
    if not isinstance(parsed, dict):
        raise BeeminderRequestError("Unexpected Beeminder response shape.")
    return parsed
