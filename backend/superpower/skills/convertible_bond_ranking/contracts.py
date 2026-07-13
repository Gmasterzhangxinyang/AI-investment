from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class CBStrategyIdentity:
    strategy_id: str
    strategy_version: str
    overlay_id: str
    overlay_version: str
    overlay_enabled: bool
    config_hash: str


@dataclass(frozen=True)
class CBBaseStrategyMetadata:
    strategy_id: str
    display_name: str
    version: str


@dataclass(frozen=True)
class CBAuxiliaryOverlayMetadata:
    overlay_id: str
    display_name: str
    version: str


class CBBaseStrategy(Protocol):
    strategy_id: str
    version: str


class CBAuxiliaryOverlay(Protocol):
    overlay_id: str
    version: str

    def evaluate(
        self,
        row: Mapping[str, Any],
        settings: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
