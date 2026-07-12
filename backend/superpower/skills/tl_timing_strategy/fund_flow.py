from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_FUND_FLOW = {
    "light_threshold": 0.03,
    "large_threshold": 0.05,
    "extreme_threshold": 0.07,
    "review_threshold": 0.20,
    "rolling_days": 5,
    "rolling_direction_threshold": 0.08,
    "minimum_valid_days": 3,
    "zero_stale_days": 3,
}

FUND_FLOW_COLUMNS = (
    "fund_share_change_daily",
    "fund_share_daily_level",
    "fund_share_5d_sum",
    "fund_share_5d_valid_days",
    "fund_share_5d_inflow_days",
    "fund_share_5d_outflow_days",
    "fund_flow_state",
    "fund_flow_relation",
    "fund_flow_note",
    "fund_flow_data_quality",
)


def attach_fund_flow_diagnostics(
    frame: pd.DataFrame,
    tl_params: Mapping[str, Any],
) -> pd.DataFrame:
    out = frame.copy()
    settings = {**DEFAULT_FUND_FLOW, **dict(tl_params.get("fund_flow", {}))}
    if "份额变化（亿份）" not in out.columns:
        return _attach_unavailable(out)

    raw = pd.to_numeric(out["份额变化（亿份）"], errors="coerce")
    review = raw.abs() > float(settings["review_threshold"])
    clean = raw.mask(review)
    window = int(settings["rolling_days"])
    valid = clean.notna().astype(int).rolling(window, min_periods=1).sum().astype(int)
    rolling_sum = clean.rolling(window, min_periods=1).sum()
    inflow_days = clean.gt(0).astype(int).rolling(window, min_periods=1).sum().astype(int)
    outflow_days = clean.lt(0).astype(int).rolling(window, min_periods=1).sum().astype(int)
    zero_runs = _consecutive_zero_runs(raw)

    out["fund_share_change_daily"] = raw
    out["fund_share_daily_level"] = [
        _daily_level(value, is_review, settings)
        for value, is_review in zip(raw, review, strict=False)
    ]
    out["fund_share_5d_sum"] = rolling_sum.round(6)
    out["fund_share_5d_valid_days"] = valid
    out["fund_share_5d_inflow_days"] = inflow_days
    out["fund_share_5d_outflow_days"] = outflow_days
    out["fund_flow_state"] = [
        _flow_state(total, count, settings)
        for total, count in zip(rolling_sum, valid, strict=False)
    ]
    out["fund_flow_relation"] = [
        _flow_relation(str(status), str(flow_state))
        for status, flow_state in zip(
            out.get("status", pd.Series("neutral", index=out.index)),
            out["fund_flow_state"],
            strict=False,
        )
    ]
    out["fund_flow_data_quality"] = [
        _data_quality(value, is_review, zero_run, settings)
        for value, is_review, zero_run in zip(raw, review, zero_runs, strict=False)
    ]
    out["fund_flow_note"] = [
        _fund_flow_note(row, zero_run, settings)
        for (_, row), zero_run in zip(out.iterrows(), zero_runs, strict=False)
    ]
    return out


def _daily_level(
    value: float,
    review: bool,
    settings: Mapping[str, Any],
) -> str:
    if pd.isna(value):
        return "数据不足"
    if review:
        return "待核验"
    magnitude = abs(float(value))
    direction = "申购" if value > 0 else "赎回" if value < 0 else ""
    if magnitude < float(settings["light_threshold"]):
        return "正常波动"
    if magnitude < float(settings["large_threshold"]):
        return f"轻度{direction}"
    if magnitude < float(settings["extreme_threshold"]):
        return f"明显{direction}"
    return f"极端{direction}"


def _flow_state(
    total: float,
    valid_days: int,
    settings: Mapping[str, Any],
) -> str:
    if valid_days < int(settings["minimum_valid_days"]) or pd.isna(total):
        return "数据不足"
    threshold = float(settings["rolling_direction_threshold"])
    if total >= threshold:
        return "持续流入"
    if total <= -threshold:
        return "持续流出"
    return "方向不明显"


def _flow_relation(status: str, flow_state: str) -> str:
    improving = status in {"entry_candidate", "attention"}
    weakening = status == "no_trade"
    if improving and flow_state == "持续流入":
        return "同向改善"
    if improving and flow_state == "持续流出":
        return "技术资金背离"
    if weakening and flow_state == "持续流出":
        return "共同走弱"
    if weakening and flow_state == "持续流入":
        return "逆势流入"
    return "中性观察"


def _data_quality(
    value: float,
    review: bool,
    zero_run: int,
    settings: Mapping[str, Any],
) -> str:
    if pd.isna(value):
        return "UNAVAILABLE"
    if review or zero_run >= int(settings["zero_stale_days"]):
        return "WARN"
    return "OK"


def _fund_flow_note(
    row: pd.Series,
    zero_run: int,
    settings: Mapping[str, Any],
) -> str:
    if row["fund_flow_data_quality"] == "UNAVAILABLE":
        return "30年国债ETF份额变化数据不足，不影响原TL状态"
    if row["fund_share_daily_level"] == "待核验":
        return (
            f"当日份额变化{float(row['fund_share_change_daily']):+.4f}亿份为统计极端值，"
            "保留原值但不计入5日方向；不影响原TL状态"
        )
    relation_notes = {
        "同向改善": "同向改善：TL技术状态与ETF资金持续流入相互确认",
        "技术资金背离": "技术资金背离：TL技术转强但ETF资金持续流出，关注假转强或拐点",
        "共同走弱": "共同走弱：TL技术状态与ETF资金持续流出方向一致",
        "逆势流入": "逆势流入：TL技术偏弱但ETF资金持续流入，仅观察潜在转向",
        "中性观察": f"中性观察：近5日资金{row['fund_flow_state']}，不作方向升级",
    }
    note = relation_notes[str(row["fund_flow_relation"])]
    if zero_run >= int(settings["zero_stale_days"]):
        note += f"；份额变化连续{zero_run}日为0，请确认Wind数据是否更新"
    return note + "；不影响原TL状态"


def _consecutive_zero_runs(values: pd.Series) -> list[int]:
    runs: list[int] = []
    current = 0
    for value in values:
        current = current + 1 if pd.notna(value) and float(value) == 0 else 0
        runs.append(current)
    return runs


def _attach_unavailable(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["fund_share_change_daily"] = np.nan
    out["fund_share_daily_level"] = "数据不足"
    out["fund_share_5d_sum"] = np.nan
    out["fund_share_5d_valid_days"] = 0
    out["fund_share_5d_inflow_days"] = 0
    out["fund_share_5d_outflow_days"] = 0
    out["fund_flow_state"] = "数据不足"
    out["fund_flow_relation"] = "中性观察"
    out["fund_flow_note"] = "30年国债ETF份额变化数据不足，不影响原TL状态"
    out["fund_flow_data_quality"] = "UNAVAILABLE"
    return out
