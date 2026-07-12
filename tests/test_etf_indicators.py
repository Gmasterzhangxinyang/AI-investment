from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from superpower.skills.technical_indicators.etf import (
    add_etf_indicators,
    classify_ma20_slope,
    classify_weekly_macd,
)


MEDIUM_PROFILE = {
    "ma20_slope_lookback": 5,
    "ma20_flat_tolerance": 0.003,
}


def indicator_history(periods: int, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=periods)
    close = 10.0 + np.arange(periods) * 0.01
    return pd.DataFrame(
        {
            "date": dates,
            "code": "510001",
            "name": "样例ETF",
            "开盘价": close - 0.02,
            "最高价": close + 0.05,
            "最低价": close - 0.05,
            "收盘价": close,
            "成交量（万股）": 100.0 + np.arange(periods),
        }
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.003001, "down"),
        (-0.003000, "flat"),
        (0.0, "flat"),
        (0.003000, "flat"),
        (0.003001, "up"),
    ],
)
def test_ma20_slope_boundaries(value: float, expected: str) -> None:
    assert classify_ma20_slope(value, 0.003) == expected


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (0.01, 0.02, "red_strengthening"),
        (0.02, 0.01, "red_weakening"),
        (-0.02, -0.01, "green_narrowing"),
        (-0.01, -0.02, "green_widening"),
        (-0.01, 0.0, "neutral_zero"),
    ],
)
def test_weekly_macd_states(previous: float, current: float, expected: str) -> None:
    assert classify_weekly_macd(current, previous) == expected


def test_current_week_change_does_not_change_official_completed_week() -> None:
    history = indicator_history(periods=260, end="2026-07-10")
    monday = add_etf_indicators(
        history[history["date"] <= "2026-07-06"],
        "成交量（万股）",
        MEDIUM_PROFILE,
    )
    friday = add_etf_indicators(history, "成交量（万股）", MEDIUM_PROFILE)

    assert monday.iloc[-1]["weekly_macd_hist"] == friday.iloc[-1]["weekly_macd_hist"]
    assert monday.iloc[-1]["weekly_macd_state"] == friday.iloc[-1]["weekly_macd_state"]
    assert monday.iloc[-1]["weekly_macd_preview"] != friday.iloc[-1]["weekly_macd_preview"]


def test_rows_after_as_of_cannot_change_historical_indicators() -> None:
    history = indicator_history(periods=260, end="2026-07-10")
    as_of = pd.Timestamp("2026-06-30")
    before = add_etf_indicators(
        history,
        "成交量（万股）",
        MEDIUM_PROFILE,
        as_of=as_of,
    )
    changed = history.copy()
    changed.loc[changed["date"] > as_of, "收盘价"] = 999.0
    after = add_etf_indicators(
        changed,
        "成交量（万股）",
        MEDIUM_PROFILE,
        as_of=as_of,
    )

    pd.testing.assert_series_equal(before.iloc[-1], after.iloc[-1], check_names=False)


def test_full_history_monday_preview_equals_monday_prefix_preview() -> None:
    history = indicator_history(periods=260, end="2026-07-10")
    full = add_etf_indicators(history, "成交量（万股）", MEDIUM_PROFILE)
    monday = pd.Timestamp("2026-07-06")
    prefix = add_etf_indicators(
        history[history["date"] <= monday],
        "成交量（万股）",
        MEDIUM_PROFILE,
    )

    full_monday = full.loc[full["date"] == monday].iloc[0]
    assert full_monday["weekly_macd_preview"] == prefix.iloc[-1]["weekly_macd_preview"]


def test_empty_calendar_week_is_not_treated_as_completed_observation() -> None:
    history = indicator_history(periods=300, end="2026-07-10")
    removed = history["date"].between("2026-06-15", "2026-06-19")
    history = history.loc[~removed].reset_index(drop=True)

    result = add_etf_indicators(history, "成交量（万股）", MEDIUM_PROFILE)

    monday_after_gap = result.loc[result["date"] == pd.Timestamp("2026-06-22")].iloc[0]
    assert monday_after_gap["weekly_completed_date"] == pd.Timestamp("2026-06-12")
