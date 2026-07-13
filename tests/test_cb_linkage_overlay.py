from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.tools.excel_reader import parse_convertible_bond_excel


def _write_cb_workbook(tmp_path: Path, **linkage: object) -> Path:
    row = {
        "是否纳入": None,
        "日期": "2026-07-06",
        "转债代码": "110001.SH",
        "转债名称": "测试转债",
        "转债价格": 112.5,
        "转股溢价率": 22.6,
        "正股当日涨幅（%）": linkage.get("stock_return"),
        "转债当日涨幅": linkage.get("bond_return"),
        "前日转股溢价率": linkage.get("previous_premium"),
        "转股溢价率当日变化": linkage.get("premium_change"),
    }
    path = tmp_path / "convertible-linkage.xlsx"
    pd.DataFrame([row]).to_excel(path, sheet_name="可转债数据", startrow=4, index=False)
    return path


def test_parser_keeps_convertible_linkage_fields(tmp_path: Path) -> None:
    path = _write_cb_workbook(
        tmp_path,
        stock_return=3.2,
        bond_return=0.8,
        previous_premium=25.0,
        premium_change=-2.4,
    )

    row = parse_convertible_bond_excel(path).iloc[0]

    assert row["stock_daily_return"] == 3.2
    assert row["bond_daily_return"] == 0.8
    assert row["previous_conversion_premium_rate"] == 25.0
    assert row["conversion_premium_change"] == -2.4


def test_parser_does_not_turn_blank_linkage_values_into_zero(tmp_path: Path) -> None:
    row = parse_convertible_bond_excel(_write_cb_workbook(tmp_path)).iloc[0]

    assert pd.isna(row["stock_daily_return"])
    assert pd.isna(row["bond_daily_return"])
    assert pd.isna(row["previous_conversion_premium_rate"])
    assert pd.isna(row["conversion_premium_change"])
