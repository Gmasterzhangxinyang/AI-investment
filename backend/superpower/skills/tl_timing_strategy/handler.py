from __future__ import annotations

import numpy as np
import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.skills.technical_indicators.handler import add_indicators


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        tl_history = tl_state_history(context.get("tl_indicators"), context.get("strategy_params"))
        tl_today = tl_history.tail(1).copy()
        tl_recent = tl_history.tail(20).copy()
        context.put("tl_today", tl_today)
        context.put("tl_recent", tl_recent)
        context.put("tl_signal_history", tl_history)
        return {
            "tl_state": str(tl_today.iloc[0]["state"]),
            "recent_rows": len(tl_recent),
        }


def tl_state(tl: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = tl_state_history(tl, params)
    return out.tail(1).copy(), out.tail(20).copy()


def tl_state_history(tl: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = tl.sort_values("date").reset_index(drop=True).copy()
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
    out["state"] = np.where(
        out["buy_signal"],
        "建议建仓",
        np.where(out["no_trade_signal"], "不做交易", np.where(out["attention_signal"], "关注交易", "中性")),
    )
    return out


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
