from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


KNOWN_CB_STRATEGY_IDS = ("legacy_v1", "dynamic_v2")


class CBConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class CBStrategyMetadata:
    strategy_id: str
    display_name: str
    version: str
    default_params: dict[str, float]


def cb_strategy_metadata() -> list[CBStrategyMetadata]:
    return [
        CBStrategyMetadata("legacy_v1", "原策略", "1.0.0", {}),
        CBStrategyMetadata(
            "dynamic_v2",
            "动态策略",
            "2.0.0",
            {"base_weight": 0.8, "dynamic_weight": 0.2},
        ),
    ]


def normalize_cb_config(params: Mapping[str, Any]) -> dict[str, Any]:
    raw = params.get("convertible_bond", {})
    if not isinstance(raw, Mapping):
        raise CBConfigurationError("convertible_bond must be an object")
    config = deepcopy(dict(raw))
    active_strategy = str(config.get("active_strategy") or "dynamic_v2")
    if active_strategy not in KNOWN_CB_STRATEGY_IDS:
        raise CBConfigurationError(f"unknown active convertible-bond strategy: {active_strategy}")

    base_strategy = str(config.get("base_strategy") or "legacy_v1")
    if base_strategy != "legacy_v1":
        raise CBConfigurationError(f"unknown convertible-bond base strategy: {base_strategy}")
    raw_overlay = config.get("auxiliary_overlay")
    if raw_overlay is not None and not isinstance(raw_overlay, Mapping):
        raise CBConfigurationError("convertible_bond.auxiliary_overlay must be an object")
    overlay = deepcopy(dict(raw_overlay or {}))
    overlay_id = str(overlay.get("overlay_id") or "dynamic_v2")
    if overlay_id != "dynamic_v2":
        raise CBConfigurationError(f"unknown convertible-bond auxiliary overlay: {overlay_id}")
    overlay_enabled = bool(overlay.get("enabled", active_strategy == "dynamic_v2"))
    settings = overlay.get("settings") or {}
    if not isinstance(settings, Mapping):
        raise CBConfigurationError("convertible_bond.auxiliary_overlay.settings must be an object")

    profiles = deepcopy(dict(config.get("strategy_profiles") or {}))
    profiles.setdefault("legacy_v1", {})
    dynamic = dict(profiles.get("dynamic_v2") or {})
    base_weight = max(float(dynamic.get("base_weight", 0.8)), 0.0)
    dynamic_weight = max(float(dynamic.get("dynamic_weight", 0.2)), 0.0)
    total = base_weight + dynamic_weight
    if total <= 0:
        base_weight, dynamic_weight, total = 0.8, 0.2, 1.0
    profiles["dynamic_v2"] = {
        "base_weight": base_weight / total,
        "dynamic_weight": dynamic_weight / total,
    }
    config["active_strategy"] = active_strategy
    config["strategy_profiles"] = profiles
    config["base_strategy"] = base_strategy
    config["auxiliary_overlay"] = {
        "enabled": overlay_enabled,
        "overlay_id": overlay_id,
        "settings": deepcopy(dict(settings)),
    }
    return config


def cb_config_hash(params: Mapping[str, Any]) -> str:
    source = params if "convertible_bond" in params else {"convertible_bond": params}
    normalized = normalize_cb_config(source)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cb_strategy_version(strategy_id: str) -> str:
    for item in cb_strategy_metadata():
        if item.strategy_id == strategy_id:
            return item.version
    raise CBConfigurationError(f"unknown active convertible-bond strategy: {strategy_id}")
