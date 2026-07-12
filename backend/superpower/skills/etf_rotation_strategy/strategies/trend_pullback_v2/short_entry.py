from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

from ...contracts import MediumStatus, ShortEntryStatus
from .medium_trend import MediumTrendResult


@dataclass(frozen=True)
class SetupState:
    date: pd.Timestamp
    session_number: int
    close: float
    high: float
    volume: float
    ma5: float
    ma10: float
    ma20: float


@dataclass(frozen=True)
class PullbackEvidence:
    confirmed: bool
    structure_broken: bool
    support: float


@dataclass(frozen=True)
class ShortEntryResult:
    status: ShortEntryStatus
    reason: str
    setup_date: pd.Timestamp | None
    setup_age: int | None
    cooldown_remaining: int
    weekly_macd_confirmation_check: str
    ma20_flat_check: str
    rule_hits: tuple[str, ...] = ()
    missing_conditions: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()
    entry_route: str = ""


def evaluate_short_entry_history(
    rows: pd.DataFrame,
    medium_results: Sequence[MediumTrendResult],
    profile: Mapping[str, Any],
    *,
    trading_session_numbers: Sequence[int],
) -> list[ShortEntryResult]:
    if len(rows) != len(medium_results) or len(rows) != len(trading_session_numbers):
        raise ValueError("rows, medium_results and trading_session_numbers must align")
    results: list[ShortEntryResult] = []
    active_setup: SetupState | None = None
    cooldown_until = -1
    previous_medium = MediumStatus.DATA_UNAVAILABLE

    for index in range(len(rows)):
        row = rows.iloc[index]
        previous = rows.iloc[index - 1] if index > 0 else None
        medium = medium_results[index]
        session_number = int(trading_session_numbers[index])
        weekly_check = weekly_confirmation_check(row.get("weekly_macd_state"))
        ma20_check = ma20_flat_check(row.get("ma20_slope_state"))

        if medium.status is MediumStatus.DATA_UNAVAILABLE:
            active_setup = None
            result = _result(
                ShortEntryStatus.DATA_UNAVAILABLE,
                "短期入场所需的中期趋势数据不足",
                None,
                session_number,
                cooldown_until,
                weekly_check,
                ma20_check,
                missing_conditions=medium.missing_conditions,
            )
            results.append(result)
            previous_medium = medium.status
            continue

        overheated = (
            previous is not None
            and overheat_inputs_available(row, previous)
            and calculate_overheat(row, previous, profile)
        )

        if medium.status in {
            MediumStatus.DO_NOT_PARTICIPATE,
            MediumStatus.TREND_NOT_CONFIRMED,
        }:
            active_setup = None
            if previous is not None and close_watch_trigger(row, previous):
                result = _result(
                    ShortEntryStatus.CLOSE_WATCH,
                    "密切观察：MA5已在MA10上方，日MACD绿柱缩短或转红。"
                    "中期确认项：1）周MACD是否绿柱缩短或红柱加长；"
                    "2）MA20是否走平。",
                    None,
                    session_number,
                    cooldown_until,
                    weekly_check,
                    ma20_check,
                    rule_hits=("ma5_above_ma10", "daily_macd_improving_or_red"),
                    risk_notes=(
                        ("overheat_detected_but_medium_not_confirmed",)
                        if overheated
                        else ()
                    ),
                )
            else:
                result = _result(
                    ShortEntryStatus.NO_ENTRY,
                    "中期趋势尚未确认，短期条件不足",
                    None,
                    session_number,
                    cooldown_until,
                    weekly_check,
                    ma20_check,
                    risk_notes=(
                        ("overheat_detected_but_medium_not_confirmed",)
                        if overheated
                        else ()
                    ),
                )
            results.append(result)
            previous_medium = medium.status
            continue

        missing = _confirmed_required_missing(row, previous)
        if missing:
            result = _result(
                ShortEntryStatus.DATA_UNAVAILABLE,
                "短期确认所需数据不足",
                active_setup,
                session_number,
                cooldown_until,
                weekly_check,
                ma20_check,
                missing_conditions=missing,
            )
            results.append(result)
            previous_medium = medium.status
            continue

        medium_just_confirmed = (
            index > 0
            and previous_medium is not MediumStatus.TREND_CONFIRMED
            and medium.status is MediumStatus.TREND_CONFIRMED
        )
        if active_setup is None and (
            medium_just_confirmed or medium.ma5_crossed_ma20_today
        ):
            active_setup = setup_from_row(row, session_number)

        if active_setup is not None:
            age = session_number - active_setup.session_number
            if age > int(profile["pullback_max_age"]):
                active_setup = None

        if overheated:
            cooldown_until = session_number + int(profile["overheat_cooldown_days"])
            result = _result(
                ShortEntryStatus.OVERHEATED_DO_NOT_CHASE,
                "趋势已确认，但短期涨幅、阳线实体、量能和MA5偏离同时过热，不追涨",
                active_setup,
                session_number,
                cooldown_until,
                weekly_check,
                ma20_check,
                rule_hits=("overheated",),
                risk_notes=("overheated",),
            )
        elif session_number <= cooldown_until:
            result = _result(
                ShortEntryStatus.WAITING_PULLBACK,
                "仍在过热冷却期，等待价格回踩和承接确认",
                active_setup,
                session_number,
                cooldown_until,
                weekly_check,
                ma20_check,
                risk_notes=("cooldown_blocks_entry",),
            )
        elif active_setup is None:
            result = _result(
                ShortEntryStatus.NO_ENTRY,
                "中期趋势已确认，但当前没有有效的短期入场结构",
                None,
                session_number,
                cooldown_until,
                weekly_check,
                ma20_check,
            )
        elif breakout_confirmed(row, active_setup, profile):
            result = _result(
                ShortEntryStatus.CAN_ENTER,
                "突破设置日高点，日MACD为红柱且未进入过热区",
                active_setup,
                session_number,
                cooldown_until,
                weekly_check,
                ma20_check,
                rule_hits=("breakout_confirmation",),
                entry_route="breakout_confirmation",
            )
        else:
            pullback = pullback_evidence(row, active_setup, profile)
            if pullback.structure_broken:
                active_setup = None
                result = _result(
                    ShortEntryStatus.NO_ENTRY,
                    "回踩跌破支撑且收盘未能收回，原入场结构失效",
                    None,
                    session_number,
                    cooldown_until,
                    weekly_check,
                    ma20_check,
                    risk_notes=("support_broken",),
                )
            elif pullback.confirmed:
                result = _result(
                    ShortEntryStatus.CAN_ENTER,
                    "缩量回踩MA5/MA10支撑并收回，日MACD保持红柱",
                    active_setup,
                    session_number,
                    cooldown_until,
                    weekly_check,
                    ma20_check,
                    rule_hits=("pullback_confirmation",),
                    entry_route="pullback_confirmation",
                )
            else:
                age = session_number - active_setup.session_number
                status = (
                    ShortEntryStatus.WAITING_CONFIRMATION
                    if age <= int(profile["confirmation_window"])
                    else ShortEntryStatus.WAITING_PULLBACK
                )
                reason = (
                    "处于设置后的确认窗口，等待后续突破设置日高点"
                    if status is ShortEntryStatus.WAITING_CONFIRMATION
                    else "突破确认窗口已结束，等待缩量回踩承接"
                )
                result = _result(
                    status,
                    reason,
                    active_setup,
                    session_number,
                    cooldown_until,
                    weekly_check,
                    ma20_check,
                    missing_conditions=("breakout_or_pullback_confirmation",),
                )
        results.append(result)
        previous_medium = medium.status
    return results


