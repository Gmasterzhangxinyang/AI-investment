# ETF Strategy Plugin v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a configurable ETF-only strategy plugin system that preserves the current legacy strategy, adds the approved medium-trend plus short-entry trend-pullback strategy, shows both states together, and supports descriptive historical diagnostics without changing TL or convertible-bond behavior.

**Architecture:** Keep ETFAgent and the outer etf-rotation-strategy Skill stable. Move ETF policy behind an explicit registry and typed ETFDecision contract; run only the configured active strategy for live projections, while diagnostic strategies run independently and cannot change live signals. Generate each refresh into a staging bundle, audit it, and promote it under rollback protection so a workflow, audit, or database failure restores the previous published bundle.

**Tech Stack:** Python 3.12+, pandas, numpy, pytest, existing Agent/Skill runtime, JSON configuration API, vanilla JavaScript, Node built-in test runner, openpyxl/reportlab output pipeline.

## Global Constraints

- Scope is ETF only; TL and convertible-bond calculations, outputs, reports, and UI behavior must remain unchanged.
- This system is a 5–20 trading-day trend and entry-state assistant, not a next-day predictor and not a promise of absolute return.
- Preserve latest_etf_signals(etf, positions, params) and its exact five-item return order for one compatibility cycle.
- Preserve etf_signal_table, etf_buy_candidates, etf_sell_alerts, etf_watchlist, and etf_detail_history.
- Missing active_strategy means legacy_v1; an explicitly unknown or invalid strategy fails closed and never silently falls back.
- Only active_strategy may create live buy, watch, or sell projections; diagnostic_strategies is descriptive only.
- trend_pullback_v2 requires at least 180 valid ETF daily rows. Missing data produces data_unavailable, not legacy fallback.
- Weekly bars use W-FRI. The official weekly MACD uses the latest non-empty completed week strictly before the as-of week; the current week is preview-only.
- A zero weekly MACD histogram is neutral_zero and does not confirm the medium trend.
- Every historical evaluation receives an explicit as_of and rejects rows later than as_of.
- Setup age is zero on setup day. A later setup event does not replace a still-valid setup.
- Repeated overheat restarts the three-session cooldown; cooldown blocks every entry route.
- A pullback that breaks support by more than 1% and closes below support invalidates the setup. Missing volume or MACD confirmation remains waiting_pullback.
- Holding ETFs with 61–179 rows may still receive the legacy exit check, but their v2 medium and short states are data_unavailable and they cannot be bought or watched.
- If a holding row simultaneously has entry evidence and a legacy exit, public sell_alert takes precedence.
- legacy_v1 reports medium_status=not_applicable; its current signal maps to short_entry_status without altering legacy projections.
- Historical event rows are recorded only on transitions into close_watch, trend_confirmed, overheated_do_not_chase, waiting_pullback, and can_enter. waiting_confirmation is not an event.
- Incomplete 5/10/20-day horizons remain as rows with null outcomes. Maximum adverse excursion is stored as a negative return.
- false_reversal_10d means no entry state appears in the next ten trading rows and the ten-day forward close return is less than or equal to zero.
- State flip frequency is transitions divided by max(valid_rows - 1, 1).
- Any plugin exception or database-ingestion failure fails the refresh and retains the previously published latest bundle. Audit keeps the current contract: it blocks publication only with --strict-audit; a non-strict FAIL is published with explicit partial-success warnings.
- Never copy, print, stash, or commit the current local model configuration secret. Revoke/rotate it before implementation.
- The dirty files in the main checkout belong to the user. Start implementation from committed HEAD in an isolated worktree and integrate overlapping frontend/config changes explicitly.
- Default rollout remains legacy_v1 until comparison diagnostics and acceptance gates pass. Switching to trend_pullback_v2 is a separate reviewed configuration change.

---

## Execution preflight

1. Revoke and rotate the exposed local API credential without printing it.
2. From /Users/bobby/Desktop/ai money/ai_research_superpower, verify the plan commit is the current HEAD, capture that immutable commit ID, and create the isolated implementation worktree from the captured ID:

~~~bash
test "$(git log -1 --format=%s)" = "docs: add ETF strategy plugin implementation plan"
BASE_SHA="$(git rev-parse HEAD)"
git worktree add -b feat/etf-strategy-plugin-v2 "/Users/bobby/Desktop/ai money/ai_research_superpower-etf-v2" "$BASE_SHA"
git -C "/Users/bobby/Desktop/ai money/ai_research_superpower-etf-v2" rev-parse HEAD
~~~

The final command must print the same value as BASE_SHA. Record it in the implementation task notes.
3. Run all remaining commands from /Users/bobby/Desktop/ai money/ai_research_superpower-etf-v2.
4. Do not use git stash -u in the dirty main checkout.

## File map

### New backend files

- backend/superpower/skills/etf_rotation_strategy/contracts.py — immutable plugin input, decision, metadata, state enums, and errors.
- backend/superpower/skills/etf_rotation_strategy/config.py — legacy normalization, profile merge/validation, and deterministic configuration hash.
- backend/superpower/skills/etf_rotation_strategy/registry.py — explicit registered-strategy constructors and frontend-safe metadata.
- backend/superpower/skills/etf_rotation_strategy/compatibility.py — canonical decision to existing DataFrame projections.
- backend/superpower/skills/etf_rotation_strategy/strategies/legacy_v1.py — frozen current entry, watch, exit, and ranking policy.
- backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/defaults.py — versioned defaults and schema.
- backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/medium_trend.py — medium trend policy only.
- backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/short_entry.py — causal setup, cooldown, breakout, and pullback state machine.
- backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/strategy.py — composition with legacy exit/ranking.
- backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/diagnostics.py — event transitions and forward outcome metrics.
- backend/superpower/skills/technical_indicators/etf.py — ETF-only MA20 slope and causal completed-week MACD.
- backend/superpower/tools/report_date.py — common report-date selection used by generation and audit.
- backend/superpower/runtime/publication.py — staging, snapshot, validation, and atomic latest-bundle promotion.
- backend/superpower/cli/migrate_publication.py — one-time, server-stopped conversion of a legacy latest directory into the versioned-pointer layout.
- frontend/assets/strategy-config.js — pure ETF strategy form state, deep merge, validation display, and config-hash comparison.

### New test files

- tests/test_report_date.py
- tests/test_etf_legacy_characterization.py
- tests/test_etf_strategy_contract.py
- tests/test_etf_config.py
- tests/test_etf_indicators.py
- tests/test_etf_medium_trend.py
- tests/test_etf_short_entry.py
- tests/test_etf_trend_pullback_strategy.py
- tests/test_etf_historical_diagnostics.py
- tests/test_atomic_publication.py
- tests/test_etf_strategy_api.py
- tests/test_etf_db_payload.py
- tests/frontend/strategy-config.test.js

### Existing files modified

- pyproject.toml — add the test dependency group.
- configs/strategy_params.json — add compatible ETF plugin keys while retaining the user's current thresholds.
- backend/superpower/skills/etf_rotation_strategy/handler.py — thin adapter, stable wrapper, and artifact publication.
- backend/superpower/skills/technical_indicators/handler.py — call ETF-specific enrichment only for ETF groups.
- backend/superpower/agents/indicator_agent.py — declare the additive ETF indicator evidence while leaving TL behavior unchanged.
- backend/superpower/skills/strategy_backtest/handler.py — stop importing private ETF helpers; keep the legacy P&L diagnostic separate.
- backend/superpower/agents/config_agent.py — normalize and snapshot ETF configuration at run start.
- backend/superpower/skills/source_archive/handler.py — archive only the normalized ETF strategy snapshot and hash, never model credentials.
- backend/superpower/agents/report_agent.py — require strategy identity and diagnostics artifacts.
- backend/superpower/skills/report_generation/handler.py — add strategy identity, state fields, and historical-diagnostics sheets/JSON.
- backend/superpower/cli/run_daily.py — stage, audit against the run snapshot, ingest, then atomically publish.
- backend/superpower/audit/latest.py — recompute with the exact run configuration and verify identity/hash.
- backend/superpower/server/app.py — registry metadata, deep-merge save, validation, and refresh-state API contract.
- backend/superpower/db/ingest.py and backend/superpower/db/repositories.py — persist and retrieve canonical ETF fields in payload_json without an ETF table migration.
- backend/superpower/chat/tools.py, backend/superpower/chat/orchestrator.py, backend/superpower/chat/rulebook.py — explain active strategy plus medium/short evidence.
- backend/superpower/skills/research_explanation/handler.py and backend/superpower/skills/ai_research_committee/handler.py — consume canonical evidence without changing deterministic signals.
- backend/superpower/tools/pdf_report.py — render the two ETF state dimensions and strategy identity.
- frontend/index.html, frontend/assets/app.js, frontend/assets/styles.css — selector, profile editor, stale-results notice, and two-state columns.
- backend/superpower/skills/etf_rotation_strategy/SKILL.md and README.md — document user and developer workflows.
- backend/superpower/skills/technical_indicators/SKILL.md, backend/superpower/skills/strategy_backtest/SKILL.md, and backend/superpower/skills/report_generation/SKILL.md — document causal weekly indicators, diagnostic naming, and additive output contracts.
- docs/ETF_MODEL.md, docs/STRATEGY_PARAMETERS.md, docs/DASHBOARD_SCHEMA.md, docs/FRONTEND_GUIDE.md, docs/CLIENT_PRODUCT_GUIDE.md, and docs/REPORTING_POLICY.md — update user-facing ETF behavior and compatibility contracts.

### Files explicitly not changed

- backend/superpower/skills/tl_timing_strategy/handler.py
- backend/superpower/skills/convertible_bond_ranking/handler.py
- backend/superpower/db/schema.sql

---

### Task 1: Re-establish a trustworthy test and audit baseline

**Files:**
- Create: backend/superpower/tools/report_date.py
- Create: tests/test_report_date.py
- Modify: pyproject.toml
- Modify: backend/superpower/skills/report_generation/handler.py
- Modify: backend/superpower/audit/latest.py
- Test: tests/test_run_daily_audit.py

**Interfaces:**
- Consumes: DataFrames containing an optional date column.
- Produces: latest_market_date(*frames: pd.DataFrame) -> pd.Timestamp | None and report_date_text(*frames: pd.DataFrame) -> str.

- [ ] **Step 1: Add the test environment and write the failing shared-date tests**

Add this optional dependency group to pyproject.toml:

~~~toml
[project.optional-dependencies]
test = ["pytest>=8.2,<9"]
~~~

Create tests/test_report_date.py:

~~~python
from datetime import datetime

import pandas as pd

from superpower.tools.report_date import latest_market_date, report_date_text


def frame(*dates: str) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(list(dates))})


def test_latest_market_date_includes_convertible_bond_frame() -> None:
    result = latest_market_date(
        frame("2026-07-03"),
        frame("2026-07-03"),
        frame("2026-07-06"),
    )
    assert result == pd.Timestamp("2026-07-06")
    assert report_date_text(frame("2026-07-03"), frame("2026-07-06")) == "20260706"


def test_latest_market_date_ignores_empty_and_invalid_frames() -> None:
    assert latest_market_date(pd.DataFrame(), pd.DataFrame({"date": ["bad"]})) is None
    assert report_date_text(
        pd.DataFrame(),
        now=datetime(2026, 7, 12, 9, 0),
    ) == "20260712"
~~~

- [ ] **Step 2: Bootstrap the isolated environment and verify the tests fail for the missing module**

~~~bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest tests/test_report_date.py -q
~~~

Expected: collection fails because superpower.tools.report_date does not exist.

- [ ] **Step 3: Implement one date source and use it in both generation and audit**

Create backend/superpower/tools/report_date.py:

~~~python
from __future__ import annotations

from datetime import datetime

import pandas as pd


def latest_market_date(*frames: pd.DataFrame) -> pd.Timestamp | None:
    candidates: list[pd.Timestamp] = []
    for frame in frames:
        if frame.empty or "date" not in frame.columns:
            continue
        value = pd.to_datetime(frame["date"], errors="coerce").max()
        if pd.notna(value):
            candidates.append(pd.Timestamp(value).normalize())
    return max(candidates) if candidates else None


def report_date_text(*frames: pd.DataFrame, now: datetime | None = None) -> str:
    value = latest_market_date(*frames)
    if value is not None:
        return value.strftime("%Y%m%d")
    return (now or datetime.now()).strftime("%Y%m%d")
~~~

Replace report_generation._report_date with a call using etf_indicators, tl_indicators, and cb_ranked. Replace audit/latest.py's two-frame max with the same helper and include cb_ranked. This makes audit recompute the same date rule as the report.

- [ ] **Step 4: Run the focused and existing audit tests**

~~~bash
.venv/bin/python -m pytest tests/test_report_date.py tests/test_run_daily_audit.py tests/test_dashboard_schema.py -q
~~~

Expected: all selected tests pass and the 20260703 versus 20260706 mismatch is covered by a regression test.

- [ ] **Step 5: Commit the baseline fix**

~~~bash
git add pyproject.toml backend/superpower/tools/report_date.py backend/superpower/skills/report_generation/handler.py backend/superpower/audit/latest.py tests/test_report_date.py tests/test_run_daily_audit.py
git commit -m "fix: align report and audit market dates"
~~~

---

### Task 2: Freeze every legacy ETF behavior before extraction

**Files:**
- Create: tests/test_etf_legacy_characterization.py
- Modify: tests/test_etf_signal_output.py
- Test: backend/superpower/skills/etf_rotation_strategy/handler.py

**Interfaces:**
- Consumes: current latest_etf_signals(etf, positions, params).
- Produces: a characterization suite that fixes both buy routes, three watch routes, two exits, holding gates, short-history behavior, score, sort order, and detail-history shape.

- [ ] **Step 1: Write a deterministic row builder and the first failing coverage assertions**

Create tests/test_etf_legacy_characterization.py with a 61-row baseline and explicit last-two-row overrides:

~~~python
from __future__ import annotations

import pandas as pd

from superpower.skills.etf_rotation_strategy.handler import latest_etf_signals, score_etf


PARAMS = {
    "etf": {
        "buy_volume_ratio_min": 1.1,
        "sell_ma10_volume_ratio_min": 1.2,
        "sell_ma5_volume_ratio_min": 1.5,
        "score_weights": {
            "trend": 0.35,
            "macd": 0.25,
            "volume": 0.25,
            "share_change": 0.15,
        },
    }
}


def history(code: str = "510001", name: str = "样例ETF") -> pd.DataFrame:
    dates = pd.bdate_range("2026-03-02", periods=61)
    rows = []
    for index, date in enumerate(dates):
        rows.append(
            {
                "date": date,
                "code": code,
                "name": name,
                "开盘价": 10.0,
                "最高价": 10.1,
                "最低价": 9.9,
                "收盘价": 10.0,
                "成交量（万股）": 100.0,
                "ma5": 10.0,
                "ma10": 10.0,
                "ma20": 9.8,
                "ma60": 9.5,
                "vol_ratio60": 1.0,
                "dif": -0.02,
                "dea": -0.01,
                "macd_hist": -0.02 + index / 10000,
                "kdj_j": 50.0,
                "份额变化（亿份）": 0.0,
            }
        )
    return pd.DataFrame(rows)


def positions(*codes: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"asset_type": "ETF", "status": "holding", "code": code} for code in codes]
    )


def test_legacy_buy_route_a_and_holding_gate() -> None:
    data = history()
    data.loc[59, ["ma5", "ma10", "macd_hist"]] = [9.9, 10.0, -0.02]
    data.loc[60, ["ma5", "ma10", "macd_hist", "vol_ratio60"]] = [10.1, 10.0, -0.01, 1.1]
    all_rows, buys, sells, watch, details = latest_etf_signals(data, positions(), PARAMS)
    assert all_rows.iloc[0]["signal_type"] == "buy_candidate"
    assert list(buys["code"]) == ["510001"]
    assert sells.empty and watch.empty and len(details) == 8

    _, holding_buys, _, holding_watch, _ = latest_etf_signals(data, positions("510001"), PARAMS)
    assert holding_buys.empty
    assert holding_watch.empty
