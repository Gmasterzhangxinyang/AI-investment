from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from superpower.runtime.context import AgentContext

from .compatibility import SIGNAL_COLUMNS, decisions_to_legacy_tables
from .config import normalize_etf_config
from .contracts import (
    ETFDecision,
    ETFHistory,
    ETFPositionState,
    ETFStrategy,
    ETFStrategyRuntimeError,
)
from .registry import default_registry
from .strategies.legacy_v1 import (
    legacy_buy_reasons,
    legacy_score,
    legacy_sell_reasons,
)


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        etf = context.get("etf_indicators")
        positions = context.get("positions")
        params = context.get("strategy_params")

        signal_table, buys, sells, watchlist, details = latest_etf_signals(
            etf,
            positions,
            params,
        )
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
    normalized = normalize_etf_config(params)
    registry = default_registry()
    strategy = registry.create(normalized["active_strategy"])
    profile = normalized["strategy_profiles"][normalized["active_strategy"]]
    decisions = evaluate_latest_by_symbol(etf, positions, strategy, profile)
    return decisions_to_legacy_tables(decisions, etf)


def evaluate_latest_by_symbol(
    etf: pd.DataFrame,
    positions: pd.DataFrame,
    strategy: ETFStrategy,
    profile: Mapping[str, Any],
) -> list[ETFDecision]:
    holding_codes: set[object] = set()
    if not positions.empty:
        holding_codes = set(
            positions[
                (positions["asset_type"] == "ETF")
                & (positions["status"] == "holding")
            ]["code"]
        )
    decisions: list[ETFDecision] = []
    for (name, code), group in etf.groupby(["name", "code"]):
        rows = group.sort_values("date").reset_index(drop=True)
        if rows.empty:
            continue
        as_of = pd.Timestamp(rows.iloc[-1]["date"])
        history = ETFHistory(
            code=str(code),
            name=str(name),
            rows=rows,
            as_of=as_of,
        )
        position = ETFPositionState(is_holding=code in holding_codes)
        try:
            decisions.append(strategy.evaluate(history, position, profile))
        except Exception as exc:
            raise ETFStrategyRuntimeError(
                f"ETF strategy {strategy.strategy_id} failed for {code} at {as_of.date()}"
            ) from exc
    return decisions


def _buy_reasons(
    row: pd.Series,
    prev: pd.Series,
    params: dict[str, Any],
) -> list[str]:
    return legacy_buy_reasons(row, prev, normalize_etf_config(params)["strategy_profiles"]["legacy_v1"])


def _sell_reasons(row: pd.Series, params: dict[str, Any]) -> list[str]:
    return legacy_sell_reasons(row, normalize_etf_config(params)["strategy_profiles"]["legacy_v1"])


def score_etf(row: pd.Series, params: dict[str, Any]) -> float:
    return legacy_score(row, normalize_etf_config(params)["strategy_profiles"]["legacy_v1"])
