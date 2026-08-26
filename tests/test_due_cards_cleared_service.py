import unittest
from datetime import date

from ankiminder.beeminder.models import CreateDatapointRequest
from ankiminder.config import AddonConfig
from ankiminder.mocks.mock_client import MockBeeminderClient
from ankiminder.services.due_cards_cleared_service import (
    REQUEST_ID_PREFIX_DUE_CLEARED,
    AnkiDueCardCountSource,
    DueCardsClearedSyncService,
    request_id_for_due_cleared_day,
)
from ankiminder.services.review_count_service import (
    REQUEST_ID_PREFIX,
    REQUEST_ID_PREFIX_COMPLETION,
    request_id_for_completion_day,
    request_id_for_day,
)


class FakeDeckTreeNode:
    def __init__(self, deck_id=0, new_count=0, learn_count=0, review_count=0, children=()):
        self.deck_id = deck_id
        self.new_count = new_count
        self.learn_count = learn_count
        self.review_count = review_count
        self.children = list(children)


class FakeSched:
    def __init__(self, finished, tree=None):
        self._finished = finished
        self._tree = tree if tree is not None else FakeDeckTreeNode()

    def is_finished(self):
        return self._finished

    def deck_due_tree(self, did=None):
        return self._tree


class FakeDecks:
    def __init__(self, name_to_id):
        self._map = name_to_id

    def id_for_name(self, name):
        return self._map.get(name)


class FakeDueCardCountSource:
    def __init__(self, count):
        self.count = count

    def due_cards_remaining(self, included_deck_names=()):
        return self.count


class TestAnkiDueCardCountSource(unittest.TestCase):
    def test_finished_with_no_filter_returns_zero(self) -> None:
        source = AnkiDueCardCountSource(sched=FakeSched(finished=True), decks=FakeDecks({}))
        self.assertEqual(source.due_cards_remaining(), 0)

    def test_not_finished_with_no_filter_sums_tree(self) -> None:
        tree = FakeDeckTreeNode(
            children=[
                FakeDeckTreeNode(deck_id=1, new_count=2, learn_count=1, review_count=3),
                FakeDeckTreeNode(deck_id=2, new_count=0, learn_count=0, review_count=1),
            ]
        )
        source = AnkiDueCardCountSource(sched=FakeSched(finished=False, tree=tree), decks=FakeDecks({}))
        self.assertEqual(source.due_cards_remaining(), 7)

    def test_empty_collection_with_no_filter_is_vacuously_clear(self) -> None:
        source = AnkiDueCardCountSource(
            sched=FakeSched(finished=True, tree=FakeDeckTreeNode(children=[])),
            decks=FakeDecks({}),
        )
        self.assertEqual(source.due_cards_remaining(), 0)

    def test_deck_filter_matches_subtree_node(self) -> None:
        tree = FakeDeckTreeNode(
            children=[
                FakeDeckTreeNode(deck_id=1, new_count=2, learn_count=0, review_count=0),
                FakeDeckTreeNode(deck_id=2, new_count=0, learn_count=0, review_count=5),
            ]
        )
        source = AnkiDueCardCountSource(
            sched=FakeSched(finished=False, tree=tree),
            decks=FakeDecks({"Japanese": 2}),
        )
        self.assertEqual(source.due_cards_remaining(("Japanese",)), 5)

    def test_unresolvable_deck_name_contributes_zero_without_erroring(self) -> None:
        tree = FakeDeckTreeNode(children=[FakeDeckTreeNode(deck_id=1, new_count=3)])
        source = AnkiDueCardCountSource(
            sched=FakeSched(finished=False, tree=tree),
            decks=FakeDecks({}),
        )
        self.assertEqual(source.due_cards_remaining(("Typo'd Deck",)), 0)