~~~

- [ ] **Step 2: Run the new test, then add exact cases until every current route is characterized**

~~~bash
.venv/bin/python -m pytest tests/test_etf_legacy_characterization.py -q
~~~

Expected initially: the first test passes. Add one concrete test per row in this matrix, using the history and positions builders above:

| Test | Last-row override | Exact assertion |
|---|---|---|
| test_legacy_buy_route_b_macd_cross | previous DIF <= DEA; current DIF > DEA; MA5 > MA10; close > MA20; volume=1.1 | buy_candidate with reason containing MACD金叉 |
| test_watch_ma_cross_missing_volume | MA5 crosses MA10; MACD improves; volume=1.0 | watch_type equals 均线已触发，量能未确认 |
| test_watch_macd_near_cross_missing_volume | negative DIF-DEA gap narrows; close > MA20; volume=1.0 | watch_type equals MACD接近确认，量能未确认 |
| test_watch_trend_improving_missing_volume | MA5 > MA10; close > MA20; MACD improves; volume=1.0 | watch_type equals 趋势改善，量能未确认 |
| test_holding_sell_below_ma10_with_volume | holding; close < MA10; volume=1.2 | sell_alert with MA10 reason |
| test_holding_sell_below_ma5_with_volume | holding; close < MA5; volume=1.5 | sell_alert with MA5 reason |
| test_non_holding_sell_shape_stays_neutral | non-holding; both sell shapes true | neutral and absent from sells |
| test_60_rows_is_data_unavailable_and_61_rows_is_evaluated | slice baseline to 60 and 61 rows | only the 60-row result is data_unavailable |
| test_score_and_sort_order_are_frozen | two symbols with fixed MA/MACD/volume/share evidence | exact scores and descending buy order |
| test_detail_history_keeps_last_eight_rows | 61-row evaluated history | eight chronological detail rows |

For each test, override only the fields named by the current rule and assert exact signal_type, reason fragment, watch_type, list membership, and numeric score. Do not change production code in this task.

- [ ] **Step 3: Add a serialization parity fixture inside the test**

Use a canonical projection instead of a binary snapshot:

~~~python
PARITY_COLUMNS = [
    "code",
    "signal_type",
    "watch_type",
    "buy_signal",
    "sell_signal",
    "signal_reason",
    "score",
]


def canonical(frame: pd.DataFrame) -> list[dict[str, object]]:
    return (
        frame[PARITY_COLUMNS]
        .sort_values("code")
        .reset_index(drop=True)
        .to_dict(orient="records")
    )
~~~

Build a multi-symbol fixture covering buy, watch, sell, neutral, and unavailable rows and assert the literal expected list. This is the parity oracle used after extraction.

- [ ] **Step 4: Run the complete legacy characterization and existing ETF output tests**

~~~bash
.venv/bin/python -m pytest tests/test_etf_legacy_characterization.py tests/test_etf_signal_output.py tests/test_chat_etf_detail.py -q
~~~

Expected: all tests pass against the unchanged monolith.

- [ ] **Step 5: Commit tests only**

~~~bash
git add tests/test_etf_legacy_characterization.py tests/test_etf_signal_output.py
git commit -m "test: characterize legacy ETF signals"
~~~

---

### Task 3: Introduce the stable plugin contract, configuration model, and registry

**Files:**
- Create: backend/superpower/skills/etf_rotation_strategy/contracts.py
- Create: backend/superpower/skills/etf_rotation_strategy/config.py
- Create: backend/superpower/skills/etf_rotation_strategy/registry.py
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/__init__.py
- Create: tests/test_etf_strategy_contract.py
- Create: tests/test_etf_config.py

**Interfaces:**
- Consumes: raw strategy_params JSON and ETF history/position data.
- Produces: ETFHistory, ETFPositionState, ETFDecision, ETFStrategyMetadata, ETFStrategy protocol, normalize_etf_config(raw), validate_etf_profile(strategy_id, profile), merge_strategy_params(current, patch), etf_config_hash(config), and ETFStrategyRegistry.

- [ ] **Step 1: Write failing contract and configuration tests**

Create tests/test_etf_strategy_contract.py:

~~~python
import pandas as pd
import pytest

from superpower.skills.etf_rotation_strategy.contracts import (
    ETFDecision,
    ETFHistory,
    ETFPositionState,
    MediumStatus,
    ShortEntryStatus,
)


def test_history_rejects_future_rows() -> None:
    rows = pd.DataFrame({"date": pd.to_datetime(["2026-07-01", "2026-07-02"])})
    with pytest.raises(ValueError, match="after as_of"):
        ETFHistory(code="510001", name="样例ETF", rows=rows, as_of=pd.Timestamp("2026-07-01"))


def test_decision_has_stable_state_and_evidence_fields() -> None:
    decision = ETFDecision.unavailable(
        as_of=pd.Timestamp("2026-07-01"),
        code="510001",
        name="样例ETF",
        strategy_id="trend_pullback_v2",
        strategy_version="2.0.0",
        reason="history_rows=120; required=180",
    )
    assert decision.medium_status is MediumStatus.DATA_UNAVAILABLE
    assert decision.short_entry_status is ShortEntryStatus.DATA_UNAVAILABLE
    assert decision.buy_candidate is False
    assert decision.metrics == {}
~~~

Create tests/test_etf_config.py:

~~~python
from copy import deepcopy

import pytest

from superpower.skills.etf_rotation_strategy.config import (
    ETFConfigurationError,
    etf_config_hash,
    merge_strategy_params,
    normalize_etf_config,
)


LEGACY = {
    "etf": {
        "buy_volume_ratio_min": 1.1,
        "sell_ma10_volume_ratio_min": 1.2,
        "sell_ma5_volume_ratio_min": 1.5,
        "score_weights": {"trend": 0.35, "macd": 0.25, "volume": 0.25, "share_change": 0.15},
    },
    "tl": {"weekly_no_trade_hard_veto": True},
}


def test_missing_active_strategy_normalizes_to_legacy_without_mutating_input() -> None:
    original = deepcopy(LEGACY)
    normalized = normalize_etf_config(LEGACY)
    assert LEGACY == original
    assert normalized["active_strategy"] == "legacy_v1"
    assert normalized["buy_volume_ratio_min"] == 1.1
    assert normalized["strategy_profiles"]["legacy_v1"]["buy_volume_ratio_min"] == 1.1


def test_normalization_is_idempotent_and_keeps_flat_compatibility_keys() -> None:
    once = normalize_etf_config(LEGACY)
    twice = normalize_etf_config({"etf": once})
    assert twice == once
    assert twice["sell_ma10_volume_ratio_min"] == 1.2
    assert twice["score_weights"]["trend"] == 0.35


def test_explicit_unknown_strategy_fails_closed() -> None:
    with pytest.raises(ETFConfigurationError, match="unknown active ETF strategy"):
        normalize_etf_config({"etf": {"active_strategy": "missing"}})


def test_deep_merge_preserves_dormant_profiles_and_replaces_arrays() -> None:
    current = {"etf": {"diagnostic_strategies": ["legacy_v1"], "strategy_profiles": {"future_v3": {"x": 1}}}}
    patch = {"etf": {"diagnostic_strategies": ["trend_pullback_v2"]}}
    merged = merge_strategy_params(current, patch)
    assert merged["etf"]["diagnostic_strategies"] == ["trend_pullback_v2"]
    assert merged["etf"]["strategy_profiles"]["future_v3"] == {"x": 1}


def test_hash_is_order_independent_and_etf_only() -> None:
    left = {"active_strategy": "legacy_v1", "strategy_profiles": {"legacy_v1": {}}}
    right = {"strategy_profiles": {"legacy_v1": {}}, "active_strategy": "legacy_v1"}
    assert etf_config_hash(left) == etf_config_hash(right)
~~~

- [ ] **Step 2: Run focused tests and verify missing imports**

~~~bash
.venv/bin/python -m pytest tests/test_etf_strategy_contract.py tests/test_etf_config.py -q
~~~

Expected: collection fails because contracts.py and config.py do not exist.

- [ ] **Step 3: Implement immutable contracts and strict normalization**

Use these public types in contracts.py:

~~~python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd


