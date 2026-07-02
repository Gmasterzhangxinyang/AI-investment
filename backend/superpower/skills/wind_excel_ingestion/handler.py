from __future__ import annotations

from pathlib import Path

import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.tools.excel_reader import (
    filter_etf_market_to_universe,
    parse_convertible_bond_excel,
    parse_enabled_etf_universe,
    parse_wind_wide_excel,
)


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        etf_file = context.get("etf_file")
        tl_file = context.get("tl_file")
        cb_file = context.maybe("cb_file")

        warnings: list[dict[str, object]] = []
        etf_raw, etf_universe = _load_etf(etf_file, warnings)
        tl_raw = _load_market_file("TL", tl_file, "成交量", warnings)
        cb_data = parse_convertible_bond_excel(cb_file)

        context.put("etf_market_raw", etf_raw)
        context.put("tl_market_raw", tl_raw)
        context.put("cb_data", cb_data)
        context.put("etf_template_universe", etf_universe)
        context.put("data_ingestion_warnings", pd.DataFrame(warnings))

        return {
            "etf_rows": len(etf_raw),
            "etf_symbols": etf_raw[["name", "code"]].drop_duplicates().shape[0] if not etf_raw.empty else 0,
            "tl_rows": len(tl_raw),
            "cb_rows": len(cb_data),
            "warning_count": len(warnings),
        }


def _load_etf(path: Path, warnings: list[dict[str, object]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not _path_exists(path):
        warnings.append(_warning("ETF", path, "源文件不存在，ETF模块将标记为不可用"))
        return _empty_market("成交量（万股）"), pd.DataFrame(columns=["code", "name"])
    try:
        market = parse_wind_wide_excel(path, "成交量（万股）")
        universe = parse_enabled_etf_universe(path)
        return filter_etf_market_to_universe(market, universe), universe
    except Exception as exc:
        warnings.append(_warning("ETF", path, f"解析失败：{exc}"))
        return _empty_market("成交量（万股）"), pd.DataFrame(columns=["code", "name"])


def _load_market_file(label: str, path: Path, volume_field: str, warnings: list[dict[str, object]]) -> pd.DataFrame:
    if not _path_exists(path):
        warnings.append(_warning(label, path, "源文件不存在，该模块将标记为不可用"))
        return _empty_market(volume_field)
    try:
        return parse_wind_wide_excel(path, volume_field)
    except Exception as exc:
        warnings.append(_warning(label, path, f"解析失败：{exc}"))
        return _empty_market(volume_field)


def _path_exists(path: Path | str | None) -> bool:
    return path is not None and Path(path).expanduser().exists()


def _warning(label: str, path: Path | str | None, message: str) -> dict[str, object]:
    return {"module": label, "path": str(path or ""), "status": "ERROR", "message": message}


def _empty_market(volume_field: str) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "date",
            "name",
            "code",
            "开盘价",
            "收盘价",
            "最低价",
            "最高价",
            volume_field,
            "成交额（亿元）",
        ]
    )
