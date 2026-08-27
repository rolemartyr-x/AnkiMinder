"""Due-card detection and sync helpers for the "all reviews cleared" signal.

Unlike ``review_count_service``'s revlog-based signals, this reads Anki's
*scheduler* state -- a point-in-time snapshot of what's still due, not a
historical ledger. There is no way to retroactively ask "were all cards
cleared on 2026-08-20"; this signal only ever computes and writes "today",
live, at the moment sync runs. There is deliberately no date-range/backfill
sync here (contrast ``sync_date_range``/``sync_completion_date_range`` in
``review_count_service``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Any, Protocol

from ..beeminder.client import BeeminderClient
from ..beeminder.models import CreateDatapointRequest, DatapointResponse
from ..config import AddonConfig
from .review_count_service import daystamp, find_datapoint_for_day
from .sync_service import SyncResult

REQUEST_ID_PREFIX_DUE_CLEARED = "anki-due-cleared"


def request_id_for_due_cleared_day(day: date_type, goal_slug: str) -> str:
    """Deterministic requestid so one day maps to one due-cleared datapoint.

    Distinct prefix from both ``REQUEST_ID_PREFIX``/``REQUEST_ID_PREFIX_COMPLETION``
    (see ``review_count_service``) so this signal can never collide with
    either of the other two, even if all three ever target the same goal.
    """

    return f"{REQUEST_ID_PREFIX_DUE_CLEARED}-{goal_slug}-{day.isoformat()}"


class DueCardCountSource(Protocol):
    """Abstraction for retrieving the number of cards still due right now."""

    def due_cards_remaining(self, included_deck_names: tuple[str, ...] = ()) -> int:
        ...


@dataclass
class AnkiDueCardCountSource:
    """Reads remaining due-card counts from Anki's scheduler.

    Takes ``sched``/``decks`` (not the whole ``col``) so tests can fake just
    the two sub-objects this class actually touches, mirroring
    ``AnkiReviewCountSource``'s ``db``-only dependency.
    """

    sched: Any
    decks: Any

    def due_cards_remaining(self, included_deck_names: tuple[str, ...] = ()) -> int:
        if not included_deck_names:
            # ``Scheduler.is_finished()`` only exists on the legacy V1/V2
            # Python schedulers, not the modern Rust-backed one exposed as
            # ``col.sched`` in current Anki -- confirmed by a real
            # AttributeError from a live install. ``deck_due_tree`` is the
            # stable, version-independent API (also used by Anki's own deck
            # browser to render its totals), so it's used for both the
            # unfiltered and filtered cases rather than special-casing the
            # unfiltered one.
            return self._sum_due_tree(None)

        included_ids = self._resolve_deck_ids(included_deck_names)
        if not included_ids:
            # A filter was requested but none of the names resolved to a
            # real deck (e.g. all typos) -- that's zero tracked due cards,
            # not "no filter" (which would wrongly fall back to the whole
            # collection).
            return 0
        return self._sum_due_tree(included_ids)

    def _resolve_deck_ids(self, names: tuple[str, ...]) -> frozenset[int]:
        ids: set[int] = set()
        for name in names:
            deck_id = self.decks.id_for_name(name)
            if deck_id is not None:
                ids.add(int(deck_id))
        return frozenset(ids)

    def _sum_due_tree(self, included_ids: frozenset[int] | None) -> int:
        root = self.sched.deck_due_tree(did=None)
        if included_ids is None:
            return sum(_node_total(child) for child in root.children)
        return sum(
            _node_total(node) for node in _find_nodes(root, included_ids)
        )


def _node_total(node: Any) -> int:
    return int(node.new_count) + int(node.learn_count) + int(node.review_count)


def _find_nodes(node: Any, deck_ids: frozenset[int]) -> list[Any]:
    matches: list[Any] = []
    for child in node.children:
        if int(child.deck_id) in deck_ids:
            matches.append(child)
        else:
            matches.extend(_find_nodes(child, deck_ids))
    return matches


@dataclass
class DueCardsClearedSyncService:
    """Upserts a sticky binary "all due cards cleared today" Beeminder datapoint."""

    config: AddonConfig
    client: BeeminderClient
    due_card_count_source: DueCardCountSource

    @classmethod
    def from_config(
        cls,
        config: AddonConfig,
        due_card_count_source: DueCardCountSource,
    ) -> "DueCardsClearedSyncService":
        client = BeeminderClient(auth_token=config.beeminder_auth_token)
        return cls(config=config, client=client, due_card_count_source=due_card_count_source)

    def _goal_slug_conflicts_with_other_signals(self, resolved_slug: str) -> bool:
        numeric_slug = self.config.review_count_goal_slug or self.config.default_goal_slug
        completion_slug = self.config.review_completion_goal_slug
        other_slugs = {slug for slug in (numeric_slug, completion_slug) if slug}
        return resolved_slug in other_slugs

    @staticmethod
    def _goal_slug_conflict_message(resolved_slug: str) -> str:
        return (
            f"due_cards_cleared_goal_slug ('{resolved_slug}') must differ from "
            "review_count_goal_slug/default_goal_slug and from "
            "review_completion_goal_slug; refusing to sync due-cards-cleared data "
            "to avoid overwriting another signal's datapoints. See config.md."
        )

    def sync_today(
        self,
        day: date_type,
        goal_slug: str = "",
        prefetched_datapoints: list[DatapointResponse] | None = None,
        due_count: int | None = None,
    ) -> SyncResult:
        """Upsert a binary (0/1) "all due cards cleared" datapoint for ``day``.

        Sticky: once today's datapoint reads ``1`` (all clear), a later
        sync the same day that finds new due cards will NOT downgrade it
        back to ``0`` -- clearing your queue once counts for the day even
        if more cards (e.g. learning-step returns, or newly added cards)
        become due afterward.
        """
        username = self.config.beeminder_username
        resolved_goal_slug = goal_slug or self.config.due_cards_cleared_goal_slug
        if not username or not resolved_goal_slug:
            return SyncResult(
                posted=False,
                message="Beeminder username and due-cards-cleared goal slug are required before syncing.",
            )

        if self._goal_slug_conflicts_with_other_signals(resolved_goal_slug):
            return SyncResult(
                posted=False,
                message=self._goal_slug_conflict_message(resolved_goal_slug),
                blocked=True,
            )

        requestid = request_id_for_due_cleared_day(day, resolved_goal_slug)
        existing = None
        if not self.config.dry_run:
            existing = find_datapoint_for_day(
                client=self.client,
                request_timeout_seconds=self.config.request_timeout_seconds,
                username=username,
                goal_slug=resolved_goal_slug,
                day=day,
                requestid=requestid,
                requestid_prefix=REQUEST_ID_PREFIX_DUE_CLEARED,
                prefetched_datapoints=prefetched_datapoints,
            )
            if existing is not None and int(existing.value) == 1:
                return SyncResult(
                    posted=False,
                    message=(
                        f"Beeminder already shows {day.isoformat()} as fully cleared (1); "
                        "not downgrading."
                    ),
                    datapoint=existing,
                )

        if due_count is None:
            due_count = self.due_card_count_source.due_cards_remaining(
                tuple(self.config.due_cards_cleared_deck_names)
            )
        value = 1.0 if due_count == 0 else 0.0
        comment = (
            f"Anki due cards for {day.isoformat()}: "
            f"{'all clear' if value else f'{due_count} still due'}"
        )

        if self.config.dry_run:
            return SyncResult(
                posted=False,
                message=(
                    "Dry run enabled: would upsert "
                    f"value={value} to {resolved_goal_slug} for {day.isoformat()}."
                ),
            )

        request = CreateDatapointRequest(
            value=value,
            daystamp=daystamp(day),
            comment=comment,
            requestid=requestid,
        )

        if existing is not None:
            if int(existing.value) == int(value):
                return SyncResult(
                    posted=False,
                    message=(
                        f"Beeminder already has {day.isoformat()} due-cleared "
                        f"({int(value)}); no update needed."
                    ),
                    datapoint=existing,
                )
            updated = self.client.update_datapoint(
                username=username,
                goal_slug=resolved_goal_slug,
                datapoint_id=existing.id,
                request=request,
                timeout_seconds=self.config.request_timeout_seconds,
            )
            return SyncResult(
                posted=True,
                message=f"Updated Beeminder due-cleared for {day.isoformat()} to {int(value)}.",
                datapoint=updated,
            )

        created = self.client.create_datapoint(
            username=username,
            goal_slug=resolved_goal_slug,
            request=request,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        return SyncResult(
            posted=True,
            message=f"Created Beeminder due-cleared for {day.isoformat()} with value {int(value)}.",
            datapoint=created,
        )
