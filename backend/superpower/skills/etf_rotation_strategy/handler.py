from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import pandas as pd

from superpower.runtime.context import AgentContext

from .compatibility import SIGNAL_COLUMNS, decisions_to_legacy_tables
from .config import etf_config_hash, normalize_etf_config
from .contracts import (
    ETFDecision,
    ETFHistory,
    ETFPositionState,
    ETFStrategy,
    ETFStrategyRuntimeError,
)
from .registry import default_registry
from .risk_overlay import evaluate_legacy_risk_overlay
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
        normalized = normalize_etf_config(params)
        registry = default_registry()
        strategy = registry.create(normalized["active_strategy"])
        quality_warnings = _etf_quality_warnings(
            context.maybe("data_quality_report", pd.DataFrame())
        )

        signal_table, buys, sells, watchlist, details = latest_etf_signals(
            etf,
            positions,
            params,
            quality_warnings=quality_warnings,
        )
        context.put("etf_signal_table", signal_table)
        context.put("etf_buy_candidates", buys)
        context.put("etf_sell_alerts", sells)
        context.put("etf_watchlist", watchlist)
        context.put("etf_detail_history", details)
        context.put(
            "etf_strategy_run",
            {
                "strategy_id": normalized["active_strategy"],
                "strategy_version": strategy.version,
                "config_hash": etf_config_hash(normalized),
            },
        )
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
    *,
    quality_warnings: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    normalized = normalize_etf_config(params)
    registry = default_registry()
    strategy = registry.create(normalized["active_strategy"])
    profile = normalized["strategy_profiles"][normalized["active_strategy"]]
    decisions = evaluate_latest_by_symbol(etf, positions, strategy, profile)
    if normalized["active_strategy"] == "legacy_v1":
        decisions = attach_legacy_risk_overlays(
            decisions,
            etf,
            normalized["strategy_profiles"]["trend_pullback_v2"]["short_entry"],
        )
    decisions = attach_quality_warnings(decisions, quality_warnings)
    return decisions_to_legacy_tables(decisions, etf)


def attach_legacy_risk_overlays(
    decisions: Sequence[ETFDecision],
    etf: pd.DataFrame,
    profile: Mapping[str, Any],
) -> list[ETFDecision]:
    histories = {
        str(code): group.sort_values("date").reset_index(drop=True)
        for (_, code), group in etf.groupby(["name", "code"])
    }
    attached: list[ETFDecision] = []
    for decision in decisions:
        rows = histories.get(str(decision.code), pd.DataFrame())
        overlay = evaluate_legacy_risk_overlay(rows, profile)
        fields = dict(decision.compatibility_fields)
        fields.update(
            {
                "risk_overlay_level": overlay.level,
                "risk_overlay_summary": overlay.summary,
                "risk_overlay_flags": "；".join(overlay.flags),
                "risk_overlay_ma20_state": overlay.ma20_state,
                "risk_overlay_weekly_macd_state": overlay.weekly_macd_state,
            }
        )
        attached.append(replace(decision, compatibility_fields=fields))
    return attached


def attach_quality_warnings(
    decisions: Sequence[ETFDecision],
    warnings: Sequence[str],
) -> list[ETFDecision]:
    clean = tuple(str(warning) for warning in warnings if str(warning).strip())
    if not clean:
        return list(decisions)
    attached: list[ETFDecision] = []
    for decision in decisions:
        fields = dict(decision.compatibility_fields)
        combined = (*decision.risk_notes, *clean)
        fields["risk_notes"] = "；".join(combined)
        fields["data_quality"] = "WARN"
        attached.append(
            replace(
                decision,
                risk_notes=combined,
                data_quality="WARN",
                compatibility_fields=fields,
            )
        )
    return attached


def _etf_quality_warnings(report: pd.DataFrame) -> tuple[str, ...]:
    if report.empty or not {"item", "status"}.issubset(report.columns):
        return ()
    relevant = report[
        report["status"].isin(["WARN", "ERROR", "FAIL"])
        & report["item"].astype(str).str.contains("ETF", case=False, na=False)
    ]
    return tuple(
        f"{row['item']}：{row.get('detail', '')} {row.get('note', '')}".strip()
        for _, row in relevant.iterrows()
    )


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
