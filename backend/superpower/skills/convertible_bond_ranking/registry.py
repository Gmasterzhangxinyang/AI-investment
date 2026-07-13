from __future__ import annotations

from .contracts import CBBaseStrategyMetadata, CBAuxiliaryOverlayMetadata
from .strategy import CBConfigurationError


class CBStrategyRegistry:
    def __init__(self) -> None:
        self._bases: dict[str, CBBaseStrategyMetadata] = {}
        self._overlays: dict[str, CBAuxiliaryOverlayMetadata] = {}

    def register_base(self, metadata: CBBaseStrategyMetadata) -> None:
        if metadata.strategy_id in self._bases:
            raise CBConfigurationError(f"duplicate convertible-bond base strategy: {metadata.strategy_id}")
        self._bases[metadata.strategy_id] = metadata

    def register_overlay(self, metadata: CBAuxiliaryOverlayMetadata) -> None:
        if metadata.overlay_id in self._overlays:
            raise CBConfigurationError(f"duplicate convertible-bond auxiliary overlay: {metadata.overlay_id}")
        self._overlays[metadata.overlay_id] = metadata

    def base(self, strategy_id: str) -> CBBaseStrategyMetadata:
        try:
            return self._bases[strategy_id]
        except KeyError as exc:
            raise CBConfigurationError(f"unknown convertible-bond base strategy: {strategy_id}") from exc

    def overlay(self, overlay_id: str) -> CBAuxiliaryOverlayMetadata:
        try:
            return self._overlays[overlay_id]
        except KeyError as exc:
            raise CBConfigurationError(f"unknown convertible-bond auxiliary overlay: {overlay_id}") from exc

    def base_metadata(self) -> tuple[CBBaseStrategyMetadata, ...]:
        return tuple(self._bases[key] for key in sorted(self._bases))

    def overlay_metadata(self) -> tuple[CBAuxiliaryOverlayMetadata, ...]:
        return tuple(self._overlays[key] for key in sorted(self._overlays))


def default_cb_registry() -> CBStrategyRegistry:
    registry = CBStrategyRegistry()
    registry.register_base(CBBaseStrategyMetadata("legacy_v1", "原策略", "1.0.0"))
    registry.register_overlay(CBAuxiliaryOverlayMetadata("dynamic_v2", "动态辅助", "2.0.0"))
    return registry
