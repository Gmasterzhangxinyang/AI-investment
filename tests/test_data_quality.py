from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.runtime import AgentContext
from superpower.skills.data_quality_gate.handler import Skill
from superpower.skills.wind_excel_ingestion.handler import Skill as IngestionSkill
from superpower.tools.excel_reader import filter_trading_rows


def test_data_quality_reports_errors_without_raising() -> None:
    context = AgentContext(run_id="test", root_dir=ROOT)
    context.put("etf_market_raw", pd.DataFrame(columns=["date", "name", "code", "开盘价", "收盘价", "最低价", "最高价", "成交量（万股）"]))
    context.put("tl_market_raw", pd.DataFrame(columns=["date", "name", "code", "开盘价", "收盘价", "最低价", "最高价", "成交量"]))
    context.put("cb_data", pd.DataFrame())
    context.put("positions", pd.DataFrame())
    context.put("source_manifest", pd.DataFrame())
    context.put("etf_template_universe", pd.DataFrame())
    context.put("universe", {"expected_min_symbols": 1})

    result = Skill().run(context)

    assert result["fail_count"] > 0
    report = context.get("data_quality_report")
    assert "ERROR" in set(report["status"])


def test_ingestion_missing_excel_produces_empty_frames_and_warning() -> None:
    context = AgentContext(run_id="test", root_dir=ROOT)
    context.put("etf_file", ROOT / "missing_etf.xlsx")
    context.put("tl_file", ROOT / "missing_tl.xlsx")
    context.put("cb_file", None)

    result = IngestionSkill().run(context)

    assert result["warning_count"] == 2
    assert context.get("etf_market_raw").empty
    assert context.get("tl_market_raw").empty
    assert not context.get("data_ingestion_warnings").empty


def test_tl_without_code_column_does_not_crash_quality_gate() -> None:
    context = AgentContext(run_id="test", root_dir=ROOT)
    etf = pd.DataFrame(
        [
            {"date": "2026-01-01", "name": "ETF", "code": "159001.SZ", "开盘价": 1, "收盘价": 1, "最低价": 1, "最高价": 1, "成交量（万股）": 1}
            for _ in range(60)
        ]
    )
    etf["date"] = pd.date_range("2026-01-01", periods=60, freq="B")
    tl = pd.DataFrame(
        [
            {"date": date, "name": "TL", "开盘价": 100, "收盘价": 101, "最低价": 99, "最高价": 102, "成交量": 1000}
            for date in pd.date_range("2026-01-01", periods=60, freq="B")
        ]
    )
    context.put("etf_market_raw", etf)
    context.put("tl_market_raw", tl)
    context.put("cb_data", pd.DataFrame())
    context.put("positions", pd.DataFrame())
    context.put("source_manifest", pd.DataFrame())
    context.put("etf_template_universe", pd.DataFrame())
    context.put("universe", {"expected_min_symbols": 1})

    result = Skill().run(context)

    assert result["checks"] > 0
    assert "TL日期代码重复行" in set(context.get("data_quality_report")["item"])


def test_filter_trading_rows_excludes_pseudo_trading_day() -> None:
    raw = pd.DataFrame(
        [
            {"date": "2026-01-02", "name": "ETF", "code": "159001.SZ", "开盘价": 1, "收盘价": 1, "最低价": 1, "最高价": 1, "成交量（万股）": 10},
            {"date": "2026-01-03", "name": "ETF", "code": "159001.SZ", "开盘价": 0, "收盘价": 1, "最低价": 0, "最高价": 0, "成交量（万股）": 0},
        ]
    )

    filtered = filter_trading_rows(raw, "成交量（万股）")

    assert len(filtered) == 1
    assert filtered.attrs["invalid_trading_rows"] == 1
