from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.skills.tl_timing_strategy.handler import tl_state_history


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
