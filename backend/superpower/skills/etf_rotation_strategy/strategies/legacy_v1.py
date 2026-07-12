from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..contracts import (
    ETFDecision,
    ETFHistory,
    ETFPositionState,
    MediumStatus,
    ShortEntryStatus,
)


STRATEGY_ID = "legacy_v1"
STRATEGY_VERSION = "1.0.0"


class LegacyV1Strategy:
    strategy_id = STRATEGY_ID
    version = STRATEGY_VERSION

    def evaluate(
        self,
        history: ETFHistory,
        position: ETFPositionState,
        params: Mapping[str, Any],
    ) -> ETFDecision:
        rows = history.rows.sort_values("date").reset_index(drop=True)
        if len(rows) < 61:
            return legacy_unavailable_decision(history, position, len(rows))
        return self._evaluate_rows(rows.iloc[-1], rows.iloc[-2], history, position, params)

    def evaluate_history(
        self,
        history: ETFHistory,
        params: Mapping[str, Any],
    ) -> list[ETFDecision]:
        rows = history.rows.sort_values("date").reset_index(drop=True)
        decisions: list[ETFDecision] = []
        for index in range(len(rows)):
            row_history = ETFHistory(
                code=history.code,
                name=history.name,
                rows=rows.iloc[index : index + 1].copy(),
                as_of=pd.Timestamp(rows.iloc[index]["date"]),
            )
            if index < 60:
                decisions.append(
                    legacy_unavailable_decision(
                        row_history,
                        ETFPositionState(False),
                        index + 1,
                    )
                )
                continue
            decisions.append(
                self._evaluate_rows(
                    rows.iloc[index],
                    rows.iloc[index - 1],
                    row_history,
                    ETFPositionState(False),
                    params,
                )
            )
        return decisions

    def _evaluate_rows(
        self,
        row: pd.Series,
        prev: pd.Series,
        history: ETFHistory,
        position: ETFPositionState,
        params: Mapping[str, Any],
    ) -> ETFDecision:
        buy_reasons = legacy_buy_reasons(row, prev, params)
        sell_reasons = legacy_sell_reasons(row, params)
        watch_type, missing_condition, suggested_action = legacy_watch_diagnosis(row, prev, params)
        buy_signal = bool(buy_reasons) and not position.is_holding
        sell_signal = bool(sell_reasons) and position.is_holding
        signal_type = legacy_signal_type(buy_signal, sell_signal, watch_type)
        watch_evidence = signal_type == "watch"
        public_watch = watch_evidence and not position.is_holding
        short_status = {
            "buy_candidate": ShortEntryStatus.LEGACY_BUY,
            "watch": ShortEntryStatus.LEGACY_WATCH,
        }.get(signal_type, ShortEntryStatus.LEGACY_NEUTRAL)
        fields = legacy_row_fields(
            row=row,
            prev=prev,
            code=history.code,
            name=history.name,
            position=position,
            params=params,
            buy_reasons=buy_reasons,
            sell_reasons=sell_reasons,
            watch_type=watch_type,
            missing_condition=missing_condition,
            suggested_action=suggested_action,
        )
        return ETFDecision(
            as_of=history.as_of,
            code=history.code,
            name=history.name,
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            medium_status=MediumStatus.NOT_APPLICABLE,
            short_entry_status=short_status,
            exit_status="triggered" if sell_signal else "not_triggered",
            eligible=buy_signal,
            buy_candidate=buy_signal,
            watch_candidate=public_watch,
            sell_alert=sell_signal,
            score=float(fields["score"]),
            medium_reason="原始策略不使用独立中期趋势状态",
            short_entry_reason=str(fields["reason"]),
            metrics=fields["metrics"],
            rule_hits=tuple(str(fields["rule_hits"]).split("；")) if fields["rule_hits"] else (),
            missing_conditions=(missing_condition,) if missing_condition else (),
            risk_notes=tuple(str(fields["risk_notes"]).split("；")) if fields["risk_notes"] else (),
            compatibility_fields=fields,
            confidence=str(fields["confidence"]),
            data_quality=str(fields["data_quality"]),
        )