class TestSyncTodayDueCleared(unittest.TestCase):
    def _make_service(self, count, dry_run=False, goal_slug="anki-due-cleared"):
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            due_cards_cleared_goal_slug=goal_slug,
            dry_run=dry_run,
        )
        client = MockBeeminderClient()
        service = DueCardsClearedSyncService(
            config=config,
            client=client,
            due_card_count_source=FakeDueCardCountSource(count=count),
        )
        return service, client

    def test_zero_due_posts_value_one(self) -> None:
        service, client = self._make_service(count=0)
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(client.calls[0][2].value, 1.0)

    def test_cards_remaining_posts_value_zero(self) -> None:
        service, client = self._make_service(count=5)
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(client.calls[0][2].value, 0.0)

    def _seed_existing(self, client, day, value, goal_slug="anki-due-cleared"):
        existing = client.create_datapoint(
            username="alice",
            goal_slug=goal_slug,
            request=CreateDatapointRequest(value=float(value), comment="existing"),
        )
        existing.daystamp = day.strftime("%Y%m%d")
        existing.timestamp = 1738454400
        existing.requestid = request_id_for_due_cleared_day(day, goal_slug)
        client.stored[existing.id] = existing
        return existing

    def test_sticky_does_not_downgrade_from_one_to_zero(self) -> None:
        """Already marked complete today; new due cards must not flip it back."""
        service, client = self._make_service(count=5)
        self._seed_existing(client, date(2026, 2, 2), value=1)
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("not downgrading", result.message)
        self.assertEqual(len(client.updated_calls), 0)

    def test_flip_zero_to_one_updates_datapoint(self) -> None:
        service, client = self._make_service(count=0)
        self._seed_existing(client, date(2026, 2, 2), value=0)
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertTrue(result.posted)
        self.assertEqual(len(client.updated_calls), 1)
        self.assertEqual(client.updated_calls[0][3].value, 1.0)

    def test_idempotent_no_op_when_existing_matches_zero(self) -> None:
        service, client = self._make_service(count=5)
        self._seed_existing(client, date(2026, 2, 2), value=0)
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("no update needed", result.message)
        self.assertEqual(len(client.updated_calls), 0)

    def test_goal_slug_collision_with_numeric_signal_is_blocked(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_count_goal_slug="shared",
            due_cards_cleared_goal_slug="shared",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = DueCardsClearedSyncService(
            config=config, client=client, due_card_count_source=FakeDueCardCountSource(count=0)
        )
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("must differ", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_goal_slug_collision_with_completion_signal_is_blocked(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            review_completion_goal_slug="shared",
            due_cards_cleared_goal_slug="shared",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = DueCardsClearedSyncService(
            config=config, client=client, due_card_count_source=FakeDueCardCountSource(count=0)
        )
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("must differ", result.message)
        self.assertEqual(len(client.calls), 0)

    def test_dry_run_makes_no_client_calls(self) -> None:
        service, client = self._make_service(count=0, dry_run=True)
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("Dry run", result.message)
        self.assertEqual(len(client.calls), 0)
        self.assertEqual(len(client.updated_calls), 0)

    def test_missing_goal_slug_does_not_fall_back(self) -> None:
        config = AddonConfig(
            beeminder_username="alice",
            beeminder_auth_token="token",
            due_cards_cleared_goal_slug="",
            default_goal_slug="anki-default",
            review_count_goal_slug="anki-reviews",
            dry_run=False,
        )
        client = MockBeeminderClient()
        service = DueCardsClearedSyncService(
            config=config, client=client, due_card_count_source=FakeDueCardCountSource(count=0)
        )
        result = service.sync_today(day=date(2026, 2, 2))
        self.assertFalse(result.posted)
        self.assertIn("required", result.message)
        self.assertEqual(len(client.calls), 0)


class TestRequestIdForDueClearedDay(unittest.TestCase):
    def test_format_and_distinctness_from_other_prefixes(self) -> None:
        day = date(2026, 2, 2)
        due_cleared_id = request_id_for_due_cleared_day(day, "anki-goal")
        self.assertEqual(due_cleared_id, "anki-due-cleared-anki-goal-2026-02-02")
        self.assertTrue(due_cleared_id.startswith(REQUEST_ID_PREFIX_DUE_CLEARED))

        count_id = request_id_for_day(day, "anki-goal")
        completion_id = request_id_for_completion_day(day, "anki-goal")
        self.assertNotEqual(due_cleared_id, count_id)
        self.assertNotEqual(due_cleared_id, completion_id)
        self.assertFalse(REQUEST_ID_PREFIX_DUE_CLEARED.startswith(REQUEST_ID_PREFIX))
        self.assertFalse(REQUEST_ID_PREFIX_DUE_CLEARED.startswith(REQUEST_ID_PREFIX_COMPLETION))


if __name__ == "__main__":
    unittest.main()
