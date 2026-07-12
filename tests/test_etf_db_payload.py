from __future__ import annotations

import json

from superpower.db.ingest import ingest_dashboard
from superpower.db.repositories import DatabaseRepository


def test_neutral_v2_state_is_discoverable_without_public_signal(tmp_path) -> None:
    dashboard = {
        "reportDate": "2026-07-10",
        "reportPath": "report.xlsx",
        "sourceManifest": [],
        "summary": [],
        "researchSummary": [],
        "etfBuyCandidates": [],
        "etfWatchlist": [],
        "etfSellAlerts": [],
        "etfDetailHistory": [],
        "etf": {
            "all_signals": [
                {
                    "date": "2026-07-10",
                    "code": "510001",
                    "name": "样例ETF",
                    "strategy_id": "trend_pullback_v2",
                    "medium_status": "trend_not_confirmed",
                    "short_entry_status": "no_entry",
                    "weekly_macd_state": "green_narrowing",
                    "ma20_slope_state": "flat",
                    "close": 10.0,
                }
            ]
        },
        "tlToday": [],
        "tlRecent": [],
        "cbTop10": [],
        "cbRanked": [],
        "dataQuality": [],
        "agentAudit": [],
        "aiCommitteeReviews": [],
        "riskSummary": [],
        "backtestSummary": [],
        "backtestTrades": [],
        "backtestNextDayChecks": [],
    }
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(dashboard, ensure_ascii=False), encoding="utf-8")

    ingest_dashboard(tmp_path, "run-test", path)
    detail = DatabaseRepository(tmp_path).asset_detail("510001")
    latest = detail["latestMarketBar"]

    assert latest["strategy_id"] == "trend_pullback_v2"
    assert latest["medium_status"] == "trend_not_confirmed"
    assert latest["short_entry_status"] == "no_entry"
    assert latest["weekly_macd_state"] == "green_narrowing"
    assert latest["ma20_slope_state"] == "flat"
