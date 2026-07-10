# ETF v2 Configurable Strategy Plugin Design

**Date:** 2026-07-10  
**Status:** Approved conversational design, pending written-spec review  
**Scope:** ETF only

## 1. Purpose

Refactor the ETF strategy from one embedded rule handler into a configurable strategy plugin. The first new plugin, `trend_pullback_v2`, separates medium-term trend eligibility from short-term entry timing while preserving the current `legacy_v1` behavior for rollback and comparison.

The design targets fewer false reversals and more stable, explainable states over roughly 5–20 trading days. It is not a next-day price predictor and does not promise investment returns.

## 2. Goals

- Keep the existing ETF Agent and daily workflow stable.
- Select the active ETF strategy by configuration.
- Preserve the existing strategy as `legacy_v1`.
- Add `trend_pullback_v2` as a plugin composed of:
  - a medium-term trend module;
  - a short-term entry module;
  - the unchanged legacy exit policy;
  - the unchanged legacy ranking policy for compatibility.
- Show medium-term and short-term states simultaneously for every ETF.
- Use the same plugin interface for live output and historical diagnostics.
- Add new strategies later without modifying the ETF Agent, report pipeline, or frontend contract.
- Fail closed when a configured strategy is missing, invalid, or lacks enough data.

## 3. Non-goals

- No changes to TL or convertible-bond logic, data, reports, or UI.
- No cross-asset allocation or portfolio optimizer.
- No machine-learning price prediction.
- No full P&L backtest in this phase.
- No redesign of the current ETF sell rules in this phase.
- No removal of existing ETF dashboard fields during the compatibility period.

## 4. Current-state problem

The project already has an outer Skill registry, and `ETFAgent` invokes the fixed `etf-rotation-strategy` Skill. However, the ETF handler currently combines rule evaluation, position gating, scoring, presentation text, watchlist construction, and output assembly in one file.

The current entry rules are event-driven daily triggers:

1. MA5 crosses above MA10, daily MACD histogram improves, and volume ratio is at least the configured threshold; or
2. DIF crosses above DEA, MA5 is above MA10, close is above MA20, and volume ratio is at least the configured threshold.

MA20 is only an enhancement item in the current strategy. ETF weekly MACD, MA20 slope, overheat detection, confirmation waiting, and pullback support do not exist. A large volume spike is always treated as favorable confirmation, even after a prolonged decline.

## 5. Chosen architecture

```text
ETFAgent (unchanged)
  -> etf-rotation-strategy Skill adapter
    -> ETFStrategyRegistry
      -> active profile selected by configuration
        -> legacy_v1
        -> trend_pullback_v2
             -> medium trend policy
             -> short entry policy
             -> legacy exit policy
             -> legacy ranking policy
    -> stable ETFDecision output
    -> compatibility projections
      -> etf_signal_table
      -> etf_buy_candidates
      -> etf_watchlist
      -> etf_sell_alerts
      -> etf_detail_history
```

The plugin boundary lives inside the current ETF Skill. The workflow continues to discover and run one `etf-rotation-strategy` Skill, so no new Agent or workflow branch is required.

## 6. File responsibilities

```text
backend/superpower/skills/etf_rotation_strategy/
├── handler.py
├── contracts.py
├── registry.py
├── config.py
├── compatibility.py
└── strategies/
    ├── __init__.py
    ├── legacy_v1.py
    └── trend_pullback_v2/
        ├── __init__.py
        ├── strategy.py
        ├── medium_trend.py
        ├── short_entry.py
        ├── defaults.py
        └── diagnostics.py
```

- `handler.py`: reads context, selects the active strategy, runs it, and writes existing artifacts.
- `contracts.py`: defines stable strategy inputs, outputs, state enums, evidence fields, and errors.
- `registry.py`: maps explicit strategy names to constructors. It does not execute arbitrary filesystem code.
- `config.py`: validates profiles and converts legacy ETF configuration into the normalized in-memory shape.
- `compatibility.py`: derives existing buy/watch/sell/all-signal tables from canonical decisions.
- `legacy_v1.py`: preserves current entry, watch, exit, and ranking behavior byte-for-byte where serialization permits.
- `trend_pullback_v2/strategy.py`: composes the medium, entry, exit, ranking, and diagnostics components.
- `medium_trend.py`: evaluates only medium-term eligibility.
- `short_entry.py`: evaluates only entry timing and consumes the medium result.
- `defaults.py`: contains versioned default parameters.
- `diagnostics.py`: calculates 5/10/20-day forward outcome diagnostics from state-transition events.