class ETFStrategyRuntimeError(RuntimeError):
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
        dates = pd.to_datetime(self.rows.get("date"), errors="coerce")
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
    def unavailable(cls, *, as_of: pd.Timestamp, code: str, name: str, strategy_id: str, strategy_version: str, reason: str) -> "ETFDecision":
        return cls(
            as_of=as_of, code=code, name=name, strategy_id=strategy_id,
            strategy_version=strategy_version, medium_status=MediumStatus.DATA_UNAVAILABLE,
            short_entry_status=ShortEntryStatus.DATA_UNAVAILABLE, exit_status="not_triggered",
            eligible=False, buy_candidate=False, watch_candidate=False, sell_alert=False,
            score=0.0, medium_reason=reason, short_entry_reason=reason,
            risk_notes=(reason,), data_quality="ERROR",
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
    def evaluate(self, history: ETFHistory, position: ETFPositionState, params: Mapping[str, Any]) -> ETFDecision:
        raise NotImplementedError
    def evaluate_history(self, history: ETFHistory, params: Mapping[str, Any]) -> list[ETFDecision]:
        raise NotImplementedError
~~~

In config.py define:

~~~python
class ETFConfigurationError(ValueError):
    """Raised before a run or save when ETF plugin configuration is invalid."""


KNOWN_STRATEGY_IDS = frozenset({"legacy_v1", "trend_pullback_v2"})
~~~

JSON-serialize the normalized ETF block with sort_keys=True and compact separators, then SHA-256 it. Deep-merge dictionaries recursively, replace lists, preserve unknown dormant profiles, validate finite numeric bounds and score weights summing to 1.0 within 1e-9. Missing active_strategy maps to legacy_v1; an explicit unknown ID raises ETFConfigurationError. The normalized ETF block remains idempotent and retains the four flat legacy keys for one compatibility cycle while also providing strategy_profiles. validate_all_etf_profiles(config) calls validate_etf_profile for every registered profile named by active_strategy or diagnostic_strategies; dormant unknown profiles are preserved but not executed.

Normalization must copy the effective legacy thresholds and score weights into trend_pullback_v2.exit.legacy_params and trend_pullback_v2.ranking.legacy_params. This is how v2 reuses the selected run's legacy exit/ranking settings without importing the raw JSON shape.

- [ ] **Step 4: Implement the explicit registry and pass focused tests**

registry.py must register constructors by literal ID, never import arbitrary filesystem modules:

~~~python
from __future__ import annotations

from collections.abc import Callable

from .contracts import ETFStrategy, ETFStrategyMetadata
from .config import ETFConfigurationError


class ETFStrategyRegistry:
    def __init__(self) -> None:
        self._constructors: dict[str, Callable[[], ETFStrategy]] = {}
        self._metadata: dict[str, ETFStrategyMetadata] = {}

    def register(self, metadata: ETFStrategyMetadata, constructor: Callable[[], ETFStrategy]) -> None:
        if metadata.strategy_id in self._constructors:
            raise ETFConfigurationError(f"duplicate ETF strategy: {metadata.strategy_id}")
        self._constructors[metadata.strategy_id] = constructor
        self._metadata[metadata.strategy_id] = metadata

    def create(self, strategy_id: str) -> ETFStrategy:
        try:
            return self._constructors[strategy_id]()
        except KeyError as exc:
            raise ETFConfigurationError(f"unknown active ETF strategy: {strategy_id}") from exc

    def metadata(self) -> list[ETFStrategyMetadata]:
        return [self._metadata[key] for key in sorted(self._metadata)]
~~~

Task 3 ships the registry class and KNOWN_STRATEGY_IDS=frozenset({"legacy_v1", "trend_pullback_v2"}). Task 4 adds default_registry() with legacy_v1; Task 8 adds trend_pullback_v2 to that same explicit function and adds a test asserting registered metadata IDs equal KNOWN_STRATEGY_IDS. normalize_etf_config rejects an active or diagnostic ID outside that set, while preserving unselected unknown profile objects for forward compatibility.

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_strategy_contract.py tests/test_etf_config.py -q
~~~

Expected: all focused tests pass.

- [ ] **Step 5: Commit the contract boundary**

~~~bash
git add backend/superpower/skills/etf_rotation_strategy/contracts.py backend/superpower/skills/etf_rotation_strategy/config.py backend/superpower/skills/etf_rotation_strategy/registry.py backend/superpower/skills/etf_rotation_strategy/strategies/__init__.py tests/test_etf_strategy_contract.py tests/test_etf_config.py
git commit -m "feat: add ETF strategy plugin contract"
~~~

---

### Task 4: Extract legacy_v1 with byte-compatible projections

**Files:**
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/legacy_v1.py
- Create: backend/superpower/skills/etf_rotation_strategy/compatibility.py
- Modify: backend/superpower/skills/etf_rotation_strategy/handler.py
- Modify: backend/superpower/skills/strategy_backtest/handler.py
- Modify: backend/superpower/skills/etf_rotation_strategy/strategies/__init__.py
- Modify: tests/test_etf_legacy_characterization.py

**Interfaces:**
- Consumes: ETFHistory, ETFPositionState, normalized legacy profile.
- Produces: LegacyV1Strategy.evaluate, legacy_buy_reasons, legacy_sell_reasons, legacy_score, decisions_to_legacy_tables, and the unchanged latest_etf_signals wrapper.

- [ ] **Step 1: Extend parity tests to select legacy_v1 explicitly**

Add:

~~~python
def plugin_params() -> dict[str, object]:
    params = deepcopy(PARAMS)
    params["etf"]["active_strategy"] = "legacy_v1"
    params["etf"]["diagnostic_strategies"] = ["legacy_v1"]
    params["etf"]["strategy_profiles"] = {"legacy_v1": {}}
    return params


def test_explicit_legacy_selection_matches_implicit_legacy() -> None:
    data = multi_symbol_parity_history()
    implicit = latest_etf_signals(data, positions("510003"), PARAMS)
    explicit = latest_etf_signals(data, positions("510003"), plugin_params())
    for implicit_frame, explicit_frame in zip(implicit, explicit):
        pd.testing.assert_frame_equal(
            implicit_frame.reset_index(drop=True),
            explicit_frame.reset_index(drop=True),
            check_dtype=False,
        )
~~~

Also add a test that strategy_backtest imports no name beginning with an underscore from etf_rotation_strategy.

- [ ] **Step 2: Run tests and observe the explicit profile is not yet routed**

~~~bash
.venv/bin/python -m pytest tests/test_etf_legacy_characterization.py -q
~~~

Expected: the new explicit-selection or import-boundary test fails.

- [ ] **Step 3: Move policy functions and create the canonical compatibility projection**

legacy_v1.py exports public names:

~~~python
class LegacyV1Strategy:
    strategy_id = "legacy_v1"
    version = "1.0.0"

    def evaluate(self, history: ETFHistory, position: ETFPositionState, params: Mapping[str, object]) -> ETFDecision:
        rows = history.rows.sort_values("date").reset_index(drop=True)
        if len(rows) < 61:
            return legacy_unavailable_decision(history, position, len(rows))
        return self._evaluate_rows(rows.iloc[-1], rows.iloc[-2], history, position, params)

    def _evaluate_rows(
        self,
        row: pd.Series,
        prev: pd.Series,
        history: ETFHistory,
        position: ETFPositionState,
        params: Mapping[str, object],
    ) -> ETFDecision:
        buy_reasons = legacy_buy_reasons(row, prev, params)
        sell_reasons = legacy_sell_reasons(row, params)
        watch_type, missing, suggested = legacy_watch_diagnosis(row, prev, params)
        buy = bool(buy_reasons) and not position.is_holding
        sell = bool(sell_reasons) and position.is_holding
        watch_evidence = bool(watch_type) and not buy and not sell
        public_watch = watch_evidence and not position.is_holding
        short = (
            ShortEntryStatus.LEGACY_BUY if buy
            else ShortEntryStatus.LEGACY_WATCH if watch_evidence
            else ShortEntryStatus.LEGACY_NEUTRAL
        )
        compatibility_fields = legacy_row_fields(
            row=row,
            prev=prev,
            params=params,
            position=position,
            buy_reasons=buy_reasons,
            sell_reasons=sell_reasons,
            watch_type=watch_type,
            missing_condition=missing,
            suggested_action=suggested,
        )
        return ETFDecision(
            as_of=history.as_of, code=history.code, name=history.name,
            strategy_id=self.strategy_id, strategy_version=self.version,
            medium_status=MediumStatus.NOT_APPLICABLE, short_entry_status=short,
            exit_status="triggered" if sell else "not_triggered",
            eligible=buy, buy_candidate=buy, watch_candidate=public_watch, sell_alert=sell,
            score=legacy_score(row, params), rule_hits=tuple(buy_reasons + sell_reasons),
            missing_conditions=(missing,) if missing else (), data_quality="OK",
            metrics={"watch_type": watch_type, "suggested_action": suggested},
            compatibility_fields=compatibility_fields,
        )

    def evaluate_history(self, history: ETFHistory, params: Mapping[str, object]) -> list[ETFDecision]:
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
                decisions.append(legacy_unavailable_decision(row_history, ETFPositionState(False), index + 1))
            else:
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
~~~

legacy_row_fields and legacy_unavailable_decision move the existing reason, display_action, watch_type, missing_condition, volume_check, rule_hits, risk_notes, confidence, data_quality, metrics, and old scalar-column construction without changing strings. legacy_unavailable_decision uses medium_status=not_applicable, short_entry_status=data_unavailable, and the exact old “有效历史仅N行” compatibility row. This preserves the current behavior where a holding ETF may have signal_type=watch in the all-signal table but is excluded from the public watchlist. compatibility.py defines SIGNAL_COLUMNS as the old columns followed by additive canonical fields and projects compatibility_fields exactly. Keep _buy_reasons, _sell_reasons, and score_etf as deprecated one-cycle wrappers in handler.py so external callers do not break abruptly.

- [ ] **Step 4: Route the stable wrapper through the registry and prove parity**

handler.latest_etf_signals must:

~~~python
normalized = normalize_etf_config(params)
strategy = default_registry().create(normalized["active_strategy"])
profile = normalized["strategy_profiles"][normalized["active_strategy"]]
decisions = evaluate_latest_by_symbol(etf, positions, strategy, profile)
return decisions_to_legacy_tables(decisions, etf, positions, params)
~~~

Define evaluate_latest_by_symbol in handler.py with the exact signature:

~~~python
def evaluate_latest_by_symbol(
    etf: pd.DataFrame,
    positions: pd.DataFrame,
    strategy: ETFStrategy,
    profile: Mapping[str, object],
) -> list[ETFDecision]:
    holding_codes = set(
        positions.loc[
            (positions["asset_type"] == "ETF") & (positions["status"] == "holding"),
            "code",
        ].astype(str)
    ) if not positions.empty else set()
    decisions: list[ETFDecision] = []
    for (name, code), group in etf.groupby(["name", "code"], sort=True):
        rows = group.sort_values("date").reset_index(drop=True)
        if rows.empty:
            continue
        as_of = pd.Timestamp(rows.iloc[-1]["date"])
        history = ETFHistory(code=str(code), name=str(name), rows=rows, as_of=as_of)
        position = ETFPositionState(is_holding=str(code) in holding_codes)
        try:
            decisions.append(strategy.evaluate(history, position, profile))
        except Exception as exc:
            raise ETFStrategyRuntimeError(
                f"ETF strategy {strategy.strategy_id} failed for {code} at {as_of.date()}"
            ) from exc
    return decisions
~~~

Import ETFHistory, ETFPositionState, ETFDecision, ETFStrategy, and ETFStrategyRuntimeError from contracts.py. This grouped loop replaces the orchestration portion of the current latest_etf_signals without embedding policy.

Update strategy_backtest/handler.py to import legacy_buy_reasons and legacy_sell_reasons from strategies.legacy_v1. Then run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_legacy_characterization.py tests/test_etf_signal_output.py tests/test_dashboard_schema.py tests/test_chat_etf_detail.py -q
~~~

Expected: exact parity tests and existing consumers all pass.

- [ ] **Step 5: Commit the legacy extraction**

~~~bash
git add backend/superpower/skills/etf_rotation_strategy/handler.py backend/superpower/skills/etf_rotation_strategy/compatibility.py backend/superpower/skills/etf_rotation_strategy/strategies/legacy_v1.py backend/superpower/skills/etf_rotation_strategy/strategies/__init__.py backend/superpower/skills/strategy_backtest/handler.py tests/test_etf_legacy_characterization.py
git commit -m "refactor: extract legacy ETF strategy plugin"
~~~

---

### Task 5: Add causal ETF-only MA20 slope and weekly MACD indicators

**Files:**
- Create: backend/superpower/skills/technical_indicators/etf.py
- Create: tests/test_etf_indicators.py
- Modify: backend/superpower/skills/technical_indicators/handler.py
- Modify: backend/superpower/agents/indicator_agent.py

**Interfaces:**
- Consumes: one ETF's daily OHLCV rows already enriched by add_indicators.
- Produces: add_etf_indicators(group, volume_field, medium_profile, as_of=None) -> pd.DataFrame, classify_ma20_slope(value, tolerance), and classify_weekly_macd(hist, previous).

- [ ] **Step 1: Write exact boundary and causality tests**

Create tests/test_etf_indicators.py:

~~~python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from superpower.skills.technical_indicators.etf import (
    add_etf_indicators,
    classify_ma20_slope,
    classify_weekly_macd,
)

MEDIUM_PROFILE = {
    "ma20_slope_lookback": 5,
    "ma20_flat_tolerance": 0.003,
}


def indicator_history(periods: int, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=periods)
    close = 10.0 + np.arange(periods) * 0.01
    return pd.DataFrame(
        {
            "date": dates,
            "code": "510001",
            "name": "样例ETF",
            "开盘价": close - 0.02,
            "最高价": close + 0.05,
            "最低价": close - 0.05,
            "收盘价": close,
            "成交量（万股）": 100.0 + np.arange(periods),
        }
    )


def indicator_history_with_removed_week() -> pd.DataFrame:
    history = indicator_history(periods=260, end="2026-07-10")
    removed = history["date"].between("2026-06-15", "2026-06-19")
    return history.loc[~removed].reset_index(drop=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.003001, "down"),
        (-0.003000, "flat"),
        (0.0, "flat"),
        (0.003000, "flat"),
        (0.003001, "up"),
    ],
)
def test_ma20_slope_boundaries(value: float, expected: str) -> None:
    assert classify_ma20_slope(value, 0.003) == expected


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (0.01, 0.02, "red_strengthening"),
        (0.02, 0.01, "red_weakening"),
        (-0.02, -0.01, "green_narrowing"),
        (-0.01, -0.02, "green_widening"),
        (-0.01, 0.0, "neutral_zero"),
    ],
)
def test_weekly_macd_states(previous: float, current: float, expected: str) -> None:
    assert classify_weekly_macd(current, previous) == expected


def test_current_week_change_does_not_change_official_completed_week() -> None:
    history = indicator_history(periods=220, end="2026-07-10")
    monday = add_etf_indicators(history[history["date"] <= "2026-07-06"], "成交量（万股）", MEDIUM_PROFILE)
    friday = add_etf_indicators(history, "成交量（万股）", MEDIUM_PROFILE)
    assert monday.iloc[-1]["weekly_macd_hist"] == friday.iloc[-1]["weekly_macd_hist"]
    assert monday.iloc[-1]["weekly_macd_state"] == friday.iloc[-1]["weekly_macd_state"]
    assert monday.iloc[-1]["weekly_macd_preview"] != friday.iloc[-1]["weekly_macd_preview"]


def test_rows_after_as_of_cannot_change_historical_indicators() -> None:
    history = indicator_history(periods=220, end="2026-07-10")
    as_of = pd.Timestamp("2026-06-30")
    before = add_etf_indicators(history[history["date"] <= as_of], "成交量（万股）", MEDIUM_PROFILE, as_of=as_of)
    changed = history.copy()
    changed.loc[changed["date"] > as_of, "收盘价"] = 999.0
    after = add_etf_indicators(changed, "成交量（万股）", MEDIUM_PROFILE, as_of=as_of)
    pd.testing.assert_series_equal(before.iloc[-1], after.iloc[-1], check_names=False)


def test_full_history_monday_preview_equals_monday_prefix_preview() -> None:
    history = indicator_history(periods=220, end="2026-07-10")
    full = add_etf_indicators(history, "成交量（万股）", MEDIUM_PROFILE)
    monday = pd.Timestamp("2026-07-06")
    prefix = add_etf_indicators(history[history["date"] <= monday], "成交量（万股）", MEDIUM_PROFILE)
    full_monday = full.loc[full["date"] == monday].iloc[0]
    assert full_monday["weekly_macd_preview"] == prefix.iloc[-1]["weekly_macd_preview"]


def test_empty_calendar_week_is_not_treated_as_completed_observation() -> None:
    history = indicator_history_with_removed_week()
    result = add_etf_indicators(history, "成交量（万股）", MEDIUM_PROFILE)
    monday_after_gap = result.loc[result["date"] == pd.Timestamp("2026-06-22")].iloc[0]
    assert monday_after_gap["weekly_completed_date"] == pd.Timestamp("2026-06-12")
~~~

- [ ] **Step 2: Run the indicator tests and verify the module is missing**

~~~bash
.venv/bin/python -m pytest tests/test_etf_indicators.py -q
~~~

Expected: collection fails because technical_indicators.etf does not exist.

- [ ] **Step 3: Implement classification and causal weekly selection**

Create the public classification functions exactly:

~~~python
from __future__ import annotations

import numpy as np
import pandas as pd


def classify_ma20_slope(value: float, tolerance: float) -> str:
    if pd.isna(value):
        return "data_unavailable"
    if value < -tolerance:
        return "down"
    if value > tolerance:
        return "up"
    return "flat"


def classify_weekly_macd(hist: float, previous: float) -> str:
    if pd.isna(hist) or pd.isna(previous):
        return "data_unavailable"
    if hist == 0:
        return "neutral_zero"
    if hist > 0:
        return "red_strengthening" if hist >= previous else "red_weakening"
    return "green_narrowing" if hist > previous else "green_widening"


def _macd(close: pd.Series) -> pd.DataFrame:
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False, min_periods=9).mean()
    return pd.DataFrame({"weekly_dif": dif, "weekly_dea": dea, "weekly_macd_hist_raw": dif - dea})
~~~

In add_etf_indicators:

1. Filter rows to date <= as_of before any calculation.
2. Sort by date and call the existing add_indicators only when MA columns are absent.
3. Read ma20_slope_lookback and ma20_flat_tolerance from medium_profile. Calculate ma20_slope_5d using the configured lookback and classify using the configured tolerance; keep the public column name for compatibility with the approved contract.
4. Resample close and volume using W-FRI, then drop weeks with no source trading row before calculating weekly MACD.
5. Map each daily row to its current week-end. Set official weekly fields from the nearest non-empty weekly observation whose W-FRI label is strictly less than the current week-end.
6. Add weekly_macd_hist, weekly_macd_state, weekly_macd_preview, weekly_macd_preview_state, and weekly_completed_date.

The official mapping must use the prior non-empty W-FRI record even on Friday, because the whole current report week is preview-only. Compute preview causally from the previous completed weekly EMA12/EMA26/DEA state plus that daily row's close as the current-week candidate; do not map the final close of the full week back onto earlier weekdays. Apply the same 12/26/9 warm-up as daily MACD.

- [ ] **Step 4: Integrate only the ETF indicator path and run causality tests**

Keep technical_indicators.handler.add_indicators unchanged for TL. Add a separate ETF call from IndicatorAgent or the ETF grouping path:

~~~python
etf_indicators = pd.concat(
    [
        add_etf_indicators(
            add_indicators(group, "成交量（万股）"),
            "成交量（万股）",
            context.get("strategy_params")["etf"]["strategy_profiles"]["trend_pullback_v2"]["medium_trend"],
        )
        for _, group in etf_raw.groupby(["name", "code"])
    ],
    ignore_index=True,
)
~~~

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_indicators.py tests/test_tl_status_output.py tests/test_data_quality.py -q
~~~

Expected: all tests pass; TL fixtures remain byte-equivalent.

- [ ] **Step 5: Commit ETF-specific indicators**

~~~bash
git add backend/superpower/skills/technical_indicators/etf.py backend/superpower/skills/technical_indicators/handler.py backend/superpower/agents/indicator_agent.py tests/test_etf_indicators.py
git commit -m "feat: add causal ETF trend indicators"
~~~

---

### Task 6: Implement the medium-trend policy

**Files:**
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/__init__.py
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/defaults.py
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/medium_trend.py
- Create: tests/test_etf_medium_trend.py

**Interfaces:**
- Consumes: latest enriched ETF row plus previous row and medium_trend profile.
- Produces: MediumTrendResult, evaluate_medium_trend(row, previous, profile), and evaluate_medium_history(rows, profile).

- [ ] **Step 1: Write precedence and customer-scenario tests**

Create tests/test_etf_medium_trend.py:

~~~python
import pandas as pd
import pytest

from superpower.skills.etf_rotation_strategy.contracts import MediumStatus
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.medium_trend import evaluate_medium_trend


def row(**overrides: object) -> pd.Series:
    values = {
        "收盘价": 10.5,
        "成交量（万股）": 120.0,
        "vol_ratio60": 1.2,
        "ma5": 10.3,
        "ma20": 10.0,
        "ma20_slope_5d": 0.0,
        "ma20_slope_state": "flat",
        "weekly_macd_hist": 0.02,
        "weekly_macd_state": "red_strengthening",
        "macd_hist": 0.01,
    }
    values.update(overrides)
    return pd.Series(values)


def test_falling_ma20_is_hard_veto_even_with_daily_cross_and_volume() -> None:
    result = evaluate_medium_trend(
        row(ma20_slope_5d=-0.004, ma20_slope_state="down", vol_ratio60=3.0),
        row(ma5=9.9),
        {},
    )
    assert result.status is MediumStatus.DO_NOT_PARTICIPATE
    assert "ma20_slope_down" in result.rule_hits


def test_weekly_green_widening_is_hard_veto() -> None:
    result = evaluate_medium_trend(row(weekly_macd_hist=-0.02, weekly_macd_state="green_widening"), row(), {})
    assert result.status is MediumStatus.DO_NOT_PARTICIPATE


def test_all_confirmations_make_persistent_trend_confirmed() -> None:
    result = evaluate_medium_trend(row(), row(ma5=10.2, ma20=10.0), {})
    assert result.status is MediumStatus.TREND_CONFIRMED
    assert result.ma5_crossed_ma20_today is False


@pytest.mark.parametrize("field", ["ma20", "ma20_slope_5d", "weekly_macd_hist", "macd_hist", "vol_ratio60"])
def test_required_missing_field_returns_data_unavailable(field: str) -> None:
    result = evaluate_medium_trend(row(**{field: float("nan")}), row(), {})
    assert result.status is MediumStatus.DATA_UNAVAILABLE


def test_zero_weekly_hist_is_not_confirmed() -> None:
    result = evaluate_medium_trend(row(weekly_macd_hist=0.0, weekly_macd_state="neutral_zero"), row(), {})
    assert result.status is MediumStatus.TREND_NOT_CONFIRMED
