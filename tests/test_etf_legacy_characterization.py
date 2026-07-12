from __future__ import annotations

from copy import deepcopy

import pandas as pd

from superpower.skills.etf_rotation_strategy.handler import latest_etf_signals, score_etf
from superpower.skills.etf_rotation_strategy.registry import default_registry


PARAMS = {
    "etf": {
        "buy_volume_ratio_min": 1.1,
        "sell_ma10_volume_ratio_min": 1.2,
        "sell_ma5_volume_ratio_min": 1.5,
        "score_weights": {
            "trend": 0.35,
            "macd": 0.25,
            "volume": 0.25,
            "share_change": 0.15,
        },
    }
}


def history(code: str = "510001", name: str = "样例ETF", rows: int = 61) -> pd.DataFrame:
    dates = pd.bdate_range("2026-03-02", periods=rows)
    return pd.DataFrame(
        [
            {
                "date": date,
                "code": code,
                "name": name,
                "开盘价": 10.0,
                "最高价": 10.1,
                "最低价": 9.9,
                "收盘价": 10.0,
                "成交量（万股）": 100.0,
                "ma5": 9.8,
                "ma10": 10.0,
                "ma20": 9.5,
                "ma60": 9.0,
                "ma20_slope_state": "flat",
                "weekly_macd_state": "green_narrowing",
                "vol_ratio60": 1.0,
                "dif": -0.02,
                "dea": -0.01,
                "macd_hist": -0.02,
                "kdj_j": 50.0,
                "份额变化（亿份）": 0.0,
            }
            for date in dates
        ]
    )


def positions(*codes: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"asset_type": "ETF", "status": "holding", "code": code} for code in codes],
        columns=["asset_type", "status", "code"],
    )


def evaluate(data: pd.DataFrame, *holding_codes: str):
    return latest_etf_signals(data, positions(*holding_codes), PARAMS)


def plugin_params() -> dict[str, object]:
    params = deepcopy(PARAMS)
    params["etf"]["active_strategy"] = "legacy_v1"
    params["etf"]["diagnostic_strategies"] = ["legacy_v1"]
    params["etf"]["strategy_profiles"] = {"legacy_v1": {}}
    return params


def test_default_registry_exposes_legacy_strategy() -> None:
    registry = default_registry()

    assert registry.create("legacy_v1").strategy_id == "legacy_v1"
    assert registry.get_metadata("legacy_v1").display_name == "原始策略"


def test_explicit_legacy_selection_adds_canonical_identity() -> None:
    data = history()

    signals, *_ = latest_etf_signals(data, positions(), plugin_params())

    row = signals.iloc[0]
    assert row["strategy_id"] == "legacy_v1"
    assert row["strategy_version"] == "1.0.0"
    assert row["medium_status"] == "not_applicable"
    assert row["short_entry_status"] == "legacy_neutral"


def test_legacy_buy_route_a_and_holding_gate() -> None:
    data = history()
    data.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    data.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60"]] = [10.1, 10.0, -0.01, 1.1]

    all_rows, buys, sells, watchlist, details = evaluate(data)

    assert all_rows.iloc[0]["signal_type"] == "buy_candidate"
    assert list(buys["code"]) == ["510001"]
    assert "MA5上穿MA10" in buys.iloc[0]["signal_reason"]
    assert "MA5同时高于MA20（增强项）" in buys.iloc[0]["signal_reason"]
    assert sells.empty
    assert watchlist.empty
    assert len(details) == 8

    _, holding_buys, _, holding_watchlist, _ = evaluate(data, "510001")
    assert holding_buys.empty
    assert holding_watchlist.empty


def test_legacy_buy_route_b_macd_cross() -> None:
    data = history()
    data.loc[59, ["ma5", "ma10", "dif", "dea"]] = [10.1, 10.0, -0.02, -0.01]
    data.loc[60, ["ma5", "ma10", "dif", "dea", "vol_ratio60"]] = [10.1, 10.0, 0.0, -0.01, 1.1]

    _, buys, _, _, _ = evaluate(data)

    assert list(buys["signal_reason"]) == ["MACD金叉"]


def test_watch_ma_cross_missing_volume() -> None:
    data = history()
    data.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    data.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60"]] = [10.1, 10.0, -0.01, 1.0]

    all_rows, buys, _, watchlist, _ = evaluate(data)

    assert buys.empty
    assert all_rows.iloc[0]["signal_type"] == "watch"
    assert list(watchlist["watch_type"]) == ["均线已触发，量能未确认"]


def test_watch_macd_near_cross_missing_volume() -> None:
    data = history()
    data.loc[59, ["dif", "dea"]] = [-0.04, -0.01]
    data.loc[60, ["dif", "dea", "vol_ratio60"]] = [-0.02, -0.01, 1.0]

    _, buys, _, watchlist, _ = evaluate(data)

    assert buys.empty
    assert list(watchlist["watch_type"]) == ["MACD接近确认，量能未确认"]


