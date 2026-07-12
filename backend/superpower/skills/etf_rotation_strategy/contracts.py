from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd


class ETFStrategyError(RuntimeError):
    """Base class for ETF strategy failures."""


class ETFStrategyRuntimeError(ETFStrategyError):
    """Raised when a registered strategy fails during deterministic evaluation."""


class MediumStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    DO_NOT_PARTICIPATE = "do_not_participate"
    TREND_NOT_CONFIRMED = "trend_not_confirmed"
    TREND_CONFIRMED = "trend_confirmed"
    DATA_UNAVAILABLE = "data_unavailable"


class ShortEntryStatus(StrEnum):
    NO_ENTRY = "no_entry"
    CLOSE_WATCH = "close_watch"
    OVERHEATED_DO_NOT_CHASE = "overheated_do_not_chase"
    WAITING_CONFIRMATION = "waiting_confirmation"
    WAITING_PULLBACK = "waiting_pullback"
    CAN_ENTER = "can_enter"
    DATA_UNAVAILABLE = "data_unavailable"
    LEGACY_BUY = "legacy_buy"
    LEGACY_WATCH = "legacy_watch"
    LEGACY_NEUTRAL = "legacy_neutral"


@dataclass(frozen=True)
class ETFHistory:
    code: str
    name: str
    rows: pd.DataFrame
    as_of: pd.Timestamp

    def __post_init__(self) -> None:
        if "date" not in self.rows.columns:
            raise ValueError("ETFHistory requires a date column")
        dates = pd.to_datetime(self.rows["date"], errors="coerce")
        if dates.notna().any() and dates.max() > self.as_of:
            raise ValueError("ETFHistory contains rows after as_of")


@dataclass(frozen=True)
class ETFPositionState:
    is_holding: bool


@dataclass(frozen=True)
class ETFDecision:
    as_of: pd.Timestamp
    code: str
    name: str
    strategy_id: str
    strategy_version: str
    medium_status: MediumStatus
    short_entry_status: ShortEntryStatus
    exit_status: str
    eligible: bool
    buy_candidate: bool
    watch_candidate: bool
    sell_alert: bool
    score: float
    medium_reason: str = ""
    short_entry_reason: str = ""
    metrics: Mapping[str, Any] = field(default_factory=dict)
    rule_hits: Sequence[str] = ()
    missing_conditions: Sequence[str] = ()
    risk_notes: Sequence[str] = ()
    compatibility_fields: Mapping[str, Any] = field(default_factory=dict)
    confidence: str = "low"
    data_quality: str = "ERROR"

    @classmethod
    def unavailable(
        cls,
        *,
        as_of: pd.Timestamp,
        code: str,
        name: str,
        strategy_id: str,
        strategy_version: str,
        reason: str,
    ) -> "ETFDecision":
        return cls(
            as_of=as_of,
            code=code,
            name=name,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            medium_status=MediumStatus.DATA_UNAVAILABLE,
            short_entry_status=ShortEntryStatus.DATA_UNAVAILABLE,
            exit_status="not_triggered",
            eligible=False,
            buy_candidate=False,
            watch_candidate=False,
            sell_alert=False,
            score=0.0,
            medium_reason=reason,
            short_entry_reason=reason,
            risk_notes=(reason,),
            data_quality="ERROR",
        )


@dataclass(frozen=True)
class ETFStrategyMetadata:
    strategy_id: str
    display_name: str
    version: str
    default_params: Mapping[str, Any]
    parameter_schema: Mapping[str, Any]


class ETFStrategy(Protocol):
    strategy_id: str
    version: str

    def evaluate(
        self,
        history: ETFHistory,
        position: ETFPositionState,
        params: Mapping[str, Any],
    ) -> ETFDecision:
        raise NotImplementedError

    def evaluate_history(
        self,
        history: ETFHistory,
        params: Mapping[str, Any],
    ) -> list[ETFDecision]:
        raise NotImplementedError
