from __future__ import annotations

from collections.abc import Callable

from .config import ETFConfigurationError
from .contracts import ETFStrategy, ETFStrategyMetadata


class ETFStrategyRegistry:
    def __init__(self) -> None:
        self._constructors: dict[str, Callable[[], ETFStrategy]] = {}
        self._metadata: dict[str, ETFStrategyMetadata] = {}

    def register(
        self,
        metadata: ETFStrategyMetadata,
        constructor: Callable[[], ETFStrategy],
    ) -> None:
        if metadata.strategy_id in self._constructors:
            raise ETFConfigurationError(f"duplicate ETF strategy: {metadata.strategy_id}")
        self._constructors[metadata.strategy_id] = constructor
        self._metadata[metadata.strategy_id] = metadata

    def create(self, strategy_id: str) -> ETFStrategy:
        try:
            return self._constructors[strategy_id]()
        except KeyError as exc:
            raise ETFConfigurationError(f"unknown active ETF strategy: {strategy_id}") from exc

    def metadata(self) -> tuple[ETFStrategyMetadata, ...]:
        return tuple(self._metadata[key] for key in sorted(self._metadata))

    def get_metadata(self, strategy_id: str) -> ETFStrategyMetadata:
        try:
            return self._metadata[strategy_id]
        except KeyError as exc:
            raise ETFConfigurationError(f"unknown ETF strategy metadata: {strategy_id}") from exc


def default_registry() -> ETFStrategyRegistry:
    from .strategies.legacy_v1 import LegacyV1Strategy

    registry = ETFStrategyRegistry()
    registry.register(
        ETFStrategyMetadata(
            strategy_id="legacy_v1",
            display_name="原始策略",
            version="1.0.0",
            default_params={},
            parameter_schema={},
        ),
        LegacyV1Strategy,
    )
    return registry