def test_watch_trend_improving_missing_volume() -> None:
    data = history()
    data.loc[59, ["ma5", "ma10", "macd_hist", "dif", "dea"]] = [10.1, 10.0, -0.02, -0.02, -0.01]
    data.loc[60, ["ma5", "ma10", "macd_hist", "dif", "dea", "vol_ratio60"]] = [
        10.1,
        10.0,
        -0.01,
        -0.02,
        -0.01,
        1.0,
    ]

    _, buys, _, watchlist, _ = evaluate(data)

    assert buys.empty
    assert list(watchlist["watch_type"]) == ["趋势改善，量能未确认"]


def test_holding_watch_evidence_stays_in_all_signals_but_not_public_watchlist() -> None:
    data = history()
    data.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    data.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60"]] = [10.1, 10.0, -0.01, 1.0]

    all_rows, _, _, watchlist, _ = evaluate(data, "510001")

    assert all_rows.iloc[0]["signal_type"] == "watch"
    assert all_rows.iloc[0]["position_status"] == "持仓中"
    assert watchlist.empty


def test_holding_sell_below_ma10_with_volume() -> None:
    data = history()
    data.loc[60, ["收盘价", "ma5", "ma10", "vol_ratio60"]] = [9.9, 9.8, 10.0, 1.2]

    _, _, sells, _, _ = evaluate(data, "510001")

    assert list(sells["signal_reason"]) == ["收盘跌破MA10且放量"]


def test_holding_sell_below_ma5_with_volume() -> None:
    data = history()
    data.loc[60, ["收盘价", "ma5", "ma10", "vol_ratio60"]] = [10.1, 10.2, 10.0, 1.5]

    _, _, sells, _, _ = evaluate(data, "510001")

    assert list(sells["signal_reason"]) == ["收盘跌破MA5且明显放量"]


def test_non_holding_sell_shape_stays_neutral() -> None:
    data = history()
    data.loc[60, ["收盘价", "ma5", "ma10", "vol_ratio60"]] = [9.0, 9.5, 10.0, 1.5]

    all_rows, buys, sells, watchlist, _ = evaluate(data)

    assert all_rows.iloc[0]["signal_type"] == "neutral"
    assert "平仓提示只对持仓生效" in all_rows.iloc[0]["reason"]
    assert buys.empty
    assert sells.empty
    assert watchlist.empty


def test_60_rows_is_data_unavailable_and_61_rows_is_evaluated() -> None:
    unavailable, *_ = evaluate(history(rows=60))
    evaluated, *_ = evaluate(history(rows=61))

    assert unavailable.iloc[0]["signal_type"] == "data_unavailable"
    assert unavailable.iloc[0]["score"] == 0.0
    assert evaluated.iloc[0]["signal_type"] == "neutral"


def test_score_and_sort_order_are_frozen() -> None:
    strong = history(code="510001", name="强ETF")
    strong.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    strong.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60", "份额变化（亿份）"]] = [
        10.1,
        10.0,
        0.01,
        1.5,
        0.2,
    ]
    weak = history(code="510002", name="弱ETF")
    weak.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    weak.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60"]] = [10.1, 10.0, -0.01, 1.1]

    all_rows, buys, _, _, _ = evaluate(pd.concat([weak, strong], ignore_index=True))

    assert score_etf(strong.iloc[-1], PARAMS) == 81.4
    assert list(buys["code"]) == ["510001", "510002"]
    assert list(all_rows.head(2)["code"]) == ["510001", "510002"]


def test_high_risk_overlay_does_not_change_legacy_candidate_score_or_order() -> None:
    high_risk = history(code="510001", name="高风险ETF")
    high_risk.loc[59, ["ma5", "ma10", "macd_hist", "收盘价"]] = [
        9.9,
        10.0,
        -0.02,
        10.0,
    ]
    high_risk.loc[
        60,
        [
            "开盘价",
            "最高价",
            "最低价",
            "收盘价",
            "ma5",
            "ma10",
            "macd_hist",
            "vol_ratio60",
            "ma20_slope_state",
        ],
    ] = [10.0, 10.6, 10.0, 10.5, 10.1, 10.0, -0.01, 2.0, "down"]
    normal = history(code="510002", name="普通ETF")
    normal.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    normal.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60"]] = [
        10.1,
        10.0,
        -0.01,
        1.1,
    ]

    all_rows, buys, _, _, _ = evaluate(
        pd.concat([normal, high_risk], ignore_index=True)
    )

    expected_score = score_etf(high_risk.iloc[-1], PARAMS)
    high_risk_row = all_rows.loc[all_rows["code"] == "510001"].iloc[0]
    assert list(buys["code"]) == ["510001", "510002"]
    assert high_risk_row["signal_type"] == "buy_candidate"
    assert high_risk_row["score"] == expected_score
    assert high_risk_row["signal_reason"].startswith("MA5上穿MA10")
    assert high_risk_row["risk_overlay_level"] == "high"
    assert "不改变原策略评分和排名" in high_risk_row["risk_overlay_summary"]


def test_detail_history_keeps_last_eight_rows_in_date_order() -> None:
    data = history(rows=65)

    _, _, _, _, details = evaluate(data)

    assert len(details) == 8
    assert list(details["date"]) == [value.date() for value in data.tail(8)["date"]]
