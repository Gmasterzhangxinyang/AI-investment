import pandas as pd
import pytest

from superpower.skills.etf_rotation_strategy.contracts import MediumStatus
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.medium_trend import (
    evaluate_medium_history,
    evaluate_medium_trend,
)


def row(**overrides: object) -> pd.Series:
    values = {
        "收盘价": 10.5,
        "vol_ratio60": 1.2,
        "ma5": 10.3,
        "ma20": 10.0,
        "ma20_slope_5d": 0.0,
        "ma20_slope_state": "flat",
        "weekly_macd_hist": 0.02,
        "weekly_macd_state": "red_strengthening",
        "macd_hist": 0.01,
    }
    values.update(overrides)
    return pd.Series(values)


def test_falling_ma20_is_hard_veto_even_with_daily_strength() -> None:
    result = evaluate_medium_trend(
        row(ma20_slope_5d=-0.004, ma20_slope_state="down", vol_ratio60=3.0),
        row(ma5=9.9),
        {},
    )

    assert result.status is MediumStatus.DO_NOT_PARTICIPATE
    assert "ma20_slope_down" in result.rule_hits


def test_weekly_green_widening_is_hard_veto() -> None:
    result = evaluate_medium_trend(
        row(weekly_macd_hist=-0.02, weekly_macd_state="green_widening"),
        row(),
        {},
    )

    assert result.status is MediumStatus.DO_NOT_PARTICIPATE
    assert "weekly_macd_green_widening" in result.rule_hits


def test_all_confirmations_make_persistent_trend_confirmed() -> None:
    result = evaluate_medium_trend(row(), row(ma5=10.2, ma20=10.0), {})

    assert result.status is MediumStatus.TREND_CONFIRMED
    assert result.ma5_crossed_ma20_today is False


def test_cross_event_is_recorded_separately_from_persistent_state() -> None:
    result = evaluate_medium_trend(row(), row(ma5=9.9, ma20=10.0), {})

    assert result.status is MediumStatus.TREND_CONFIRMED
    assert result.ma5_crossed_ma20_today is True


@pytest.mark.parametrize(
    "field",
    ["ma20", "ma20_slope_5d", "weekly_macd_hist", "macd_hist", "vol_ratio60"],
)
def test_required_missing_field_returns_data_unavailable(field: str) -> None:
    result = evaluate_medium_trend(row(**{field: float("nan")}), row(), {})

    assert result.status is MediumStatus.DATA_UNAVAILABLE
    assert field in result.missing_conditions


def test_zero_weekly_hist_is_not_confirmed() -> None:
    result = evaluate_medium_trend(
        row(weekly_macd_hist=0.0, weekly_macd_state="neutral_zero"),
        row(),
        {},
    )

    assert result.status is MediumStatus.TREND_NOT_CONFIRMED


def test_history_wrapper_marks_first_row_unavailable_without_previous_data() -> None:
    rows = pd.DataFrame([row().to_dict(), row().to_dict()])

    results = evaluate_medium_history(rows, {})

    assert results[0].status is MediumStatus.DATA_UNAVAILABLE
    assert results[1].status is MediumStatus.TREND_CONFIRMED
