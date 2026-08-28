import unittest
from urllib.request import Request

from ankiminder.beeminder.transport import (
    MAX_RESPONSE_BYTES,
    _HttpsOnlyRedirectHandler,
    _read_capped,
)
from ankiminder.exceptions import BeeminderRequestError


class FakeReadable:
    """Minimal stand-in for an `http.client.HTTPResponse`/`HTTPError`, which
    both expose a `.read(size)` method."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, size: int) -> bytes:
        return self._body[:size]


class TestReadCapped(unittest.TestCase):
    def test_body_under_limit_is_returned_whole(self) -> None:
        body = b'{"ok": true}'
        self.assertEqual(_read_capped(FakeReadable(body), limit=1024), body)

    def test_body_exactly_at_limit_is_returned_whole(self) -> None:
        body = b"x" * 10
        self.assertEqual(_read_capped(FakeReadable(body), limit=10), body)

    def test_body_over_limit_raises(self) -> None:
        body = b"x" * 11
        with self.assertRaises(BeeminderRequestError):
            _read_capped(FakeReadable(body), limit=10)

    def test_default_limit_is_generous_but_bounded(self) -> None:
        self.assertGreater(MAX_RESPONSE_BYTES, 1024 * 1024)
        small_body = b'{"ok": true}'
        self.assertEqual(_read_capped(FakeReadable(small_body)), small_body)


class TestHttpsOnlyRedirectHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = _HttpsOnlyRedirectHandler()
        self.req = Request("https://www.beeminder.com/api/v1/users/alice.json")

    def test_https_redirect_target_is_allowed(self) -> None:
        new_request = self.handler.redirect_request(
            self.req,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="https://www.beeminder.com/api/v1/users/alice/goals.json",
        )
        self.assertIsNotNone(new_request)
        self.assertTrue(new_request.full_url.startswith("https://"))

    def test_http_redirect_target_is_refused(self) -> None:
        with self.assertRaises(BeeminderRequestError):
            self.handler.redirect_request(
                self.req,
                fp=None,
                code=302,
                msg="Found",
                headers={},
                newurl="http://www.beeminder.com/api/v1/users/alice/goals.json",
            )

    def test_scheme_check_is_case_insensitive(self) -> None:
        new_request = self.handler.redirect_request(
            self.req,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="HTTPS://www.beeminder.com/api/v1/users/alice/goals.json",
        )
        self.assertIsNotNone(new_request)


if __name__ == "__main__":
    unittest.main()
