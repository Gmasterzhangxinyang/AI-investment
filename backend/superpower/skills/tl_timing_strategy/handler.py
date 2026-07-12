from __future__ import annotations

import numpy as np
import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.skills.technical_indicators.handler import add_indicators

from .fund_flow import attach_fund_flow_diagnostics


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        tl_history = tl_state_history(context.get("tl_indicators"), context.get("strategy_params"))
        tl_today = tl_history.tail(1).copy()
        tl_recent = tl_history.tail(20).copy()
        context.put("tl_today", tl_today)
        context.put("tl_recent", tl_recent)
        context.put("tl_signal_history", tl_history)
        return {
            "tl_state": str(tl_today.iloc[0]["display_status"]) if not tl_today.empty else "数据不足，无法判断",
            "recent_rows": len(tl_recent),
        }


def tl_state(tl: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = tl_state_history(tl, params)
    return out.tail(1).copy(), out.tail(20).copy()


def tl_state_history(tl: pd.DataFrame, params: dict) -> pd.DataFrame:
    tl_params = params.get("tl", {})
    if tl.empty:
        return attach_fund_flow_diagnostics(_empty_tl_state(), tl_params)
    out = tl.sort_values("date").reset_index(drop=True).copy()
    if len(out) < 60:
        return attach_fund_flow_diagnostics(_insufficient_tl_history(out), tl_params)
    weekly_map = _weekly_state_as_of_each_day(out, params)
    out = out.merge(weekly_map, on="date", how="left")
    daily_conditions = [
        _macd_condition(current, previous, params["tl"].get("macd_hist_min_delta", 0.0))
        for current, previous in zip(out["macd_hist"], out["macd_hist"].shift(1))
    ]
    out["daily_macd_condition"] = [condition for condition, _ in daily_conditions]
    out["daily_macd_reason"] = [reason for _, reason in daily_conditions]
    daily_low = out["kdj_j"].shift(1).rolling(params["tl"]["daily_kdj_lookback"], min_periods=1).min()
    out["daily_kdj_low_window"] = daily_low
    out["daily_attention"] = out["daily_macd_condition"] == "attention"
    out["daily_no_trade"] = out["daily_macd_condition"] == "no_trade"
    out["daily_kdj_rebound"] = (daily_low < params["tl"]["daily_j_low_threshold"]) & (out["kdj_j"] > daily_low)
    out["daily_kdj_threshold_check"] = [
        _kdj_threshold_text(value, params["tl"]["daily_j_low_threshold"], f"日线近{params['tl']['daily_kdj_lookback']}日", bool(matched))
        for value, matched in zip(daily_low, out["daily_kdj_rebound"])
    ]

    raw_buy_signal = (out["attention_week"].fillna(False) & out["weekly_kdj_rebound"].fillna(False)) | (
        out["daily_attention"].fillna(False) & out["daily_kdj_rebound"].fillna(False)
    )
    weekly_no_trade = out["no_trade_week"].fillna(False)
    if params["tl"].get("weekly_no_trade_hard_veto", True):
        out["buy_signal"] = raw_buy_signal & ~weekly_no_trade
    else:
        out["buy_signal"] = raw_buy_signal
    out["attention_signal"] = out["attention_week"].fillna(False) | out["daily_attention"].fillna(False)
    out["no_trade_signal"] = weekly_no_trade & ~out["buy_signal"]
    out["status"] = np.where(
        out["buy_signal"],
        "entry_candidate",
        np.where(out["no_trade_signal"], "no_trade", np.where(out["attention_signal"], "attention", "neutral")),
    )
    out["display_status"] = out["status"].map(_display_status)
    out["state"] = out["display_status"]
    out["action"] = out["display_status"]
    out["reason"] = out["weekly_macd_reason"].fillna("MACD历史不足") + "；" + out["daily_kdj_threshold_check"].fillna("KDJ历史不足")
    out["rule_hits"] = [
        _tl_rule_hits(row)
        for _, row in out.iterrows()
    ]
    out["risk_notes"] = TL_DIAGNOSTIC_NOTE
    out["data_quality"] = np.where(out["macd_hist"].notna() & out["kdj_j"].notna(), "OK", "WARN")
    out["confidence"] = np.where(out["data_quality"] == "OK", "medium", "low")
    out = attach_fund_flow_diagnostics(out, tl_params)
    out["metrics"] = [
        {
            "close": _safe_float(row.get("收盘价")),
            "daily_macd_hist": _safe_float(row.get("macd_hist")),
            "daily_kdj_j": _safe_float(row.get("kdj_j")),
            "weekly_macd_hist": _safe_float(row.get("week_macd_hist")),
            "weekly_kdj_j": _safe_float(row.get("week_kdj_j")),
            "weekly_kdj_low_window": _safe_float(row.get("weekly_kdj_low_window")),
            "daily_kdj_low_window": _safe_float(row.get("daily_kdj_low_window")),
            "fund_share_change_daily": _safe_float(row.get("fund_share_change_daily")),
            "fund_share_5d_sum": _safe_float(row.get("fund_share_5d_sum")),
            "fund_flow_state": row.get("fund_flow_state"),
            "fund_flow_relation": row.get("fund_flow_relation"),
        }
        for _, row in out.iterrows()
    ]
    return out


TL_DIAGNOSTIC_NOTE = "TL 当前仅做状态诊断，不模拟期货连续合约、换月、杠杆、保证金、滑点和完整平仓收益。"


def _weekly_state_as_of_each_day(tl: pd.DataFrame, params: dict) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for idx in range(len(tl)):
        history = tl.iloc[: idx + 1]
        weekly = (
            history.set_index("date")
            .resample("W-FRI")
            .agg({"开盘价": "first", "最高价": "max", "最低价": "min", "收盘价": "last", "成交量": "sum"})
            .dropna()
            .reset_index()
        )
        weekly["name"] = "TL"
        weekly["code"] = "TL.CFE"
        weekly = add_indicators(weekly, "成交量")

        current = weekly.iloc[-1]
        previous = weekly.iloc[-2] if len(weekly) >= 2 else None
        previous_hist = previous["macd_hist"] if previous is not None else np.nan
        current_hist = current["macd_hist"]

        weekly_macd_condition, weekly_macd_reason = _macd_condition(
            current_hist,
            previous_hist,
            params["tl"].get("macd_hist_min_delta", 0.0),
        )
        attention_week = weekly_macd_condition == "attention"
        no_trade_week = weekly_macd_condition == "no_trade"

        lookback = params["tl"]["weekly_kdj_lookback"]
        previous_j = weekly["kdj_j"].iloc[:-1].tail(lookback)
        weekly_low = previous_j.min() if not previous_j.empty else np.nan
        weekly_kdj_rebound = bool(
            pd.notna(weekly_low)
            and weekly_low < params["tl"]["weekly_j_low_threshold"]
            and current["kdj_j"] > weekly_low
        )
        weekly_kdj_threshold_check = _kdj_threshold_text(
            weekly_low,
            params["tl"]["weekly_j_low_threshold"],
            f"周线近{lookback}周",
            weekly_kdj_rebound,
        )

        rows.append(
            {
                "date": tl.iloc[idx]["date"],
                "week_macd_hist": current_hist,
                "week_kdj_j": current["kdj_j"],
                "weekly_macd_condition": weekly_macd_condition,
                "weekly_macd_reason": weekly_macd_reason,
                "attention_week": attention_week,
                "no_trade_week": no_trade_week,
                "weekly_kdj_low_window": weekly_low,
                "weekly_kdj_rebound": weekly_kdj_rebound,
                "weekly_kdj_threshold_check": weekly_kdj_threshold_check,
            }
        )
    return pd.DataFrame(rows)


def _macd_condition(current_hist: float, previous_hist: float, min_delta: float) -> tuple[str, str]:
    if pd.isna(current_hist) or pd.isna(previous_hist):
        return "neutral", "MACD历史不足"

    delta = current_hist - previous_hist
    if previous_hist > 0 and current_hist < 0:
        return "no_trade", "红转绿阶段"

    if delta > min_delta:
        if previous_hist < 0 and current_hist < 0:
            return "attention", "绿柱T日短于T-1日"
        if previous_hist < 0 <= current_hist:
            return "attention", "绿转红阶段"
        if previous_hist >= 0 and current_hist > 0:
            return "attention", "红柱T日长于T-1日"
        return "attention", "MACD柱改善"

    if delta < -min_delta:
        if previous_hist > 0 and current_hist > 0:
            return "no_trade", "红柱T日短于T-1日"
        if previous_hist <= 0 and current_hist < 0:
            return "no_trade", "绿柱T日长于T-1日"
        return "no_trade", "MACD柱走弱"

    return "neutral", "MACD柱变化不足"


def _kdj_threshold_text(low_value: float, threshold: float, label: str, condition_met: bool) -> str:
    if pd.isna(low_value):
        return f"{label}J值历史不足，KDJ低位条件不满足"
    status = "低于" if low_value < threshold else "未低于"
    result = "满足" if condition_met else "不满足"
    return f"{label}J值最低值：{low_value:.4f}，{status}{threshold:g}，KDJ低位反弹条件{result}"


def _display_status(status: str) -> str:
    return {
        "no_trade": "不做交易",
        "attention": "关注交易",
        "entry_candidate": "模型触发建仓候选",
        "neutral": "中性",
        "unavailable": "数据不足，无法判断",
    }.get(status, "中性")


def _tl_rule_hits(row: pd.Series) -> str:
    hits = [
        f"周线MACD：{row.get('weekly_macd_reason', '未知')}",
        f"周线KDJ：{row.get('weekly_kdj_threshold_check', '未知')}",
        f"日线MACD：{row.get('daily_macd_reason', '未知')}",
        f"日线KDJ：{row.get('daily_kdj_threshold_check', '未知')}",
    ]
    if bool(row.get("buy_signal")):
        hits.append("满足TL建仓候选规则")
    elif bool(row.get("no_trade_signal")):
        hits.append("满足TL不做交易规则")
    elif bool(row.get("attention_signal")):
        hits.append("满足TL关注规则")
    return "；".join(hits)


def _safe_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _empty_tl_state() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.NaT,
                "code": "TL.CFE",
                "name": "30年国债期货TL",
                "status": "unavailable",
                "display_status": "数据不足，无法判断",
                "state": "数据不足，无法判断",
                "action": "数据不足，无法判断",
                "reason": "TL有效行情不足",
                "metrics": {},
                "rule_hits": "",
                "risk_notes": TL_DIAGNOSTIC_NOTE,
                "confidence": "low",
                "data_quality": "ERROR",
                "buy_signal": False,
                "attention_signal": False,
                "no_trade_signal": False,
                "收盘价": np.nan,
                "macd_hist": np.nan,
                "kdj_j": np.nan,
                "week_macd_hist": np.nan,
                "week_kdj_j": np.nan,
                "weekly_macd_reason": "TL行情不足",
                "weekly_kdj_threshold_check": "TL行情不足，KDJ低位条件不满足",
                "daily_macd_reason": "TL行情不足",
                "daily_kdj_threshold_check": "TL行情不足，KDJ低位条件不满足",
                "weekly_kdj_low_window": np.nan,
                "daily_kdj_low_window": np.nan,
                "份额变化（亿份）": np.nan,
            }
        ]
    )