## 7. Stable plugin contract

Each strategy implements the following conceptual interface:

```python
class ETFStrategy(Protocol):
    strategy_id: str
    version: str

    def evaluate(
        self,
        history: ETFHistory,
        position: ETFPositionState,
        params: Mapping[str, object],
    ) -> ETFDecision: ...
```

`ETFDecision` contains:

```text
as_of
code
name
strategy_id
strategy_version
medium_status
short_entry_status
exit_status
eligible
buy_candidate
watch_candidate
sell_alert
score
metrics
rule_hits
missing_conditions
risk_notes
confidence
data_quality
```

Core consumers use only this contract. They do not import private strategy helpers.

## 8. Strategy configuration

The normalized configuration shape is:

```json
{
  "etf": {
    "active_strategy": "trend_pullback_v2",
    "diagnostic_strategies": ["legacy_v1", "trend_pullback_v2"],
    "strategy_profiles": {
      "legacy_v1": {},
      "trend_pullback_v2": {
        "medium_trend": {},
        "short_entry": {},
        "exit": {},
        "ranking": {}
      }
    }
  }
}
```

The current flat ETF keys remain readable for one compatibility cycle:

```text
buy_volume_ratio_min
sell_ma10_volume_ratio_min
sell_ma5_volume_ratio_min
score_weights
```

They are normalized into the `legacy_v1` profile in memory. Saving configuration must preserve unknown strategy profiles rather than deleting them.

Only `active_strategy` controls live buy/watch/sell projections. `diagnostic_strategies` may run in historical-diagnostic mode but cannot change the live decision.

### 8.1 End-user selection workflow

The normal user does not edit JSON manually. The frontend strategy-parameter page adds an `ETF策略` selector populated from registered strategy metadata.

Initial options:

```text
原始策略 (legacy_v1)
趋势回踩策略 (trend_pullback_v2)
```

The daily workflow is:

1. Open `策略参数 -> ETF策略`.
2. Select the active strategy from the dropdown.
3. Review that strategy's versioned parameters and keep defaults or edit allowed values.
4. Save through the existing strategy-parameter API.
5. Refresh data to generate a new dashboard and report.
6. Read the active strategy ID/version plus simultaneous medium and short states in ETF results.

Saving changes configuration only. Existing dashboard results remain unchanged until refresh completes successfully. The previous valid dashboard remains available if refresh fails.

The page may expose `旧版与新版历史诊断对比` as a separate option. It changes `diagnostic_strategies` only; it cannot change `active_strategy` or create live buy/sell projections from a non-active strategy.

### 8.2 Developer plugin lifecycle

To add another ETF strategy, a developer:

1. Adds a package under `strategies/`.
2. Implements the stable `ETFStrategy` contract.
3. Provides strategy metadata, version, default parameters, and parameter validation.
4. Registers the explicit strategy name in `ETFStrategyRegistry`.
5. Adds contract, behavior, failure, and compatibility tests.
6. Restarts the local service once so the new Python package is loaded.

After installation, switching among already registered strategies requires only save plus data refresh, not another service restart.

The frontend must show a clear error and retain the previous selection when the requested strategy name is unknown or its profile is invalid. Runtime plugin failure produces no ETF signal and never silently activates another strategy.

## 9. Shared indicator additions

### 9.1 MA20 normalized slope

```text
ma20_slope_5d = MA20(t) / MA20(t-5) - 1
```

Defaults:

```text
ma20_slope_lookback = 5
ma20_flat_tolerance = 0.003
```

Classification:

```text
down:  slope < -0.003
flat: -0.003 <= slope <= 0.003
up:    slope > 0.003
```

The tolerance is configurable and must not be optimized silently after results are viewed.

### 9.2 ETF weekly MACD

Weekly OHLCV is derived causally from daily bars. The official medium-term decision uses the last completed week strictly before the current report week. The current partial week is exposed only as a preview metric and cannot change the official medium status.

Weekly histogram states are mutually exclusive:

