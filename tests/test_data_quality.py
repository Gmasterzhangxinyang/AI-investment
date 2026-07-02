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
