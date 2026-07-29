import unittest

from ankiminder.beeminder.client import BeeminderClient
from ankiminder.beeminder.models import CreateDatapointRequest
from ankiminder.exceptions import BeeminderAuthError, BeeminderRequestError
from ankiminder.mocks.mock_transport import MockTransport


class TestBeeminderClient(unittest.TestCase):
    def test_create_datapoint_posts_payload(self) -> None:
        transport = MockTransport()
        transport.queue_json(
            200,
            {
                "id": "dp-1",
                "value": 2.0,
                "timestamp": 1,
                "comment": "ok",
            },
        )
        client = BeeminderClient(auth_token="token-1", transport=transport)
        result = client.create_datapoint(
            username="alice",
            goal_slug="anki",
            request=CreateDatapointRequest(value=2.0, comment="ok"),
        )
        self.assertEqual(result.id, "dp-1")
        self.assertEqual(transport.requests[0].data["auth_token"], "token-1")
        self.assertEqual(transport.requests[0].data["value"], 2.0)

    def test_auth_failure_raises_auth_error(self) -> None:
        transport = MockTransport()
        transport.queue_json(401, {"error": "bad token"})
        client = BeeminderClient(auth_token="bad", transport=transport)
        with self.assertRaises(BeeminderAuthError):
            client.get_user("alice")

    def test_update_datapoint_uses_put(self) -> None:
        transport = MockTransport()
        transport.queue_json(200, {"id": "dp-1", "value": 3.0, "timestamp": 1, "comment": "updated"})
        client = BeeminderClient(auth_token="token", transport=transport)
        result = client.update_datapoint(
            username="alice",
            goal_slug="anki",
            datapoint_id="dp-1",
            request=CreateDatapointRequest(value=3.0, comment="updated", requestid="rid-1"),
        )
        self.assertEqual(result.id, "dp-1")
        self.assertEqual(transport.requests[0].method, "PUT")
        self.assertEqual(transport.requests[0].data["requestid"], "rid-1")

    def test_list_datapoints_shape_validation(self) -> None:
        transport = MockTransport()
        transport.queue_json(200, {"unexpected": "object"})
        client = BeeminderClient(auth_token="token", transport=transport)
        with self.assertRaises(BeeminderRequestError):
            client.list_datapoints("alice", "anki")

    def test_username_and_goal_slug_are_percent_encoded_in_url(self) -> None:
        """A stray `/` or space in a self-typed goal slug must not alter the
        request path -- it should be encoded into the segment, not create
        new path segments."""
        transport = MockTransport()
        transport.queue_json(200, {"unexpected": "object"})
        client = BeeminderClient(auth_token="token", transport=transport)
        with self.assertRaises(BeeminderRequestError):
            client.list_datapoints("ali ce", "anki/reviews")

        url = transport.requests[0].url
        self.assertIn("/users/ali%20ce/goals/anki%2Freviews/datapoints.json", url)


if __name__ == "__main__":
    unittest.main()