```text
red_strengthening: histogram > 0 and histogram >= previous histogram
red_weakening:     histogram > 0 and histogram < previous histogram
green_narrowing:   histogram < 0 and histogram > previous histogram
green_widening:    histogram < 0 and histogram <= previous histogram
```

Weekly calculations must not use any daily bar after the decision date.

### 9.3 Minimum history

`trend_pullback_v2` requires at least 180 valid daily trading rows per ETF so MA60, daily MACD, and completed-week MACD have adequate warm-up. With less history, both strategy states are `data_unavailable`; the strategy does not fall back to `legacy_v1`.

## 10. Medium-term trend policy

Official states:

```text
do_not_participate
turning_watch
trend_confirmed
data_unavailable
```

Evaluation precedence is fixed.

### 10.1 `data_unavailable`

Returned when required price, volume, MA, MACD, or completed-week history is missing.

### 10.2 `do_not_participate`

Returned when either hard veto is true:

```text
ma20_slope_state == down
or weekly_macd_state == green_widening
```

It is also the fallback when neither the watch nor confirmation conditions below are complete.

A daily golden cross or large positive volume bar cannot override this state.

### 10.3 `turning_watch`

Returned when all are true:

```text
ma20_slope_state in {flat, up}
daily_macd_hist > 0
weekly_macd_state in {green_narrowing, red_weakening, red_strengthening}
trend_confirmed conditions are not all complete
```

This captures the early pattern discussed for Innovation Drug ETF: daily momentum has turned positive while the completed weekly bar may still be negative but improving. It is observation only and cannot create a buy candidate.

### 10.4 `trend_confirmed`

Returned when all are true:

```text
close > MA20
MA5 > MA20
ma20_slope_state in {flat, up}
completed weekly MACD histogram > 0
daily MACD histogram > 0
```

The output separately records whether MA5 crossed above MA20 today or remains above it after an earlier cross. A one-day cross event is not required every day for the confirmed state to persist.

## 11. Short-term entry policy

Official states:

```text
no_entry
overheated_do_not_chase
waiting_confirmation
waiting_pullback
can_enter
data_unavailable
```

The short module cannot override medium eligibility.

### 11.1 Setup event

A setup begins when either event occurs:

```text
medium status transitions into trend_confirmed
or MA5 crosses above MA20 while medium status is trend_confirmed
```

The setup records the setup date, close, high, volume, MA5, MA10, and MA20 from historical bars. It expires after 10 trading sessions or immediately if medium status leaves `trend_confirmed`.

### 11.2 Overheat definition

Defaults:

```text
overheat_daily_return_min = 0.04
overheat_body_ratio_min = 0.60
overheat_volume_ratio_min = 1.80
overheat_ma5_distance_min = 0.03
overheat_cooldown_days = 3
```

Definitions:

```text
daily_return = close / previous_close - 1
body_ratio = max(close - open, 0) / max(high - low, epsilon)
ma5_distance = close / MA5 - 1

long_bullish_bar =
  daily_return >= overheat_daily_return_min
  and body_ratio >= overheat_body_ratio_min

overheated =
  long_bullish_bar
  and vol_ratio60 >= overheat_volume_ratio_min
  and ma5_distance >= overheat_ma5_distance_min
```

An overheated bar returns `overheated_do_not_chase` even when the medium trend is confirmed. It begins a three-session cooling period. If medium status is `do_not_participate`, the result remains `no_entry`, with the large-bar risk included in `risk_notes`.

### 11.3 `no_entry`

Returned when:

```text
medium status == do_not_participate
or no active setup exists
or the setup has expired
```

### 11.4 `waiting_confirmation`

Returned during the first three sessions after a valid setup when no later close has confirmed the setup and the ETF is not overheated.

A later bar confirms the breakout when all are true:

```text
bar date > setup date
close > setup high
daily MACD histogram > 0
ma5_distance < overheat_ma5_distance_min
not overheated
```

### 11.5 `waiting_pullback`

Returned when the medium trend remains confirmed and any is true:

```text
the ETF is inside the post-overheat cooling period
or ma5_distance >= overheat_ma5_distance_min
or the first three-session confirmation window ended without confirmation
```

The state remains eligible for pullback evaluation until the setup expires.