def legacy_unavailable_decision(
    history: ETFHistory,
    position: ETFPositionState,
    history_rows: int,
) -> ETFDecision:
    row = history.rows.sort_values("date").iloc[-1]
    reason = f"有效历史仅{history_rows}行，少于61行，不能计算完整MA60/量能确认"
    fields = {
        "date": row["date"].date() if pd.notna(row.get("date")) else "",
        "code": history.code,
        "name": history.name,
        "position_status": "持仓中" if position.is_holding else "未持仓/已平仓",
        "signal_type": "data_unavailable",
        "action": "data_unavailable",
        "display_action": "数据不足，无法判断",
        "reason": reason,
        "metrics": legacy_metrics(row),
        "rule_hits": "",
        "risk_notes": reason,
        "confidence": "low",
        "data_quality": "ERROR",
        "close": row.get("收盘价", np.nan),
        "ma5": row.get("ma5", np.nan),
        "ma10": row.get("ma10", np.nan),
        "ma20": row.get("ma20", np.nan),
        "ma60": row.get("ma60", np.nan),
        "vol_ratio60": row.get("vol_ratio60", np.nan),
        "macd_hist": row.get("macd_hist", np.nan),
        "ma5_ma10_signal": "历史不足",
        "ma5_ma20_status": "历史不足",
        "volume_check": "量能历史不足",
        "watch_type": "",
        "missing_condition": reason,
        "suggested_action": "补足历史后再判断",
        "share_change": row.get("份额变化（亿份）", np.nan),
        "buy_signal": False,
        "sell_signal": False,
        "signal_reason": reason,
        "score": 0.0,
    }
    return ETFDecision(
        as_of=history.as_of,
        code=history.code,
        name=history.name,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        medium_status=MediumStatus.NOT_APPLICABLE,
        short_entry_status=ShortEntryStatus.DATA_UNAVAILABLE,
        exit_status="not_triggered",
        eligible=False,
        buy_candidate=False,
        watch_candidate=False,
        sell_alert=False,
        score=0.0,
        medium_reason="原始策略不使用独立中期趋势状态",
        short_entry_reason=reason,
        metrics=fields["metrics"],
        risk_notes=(reason,),
        compatibility_fields=fields,
        confidence="low",
        data_quality="ERROR",
    )


def legacy_row_fields(
    *,
    row: pd.Series,
    prev: pd.Series,
    code: str,
    name: str,
    position: ETFPositionState,
    params: Mapping[str, Any],
    buy_reasons: list[str],
    sell_reasons: list[str],
    watch_type: str,
    missing_condition: str,
    suggested_action: str,
) -> dict[str, Any]:
    buy_signal = bool(buy_reasons) and not position.is_holding
    sell_signal = bool(sell_reasons) and position.is_holding
    signal_type = legacy_signal_type(buy_signal, sell_signal, watch_type)
    data_quality = "OK" if pd.notna(row.get("vol_ratio60")) else "WARN"
    if buy_signal:
        reason = "；".join(buy_reasons)
    elif sell_signal:
        reason = "；".join(sell_reasons)
    elif watch_type:
        reason = watch_type
    else:
        reason = legacy_neutral_reason(row, prev, params, position.is_holding, bool(sell_reasons))
    rule_hits = legacy_rule_hits(
        buy_reasons if buy_signal else [],
        sell_reasons if sell_signal else [],
        watch_type,
        missing_condition,
    )
    risk_notes = legacy_risk_notes(row, prev, signal_type, watch_type)
    return {
        "date": row["date"].date(),
        "code": code,
        "name": name,
        "position_status": "持仓中" if position.is_holding else "未持仓/已平仓",
        "signal_type": signal_type,
        "action": signal_type,
        "display_action": legacy_action_text(signal_type),
        "reason": reason,
        "metrics": legacy_metrics(row),
        "rule_hits": rule_hits,
        "risk_notes": risk_notes,
        "confidence": legacy_confidence(data_quality, signal_type, row),
        "data_quality": data_quality,
        "close": row["收盘价"],
        "ma5": row["ma5"],
        "ma10": row["ma10"],
        "ma20": row["ma20"],
        "ma60": row["ma60"],
        "vol_ratio60": row["vol_ratio60"],
        "macd_hist": row["macd_hist"],
        "ma5_ma10_signal": legacy_ma5_ma10_signal(row, prev),
        "ma5_ma20_status": legacy_ma5_ma20_status(row),
        "volume_check": legacy_volume_check(row, float(params["buy_volume_ratio_min"])),
        "watch_type": watch_type,
        "missing_condition": missing_condition,
        "suggested_action": suggested_action,
        "share_change": row.get("份额变化（亿份）", np.nan),
        "buy_signal": buy_signal,
        "sell_signal": sell_signal,
        "signal_reason": reason,
        "score": legacy_score(row, params),
    }


