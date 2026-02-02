import unittest

from anki_beeminder.config import AddonConfig
from anki_beeminder.mocks.mock_client import MockBeeminderClient
from anki_beeminder.services.sync_service import SyncService


class TestSyncService(unittest.TestCase):
    def test_dry_run_does_not_post(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="t",
            default_goal_slug="anki",
            dry_run=True,
        )
        client = MockBeeminderClient()
        service = SyncService(config=config, client=client)
        result = service.send_value(1.0, "dry")
        self.assertFalse(result.posted)
        self.assertEqual(len(client.calls), 0)

    def test_posts_when_dry_run_disabled(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="t",
            default_goal_slug="anki",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = SyncService(config=config, client=client)
        result = service.send_value(4.0, "real")
        self.assertTrue(result.posted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1], "anki")


if __name__ == "__main__":
    unittest.main()