### 11.6 Pullback confirmation

Defaults:

```text
pullback_support_tolerance = 0.005
pullback_max_intraday_break = 0.010
pullback_max_age = 10
```

For each bar inside the setup window:

```text
support_candidates = [MA5, MA10]
if close >= setup high:
  support_candidates also includes setup high
support = max(support_candidates)
touches_support = low <= support * (1 + pullback_support_tolerance)
structure_intact = low >= support * (1 - pullback_max_intraday_break)
holds_support = close >= support
volume_contracts = volume < setup volume

pullback_confirmed =
  touches_support
  and structure_intact
  and holds_support
  and volume_contracts
  and daily MACD histogram > 0
  and medium status == trend_confirmed
```

### 11.7 `can_enter`

Returned when medium status is `trend_confirmed`, the ETF is not overheated, and either breakout confirmation or pullback confirmation is true.

For a non-holding ETF, `can_enter` maps to the compatibility output `buy_candidate`. For a holding ETF, the state is still displayed as evidence but cannot create another buy candidate.

## 12. Legacy evidence retained in v2

The following current signals remain visible inside the v2 evidence package:

- MA5/MA10 relationship and cross event;
- daily DIF/DEA golden-cross event;
- daily MACD histogram and change;
- 60-day volume ratio;
- close relative to MA20 and MA60;
- legacy strength score.

They no longer create eligibility on their own. The legacy score remains a ranking/display value and cannot turn `no_entry` or `waiting_*` into `can_enter`.

## 13. Exit and ranking behavior

For the first ETF v2 release:

- exit policy remains the configured legacy MA5/MA10 volume-confirmed policy;
- ranking remains the legacy score for compatibility;
- both policies are referenced by name from the active strategy profile rather than called as private functions;
- sell-alert behavior is characterized by tests before extraction;
- redesigning exits or ranking requires a separate reviewed strategy version.

This isolates the effect of the new entry design and avoids changing entry, exit, and ranking simultaneously.

## 14. Compatibility mapping

Canonical v2 decisions add fields to `etf.all_signals` and equivalent report rows:

```text
strategy_id
strategy_version
medium_status
medium_reason
short_entry_status
short_entry_reason
weekly_macd_state
weekly_macd_hist
weekly_macd_preview
ma20_slope_5d
ma20_slope_state
setup_date
setup_age
```

Existing projections remain:

```text
can_enter + non-holding       -> buy_candidate
waiting_confirmation          -> watch
waiting_pullback              -> watch
turning_watch                 -> watch
overheated_do_not_chase       -> watch with risk flag
legacy exit + holding         -> sell_alert
all other valid states        -> neutral
data unavailable              -> data_unavailable
```

No holding ETF may be inserted into the public watchlist, even though its medium and short states remain visible in `all_signals`.

## 15. Historical performance diagnostics

The feature is named `historical_diagnostics`, not a profit backtest.

Diagnostic events are recorded only when a state changes into:

```text
trend_confirmed
overheated_do_not_chase
waiting_pullback
can_enter
```

Repeated daily rows in the same state episode are not counted as independent events.

For each event, when sufficient future data exists, calculate:

```text
forward_close_return_5d
forward_close_return_10d
forward_close_return_20d
maximum_favorable_excursion_5d/10d/20d
maximum_adverse_excursion_5d/10d/20d
```

Forward returns use signal-day close to future close. Favorable and adverse excursions use subsequent highs and lows relative to signal-day close. Results are descriptive and do not claim executable portfolio returns.

The output compares `legacy_v1` and `trend_pullback_v2` on the same dates and instruments, including:

- event counts;
- false-reversal frequency;
- signal-state flip frequency;
- 5/10/20-day distributions;
- drawdown distributions;
- direct-chase versus waiting-pullback outcomes.

## 16. Failure behavior

- Unknown `active_strategy`: ETF module returns an explicit configuration error and produces no buy/sell suggestion.
- Invalid profile values: configuration validation fails before the daily strategy runs.
- Missing weekly/daily history: affected ETF returns `data_unavailable` without fallback.
- Plugin exception: ETF run is marked failed/degraded with the strategy ID and error; the system does not silently switch to `legacy_v1`.
- Missing optional preview data: official state still runs from completed-week data and records a warning.
- Stale source data: current QA behavior remains, but ETF output must display the stale-data warning beside strategy states.