def close_watch_trigger(row: pd.Series, previous: pd.Series) -> bool:
    ma_ready = (
        pd.notna(row.get("ma5"))
        and pd.notna(row.get("ma10"))
        and row["ma5"] > row["ma10"]
    )
    green_narrowing = (
        pd.notna(previous.get("macd_hist"))
        and pd.notna(row.get("macd_hist"))
        and row["macd_hist"] < 0
        and row["macd_hist"] > previous["macd_hist"]
    )
    green_to_red = (
        pd.notna(previous.get("macd_hist"))
        and pd.notna(row.get("macd_hist"))
        and previous["macd_hist"] <= 0
        and row["macd_hist"] > 0
    )
    return bool(ma_ready and (green_narrowing or green_to_red))


def calculate_overheat(
    row: pd.Series,
    previous: pd.Series,
    profile: Mapping[str, Any],
) -> bool:
    daily_return = row["收盘价"] / previous["收盘价"] - 1
    body_ratio = max(row["收盘价"] - row["开盘价"], 0.0) / max(
        row["最高价"] - row["最低价"],
        1e-12,
    )
    ma5_distance = row["收盘价"] / row["ma5"] - 1
    return bool(
        daily_return >= float(profile["overheat_daily_return_min"])
        and body_ratio >= float(profile["overheat_body_ratio_min"])
        and row["vol_ratio60"] >= float(profile["overheat_volume_ratio_min"])
        and ma5_distance >= float(profile["overheat_ma5_distance_min"])
    )


