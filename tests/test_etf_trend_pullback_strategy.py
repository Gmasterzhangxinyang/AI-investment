from __future__ import annotations

import pandas as pd

from superpower.skills.etf_rotation_strategy.config import (
    KNOWN_STRATEGY_IDS,
    normalize_etf_config,
)
from superpower.skills.etf_rotation_strategy.contracts import (
    ETFHistory,
    ETFPositionState,
    MediumStatus,
    ShortEntryStatus,
)
from superpower.skills.etf_rotation_strategy.registry import default_registry
from superpower.skills.etf_rotation_strategy.handler import latest_etf_signals
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.strategy import (
    TrendPullbackV2Strategy,
)


PROFILE = normalize_etf_config({})["strategy_profiles"]["trend_pullback_v2"]


def history(rows: int = 180) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=rows)
    return pd.DataFrame(
        {
            "date": dates,
            "code": "510001",
            "name": "样例ETF",
            "开盘价": 10.0,
            "最高价": 10.1,
            "最低价": 9.9,
            "收盘价": 10.0,
            "成交量（万股）": 100.0,
            "ma5": 10.0,
            "ma10": 9.9,
            "ma20": 9.8,
            "ma60": 9.5,
            "ma20_slope_5d": 0.0,
            "ma20_slope_state": "flat",
            "vol_ratio60": 1.0,
            "dif": 0.02,
            "dea": 0.01,
            "macd_hist": 0.01,
            "weekly_macd_hist": 0.02,
            "weekly_macd_state": "red_strengthening",
            "weekly_macd_preview": 0.021,
            "daily_macd_state": "red_strengthening",
            "份额变化（亿份）": 0.0,
            "kdj_j": 50.0,
        }
    )


def evaluate(frame: pd.DataFrame, *, holding: bool = False):
    rows = frame.sort_values("date").reset_index(drop=True)
    item = ETFHistory(
        code="510001",
        name="样例ETF",
        rows=rows,
        as_of=pd.Timestamp(rows.iloc[-1]["date"]),
    )
    return TrendPullbackV2Strategy().evaluate(
        item,
        ETFPositionState(holding),
        PROFILE,
    )


def test_registry_contains_both_known_etf_strategies() -> None:
    registered = {item.strategy_id for item in default_registry().metadata()}
    assert registered == KNOWN_STRATEGY_IDS


def test_customer_close_watch_rule_is_public_watch_for_nonholding_only() -> None:
    frame = history()
    frame.loc[len(frame) - 2, "macd_hist"] = -0.02
    frame.loc[len(frame) - 1, ["macd_hist", "weekly_macd_hist", "weekly_macd_state"]] = [
        -0.01,
        -0.01,
        "green_narrowing",
    ]

    nonholding = evaluate(frame)
    holding = evaluate(frame, holding=True)

    assert nonholding.medium_status is MediumStatus.TREND_NOT_CONFIRMED
    assert nonholding.short_entry_status is ShortEntryStatus.CLOSE_WATCH
    assert nonholding.watch_candidate is True
    assert holding.short_entry_status is ShortEntryStatus.CLOSE_WATCH
    assert holding.watch_candidate is False
    assert "周MACD" in nonholding.short_entry_reason
    assert "MA20" in nonholding.short_entry_reason


def test_long_decline_giant_bar_is_never_a_buy_candidate() -> None:
    frame = history()
    last = len(frame) - 1
    frame.loc[last - 1, "收盘价"] = 10.0
    frame.loc[last, ["开盘价", "最高价", "最低价", "收盘价"]] = [10.0, 10.5, 10.0, 10.5]
    frame.loc[last, ["ma5", "ma10", "ma20", "ma20_slope_5d", "ma20_slope_state"]] = [
        10.1,
        10.0,
        10.2,
        -0.02,
        "down",
    ]
    frame.loc[last, ["vol_ratio60", "macd_hist"]] = [2.0, 0.02]

    decision = evaluate(frame)

    assert decision.medium_status is MediumStatus.DO_NOT_PARTICIPATE
    assert decision.buy_candidate is False
    assert any("overheat" in note for note in decision.risk_notes)


