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