def legacy_buy_reasons(
    row: pd.Series,
    prev: pd.Series,
    params: Mapping[str, Any],
) -> list[str]:
    params = _profile(params)
    threshold = float(params["buy_volume_ratio_min"])
    reasons: list[str] = []
    ma5_cross_ma10 = (
        pd.notna(prev["ma5"])
        and pd.notna(prev["ma10"])
        and prev["ma5"] <= prev["ma10"]
        and row["ma5"] > row["ma10"]
    )
    macd_improving = (
        pd.notna(row["macd_hist"])
        and pd.notna(prev["macd_hist"])
        and row["macd_hist"] > prev["macd_hist"]
    )
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


def legacy_sell_reasons(row: pd.Series, params: Mapping[str, Any]) -> list[str]:
    params = _profile(params)
    reasons: list[str] = []
    if row["收盘价"] < row["ma10"] and row["vol_ratio60"] >= params["sell_ma10_volume_ratio_min"]:
        reasons.append("收盘跌破MA10且放量")
    if row["收盘价"] < row["ma5"] and row["vol_ratio60"] >= params["sell_ma5_volume_ratio_min"]:
        reasons.append("收盘跌破MA5且明显放量")
    return reasons


def legacy_watch_diagnosis(
    row: pd.Series,
    prev: pd.Series,
    params: Mapping[str, Any],
) -> tuple[str, str, str]:
    threshold = float(params["buy_volume_ratio_min"])
    volume_ok = pd.notna(row.get("vol_ratio60")) and row["vol_ratio60"] >= threshold
    macd_improving = (
        pd.notna(row.get("macd_hist"))
        and pd.notna(prev.get("macd_hist"))
        and row["macd_hist"] > prev["macd_hist"]
    )
    ma5_cross_ma10 = (
        pd.notna(prev.get("ma5"))
        and pd.notna(prev.get("ma10"))
        and pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and prev["ma5"] <= prev["ma10"]
        and row["ma5"] > row["ma10"]
    )
    macd_gap_prev = (
        prev["dif"] - prev["dea"]
        if pd.notna(prev.get("dif")) and pd.notna(prev.get("dea"))
        else np.nan
    )
    macd_gap = (
        row["dif"] - row["dea"]
        if pd.notna(row.get("dif")) and pd.notna(row.get("dea"))
        else np.nan
    )
    macd_near_cross = (
        pd.notna(macd_gap)
        and pd.notna(macd_gap_prev)
        and macd_gap < 0
        and macd_gap > macd_gap_prev
    )
    trend_strong = (
        pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and pd.notna(row.get("ma20"))
        and row["ma5"] > row["ma10"]
        and row["收盘价"] > row["ma20"]
    )
    if ma5_cross_ma10 and macd_improving and not volume_ok:
        return "均线已触发，量能未确认", legacy_volume_check(row, threshold), "关注，等待放量确认"
    if macd_near_cross and row["收盘价"] > row["ma20"] and not volume_ok:
        return (
            "MACD接近确认，量能未确认",
            legacy_volume_check(row, threshold),
            "关注，等待MACD金叉与量能确认",
        )
    if trend_strong and macd_improving and not volume_ok:
        return "趋势改善，量能未确认", legacy_volume_check(row, threshold), "跟踪，不追高，等待再次放量"
    return "", "", ""


def legacy_score(row: pd.Series, params: Mapping[str, Any]) -> float:
    weights = params["score_weights"]
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


def legacy_ma5_ma10_signal(row: pd.Series, prev: pd.Series) -> str:
    if (
        pd.isna(prev.get("ma5"))
        or pd.isna(prev.get("ma10"))
        or pd.isna(row.get("ma5"))
        or pd.isna(row.get("ma10"))
    ):
        return "MA历史不足"
    if prev["ma5"] <= prev["ma10"] and row["ma5"] > row["ma10"]:
        return "MA5上穿MA10"
    if row["ma5"] > row["ma10"]:
        return "MA5高于MA10"
    return "MA5未高于MA10"


