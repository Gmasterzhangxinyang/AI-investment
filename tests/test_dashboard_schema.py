from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.runtime import AgentContext
from superpower.skills.report_generation.handler import _stable_dashboard_schema


def test_stable_dashboard_schema_has_required_top_level_keys() -> None:
    context = AgentContext(run_id="test_run", root_dir=ROOT)
    quality = pd.DataFrame([{"item": "ETF行情行数", "status": "ERROR", "detail": 0, "note": ""}])
    dashboard = pd.DataFrame([{"item": "ETF建仓候选数量", "value": 0}, {"item": "ETF关注池数量", "value": 0}, {"item": "TL今日状态", "value": "数据不足，无法判断"}, {"item": "可转债Top10数量", "value": 0}])

    payload = _stable_dashboard_schema(
        context=context,
        report_date="20260626",
        dashboard=dashboard,
        quality=quality,
        etf_buys=pd.DataFrame(),
        etf_watchlist=pd.DataFrame(),
        etf_sells=pd.DataFrame(),
        etf_all=pd.DataFrame(),
        tl_today=pd.DataFrame(),
        tl_recent=pd.DataFrame(),
        cb_top10=pd.DataFrame(),
        cb_ranked=pd.DataFrame(),
        cb_excluded=pd.DataFrame(),
        cb_qualified=pd.DataFrame(),
        cb_weak_watch=pd.DataFrame(),
        cb_risk_watch=pd.DataFrame(),
        cb_quality_summary={},
        backtest_summary=pd.DataFrame(),
        backtest_next_day_checks=pd.DataFrame(),
        risk=pd.DataFrame(),
        llm_usage={},
        safety_scan=pd.DataFrame(),
    )

    assert {"run_info", "data_quality", "etf", "tl", "convertible_bond", "report_summary"}.issubset(payload)
    assert payload["data_quality"]["overall_status"] == "ERROR"
    assert "warnings" in payload["run_info"]
    assert {"etf", "tl", "convertible_bond"}.issubset(payload["data_quality"])
    assert "all_signals" in payload["etf"]
    assert payload["tl"]["status"] == "unavailable"
    assert "candidates" in payload["convertible_bond"]
    assert "qualified" in payload["convertible_bond"]
    assert "weak_watch" in payload["convertible_bond"]
    assert "risk_watch" in payload["convertible_bond"]
    assert "summary" in payload["convertible_bond"]
    assert "key_points" in payload["report_summary"]
