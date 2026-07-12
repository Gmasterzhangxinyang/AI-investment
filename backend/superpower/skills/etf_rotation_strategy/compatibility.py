from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .contracts import ETFDecision


LEGACY_SIGNAL_COLUMNS = [
    "date",
    "code",
    "name",
    "position_status",
    "signal_type",
    "action",
    "display_action",
    "reason",
    "metrics",
    "rule_hits",
    "risk_notes",
    "confidence",
    "data_quality",
    "close",
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "vol_ratio60",
    "macd_hist",
    "ma5_ma10_signal",
    "ma5_ma20_status",
    "volume_check",
    "watch_type",
    "missing_condition",
    "suggested_action",
    "share_change",
    "buy_signal",
    "sell_signal",
    "signal_reason",
    "score",
]

CANONICAL_SIGNAL_COLUMNS = [
    "strategy_id",
    "strategy_version",
    "medium_status",
    "medium_reason",
    "short_entry_status",
    "short_entry_reason",
    "weekly_macd_state",
    "weekly_macd_hist",
    "weekly_macd_preview",
    "weekly_macd_confirmation_check",
    "ma20_slope_5d",
    "ma20_slope_state",
    "ma20_flat_check",
    "daily_macd_state",
    "ma5_above_ma10",
    "ma5_crossed_ma10_today",
    "setup_date",
    "setup_age",
]

SIGNAL_COLUMNS = LEGACY_SIGNAL_COLUMNS + CANONICAL_SIGNAL_COLUMNS


def decisions_to_legacy_tables(
    decisions: Sequence[ETFDecision],
    etf: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = [_project_decision(decision) for decision in decisions]
    signal_table = pd.DataFrame(rows, columns=SIGNAL_COLUMNS)
    details = _detail_history(etf)
    if signal_table.empty:
        return (
            signal_table,
            signal_table.copy(),
            signal_table.copy(),
            signal_table.copy(),
            details,
        )
    signal_table = signal_table.sort_values(
        ["buy_signal", "sell_signal", "score"],
        ascending=[False, False, False],
    )
    buys = signal_table[signal_table["buy_signal"]].copy().sort_values("score", ascending=False)
    sells = signal_table[signal_table["sell_signal"]].copy().sort_values("score")
    watchlist = signal_table[
        (~signal_table["buy_signal"])
        & (~signal_table["sell_signal"])
        & (signal_table["position_status"] != "持仓中")
        & (signal_table["watch_type"] != "")
    ].copy().sort_values("score", ascending=False)
    return signal_table, buys, sells, watchlist, details


def _project_decision(decision: ETFDecision) -> dict[str, object]:
    fields = dict(decision.compatibility_fields)
    fields.update(
        {
            "strategy_id": decision.strategy_id,
            "strategy_version": decision.strategy_version,
            "medium_status": decision.medium_status.value,
            "medium_reason": decision.medium_reason,
            "short_entry_status": decision.short_entry_status.value,
            "short_entry_reason": decision.short_entry_reason,
        }
    )
    return fields


def _detail_history(etf: pd.DataFrame) -> pd.DataFrame:
    details: list[dict[str, object]] = []
    for (name, code), group in etf.groupby(["name", "code"]):
        rows = group.sort_values("date").reset_index(drop=True)
        if len(rows) < 61:
            continue
        for _, history in rows.tail(8).iterrows():
            details.append(
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
    return pd.DataFrame(details)
