from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.skills.etf_rotation_strategy.handler import _buy_reasons, _sell_reasons
from superpower.skills.tl_timing_strategy.handler import tl_state_history


FEE_RATE = 0.001


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        etf = context.get("etf_indicators")
        tl = context.get("tl_indicators")
        params = context.get("strategy_params")

        etf_trades = _backtest_etf(etf, params)
        tl_history = tl_state_history(tl, params)
        next_day_checks = _next_day_signal_checks(etf, params)
        summary = _summary(etf, etf_trades, tl_history, next_day_checks)

        context.put("backtest_summary", summary)
        context.put("backtest_trades", etf_trades)
        context.put("backtest_next_day_checks", next_day_checks)
        return {
            "backtest_summary_rows": len(summary),
            "backtest_trades": len(etf_trades),
            "backtest_next_day_checks": len(next_day_checks),
            "history_days": int(etf["date"].nunique()) if not etf.empty else 0,
        }


def _backtest_etf(etf: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    trades: list[dict[str, Any]] = []
    for (name, code), group in etf.groupby(["name", "code"]):
        g = group.sort_values("date").reset_index(drop=True)
        if len(g) < 62:
            continue
        in_position = False
        entry_date = None
        entry_price = np.nan
        entry_signal_date = None
        entry_reason = ""

        for idx in range(61, len(g) - 1):
            row = g.iloc[idx]
            prev = g.iloc[idx - 1]
            next_row = g.iloc[idx + 1]

            if not in_position:
                reasons = _buy_reasons(row, prev, params)
                if reasons:
                    in_position = True
                    entry_date = next_row["date"]
                    entry_signal_date = row["date"]
                    entry_price = float(next_row["开盘价"])
                    entry_reason = "；".join(reasons)
                continue

            exit_reasons = _sell_reasons(row, params)
            if exit_reasons:
                exit_price = float(next_row["开盘价"])
                gross_return = exit_price / entry_price - 1
                net_return = gross_return - FEE_RATE * 2
                trades.append(
                    {
                        "code": code,
                        "name": name,
                        "entry_signal_date": entry_signal_date,
                        "entry_date": entry_date,
                        "entry_price": entry_price,
                        "exit_signal_date": row["date"],
                        "exit_date": next_row["date"],
                        "exit_price": exit_price,
                        "holding_days": int((next_row["date"] - entry_date).days) if entry_date is not None else None,
                        "gross_return": gross_return,
                        "net_return": net_return,
                        "entry_reason": entry_reason,
                        "exit_reason": "；".join(exit_reasons),
                    }
                )
                in_position = False
                entry_date = None
                entry_signal_date = None
                entry_price = np.nan
                entry_reason = ""

        if in_position and entry_date is not None:
            last = g.iloc[-1]
            mark_return = float(last["收盘价"]) / entry_price - 1 - FEE_RATE
            trades.append(
                {
                    "code": code,
                    "name": name,
                    "entry_signal_date": entry_signal_date,
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "exit_signal_date": pd.NaT,
                    "exit_date": pd.NaT,
                    "exit_price": np.nan,
                    "holding_days": int((last["date"] - entry_date).days),
                    "gross_return": np.nan,
                    "net_return": mark_return,
                    "entry_reason": entry_reason,
                    "exit_reason": "open_trade",
                }
            )

    return pd.DataFrame(trades)


def _next_day_signal_checks(etf: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []
    for (name, code), group in etf.groupby(["name", "code"]):
        g = group.sort_values("date").reset_index(drop=True)
        if len(g) < 62:
            continue

        in_position = False
        for idx in range(61, len(g) - 1):
            row = g.iloc[idx]
            prev = g.iloc[idx - 1]
            next_row = g.iloc[idx + 1]
            next_open = float(next_row["开盘价"])
            next_close = float(next_row["收盘价"])
            next_return = next_close / next_open - 1 if next_open else np.nan
            next_close_vs_signal_close = next_close / float(row["收盘价"]) - 1 if float(row["收盘价"]) else np.nan

            if not in_position:
                reasons = _buy_reasons(row, prev, params)
                if reasons:
                    checks.append(
                        {
                            "code": code,
                            "name": name,
                            "signal_type": "建仓",
                            "signal_date": row["date"],
                            "next_date": next_row["date"],
                            "next_open": next_open,
                            "next_close": next_close,
                            "expected_direction": "上涨",
                            "next_day_return": next_return,
                            "next_close_vs_signal_close": next_close_vs_signal_close,
                            "hit": bool(pd.notna(next_return) and next_return > 0),
                            "reason": "；".join(reasons),
                        }
                    )
                    in_position = True
                continue

            exit_reasons = _sell_reasons(row, params)
            if exit_reasons:
                checks.append(
                    {
                        "code": code,
                        "name": name,
                        "signal_type": "平仓",
                        "signal_date": row["date"],
                        "next_date": next_row["date"],
                        "next_open": next_open,
                        "next_close": next_close,
                        "expected_direction": "下跌",
                        "next_day_return": next_return,
                        "next_close_vs_signal_close": next_close_vs_signal_close,
                        "hit": bool(pd.notna(next_return) and next_return < 0),
                        "reason": "；".join(exit_reasons),
                    }
                )
                in_position = False

    return pd.DataFrame(checks)


def _summary(
    etf: pd.DataFrame,
    trades: pd.DataFrame,
    tl_history: pd.DataFrame,
    next_day_checks: pd.DataFrame,
) -> pd.DataFrame:
    history_days = int(etf["date"].nunique()) if not etf.empty else 0
    symbol_count = int(etf[["name", "code"]].drop_duplicates().shape[0]) if not etf.empty else 0
    closed = trades[trades["exit_reason"] != "open_trade"].copy() if not trades.empty else pd.DataFrame()
    trade_count = len(closed)
    win_rate = float((closed["net_return"] > 0).mean()) if trade_count else np.nan
    avg_return = float(closed["net_return"].mean()) if trade_count else np.nan
    best_return = float(closed["net_return"].max()) if trade_count else np.nan
    worst_return = float(closed["net_return"].min()) if trade_count else np.nan
    avg_holding_days = float(closed["holding_days"].mean()) if trade_count else np.nan
    buy_checks = next_day_checks[next_day_checks["signal_type"] == "建仓"] if not next_day_checks.empty else pd.DataFrame()
    sell_checks = next_day_checks[next_day_checks["signal_type"] == "平仓"] if not next_day_checks.empty else pd.DataFrame()
    buy_next_day_count = len(buy_checks)
    sell_next_day_count = len(sell_checks)
    buy_next_day_hit_rate = float(buy_checks["hit"].mean()) if buy_next_day_count else np.nan
    sell_next_day_hit_rate = float(sell_checks["hit"].mean()) if sell_next_day_count else np.nan
    buy_next_day_avg_return = float(buy_checks["next_day_return"].mean()) if buy_next_day_count else np.nan
    sell_next_day_avg_return = float(sell_checks["next_day_return"].mean()) if sell_next_day_count else np.nan
    history_level = "OK" if history_days >= 750 else "WARN"
    history_note = "样本可用于初步回测" if history_days >= 750 else "历史不足，当前仅可做流程和信号频率诊断"

    rows = [
        {"item": "ETF回测标的数", "value": symbol_count, "level": "INFO", "note": ""},
        {"item": "ETF历史交易日", "value": history_days, "level": history_level, "note": history_note},
        {"item": "ETF闭合交易次数", "value": trade_count, "level": "INFO", "note": "信号日收盘后生成，下一交易日开盘模拟成交"},
        {"item": "ETF胜率", "value": win_rate, "level": "INFO", "note": ""},
        {"item": "ETF单笔平均收益", "value": avg_return, "level": "INFO", "note": "已扣双边千一费用假设"},
        {"item": "ETF最好单笔收益", "value": best_return, "level": "INFO", "note": ""},
        {"item": "ETF最差单笔收益", "value": worst_return, "level": "WARN" if pd.notna(worst_return) and worst_return < -0.08 else "INFO", "note": ""},
        {"item": "ETF平均持仓天数", "value": avg_holding_days, "level": "INFO", "note": ""},
        {
            "item": "ETF建仓次日样本数",
            "value": buy_next_day_count,
            "level": "INFO",
            "note": "信号日收盘后生成，验证T+1开盘到收盘是否上涨",
        },
        {"item": "ETF建仓次日上涨命中率", "value": buy_next_day_hit_rate, "level": "INFO", "note": ""},
        {"item": "ETF建仓次日平均收益", "value": buy_next_day_avg_return, "level": "INFO", "note": "T+1开盘到收盘"},
        {
            "item": "ETF平仓次日样本数",
            "value": sell_next_day_count,
            "level": "INFO",
            "note": "仅统计模拟持仓中触发的平仓信号，验证T+1开盘到收盘是否下跌",
        },
        {"item": "ETF平仓次日下跌命中率", "value": sell_next_day_hit_rate, "level": "INFO", "note": ""},
        {"item": "ETF平仓次日平均收益", "value": sell_next_day_avg_return, "level": "INFO", "note": "负数表示平仓后次日下跌"},
        {
            "item": "TL建议建仓信号次数",
            "value": int((tl_history["state"] == "建议建仓").sum()) if not tl_history.empty else 0,
            "level": "INFO",
            "note": "TL第一版只做状态诊断，不模拟平仓收益",
        },
        {
            "item": "TL不做交易天数",
            "value": int((tl_history["state"] == "不做交易").sum()) if not tl_history.empty else 0,
            "level": "INFO",
            "note": "",
        },
    ]
    return pd.DataFrame(rows)
