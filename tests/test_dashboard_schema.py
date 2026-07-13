from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.runtime import AgentContext
from superpower.skills.report_generation.handler import (
    _normalise_market_indicators,
    _stable_dashboard_schema,
)


def test_stable_dashboard_schema_has_required_top_level_keys() -> None:
    context = AgentContext(run_id="test_run", root_dir=ROOT)
    context.put(
        "etf_strategy_run",
        {
            "strategy_id": "trend_pullback_v2",
            "strategy_version": "2.0.0",
            "config_hash": "a" * 64,
        },
    )
    context.put("etf_historical_diagnostics", pd.DataFrame([{"strategy_id": "trend_pullback_v2", "horizon": 10}]))
    context.put("etf_historical_diagnostic_events", pd.DataFrame([{"strategy_id": "trend_pullback_v2", "state_type": "can_enter"}]))
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
        etf_all=pd.DataFrame(
            [
                {
                    "code": "510001.SH",
                    "strategy_id": "legacy_v1",
                    "risk_overlay_level": "caution",
                    "risk_overlay_summary": "MA20仍向下；仅作风险辅助，不改变原策略评分和排名",
                }
            ]
        ),
        tl_today=pd.DataFrame(),
        tl_recent=pd.DataFrame(),
        cb_top10=pd.DataFrame(),
        cb_ranked=pd.DataFrame(
            [
                {
                    "bond_code": "110001.SH",
                    "date": "2026-07-06",
                    "strategy_id": "legacy_v1",
                    "strategy_version": "1.0.0",
                    "strategy_fallback_reason": "",
                    "overlay_id": "dynamic_v2",
                    "overlay_version": "2.0.0",
                    "overlay_enabled": True,
                    "overlay_fallback_reason": "",
                    "config_hash": "b" * 64,
                    "base_score": 70.0,
                    "auxiliary_score": 80.0,
                    "score": 70.0,
                }
            ]
        ),
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
    assert payload["convertible_bond"]["strategy"] == {
        "strategy_id": "legacy_v1",
        "strategy_version": "1.0.0",
        "display_name": "原策略",
        "fallback_reason": "",
        "overlay_id": "dynamic_v2",
        "overlay_version": "2.0.0",
        "overlay_enabled": True,
        "overlay_display_name": "动态辅助",
        "overlay_fallback_reason": "",
        "config_hash": "b" * 64,
        "source_date": "2026-07-06",
    }
    assert "key_points" in payload["report_summary"]
    assert payload["etf"]["strategy"]["strategy_id"] == "trend_pullback_v2"
    assert payload["etf"]["strategy"]["strategy_version"] == "2.0.0"
    assert len(payload["etf"]["strategy"]["config_hash"]) == 64
    assert payload["etf"]["historical_diagnostics"]
    assert payload["etf"]["historical_diagnostic_events"]
    assert payload["etf"]["all_signals"][0]["risk_overlay_level"] == "caution"
    assert "不改变原策略评分和排名" in payload["etf"]["all_signals"][0]["risk_overlay_summary"]


def test_tl_market_payload_preserves_fund_share_change() -> None:
    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-07-09"),
                "code": "TL.CFE",
                "name": "30年国债期货TL",
                "收盘价": 113.86,
                "成交量": 1000,
                "份额变化（亿份）": 0.0802,
            }
        ]
    )

    result = _normalise_market_indicators(frame, asset_type="TL", volume_field="成交量")

    assert result.iloc[0]["fund_share_change"] == 0.0802
