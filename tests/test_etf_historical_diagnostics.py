from __future__ import annotations

import math

import pandas as pd

from superpower.skills.etf_rotation_strategy.contracts import (
    ETFDecision,
    MediumStatus,
    ShortEntryStatus,
)
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.diagnostics import (
    HORIZONS,
    diagnostic_events,
    diagnostic_trace,
    summarize_historical_diagnostics,
)


def test_historical_diagnostics_cover_short_and_medium_horizons() -> None:
    assert HORIZONS == (1, 3, 5, 10, 20)


def bars_for_returns(closes: list[float]) -> pd.DataFrame:
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=len(close)),
            "收盘价": close,
            "最高价": close * 1.01,
            "最低价": close * 0.99,
        }
    )


def decisions(states: list[str], *, strategy_id: str = "trend_pullback_v2") -> list[ETFDecision]:
    dates = pd.bdate_range("2026-01-01", periods=len(states))
    return [
        ETFDecision(
            as_of=dates[index],
            code="510001",
            name="样例ETF",
            strategy_id=strategy_id,
            strategy_version="2.0.0" if strategy_id != "legacy_v1" else "1.0.0",
            medium_status=(
                MediumStatus.TREND_CONFIRMED
                if strategy_id != "legacy_v1"
                else MediumStatus.NOT_APPLICABLE
            ),
            short_entry_status=ShortEntryStatus(state),
            exit_status="not_triggered",
            eligible=state in {"can_enter", "legacy_buy"},
            buy_candidate=state in {"can_enter", "legacy_buy"},
            watch_candidate=state in {"close_watch", "legacy_watch"},
            sell_alert=False,
            score=50.0,
            metrics={"entry_route": "breakout_confirmation" if state == "can_enter" else ""},
            data_quality="OK",
        )
        for index, state in enumerate(states)
    ]


def test_state_episode_is_counted_once_and_waiting_confirmation_is_not_event() -> None:
    trace = diagnostic_trace(
        decisions(["no_entry", "close_watch", "close_watch", "waiting_confirmation", "can_enter", "can_enter"]),
        bars_for_returns([10, 10, 11, 9, 10, 12]),
        config_hash="test",
    )
    events = diagnostic_events(trace)
    assert list(events["state_type"]) == ["close_watch", "can_enter"]


def test_forward_returns_and_excursions_are_exact_and_causal() -> None:
    bars = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=21),
            "收盘价": [100.0] + [110.0] * 20,
            "最高价": [100.0] + [120.0] * 20,
            "最低价": [100.0] + [90.0] * 20,
        }
    )
    event = diagnostic_events(
        diagnostic_trace(decisions(["can_enter"] + ["no_entry"] * 20), bars, config_hash="test")
    ).iloc[0]
    assert event["forward_close_return_5d"] == 0.10
    assert event["maximum_favorable_excursion_5d"] == 0.20
    assert event["maximum_adverse_excursion_5d"] == -0.10


def test_incomplete_horizon_keeps_event_with_null_metric() -> None:
    trace = diagnostic_trace(
        decisions(["can_enter", "no_entry", "no_entry"]),
        bars_for_returns([10.0, 10.2, 10.1]),
        config_hash="test",
    )
    event = diagnostic_events(trace).iloc[0]
    assert math.isnan(event["forward_close_return_5d"])


def test_legacy_states_map_to_comparable_event_types() -> None:
    trace = diagnostic_trace(
        decisions(["legacy_neutral", "legacy_watch", "legacy_buy"], strategy_id="legacy_v1"),
        bars_for_returns([10, 10, 10]),
        config_hash="test",
    )
    assert list(diagnostic_events(trace)["state_type"]) == ["close_watch", "can_enter"]


def test_summary_reports_positive_rate_drawdown_false_reversals_and_flips() -> None:
    states = ["can_enter"] + ["no_entry"] * 10 + ["can_enter"] + ["no_entry"] * 10
    closes = [100.0] * len(states)
    closes[10] = 90.0
    closes[21] = 110.0
    trace = diagnostic_trace(decisions(states), bars_for_returns(closes), config_hash="test")
    events = diagnostic_events(trace)
    summary = summarize_historical_diagnostics(events, trace)
    row = summary[(summary["state_type"] == "can_enter") & (summary["horizon"] == 10)].iloc[0]
    assert row["event_count"] == 2
    assert row["complete_horizon_count"] == 2
    assert row["positive_return_rate"] == 0.5
    assert row["false_reversal_10d_count"] == 1
    assert row["false_reversal_10d_rate"] == 0.5
    assert row["state_flip_frequency"] == row["transition_count"] / (row["valid_rows"] - 1)