def legacy_ma5_ma20_status(row: pd.Series) -> str:
    if pd.isna(row.get("ma5")) or pd.isna(row.get("ma20")):
        return "MA20历史不足"
    return "MA5高于MA20（增强项）" if row["ma5"] > row["ma20"] else "MA5未高于MA20（不作为硬条件）"


def legacy_volume_check(row: pd.Series, threshold: float) -> str:
    if pd.isna(row.get("vol_ratio60")):
        return "量能历史不足"
    status = "达标" if row["vol_ratio60"] >= threshold else "未达标"
    return f"前60日均量倍数{row['vol_ratio60']:.4f}，阈值{threshold:g}，{status}"


def legacy_neutral_reason(
    row: pd.Series,
    prev: pd.Series,
    params: Mapping[str, Any],
    is_holding: bool,
    has_sell_shape: bool,
) -> str:
    if is_holding:
        return "持仓中，未触发平仓提示：" + "；".join(legacy_sell_missing_conditions(row, params))
    prefix = "非持仓标的；虽有平仓形态，但平仓提示只对持仓生效；" if has_sell_shape else ""
    return prefix + "未触发建仓候选：" + "；".join(legacy_buy_missing_conditions(row, prev, params))


def legacy_buy_missing_conditions(
    row: pd.Series,
    prev: pd.Series,
    params: Mapping[str, Any],
) -> list[str]:
    threshold = float(params["buy_volume_ratio_min"])
    ma5_cross_ma10 = (
        pd.notna(prev.get("ma5"))
        and pd.notna(prev.get("ma10"))
        and pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and prev["ma5"] <= prev["ma10"]
        and row["ma5"] > row["ma10"]
    )
    macd_improving = (
        pd.notna(row.get("macd_hist"))
        and pd.notna(prev.get("macd_hist"))
        and row["macd_hist"] > prev["macd_hist"]
    )
    volume_ok = pd.notna(row.get("vol_ratio60")) and row["vol_ratio60"] >= threshold
    dif_cross_dea = (
        pd.notna(prev.get("dif"))
        and pd.notna(prev.get("dea"))
        and pd.notna(row.get("dif"))
        and pd.notna(row.get("dea"))
        and prev["dif"] <= prev["dea"]
        and row["dif"] > row["dea"]
    )
    ma5_above_ma10 = pd.notna(row.get("ma5")) and pd.notna(row.get("ma10")) and row["ma5"] > row["ma10"]
    close_above_ma20 = (
        pd.notna(row.get("收盘价"))
        and pd.notna(row.get("ma20"))
        and row["收盘价"] > row["ma20"]
    )
    rule_a_missing: list[str] = []
    if not ma5_cross_ma10:
        rule_a_missing.append("MA5今日未上穿MA10")
    if not macd_improving:
        rule_a_missing.append("MACD柱未较昨日改善")
    if not volume_ok:
        rule_a_missing.append(f"量能倍数未达到{threshold:g}")
    rule_b_missing: list[str] = []
    if not dif_cross_dea:
        rule_b_missing.append("DIF今日未上穿DEA")
    if not ma5_above_ma10:
        rule_b_missing.append("MA5未高于MA10")
    if not close_above_ma20:
        rule_b_missing.append("收盘价未高于MA20")
    if not volume_ok:
        rule_b_missing.append(f"量能倍数未达到{threshold:g}")
    return [
        f"规则A缺{'、'.join(rule_a_missing)}",
        f"规则B缺{'、'.join(rule_b_missing)}",
    ]


