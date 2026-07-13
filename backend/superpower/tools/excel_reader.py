from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def parse_wind_wide_excel(path: Path, volume_field: str) -> pd.DataFrame:
    """Parse current Wind-style wide workbook into normalized rows.

    Expected Wind wide layout:
    row 1: instrument name
    row 2: instrument code
    row 3: field names
    col A from row 4: dates

    The customer delivery template has front-facing maintenance sheets before
    the Wind raw sheets, so this reader tries each worksheet until it finds a
    valid Wind wide table with the requested volume field. Legacy single-sheet
    exports still work because their first sheet is valid.
    """
    errors: list[str] = []
    for sheet_name in pd.ExcelFile(path).sheet_names:
        try:
            return _parse_wind_wide_sheet(path, sheet_name, volume_field)
        except ValueError as exc:
            errors.append(f"{sheet_name}: {exc}")
    raise ValueError(f"{path.name} contains no usable Wind wide table for {volume_field}. Tried: {errors[:6]}")


def read_etf_control_sheet(path: Path) -> pd.DataFrame:
    """Read the split customer ETF template control sheet, if present."""
    try:
        xls = pd.ExcelFile(path)
    except Exception:
        return pd.DataFrame()
    if "ETF清单和持仓" not in xls.sheet_names:
        return pd.DataFrame()

    df = pd.read_excel(path, sheet_name="ETF清单和持仓", header=4)
    if df.empty:
        return df
    return df.rename(columns={str(col).strip(): str(col).strip() for col in df.columns})


def parse_enabled_etf_universe(path: Path) -> pd.DataFrame:
    df = read_etf_control_sheet(path)
    required = {"是否纳入", "ETF代码", "ETF名称"}
    if df.empty or not required.issubset(set(df.columns)):
        return pd.DataFrame(columns=["code", "name"])

    universe = df[df["是否纳入"].astype(str).str.upper().str.strip() == "Y"].copy()
    universe["code"] = universe["ETF代码"].astype(str).str.strip()
    universe["name"] = universe["ETF名称"].astype(str).str.strip()
    universe = universe[(universe["code"] != "") & (universe["code"].str.lower() != "nan")]
    return universe[["code", "name"]].drop_duplicates("code", keep="first").reset_index(drop=True)


