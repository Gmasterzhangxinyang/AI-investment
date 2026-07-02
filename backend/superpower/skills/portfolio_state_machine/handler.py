from __future__ import annotations

import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.tools.excel_reader import parse_positions_from_etf_workbook


POSITION_COLUMNS = [
    "asset_type",
    "code",
    "name",
    "status",
    "entry_date",
    "entry_price",
    "position_size",
    "notes",
]


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        path = context.get("positions_file")
        etf_file = context.maybe("etf_file")

        positions = pd.DataFrame(columns=POSITION_COLUMNS)
        if etf_file is not None:
            excel_positions = parse_positions_from_etf_workbook(etf_file)
            if not excel_positions.empty:
                positions = excel_positions

        if positions.empty and path.exists():
            positions = pd.read_csv(path)

        if not positions.empty:
            positions["asset_type"] = positions["asset_type"].astype(str).str.upper().str.strip()
            positions["code"] = positions["code"].astype(str).str.strip()
            positions["status"] = positions["status"].astype(str).str.lower().str.strip()

        context.put("positions", positions)
        return {
            "position_rows": len(positions),
            "holding_rows": int((positions.get("status", pd.Series(dtype=str)) == "holding").sum()) if not positions.empty else 0,
        }
