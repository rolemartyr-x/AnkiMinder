"""Transport abstraction for HTTP requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..exceptions import BeeminderRequestError

DEFAULT_TIMEOUT_SECONDS = 10

# Beeminder's user/datapoint JSON payloads are a few KB at most; this is a
# generous ceiling to guard against an unbounded/oversized response body
# (e.g. a misbehaving endpoint) being buffered entirely into memory.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


@dataclass
class HttpResponse:
    """Transport response container."""

    status_code: int
    body: str
    headers: dict[str, str]


class Transport(Protocol):
    """Interface for HTTP transport implementations."""

    def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        ...


class _HttpsOnlyRedirectHandler(HTTPRedirectHandler):
    """Refuses to follow a redirect whose target isn't HTTPS.

    Stdlib ``urlopen`` otherwise follows a redirect regardless of scheme,
    which would silently downgrade an HTTPS request (and the auth token
    riding along with it) to plaintext HTTP if a redirect to an ``http://``
    URL were ever encountered.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        if not newurl.lower().startswith("https://"):
            raise BeeminderRequestError(
                f"Refusing to follow insecure redirect to non-HTTPS URL: {newurl}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# A single opener reused across requests; `build_opener` swaps out the
# default `HTTPRedirectHandler` for the HTTPS-only variant above (it's a
# subclass, so `build_opener` skips adding the stock one).
_opener = build_opener(_HttpsOnlyRedirectHandler)


def _read_capped(fp: Any, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    """Read at most ``limit`` bytes from ``fp``, raising if more remain."""

    data = fp.read(limit + 1)
    if len(data) > limit:
        raise BeeminderRequestError("Beeminder response exceeded the maximum allowed size.")
    return data


class UrllibTransport:
    """Default transport using urllib from Python stdlib."""

    def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        query = urlencode(params or {}, doseq=True)
        url_with_query = f"{url}?{query}" if query else url
        payload = urlencode(data or {}, doseq=True).encode("utf-8") if data else None
        request = Request(url_with_query, data=payload, method=method.upper())
        request.add_header("Accept", "application/json")
        if payload is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with _opener.open(request, timeout=timeout_seconds) as response:
                body = _read_capped(response).decode("utf-8")
                return HttpResponse(
                    status_code=int(response.getcode()),
                    body=body,
                    headers={k: v for k, v in response.headers.items()},
                )
        except HTTPError as error:
            body = _read_capped(error).decode("utf-8")
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


def parse_json_object(response: HttpResponse) -> dict[str, Any]:
    """Decode JSON and require an object payload."""

    parsed = parse_json_body(response)
    if not isinstance(parsed, dict):
        raise BeeminderRequestError("Unexpected Beeminder response shape.")
    return parsed
