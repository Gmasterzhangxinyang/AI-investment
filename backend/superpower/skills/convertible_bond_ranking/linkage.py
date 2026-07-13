from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


DEFAULT_LINKAGE_CONFIG: dict[str, float] = {
    "validation_tolerance": 0.05,
    "stock_strong_threshold": 3.0,
    "stock_weak_threshold": -3.0,
    "bond_strong_threshold": 3.0,
    "bond_weak_threshold": -2.0,
    "relative_gap_threshold": 2.0,
    "premium_expand_threshold": 2.0,
    "premium_compress_threshold": -2.0,
}

DEFAULT_DYNAMIC_CONFIG: dict[str, Any] = {
    **DEFAULT_LINKAGE_CONFIG,
    "component_weights": {
        "stock": 0.2,
        "bond": 0.15,
        "relative": 0.3,
        "premium_change": 0.35,
    },
    "return_score_range": 5.0,
    "relative_score_range": 4.0,
    "premium_change_score_range": 4.0,
}


def classify_linkage(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, object]:
    thresholds = {**DEFAULT_LINKAGE_CONFIG, **dict(config or {})}
    current_premium = _finite_number(row.get("conversion_premium_rate"))
    stock_return = _finite_number(row.get("stock_daily_return"))
    bond_return = _finite_number(row.get("bond_daily_return"))
    previous_premium = _finite_number(row.get("previous_conversion_premium_rate"))
    premium_change = _finite_number(row.get("conversion_premium_change"))

    if any(value is None for value in (current_premium, stock_return, bond_return, previous_premium, premium_change)):
        return _result("数据不足", "", False, "MISSING")

    expected_change = current_premium - previous_premium
    if abs(premium_change - expected_change) > float(thresholds["validation_tolerance"]):
        return _result(
            "数据待核验",
            "转股溢价率当日变化与今日、前日溢价率不一致，暂不生成联动结论；不改变原排名。",
            True,
            "REVIEW",
        )

    if stock_return <= float(thresholds["stock_weak_threshold"]) and bond_return <= float(thresholds["bond_weak_threshold"]):
        return _result(
            "联动走弱",
            "正股与转债同步走弱，注意短期回撤风险；不改变原排名。",
            True,
            "OK",
        )

    relative_gap = float(thresholds["relative_gap_threshold"])
    if (
        bond_return >= float(thresholds["bond_strong_threshold"])
        and bond_return - stock_return >= relative_gap
        and premium_change >= float(thresholds["premium_expand_threshold"])
    ):
        return _result(
            "谨慎追涨",
            "转债涨幅领先正股且溢价扩大，短期偏贵，谨慎追涨；不改变原排名。",
            True,
            "OK",
        )

    if (
        stock_return >= float(thresholds["stock_strong_threshold"])
        and stock_return - bond_return >= relative_gap
        and premium_change <= float(thresholds["premium_compress_threshold"])
    ):
        return _result(
            "关注补涨",
            "正股偏强、转债跟涨不足且溢价收缩，关注后续是否补涨；不改变原排名。",
            True,
            "OK",
        )

    return _result("正常联动", "", False, "OK")


def score_dynamic_linkage(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, object]:
    settings = {**DEFAULT_DYNAMIC_CONFIG, **dict(config or {})}
    classified = classify_linkage(row, settings)
    if classified["linkage_data_quality"] != "OK":
        return {
            "dynamic_score": None,
            "dynamic_state": classified["linkage_state"],
            "dynamic_note": classified["linkage_note"],
            "dynamic_data_quality": classified["linkage_data_quality"],
            "dynamic_components": {},
        }

    stock_return = float(row["stock_daily_return"])
    bond_return = float(row["bond_daily_return"])
    premium_change = float(row["conversion_premium_change"])
    components = {
        "stock": _bounded_component(stock_return, float(settings["return_score_range"])),
        "bond": _bounded_component(bond_return, float(settings["return_score_range"])),
        "relative": _bounded_component(stock_return - bond_return, float(settings["relative_score_range"])),
        "premium_change": _bounded_component(-premium_change, float(settings["premium_change_score_range"])),
    }
    raw_weights = dict(settings.get("component_weights") or {})
    weights = {key: max(float(raw_weights.get(key, 0.0)), 0.0) for key in components}
    total = sum(weights.values())
    if total <= 0:
        weights = dict(DEFAULT_DYNAMIC_CONFIG["component_weights"])
        total = sum(weights.values())
    score = sum(components[key] * weights[key] for key in components) / total
    return {
        "dynamic_score": round(max(0.0, min(100.0, score)), 2),
        "dynamic_state": classified["linkage_state"],
        "dynamic_note": _dynamic_note(str(classified["linkage_state"])),
        "dynamic_data_quality": "OK",
        "dynamic_components": {key: round(value, 2) for key, value in components.items()},
    }


def _bounded_component(signal: float, full_range: float) -> float:
    if full_range <= 0:
        return 50.0
    return max(0.0, min(100.0, 50.0 + 50.0 * signal / full_range))


def _dynamic_note(state: str) -> str:
    return {
        "关注补涨": "正股偏强、转债跟涨不足且溢价收缩，动态层偏积极。",
        "谨慎追涨": "转债涨幅领先正股且溢价扩大，动态层提示谨慎追涨。",
        "联动走弱": "正股与转债同步走弱，动态层提示短期回撤风险。",
        "正常联动": "正股、转债与溢价率变化处于正常联动范围。",
    }.get(state, "")


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _result(state: str, note: str, abnormal: bool, data_quality: str) -> dict[str, object]:
    return {
        "linkage_state": state,
        "linkage_note": note,
        "linkage_is_abnormal": abnormal,
        "linkage_data_quality": data_quality,
    }
