from __future__ import annotations

import json

from superpower.server.app import _strategy_params_payload, _validate_strategy_params
from superpower.skills.etf_rotation_strategy.config import merge_strategy_params


def params() -> dict:
    return {
        "etf": {
            "active_strategy": "legacy_v1",
            "diagnostic_strategies": ["legacy_v1", "trend_pullback_v2"],
            "buy_volume_ratio_min": 1.1,
            "sell_ma10_volume_ratio_min": 1.2,
            "sell_ma5_volume_ratio_min": 1.2,
            "score_weights": {
                "trend": 0.35,
                "macd": 0.25,
                "volume": 0.25,
                "share_change": 0.15,
            },
            "strategy_profiles": {
                "legacy_v1": {},
                "trend_pullback_v2": {},
                "future_v3": {"kept": True},
            },
        },
        "tl": {},
        "convertible_bond": {"min_price": 100, "price_limit": 140},
        "risk": {},
    }


def test_strategy_payload_has_registry_metadata_and_config_hash() -> None:
    payload = _strategy_params_payload(params())
    assert {item["strategy_id"] for item in payload["etfStrategies"]} == {
        "legacy_v1",
        "trend_pullback_v2",
    }
    assert len(payload["etfConfigHash"]) == 64
    json.dumps(payload, ensure_ascii=False)


def test_bare_patch_deep_merges_without_losing_other_sections_or_profiles() -> None:
    merged = merge_strategy_params(
        params(),
        {"etf": {"active_strategy": "trend_pullback_v2"}},
    )
    _validate_strategy_params(merged)
    assert merged["etf"]["strategy_profiles"]["future_v3"] == {"kept": True}
    assert merged["tl"] == {}


def test_unknown_active_strategy_is_rejected_before_save() -> None:
    merged = merge_strategy_params(params(), {"etf": {"active_strategy": "missing"}})
    try:
        _validate_strategy_params(merged)
    except ValueError as exc:
        assert "unknown active ETF strategy" in str(exc)
    else:
        raise AssertionError("unknown strategy was accepted")
