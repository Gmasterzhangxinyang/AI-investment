from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ...contracts import (
    ETFDecision,
    ETFHistory,
    ETFPositionState,
    MediumStatus,
    ShortEntryStatus,
)
from ..legacy_v1 import (
    legacy_action_text,
    legacy_ma5_ma10_signal,
    legacy_ma5_ma20_status,
    legacy_metrics,
    legacy_score,
    legacy_sell_reasons,
    legacy_volume_check,
)
from .defaults import STRATEGY_ID, STRATEGY_VERSION
from .medium_trend import MediumTrendResult, evaluate_medium_history
from .short_entry import ShortEntryResult, evaluate_short_entry_history


WATCH_STATES = {
    ShortEntryStatus.CLOSE_WATCH,
    ShortEntryStatus.WAITING_CONFIRMATION,
    ShortEntryStatus.WAITING_PULLBACK,
    ShortEntryStatus.OVERHEATED_DO_NOT_CHASE,
}

REQUIRED_RAW_COLUMNS = (
    "date",
    "开盘价",
    "最高价",
    "最低价",
    "收盘价",
    "成交量（万股）",
)


class TrendPullbackV2Strategy:
    strategy_id = STRATEGY_ID
    version = STRATEGY_VERSION

    def evaluate_history(
        self,
        history: ETFHistory,
        params: Mapping[str, Any],
    ) -> list[ETFDecision]:
        rows = history.rows.sort_values("date").reset_index(drop=True)
        if rows.empty:
            return []
        missing_columns = [key for key in REQUIRED_RAW_COLUMNS if key not in rows]
        if missing_columns:
            return [
                ETFDecision.unavailable(
                    as_of=pd.Timestamp(row["date"]),
                    code=history.code,
                    name=history.name,
                    strategy_id=self.strategy_id,
                    strategy_version=self.version,
                    reason="missing_columns=" + ",".join(missing_columns),
                )
                for _, row in rows.iterrows()
            ]

        unique_date = ~rows["date"].duplicated(keep="last")
        complete = rows[list(REQUIRED_RAW_COLUMNS)].notna().all(axis=1)
        valid_row = unique_date & complete
        valid_count = valid_row.astype(int).cumsum()
        minimum = int(params["medium_trend"]["minimum_history_rows"])

        medium = evaluate_medium_history(rows, params["medium_trend"])
        for index in range(len(rows)):
            if not bool(valid_row.iloc[index]) or int(valid_count.iloc[index]) < minimum:
                count = int(valid_count.iloc[index])
                medium[index] = MediumTrendResult(
                    status=MediumStatus.DATA_UNAVAILABLE,
                    reason=f"valid_history_rows={count}; required={minimum}",
                    rule_hits=(),
                    missing_conditions=("minimum_history_rows",),
                    ma5_crossed_ma20_today=False,
                )

        short = evaluate_short_entry_history(
            rows,
            medium,
            params["short_entry"],
            trading_session_numbers=valid_count.tolist(),
        )
        return [
            self._compose_decision(
                history=history,
                rows=rows,
                index=index,
                medium=medium[index],
                short=short[index],
                params=params,
            )
            for index in range(len(rows))
        ]

    def evaluate(
        self,
        history: ETFHistory,
        position: ETFPositionState,
        params: Mapping[str, Any],
    ) -> ETFDecision:
        decisions = self.evaluate_history(history, params)
        if not decisions:
            raise ValueError("ETF history must not be empty")
        decision = decisions[-1]
        row = history.rows.sort_values("date").reset_index(drop=True).iloc[-1]
        legacy_params = params["exit"]["legacy_params"]
        sell_reasons = legacy_sell_reasons(row, legacy_params)
        sell = position.is_holding and bool(sell_reasons)
        buy = (
            decision.short_entry_status is ShortEntryStatus.CAN_ENTER
            and not position.is_holding
            and not sell
        )
        watch = (
            decision.short_entry_status in WATCH_STATES
            and not position.is_holding
            and not sell
        )
        signal_type = (
            "sell_alert"
            if sell
            else "buy_candidate"
            if buy
            else "watch"
            if watch
            else "data_unavailable"
            if decision.medium_status is MediumStatus.DATA_UNAVAILABLE
            else "neutral"
        )
        reason = "；".join(sell_reasons) if sell else decision.short_entry_reason
        fields = dict(decision.compatibility_fields)
        fields.update(
            {
                "position_status": "持仓中" if position.is_holding else "未持仓/已平仓",
                "signal_type": signal_type,
                "action": signal_type,
                "display_action": legacy_action_text(signal_type),
                "reason": reason,
                "watch_type": decision.short_entry_reason if watch else "",
                "buy_signal": buy,
                "sell_signal": sell,
                "signal_reason": reason,
            }
        )
        return replace(
            decision,
            eligible=buy,
            buy_candidate=buy,
            watch_candidate=watch,
            sell_alert=sell,
            exit_status="triggered" if sell else "not_triggered",
            short_entry_reason=reason if sell else decision.short_entry_reason,
            compatibility_fields=fields,
        )

    def _compose_decision(
        self,
        *,
        history: ETFHistory,
        rows: pd.DataFrame,
        index: int,
        medium: MediumTrendResult,
        short: ShortEntryResult,
        params: Mapping[str, Any],
    ) -> ETFDecision:
        row = rows.iloc[index]
        previous = rows.iloc[index - 1] if index > 0 else row
        ranking_params = params["ranking"]["legacy_params"]
        score = legacy_score(row, ranking_params) if index >= 60 else 0.0
        preview_missing = pd.isna(row.get("weekly_macd_preview"))
        risk_notes = tuple(short.risk_notes) + (
            ("周MACD预览不可用，仍按已完成周的正式状态判断",)
            if preview_missing and pd.notna(row.get("weekly_macd_hist"))
            else ()
        )
        data_quality = "WARN" if risk_notes else "OK"
        signal_type = (
            "data_unavailable"
            if medium.status is MediumStatus.DATA_UNAVAILABLE
            else "neutral"
        )
        fields: dict[str, Any] = {
            "date": pd.Timestamp(row["date"]).date(),
            "code": history.code,
            "name": history.name,
            "position_status": "未持仓/已平仓",
            "signal_type": signal_type,
            "action": signal_type,
            "display_action": legacy_action_text(signal_type),
            "reason": short.reason,
            "metrics": {**legacy_metrics(row), "entry_route": short.entry_route},
            "rule_hits": "；".join((*medium.rule_hits, *short.rule_hits)),
            "risk_notes": "；".join(risk_notes),
            "confidence": "low" if medium.status is MediumStatus.DATA_UNAVAILABLE else "medium",
            "data_quality": "ERROR" if medium.status is MediumStatus.DATA_UNAVAILABLE else data_quality,
            "close": row.get("收盘价", np.nan),
            "ma5": row.get("ma5", np.nan),
            "ma10": row.get("ma10", np.nan),
            "ma20": row.get("ma20", np.nan),
            "ma60": row.get("ma60", np.nan),
            "vol_ratio60": row.get("vol_ratio60", np.nan),
            "macd_hist": row.get("macd_hist", np.nan),
            "ma5_ma10_signal": legacy_ma5_ma10_signal(row, previous),
            "ma5_ma20_status": legacy_ma5_ma20_status(row),
            "volume_check": legacy_volume_check(
                row,
                float(ranking_params["buy_volume_ratio_min"]),
            ),
            "watch_type": "",
            "missing_condition": "；".join((*medium.missing_conditions, *short.missing_conditions)),
            "suggested_action": short.reason,
            "share_change": row.get("份额变化（亿份）", np.nan),
            "buy_signal": False,
            "sell_signal": False,
            "signal_reason": short.reason,
            "score": score,
            "strategy_id": self.strategy_id,
            "strategy_version": self.version,
            "medium_status": medium.status.value,
            "medium_reason": medium.reason,
            "short_entry_status": short.status.value,
            "short_entry_reason": short.reason,
            "weekly_macd_state": row.get("weekly_macd_state"),
            "weekly_macd_hist": _safe_float(row.get("weekly_macd_hist")),
            "weekly_macd_preview": _safe_float(row.get("weekly_macd_preview")),
            "weekly_macd_confirmation_check": short.weekly_macd_confirmation_check,
            "ma20_slope_5d": _safe_float(row.get("ma20_slope_5d")),
            "ma20_slope_state": row.get("ma20_slope_state"),
            "ma20_flat_check": short.ma20_flat_check,
            "daily_macd_state": row.get("daily_macd_state"),
            "ma5_above_ma10": bool(
                pd.notna(row.get("ma5"))
                and pd.notna(row.get("ma10"))
                and row["ma5"] > row["ma10"]
            ),
            "ma5_crossed_ma10_today": bool(
                index > 0
                and pd.notna(previous.get("ma5"))
                and pd.notna(previous.get("ma10"))
                and previous["ma5"] <= previous["ma10"]
                and row["ma5"] > row["ma10"]
            ),
            "setup_date": short.setup_date.date() if short.setup_date is not None else None,
            "setup_age": short.setup_age,
        }
        return ETFDecision(
            as_of=pd.Timestamp(row["date"]),
            code=history.code,
            name=history.name,
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            medium_status=medium.status,
            short_entry_status=short.status,
            exit_status="not_triggered",
            eligible=False,
            buy_candidate=False,
            watch_candidate=False,
            sell_alert=False,
            score=score,
            medium_reason=medium.reason,
            short_entry_reason=short.reason,
            metrics=fields["metrics"],
            rule_hits=(*medium.rule_hits, *short.rule_hits),
            missing_conditions=(*medium.missing_conditions, *short.missing_conditions),
            risk_notes=risk_notes,
            compatibility_fields=fields,
            confidence=str(fields["confidence"]),
            data_quality=str(fields["data_quality"]),
        )


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None
