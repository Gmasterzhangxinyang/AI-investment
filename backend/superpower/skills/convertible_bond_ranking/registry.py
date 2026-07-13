from __future__ import annotations

from collections.abc import Callable

from .contracts import CBBaseStrategy, CBBaseStrategyMetadata, CBAuxiliaryOverlay, CBAuxiliaryOverlayMetadata
from .strategy import CBConfigurationError


class CBStrategyRegistry:
    def __init__(self) -> None:
        self._bases: dict[str, tuple[CBBaseStrategyMetadata, Callable[[], CBBaseStrategy]]] = {}
        self._overlays: dict[str, tuple[CBAuxiliaryOverlayMetadata, Callable[[], CBAuxiliaryOverlay]]] = {}

    def register_base(self, metadata: CBBaseStrategyMetadata, constructor: Callable[[], CBBaseStrategy]) -> None:
        if metadata.strategy_id in self._bases:
            raise CBConfigurationError(f"duplicate convertible-bond base strategy: {metadata.strategy_id}")
        self._bases[metadata.strategy_id] = (metadata, constructor)

    def register_overlay(
        self,
        metadata: CBAuxiliaryOverlayMetadata,
        constructor: Callable[[], CBAuxiliaryOverlay],
    ) -> None:
        if metadata.overlay_id in self._overlays:
            raise CBConfigurationError(f"duplicate convertible-bond auxiliary overlay: {metadata.overlay_id}")
        self._overlays[metadata.overlay_id] = (metadata, constructor)

    def base(self, strategy_id: str) -> CBBaseStrategy:
        try:
            return self._bases[strategy_id][1]()
        except KeyError as exc:
            raise CBConfigurationError(f"unknown convertible-bond base strategy: {strategy_id}") from exc

    def overlay(self, overlay_id: str) -> CBAuxiliaryOverlay:
        try:
            return self._overlays[overlay_id][1]()
        except KeyError as exc:
            raise CBConfigurationError(f"unknown convertible-bond auxiliary overlay: {overlay_id}") from exc

    def base_metadata(self) -> tuple[CBBaseStrategyMetadata, ...]:
        return tuple(self._bases[key][0] for key in sorted(self._bases))

    def overlay_metadata(self) -> tuple[CBAuxiliaryOverlayMetadata, ...]:
        return tuple(self._overlays[key][0] for key in sorted(self._overlays))


def default_cb_registry() -> CBStrategyRegistry:
    from .overlays.dynamic_v2 import DynamicV2Overlay
    from .strategies.legacy_v1 import LegacyV1Strategy

    registry = CBStrategyRegistry()
    registry.register_base(CBBaseStrategyMetadata("legacy_v1", "原策略", "1.0.0"), LegacyV1Strategy)
    registry.register_overlay(CBAuxiliaryOverlayMetadata("dynamic_v2", "动态辅助", "2.0.0"), DynamicV2Overlay)
    return registry
