from __future__ import annotations

import sys
from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.skills.tl_timing_strategy.handler import tl_state_history
from superpower.skills.technical_indicators.handler import add_indicators


def test_empty_tl_outputs_unavailable_contract() -> None:
    out = tl_state_history(pd.DataFrame(), {"tl": {"daily_kdj_lookback": 3, "weekly_kdj_lookback": 2}})
    assert out.iloc[0]["status"] == "unavailable"
    assert out.iloc[0]["display_status"] == "数据不足，无法判断"
    assert out.iloc[0]["data_quality"] == "ERROR"


def test_insufficient_tl_history_cannot_emit_entry_candidate() -> None:
    tl = pd.DataFrame(
        [
            {
                "date": date,
                "code": "TL.CFE",
                "name": "30年国债期货TL",
                "开盘价": 100,
                "最高价": 101,
                "最低价": 99,
                "收盘价": 100.5,
                "成交量": 1000,
                "macd_hist": 0.01,
                "kdj_j": 10,
            }
            for date in pd.date_range("2026-01-01", periods=20, freq="B")
        ]
    )

    out = tl_state_history(tl, {"tl": {"daily_kdj_lookback": 3, "weekly_kdj_lookback": 2}})

    assert set(out["status"]) == {"unavailable"}
    assert not out["buy_signal"].any()
    assert out.iloc[-1]["confidence"] == "low"


def test_fund_flow_overlay_never_changes_existing_tl_signals() -> None:
    dates = pd.bdate_range("2025-10-01", periods=100)
    raw = pd.DataFrame(
        {
            "date": dates,
            "code": "TL.CFE",
            "name": "30年国债期货TL",
            "开盘价": [110 + index * 0.01 for index in range(100)],
            "最高价": [110.2 + index * 0.01 for index in range(100)],
            "最低价": [109.8 + index * 0.01 for index in range(100)],
            "收盘价": [110.05 + index * 0.01 for index in range(100)],
            "成交量": [1000 + index for index in range(100)],
        }
    )
    indicators = add_indicators(raw, "成交量")
    with_flow = indicators.copy()
    with_flow["份额变化（亿份）"] = [0.0] * 95 + [-0.02] * 5
    params = json.loads((ROOT / "configs" / "strategy_params.json").read_text(encoding="utf-8"))

    baseline = tl_state_history(indicators, params)
    enriched = tl_state_history(with_flow, params)

    frozen = [
        "status",
        "buy_signal",
        "attention_signal",
        "no_trade_signal",
        "reason",
        "rule_hits",
    ]
    pd.testing.assert_frame_equal(baseline[frozen], enriched[frozen])
    assert enriched.iloc[-1]["fund_flow_state"] == "持续流出"
    assert enriched.iloc[-1]["fund_share_5d_sum"] == -0.1
    assert baseline.iloc[-1]["fund_flow_state"] == "数据不足"