## 17. Testing strategy

### 17.1 Legacy characterization

- Freeze both current buy routes.
- Freeze current watchlist routes.
- Freeze current holding-only sell behavior.
- Freeze current ranking results for representative rows.
- Add regression coverage for the holding/watch leakage case.

### 17.2 Plugin contract

- Select `legacy_v1` through configuration.
- Select `trend_pullback_v2` through configuration.
- Reject an unknown strategy name.
- Reject invalid parameters.
- Prove that strategy outputs satisfy the stable contract.
- Prove that a non-active diagnostic strategy cannot change live output.

### 17.3 Indicator correctness

- MA20 slope down/flat/up boundaries.
- Completed-week MACD classification.
- Partial-week preview cannot change official state.
- Changing data after decision date cannot change a historical decision.
- Insufficient 180-day history returns `data_unavailable`.

### 17.4 Strategy scenarios

- Prolonged decline plus one giant-volume bullish bar remains `do_not_participate` and cannot buy.
- MA20 flattening plus daily red MACD plus narrowing weekly green MACD becomes `turning_watch`.
- MA5 above MA20 plus flat/rising MA20 plus weekly/daily red MACD becomes `trend_confirmed`.
- An overheated confirmed-trend bar becomes `overheated_do_not_chase`.
- A later support-holding, lower-volume pullback becomes `can_enter`.
- A broken pullback or expired setup returns `no_entry`.
- A short-term signal never overrides a medium hard veto.

### 17.5 Compatibility and diagnostics

- V2 `can_enter` maps to the current buy-candidate table only for non-holdings.
- V2 wait/overheat states map to watchlist only for non-holdings.
- Existing dashboard keys remain present.
- State-transition events are counted once per episode.
- 5/10/20-day forward-return and excursion formulas are causal and exact.
- TL and convertible-bond outputs remain unchanged.

## 18. Rollout sequence

1. Add characterization tests around current ETF behavior.
2. Extract `legacy_v1` behind the stable plugin contract with no intended output change.
3. Add configuration normalization, registry metadata, API validation, and explicit strategy selection.
4. Add MA20 slope and causal ETF weekly MACD indicators.
5. Implement and unit-test the medium trend module.
6. Implement and unit-test the short entry state machine.
7. Compose `trend_pullback_v2` with legacy exit and ranking components.
8. Add canonical fields and compatibility projections.
9. Add 5/10/20-day historical diagnostics for both strategies.
10. Add the frontend ETF-strategy selector, save/refresh workflow, diagnostics selector, and update ETF-only documentation, reports, and chat evidence.
11. Run legacy parity, full automated tests, daily workflow, audit, and dashboard verification.
12. Compare old and new diagnostics before making `trend_pullback_v2` the default.

## 19. Acceptance criteria

- The active ETF strategy is selected by configuration.
- A user can select a registered strategy from the frontend, save it, refresh data, and see the selected ID/version in generated ETF results.
- Saving a strategy does not mutate already-generated results before refresh.
- Diagnostic comparison cannot change the active live strategy.
- Installing a new strategy requires a service restart once; switching installed strategies does not.
- Adding another registered strategy does not require changes to ETFAgent or report consumers.
- `legacy_v1` remains selectable and matches characterized behavior.
- `trend_pullback_v2` produces simultaneous medium and short states with full evidence.
- MA20 decline and weekly green-widening conditions cannot be overridden by a daily spike.
- Weekly official states are causal and stable during the report week.
- Overheat, confirmation, and pullback states follow the configured state machine.
- Missing or invalid plugins fail closed.
- Existing ETF dashboard keys remain compatible during migration.
- Historical diagnostics compare both strategies without presenting simulated portfolio returns.
- TL and convertible-bond tests and outputs are unchanged.
- The implementation has automated coverage for every state transition and failure path above.

## 20. Worktree protection

The repository already contains unrelated user changes in database, model configuration, ETF parameter configuration, frontend files, and an untracked database test. Implementation must preserve those changes. The design document is committed alone. Later implementation should begin in an isolated worktree from the current committed `HEAD`, and any necessary integration with the dirty configuration/frontend files must be reviewed explicitly rather than overwritten.