def overheat_inputs_available(row: pd.Series, previous: pd.Series) -> bool:
    required_row = (
        "开盘价",
        "最高价",
        "最低价",
        "收盘价",
        "ma5",
        "vol_ratio60",
    )
    return bool(
        all(pd.notna(row.get(key)) for key in required_row)
        and pd.notna(previous.get("收盘价"))
        and previous["收盘价"] != 0
        and row["ma5"] != 0
    )


def setup_from_row(row: pd.Series, session_number: int) -> SetupState:
    return SetupState(
        date=pd.Timestamp(row["date"]),
        session_number=session_number,
        close=float(row["收盘价"]),
        high=float(row["最高价"]),
        volume=float(row["成交量（万股）"]),
        ma5=float(row["ma5"]),
        ma10=float(row["ma10"]),
        ma20=float(row["ma20"]),
    )


def breakout_confirmed(
    row: pd.Series,
    setup: SetupState,
    profile: Mapping[str, Any],
) -> bool:
    ma5_distance = row["收盘价"] / row["ma5"] - 1
    return bool(
        pd.Timestamp(row["date"]) > setup.date
        and row["收盘价"] > setup.high
        and row["macd_hist"] > 0
        and ma5_distance < float(profile["overheat_ma5_distance_min"])
    )


def pullback_evidence(
    row: pd.Series,
    setup: SetupState,
    profile: Mapping[str, Any],
) -> PullbackEvidence:
    support_candidates = [float(row["ma5"]), float(row["ma10"])]
    if row["收盘价"] >= setup.high:
        support_candidates.append(setup.high)
    support = max(support_candidates)
    tolerance = float(profile["pullback_support_tolerance"])
    max_break = float(profile["pullback_max_intraday_break"])
    touches = row["最低价"] <= support * (1 + tolerance)
    structure_intact = row["最低价"] >= support * (1 - max_break)
    holds = row["收盘价"] >= support
    volume_contracts = row["成交量（万股）"] < setup.volume
    structure_broken = row["最低价"] < support * (1 - max_break) and not holds
    confirmed = bool(
        touches
        and structure_intact
        and holds
        and volume_contracts
        and row["macd_hist"] > 0
    )
    return PullbackEvidence(
        confirmed=confirmed,
        structure_broken=bool(structure_broken),
        support=support,
    )


def weekly_confirmation_check(value: Any) -> str:
    return {
        "green_narrowing": "favorable",
        "red_strengthening": "favorable",
        "red_weakening": "caution",
        "green_widening": "unfavorable",
        "neutral_zero": "not_confirmed",
    }.get(str(value), "unavailable")


def ma20_flat_check(value: Any) -> str:
    return {
        "flat": "met",
        "up": "positive",
        "down": "not_met",
    }.get(str(value), "unavailable")


def _confirmed_required_missing(
    row: pd.Series,
    previous: pd.Series | None,
) -> tuple[str, ...]:
    required = (
        "date",
        "开盘价",
        "最高价",
        "最低价",
        "收盘价",
        "成交量（万股）",
        "vol_ratio60",
        "ma5",
        "ma10",
        "ma20",
        "macd_hist",
    )
    missing = [key for key in required if pd.isna(row.get(key))]
    if previous is None or pd.isna(previous.get("收盘价")):
        missing.append("previous_close")
    return tuple(missing)


def _result(
    status: ShortEntryStatus,
    reason: str,
    setup: SetupState | None,
    session_number: int,
    cooldown_until: int,
    weekly_check: str,
    ma20_check: str,
    *,
    rule_hits: tuple[str, ...] = (),
    missing_conditions: tuple[str, ...] = (),
    risk_notes: tuple[str, ...] = (),
    entry_route: str = "",
) -> ShortEntryResult:
    return ShortEntryResult(
        status=status,
        reason=reason,
        setup_date=setup.date if setup else None,
        setup_age=session_number - setup.session_number if setup else None,
        cooldown_remaining=max(cooldown_until - session_number, 0),
        weekly_macd_confirmation_check=weekly_check,
        ma20_flat_check=ma20_check,
        rule_hits=rule_hits,
        missing_conditions=missing_conditions,
        risk_notes=risk_notes,
        entry_route=entry_route,
    )
