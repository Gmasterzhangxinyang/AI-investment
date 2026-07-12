from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.cli.run_daily import _append_audit_warnings, _audit_requires_exit
from superpower.audit.latest import _add_etf_audit_indicators


def test_audit_default_does_not_require_exit_but_strict_does() -> None:
    qa_result = {"status": "FAIL", "checks": []}
    assert not _audit_requires_exit(qa_result, strict_audit=False)
    assert _audit_requires_exit(qa_result, strict_audit=True)


def test_audit_warnings_are_written_to_dashboard_run_info() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "dashboard.json"
        path.write_text(json.dumps({"run_info": {"warnings": []}}, ensure_ascii=False), encoding="utf-8")
        _append_audit_warnings(
            path,
            {
                "status": "FAIL",
                "checks": [{"name": "x", "status": "FAIL", "detail": "bad"}],
            },
        )
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        assert dashboard["run_info"]["status"] == "partial_success"
        assert any("QA audit status=FAIL" in warning for warning in dashboard["run_info"]["warnings"])


def test_audit_uses_same_etf_specific_indicators_as_live_strategy() -> None:
    rows = 220
    raw = pd.DataFrame(
        {
            "date": pd.bdate_range("2025-01-02", periods=rows),
            "name": "样例ETF",
            "code": "510001",
            "开盘价": 10.0,
            "最高价": 10.1,
            "最低价": 9.9,
            "收盘价": [10 + index * 0.01 for index in range(rows)],
            "成交量（万股）": 100.0,
        }
    )
    enriched = _add_etf_audit_indicators(
        raw,
        {"etf": {"active_strategy": "trend_pullback_v2"}},
    )
    assert {
        "ma20_slope_5d",
        "ma20_slope_state",
        "weekly_macd_hist",
        "weekly_macd_state",
    } <= set(enriched.columns)
