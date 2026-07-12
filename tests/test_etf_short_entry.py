from __future__ import annotations

from dataclasses import replace

import pandas as pd

from superpower.skills.etf_rotation_strategy.contracts import (
    MediumStatus,
    ShortEntryStatus,
)
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.defaults import (
    DEFAULT_PROFILE,
)
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.medium_trend import (
    MediumTrendResult,
)
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.short_entry import (
    evaluate_short_entry_history,
)


PROFILE = DEFAULT_PROFILE["short_entry"]


def rows(count: int = 14) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=count)
    return pd.DataFrame(
        {
            "date": dates,
            "开盘价": 10.0,
            "最高价": 10.1,
            "最低价": 9.9,
            "收盘价": 10.0,
            "成交量（万股）": 100.0,
            "vol_ratio60": 1.0,
            "ma5": 10.0,
            "ma10": 9.9,
            "ma20": 9.8,
            "macd_hist": 0.01,
            "weekly_macd_state": "red_strengthening",
            "ma20_slope_state": "flat",
        }
    )


def medium_result(
    status: MediumStatus,
    *,
    crossed: bool = False,
) -> MediumTrendResult:
    return MediumTrendResult(
        status=status,
        reason=status.value,
        rule_hits=(),
        missing_conditions=(),
        ma5_crossed_ma20_today=crossed,
    )


def medium_history(
    count: int,
    *,
    setup_index: int | None = None,
) -> list[MediumTrendResult]:
    results = [medium_result(MediumStatus.TREND_CONFIRMED) for _ in range(count)]
    if setup_index is not None:
        for index in range(setup_index):
            results[index] = medium_result(MediumStatus.TREND_NOT_CONFIRMED)
    return results


def evaluate(
    frame: pd.DataFrame,
    mediums: list[MediumTrendResult],
):
    return evaluate_short_entry_history(
        frame,
        mediums,
        PROFILE,
        trading_session_numbers=list(range(1, len(frame) + 1)),
    )


def test_ma5_above_ma10_and_green_narrowing_becomes_close_watch() -> None:
    frame = rows(2)
    frame.loc[0, "macd_hist"] = -0.02
    frame.loc[1, "macd_hist"] = -0.01
    mediums = [medium_result(MediumStatus.TREND_NOT_CONFIRMED)] * 2

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.CLOSE_WATCH
    assert result.weekly_macd_confirmation_check == "favorable"
    assert result.ma20_flat_check == "met"
    assert "周MACD" in result.reason
    assert "MA20" in result.reason


def test_ma5_above_ma10_and_daily_green_to_red_becomes_close_watch() -> None:
    frame = rows(2)
    frame.loc[0, "macd_hist"] = -0.01
    frame.loc[1, "macd_hist"] = 0.01
    mediums = [medium_result(MediumStatus.DO_NOT_PARTICIPATE)] * 2

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.CLOSE_WATCH


def test_nonconfirmed_without_close_watch_is_no_entry() -> None:
    frame = rows(2)
    frame.loc[1, "ma5"] = 9.8
    frame.loc[1, "ma10"] = 10.0
    mediums = [medium_result(MediumStatus.TREND_NOT_CONFIRMED)] * 2

    assert evaluate(frame, mediums)[-1].status is ShortEntryStatus.NO_ENTRY


def test_setup_day_waits_for_later_confirmation() -> None:
    frame = rows(2)
    mediums = medium_history(2, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.WAITING_CONFIRMATION
    assert result.setup_age == 0
    assert result.setup_date == frame.iloc[1]["date"]


def test_later_breakout_confirmation_can_enter() -> None:
    frame = rows(3)
    frame.loc[1, ["最高价", "成交量（万股）"]] = [10.1, 200.0]
    frame.loc[2, ["收盘价", "最高价", "ma5", "macd_hist"]] = [10.2, 10.25, 10.0, 0.02]
    mediums = medium_history(3, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.CAN_ENTER
    assert result.entry_route == "breakout_confirmation"


def test_confirmed_giant_volume_bar_is_overheated_do_not_chase() -> None:
    frame = rows(2)
    frame.loc[1, ["开盘价", "最高价", "最低价", "收盘价"]] = [10.0, 10.5, 10.0, 10.5]
    frame.loc[1, ["vol_ratio60", "ma5"]] = [2.0, 10.1]
    mediums = medium_history(2, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.OVERHEATED_DO_NOT_CHASE
    assert "overheated" in result.risk_notes


def test_cooldown_blocks_entry_after_overheat() -> None:
    frame = rows(3)
    frame.loc[1, ["开盘价", "最高价", "最低价", "收盘价"]] = [10.0, 10.5, 10.0, 10.5]
    frame.loc[1, ["vol_ratio60", "ma5"]] = [2.0, 10.1]
    frame.loc[2, ["收盘价", "最高价", "ma5"]] = [10.6, 10.7, 10.4]
    mediums = medium_history(3, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.WAITING_PULLBACK
    assert result.cooldown_remaining == 2


def test_contracting_volume_support_hold_can_enter() -> None:
    frame = rows(6)
    frame.loc[1, ["最高价", "成交量（万股）"]] = [10.5, 200.0]
    frame.loc[5, ["最低价", "收盘价", "成交量（万股）", "ma5", "ma10", "macd_hist"]] = [
        9.98,
        10.02,
        100.0,
        10.0,
        9.9,
        0.02,
    ]
    mediums = medium_history(6, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.CAN_ENTER
    assert result.entry_route == "pullback_confirmation"


def test_broken_support_invalidates_setup() -> None:
    frame = rows(6)
    frame.loc[1, ["最高价", "成交量（万股）"]] = [10.5, 200.0]
    frame.loc[5, ["最低价", "收盘价", "ma5", "ma10"]] = [9.8, 9.8, 10.0, 9.9]
    mediums = medium_history(6, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.NO_ENTRY
    assert "support_broken" in result.risk_notes


def test_setup_expires_after_ten_trading_sessions() -> None:
    frame = rows(13)
    frame.loc[1, ["最高价", "成交量（万股）"]] = [10.5, 200.0]
    frame.loc[2:, "成交量（万股）"] = 250.0
    mediums = medium_history(13, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.NO_ENTRY
    assert result.setup_date is None


def test_repeated_overheat_restarts_cooldown() -> None:
    frame = rows(5)
    for index in (1, 3):
        frame.loc[index - 1, "收盘价"] = 10.0
        frame.loc[index, ["开盘价", "最高价", "最低价", "收盘价"]] = [10.0, 10.5, 10.0, 10.5]
        frame.loc[index, ["vol_ratio60", "ma5"]] = [2.0, 10.1]
    mediums = medium_history(5, setup_index=1)

    result = evaluate(frame, mediums)[-1]

    assert result.status is ShortEntryStatus.WAITING_PULLBACK
    assert result.cooldown_remaining == 2


def test_later_cross_does_not_replace_active_setup() -> None:
    frame = rows(5)
    mediums = medium_history(5, setup_index=1)
    mediums[3] = replace(mediums[3], ma5_crossed_ma20_today=True)

    results = evaluate(frame, mediums)

    assert results[-1].setup_date == frame.iloc[1]["date"]


def test_medium_data_unavailable_routes_to_short_data_unavailable() -> None:
    frame = rows(2)
    mediums = [medium_result(MediumStatus.DATA_UNAVAILABLE)] * 2

    assert evaluate(frame, mediums)[-1].status is ShortEntryStatus.DATA_UNAVAILABLE
