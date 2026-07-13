from __future__ import annotations

import json

from superpower.db.connection import get_connection
from superpower.db.ingest import ingest_dashboard


def _dashboard() -> dict[str, object]:
    base: dict[str, object] = {
        "reportDate": "2026-07-10",
        "reportPath": "report.xlsx",
        "sourceManifest": [],
        "summary": [],
        "researchSummary": [],
        "etfBuyCandidates": [],
        "etfWatchlist": [],
        "etfSellAlerts": [],
        "etfDetailHistory": [],
        "etf": {"all_signals": []},
        "tlToday": [],
        "tlRecent": [],
        "dataQuality": [],
        "agentAudit": [],
        "aiCommitteeReviews": [],
        "riskSummary": [],
        "backtestSummary": [],
        "backtestTrades": [],
        "backtestNextDayChecks": [],
    }
    base["cbRanked"] = [
        {
            "date": "2026-07-06",
            "bond_code": "R1",
            "bond_name": "候选转债",
            "rank": 1,
            "score": 45,
            "base_score": 45,
            "base_grade": "C",
            "strategy_id": "legacy_v1",
            "strategy_version": "1.0.0",
            "overlay_id": "dynamic_v2",
            "overlay_version": "2.0.0",
            "overlay_enabled": True,
            "config_hash": "a" * 64,
            "auxiliary_score": 60,
            "auxiliary_state": "关注补涨",
        }
    ]
    base["cbExcluded"] = [
        {"date": "2026-07-06", "bond_code": "E1", "bond_name": "排除一", "excluded_reason": "价格低于100元"},
        {"date": "2026-07-06", "bond_code": "E2", "bond_name": "排除二", "excluded_reason": "已发布强赎公告"},
    ]
    return base


def test_ingest_persists_ranked_and_excluded_convertibles(tmp_path) -> None:
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(_dashboard(), ensure_ascii=False), encoding="utf-8")

    ingest_dashboard(tmp_path, "run-1", path)

    with get_connection(tmp_path) as connection:
        rows = connection.execute(
            "SELECT * FROM convertible_bond_snapshots WHERE report_date=? ORDER BY bond_code",
            ("2026-07-10",),
        ).fetchall()

    assert len(rows) == 3
    assert {row["record_status"] for row in rows} == {"ranked", "excluded"}
    assert {row["source_date"] for row in rows} == {"2026-07-06"}
    ranked = next(row for row in rows if row["record_status"] == "ranked")
    assert ranked["base_score"] == 45
    assert ranked["auxiliary_state"] == "关注补涨"
    assert ranked["config_hash"] == "a" * 64
