from __future__ import annotations

import pandas as pd
import pytest

from superpower.skills.tl_timing_strategy.fund_flow import (
    attach_fund_flow_diagnostics,
)


def frame(changes: list[float | None], *, status: str = "neutral") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-06-01", periods=len(changes)),
            "status": status,
            "份额变化（亿份）": changes,
        }
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (0.0, "正常波动"),
        (0.0299, "正常波动"),
        (0.03, "轻度申购"),
        (-0.03, "轻度赎回"),
        (0.05, "明显申购"),
        (-0.05, "明显赎回"),
        (0.07, "极端申购"),
        (-0.07, "极端赎回"),
        (0.20, "极端申购"),
        (-0.20, "极端赎回"),
        (0.2001, "待核验"),
        (-0.2001, "待核验"),
    ],
)
def test_daily_flow_boundaries(change: float, expected: str) -> None:
    result = attach_fund_flow_diagnostics(frame([change]), {})

    assert result.iloc[-1]["fund_share_daily_level"] == expected
    assert result.iloc[-1]["fund_share_change_daily"] == change


def test_review_only_extreme_is_preserved_but_excluded_from_rolling_sum() -> None:
    result = attach_fund_flow_diagnostics(
        frame([0.04, 0.04, 2.918147, -0.01, 0.02]),
        {},
    )
    latest = result.iloc[-1]

    assert result.iloc[2]["fund_share_change_daily"] == 2.918147
    assert result.iloc[2]["fund_share_daily_level"] == "待核验"
    assert latest["fund_share_5d_sum"] == pytest.approx(0.09)
    assert latest["fund_share_5d_valid_days"] == 4
    assert latest["fund_flow_state"] == "持续流入"


def test_five_session_outflow_and_day_counts() -> None:
    latest = attach_fund_flow_diagnostics(
        frame([-0.03, -0.02, 0.01, -0.04, -0.01]),
        {},
    ).iloc[-1]

    assert latest["fund_share_5d_sum"] == pytest.approx(-0.09)
    assert latest["fund_share_5d_valid_days"] == 5
    assert latest["fund_share_5d_inflow_days"] == 1
    assert latest["fund_share_5d_outflow_days"] == 4
    assert latest["fund_flow_state"] == "持续流出"


def test_missing_column_is_unavailable_and_does_not_raise() -> None:
    source = frame([0.01, 0.02]).drop(columns=["份额变化（亿份）"])
    result = attach_fund_flow_diagnostics(source, {})

    assert result["fund_share_change_daily"].isna().all()
    assert set(result["fund_flow_state"]) == {"数据不足"}
    assert set(result["fund_flow_data_quality"]) == {"UNAVAILABLE"}


def test_numeric_zero_is_valid_but_three_consecutive_zeros_warn_about_freshness() -> None:
    result = attach_fund_flow_diagnostics(frame([0.01, 0.0, 0.0, 0.0]), {})
    latest = result.iloc[-1]

    assert latest["fund_share_change_daily"] == 0.0
    assert latest["fund_share_5d_valid_days"] == 4
    assert latest["fund_flow_data_quality"] == "WARN"
    assert "连续3日为0" in latest["fund_flow_note"]


@pytest.mark.parametrize(
    ("status", "changes", "relation"),
    [
        ("attention", [0.02] * 5, "同向改善"),
        ("entry_candidate", [-0.02] * 5, "技术资金背离"),
        ("no_trade", [-0.02] * 5, "共同走弱"),
        ("no_trade", [0.02] * 5, "逆势流入"),
        ("neutral", [0.02] * 5, "中性观察"),
    ],
)
def test_flow_relation_is_an_overlay_on_technical_status(
    status: str,
    changes: list[float],
    relation: str,
) -> None:
    latest = attach_fund_flow_diagnostics(
        frame(changes, status=status),
        {},
    ).iloc[-1]

    assert latest["fund_flow_relation"] == relation
    assert relation in latest["fund_flow_note"]