def _insufficient_tl_history(tl: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    history_rows = len(tl)
    reason = f"TL有效历史仅{history_rows}行，少于60行，不能形成完整日线/周线状态诊断"
    for _, row in tl.iterrows():
        rows.append(
            {
                "date": row.get("date", pd.NaT),
                "code": row.get("code", "TL.CFE"),
                "name": row.get("name", "30年国债期货TL"),
                "status": "unavailable",
                "display_status": "数据不足，无法判断",
                "state": "数据不足，无法判断",
                "action": "数据不足，无法判断",
                "reason": reason,
                "metrics": {
                    "close": _safe_float(row.get("收盘价")),
                    "daily_macd_hist": _safe_float(row.get("macd_hist")),
                    "daily_kdj_j": _safe_float(row.get("kdj_j")),
                    "weekly_macd_hist": None,
                    "weekly_kdj_j": None,
                    "weekly_kdj_low_window": None,
                    "daily_kdj_low_window": None,
                },
                "rule_hits": "TL有效历史不足，不能触发建仓候选规则",
                "risk_notes": TL_DIAGNOSTIC_NOTE,
                "confidence": "low",
                "data_quality": "ERROR",
                "buy_signal": False,
                "attention_signal": False,
                "no_trade_signal": False,
                "收盘价": row.get("收盘价", np.nan),
                "macd_hist": row.get("macd_hist", np.nan),
                "kdj_j": row.get("kdj_j", np.nan),
                "week_macd_hist": np.nan,
                "week_kdj_j": np.nan,
                "weekly_macd_reason": "TL有效历史不足",
                "weekly_kdj_threshold_check": "TL有效历史不足，KDJ低位条件不满足",
                "daily_macd_reason": "TL有效历史不足",
                "daily_kdj_threshold_check": "TL有效历史不足，KDJ低位条件不满足",
                "weekly_kdj_low_window": np.nan,
                "daily_kdj_low_window": np.nan,
                "份额变化（亿份）": row.get("份额变化（亿份）", np.nan),
            }
        )
    return pd.DataFrame(rows)
