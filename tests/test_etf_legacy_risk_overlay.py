from __future__ import annotations

import pandas as pd

from superpower.skills.etf_rotation_strategy.risk_overlay import (
    evaluate_legacy_risk_overlay,
)
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.defaults import (
    DEFAULT_PROFILE,
)


PROFILE = DEFAULT_PROFILE["short_entry"]


def history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-07-02"),
                "开盘价": 10.0,
                "最高价": 10.1,
                "最低价": 9.9,
                "收盘价": 10.0,
                "ma5": 10.0,
                "ma20_slope_state": "flat",
                "weekly_macd_state": "green_narrowing",
                "vol_ratio60": 1.0,
            },
            {
                "date": pd.Timestamp("2026-07-03"),
                "开盘价": 10.0,
                "最高价": 10.1,
                "最低价": 9.9,
                "收盘价": 10.0,
                "ma5": 10.0,
                "ma20_slope_state": "flat",
                "weekly_macd_state": "green_narrowing",
                "vol_ratio60": 1.0,
            },
        ]
    )


def test_neutral_overlay_explicitly_does_not_change_ranking() -> None:
    result = evaluate_legacy_risk_overlay(history(), PROFILE)

    assert result.level == "info"
    assert result.flags == ()
    assert result.ma20_state == "flat"
    assert result.weekly_macd_state == "green_narrowing"
    assert "不改变原策略评分和排名" in result.summary


def test_falling_ma20_and_weakening_weekly_macd_are_cautions() -> None:
    rows = history()
    rows.loc[1, ["ma20_slope_state", "weekly_macd_state"]] = [
        "down",
        "green_widening",
    ]

    result = evaluate_legacy_risk_overlay(rows, PROFILE)

    assert result.level == "caution"
    assert result.flags == ("ma20_down", "weekly_macd_weakening")
    assert "MA20仍向下" in result.summary
    assert "周MACD绿柱扩大" in result.summary


def test_extreme_bar_in_falling_ma20_is_high_false_reversal_warning() -> None:
    rows = history()
    rows.loc[1, ["开盘价", "最高价", "最低价", "收盘价"]] = [
        10.0,
        10.6,
        10.0,
        10.5,
    ]
    rows.loc[1, ["ma5", "ma20_slope_state", "vol_ratio60"]] = [
        10.1,
        "down",
        2.0,
    ]

    result = evaluate_legacy_risk_overlay(rows, PROFILE)

    assert result.level == "high"
    assert "overheated_bar" in result.flags
    assert "extreme_false_reversal" in result.flags
    assert "长期弱势后的巨量长阳" in result.summary
    assert "不改变原策略评分和排名" in result.summary


def test_overheated_bar_without_falling_ma20_is_caution_not_false_reversal() -> None:
    rows = history()
    rows.loc[1, ["开盘价", "最高价", "最低价", "收盘价"]] = [
        10.0,
        10.6,
        10.0,
        10.5,
    ]
    rows.loc[1, ["ma5", "ma20_slope_state", "vol_ratio60"]] = [
        10.1,
        "up",
        2.0,
    ]

    result = evaluate_legacy_risk_overlay(rows, PROFILE)

    assert result.level == "caution"
    assert "overheated_bar" in result.flags
    assert "extreme_false_reversal" not in result.flags
    assert "短期过热" in result.summary


def test_missing_overlay_inputs_degrade_to_unavailable_without_exception() -> None:
    result = evaluate_legacy_risk_overlay(
        history().drop(columns=["weekly_macd_state"]),
        PROFILE,
    )

    assert result.level == "unavailable"
    assert result.flags == ("overlay_data_unavailable",)
    assert "辅助指标不足" in result.summary
