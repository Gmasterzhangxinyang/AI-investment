from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .strategies.trend_pullback_v2.defaults import DEFAULT_PROFILE


class ETFConfigurationError(ValueError):
    """Raised before a run or save when ETF plugin configuration is invalid."""


KNOWN_STRATEGY_IDS = frozenset({"legacy_v1", "trend_pullback_v2"})

DEFAULT_SCORE_WEIGHTS = {
    "trend": 0.35,
    "macd": 0.25,
    "volume": 0.25,
    "share_change": 0.15,
}

DEFAULT_LEGACY_PROFILE = {
    "buy_volume_ratio_min": 1.1,
    "sell_ma10_volume_ratio_min": 1.2,
    "sell_ma5_volume_ratio_min": 1.5,
    "score_weights": DEFAULT_SCORE_WEIGHTS,
}


def normalize_etf_config(strategy_params: Mapping[str, Any]) -> dict[str, Any]:
    source = strategy_params.get("etf", strategy_params)
    if not isinstance(source, Mapping):
        raise ETFConfigurationError("etf configuration must be an object")
    normalized = deepcopy(dict(source))

    active_strategy = str(source.get("active_strategy") or "legacy_v1")
    if active_strategy not in KNOWN_STRATEGY_IDS:
        raise ETFConfigurationError(f"unknown active ETF strategy: {active_strategy}")

    raw_diagnostics = source.get("diagnostic_strategies")
    diagnostics = [active_strategy] if raw_diagnostics is None else list(raw_diagnostics)
    for strategy_id in diagnostics:
        if strategy_id not in KNOWN_STRATEGY_IDS:
            raise ETFConfigurationError(f"unknown diagnostic ETF strategy: {strategy_id}")

    raw_profiles = source.get("strategy_profiles", {})
    if not isinstance(raw_profiles, Mapping):
        raise ETFConfigurationError("strategy_profiles must be an object")
    profiles = deepcopy(dict(raw_profiles))
    raw_legacy = profiles.get("legacy_v1", {})
    if not isinstance(raw_legacy, Mapping):
        raise ETFConfigurationError("legacy_v1 profile must be an object")

    legacy = deepcopy(DEFAULT_LEGACY_PROFILE)
    legacy.update(deepcopy(dict(raw_legacy)))
    for key in (
        "buy_volume_ratio_min",
        "sell_ma10_volume_ratio_min",
        "sell_ma5_volume_ratio_min",
        "score_weights",
    ):
        if key in source:
            legacy[key] = deepcopy(source[key])
    validate_etf_profile("legacy_v1", legacy)

    normalized["active_strategy"] = active_strategy
    normalized["diagnostic_strategies"] = diagnostics
    for key, value in legacy.items():
        normalized[key] = deepcopy(value)
    profiles["legacy_v1"] = deepcopy(legacy)
    raw_v2 = profiles.get("trend_pullback_v2", {})
    if not isinstance(raw_v2, Mapping):
        raise ETFConfigurationError("trend_pullback_v2 profile must be an object")
    v2_profile = merge_strategy_params(DEFAULT_PROFILE, raw_v2)
    v2_profile["exit"]["legacy_params"] = deepcopy(legacy)
    v2_profile["ranking"]["legacy_params"] = deepcopy(legacy)
    profiles["trend_pullback_v2"] = v2_profile
    normalized["strategy_profiles"] = profiles
    return normalized


def validate_etf_profile(strategy_id: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    if strategy_id not in KNOWN_STRATEGY_IDS:
        raise ETFConfigurationError(f"unknown ETF strategy profile: {strategy_id}")
    validated = deepcopy(dict(profile))
    if strategy_id == "legacy_v1":
        for key in (
            "buy_volume_ratio_min",
            "sell_ma10_volume_ratio_min",
            "sell_ma5_volume_ratio_min",
        ):
            value = validated.get(key)
            if not _positive_finite(value):
                raise ETFConfigurationError(f"{key} must be a positive finite number")
        weights = validated.get("score_weights")
        if not isinstance(weights, Mapping) or set(weights) != set(DEFAULT_SCORE_WEIGHTS):
            raise ETFConfigurationError("score_weights must contain trend, macd, volume, share_change")
        numeric_weights = [float(weights[key]) for key in DEFAULT_SCORE_WEIGHTS]
        if not all(math.isfinite(value) and value >= 0 for value in numeric_weights):
            raise ETFConfigurationError("score_weights must be finite non-negative numbers")
        if not math.isclose(sum(numeric_weights), 1.0, abs_tol=1e-9):
            raise ETFConfigurationError("score_weights must sum to 1")
    return validated


def validate_all_etf_profiles(config: Mapping[str, Any]) -> None:
    profiles = config.get("strategy_profiles", {})
    referenced = {str(config["active_strategy"]), *map(str, config.get("diagnostic_strategies", []))}
    for strategy_id in referenced:
        profile = profiles.get(strategy_id, {})
        validate_etf_profile(strategy_id, profile)


def merge_strategy_params(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(existing))
    for key, value in incoming.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = merge_strategy_params(current, value)
        else:
            result[key] = deepcopy(value)
    return result


def etf_config_hash(config: Mapping[str, Any]) -> str:
    normalized = normalize_etf_config(config)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _positive_finite(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0
