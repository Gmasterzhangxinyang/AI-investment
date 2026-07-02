from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from superpower.runtime.context import AgentContext


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        etf = context.get("etf_indicators")
        positions = context.get("positions")
        params = context.get("strategy_params")

        signal_table, buys, sells, watchlist, details = latest_etf_signals(etf, positions, params)
        context.put("etf_signal_table", signal_table)
        context.put("etf_buy_candidates", buys)
        context.put("etf_sell_alerts", sells)
        context.put("etf_watchlist", watchlist)
        context.put("etf_detail_history", details)
        return {
            "signal_rows": len(signal_table),
            "buy_candidates": len(buys),
            "sell_alerts": len(sells),
            "watchlist_candidates": len(watchlist),
        }


def latest_etf_signals(
    etf: pd.DataFrame,
    positions: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    holding_codes = set()
    if not positions.empty:
        holding_codes = set(positions[(positions["asset_type"] == "ETF") & (positions["status"] == "holding")]["code"])

    for (name, code), group in etf.groupby(["name", "code"]):
        g = group.sort_values("date").reset_index(drop=True)
        if len(g) < 61:
            continue

        row = g.iloc[-1]
        prev = g.iloc[-2]
        buy_reasons = _buy_reasons(row, prev, params)
        sell_reasons = _sell_reasons(row, params)
        ma5_ma10_signal = _ma5_ma10_signal(row, prev)
        ma5_ma20_status = _ma5_ma20_status(row)
        volume_check = _volume_check(row, params["etf"]["buy_volume_ratio_min"])
        watch_type, missing_condition, suggested_action = _watchlist_diagnosis(row, prev, params)

        rows.append(
            {
                "date": row["date"].date(),
                "code": code,
                "name": name,
                "position_status": "持仓中" if code in holding_codes else "未持仓/已平仓",
                "close": row["收盘价"],
                "ma5": row["ma5"],
                "ma10": row["ma10"],
                "ma20": row["ma20"],
                "ma60": row["ma60"],
                "vol_ratio60": row["vol_ratio60"],
                "macd_hist": row["macd_hist"],
                "ma5_ma10_signal": ma5_ma10_signal,
                "ma5_ma20_status": ma5_ma20_status,
                "volume_check": volume_check,
                "watch_type": watch_type,
                "missing_condition": missing_condition,
                "suggested_action": suggested_action,
                "share_change": row.get("份额变化（亿份）", np.nan),
                "buy_signal": bool(buy_reasons) and code not in holding_codes,
                "sell_signal": bool(sell_reasons) and code in holding_codes,
                "signal_reason": "；".join(buy_reasons + sell_reasons) or "未触发",
                "score": score_etf(row, params),
            }
        )
        for _, history in g.tail(8).iterrows():
            detail_rows.append(
                {
                    "code": code,
                    "name": name,
                    "date": history["date"].date(),
                    "close": history["收盘价"],
                    "ma5": history["ma5"],
                    "ma10": history["ma10"],
                    "ma20": history["ma20"],
                    "vol_ratio60": history["vol_ratio60"],
                    "dif": history["dif"],
                    "dea": history["dea"],
                    "macd_hist": history["macd_hist"],
                    "kdj_j": history["kdj_j"],
                }
            )

    signal_table = pd.DataFrame(rows)
    if signal_table.empty:
        return signal_table, signal_table.copy(), signal_table.copy(), signal_table.copy(), pd.DataFrame(detail_rows)

    signal_table = signal_table.sort_values(["buy_signal", "sell_signal", "score"], ascending=[False, False, False])
    buys = signal_table[signal_table["buy_signal"]].copy().sort_values("score", ascending=False)
    sells = signal_table[signal_table["sell_signal"]].copy().sort_values("score")
    watchlist = signal_table[
        (~signal_table["buy_signal"])
        & (~signal_table["sell_signal"])
        & (signal_table["position_status"] != "持仓中")
        & (signal_table["watch_type"] != "")
    ].copy().sort_values("score", ascending=False)
    return signal_table, buys, sells, watchlist, pd.DataFrame(detail_rows)


def _buy_reasons(row: pd.Series, prev: pd.Series, params: dict[str, Any]) -> list[str]:
    threshold = params["etf"]["buy_volume_ratio_min"]
    reasons = []
    ma5_cross_ma10 = (
        pd.notna(prev["ma5"])
        and pd.notna(prev["ma10"])
        and prev["ma5"] <= prev["ma10"]
        and row["ma5"] > row["ma10"]
    )
    macd_improving = pd.notna(row["macd_hist"]) and pd.notna(prev["macd_hist"]) and row["macd_hist"] > prev["macd_hist"]
    volume_ok = pd.notna(row["vol_ratio60"]) and row["vol_ratio60"] >= threshold

    if ma5_cross_ma10 and macd_improving and volume_ok:
        reasons.append("MA5上穿MA10")
        if pd.notna(row.get("ma20")) and row["ma5"] > row["ma20"]:
            reasons.append("MA5同时高于MA20（增强项）")

    if (
        pd.notna(prev["dif"])
        and prev["dif"] <= prev["dea"]
        and row["dif"] > row["dea"]
        and row["ma5"] > row["ma10"]
        and row["收盘价"] > row["ma20"]
        and volume_ok
    ):
        reasons.append("MACD金叉")
    return reasons


def _ma5_ma10_signal(row: pd.Series, prev: pd.Series) -> str:
    if pd.isna(prev.get("ma5")) or pd.isna(prev.get("ma10")) or pd.isna(row.get("ma5")) or pd.isna(row.get("ma10")):
        return "MA历史不足"
    if prev["ma5"] <= prev["ma10"] and row["ma5"] > row["ma10"]:
        return "MA5上穿MA10"
    if row["ma5"] > row["ma10"]:
        return "MA5高于MA10"
    return "MA5未高于MA10"


def _ma5_ma20_status(row: pd.Series) -> str:
    if pd.isna(row.get("ma5")) or pd.isna(row.get("ma20")):
        return "MA20历史不足"
    return "MA5高于MA20（增强项）" if row["ma5"] > row["ma20"] else "MA5未高于MA20（不作为硬条件）"


def _volume_check(row: pd.Series, threshold: float) -> str:
    if pd.isna(row.get("vol_ratio60")):
        return "量能历史不足"
    status = "达标" if row["vol_ratio60"] >= threshold else "未达标"
    return f"前60日均量倍数{row['vol_ratio60']:.4f}，阈值{threshold:g}，{status}"


def _watchlist_diagnosis(row: pd.Series, prev: pd.Series, params: dict[str, Any]) -> tuple[str, str, str]:
    threshold = params["etf"]["buy_volume_ratio_min"]
    volume_ok = pd.notna(row.get("vol_ratio60")) and row["vol_ratio60"] >= threshold
    macd_improving = pd.notna(row.get("macd_hist")) and pd.notna(prev.get("macd_hist")) and row["macd_hist"] > prev["macd_hist"]
    ma5_cross_ma10 = (
        pd.notna(prev.get("ma5"))
        and pd.notna(prev.get("ma10"))
        and pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and prev["ma5"] <= prev["ma10"]
        and row["ma5"] > row["ma10"]
    )
    macd_gap_prev = prev["dif"] - prev["dea"] if pd.notna(prev.get("dif")) and pd.notna(prev.get("dea")) else np.nan
    macd_gap = row["dif"] - row["dea"] if pd.notna(row.get("dif")) and pd.notna(row.get("dea")) else np.nan
    macd_near_cross = pd.notna(macd_gap) and pd.notna(macd_gap_prev) and macd_gap < 0 and macd_gap > macd_gap_prev
    trend_strong = (
        pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and pd.notna(row.get("ma20"))
        and row["ma5"] > row["ma10"]
        and row["收盘价"] > row["ma20"]
    )

    if ma5_cross_ma10 and macd_improving and not volume_ok:
        return "均线已触发，量能未确认", _volume_check(row, threshold), "关注，等待放量确认"
    if macd_near_cross and row["收盘价"] > row["ma20"] and not volume_ok:
        return "MACD接近确认，量能未确认", _volume_check(row, threshold), "关注，等待MACD金叉与量能确认"
    if trend_strong and macd_improving and not volume_ok:
        return "趋势改善，量能未确认", _volume_check(row, threshold), "跟踪，不追高，等待再次放量"
    return "", "", ""


def _sell_reasons(row: pd.Series, params: dict[str, Any]) -> list[str]:
    reasons = []
    if row["收盘价"] < row["ma10"] and row["vol_ratio60"] >= params["etf"]["sell_ma10_volume_ratio_min"]:
        reasons.append("收盘跌破MA10且放量")
    if row["收盘价"] < row["ma5"] and row["vol_ratio60"] >= params["etf"]["sell_ma5_volume_ratio_min"]:
        reasons.append("收盘跌破MA5且明显放量")
    return reasons


def score_etf(row: pd.Series, params: dict[str, Any]) -> float:
    weights = params["etf"]["score_weights"]
    trend = 0.0
    if pd.notna(row.get("ma5")) and pd.notna(row.get("ma10")) and row["ma5"] > row["ma10"]:
        trend += 50
    if pd.notna(row.get("ma20")) and row["收盘价"] > row["ma20"]:
        trend += 30
    if pd.notna(row.get("ma60")) and row["收盘价"] > row["ma60"]:
        trend += 20

    macd = 50.0
    if pd.notna(row.get("macd_hist")):
        macd += min(max(row["macd_hist"] * 3000, -50), 50)

    volume = 0.0 if pd.isna(row.get("vol_ratio60")) else min(row["vol_ratio60"] / 2 * 100, 100)
    share_change = 50.0
    if "份额变化（亿份）" in row and pd.notna(row["份额变化（亿份）"]):
        share_change = min(max(50 + row["份额变化（亿份）"] * 5, 0), 100)

    return round(
        trend * weights["trend"]
        + macd * weights["macd"]
        + volume * weights["volume"]
        + share_change * weights["share_change"],
        2,
    )