def filter_etf_market_to_universe(market: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if universe.empty:
        return market
    enabled_codes = set(universe["code"].astype(str))
    name_by_code = dict(zip(universe["code"], universe["name"], strict=False))
    filtered = market[market["code"].astype(str).isin(enabled_codes)].copy()
    filtered.attrs.update(market.attrs)
    if filtered.empty:
        return filtered
    filtered["name"] = filtered["code"].map(name_by_code).fillna(filtered["name"])
    return filtered.drop_duplicates(["date", "code"], keep="first").sort_values(["code", "date"]).reset_index(drop=True)


def parse_positions_from_etf_workbook(path: Path) -> pd.DataFrame:
    df = read_etf_control_sheet(path)
    required = {"ETF代码", "ETF名称", "客户状态"}
    columns = [
        "asset_type",
        "code",
        "name",
        "status",
        "entry_date",
        "entry_price",
        "position_size",
        "notes",
    ]
    if df.empty or not required.issubset(set(df.columns)):
        return pd.DataFrame(columns=columns)
    if "是否纳入" in df.columns:
        df = df[df["是否纳入"].astype(str).str.upper().str.strip() == "Y"].copy()
    df = df.drop_duplicates("ETF代码", keep="first")

    status_map = {
        "持有": "holding",
        "已平仓": "closed",
        "空仓": "flat",
        "观察": "watch",
        "holding": "holding",
        "closed": "closed",
        "flat": "flat",
        "watch": "watch",
    }
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        code = str(row.get("ETF代码", "")).strip()
        if not code or code.lower() == "nan":
            continue
        raw_status = str(row.get("客户状态", "")).strip()
        if not raw_status or raw_status.lower() == "nan":
            continue
        rows.append(
            {
                "asset_type": "ETF",
                "code": code,
                "name": str(row.get("ETF名称", "")).strip(),
                "status": status_map.get(raw_status, raw_status.lower()),
                "entry_date": row.get("买入日期", None),
                "entry_price": None,
                "position_size": row.get("持仓数量", None),
                "notes": row.get("备注", None),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def parse_convertible_bond_excel(path: Path | None) -> pd.DataFrame:
    """Read the customer convertible-bond workbook into one normalized table.

    The split customer template uses four title/blank rows and headers on row 5.
    This reader also accepts ordinary first-row headers so that exported Wind
    snapshots can be pasted into a simple sheet without breaking ingestion.
    """
    columns = [
        "enabled",
        "date",
        "bond_code",
        "bond_name",
        "price",
        "remaining_years",
        "conversion_premium_rate",
        "ytm",
        "stock_code",
        "stock_name",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "profit_growth_25_vs_24",
        "latest_half_profit_growth",
        "stock_price",
        "conversion_price",
        "stock_daily_return",
        "bond_daily_return",
        "previous_conversion_premium_rate",
        "conversion_premium_change",
        "redemption_trigger_ratio",
        "redemption_triggered",
        "redemption_announcement_date",
        "no_redemption_announcement_date",
        "issue_size",
        "remaining_size",
        "unconverted_ratio",
        "maturity_date",
        "bond_rating",
        "sw_l1",
        "sw_l2",
        "notes",
    ]
    if path is None:
        return pd.DataFrame(columns=columns)
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=columns)

    errors: list[str] = []
    for sheet_name in pd.ExcelFile(path).sheet_names:
        for header_row in (4, 0):
            try:
                raw = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
                parsed = _normalize_convertible_bond_frame(raw)
                if not parsed.empty:
                    return parsed
            except ValueError as exc:
                errors.append(f"{sheet_name}/header={header_row}: {exc}")
    return pd.DataFrame(columns=columns)


def _normalize_convertible_bond_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        raise ValueError("empty sheet")
    raw = raw.rename(columns={str(col).strip(): str(col).strip() for col in raw.columns})
    aliases = {
        "是否纳入": "enabled",
        "日期": "date",
        "转债代码": "bond_code",
        "转债名称": "bond_name",
        "价格": "price",
        "转债价格": "price",
        "剩余期限": "remaining_years",
        "转股溢价率": "conversion_premium_rate",
        "到期收益率": "ytm",
        "正股代码": "stock_code",
        "正股名称": "stock_name",
        "扣非净利润增长率": "deducted_profit_growth",
        "3Y avg扣非净利润增长率": "deducted_profit_growth",
        "25 vs 3Y avg扣非净利润增长率": "profit_growth_acceleration",
        "正股价格": "stock_price",
        "最新转股价": "conversion_price",
        "正股当日涨幅（%）": "stock_daily_return",
        "转债当日涨幅": "bond_daily_return",
        "前日转股溢价率": "previous_conversion_premium_rate",
        "转股溢价率当日变化": "conversion_premium_change",
        "触发赎回比例": "redemption_trigger_ratio",
        "是否满足触发价格": "redemption_triggered",
        "赎回公告日": "redemption_announcement_date",
        "不强赎提示公告日": "no_redemption_announcement_date",
        "发行规模": "issue_size",
        "存续规模": "remaining_size",
        "未转股票比例": "unconverted_ratio",
        "到期日期": "maturity_date",
        "债项评级": "bond_rating",
        "申万一级行业": "sw_l1",
        "申万二级行业": "sw_l2",
        "23 vs. 22": "profit_growth_23_vs_22",
        "24 vs. 23": "profit_growth_24_vs_23",
        "25 vs. 24": "profit_growth_25_vs_24",
        "26H1 vs 26H2": "latest_half_profit_growth",
        "到期兑付价格": "maturity_redemption_price",
        "备注": "notes",
        "code": "bond_code",
        "name": "bond_name",
        "close": "price",
        "premium_rate": "conversion_premium_rate",
        "profit_growth": "deducted_profit_growth",
    }
    date_aliases = {}
    for col in raw.columns:
        parsed_col = pd.to_datetime(col, errors="coerce")
        if pd.isna(parsed_col):
            continue
        timestamp = pd.Timestamp(parsed_col)
        if timestamp.month == 12 and timestamp.day == 31:
            date_aliases[col] = f"deducted_profit_{timestamp.year}"
        elif timestamp.month == 6 and timestamp.day == 30:
            date_aliases[col] = f"deducted_profit_h1_{timestamp.year}"

    renamed = raw.rename(columns={col: aliases[col] for col in raw.columns if col in aliases}).rename(columns=date_aliases).copy()
    required = {"bond_code", "bond_name", "price"}
    if not required.issubset(set(renamed.columns)):
        raise ValueError(f"missing required convertible bond columns: {sorted(required - set(renamed.columns))}")

    for col in [
        "enabled",
        "date",
        "bond_code",
        "bond_name",
        "price",
        "remaining_years",
        "conversion_premium_rate",
        "ytm",
        "stock_code",
        "stock_name",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "profit_growth_23_vs_22",
        "profit_growth_24_vs_23",
        "profit_growth_25_vs_24",
        "latest_half_profit_growth",
        "stock_price",
        "conversion_price",
        "stock_daily_return",
        "bond_daily_return",
        "previous_conversion_premium_rate",
        "conversion_premium_change",
        "redemption_trigger_ratio",
        "redemption_triggered",
        "redemption_announcement_date",
        "no_redemption_announcement_date",
        "issue_size",
        "remaining_size",
        "unconverted_ratio",
        "maturity_date",
        "bond_rating",
        "sw_l1",
        "sw_l2",
        "deducted_profit_2022",
        "deducted_profit_2023",
        "deducted_profit_2024",
        "deducted_profit_2025",
        "deducted_profit_h1_2025",
        "deducted_profit_h1_2026",
        "maturity_redemption_price",
        "notes",
    ]:
        if col not in renamed.columns:
            renamed[col] = pd.NA

    output_columns = [
        "enabled",
        "date",
        "bond_code",
        "bond_name",
        "price",
        "remaining_years",
        "conversion_premium_rate",
        "ytm",
        "stock_code",
        "stock_name",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "profit_growth_23_vs_22",
        "profit_growth_24_vs_23",
        "profit_growth_25_vs_24",
        "latest_half_profit_growth",
        "stock_price",
        "conversion_price",
        "stock_daily_return",
        "bond_daily_return",
        "previous_conversion_premium_rate",
        "conversion_premium_change",
        "redemption_trigger_ratio",
        "redemption_triggered",
        "redemption_announcement_date",
        "no_redemption_announcement_date",
        "issue_size",
        "remaining_size",
        "unconverted_ratio",
        "maturity_date",
        "bond_rating",
        "sw_l1",
        "sw_l2",
        "deducted_profit_2022",
        "deducted_profit_2023",
        "deducted_profit_2024",
        "deducted_profit_2025",
        "deducted_profit_h1_2025",
        "deducted_profit_h1_2026",
        "maturity_redemption_price",
        "notes",
    ]
    out = renamed[output_columns].copy()
    out["bond_code"] = out["bond_code"].astype(str).str.strip()
    out["bond_name"] = out["bond_name"].astype(str).str.strip()
    out = out[(out["bond_code"] != "") & (out["bond_code"].str.lower() != "nan")]
    out = out[pd.to_numeric(out["price"], errors="coerce").fillna(0) > 0]
    enabled = out["enabled"].astype(str).str.upper().str.strip()
    out = out[(enabled != "N") & (enabled != "否")]
    out["date"] = _clean_excel_date(out["date"])
    out["maturity_date"] = _clean_excel_date(out["maturity_date"])
    out["redemption_announcement_date"] = _clean_excel_date(out["redemption_announcement_date"])
    out["no_redemption_announcement_date"] = _clean_excel_date(out["no_redemption_announcement_date"])
    for col in [
        "price",
        "remaining_years",
        "conversion_premium_rate",
        "ytm",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "profit_growth_23_vs_22",
        "profit_growth_24_vs_23",
        "profit_growth_25_vs_24",
        "latest_half_profit_growth",
        "stock_price",
        "conversion_price",
        "stock_daily_return",
        "bond_daily_return",
        "previous_conversion_premium_rate",
        "conversion_premium_change",
        "redemption_trigger_ratio",
        "issue_size",
        "remaining_size",
        "unconverted_ratio",
        "deducted_profit_2022",
        "deducted_profit_2023",
        "deducted_profit_2024",
        "deducted_profit_2025",
        "deducted_profit_h1_2025",
        "deducted_profit_h1_2026",
        "maturity_redemption_price",
    ]:
        out[col] = _numeric_percent_safe(out[col])
    out["redemption_triggered"] = _truthy_series(out["redemption_triggered"])
    return out.reset_index(drop=True)


def _numeric_percent_safe(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip().str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    values = pd.to_numeric(cleaned, errors="coerce")
    percent_like = series.astype(str).str.contains("%", regex=False, na=False)
    values.loc[percent_like] = values.loc[percent_like] / 100
    return values


def _clean_excel_date(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    invalid = text.str.lower().isin({"", "nan", "nat", "none", "0", "00:00:00", "1900-01-00", "1900-01-01"})
    cleaned = series.mask(invalid, pd.NA)
    values = pd.to_datetime(cleaned, errors="coerce")
    values = values.mask(values.dt.year.fillna(0).astype(int) <= 1900)
    return values


def _truthy_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip().str.upper()
    return text.isin({"Y", "YES", "TRUE", "1", "是", "满足"})


def _parse_wind_wide_sheet(path: Path, sheet_name: str, volume_field: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if raw.shape[0] < 4:
        raise ValueError("not enough rows")
    required = ["开盘价", "收盘价", "最低价", "最高价", volume_field]
    field_row = {str(field).strip() for field in raw.iloc[2].dropna().tolist()}
    missing_from_header = [field for field in required if field not in field_row]
    if missing_from_header:
        raise ValueError(f"required fields not in row 3: {missing_from_header}")

    dates = pd.to_datetime(raw.iloc[3:, 0], errors="coerce")
    rows: list[dict[str, Any]] = []
    current_name: str | None = None

    for col_idx in range(raw.shape[1]):
        header_name = raw.iat[0, col_idx]
        if pd.notna(header_name):
            current_name = str(header_name).strip()

        code = raw.iat[1, col_idx]
        field = raw.iat[2, col_idx]
        if pd.isna(code) or pd.isna(field):
            continue

        values = pd.to_numeric(raw.iloc[3:, col_idx], errors="coerce")
        for row_idx, value in values.items():
            date_value = dates.loc[row_idx]
            if pd.isna(date_value):
                continue
            rows.append(
                {
                    "date": date_value,
                    "name": current_name or str(code).strip(),
                    "code": str(code).strip(),
                    "field": str(field).strip(),
                    "value": value,
                }
            )

    if not rows:
        raise ValueError("no usable market data")

    long_df = pd.DataFrame(rows)
    wide = (
        long_df.pivot_table(
            index=["date", "name", "code"],
            columns="field",
            values="value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    trading = filter_trading_rows(wide, volume_field)
    return _attach_date_aligned_auxiliary_fields(wide, trading, required)


def _attach_date_aligned_auxiliary_fields(
    wide: pd.DataFrame,
    trading: pd.DataFrame,
    required: list[str],
) -> pd.DataFrame:
    if trading.empty:
        return trading
    valid_primary = pd.Series(True, index=wide.index)
    for field in required:
        valid_primary &= pd.to_numeric(wide[field], errors="coerce").fillna(0).gt(0)
    auxiliary = wide[~valid_primary].copy()
    identifiers = {"date", "name", "code", *required}
    for field in (column for column in wide.columns if column not in identifiers):
        if field not in trading.columns or not trading[field].isna().all():
            continue
        candidates = auxiliary[["date", "code", field]].dropna(subset=[field])
        if candidates.empty or candidates["code"].nunique() != 1:
            continue
        date_values = candidates.drop_duplicates("date", keep="last").set_index("date")[field]
        trading[field] = trading["date"].map(date_values)
    return trading


def filter_trading_rows(df: pd.DataFrame, volume_field: str) -> pd.DataFrame:
    required = ["开盘价", "收盘价", "最低价", "最高价", volume_field]
    missing = [field for field in required if field not in df.columns]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    valid = pd.Series(True, index=df.index)
    for field in required:
        valid = valid & pd.to_numeric(df[field], errors="coerce").fillna(0).gt(0)

    filtered = df[valid].copy().sort_values(["code", "date"]).reset_index(drop=True)
    filtered.attrs["invalid_trading_rows"] = int((~valid).sum())
    return filtered