def legacy_sell_missing_conditions(
    row: pd.Series,
    params: Mapping[str, Any],
) -> list[str]:
    ma10_threshold = float(params["sell_ma10_volume_ratio_min"])
    ma5_threshold = float(params["sell_ma5_volume_ratio_min"])
    close_below_ma10 = pd.notna(row.get("收盘价")) and pd.notna(row.get("ma10")) and row["收盘价"] < row["ma10"]
    close_below_ma5 = pd.notna(row.get("收盘价")) and pd.notna(row.get("ma5")) and row["收盘价"] < row["ma5"]
    volume = row.get("vol_ratio60")
    ma10_volume_ok = pd.notna(volume) and volume >= ma10_threshold
    ma5_volume_ok = pd.notna(volume) and volume >= ma5_threshold
    missing: list[str] = []
    if not (close_below_ma10 and ma10_volume_ok):
        detail: list[str] = []
        if not close_below_ma10:
            detail.append("收盘未跌破MA10")
        if not ma10_volume_ok:
            detail.append(f"量能倍数未达到{ma10_threshold:g}")
        missing.append("MA10平仓条件未满足：" + "、".join(detail))
    if not (close_below_ma5 and ma5_volume_ok):
        detail = []
        if not close_below_ma5:
            detail.append("收盘未跌破MA5")
        if not ma5_volume_ok:
            detail.append(f"量能倍数未达到{ma5_threshold:g}")
        missing.append("MA5平仓条件未满足：" + "、".join(detail))
    return missing


def legacy_signal_type(buy_signal: bool, sell_signal: bool, watch_type: str) -> str:
    if buy_signal:
        return "buy_candidate"
    if sell_signal:
        return "sell_alert"
    if watch_type:
        return "watch"
    return "neutral"


def legacy_action_text(signal_type: str) -> str:
    return {
        "buy_candidate": "模型触发建仓候选",
        "sell_alert": "模型触发平仓提示",
        "watch": "进入观察池",
        "neutral": "未触发",
        "data_unavailable": "数据不足，无法判断",
    }.get(signal_type, "未触发")


def legacy_metrics(row: pd.Series) -> dict[str, Any]:
    return {
        "close": _safe_float(row.get("收盘价")),
        "ma5": _safe_float(row.get("ma5")),
        "ma10": _safe_float(row.get("ma10")),
        "ma20": _safe_float(row.get("ma20")),
        "ma60": _safe_float(row.get("ma60")),
        "vol_ratio60": _safe_float(row.get("vol_ratio60")),
        "volume_ratio_60": _safe_float(row.get("vol_ratio60")),
        "macd_hist": _safe_float(row.get("macd_hist")),
        "dif": _safe_float(row.get("dif")),
        "dea": _safe_float(row.get("dea")),
    }


def legacy_rule_hits(
    buy_reasons: list[str],
    sell_reasons: list[str],
    watch_type: str,
    missing_condition: str,
) -> str:
    hits = buy_reasons + sell_reasons
    if watch_type:
        hits.append(watch_type)
    if missing_condition:
        hits.append(f"未满足：{missing_condition}")
    return "；".join(hits)


def legacy_risk_notes(
    row: pd.Series,
    prev: pd.Series,
    signal_type: str,
    watch_type: str,
) -> str:
    notes: list[str] = []
    ma5_cross_ma10 = (
        pd.notna(prev.get("ma5"))
        and pd.notna(prev.get("ma10"))
        and pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and prev["ma5"] <= prev["ma10"]
        and row["ma5"] > row["ma10"]
    )
    macd_improving = (
        pd.notna(row.get("macd_hist"))
        and pd.notna(prev.get("macd_hist"))
        and row["macd_hist"] > prev["macd_hist"]
    )
    if ma5_cross_ma10 and not macd_improving:
        notes.append("均线触发但MACD未确认")
    if watch_type:
        notes.append("关注池不等于建仓候选，需等待缺失条件确认")
    if signal_type == "neutral":
        notes.append("未触发完整建仓或平仓规则")
    return "；".join(notes)


def legacy_confidence(data_quality: str, signal_type: str, row: pd.Series) -> str:
    if data_quality == "ERROR":
        return "low"
    if data_quality == "WARN" or pd.isna(row.get("vol_ratio60")):
        return "low"
    if signal_type in {"watch", "neutral"}:
        return "medium"
    return "high"


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _profile(params: Mapping[str, Any]) -> Mapping[str, Any]:
    if "etf" not in params:
        return params
    etf = params["etf"]
    if isinstance(etf, Mapping) and "strategy_profiles" in etf:
        profiles = etf.get("strategy_profiles", {})
        if isinstance(profiles, Mapping) and isinstance(profiles.get("legacy_v1"), Mapping):
            return profiles["legacy_v1"]
    return etf