~~~

- [ ] **Step 2: Run tests and verify the policy module is missing**

~~~bash
.venv/bin/python -m pytest tests/test_etf_medium_trend.py -q
~~~

Expected: collection fails for the missing trend_pullback_v2 package.

- [ ] **Step 3: Add versioned defaults and immutable medium result**

defaults.py contains:

~~~python
STRATEGY_ID = "trend_pullback_v2"
STRATEGY_VERSION = "2.0.0"

DEFAULT_PROFILE = {
    "medium_trend": {
        "minimum_history_rows": 180,
        "ma20_slope_lookback": 5,
        "ma20_flat_tolerance": 0.003,
    },
    "short_entry": {
        "confirmation_window": 3,
        "overheat_daily_return_min": 0.04,
        "overheat_body_ratio_min": 0.60,
        "overheat_volume_ratio_min": 1.80,
        "overheat_ma5_distance_min": 0.03,
        "overheat_cooldown_days": 3,
        "pullback_support_tolerance": 0.005,
        "pullback_max_intraday_break": 0.010,
        "pullback_max_age": 10,
    },
    "exit": {"policy": "legacy_v1"},
    "ranking": {"policy": "legacy_v1"},
}

PARAMETER_SCHEMA = {
    "medium_trend": {
        "minimum_history_rows": {"type": "integer", "label": "最少历史交易日", "min": 180, "max": 1000, "step": 1},
        "ma20_slope_lookback": {"type": "integer", "label": "MA20斜率回看日", "min": 2, "max": 20, "step": 1},
        "ma20_flat_tolerance": {"type": "number", "label": "MA20走平容差", "min": 0.0, "max": 0.05, "step": 0.0005},
    },
    "short_entry": {
        "confirmation_window": {"type": "integer", "label": "突破确认窗口", "min": 1, "max": 5, "step": 1},
        "overheat_daily_return_min": {"type": "number", "label": "过热日涨幅", "min": 0.01, "max": 0.20, "step": 0.005},
        "overheat_body_ratio_min": {"type": "number", "label": "过热阳线实体比例", "min": 0.10, "max": 1.0, "step": 0.05},
        "overheat_volume_ratio_min": {"type": "number", "label": "过热量能倍数", "min": 1.0, "max": 5.0, "step": 0.1},
        "overheat_ma5_distance_min": {"type": "number", "label": "偏离MA5比例", "min": 0.005, "max": 0.20, "step": 0.005},
        "overheat_cooldown_days": {"type": "integer", "label": "过热冷却日", "min": 1, "max": 10, "step": 1},
        "pullback_support_tolerance": {"type": "number", "label": "回踩触及容差", "min": 0.0, "max": 0.03, "step": 0.001},
        "pullback_max_intraday_break": {"type": "number", "label": "盘中最大跌破", "min": 0.001, "max": 0.05, "step": 0.001},
        "pullback_max_age": {"type": "integer", "label": "回踩最长等待日", "min": 3, "max": 30, "step": 1},
    },
}
~~~

medium_trend.py defines:

~~~python
from dataclasses import dataclass

from superpower.skills.etf_rotation_strategy.contracts import MediumStatus
from typing import Sequence


@dataclass(frozen=True)
class MediumTrendResult:
    status: MediumStatus
    reason: str
    rule_hits: Sequence[str]
    missing_conditions: Sequence[str]
    ma5_crossed_ma20_today: bool
~~~

- [ ] **Step 4: Implement fixed precedence and pass all medium tests**

evaluate_medium_trend must execute in this order:

~~~python
required = ("收盘价", "成交量（万股）", "vol_ratio60", "ma5", "ma20", "ma20_slope_5d", "weekly_macd_hist", "macd_hist")
missing = tuple(key for key in required if pd.isna(row.get(key)))
if missing:
    return MediumTrendResult(MediumStatus.DATA_UNAVAILABLE, "required medium data missing", (), missing, False)

crossed_today = bool(
    pd.notna(previous.get("ma5"))
    and pd.notna(previous.get("ma20"))
    and previous["ma5"] <= previous["ma20"]
    and row["ma5"] > row["ma20"]
)
if row["ma20_slope_state"] == "down" or row["weekly_macd_state"] == "green_widening":
    hits = tuple(
        hit for hit, active in (
            ("ma20_slope_down", row["ma20_slope_state"] == "down"),
            ("weekly_macd_green_widening", row["weekly_macd_state"] == "green_widening"),
        ) if active
    )
    return MediumTrendResult(MediumStatus.DO_NOT_PARTICIPATE, "medium hard veto", hits, (), crossed_today)

confirmed = (
    row["收盘价"] > row["ma20"]
    and row["ma5"] > row["ma20"]
    and row["ma20_slope_state"] in {"flat", "up"}
    and row["weekly_macd_hist"] > 0
    and row["macd_hist"] > 0
)
status = MediumStatus.TREND_CONFIRMED if confirmed else MediumStatus.TREND_NOT_CONFIRMED
return MediumTrendResult(status, "all medium confirmations met" if confirmed else "medium confirmation incomplete", (), (), crossed_today)
~~~

Add the one-pass history wrapper:

~~~python
def evaluate_medium_history(rows: pd.DataFrame, profile: Mapping[str, object]) -> list[MediumTrendResult]:
    results: list[MediumTrendResult] = []
    for index in range(len(rows)):
        if index == 0:
            results.append(
                MediumTrendResult(
                    MediumStatus.DATA_UNAVAILABLE,
                    "previous row missing",
                    (),
                    ("previous_row",),
                    False,
                )
            )
            continue
        results.append(evaluate_medium_trend(rows.iloc[index], rows.iloc[index - 1], profile))
    return results
~~~

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_medium_trend.py tests/test_etf_indicators.py -q
~~~

Expected: all tests pass.

- [ ] **Step 5: Commit the medium module**

~~~bash
git add backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2 tests/test_etf_medium_trend.py
git commit -m "feat: add ETF medium trend policy"
~~~

---

### Task 7: Implement the short-entry state machine

**Files:**
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/short_entry.py
- Create: tests/test_etf_short_entry.py

**Interfaces:**
- Consumes: a chronological list of MediumTrendResult plus enriched daily rows and short_entry profile.
- Produces: SetupState, ShortEntryResult, evaluate_short_entry(history, medium_results, profile), and evaluate_short_entry_history(history, medium_results, profile, trading_session_numbers).

- [ ] **Step 1: Write table-driven transition tests**

Create tests/test_etf_short_entry.py with fixture builders that produce explicit daily rows and medium states. Required test names and exact expected states:

~~~python
CASES = [
    ("ma5_above_ma10_green_narrowing", "close_watch"),
    ("ma5_above_ma10_green_to_red", "close_watch"),
    ("nonconfirmed_without_close_watch", "no_entry"),
    ("setup_day", "waiting_confirmation"),
    ("confirmed_breakout_next_day", "can_enter"),
    ("giant_volume_bar", "overheated_do_not_chase"),
    ("cooldown_day", "waiting_pullback"),
    ("contracting_volume_support_hold", "can_enter"),
    ("broken_support", "no_entry"),
    ("expired_setup", "no_entry"),
]


@pytest.mark.parametrize(("scenario", "expected"), CASES)
def test_short_entry_scenarios(scenario: str, expected: str) -> None:
    history, medium_results = scenario_data(scenario)
    result = evaluate_short_entry(history, medium_results, DEFAULT_PROFILE["short_entry"])
    assert result.status.value == expected


def test_close_watch_contains_both_customer_prompts() -> None:
    history, medium_results = scenario_data("ma5_above_ma10_green_narrowing")
    result = evaluate_short_entry(history, medium_results, DEFAULT_PROFILE["short_entry"])
    assert result.weekly_macd_confirmation_check in {"favorable", "caution", "unfavorable", "not_confirmed"}
    assert result.ma20_flat_check in {"met", "positive", "not_met"}
    assert "周MACD" in result.reason
    assert "MA20" in result.reason


def test_repeated_overheat_restarts_three_session_cooldown() -> None:
    history, medium_results = scenario_data("repeated_overheat")
    results = evaluate_short_entry_history(
        history,
        medium_results,
        DEFAULT_PROFILE["short_entry"],
        trading_session_numbers=list(range(1, len(history) + 1)),
    )
    assert results[-1].status.value == "waiting_pullback"
    assert results[-1].cooldown_remaining == 2


def test_later_cross_does_not_replace_active_setup() -> None:
    history, medium_results = scenario_data("second_cross_inside_setup")
    results = evaluate_short_entry_history(
        history,
        medium_results,
        DEFAULT_PROFILE["short_entry"],
        trading_session_numbers=list(range(1, len(history) + 1)),
    )
    assert results[-1].setup_date == results[0].setup_date
~~~

Also assert setup_age=0 on the setup day, setup expiry at age 11, short data_unavailable when fewer than 180 rows, and medium hard veto never produces can_enter.

scenario_data is created in the same test file. It emits 180 neutral warm-up rows followed by the literal tail below; unlisted OHLCV values use close=10, high=10.1, low=9.9, volume=100, MA5=10, MA10=9.95, positive daily MACD, and confirmed medium:

| Scenario | Tail conditions |
|---|---|
| ma5_above_ma10_green_narrowing | medium=trend_not_confirmed; previous/current MACD=-0.02/-0.01 |
| ma5_above_ma10_green_to_red | medium=trend_not_confirmed; previous/current MACD=-0.01/+0.01 |
| nonconfirmed_without_close_watch | medium=trend_not_confirmed; MA5<=MA10 |
| setup_day | previous medium=trend_not_confirmed; current medium=trend_confirmed |
| confirmed_breakout_next_day | setup high=10.1; next close=10.2; MACD>0; MA5 distance<3% |
| giant_volume_bar | daily return=4%; body ratio=60%; vol ratio=1.8; MA5 distance=3% |
| cooldown_day | prior row is giant_volume_bar; current row does not confirm pullback |
| contracting_volume_support_hold | active setup volume=200; low touches support; close>=support; current volume=100; MACD>0 |
| broken_support | low<support*0.99 and close<support |
| expired_setup | current trading-session age=11 |
| repeated_overheat | overheat at ages 1 and 3; inspect age 4 |
| second_cross_inside_setup | setup at age 0; another MA5/MA20 cross at age 2 |

The helper returns rows and a same-length MediumTrendResult list; tests derive trading-session numbers as 1 through len(rows). No undeclared pytest fixture is assumed.

- [ ] **Step 2: Run the state-machine tests and observe missing functions**

~~~bash
.venv/bin/python -m pytest tests/test_etf_short_entry.py -q
~~~

Expected: collection fails because short_entry.py does not exist.

- [ ] **Step 3: Define state and event records**

short_entry.py defines:

~~~python
from dataclasses import dataclass

import pandas as pd

from superpower.skills.etf_rotation_strategy.contracts import ShortEntryStatus
from typing import Sequence


@dataclass(frozen=True)
class SetupState:
    date: pd.Timestamp
    close: float
    high: float
    volume: float
    ma5: float
    ma10: float
    ma20: float


@dataclass(frozen=True)
class ShortEntryResult:
    status: ShortEntryStatus
    reason: str
    setup_date: pd.Timestamp | None
    setup_age: int | None
    cooldown_remaining: int
    weekly_macd_confirmation_check: str
    ma20_flat_check: str
    rule_hits: Sequence[str]
    missing_conditions: Sequence[str]
    risk_notes: Sequence[str]
~~~

Add pure helpers calculate_overheat(row, previous, profile), close_watch_trigger(row, previous), breakout_confirmed(row, setup, profile), and pullback_result(row, setup, profile). Each returns booleans plus evidence, never mutates the input frame.

Implement the customer's close-watch trigger and overheat calculation literally:

~~~python
def close_watch_trigger(row: pd.Series, previous: pd.Series) -> bool:
    ma_ready = pd.notna(row.get("ma5")) and pd.notna(row.get("ma10")) and row["ma5"] > row["ma10"]
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


def calculate_overheat(row: pd.Series, previous: pd.Series, profile: Mapping[str, float]) -> bool:
    daily_return = row["收盘价"] / previous["收盘价"] - 1
    body_ratio = max(row["收盘价"] - row["开盘价"], 0.0) / max(row["最高价"] - row["最低价"], 1e-12)
    ma5_distance = row["收盘价"] / row["ma5"] - 1
    return bool(
        daily_return >= profile["overheat_daily_return_min"]
        and body_ratio >= profile["overheat_body_ratio_min"]
        and row["vol_ratio60"] >= profile["overheat_volume_ratio_min"]
        and ma5_distance >= profile["overheat_ma5_distance_min"]
    )
~~~

Map weekly prompts exactly: green_narrowing/red_strengthening -> favorable, red_weakening -> caution, green_widening -> unfavorable, and neutral_zero -> not_confirmed. Map MA20 slope flat -> met, up -> positive, and down -> not_met.

close_watch_result uses this exact base copy:

~~~text
密切观察：MA5已在MA10上方，日MACD绿柱缩短或转红。
中期确认项：
1）周MACD是否绿柱缩短或红柱加长；
2）MA20是否走平。
~~~

- [ ] **Step 4: Implement a single forward pass with fixed routing**

The loop owns active_setup, cooldown_until_index, and prior short state. Calculate overheated before medium routing so a giant bar in a non-confirmed/downtrend state is still recorded as追高风险 even though its state remains close_watch or no_entry. Per row:

~~~python
overheated = False if overheat_inputs_missing(row, previous) else calculate_overheat(row, previous, profile)
if required_data_missing:
    result = unavailable_result()
elif medium.status in {MediumStatus.DO_NOT_PARTICIPATE, MediumStatus.TREND_NOT_CONFIRMED}:
    result = close_watch_result(row) if close_watch_trigger(row, previous) else no_entry_result()
    if overheated:
        result = with_risk_note(result, "overheat_detected_but_medium_not_confirmed")
    active_setup = None
elif medium.status is MediumStatus.TREND_CONFIRMED:
    if active_setup is None and (medium_just_confirmed or medium.ma5_crossed_ma20_today):
        active_setup = setup_from_row(row)
    if setup_is_expired_or_invalid(active_setup, row, profile):
        active_setup = None
    if overheated:
        cooldown_until_index = index + int(profile["overheat_cooldown_days"])
        result = overheated_result(active_setup)
    elif index <= cooldown_until_index:
        result = waiting_pullback_result(active_setup, cooldown_until_index - index)
    elif active_setup is None:
        result = no_entry_result()
    elif breakout_confirmed(row, active_setup, profile):
        result = can_enter_breakout_result(active_setup)
    else:
        pullback = pullback_result(row, active_setup, profile)
        if pullback.structure_broken:
            active_setup = None
            result = no_entry_broken_result()
        elif pullback.confirmed:
            result = can_enter_pullback_result(active_setup)
        elif setup_age(index, active_setup) <= int(profile["confirmation_window"]):
            result = waiting_confirmation_result(active_setup)
        else:
            result = waiting_pullback_result(active_setup, 0)
~~~

Calculate support as max(MA5, MA10, and setup high only when close >= setup high). A support break greater than 1% plus close below support invalidates. A touch with intact structure, close at/above support, lower volume than setup, positive daily MACD, and confirmed medium returns can_enter.

Use short_entry.pullback_max_age as the single setup-expiry limit; no second setup-age parameter is introduced.
Set entry_route=breakout_confirmation for breakout can_enter, entry_route=pullback_confirmation for support-hold can_enter, and an empty route for all other states.

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_short_entry.py tests/test_etf_medium_trend.py -q
~~~

Expected: every scenario and edge transition passes.

- [ ] **Step 5: Commit the short-entry state machine**

