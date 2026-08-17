"""Configuration helpers for persisting add-on settings in Anki."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_HISTORICAL_LOOKBACK_DAYS = 7
DEFAULT_LAST_REVIEW_COUNT_VALUE = -1
DEFAULT_LAST_REVIEW_COMPLETION_VALUE = -1


def _safe_int(value: Any, default: int) -> int:
    """Parse ``value`` as an int, falling back to ``default`` on bad input.

    Config data is user- and disk-editable, so a manually edited or corrupted
    ``config.json`` (e.g. a non-numeric string) must not crash add-on load.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    """Parse ``value`` as a bool without the ``bool("false") == True`` pitfall.

    JSON booleans decode to native ``bool`` already, but a hand-edited config
    can contain the *string* ``"false"``; naive ``bool(...)`` would treat that
    truthy string as ``True``.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no", ""):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


@dataclass
class AddonConfig:
    """User-editable settings for this add-on."""

    beeminder_username: str = ""
    beeminder_auth_token: str = ""
    default_goal_slug: str = ""
    review_count_goal_slug: str = ""
    review_completion_goal_slug: str = ""
    review_completion_sync_enabled: bool = False
    automation_enabled: bool = False
    automation_triggers: list[str] | None = None
    last_review_count_sync_date: str = ""
    last_review_count_value: int = DEFAULT_LAST_REVIEW_COUNT_VALUE
    last_review_count_datapoint_id: str = ""
    last_review_completion_sync_date: str = ""
    last_review_completion_value: int = DEFAULT_LAST_REVIEW_COMPLETION_VALUE
    last_review_completion_datapoint_id: str = ""
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS
    historical_lookback_days: int = DEFAULT_HISTORICAL_LOOKBACK_DAYS
    dry_run: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AddonConfig":
        data = dict(raw or {})
        raw_triggers = data.get("automation_triggers", ["sync"])
        if isinstance(raw_triggers, list):
            triggers = [str(item).strip() for item in raw_triggers if str(item).strip()]
        elif isinstance(raw_triggers, str):
            triggers = [raw_triggers.strip()] if raw_triggers.strip() else []
        else:
            triggers = ["sync"]

        timeout_seconds = _safe_int(
            data.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        if timeout_seconds <= 0:
            timeout_seconds = DEFAULT_REQUEST_TIMEOUT_SECONDS

        lookback_days = _safe_int(
            data.get("historical_lookback_days", DEFAULT_HISTORICAL_LOOKBACK_DAYS),
            DEFAULT_HISTORICAL_LOOKBACK_DAYS,
        )
        if lookback_days < 0:
            lookback_days = DEFAULT_HISTORICAL_LOOKBACK_DAYS

        return cls(
            beeminder_username=str(data.get("beeminder_username", "")).strip(),
            beeminder_auth_token=str(data.get("beeminder_auth_token", "")).strip(),
            default_goal_slug=str(data.get("default_goal_slug", "")).strip(),
            review_count_goal_slug=str(data.get("review_count_goal_slug", "")).strip(),
            review_completion_goal_slug=str(
                data.get("review_completion_goal_slug", "")
            ).strip(),
            review_completion_sync_enabled=_safe_bool(
                data.get("review_completion_sync_enabled", False), False
            ),
            automation_enabled=_safe_bool(data.get("automation_enabled", False), False),
            automation_triggers=triggers or ["sync"],
            last_review_count_sync_date=str(data.get("last_review_count_sync_date", "")).strip(),
            last_review_count_value=_safe_int(
                data.get("last_review_count_value", DEFAULT_LAST_REVIEW_COUNT_VALUE),
                DEFAULT_LAST_REVIEW_COUNT_VALUE,
            ),
            last_review_count_datapoint_id=str(
                data.get("last_review_count_datapoint_id", "")
            ).strip(),
            last_review_completion_sync_date=str(
                data.get("last_review_completion_sync_date", "")
            ).strip(),
            last_review_completion_value=_safe_int(
                data.get("last_review_completion_value", DEFAULT_LAST_REVIEW_COMPLETION_VALUE),
                DEFAULT_LAST_REVIEW_COMPLETION_VALUE,
            ),
            last_review_completion_datapoint_id=str(
                data.get("last_review_completion_datapoint_id", "")
            ).strip(),
            request_timeout_seconds=timeout_seconds,
            historical_lookback_days=lookback_days,
            dry_run=_safe_bool(data.get("dry_run", True), True),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigRepository:
    """Read/write config through Anki's addonManager."""

    def __init__(self, addon_manager: Any, addon_module_name: str):
        self._addon_manager = addon_manager
        self._addon_module_name = addon_module_name

    def load(self) -> AddonConfig:
        raw = self._addon_manager.getConfig(self._addon_module_name)
        return AddonConfig.from_dict(raw)

    def save(self, config: AddonConfig) -> None:
        self._addon_manager.writeConfig(self._addon_module_name, config.to_dict())
