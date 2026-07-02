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