~~~bash
git add backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/short_entry.py tests/test_etf_short_entry.py
git commit -m "feat: add ETF short entry state machine"
~~~

---

### Task 8: Compose trend_pullback_v2 and publish canonical ETF decisions

**Files:**
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/strategy.py
- Create: tests/test_etf_trend_pullback_strategy.py
- Modify: backend/superpower/skills/etf_rotation_strategy/registry.py
- Modify: backend/superpower/skills/etf_rotation_strategy/compatibility.py
- Modify: backend/superpower/skills/etf_rotation_strategy/handler.py
- Modify: configs/strategy_params.json

**Interfaces:**
- Consumes: normalized active profile, ETFHistory, ETFPositionState, medium/short modules, legacy exit/ranking.
- Produces: TrendPullbackV2Strategy, registered metadata, canonical state columns, etf_strategy_run artifact, and unchanged legacy projections.

- [ ] **Step 1: Write end-to-end strategy and holding-precedence tests**

Create tests/test_etf_trend_pullback_strategy.py:

~~~python
def test_long_decline_giant_bar_cannot_become_buy_candidate() -> None:
    history = prolonged_decline_with_giant_last_bar(rows=220)
    decision = evaluate_v2(history, holding=False)
    assert decision.medium_status.value == "do_not_participate"
    assert decision.short_entry_status.value in {"close_watch", "no_entry"}
    assert decision.buy_candidate is False
    assert "overheat" in " ".join(decision.risk_notes)


def test_close_watch_maps_to_public_watch_only_for_nonholding() -> None:
    history = customer_close_watch_history(rows=220)
    nonholding = evaluate_v2(history, holding=False)
    holding = evaluate_v2(history, holding=True)
    assert nonholding.watch_candidate is True
    assert holding.watch_candidate is False
    assert holding.short_entry_status == nonholding.short_entry_status


def test_holding_sell_takes_precedence_over_entry_evidence() -> None:
    history = can_enter_and_legacy_sell_history(rows=220)
    decision = evaluate_v2(history, holding=True)
    assert decision.short_entry_status.value == "can_enter"
    assert decision.sell_alert is True
    assert decision.buy_candidate is False
    assert decision.watch_candidate is False


def test_61_to_179_row_holding_can_sell_but_v2_states_are_unavailable() -> None:
    history = short_history_legacy_sell(rows=100)
    decision = evaluate_v2(history, holding=True)
    assert decision.medium_status.value == "data_unavailable"
    assert decision.short_entry_status.value == "data_unavailable"
    assert decision.sell_alert is True


def test_duplicate_or_invalid_rows_do_not_satisfy_180_day_minimum() -> None:
    history = history_with_valid_duplicate_and_missing_ohlcv(total_rows=182, valid_unique_rows=179)
    decision = evaluate_v2(history, holding=False)
    assert decision.medium_status.value == "data_unavailable"
    assert decision.short_entry_status.value == "data_unavailable"


def test_plugin_exception_is_explicit_and_never_falls_back_to_legacy() -> None:
    with pytest.raises(ETFStrategyRuntimeError, match="trend_pullback_v2"):
        evaluate_with_registered_strategy(RaisingTrendStrategy())
    assert legacy_fallback_call_count() == 0
~~~

The named history builders are local functions in this test file:

- prolonged_decline_with_giant_last_bar: 220 valid rows, MA20 slope below -0.003, last-day return/body/volume/MA5 distance all at or above overheat thresholds.
- customer_close_watch_history: 220 valid rows, medium unconfirmed, MA5>MA10, and daily MACD -0.02 to -0.01.
- can_enter_and_legacy_sell_history: a confirmed setup plus valid pullback evidence, with the latest close below MA5/MA10 and volume at both configured sell thresholds.
- short_history_legacy_sell: 100 valid rows with the same legacy sell shape.
- history_with_valid_duplicate_and_missing_ohlcv: literal total and valid_unique_rows arguments determine duplicate dates and one missing close.
- RaisingTrendStrategy: registered under trend_pullback_v2 and raises RuntimeError("synthetic plugin failure"); the test registry's legacy constructor increments a local counter so fallback_call_count is directly asserted.

Each builder sets all required raw and indicator columns explicitly; it does not call production policy code to manufacture the expected state.

Add a contract test asserting every output row includes strategy_id, strategy_version, medium_status, medium_reason, short_entry_status, short_entry_reason, weekly_macd_state, weekly_macd_hist, weekly_macd_preview, weekly_macd_confirmation_check, ma20_slope_5d, ma20_slope_state, ma20_flat_check, daily_macd_state, ma5_above_ma10, ma5_crossed_ma10_today, setup_date, and setup_age.

Also test that missing optional weekly preview leaves the official completed-week state usable and adds a warning, and that an existing stale-source warning is copied into the row's risk_notes/data_quality beside the two strategy states.

- [ ] **Step 2: Run end-to-end tests and verify v2 is not registered**

~~~bash
.venv/bin/python -m pytest tests/test_etf_trend_pullback_strategy.py -q
~~~

Expected: tests fail because TrendPullbackV2Strategy is missing or unregistered.

- [ ] **Step 3: Compose one historical pass and one latest decision**

strategy.py:

~~~python
class TrendPullbackV2Strategy:
    strategy_id = STRATEGY_ID
    version = STRATEGY_VERSION

    def evaluate_history(self, history: ETFHistory, params: Mapping[str, object]) -> list[ETFDecision]:
        rows = history.rows.sort_values("date").reset_index(drop=True)
        normalized_history = ETFHistory(
            code=history.code,
            name=history.name,
            rows=rows,
            as_of=history.as_of,
        )
        required = ["date", "开盘价", "最高价", "最低价", "收盘价", "成交量（万股）"]
        unique_date = ~rows["date"].duplicated(keep="last")
        complete = rows[required].notna().all(axis=1)
        valid_row = unique_date & complete
        valid_count = valid_row.astype(int).cumsum()
        minimum = int(params["medium_trend"]["minimum_history_rows"])
        medium = evaluate_medium_history(rows, params["medium_trend"])
        for index in range(len(rows)):
            if not valid_row.iloc[index] or valid_count.iloc[index] < minimum:
                medium[index] = MediumTrendResult(
                    MediumStatus.DATA_UNAVAILABLE,
                    f"valid_history_rows={valid_count.iloc[index]}; required={minimum}",
                    (),
                    ("minimum_history_rows",),
                    False,
                )
        short = evaluate_short_entry_history(
            rows,
            medium,
            params["short_entry"],
            trading_session_numbers=valid_count.tolist(),
        )
        return [
            compose_decision(normalized_history, index, medium[index], short[index], params)
            for index in range(len(rows))
        ]

    def evaluate(self, history: ETFHistory, position: ETFPositionState, params: Mapping[str, object]) -> ETFDecision:
        decision = self.evaluate_history(history, params)[-1]
        row = history.rows.sort_values("date").iloc[-1]
        sell_reasons = legacy_sell_reasons(row, params["exit"]["legacy_params"])
        sell = position.is_holding and bool(sell_reasons)
        return replace(
            decision,
            buy_candidate=decision.short_entry_status is ShortEntryStatus.CAN_ENTER and not position.is_holding and not sell,
            watch_candidate=decision.short_entry_status in WATCH_STATES and not position.is_holding and not sell,
            sell_alert=sell,
            exit_status="triggered" if sell else "not_triggered",
            score=legacy_score(row, params["ranking"]["legacy_params"]),
        )
~~~

The implementation may cache medium and short arrays by code/as_of/config hash, but it must not call evaluate on every prefix. Target one forward pass per ETF. Minimum history, setup age, confirmation window, cooldown, and expiry use trading_session_numbers, never calendar days or raw duplicate-row indexes.

Define the compatibility watch set explicitly:

~~~python
WATCH_STATES = {
    ShortEntryStatus.CLOSE_WATCH,
    ShortEntryStatus.WAITING_CONFIRMATION,
    ShortEntryStatus.WAITING_PULLBACK,
    ShortEntryStatus.OVERHEATED_DO_NOT_CHASE,
}
~~~

Add a parameterized projection test for all four states: each maps to the public watchlist only when non-holding; none maps when holding; only CAN_ENTER maps to buy_candidate; SELL_ALERT wins over both.

- [ ] **Step 4: Register v2, expose identity, and pass compatibility tests**

Add literal registry metadata:

~~~python
ETFStrategyMetadata(
    strategy_id="trend_pullback_v2",
    display_name="趋势回踩策略",
    version="2.0.0",
    default_params=DEFAULT_PROFILE,
    parameter_schema=PARAMETER_SCHEMA,
)
~~~

Add registry tests proving duplicate IDs fail, unknown IDs fail, installed metadata IDs equal KNOWN_STRATEGY_IDS, and switching between already registered constructors in the same process needs no reload/restart. Document that adding new Python code still requires one service restart to load it.

Add etf_strategy_run to context:

~~~python
context.put(
    "etf_strategy_run",
    {
        "strategy_id": normalized["active_strategy"],
        "strategy_version": strategy.version,
        "config_hash": etf_config_hash(normalized),
    },
)
~~~

Preserve the existing three positional arguments on latest_etf_signals and add only a keyword-only quality_warnings: Sequence[str] = (). handler.Skill.run extracts ETF stale-source warnings from context.get("data_quality_report") after QA, then calls the wrapper with that keyword. A pure attach_quality_warnings(decisions, warnings) uses dataclasses.replace to append each warning to risk_notes and raise data_quality from OK to WARN without changing medium/short states or projections. Audit derives and passes the same warnings from the audited source snapshot.

Extend configs/strategy_params.json additively. Preserve its current buy/sell thresholds verbatim, set active_strategy to legacy_v1 for rollout A, and include both strategy profiles and diagnostic strategies.

When reconciling the dirty main checkout, port only the verified ETF override sell_ma5_volume_ratio_min=1.2 into the isolated branch. Do not copy the dirty model_config.json or overwrite unrelated frontend/database changes.

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_trend_pullback_strategy.py tests/test_etf_legacy_characterization.py tests/test_etf_signal_output.py tests/test_dashboard_schema.py -q
~~~

Expected: v2 scenarios pass and explicit/implicit legacy parity remains green.

- [ ] **Step 5: Commit strategy composition**

~~~bash
git add backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/strategy.py backend/superpower/skills/etf_rotation_strategy/registry.py backend/superpower/skills/etf_rotation_strategy/compatibility.py backend/superpower/skills/etf_rotation_strategy/handler.py configs/strategy_params.json tests/test_etf_trend_pullback_strategy.py
git commit -m "feat: compose ETF trend pullback strategy"
~~~

---

### Task 9: Add descriptive historical diagnostics without replacing the legacy backtest

**Files:**
- Create: backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/diagnostics.py
- Create: tests/test_etf_historical_diagnostics.py
- Modify: backend/superpower/skills/etf_rotation_strategy/handler.py
- Modify: backend/superpower/agents/backtest_agent.py
- Modify: backend/superpower/skills/strategy_backtest/handler.py

**Interfaces:**
- Consumes: per-day ETFDecision sequences and OHLC rows for each diagnostic strategy.
- Produces: diagnostic_trace(decisions, bars), diagnostic_events(trace), summarize_historical_diagnostics(events, traces), etf_historical_state_traces, etf_historical_diagnostic_events, and etf_historical_diagnostics.

- [ ] **Step 1: Write exact event and forward-metric tests**

Create tests/test_etf_historical_diagnostics.py:

~~~python
import math

import pandas as pd

from superpower.skills.etf_rotation_strategy.contracts import (
    ETFDecision,
    MediumStatus,
    ShortEntryStatus,
)
from superpower.skills.etf_rotation_strategy.strategies.trend_pullback_v2.diagnostics import (
    diagnostic_trace,
    diagnostic_events,
    summarize_historical_diagnostics,
)


def bars_for_returns(closes: list[float]) -> pd.DataFrame:
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=len(close)),
            "收盘价": close,
            "最高价": close * 1.01,
            "最低价": close * 0.99,
        }
    )


def decision_sequence(states: list[str]) -> list[ETFDecision]:
    dates = pd.bdate_range("2026-01-01", periods=len(states))
    return [
        ETFDecision(
            as_of=dates[index],
            code="510001",
            name="样例ETF",
            strategy_id="trend_pullback_v2",
            strategy_version="2.0.0",
            medium_status=MediumStatus.TREND_CONFIRMED,
            short_entry_status=ShortEntryStatus(state),
            exit_status="not_triggered",
            eligible=state == "can_enter",
            buy_candidate=state == "can_enter",
            watch_candidate=state in {"close_watch", "waiting_confirmation", "waiting_pullback", "overheated_do_not_chase"},
            sell_alert=False,
            score=50.0,
            metrics={"entry_route": "breakout_confirmation" if state == "can_enter" else ""},
            data_quality="OK",
        )
        for index, state in enumerate(states)
    ]


def legacy_trace(states: list[str]) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(states))
    return pd.DataFrame(
        {
            "date": dates,
            "code": "510001",
            "name": "样例ETF",
            "strategy_id": "legacy_v1",
            "strategy_version": "1.0.0",
            "config_hash": "test-config",
            "medium_status": "not_applicable",
            "short_entry_status": states,
            "combined_state_key": ["not_applicable|" + state for state in states],
            "entry_route": "",
            "收盘价": 10.0,
            "最高价": 10.1,
            "最低价": 9.9,
        }
    )


def simultaneous_transition_trace(medium: str, short: str) -> pd.DataFrame:
    trace = legacy_trace(["no_entry", short])
    trace["strategy_id"] = "trend_pullback_v2"
    trace["medium_status"] = ["trend_not_confirmed", medium]
    trace["combined_state_key"] = trace["medium_status"] + "|" + trace["short_entry_status"]
    return trace


def false_reversal_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    states = (
        ["close_watch"]
        + ["no_entry"] * 4
        + ["can_enter"]
        + ["no_entry"] * 5
        + ["close_watch"]
        + ["no_entry"] * 11
    )
    closes = [100.0] * len(states)
    closes[10] = 110.0
    closes[11] = 100.0
    closes[21] = 90.0
    traces = diagnostic_trace(decision_sequence(states), bars_for_returns(closes))
    return diagnostic_events(traces), traces


def test_state_episode_is_counted_once_and_waiting_confirmation_is_not_event() -> None:
    decisions = decision_sequence(
        ["no_entry", "close_watch", "close_watch", "waiting_confirmation", "can_enter", "can_enter"]
    )
    trace = diagnostic_trace(decisions, bars_for_returns([10, 10, 11, 9, 10, 12]))
    events = diagnostic_events(trace)
    assert list(events["state_type"]) == ["close_watch", "can_enter"]


def test_forward_returns_and_excursions_are_exact_and_causal() -> None:
    bars = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=21),
            "收盘价": [100.0] + [110.0] * 20,
            "最高价": [100.0] + [120.0] * 20,
            "最低价": [100.0] + [90.0] * 20,
        }
    )
    event = diagnostic_events(diagnostic_trace(decision_sequence(["can_enter"] + ["no_entry"] * 20), bars)).iloc[0]
    assert event["forward_close_return_5d"] == 0.10
    assert event["maximum_favorable_excursion_5d"] == 0.20
    assert event["maximum_adverse_excursion_5d"] == -0.10


def test_incomplete_horizon_keeps_event_with_null_metric() -> None:
    bars = bars_for_returns([10.0, 10.2, 10.1])
    event = diagnostic_events(diagnostic_trace(decision_sequence(["can_enter", "no_entry", "no_entry"]), bars)).iloc[0]
    assert math.isnan(event["forward_close_return_5d"])


def test_false_reversal_definition_and_flip_frequency() -> None:
    events, traces = false_reversal_fixture()
    summary = summarize_historical_diagnostics(events, traces)
    row = summary.iloc[0]
    assert row["false_reversal_10d_count"] == 1
    assert row["false_reversal_10d_rate"] == 0.5
    assert row["state_flip_frequency"] == row["transition_count"] / max(row["valid_rows"] - 1, 1)


