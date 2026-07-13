from __future__ import annotations

import pytest

from superpower.server.app import _strategy_params_payload, _validate_strategy_params
from superpower.skills.convertible_bond_ranking.strategy import (
    CBConfigurationError,
    cb_config_hash,
    cb_strategy_metadata,
    normalize_cb_config,
)
from superpower.skills.convertible_bond_ranking.registry import default_cb_registry


def _params(strategy_id: str = "dynamic_v2") -> dict[str, object]:
    return {
        "etf": {
            "active_strategy": "legacy_v1",
            "diagnostic_strategies": ["legacy_v1"],
            "strategy_profiles": {"legacy_v1": {}},
            "buy_volume_ratio_min": 1.1,
        },
        "tl": {},
        "convertible_bond": {
            "active_strategy": strategy_id,
            "min_price": 100,
            "price_limit": 140,
        },
        "risk": {},
    }


def test_dynamic_v2_is_default_auxiliary_overlay() -> None:
    config = normalize_cb_config({"convertible_bond": {}})

    assert config["base_strategy"] == "legacy_v1"
    assert config["auxiliary_overlay"] == {
        "enabled": True,
        "overlay_id": "dynamic_v2",
        "settings": {},
    }


def test_default_cb_registry_has_legacy_base_and_dynamic_overlay() -> None:
    registry = default_cb_registry()

    assert registry.base("legacy_v1").strategy_id == "legacy_v1"
    assert registry.overlay("dynamic_v2").overlay_id == "dynamic_v2"


def test_cb_config_hash_changes_when_overlay_threshold_changes() -> None:
    left = cb_config_hash(
        {"auxiliary_overlay": {"overlay_id": "dynamic_v2", "settings": {"stock_strong_threshold": 3}}}
    )
    right = cb_config_hash(
        {"auxiliary_overlay": {"overlay_id": "dynamic_v2", "settings": {"stock_strong_threshold": 4}}}
    )

    assert left != right


def test_old_dynamic_strategy_config_migrates_to_enabled_overlay() -> None:
    config = normalize_cb_config({"convertible_bond": {"active_strategy": "dynamic_v2"}})

    assert config["base_strategy"] == "legacy_v1"
    assert config["auxiliary_overlay"]["enabled"] is True
    assert config["auxiliary_overlay"]["overlay_id"] == "dynamic_v2"


def test_unknown_cb_strategy_is_rejected() -> None:
    with pytest.raises(CBConfigurationError, match="unknown active convertible-bond strategy"):
        normalize_cb_config({"convertible_bond": {"active_strategy": "missing"}})


def test_metadata_exposes_two_plugins() -> None:
    assert [item.strategy_id for item in cb_strategy_metadata()] == ["legacy_v1", "dynamic_v2"]


def test_strategy_api_exposes_cb_plugins_and_validates_selection() -> None:
    params = _params()

    _validate_strategy_params(params)
    payload = _strategy_params_payload(params)

    assert payload["params"]["convertible_bond"]["active_strategy"] == "dynamic_v2"
    assert {item["strategy_id"] for item in payload["cbStrategies"]} == {"legacy_v1", "dynamic_v2"}


def test_strategy_api_rejects_unknown_cb_plugin() -> None:
    with pytest.raises(CBConfigurationError, match="unknown active convertible-bond strategy"):
        _validate_strategy_params(_params("missing"))
