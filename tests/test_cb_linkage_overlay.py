from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.tools.excel_reader import parse_convertible_bond_excel
from superpower.skills.convertible_bond_ranking.linkage import classify_linkage


DEFAULT_CONFIG = {
    "validation_tolerance": 0.05,
    "stock_strong_threshold": 3.0,
    "stock_weak_threshold": -3.0,
    "bond_strong_threshold": 3.0,
    "bond_weak_threshold": -2.0,
    "relative_gap_threshold": 2.0,
    "premium_expand_threshold": 2.0,
    "premium_compress_threshold": -2.0,
}


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


def _linkage_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "conversion_premium_rate": 25.5,
        "stock_daily_return": 1.0,
        "bond_daily_return": 0.8,
        "previous_conversion_premium_rate": 25.0,
        "conversion_premium_change": 0.5,
    }
    row.update(overrides)
    return row


def test_linkage_classifier_marks_catch_up_at_exact_boundaries() -> None:
    result = classify_linkage(
        _linkage_row(
            conversion_premium_rate=23.0,
            stock_daily_return=3.0,
            bond_daily_return=1.0,
            previous_conversion_premium_rate=25.0,
            conversion_premium_change=-2.0,
        ),
        DEFAULT_CONFIG,
    )

    assert result["linkage_state"] == "关注补涨"
    assert result["linkage_is_abnormal"] is True
    assert "不改变原排名" in result["linkage_note"]


def test_linkage_classifier_marks_chase_risk_at_exact_boundaries() -> None:
    result = classify_linkage(
        _linkage_row(
            conversion_premium_rate=27.0,
            stock_daily_return=1.0,
            bond_daily_return=3.0,
            previous_conversion_premium_rate=25.0,
            conversion_premium_change=2.0,
        ),
        DEFAULT_CONFIG,
    )

    assert result["linkage_state"] == "谨慎追涨"
    assert result["linkage_is_abnormal"] is True


def test_linkage_classifier_marks_joint_weakness() -> None:
    result = classify_linkage(
        _linkage_row(
            conversion_premium_rate=24.0,
            stock_daily_return=-3.0,
            bond_daily_return=-2.0,
            previous_conversion_premium_rate=25.0,
            conversion_premium_change=-1.0,
        ),
        DEFAULT_CONFIG,
    )

    assert result["linkage_state"] == "联动走弱"
    assert result["linkage_is_abnormal"] is True


def test_linkage_classifier_keeps_near_threshold_row_normal() -> None:
    result = classify_linkage(
        _linkage_row(
            conversion_premium_rate=23.01,
            stock_daily_return=2.99,
            bond_daily_return=0.99,
            previous_conversion_premium_rate=25.0,
            conversion_premium_change=-1.99,
        ),
        DEFAULT_CONFIG,
    )

    assert result["linkage_state"] == "正常联动"
    assert result["linkage_is_abnormal"] is False
    assert result["linkage_note"] == ""


def test_linkage_classifier_does_not_guess_when_data_is_missing() -> None:
    result = classify_linkage(
        _linkage_row(stock_daily_return=None, conversion_premium_change=None),
        DEFAULT_CONFIG,
    )

    assert result["linkage_state"] == "数据不足"
    assert result["linkage_is_abnormal"] is False
    assert result["linkage_data_quality"] == "MISSING"


def test_linkage_classifier_rejects_inconsistent_premium_change_before_market_state() -> None:
    result = classify_linkage(
        _linkage_row(
            conversion_premium_rate=30.0,
            stock_daily_return=-5.0,
            bond_daily_return=-4.0,
            previous_conversion_premium_rate=25.0,
            conversion_premium_change=2.0,
        ),
        DEFAULT_CONFIG,
    )

    assert result["linkage_state"] == "数据待核验"
    assert result["linkage_is_abnormal"] is True
    assert result["linkage_data_quality"] == "REVIEW"