def test_legacy_states_are_mapped_to_comparable_event_types() -> None:
    trace = legacy_trace(["legacy_neutral", "legacy_watch", "legacy_buy"])
    events = diagnostic_events(trace)
    assert list(events["state_type"]) == ["close_watch", "can_enter"]


def test_same_day_medium_and_short_transitions_emit_two_typed_events() -> None:
    trace = simultaneous_transition_trace(medium="trend_confirmed", short="can_enter")
    events = diagnostic_events(trace)
    assert list(events["state_type"]) == ["trend_confirmed", "can_enter"]
~~~

Add comparison tests proving legacy_v1 and trend_pullback_v2 traces are evaluated over the same code/date bar universe even though their event dates may differ, a diagnostic strategy cannot change live output, and breakout_confirmation versus pullback_confirmation outcomes appear as separate groups.

- [ ] **Step 2: Run tests and verify diagnostics are absent**

~~~bash
.venv/bin/python -m pytest tests/test_etf_historical_diagnostics.py -q
~~~

Expected: collection fails because diagnostics.py does not exist.

- [ ] **Step 3: Implement transition extraction and forward outcomes**

Use these constants and formulas:

~~~python
EVENT_STATES = {
    "close_watch",
    "trend_confirmed",
    "overheated_do_not_chase",
    "waiting_pullback",
    "can_enter",
}
LEGACY_EVENT_MAP = {
    "legacy_watch": "close_watch",
    "legacy_buy": "can_enter",
}
HORIZONS = (5, 10, 20)


def _outcomes(bars: pd.DataFrame, index: int) -> dict[str, float | None]:
    signal_close = float(bars.iloc[index]["收盘价"])
    result: dict[str, float | None] = {}
    for horizon in HORIZONS:
        future = bars.iloc[index + 1 : index + horizon + 1]
        if len(future) < horizon:
            result[f"forward_close_return_{horizon}d"] = None
            result[f"maximum_favorable_excursion_{horizon}d"] = None
            result[f"maximum_adverse_excursion_{horizon}d"] = None
            continue
        result[f"forward_close_return_{horizon}d"] = float(future.iloc[-1]["收盘价"]) / signal_close - 1
        result[f"maximum_favorable_excursion_{horizon}d"] = float(future["最高价"].max()) / signal_close - 1
        result[f"maximum_adverse_excursion_{horizon}d"] = float(future["最低价"].min()) / signal_close - 1
    return result
~~~

The trace stores one row for every valid unique trading date with strategy ID/version, code/name, medium state, short state, combined_state_key, entry_route, and config_hash. Emit an event when either the short state transitions into an EVENT_STATES value or medium transitions into trend_confirmed. Map legacy_watch to close_watch and legacy_buy to can_enter for comparable event labels while retaining strategy_id. Store event_date, state_type, entry_route, and all outcomes. For false_reversal_10d, inspect the next ten trace rows for can_enter/legacy_buy and require ten-day forward return <= 0.

summarize_historical_diagnostics receives both events and traces. Per strategy/state/entry_route/horizon it outputs event_count, complete_horizon_count, mean, median, p25, p75, positive_return_rate, MFE distribution, and negative MAE/drawdown distribution. It computes valid_rows and transitions from consecutive combined_state_key trace rows, then state_flip_frequency = transitions / max(valid_rows - 1, 1). This makes flip frequency computable even when no event fires.

- [ ] **Step 4: Add artifacts while keeping the old P&L diagnostic separate**

handler.Skill.run evaluates only normalized diagnostic_strategies for diagnostics and writes:

~~~python
context.put("etf_historical_diagnostic_events", event_frame)
context.put("etf_historical_diagnostics", summary_frame)
context.put("etf_historical_state_traces", trace_frame)
~~~

Keep current backtest_summary, backtest_trades, top-level backtestSummary, and nested etf.backtest_diagnostics keys. Name only the new v2 material 历史表现诊断; do not claim executable returns. Ensure evaluate_history is called once per symbol and strategy.

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_historical_diagnostics.py tests/test_etf_legacy_characterization.py tests/test_run_daily_audit.py -q
~~~

Expected: diagnostics pass and the existing legacy backtest tests remain green.

- [ ] **Step 5: Commit historical diagnostics**

~~~bash
git add backend/superpower/skills/etf_rotation_strategy/strategies/trend_pullback_v2/diagnostics.py backend/superpower/skills/etf_rotation_strategy/handler.py backend/superpower/agents/backtest_agent.py backend/superpower/skills/strategy_backtest/handler.py tests/test_etf_historical_diagnostics.py
git commit -m "feat: add ETF historical state diagnostics"
~~~

---

### Task 10: Add run-snapshotted configuration and a safe strategy API

**Files:**
- Create: tests/test_etf_strategy_api.py
- Modify: backend/superpower/agents/config_agent.py
- Modify: backend/superpower/skills/source_archive/handler.py
- Modify: backend/superpower/server/app.py
- Modify: tests/test_server_refresh.py
- Modify: configs/strategy_params.json

**Interfaces:**
- Consumes: GET/POST /api/strategy-params and registry metadata.
- Produces: {status, params, etfStrategies, etfConfigHash}, a validated deep-merge save, context artifacts etf_config_snapshot plus etf_config_hash, and a secret-free archived ETF strategy snapshot.

- [ ] **Step 1: Write API contract and run-snapshot tests**

Create tests/test_etf_strategy_api.py:

~~~python
import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import ThreadingHTTPServer

import pytest

from superpower.server.app import ResearchDashboardHandler


def valid_strategy_params() -> dict:
    return {
        "etf": {
            "active_strategy": "legacy_v1",
            "diagnostic_strategies": ["legacy_v1", "trend_pullback_v2"],
            "buy_volume_ratio_min": 1.1,
            "sell_ma10_volume_ratio_min": 1.2,
            "sell_ma5_volume_ratio_min": 1.2,
            "score_weights": {"trend": 0.35, "macd": 0.25, "volume": 0.25, "share_change": 0.15},
            "strategy_profiles": {"legacy_v1": {}, "trend_pullback_v2": {}},
        },
        "tl": {},
        "convertible_bond": {"min_price": 100, "price_limit": 140},
        "risk": {},
    }


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class JsonResponse:
    status_code: int
    payload: dict

    def json(self) -> dict:
        return self.payload


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def get(self, path: str) -> JsonResponse:
        return self._request(path, None)

    def post(self, path: str, json: dict) -> JsonResponse:
        return self._request(path, json)

    def _request(self, path: str, payload: dict | None) -> JsonResponse:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            return JsonResponse(exc.code, json.loads(exc.read().decode("utf-8")))
        return JsonResponse(response.status, json.loads(response.read().decode("utf-8")))


@pytest.fixture
def strategy_file(tmp_path):
    path = tmp_path / "configs" / "strategy_params.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(valid_strategy_params(), ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def dashboard_file(tmp_path):
    path = tmp_path / "outputs" / "latest" / "dashboard.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"marker":"generated-before-save"}', encoding="utf-8")
    return path


@pytest.fixture
def client(tmp_path, strategy_file, dashboard_file):
    handler = type("TestResearchDashboardHandler", (ResearchDashboardHandler,), {})
    handler.root_dir = tmp_path
    handler.etf_file = tmp_path / "etf.xlsx"
    handler.tl_file = tmp_path / "tl.xlsx"
    handler.cb_file = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield ApiClient(f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_get_strategy_params_returns_registry_metadata_and_hash(client) -> None:
    response = client.get("/api/strategy-params")
    payload = response.json()
    assert payload["status"] == "success"
    assert {item["strategy_id"] for item in payload["etfStrategies"]} == {"legacy_v1", "trend_pullback_v2"}
    assert len(payload["etfConfigHash"]) == 64


def test_post_deep_merges_and_preserves_dormant_profile(client, strategy_file) -> None:
    original = read_json(strategy_file)
    original["etf"]["strategy_profiles"]["future_v3"] = {"kept": True}
    write_json(strategy_file, original)
    response = client.post(
        "/api/strategy-params",
        json={"params": {"etf": {"active_strategy": "trend_pullback_v2"}}},
    )
    assert response.status_code == 200
    saved = read_json(strategy_file)
    assert saved["etf"]["strategy_profiles"]["future_v3"] == {"kept": True}
    assert saved["tl"] == original["tl"]


def test_bare_patch_remains_supported_for_new_clients(client) -> None:
    response = client.post("/api/strategy-params", json={"etf": {"active_strategy": "trend_pullback_v2"}})
    assert response.status_code == 200


def test_successful_save_does_not_mutate_generated_dashboard(client, dashboard_file) -> None:
    before = dashboard_file.read_bytes()
    response = client.post(
        "/api/strategy-params",
        json={"params": {"etf": {"active_strategy": "trend_pullback_v2"}}},
    )
    assert response.status_code == 200
    assert dashboard_file.read_bytes() == before


def test_unknown_strategy_rejected_without_file_or_dashboard_change(client, strategy_file, dashboard_file) -> None:
    config_before = strategy_file.read_bytes()
    dashboard_before = dashboard_file.read_bytes()
    response = client.post("/api/strategy-params", json={"etf": {"active_strategy": "missing"}})
    assert response.status_code == 400
    assert strategy_file.read_bytes() == config_before
    assert dashboard_file.read_bytes() == dashboard_before


def test_unknown_diagnostic_strategy_is_rejected(client) -> None:
    response = client.post(
        "/api/strategy-params",
        json={"params": {"etf": {"diagnostic_strategies": ["missing"]}}},
    )
    assert response.status_code == 400


def test_rejected_save_returns_last_confirmed_selection(client) -> None:
    response = client.post(
        "/api/strategy-params",
        json={"params": {"etf": {"active_strategy": "trend_pullback_v2", "strategy_profiles": {"trend_pullback_v2": {"short_entry": {"pullback_max_age": -1}}}}}},
    )
    assert response.status_code == 400
    assert response.json()["params"]["etf"]["active_strategy"] == "legacy_v1"
~~~

Add a ConfigAgent test that mutating strategy_params.json after execute does not change context.get("etf_config_snapshot") or its hash.

- [ ] **Step 2: Run API tests and observe the old response/save behavior**

~~~bash
.venv/bin/python -m pytest tests/test_etf_strategy_api.py tests/test_server_refresh.py -q
~~~

Expected: failures for missing metadata, shallow/whole-file save behavior, and absent run snapshot.

- [ ] **Step 3: Snapshot normalized configuration at run start**

In ConfigAgent.execute:

~~~python
raw_strategy_params = json.loads(context.get("strategy_params_file").read_text(encoding="utf-8"))
normalized_etf = normalize_etf_config(raw_strategy_params)
strategy_params = deepcopy(raw_strategy_params)
strategy_params["etf"] = normalized_etf
context.put("strategy_params", strategy_params)
context.put("etf_config_snapshot", deepcopy(normalized_etf))
context.put("etf_config_hash", etf_config_hash(normalized_etf))
~~~

SourceArchive writes only normalized_etf to data/archive/<run_id>/etf_strategy_config.json with its SHA-256 hash in the source manifest. It must never archive model_config.json or any API credential. No later agent or audit may reread configs/strategy_params.json for ETF logic during that run.

- [ ] **Step 4: Implement API metadata, validation, deep merge, and atomic file replacement**

GET response:

~~~python
raw = self._load_strategy_params()
normalized = normalize_etf_config(raw)
response_params = deepcopy(raw)
response_params["etf"] = normalized
self._send_json(
    {
        "status": "success",
        "params": response_params,
        "etfStrategies": [asdict(item) for item in default_registry().metadata()],
        "etfConfigHash": etf_config_hash(normalized),
    }
)
~~~

POST flow:

~~~python
current = self._load_strategy_params()
payload = self._read_json_body()
patch = payload.get("params", payload)
candidate = merge_strategy_params(current, patch)
normalized = normalize_etf_config(candidate)
validate_all_etf_profiles(normalized)
temporary = strategy_path.with_suffix(".json.tmp")
temporary.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temporary, strategy_path)
~~~

Successful POST and ETFConfigurationError responses both use the same normalized response_params shape as GET. On ETFConfigurationError, return HTTP 400 with status=failed, message, current params, registry metadata, and current hash. Never write the temporary file before the candidate validates. Arrays replace; mappings merge recursively.

Run:

~~~bash
.venv/bin/python -m pytest tests/test_etf_strategy_api.py tests/test_server_refresh.py tests/test_etf_config.py -q
~~~

Expected: all tests pass.

- [ ] **Step 5: Commit configuration governance**

~~~bash
git add backend/superpower/agents/config_agent.py backend/superpower/skills/source_archive/handler.py backend/superpower/server/app.py configs/strategy_params.json tests/test_etf_strategy_api.py tests/test_server_refresh.py
git commit -m "feat: add safe ETF strategy configuration API"
~~~

---

### Task 11: Publish a complete run bundle with an atomic latest pointer

**Files:**
- Create: backend/superpower/runtime/publication.py
- Create: backend/superpower/cli/migrate_publication.py
- Create: tests/test_atomic_publication.py
- Modify: backend/superpower/cli/run_daily.py
- Modify: backend/superpower/server/app.py
- Modify: backend/superpower/audit/latest.py
- Modify: backend/superpower/skills/report_generation/handler.py
- Modify: backend/superpower/db/ingest.py
- Modify: tests/test_run_daily_audit.py
- Modify: tests/test_server_refresh.py

**Interfaces:**
- Consumes: an immutable staged run bundle, the run-start configuration snapshot/hash, audit result, and database transaction.
- Produces: StagedPublication, recover_publication, an atomic outputs/latest symlink switch, and backward-compatible optional arguments on audit_latest and ingest_dashboard.

- [ ] **Step 1: Write failure, concurrency, recovery, and audit-mode tests**

Create tests/test_atomic_publication.py. Its seed_bundle helper writes dashboard.json, market_indicators.json, audit.json, and a report workbook marker into outputs/runs/<run_id>; seed_latest creates outputs/latest as a symlink to that complete directory.

Required tests:

~~~python
def test_strict_audit_failure_keeps_old_latest_target() -> None:
    assert latest_target_after("strict_audit_fail") == "run-old"


def test_non_strict_audit_failure_publishes_partial_success_bundle() -> None:
    result = publish_scenario("non_strict_audit_fail")
    assert result.latest_target == "run-new"
    assert "QA audit status=FAIL" in result.dashboard["run_info"]["warnings"]


def test_plugin_exception_never_changes_latest_target() -> None:
    assert latest_target_after("plugin_exception") == "run-old"


def test_database_failure_restores_old_pointer() -> None:
    assert latest_target_after("database_failure") == "run-old"


def test_success_switches_one_pointer_to_one_complete_bundle() -> None:
    result = publish_scenario("success")
    assert result.latest_target == "run-new"
    assert {read_marker(result.latest / name) for name in result.bundle_files} == {"run-new"}


def test_reader_never_resolves_an_incomplete_bundle_during_switch() -> None:
    observations = read_resolved_bundle_while_switching()
    assert observations
    assert all(item in {"run-old", "run-new"} for item in observations)


def test_recovery_reverts_pointer_when_process_died_before_db_commit() -> None:
    result = recover_scenario(journal_phase="pointer_switched", db_run_status="running")
    assert result.latest_target == "run-old"


def test_recovery_keeps_pointer_when_database_commit_succeeded() -> None:
    result = recover_scenario(journal_phase="pointer_switched", db_run_status="success")
    assert result.latest_target == "run-new"
~~~

Also add a one-time migration test: with the local server explicitly stopped, an existing real outputs/latest directory and its dashboard-referenced report workbook are assembled into outputs/runs/legacy-<timestamp>, internal report/market paths are rewritten to that bundle, and outputs/latest is replaced by a symlink before publication-enabled code is started. Normal refresh code must assert that this migration is already complete; it never performs the non-atomic directory-to-symlink conversion while readers are live.

