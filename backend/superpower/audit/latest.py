from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from superpower.skills.convertible_bond_ranking.handler import rank_convertible_bonds, split_candidate_qualification
from superpower.skills.etf_rotation_strategy.handler import latest_etf_signals
from superpower.skills.technical_indicators.handler import add_indicators
from superpower.skills.tl_timing_strategy.handler import tl_state
from superpower.tools.excel_reader import (
    filter_etf_market_to_universe,
    parse_convertible_bond_excel,
    parse_enabled_etf_universe,
    parse_positions_from_etf_workbook,
    parse_wind_wide_excel,
)
from superpower.tools.report_date import report_date_text


FLOAT_TOLERANCE = 1e-8


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the latest AI research daily report.")
    parser.add_argument("--root-dir", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--etf-file", type=Path, required=True)
    parser.add_argument("--tl-file", type=Path, required=True)
    parser.add_argument("--cb-file", type=Path, default=None)
    args = parser.parse_args()

    result = audit_latest(args.root_dir, args.etf_file, args.tl_file, args.cb_file)
    print(f"audit_status={result['status']}")
    for check in result["checks"]:
        print(f"{check['status']}: {check['name']} - {check['detail']}")
    if result["status"] != "PASS":
        raise SystemExit(1)


def audit_latest(root_dir: Path, etf_file: Path, tl_file: Path, cb_file: Path | None = None) -> dict[str, Any]:
    output_dir = root_dir / "outputs"
    latest_dir = output_dir / "latest"
    dashboard_path = latest_dir / "dashboard.json"
    params_path = root_dir / "configs" / "strategy_params.json"
    positions_path = root_dir / "configs" / "positions.csv"

    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    params = json.loads(params_path.read_text(encoding="utf-8"))
    cb_file = cb_file or _configured_cb_file(root_dir)

    etf_universe = parse_enabled_etf_universe(etf_file)
    etf_raw = filter_etf_market_to_universe(parse_wind_wide_excel(etf_file, "成交量（万股）"), etf_universe)
    tl_raw = parse_wind_wide_excel(tl_file, "成交量")
    cb_data = parse_convertible_bond_excel(cb_file)
    positions = parse_positions_from_etf_workbook(etf_file)
    if positions.empty and positions_path.exists():
        positions = pd.read_csv(positions_path)

    etf_indicators = pd.concat(
        [add_indicators(group, "成交量（万股）") for _, group in etf_raw.groupby(["name", "code"])],
        ignore_index=True,
    )
    tl_indicators = add_indicators(tl_raw, "成交量").sort_values("date").reset_index(drop=True)
    etf_all, etf_buys, etf_sells, etf_watchlist, etf_details = latest_etf_signals(etf_indicators, positions, params)
    tl_today, tl_recent = tl_state(tl_indicators, params)
    cb_ranked = rank_convertible_bonds(cb_data, params) if not cb_data.empty else pd.DataFrame()
    cb_qualified, _, _ = split_candidate_qualification(cb_ranked) if not cb_ranked.empty else (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    report_date = report_date_text(etf_indicators, tl_indicators, cb_ranked)
    report_path = _resolve_report_path(root_dir, dashboard.get("reportPath", ""))
    checks = [
        check_equal("latest report date", report_date, dashboard["reportDate"]),
        check_min("ETF source symbol count", etf_raw[["name", "code"]].drop_duplicates().shape[0], 10),
        check_min("ETF source trading days", etf_raw["date"].nunique(), 60),
        check_min("TL source trading rows", len(tl_raw), 60),
        check_equal("ETF buy count", len(etf_buys), dashboard_summary_value(dashboard, "ETF建仓候选数量")),
        check_equal("ETF watchlist count", len(etf_watchlist), dashboard_summary_value(dashboard, "ETF关注池数量")),
        check_equal("ETF sell count", len(etf_sells), dashboard_summary_value(dashboard, "ETF平仓提示数量")),
        check_equal("CB top10 count", min(len(cb_qualified), 10), dashboard_summary_value(dashboard, "可转债Top10数量")),
        check_equal("TL state", str(tl_today.iloc[0]["state"]), dashboard_summary_value(dashboard, "TL今日状态")),
        check_float("TL close", tl_today.iloc[0]["收盘价"], dashboard_summary_value(dashboard, "TL收盘价"), 1e-4),
        check_float("TL daily MACD histogram", tl_today.iloc[0]["macd_hist"], dashboard_summary_value(dashboard, "TL日线MACD柱"), 1e-6),
        check_float("TL daily KDJ J", tl_today.iloc[0]["kdj_j"], dashboard_summary_value(dashboard, "TL日线KDJ J"), 1e-4),
        check_records("ETF buy records", etf_buys, pd.DataFrame(dashboard["etfBuyCandidates"]), ["code", "signal_reason", "score"]),
        check_records("ETF watchlist records", etf_watchlist, pd.DataFrame(dashboard["etfWatchlist"]), ["code", "watch_type", "missing_condition", "score"]),
        check_records("ETF sell records", etf_sells, pd.DataFrame(dashboard["etfSellAlerts"]), ["code", "signal_reason", "score"]),
        check_dashboard_is_json_clean(dashboard),
        check_report_workbook(report_path),
    ]

    status = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
    payload = {
        "status": status,
        "checks": [check.__dict__ for check in checks],
        "source": {
            "etfFile": str(etf_file),
            "tlFile": str(tl_file),
            "cbFile": str(cb_file) if cb_file else "",
            "reportPath": str(report_path),
            "reportDate": report_date,
        },
    }
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _configured_cb_file(root_dir: Path) -> Path | None:
    sources_path = root_dir / "configs" / "data_sources.json"
    if not sources_path.exists():
        return None
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    value = sources.get("convertible_bond_file")
    return _resolve_report_path(root_dir, value) if value else None


def _resolve_report_path(root_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else root_dir / path


def dashboard_summary_value(dashboard: dict[str, Any], item: str) -> Any:
    for row in dashboard["summary"]:
        if row["item"] == item:
            return row["value"]
    raise KeyError(item)


def check_equal(name: str, actual: Any, expected: Any) -> Check:
    status = "PASS" if actual == expected else "FAIL"
    return Check(name, status, f"actual={actual}, expected={expected}")


def check_min(name: str, actual: Any, minimum: Any) -> Check:
    status = "PASS" if actual >= minimum else "FAIL"
    return Check(name, status, f"actual={actual}, minimum={minimum}")


def check_float(name: str, actual: Any, expected: Any, tolerance: float = FLOAT_TOLERANCE) -> Check:
    actual_float = float(actual)
    expected_float = float(expected)
    status = "PASS" if abs(actual_float - expected_float) <= tolerance else "FAIL"
    return Check(name, status, f"actual={actual_float:.12g}, expected={expected_float:.12g}, tolerance={tolerance}")


def check_records(name: str, actual: pd.DataFrame, expected: pd.DataFrame, columns: list[str]) -> Check:
    if actual.empty and expected.empty:
        return Check(name, "PASS", "both empty")
    if len(actual) != len(expected):
        return Check(name, "FAIL", f"row count actual={len(actual)}, expected={len(expected)}")
    actual_view = actual[columns].sort_values(columns[0]).reset_index(drop=True)
    expected_view = expected[columns].sort_values(columns[0]).reset_index(drop=True)
    mismatches: list[str] = []
    for idx in range(len(actual_view)):
        for column in columns:
            actual_value = actual_view.at[idx, column]
            expected_value = expected_view.at[idx, column]
            if isinstance(actual_value, (float, np.floating)) or isinstance(expected_value, (float, np.floating)):
                if abs(float(actual_value) - float(expected_value)) > 1e-6:
                    mismatches.append(f"row={idx} column={column} actual={actual_value} expected={expected_value}")
            elif str(actual_value) != str(expected_value):
                mismatches.append(f"row={idx} column={column} actual={actual_value} expected={expected_value}")
    status = "PASS" if not mismatches else "FAIL"
    detail = "matched" if not mismatches else "; ".join(mismatches[:5])
    return Check(name, status, detail)


def check_dashboard_is_json_clean(dashboard: dict[str, Any]) -> Check:
    issues: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                walk(child, f"{path}[{idx}]")
        elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            issues.append(path)

    walk(dashboard, "dashboard")
    status = "PASS" if not issues else "FAIL"
    return Check("dashboard JSON finite values", status, "no NaN/Inf" if not issues else ", ".join(issues[:5]))


def check_report_workbook(report_path: Path) -> Check:
    expected = {
        "今日总览",
        "AI解释",
        "ETF建仓候选",
        "ETF关注池",
        "ETF详情近8日",
        "ETF平仓提示",
        "ETF全量信号",
        "TL今日状态",
        "TL近期状态",
        "可转债Top10",
        "历史诊断摘要",
        "AI研究委员会",
        "组合风控",
        "数据校验",
        "源文件Manifest",
        "Agent审计",
    }
    if not report_path.exists():
        return Check("report workbook", "FAIL", f"missing workbook: {report_path}")
    sheet_names = set(pd.ExcelFile(report_path).sheet_names)
    missing = sorted(expected - sheet_names)
    status = "PASS" if not missing else "FAIL"
    return Check("report workbook", status, "required sheets present" if not missing else f"missing={missing}")


if __name__ == "__main__":
    main()
