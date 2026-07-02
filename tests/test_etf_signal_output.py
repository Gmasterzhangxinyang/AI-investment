from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.skills.etf_rotation_strategy.handler import latest_etf_signals


def test_etf_signal_rows_include_delivery_evidence_fields() -> None:
    dates = pd.date_range("2026-01-01", periods=62, freq="B")
    rows = []
    for i, date in enumerate(dates):
        rows.append(
            {
                "date": date,
                "name": "测试ETF",
                "code": "159999.SZ",
                "开盘价": 1.0,
                "收盘价": 1.0 + i * 0.001,
                "最高价": 1.1,
                "最低价": 0.9,
                "成交量（万股）": 100,
                "ma5": 1.0,
                "ma10": 1.0,
                "ma20": 0.99,
                "ma60": 0.95,
                "vol_ratio60": 1.2,
                "dif": 0.01,
                "dea": 0.02,
                "macd_hist": -0.01,
                "kdj_j": 50,
            }
        )
    rows[-2]["ma5"] = 0.99
    rows[-2]["ma10"] = 1.0
    rows[-2]["macd_hist"] = -0.02
    rows[-1]["ma5"] = 1.01
    rows[-1]["ma10"] = 1.0
    rows[-1]["macd_hist"] = -0.01

    signals, buys, sells, watchlist, _ = latest_etf_signals(
        pd.DataFrame(rows),
        pd.DataFrame(columns=["asset_type", "code", "status"]),
        {"etf": {"buy_volume_ratio_min": 1.1, "sell_ma10_volume_ratio_min": 1.2, "sell_ma5_volume_ratio_min": 1.5, "score_weights": {"trend": 0.35, "macd": 0.25, "volume": 0.25, "share_change": 0.15}}},
    )

    assert not signals.empty
    assert buys.iloc[0]["signal_type"] == "buy_candidate"
    assert buys.iloc[0]["action"] == "模型触发建仓候选"
    for column in ["reason", "metrics", "rule_hits", "risk_notes", "confidence", "data_quality"]:
        assert column in signals.columns
    assert sells.empty
    assert watchlist.empty