In tests/test_run_daily_audit.py add two modes: non-strict FAIL preserves current partial-success publication semantics; --strict-audit FAIL exits nonzero and leaves latest unchanged. Add a config-race test that modifies the saved file after ConfigAgent and proves audit still receives the original params_snapshot, strategy ID, version, and hash.

- [ ] **Step 2: Run the focused tests and confirm direct latest writes fail them**

~~~bash
.venv/bin/python -m pytest tests/test_atomic_publication.py tests/test_run_daily_audit.py tests/test_server_refresh.py -q
~~~

Expected: tests fail because report generation currently writes files directly into outputs/latest and no recovery journal/pointer exists.

- [ ] **Step 3: Implement immutable bundles and last-step pointer switching**

Use this layout:

~~~text
outputs/
  runs/
    <run_id>/
      dashboard.json
      market_indicators.json
      audit.json
      AI投研日报-Superpower-<date>.xlsx
  latest -> runs/<published_run_id>
  .staging/<run_id>/
  .publication/<run_id>.json
~~~

publication.py defines:

~~~python
@dataclass
class StagedPublication:
    outputs_dir: Path
    run_id: str
    stage_bundle: Path
    final_bundle: Path
    previous_target: str
    journal_path: Path

    @classmethod
    def create(cls, outputs_dir: Path, run_id: str) -> "StagedPublication":
        require_latest_pointer(outputs_dir)
        stage = outputs_dir / ".staging" / run_id
        stage.mkdir(parents=True, exist_ok=False)
        previous = os.readlink(outputs_dir / "latest")
        journal = outputs_dir / ".publication" / f"{run_id}.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        return cls(outputs_dir, run_id, stage, outputs_dir / "runs" / run_id, previous, journal)

    def finalize_bundle(self) -> Path:
        self._rewrite_dashboard_paths(self.final_bundle)
        self._require_complete_bundle()
        self.final_bundle.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.stage_bundle, self.final_bundle)
        self._write_phase("bundle_ready")
        return self.final_bundle

    def switch_latest(self) -> None:
        temporary = self.outputs_dir / f".latest-{self.run_id}"
        temporary.symlink_to(Path("runs") / self.run_id, target_is_directory=True)
        os.replace(temporary, self.outputs_dir / "latest")
        self._write_phase("pointer_switched")

    def restore_latest(self) -> None:
        temporary = self.outputs_dir / f".latest-restore-{self.run_id}"
        temporary.symlink_to(self.previous_target, target_is_directory=True)
        os.replace(temporary, self.outputs_dir / "latest")
        self._write_phase("pointer_restored")
~~~

All four artifacts live inside one immutable run directory; no report is moved separately. migrate_latest_to_pointer is a one-time maintenance command run with the server stopped; require_latest_pointer fails closed during normal refresh if migration was skipped. recover_publication runs before a daily workflow and before the local server starts: when the journal says pointer_switched, query import_runs for run_id; keep the pointer only when DB status is success, otherwise restore previous_target.

With the server stopped, execute the migration once:

~~~bash
PYTHONPATH=backend .venv/bin/python -m superpower.cli.migrate_publication --root-dir "$PWD"
~~~

Expected: the old dashboard's report date, rows, and artifact contents remain available through the new symlink, every rewritten path exists, and a second invocation is an idempotent no-op.

Extend ingest_dashboard with optional callbacks while preserving existing callers:

~~~python
def ingest_dashboard(
    root_dir: Path,
    run_id: str,
    dashboard_path: Path,
    *,
    before_commit: Callable[[], None] | None = None,
    on_commit_failure: Callable[[], None] | None = None,
) -> dict[str, Any]:
    # Existing inserts remain inside the current transaction.
    if before_commit is not None:
        before_commit()
    try:
        connection.commit()
    except Exception:
        connection.rollback()
        if on_commit_failure is not None:
            on_commit_failure()
        raise
~~~

The actual edit keeps the existing insert order and failed import-run record. The callback is invoked only after all inserts and the success-status update are prepared, so latest switches at the last visible file step. After a successful commit, mark the journal db_committed and then complete.

- [ ] **Step 4: Generate/audit in staging, preserve audit semantics, and verify identity**

report_generation writes dashboard, market indicators, report workbook, and later audit into context.get("publication_bundle_dir") when present; without that artifact its existing output paths remain compatible.

run_daily orchestration:

~~~python
publication = StagedPublication.create(output_dir, run_id)
context.put("publication_bundle_dir", publication.stage_bundle)
workflow_result = AgentOrchestrator(build_daily_workflow(), progress_callback=_emit_progress).run(context)
if workflow_result.status == "failed":
    publication.abort()
    raise SystemExit(1)

qa_result = (
    {"status": "SKIPPED", "checks": []}
    if args.skip_audit
    else audit_latest(
        root_dir,
        args.etf_file,
        args.tl_file,
        cb_file,
        dashboard_path=publication.stage_bundle / "dashboard.json",
        params_snapshot=context.get("strategy_params"),
        audit_output_path=publication.stage_bundle / "audit.json",
    )
)
(publication.stage_bundle / "audit.json").write_text(
    json.dumps(qa_result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
if qa_result["status"] == "FAIL" and args.strict_audit:
    publication.abort()
    raise SystemExit(1)
if qa_result["status"] == "FAIL":
    append_audit_warnings(publication.stage_bundle / "dashboard.json", qa_result)

final_bundle = publication.finalize_bundle()
ingest_result = ingest_dashboard(
    root_dir,
    run_id,
    final_bundle / "dashboard.json",
    before_commit=publication.switch_latest,
    on_commit_failure=publication.restore_latest,
)
publication.mark_db_committed()
publication.complete()
~~~

audit_latest keeps its current positional signature and adds keyword-only dashboard_path=None, params_snapshot=None, and audit_output_path=None. It uses add_etf_indicators, the snapshot-selected registry strategy, and checks module/row strategy_id, strategy_version, config_hash, canonical state projections, and report columns. It never rereads a newer ETF config when params_snapshot is supplied.

Print only final outputs/latest paths after commit. The server's existing /outputs/latest URLs continue to work through the symlink.

- [ ] **Step 5: Run publication regression and commit**

~~~bash
.venv/bin/python -m pytest tests/test_atomic_publication.py tests/test_run_daily_audit.py tests/test_server_refresh.py tests/test_dashboard_schema.py -q
git diff --check
git add backend/superpower/runtime/publication.py backend/superpower/cli/migrate_publication.py backend/superpower/cli/run_daily.py backend/superpower/server/app.py backend/superpower/audit/latest.py backend/superpower/skills/report_generation/handler.py backend/superpower/db/ingest.py tests/test_atomic_publication.py tests/test_run_daily_audit.py tests/test_server_refresh.py
git commit -m "fix: publish complete research bundles atomically"
~~~

---

### Task 12: Build the ETF strategy selector and saved-versus-generated state UX

**Files:**
- Create: frontend/assets/strategy-config.js
- Create: tests/frontend/strategy-config.test.js
- Modify: frontend/index.html
- Modify: frontend/assets/app.js
- Modify: frontend/assets/styles.css
- Test: tests/test_etf_strategy_api.py

**Interfaces:**
- Consumes: strategy API response and generated dashboard strategy identity.
- Produces: deepMerge, normalizeStrategyResponse, generatedResultState, schema-driven ETF parameter controls, and a selector that restores the server-confirmed value after rejected saves.

- [ ] **Step 1: Write dependency-free frontend state tests**

Create tests/frontend/strategy-config.test.js:

~~~javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  deepMerge,
  normalizeStrategyResponse,
  generatedResultState,
} = require("../../frontend/assets/strategy-config.js");

test("deepMerge preserves dormant profiles and replaces arrays", () => {
  const current = {
    etf: {
      diagnostic_strategies: ["legacy_v1"],
      strategy_profiles: { future_v3: { kept: true } },
    },
  };
  const patch = { etf: { diagnostic_strategies: ["trend_pullback_v2"] } };
  const merged = deepMerge(current, patch);
  assert.deepEqual(merged.etf.diagnostic_strategies, ["trend_pullback_v2"]);
  assert.deepEqual(merged.etf.strategy_profiles.future_v3, { kept: true });
});

test("normalizeStrategyResponse keeps a server-confirmed selection", () => {
  const state = normalizeStrategyResponse({
    status: "success",
    params: { etf: { active_strategy: "legacy_v1" } },
    etfStrategies: [{ strategy_id: "legacy_v1", display_name: "原始策略", version: "1.0.0" }],
    etfConfigHash: "abc",
  });
  assert.equal(state.confirmedStrategyId, "legacy_v1");
  assert.equal(state.confirmedStrategyVersion, "1.0.0");
  assert.equal(state.savedConfigHash, "abc");
});

test("saved config newer than dashboard is shown as waiting refresh", () => {
  assert.equal(
    generatedResultState(
      { savedConfigHash: "new", confirmedStrategyId: "trend_pullback_v2" },
      { config_hash: "old", strategy_id: "legacy_v1", strategy_version: "1.0.0" },
    ).status,
    "saved_waiting_refresh",
  );
});

test("matching hash is shown as generated and current", () => {
  assert.equal(
    generatedResultState(
      { savedConfigHash: "same", confirmedStrategyId: "trend_pullback_v2", confirmedStrategyVersion: "2.0.0" },
      { config_hash: "same", strategy_id: "trend_pullback_v2", strategy_version: "2.0.0" },
    ).status,
    "current",
  );
});

test("diagnostic selection cannot mutate active strategy", () => {
  const current = { etf: { active_strategy: "legacy_v1", diagnostic_strategies: ["legacy_v1"] } };
  const merged = deepMerge(current, { etf: { diagnostic_strategies: ["legacy_v1", "trend_pullback_v2"] } });
  assert.equal(merged.etf.active_strategy, "legacy_v1");
});
~~~

- [ ] **Step 2: Run Node tests and verify the pure module is missing**

~~~bash
node --test tests/frontend/strategy-config.test.js
~~~

Expected: failure because frontend/assets/strategy-config.js does not exist.

- [ ] **Step 3: Implement the pure UMD state module**

Create frontend/assets/strategy-config.js:

~~~javascript
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ETFStrategyConfig = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function clone(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  }

  function deepMerge(current, patch) {
    if (Array.isArray(patch)) return clone(patch);
    if (!patch || typeof patch !== "object") return patch;
    const output = current && typeof current === "object" && !Array.isArray(current) ? clone(current) : {};
    Object.entries(patch).forEach(([key, value]) => {
      output[key] = deepMerge(output[key], value);
    });
    return output;
  }

  function normalizeStrategyResponse(payload) {
    const params = clone(payload.params || {});
    const confirmedStrategyId = params.etf?.active_strategy || "legacy_v1";
    const selected = (payload.etfStrategies || []).find((item) => item.strategy_id === confirmedStrategyId);
    return {
      params,
      strategies: clone(payload.etfStrategies || []),
      confirmedStrategyId,
      confirmedStrategyVersion: selected?.version || "",
      savedConfigHash: payload.etfConfigHash || "",
    };
  }

  function generatedResultState(saved, generated) {
    if (!generated || !generated.config_hash) return { status: "not_generated", label: "尚未生成策略结果" };
    if (
      saved.savedConfigHash !== generated.config_hash
      || saved.confirmedStrategyId !== generated.strategy_id
      || saved.confirmedStrategyVersion !== generated.strategy_version
    ) {
      return { status: "saved_waiting_refresh", label: "已保存，待刷新后生效" };
    }
    return { status: "current", label: "当前结果已按此策略生成" };
  }

  return { deepMerge, normalizeStrategyResponse, generatedResultState };
});
~~~

Run:

~~~bash
node --test tests/frontend/strategy-config.test.js
~~~

Expected: five tests pass.

- [ ] **Step 4: Wire selector, dynamic profile controls, rejection rollback, and two state columns**

Add strategy-config.js before app.js in frontend/index.html. Add these stable hooks:

~~~html
<select id="etf-strategy-select"></select>
<div id="etf-generated-strategy"></div>
<div id="etf-strategy-refresh-state" role="status"></div>
<div id="etf-strategy-params"></div>
<label>
  <input id="etf-diagnostics-enabled" type="checkbox">
  对比旧版与趋势回踩历史诊断
</label>
~~~

In app.js keep serverStrategyState separate from editable draft:

~~~javascript
let serverStrategyState = null;

async function loadStrategyParams() {
  const response = await fetch("/api/strategy-params?ts=" + Date.now(), { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "策略参数读取失败");
  serverStrategyState = ETFStrategyConfig.normalizeStrategyResponse(payload);
  renderStrategyParams(serverStrategyState);
}

async function saveStrategyParams() {
  const draft = collectStrategyDraft(serverStrategyState.params);
  const response = await fetch("/api/strategy-params", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params: draft }),
  });
  const payload = await response.json();
  serverStrategyState = ETFStrategyConfig.normalizeStrategyResponse(payload);
  renderStrategyParams(serverStrategyState);
  if (!response.ok) throw new Error(payload.message || "策略参数保存失败");
  renderStrategyRefreshState();
}
~~~

collectStrategyDraft handles the string selector separately; do not pass it through the current numeric input coercion. Numeric controls come from parameter_schema, enforce min/max/step client-side, and the server remains authoritative. ETF tables and detail panels add 中期趋势状态 and 短期入场状态 side by side. Preserve the user's existing CB table formatting changes when integrating app.js/styles/index.

Run:

~~~bash
node --check frontend/assets/strategy-config.js
node --check frontend/assets/app.js
node --test tests/frontend/strategy-config.test.js
.venv/bin/python -m pytest tests/test_etf_strategy_api.py tests/test_dashboard_schema.py -q
~~~

Expected: all checks pass.

- [ ] **Step 5: Commit the strategy UX**

~~~bash
git add frontend/assets/strategy-config.js frontend/index.html frontend/assets/app.js frontend/assets/styles.css tests/frontend/strategy-config.test.js
git commit -m "feat: add ETF strategy selection workflow"
~~~

---

### Task 13: Update reports, storage, chat, and PDF to consume canonical ETF evidence

**Files:**
- Modify: backend/superpower/agents/report_agent.py
- Modify: backend/superpower/skills/report_generation/handler.py
- Modify: backend/superpower/db/ingest.py
- Modify: backend/superpower/db/repositories.py
- Modify: backend/superpower/chat/tools.py
- Modify: backend/superpower/chat/orchestrator.py
- Modify: backend/superpower/chat/rulebook.py
- Modify: backend/superpower/skills/research_explanation/handler.py
- Modify: backend/superpower/skills/ai_research_committee/handler.py
- Modify: backend/superpower/tools/pdf_report.py
- Modify: tests/test_dashboard_schema.py
- Modify: tests/test_chat_etf_detail.py
- Modify: tests/test_commercial_components.py
- Modify: tests/test_report_text_safety.py
- Create: tests/test_etf_db_payload.py

**Interfaces:**
- Consumes: etf_strategy_run, canonical ETF rows, historical diagnostic summary/events.
- Produces: dashboard.etf.strategy identity, simultaneous state fields across outputs, and explanations that never invent or override deterministic signals.

- [ ] **Step 1: Write failing downstream contract tests**

In the existing test_stable_dashboard_schema_has_required_top_level_keys, put etf_strategy_run, etf_historical_diagnostics, and etf_historical_diagnostic_events into context, pass one canonical v2 row as etf_all, and append these assertions to its existing payload variable:

~~~python
assert payload["etf"]["strategy"] == {
    "strategy_id": "trend_pullback_v2",
    "strategy_version": "2.0.0",
    "config_hash": payload["etf"]["strategy"]["config_hash"],
}
assert len(payload["etf"]["strategy"]["config_hash"]) == 64
for row in payload["etf"]["all_signals"]:
        assert "medium_status" in row
        assert "short_entry_status" in row
        assert "strategy_id" in row

