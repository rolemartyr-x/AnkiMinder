import unittest

from ankiminder.beeminder.models import CreateDatapointRequest, DatapointResponse


class TestModels(unittest.TestCase):
    def test_create_datapoint_request_payload(self) -> None:
        request = CreateDatapointRequest(
            value=3.5, timestamp=1738790400, comment="from test", requestid="req-1"
        )
        self.assertEqual(
            request.to_payload(),
            {
                "value": 3.5,
                "timestamp": 1738790400,
                "comment": "from test",
                "requestid": "req-1",
            },
        )

    def test_create_datapoint_request_payload_with_daystamp(self) -> None:
        request = CreateDatapointRequest(
            value=10.0, daystamp="20260220", comment="historical", requestid="req-2"
        )
        payload = request.to_payload()
        self.assertEqual(payload["daystamp"], "20260220")
        self.assertEqual(payload["value"], 10.0)
        self.assertNotIn("timestamp", payload)

    def test_datapoint_response_parsing(self) -> None:
        raw = {
            "id": "123",
            "value": 5,
            "timestamp": 1738790400,
            "comment": "ok",
            "daystamp": "20260202",
            "fulltext": "ok details",
        }
        parsed = DatapointResponse.from_json(raw)
        self.assertEqual(parsed.id, "123")
        self.assertEqual(parsed.value, 5.0)
        self.assertEqual(parsed.daystamp, "20260202")


if __name__ == "__main__":
    unittest.main()

