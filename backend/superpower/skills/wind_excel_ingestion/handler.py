from __future__ import annotations

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

        etf_raw = parse_wind_wide_excel(etf_file, "成交量（万股）")
        etf_universe = parse_enabled_etf_universe(etf_file)
        etf_raw = filter_etf_market_to_universe(etf_raw, etf_universe)
        tl_raw = parse_wind_wide_excel(tl_file, "成交量")
        cb_data = parse_convertible_bond_excel(cb_file)

        context.put("etf_market_raw", etf_raw)
        context.put("tl_market_raw", tl_raw)
        context.put("cb_data", cb_data)
        context.put("etf_template_universe", etf_universe)

        return {
            "etf_rows": len(etf_raw),
            "etf_symbols": etf_raw[["name", "code"]].drop_duplicates().shape[0],
            "tl_rows": len(tl_raw),
            "cb_rows": len(cb_data),
        }
