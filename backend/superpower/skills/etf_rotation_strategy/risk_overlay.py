from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class LegacyRiskOverlay:
    level: str
    summary: str
    flags: tuple[str, ...]
    ma20_state: str
    weekly_macd_state: str


def evaluate_legacy_risk_overlay(
    rows: pd.DataFrame,
    profile: Mapping[str, Any],
) -> LegacyRiskOverlay:
    ordered = rows.sort_values("date").reset_index(drop=True)
    required = {
        "date",
        "开盘价",
        "最高价",
        "最低价",
        "收盘价",
        "ma5",
        "ma20_slope_state",
        "weekly_macd_state",
        "vol_ratio60",
    }
    if len(ordered) < 2 or not required.issubset(ordered.columns):
        return _unavailable()

    latest = ordered.iloc[-1]
    previous = ordered.iloc[-2]
    if any(pd.isna(latest.get(key)) for key in required - {"date"}) or pd.isna(
        previous.get("收盘价")
    ):
        return _unavailable()

    ma20_state = str(latest["ma20_slope_state"])
    weekly_state = str(latest["weekly_macd_state"])
    flags: list[str] = []
    explanations: list[str] = []

    if ma20_state == "down":
        flags.append("ma20_down")
        explanations.append("MA20仍向下")
    if weekly_state == "green_widening":
        flags.append("weekly_macd_weakening")
        explanations.append("周MACD绿柱扩大")

    overheated = _is_overheated_bar(latest, previous, profile)
    if overheated:
        flags.append("overheated_bar")
        explanations.append("短期过热")
    if overheated and ma20_state == "down":
        flags.append("extreme_false_reversal")
        explanations = ["长期弱势后的巨量长阳，存在假反转风险"]

    if "extreme_false_reversal" in flags:
        level = "high"
    elif flags:
        level = "caution"
    else:
        level = "info"
        explanations.append("暂未发现额外风险")

    return LegacyRiskOverlay(
        level=level,
        summary="；".join(explanations) + "；仅作风险辅助，不改变原策略评分和排名",
        flags=tuple(flags),
        ma20_state=ma20_state,
        weekly_macd_state=weekly_state,
    )


def _is_overheated_bar(
    row: pd.Series,
    previous: pd.Series,
    profile: Mapping[str, Any],
) -> bool:
    previous_close = float(previous["收盘价"])
    ma5 = float(row["ma5"])
    if previous_close == 0 or ma5 == 0:
        return False
    daily_return = float(row["收盘价"]) / previous_close - 1
    body_ratio = max(float(row["收盘价"]) - float(row["开盘价"]), 0.0) / max(
        float(row["最高价"]) - float(row["最低价"]),
        1e-12,
    )
    ma5_distance = float(row["收盘价"]) / ma5 - 1
    return bool(
        daily_return >= float(profile["overheat_daily_return_min"])
        and body_ratio >= float(profile["overheat_body_ratio_min"])
        and float(row["vol_ratio60"]) >= float(profile["overheat_volume_ratio_min"])
        and ma5_distance >= float(profile["overheat_ma5_distance_min"])
    )


def _unavailable() -> LegacyRiskOverlay:
    return LegacyRiskOverlay(
        level="unavailable",
        summary="风险辅助指标不足；不改变原策略评分和排名",
        flags=("overlay_data_unavailable",),
        ma20_state="unavailable",
        weekly_macd_state="unavailable",
    )
