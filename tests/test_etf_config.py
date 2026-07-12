from copy import deepcopy

import pytest

from superpower.skills.etf_rotation_strategy.config import (
    ETFConfigurationError,
    etf_config_hash,
    merge_strategy_params,
    normalize_etf_config,
)


LEGACY = {
    "etf": {
        "buy_volume_ratio_min": 1.1,
        "sell_ma10_volume_ratio_min": 1.2,
        "sell_ma5_volume_ratio_min": 1.5,
        "score_weights": {
            "trend": 0.35,
            "macd": 0.25,
            "volume": 0.25,
            "share_change": 0.15,
        },
    },
    "tl": {"weekly_no_trade_hard_veto": True},
}


def test_missing_active_strategy_normalizes_to_legacy_without_mutating_input() -> None:
    original = deepcopy(LEGACY)

    normalized = normalize_etf_config(LEGACY)

    assert LEGACY == original
    assert normalized["active_strategy"] == "legacy_v1"
    assert normalized["diagnostic_strategies"] == ["legacy_v1"]
    assert normalized["buy_volume_ratio_min"] == 1.1
    assert normalized["strategy_profiles"]["legacy_v1"]["buy_volume_ratio_min"] == 1.1


def test_normalization_is_idempotent_and_keeps_flat_compatibility_keys() -> None:
    once = normalize_etf_config(LEGACY)
    twice = normalize_etf_config({"etf": once})

    assert twice == once
    assert twice["sell_ma10_volume_ratio_min"] == 1.2
    assert twice["score_weights"]["trend"] == 0.35


def test_explicit_unknown_active_strategy_fails_closed() -> None:
    with pytest.raises(ETFConfigurationError, match="unknown active ETF strategy"):
        normalize_etf_config({"etf": {"active_strategy": "missing"}})


def test_explicit_unknown_diagnostic_strategy_fails_closed() -> None:
    with pytest.raises(ETFConfigurationError, match="unknown diagnostic ETF strategy"):
        normalize_etf_config(
            {
                "etf": {
                    "active_strategy": "legacy_v1",
                    "diagnostic_strategies": ["missing"],
                }
            }
        )


def test_deep_merge_preserves_dormant_profiles_and_replaces_arrays() -> None:
    current = {
        "etf": {
            "diagnostic_strategies": ["legacy_v1"],
            "strategy_profiles": {"future_v3": {"kept": True}},
        },
        "tl": {"kept": True},
    }
    patch = {"etf": {"diagnostic_strategies": ["trend_pullback_v2"]}}

    merged = merge_strategy_params(current, patch)

    assert merged["etf"]["diagnostic_strategies"] == ["trend_pullback_v2"]
    assert merged["etf"]["strategy_profiles"]["future_v3"] == {"kept": True}
    assert merged["tl"] == {"kept": True}


def test_hash_is_order_independent_and_etf_only() -> None:
    left = {
        "active_strategy": "legacy_v1",
        "diagnostic_strategies": ["legacy_v1"],
        "strategy_profiles": {"legacy_v1": {}},
    }
    right = {
        "strategy_profiles": {"legacy_v1": {}},
        "diagnostic_strategies": ["legacy_v1"],
        "active_strategy": "legacy_v1",
    }

    assert etf_config_hash(left) == etf_config_hash(right)


def test_invalid_legacy_profile_value_is_rejected() -> None:
    invalid = deepcopy(LEGACY)
    invalid["etf"]["buy_volume_ratio_min"] = 0

    with pytest.raises(ETFConfigurationError, match="buy_volume_ratio_min"):
        normalize_etf_config(invalid)


def test_score_weights_must_sum_to_one() -> None:
    invalid = deepcopy(LEGACY)
    invalid["etf"]["score_weights"]["trend"] = 0.5

    with pytest.raises(ETFConfigurationError, match="score_weights"):
        normalize_etf_config(invalid)
