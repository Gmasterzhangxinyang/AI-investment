from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from ...contracts import MediumStatus


@dataclass(frozen=True)
class MediumTrendResult:
    status: MediumStatus
    reason: str
    rule_hits: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    ma5_crossed_ma20_today: bool


def evaluate_medium_trend(
    row: pd.Series,
    previous: pd.Series,
    profile: Mapping[str, Any],
) -> MediumTrendResult:
    required = (
        "收盘价",
        "vol_ratio60",
        "ma5",
        "ma20",
        "ma20_slope_5d",
        "ma20_slope_state",
        "weekly_macd_hist",
        "weekly_macd_state",
        "macd_hist",
    )
    missing = tuple(key for key in required if pd.isna(row.get(key)))
    if missing:
        return MediumTrendResult(
            status=MediumStatus.DATA_UNAVAILABLE,
            reason="中期趋势所需数据不足",
            rule_hits=(),
            missing_conditions=missing,
            ma5_crossed_ma20_today=False,
        )

    crossed_today = bool(
        pd.notna(previous.get("ma5"))
        and pd.notna(previous.get("ma20"))
        and previous["ma5"] <= previous["ma20"]
        and row["ma5"] > row["ma20"]
    )
    hard_vetoes = tuple(
        hit
        for hit, active in (
            ("ma20_slope_down", row["ma20_slope_state"] == "down"),
            (
                "weekly_macd_green_widening",
                row["weekly_macd_state"] == "green_widening",
            ),
        )
        if active
    )
    if hard_vetoes:
        return MediumTrendResult(
            status=MediumStatus.DO_NOT_PARTICIPATE,
            reason="中期趋势存在硬性否决条件",
            rule_hits=hard_vetoes,
            missing_conditions=(),
            ma5_crossed_ma20_today=crossed_today,
        )

    confirmations = {
        "close_above_ma20": row["收盘价"] > row["ma20"],
        "ma5_above_ma20": row["ma5"] > row["ma20"],
        "ma20_flat_or_up": row["ma20_slope_state"] in {"flat", "up"},
        "weekly_macd_red": row["weekly_macd_hist"] > 0,
        "daily_macd_red": row["macd_hist"] > 0,
    }
    if all(confirmations.values()):
        return MediumTrendResult(
            status=MediumStatus.TREND_CONFIRMED,
            reason="价格、均线、周MACD和日MACD共同确认中期趋势",
            rule_hits=tuple(confirmations),
            missing_conditions=(),
            ma5_crossed_ma20_today=crossed_today,
        )
    return MediumTrendResult(
        status=MediumStatus.TREND_NOT_CONFIRMED,
        reason="中期趋势确认条件尚未全部满足",
        rule_hits=tuple(key for key, active in confirmations.items() if active),
        missing_conditions=tuple(
            key for key, active in confirmations.items() if not active
        ),
        ma5_crossed_ma20_today=crossed_today,
    )


def evaluate_medium_history(
    rows: pd.DataFrame,
    profile: Mapping[str, Any],
) -> list[MediumTrendResult]:
    results: list[MediumTrendResult] = []
    for index in range(len(rows)):
        if index == 0:
            results.append(
                MediumTrendResult(
                    status=MediumStatus.DATA_UNAVAILABLE,
                    reason="缺少前一交易日，无法判断均线事件",
                    rule_hits=(),
                    missing_conditions=("previous_row",),
                    ma5_crossed_ma20_today=False,
                )
            )
            continue
        results.append(evaluate_medium_trend(rows.iloc[index], rows.iloc[index - 1], profile))
    return results
