from dataclasses import dataclass

import pytest

from superpower.skills.etf_rotation_strategy.config import ETFConfigurationError
from superpower.skills.etf_rotation_strategy.contracts import ETFStrategyMetadata
from superpower.skills.etf_rotation_strategy.registry import ETFStrategyRegistry


@dataclass
class StubStrategy:
    strategy_id: str = "stub"
    version: str = "1.0.0"


def metadata(strategy_id: str = "stub") -> ETFStrategyMetadata:
    return ETFStrategyMetadata(
        strategy_id=strategy_id,
        display_name="测试策略",
        version="1.0.0",
        default_params={},
        parameter_schema={},
    )


def test_registry_creates_only_explicitly_registered_strategy() -> None:
    registry = ETFStrategyRegistry()
    registry.register(metadata(), StubStrategy)

    strategy = registry.create("stub")

    assert strategy.strategy_id == "stub"
    assert registry.get_metadata("stub").display_name == "测试策略"
    assert [item.strategy_id for item in registry.metadata()] == ["stub"]


def test_registry_rejects_duplicate_and_unknown_ids() -> None:
    registry = ETFStrategyRegistry()
    registry.register(metadata(), StubStrategy)

    with pytest.raises(ETFConfigurationError, match="duplicate ETF strategy"):
        registry.register(metadata(), StubStrategy)
    with pytest.raises(ETFConfigurationError, match="unknown active ETF strategy"):
        registry.create("missing")
