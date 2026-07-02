from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "templates" / "build"
ETF_FILE = Path("/Users/bobby/Downloads/ETF数据快照-20250101-20260617.xlsx")
TL_FILE = Path("/Users/bobby/Downloads/TL-快照1.xlsx")


def matrix_from_excel(path: Path) -> list[list[object | None]]:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    raw = raw.where(pd.notna(raw), None)
    rows: list[list[object | None]] = []
    for row in raw.itertuples(index=False, name=None):
        values: list[object | None] = []
        for value in row:
            if pd.isna(value):
                values.append(None)
            elif isinstance(value, pd.Timestamp):
                values.append(value.strftime("%Y-%m-%d"))
            else:
                values.append(value)
        rows.append(values)
    return rows


def etf_universe(matrix: list[list[object | None]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    current_name = ""
    row_name, row_code, row_field = matrix[0], matrix[1], matrix[2]
    for idx, value in enumerate(row_name):
        if value:
            current_name = str(value).strip()
        code = row_code[idx] if idx < len(row_code) else None
        field = row_field[idx] if idx < len(row_field) else None
        if code and field == "开盘价":
            code_text = str(code).strip()
            if code_text not in seen:
                seen.add(code_text)
                output.append({"enabled": "Y", "asset_type": "ETF", "code": code_text, "name": current_name})
    return output


def main() -> None:
    etf_matrix = matrix_from_excel(ETF_FILE)
    tl_matrix = matrix_from_excel(TL_FILE)
    payload = {
        "source_files": {
            "etf": str(ETF_FILE),
            "tl": str(TL_FILE),
        },
        "etf_matrix": etf_matrix,
        "tl_matrix": tl_matrix,
        "etf_universe": etf_universe(etf_matrix),
    }
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "seed_data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