assert "backtest_diagnostics" in payload["etf"]
assert "historical_diagnostics" in payload["etf"]
assert "historical_diagnostic_events" in payload["etf"]
~~~

In the report-generation integration test, separately assert the existing top-level keys etfBuyCandidates, etfWatchlist, etfSellAlerts, and backtestSummary remain present.

Extend tests/test_chat_etf_detail.py to assert an ETF answer includes active strategy ID, medium status, short-entry status, weekly MACD confirmation, MA20 slope check, and risk note, while retaining the investment disclaimer. Add PDF/report tests for the same labels.

Create tests/test_etf_db_payload.py with a neutral v2 all-signal row, ingest it, and assert DatabaseRepository.asset_detail(code) returns strategy_id, medium_status, short_entry_status, weekly_macd_state, and ma20_slope_state even though no entry/watch/exit row exists.

- [ ] **Step 2: Run downstream tests and observe missing canonical fields**

~~~bash
.venv/bin/python -m pytest tests/test_dashboard_schema.py tests/test_chat_etf_detail.py tests/test_commercial_components.py tests/test_report_text_safety.py -q
~~~

Expected: new assertions fail while legacy keys still pass.

- [ ] **Step 3: Add identity and diagnostics to dashboard/workbook/storage**

ReportAgent requires etf_strategy_run, etf_historical_diagnostics, and etf_historical_diagnostic_events. In report_generation, run this update immediately after the existing dashboard_payload.update call that merges _stable_dashboard_schema, so the existing nested ETF object is extended rather than replaced:

~~~python
dashboard_payload["etf"].update(
    {
        "strategy": context.get("etf_strategy_run"),
        "all_signals": records(etf_all),
        "historical_diagnostics": records(context.get("etf_historical_diagnostics")),
        "historical_diagnostic_events": records(context.get("etf_historical_diagnostic_events"), limit=1000),
    }
)
~~~

Add workbook sheets ETF策略状态说明, ETF历史表现诊断, and ETF诊断事件. Keep all old sheet names. Include the new indicator columns in market_indicators.json rather than dropping them.

In db/ingest.py:

1. Keep etf_daily_signals limited to current entry/watch/exit projections.
2. Include dashboard.etf.all_signals when upserting asset_master so neutral/data_unavailable ETFs remain discoverable.
3. Merge each latest canonical all-signal row into the matching etf_daily_bars.payload_json; insert a latest bar payload when a code has no detail-history row.
4. Keep the complete dashboard, including all_signals, in daily_reports.payload_json.
5. Make DatabaseRepository.asset_detail prefer the latest bar payload's canonical states and fall back to daily_reports.payload_json.

Do not modify schema.sql in this release.

- [ ] **Step 4: Replace hard-coded legacy explanations with canonical evidence**

Chat and explanation payloads use:

~~~python
ETF_EVIDENCE_FIELDS = (
    "strategy_id",
    "strategy_version",
    "medium_status",
    "medium_reason",
    "short_entry_status",
    "short_entry_reason",
    "weekly_macd_confirmation_check",
    "ma20_flat_check",
    "risk_notes",
)
~~~

The rulebook describes both installed strategies from registry metadata. For legacy_v1, say 中期状态不适用 and show current legacy evidence. For v2, explain that close_watch is observation only, can_enter requires confirmed medium trend, and no result is a guaranteed-return instruction. LLM review can restate evidence but cannot change status, buy_candidate, watch_candidate, or sell_alert.

Update PDF sections to show active strategy/version/hash and columns 中期趋势状态 / 短期入场状态. Run:

~~~bash
.venv/bin/python -m pytest tests/test_dashboard_schema.py tests/test_chat_etf_detail.py tests/test_etf_db_payload.py tests/test_commercial_components.py tests/test_report_text_safety.py tests/test_cb_ranking_output.py tests/test_tl_status_output.py -q
~~~

Expected: all ETF and unchanged-asset tests pass.

- [ ] **Step 5: Commit downstream integration**

~~~bash
git add backend/superpower/agents/report_agent.py backend/superpower/skills/report_generation/handler.py backend/superpower/db/ingest.py backend/superpower/db/repositories.py backend/superpower/chat/tools.py backend/superpower/chat/orchestrator.py backend/superpower/chat/rulebook.py backend/superpower/skills/research_explanation/handler.py backend/superpower/skills/ai_research_committee/handler.py backend/superpower/tools/pdf_report.py tests/test_dashboard_schema.py tests/test_chat_etf_detail.py tests/test_etf_db_payload.py tests/test_commercial_components.py tests/test_report_text_safety.py
git commit -m "feat: expose ETF strategy states across outputs"
~~~

---

### Task 14: Document, verify, and roll out with legacy as the default

**Files:**
- Modify: backend/superpower/skills/etf_rotation_strategy/SKILL.md
- Modify: backend/superpower/skills/technical_indicators/SKILL.md
- Modify: backend/superpower/skills/strategy_backtest/SKILL.md
- Modify: backend/superpower/skills/report_generation/SKILL.md
- Modify: README.md
- Modify: docs/ETF_MODEL.md
- Modify: docs/STRATEGY_PARAMETERS.md
- Modify: docs/DASHBOARD_SCHEMA.md
- Modify: docs/FRONTEND_GUIDE.md
- Modify: docs/CLIENT_PRODUCT_GUIDE.md
- Modify: docs/REPORTING_POLICY.md
- Modify: docs/superpowers/specs/2026-07-10-etf-strategy-plugin-v2-design.md
- Modify: configs/strategy_params.json
- Test: full repository and real-data daily workflow

**Interfaces:**
- Consumes: completed plugin implementation and current Wind input files.
- Produces: user/developer instructions, verified legacy and v2 bundles, comparison evidence, and reversible rollout.

- [ ] **Step 1: Add concise user and developer documentation**

Document this exact user flow:

~~~text
策略参数 → ETF策略 → 选择策略 → 保存 → 刷新数据

“已保存，待刷新后生效”表示配置已经保存，但页面仍显示上一次成功生成的结果。
刷新成功后，ETF结果同时显示“中期趋势状态”和“短期入场状态”。
刷新失败时，系统继续保留上一次成功结果。
~~~

Document this exact developer flow:

~~~text
1. 在 strategies/ 下新增策略包。
2. 实现 ETFStrategy.evaluate 与 evaluate_history。
3. 提供 strategy_id、version、default_params、parameter_schema。
4. 在 ETFStrategyRegistry 中显式注册。
5. 补齐合约、行为、失败和兼容性测试。
6. 重启服务一次；之后切换已注册策略只需保存并刷新。
~~~

State that historical_diagnostics is descriptive, not a P&L backtest. Mark the design spec status as Implemented and verified only after every command below passes.

- [ ] **Step 2: Run static and automated verification**

~~~bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q backend/superpower
node --check frontend/assets/strategy-config.js
node --check frontend/assets/app.js
node --test tests/frontend/strategy-config.test.js
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/smoke.py
git diff --check
~~~

Expected: all pytest and Node tests pass, smoke exits zero, compileall emits no error, and git diff --check emits no output.

- [ ] **Step 3: Run the real daily workflow once per active strategy**

Run with the supplied data files:

~~~bash
PYTHONPATH=backend .venv/bin/python -m superpower.cli.run_daily \
  --root-dir "$PWD" \
  --etf-file "/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/01_ETF清单和日频公式.xlsx" \
  --tl-file "/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/02_TL日频公式.xlsx" \
  --cb-file "/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/03_可转债数据.xlsx" \
  --disable-llm \
  --strict-audit
~~~

First run with active_strategy=legacy_v1 and diagnostic_strategies containing both IDs. Save the generated dashboard/audit as acceptance evidence outside outputs/latest. Then switch only active_strategy to trend_pullback_v2 through the same validation function/API and run the command again.

Expected for both runs: process exits zero, qa_status=PASS, database status=success, dashboard strategy ID/version/hash match the run snapshot, and the report workbook opens with all old plus new sheets.

- [ ] **Step 4: Verify isolation, performance, and browser behavior**

Programmatically compare both accepted dashboards:

~~~python
assert legacy["tl"] == v2["tl"]
assert legacy["convertible_bond"] == v2["convertible_bond"]
assert legacy["etf"]["strategy"]["strategy_id"] == "legacy_v1"
assert v2["etf"]["strategy"]["strategy_id"] == "trend_pullback_v2"
assert all("medium_status" in row and "short_entry_status" in row for row in v2["etf"]["all_signals"])
~~~

Measure diagnostic runtime on at least 30 ETFs with at least 1,600 daily rows. Expected: one full deterministic refresh finishes within 120 seconds on the development machine and does not exhibit per-prefix quadratic evaluation.

Start the local server:

~~~bash
.venv/bin/python serve.py --port 8770
~~~

Use the browser-control skill to verify:

1. Both registered strategies appear in the selector.
2. Saving without refresh shows 已保存，待刷新后生效 and leaves current tables unchanged.
3. A rejected invalid profile restores the last server-confirmed selection.
4. Successful refresh updates strategy ID/version and shows medium/short columns.
5. Failed refresh leaves the old dashboard visible.
6. Diagnostic selector cannot alter active live projections.
7. Existing CB and TL screens still render correctly.

- [ ] **Step 5: Set rollout default, commit docs, and preserve rollback**

For release A, restore configs/strategy_params.json to:

~~~json
{
  "etf": {
    "active_strategy": "legacy_v1",
    "diagnostic_strategies": ["legacy_v1", "trend_pullback_v2"]
  }
}
~~~

Retain all existing flat ETF thresholds and both full profiles around those keys; the snippet above shows only the rollout selector fields. Do not make trend_pullback_v2 the default in this commit. Present the comparison diagnostics for review; switching the default later is a one-line validated configuration change. Rollback remains selecting legacy_v1, saving, and refreshing.

Commit:

~~~bash
git add README.md backend/superpower/skills/etf_rotation_strategy/SKILL.md backend/superpower/skills/technical_indicators/SKILL.md backend/superpower/skills/strategy_backtest/SKILL.md backend/superpower/skills/report_generation/SKILL.md docs/ETF_MODEL.md docs/STRATEGY_PARAMETERS.md docs/DASHBOARD_SCHEMA.md docs/FRONTEND_GUIDE.md docs/CLIENT_PRODUCT_GUIDE.md docs/REPORTING_POLICY.md docs/superpowers/specs/2026-07-10-etf-strategy-plugin-v2-design.md configs/strategy_params.json
git commit -m "docs: document ETF strategy plugin rollout"
~~~

Final acceptance:

~~~bash
git status --short
git log --oneline --decorate -15
~~~

Expected: no uncommitted implementation files in the isolated worktree before overlap reconciliation. Continue to Task 15 before declaring the feature branch accepted.

---

### Task 15: Integrate the user's overlapping frontend and ETF parameter changes

**Files:**
- Modify: frontend/index.html
- Modify: frontend/assets/app.js
- Modify: frontend/assets/styles.css
- Modify: configs/strategy_params.json
- Test: frontend, API, full daily workflow, and browser acceptance after three-way reconciliation

**Interfaces:**
- Consumes: the feature branch plus the user's existing uncommitted CB frontend work and ETF sell-threshold override from the main checkout.
- Produces: a clean feature branch containing both sets of intended changes, while model_config.json, database edits, and the dirty main checkout remain untouched.

- [ ] **Step 1: Capture only safe overlap evidence from the main checkout**

Record hashes, not contents, for every dirty main-checkout file. Export only the three frontend diffs; never export model_config.json:

~~~bash
git -C "/Users/bobby/Desktop/ai money/ai_research_superpower" diff --binary \
  --output=/private/tmp/etf-v2-user-frontend.patch \
  -- frontend/index.html frontend/assets/app.js frontend/assets/styles.css
git -C "/Users/bobby/Desktop/ai money/ai_research_superpower" status --short
shasum -a 256 \
  "/Users/bobby/Desktop/ai money/ai_research_superpower/frontend/index.html" \
  "/Users/bobby/Desktop/ai money/ai_research_superpower/frontend/assets/app.js" \
  "/Users/bobby/Desktop/ai money/ai_research_superpower/frontend/assets/styles.css" \
  "/Users/bobby/Desktop/ai money/ai_research_superpower/configs/strategy_params.json" \
  "/Users/bobby/Desktop/ai money/ai_research_superpower/configs/model_config.json"
~~~

Expected: the patch contains only frontend files. Store the hash output in the implementation notes without opening or printing the model credential.

- [ ] **Step 2: Reconcile frontend hunks and the verified ETF threshold**

Run git apply --check /private/tmp/etf-v2-user-frontend.patch in the feature worktree to identify overlap without writing files. Read each safe hunk and apply it with apply_patch:

- Preserve the user's CB table markup, columns, formatters, and CSS selectors.
- Preserve the new ETF selector, schema controls, two state columns, and saved-versus-generated notice.
- Remove every conflict marker and keep one load/save/render path.

In configs/strategy_params.json, set sell_ma5_volume_ratio_min to the user's verified value 1.2 in both the flat compatibility key and normalized legacy/v2 inherited exit profile. Do not copy any other dirty config file.

- [ ] **Step 3: Run focused overlap regression**

~~~bash
node --check frontend/assets/strategy-config.js
node --check frontend/assets/app.js
node --test tests/frontend/strategy-config.test.js
.venv/bin/python -m pytest tests/test_etf_strategy_api.py tests/test_dashboard_schema.py tests/test_cb_ranking_output.py tests/test_tl_status_output.py -q
rg -n "^(<<<<<<<|=======|>>>>>>>)" frontend configs/strategy_params.json
git diff --check
~~~

Expected: all tests pass, the conflict-marker search returns no matches, CB/TL regressions remain green, and diff check emits no error.

- [ ] **Step 4: Repeat real-data and browser acceptance on the integrated branch**

Run Task 14's strict-audit daily command for both active strategies using the absolute read-only Wind paths. Repeat all seven browser checks, paying special attention to CB rendering and ETF selector/save/refresh behavior.

Expected: both strict runs pass; the integrated frontend displays both the user's CB work and the ETF plugin UX; a failed refresh retains the previous latest pointer.

- [ ] **Step 5: Verify main-checkout preservation and commit the integrated branch**

Re-run the Step 1 hashes and compare them byte-for-byte with the recorded values. Confirm the main checkout status still contains the same user-owned changes and untracked test. Then commit only the reconciled feature-branch files:

~~~bash
git add frontend/index.html frontend/assets/app.js frontend/assets/styles.css configs/strategy_params.json
git commit -m "chore: integrate existing UI and ETF parameter changes"
git status --short
~~~

Expected: the feature worktree is clean and fully accepted; the dirty main checkout is unchanged. Do not merge into the dirty main checkout until the user explicitly chooses the integration method.

---

## Acceptance summary

- The old ETF strategy remains selectable, characterized, and rollback-safe.
- The new strategy implements the customer's close-watch rule exactly: MA5 above MA10 plus daily MACD green narrowing or turning red, with separate weekly-MACD and MA20-flat prompts.
- The new strategy blocks entry when MA20 is falling or completed-week MACD green is widening, even after a giant-volume bullish bar.
- Medium trend and short entry are displayed together; only can_enter maps to a new buy candidate.
- Existing exits and ranking remain unchanged for v2.
- Configuration selection is plugin-based and new registered strategies do not require ETFAgent/report changes.
- Historical diagnostics compare state outcomes over 5/10/20 days without claiming executable returns.
- Plugin, workflow, database, and strict-audit failures retain the previous successful dashboard; non-strict audit FAIL keeps the existing partial-success publication contract with visible warnings.
- TL and convertible-bond outputs are unchanged.
