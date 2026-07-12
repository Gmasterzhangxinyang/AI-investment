from __future__ import annotations

from datetime import datetime

from openpyxl import Workbook

from superpower.tools.excel_reader import parse_wind_wide_excel


def test_auxiliary_instrument_field_is_aligned_to_primary_tl_by_date(tmp_path) -> None:
    path = tmp_path / "tl-with-etf-flow.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "TL日频公式区"
    sheet.append(["TL", "30年国债期货TL", None, None, None, None, None, None, None, "30年国债ETF"])
    sheet.append([None, "TL.CFE", "TL.CFE", "TL.CFE", "TL.CFE", "TL.CFE", "TL.CFE", "TL.CFE", "TL.CFE", "511090.SH"])
    sheet.append(["日期", "开盘价", "收盘价", "最低价", "最高价", "成交量", "成交额(亿元）", "持仓量", "持仓量变化", "份额变化（亿份）"])
    sheet.append([datetime(2026, 7, 8), 113.62, 113.94, 113.48, 113.99, 90726, 1031.72, 178575, 6348, 0.0460])
    sheet.append([datetime(2026, 7, 9), 113.94, 113.86, 113.81, 114.01, 62305, 709.72, 179846, 1271, 0.0802])
    workbook.save(path)

    result = parse_wind_wide_excel(path, "成交量")

    assert list(result["code"]) == ["TL.CFE", "TL.CFE"]
    assert list(result["份额变化（亿份）"]) == [0.0460, 0.0802]
