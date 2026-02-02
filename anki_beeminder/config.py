"""Configuration helpers for persisting add-on settings in Anki."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class AddonConfig:
    """User-editable settings for this add-on."""

    beeminder_username: str = ""
    beeminder_auth_token: str = ""
    default_goal_slug: str = ""
    request_timeout_seconds: int = 10
    dry_run: bool = True

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AddonConfig":
        data = dict(raw or {})
        return cls(
            beeminder_username=str(data.get("beeminder_username", "")).strip(),
            beeminder_auth_token=str(data.get("beeminder_auth_token", "")).strip(),
            default_goal_slug=str(data.get("default_goal_slug", "")).strip(),
            request_timeout_seconds=int(data.get("request_timeout_seconds", 10)),
            dry_run=bool(data.get("dry_run", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
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