def test_holding_sell_takes_public_precedence_over_short_entry() -> None:
    frame = history(181)
    setup = len(frame) - 2
    final = len(frame) - 1
    frame.loc[setup - 1, ["weekly_macd_hist", "macd_hist"]] = [-0.01, -0.01]
    frame.loc[setup, ["最高价", "收盘价", "ma5", "ma20", "成交量（万股）"]] = [
        10.1,
        10.0,
        9.9,
        9.8,
        200.0,
    ]
    frame.loc[final, ["最高价", "收盘价", "ma5", "ma10", "ma20", "vol_ratio60"]] = [
        10.25,
        10.2,
        10.3,
        10.1,
        9.8,
        1.5,
    ]

    decision = evaluate(frame, holding=True)

    assert decision.short_entry_status is ShortEntryStatus.CAN_ENTER
    assert decision.sell_alert is True
    assert decision.buy_candidate is False
    assert decision.watch_candidate is False


def test_short_history_keeps_v2_states_unavailable_but_allows_legacy_exit() -> None:
    frame = history(100)
    last = len(frame) - 1
    frame.loc[last, ["收盘价", "ma5", "ma10", "vol_ratio60"]] = [9.7, 10.0, 9.9, 1.5]

    decision = evaluate(frame, holding=True)

    assert decision.medium_status is MediumStatus.DATA_UNAVAILABLE
    assert decision.short_entry_status is ShortEntryStatus.DATA_UNAVAILABLE
    assert decision.sell_alert is True


def test_invalid_or_duplicate_rows_do_not_satisfy_minimum_history() -> None:
    frame = history(181)
    frame.loc[180, "date"] = frame.loc[179, "date"]
    frame.loc[178, "收盘价"] = float("nan")
    frame.loc[179, "收盘价"] = float("nan")

    decision = evaluate(frame)

    assert decision.medium_status is MediumStatus.DATA_UNAVAILABLE
    assert decision.short_entry_status is ShortEntryStatus.DATA_UNAVAILABLE


def test_decision_exposes_complete_strategy_state_contract() -> None:
    decision = evaluate(history())
    fields = decision.compatibility_fields
    expected = {
        "strategy_id",
        "strategy_version",
        "medium_status",
        "medium_reason",
        "short_entry_status",
        "short_entry_reason",
        "weekly_macd_state",
        "weekly_macd_hist",
        "weekly_macd_preview",
        "weekly_macd_confirmation_check",
        "ma20_slope_5d",
        "ma20_slope_state",
        "ma20_flat_check",
        "daily_macd_state",
        "ma5_above_ma10",
        "ma5_crossed_ma10_today",
        "setup_date",
        "setup_age",
    }
    assert expected <= set(fields)


def test_v2_public_signal_table_keeps_all_canonical_state_columns() -> None:
    frame = history()
    params = {
        "etf": {
            "active_strategy": "trend_pullback_v2",
            "diagnostic_strategies": ["legacy_v1", "trend_pullback_v2"],
        }
    }

    signals, _, _, _, _ = latest_etf_signals(
        frame,
        pd.DataFrame(columns=["asset_type", "code", "status"]),
        params,
        quality_warnings=("ETF最新日期：数据可能陈旧",),
    )

    expected = {
        "weekly_macd_state",
        "weekly_macd_hist",
        "weekly_macd_preview",
        "weekly_macd_confirmation_check",
        "ma20_slope_5d",
        "ma20_slope_state",
        "ma20_flat_check",
        "daily_macd_state",
        "ma5_above_ma10",
        "ma5_crossed_ma10_today",
        "setup_date",
        "setup_age",
    }
    assert expected <= set(signals.columns)
    assert signals.iloc[0]["strategy_id"] == "trend_pullback_v2"
    assert "数据可能陈旧" in signals.iloc[0]["risk_notes"]
    assert signals.iloc[0]["data_quality"] == "WARN"
