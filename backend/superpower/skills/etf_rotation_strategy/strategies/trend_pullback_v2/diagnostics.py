from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from ...contracts import ETFDecision


EVENT_STATES = {
    "close_watch",
    "overheated_do_not_chase",
    "waiting_pullback",
    "can_enter",
}
LEGACY_EVENT_MAP = {
    "legacy_watch": "close_watch",
    "legacy_buy": "can_enter",
}
HORIZONS = (1, 3, 5, 10, 20)


def diagnostic_trace(
    decisions: Sequence[ETFDecision],
    bars: pd.DataFrame,
    *,
    config_hash: str,
) -> pd.DataFrame:
    bar_rows = bars.sort_values("date").drop_duplicates("date", keep="last")
    bar_by_date = {
        pd.Timestamp(row["date"]): row
        for _, row in bar_rows.iterrows()
        if pd.notna(row.get("date"))
    }
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        date = pd.Timestamp(decision.as_of)
        bar = bar_by_date.get(date)
        if bar is None or any(pd.isna(bar.get(key)) for key in ("收盘价", "最高价", "最低价")):
            continue
        entry_route = str(decision.metrics.get("entry_route", ""))
        rows.append(
            {
                "date": date,
                "code": decision.code,
                "name": decision.name,
                "strategy_id": decision.strategy_id,
                "strategy_version": decision.strategy_version,
                "config_hash": config_hash,
                "medium_status": decision.medium_status.value,
                "short_entry_status": decision.short_entry_status.value,
                "combined_state_key": (
                    f"{decision.medium_status.value}|{decision.short_entry_status.value}"
                ),
                "entry_route": entry_route,
                "收盘价": float(bar["收盘价"]),
                "最高价": float(bar["最高价"]),
                "最低价": float(bar["最低价"]),
            }
        )
    return pd.DataFrame(rows)


def diagnostic_events(trace: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if trace.empty:
        return pd.DataFrame()
    group_columns = ["strategy_id", "code"]
    for _, group in trace.groupby(group_columns, sort=False):
        bars = group.sort_values("date").reset_index(drop=True)
        previous_short: str | None = None
        previous_medium: str | None = None
        for index, row in bars.iterrows():
            short = LEGACY_EVENT_MAP.get(
                str(row["short_entry_status"]),
                str(row["short_entry_status"]),
            )
            event_types: list[str] = []
            if short in EVENT_STATES and short != previous_short:
                event_types.append(short)
            medium = str(row["medium_status"])
            if (
                previous_medium is not None
                and medium == "trend_confirmed"
                and previous_medium != "trend_confirmed"
            ):
                event_types.insert(0, "trend_confirmed")
            for state_type in event_types:
                event = {
                    "event_date": row["date"],
                    "code": row["code"],
                    "name": row["name"],
                    "strategy_id": row["strategy_id"],
                    "strategy_version": row["strategy_version"],
                    "config_hash": row["config_hash"],
                    "state_type": state_type,
                    "entry_route": row.get("entry_route", "") if state_type == "can_enter" else "",
                }
                event.update(_outcomes(bars, index))
                forward_10 = event.get("forward_close_return_10d")
                event["false_reversal_10d"] = (
                    bool(forward_10 <= 0)
                    if state_type == "can_enter" and forward_10 is not None
                    else False
                )
                rows.append(event)
            previous_short = short
            previous_medium = medium
    return pd.DataFrame(rows)


def summarize_historical_diagnostics(
    events: pd.DataFrame,
    traces: pd.DataFrame,
) -> pd.DataFrame:
    if traces.empty:
        return pd.DataFrame()
    stability: dict[str, dict[str, float | int]] = {}
    for strategy_id, group in traces.groupby("strategy_id"):
        ordered = group.sort_values(["code", "date"])
        transitions = 0
        possible = 0
        for _, symbol in ordered.groupby("code"):
            states = symbol["combined_state_key"].tolist()
            transitions += sum(left != right for left, right in zip(states, states[1:], strict=False))
            possible += max(len(states) - 1, 0)
        valid_rows = len(ordered)
        stability[str(strategy_id)] = {
            "valid_rows": valid_rows,
            "transition_count": transitions,
            "state_flip_frequency": transitions / max(possible, 1),
        }
    if events.empty:
        return pd.DataFrame(
            [
                {"strategy_id": strategy_id, **values}
                for strategy_id, values in stability.items()
            ]
        )

    summaries: list[dict[str, Any]] = []
    grouping = ["strategy_id", "state_type", "entry_route"]
    for keys, group in events.groupby(grouping, dropna=False):
        strategy_id, state_type, entry_route = keys
        false_complete = group[
            (group["state_type"] == "can_enter")
            & group["forward_close_return_10d"].notna()
        ]
        false_count = int(false_complete["false_reversal_10d"].sum())
        false_rate = false_count / len(false_complete) if len(false_complete) else np.nan
        for horizon in HORIZONS:
            return_column = f"forward_close_return_{horizon}d"
            mfe_column = f"maximum_favorable_excursion_{horizon}d"
            mae_column = f"maximum_adverse_excursion_{horizon}d"
            complete = group[group[return_column].notna()]
            returns = complete[return_column]
            summary = {
                "strategy_id": strategy_id,
                "state_type": state_type,
                "entry_route": entry_route,
                "horizon": horizon,
                "event_count": len(group),
                "complete_horizon_count": len(complete),
                "mean_return": returns.mean(),
                "median_return": returns.median(),
                "p25_return": returns.quantile(0.25),
                "p75_return": returns.quantile(0.75),
                "positive_return_rate": (returns > 0).mean() if len(returns) else np.nan,
                "mean_maximum_favorable_excursion": complete[mfe_column].mean(),
                "mean_maximum_adverse_excursion": complete[mae_column].mean(),
                "false_reversal_10d_count": false_count,
                "false_reversal_10d_rate": false_rate,
                **stability[str(strategy_id)],
            }
            summaries.append(summary)
    return pd.DataFrame(summaries)


def _outcomes(bars: pd.DataFrame, index: int) -> dict[str, float | None]:
    signal_close = float(bars.iloc[index]["收盘价"])
    result: dict[str, float | None] = {}
    for horizon in HORIZONS:
        future = bars.iloc[index + 1 : index + horizon + 1]
        if len(future) < horizon:
            result[f"forward_close_return_{horizon}d"] = np.nan
            result[f"maximum_favorable_excursion_{horizon}d"] = np.nan
            result[f"maximum_adverse_excursion_{horizon}d"] = np.nan
            continue
        result[f"forward_close_return_{horizon}d"] = round(
            float(future.iloc[-1]["收盘价"]) / signal_close - 1,
            12,
        )
        result[f"maximum_favorable_excursion_{horizon}d"] = round(
            float(future["最高价"].max()) / signal_close - 1,
            12,
        )
        result[f"maximum_adverse_excursion_{horizon}d"] = round(
            float(future["最低价"].min()) / signal_close - 1,
            12,
        )
    return result
