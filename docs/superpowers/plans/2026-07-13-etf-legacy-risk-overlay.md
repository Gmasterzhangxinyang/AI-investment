# ETF Legacy Risk Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `legacy_v1` as the unchanged default ETF signal and ranking engine while adding a separate, non-blocking risk overlay to its output.

**Architecture:** A focused backend module evaluates MA20, weekly MACD and extreme overheat from the latest two indicator rows and returns structured display-only fields. The handler attaches those fields only after the legacy decision has been produced, so buy/watch/sell flags, scores and ordering remain untouched. Frontend, report and chat consume the same fields; `trend_pullback_v2` remains an independently selectable experimental plugin.

**Tech Stack:** Python 3.12, pandas, pytest, vanilla JavaScript, Node test runner, HTML/CSS, JSON/Excel report pipeline.

## Global Constraints

- `legacy_v1` is the default active strategy.
- The overlay must never change `buy_candidate`, `watch_candidate`, `sell_alert`, `score`, `signal_reason` or result ordering.
- MA20, weekly MACD, overheat and false-reversal checks are display-only warnings.
- `trend_pullback_v2` remains selectable and is labelled as an experimental strategy.
- Historical diagnostics retain 1, 3, 5, 10 and 20 trading-day horizons and remain an event study rather than an executable backtest.
- Do not add dependencies or search the existing full sample for optimized thresholds.

---

### Task 1: Deterministic Legacy Risk Overlay

**Files:**
- Create: `backend/superpower/skills/etf_rotation_strategy/risk_overlay.py`
- Create: `tests/test_etf_legacy_risk_overlay.py`

**Interfaces:**
- Consumes: `evaluate_legacy_risk_overlay(rows: pd.DataFrame, profile: Mapping[str, Any])`
- Produces: immutable `LegacyRiskOverlay` with `level`, `summary`, `flags`, `ma20_state`, and `weekly_macd_state`

- [ ] **Step 1: Write failing tests for neutral, MA20-down and extreme false-reversal cases**

```python
def test_extreme_bar_in_falling_ma20_is_warning_only():
    rows = history()
    rows.loc[0, "收盘价"] = 10.0
    rows.loc[1, ["开盘价", "最高价", "最低价", "收盘价"]] = [10.0, 10.6, 10.0, 10.5]
    rows.loc[1, ["ma5", "ma20_slope_state", "weekly_macd_state", "vol_ratio60"]] = [10.1, "down", "green_narrowing", 2.0]
    result = evaluate_legacy_risk_overlay(rows, DEFAULT_PROFILE["short_entry"])
    assert result.level == "high"
    assert "extreme_false_reversal" in result.flags
    assert "不改变原策略排名" in result.summary
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_etf_legacy_risk_overlay.py`

Expected: FAIL because `risk_overlay` does not exist.

- [ ] **Step 3: Implement the minimal evaluator**

```python
@dataclass(frozen=True)
class LegacyRiskOverlay:
    level: str
    summary: str
    flags: tuple[str, ...]
    ma20_state: str
    weekly_macd_state: str

def evaluate_legacy_risk_overlay(rows, profile):
    latest, previous = rows.sort_values("date").iloc[-1], rows.sort_values("date").iloc[-2]
    flags = []
    if latest.get("ma20_slope_state") == "down":
        flags.append("ma20_down")
    if latest.get("weekly_macd_state") == "green_widening":
        flags.append("weekly_macd_weakening")
    if _is_extreme_bar(latest, previous, profile) and "ma20_down" in flags:
        flags.append("extreme_false_reversal")
    return _overlay_from_flags(flags, latest)
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_etf_legacy_risk_overlay.py`

Expected: all overlay tests pass.

- [ ] **Step 5: Commit the isolated evaluator**

```bash
git add backend/superpower/skills/etf_rotation_strategy/risk_overlay.py tests/test_etf_legacy_risk_overlay.py
git commit -m "feat: add legacy ETF risk overlay"
```

### Task 2: Attach Overlay Without Changing Legacy Decisions

**Files:**
- Modify: `backend/superpower/skills/etf_rotation_strategy/handler.py`
- Modify: `backend/superpower/skills/etf_rotation_strategy/compatibility.py`
- Modify: `tests/test_etf_signal_output.py`

**Interfaces:**
- Consumes: `attach_legacy_risk_overlays(decisions, etf, profile) -> list[ETFDecision]`
- Produces compatibility fields `risk_overlay_level`, `risk_overlay_summary`, `risk_overlay_flags`, `risk_overlay_ma20_state`, `risk_overlay_weekly_macd_state`

- [ ] **Step 1: Write a failing preservation test**

```python
baseline = LegacyV1Strategy().evaluate(history, position, legacy_profile)
signals, buys, sells, watch, _ = latest_etf_signals(frame, positions, params)
row = signals.loc[signals.code == baseline.code].iloc[0]
assert row.buy_signal == baseline.buy_candidate
assert row.score == baseline.score
assert row.signal_reason == baseline.compatibility_fields["signal_reason"]
assert row.risk_overlay_level == "high"
```

Also compare the ordered `(code, score, signal_type)` tuples before and after attachment.

- [ ] **Step 2: Run the preservation test and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_etf_signal_output.py`

Expected: FAIL because overlay columns are absent.

- [ ] **Step 3: Attach overlay after strategy evaluation**

```python
decisions = evaluate_latest_by_symbol(etf, positions, strategy, profile)
if normalized["active_strategy"] == "legacy_v1":
    decisions = attach_legacy_risk_overlays(
        decisions,
        etf,
        normalized["strategy_profiles"]["trend_pullback_v2"]["short_entry"],
    )
decisions = attach_quality_warnings(decisions, quality_warnings)
```

Append the five overlay fields to `LEGACY_SIGNAL_COLUMNS`; do not mutate canonical strategy states.

- [ ] **Step 4: Run legacy characterization and output tests**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_etf_signal_output.py tests/test_etf_legacy_characterization.py tests/test_etf_trend_pullback_strategy.py`

Expected: all pass with unchanged legacy signal behavior and independently working 2.0 behavior.

- [ ] **Step 5: Commit backend integration**

```bash
git add backend/superpower/skills/etf_rotation_strategy/handler.py backend/superpower/skills/etf_rotation_strategy/compatibility.py tests/test_etf_signal_output.py
git commit -m "feat: attach risk guidance to legacy ETF signals"
```

### Task 3: Present the Overlay Consistently

**Files:**
- Modify: `backend/superpower/skills/etf_rotation_strategy/registry.py`
- Modify: `backend/superpower/skills/report_generation/handler.py`
- Modify: `backend/superpower/chat/tools.py`
- Modify: `backend/superpower/chat/orchestrator.py`
- Modify: `frontend/assets/strategy-config.js`
- Modify: `frontend/assets/app.js`
- Modify: `tests/frontend/strategy-config.test.js`
- Modify: `tests/test_chat_etf_detail.py`
- Modify: `tests/test_dashboard_schema.py`

**Interfaces:**
- Consumes the five `risk_overlay_*` fields from dashboard rows.
- Produces a “风险辅助” column for generated legacy results and chat/report copy that states the overlay does not alter ranking.

- [ ] **Step 1: Write failing frontend and chat tests**

```javascript
test("legacy result shows risk overlay while v2 shows state columns", () => {
  assert.equal(showLegacyRiskOverlay({ strategy_id: "legacy_v1" }), true);
  assert.equal(showLegacyRiskOverlay({ strategy_id: "trend_pullback_v2" }), false);
  assert.equal(tableColumnClass("risk_overlay_summary"), "long-text-column");
});
```

Add a chat assertion that a legacy ETF detail answer contains `风险辅助` and `不改变原策略排名` when the field is present.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test tests/frontend/strategy-config.test.js && PYTHONPATH=backend .venv/bin/pytest -q tests/test_chat_etf_detail.py tests/test_dashboard_schema.py`

Expected: FAIL because legacy overlay presentation is absent.

- [ ] **Step 3: Implement presentation changes**

```javascript
function showLegacyRiskOverlay(generated) {
  return generated?.strategy_id === "legacy_v1";
}

const etfRiskColumns = showLegacyRiskOverlay(generatedEtfStrategy)
  ? [["risk_overlay_summary", "风险辅助"]]
  : [];
```

Add `...etfRiskColumns` after score in legacy ETF tables, include the structured fields in chat compaction, and label the registry entry `趋势回踩策略（实验）`. Update the strategy manual to say the legacy overlay is display-only.

- [ ] **Step 4: Run focused frontend, chat and report tests**

Run: `node --test tests/frontend/strategy-config.test.js && PYTHONPATH=backend .venv/bin/pytest -q tests/test_chat_etf_detail.py tests/test_dashboard_schema.py tests/test_etf_strategy_api.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit delivery changes**

```bash
git add backend/superpower/skills/etf_rotation_strategy/registry.py backend/superpower/skills/report_generation/handler.py backend/superpower/chat/tools.py backend/superpower/chat/orchestrator.py frontend/assets/strategy-config.js frontend/assets/app.js tests/frontend/strategy-config.test.js tests/test_chat_etf_detail.py tests/test_dashboard_schema.py
git commit -m "feat: show legacy ETF risk guidance"
```

### Task 4: Full Verification With Real ETF Data

**Files:**
- Modify only if verification exposes a defect in files already listed above.

**Interfaces:**
- Verifies the complete dashboard, report, audit and UI path.

- [ ] **Step 1: Run all automated tests and syntax checks**

Run: `PYTHONPATH=backend .venv/bin/pytest -q`

Expected: full Python suite passes.

Run: `node --test tests/frontend/strategy-config.test.js && node --check frontend/assets/app.js && node --check frontend/assets/strategy-config.js`

Expected: all Node tests and syntax checks pass.

- [ ] **Step 2: Refresh using the real ETF data with default legacy strategy**

Run:

```bash
PYTHONPATH=backend .venv/bin/python -m superpower.cli.run_daily \
  --root-dir "$PWD" \
  --etf-file "/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/01_ETF清单和日频公式.xlsx" \
  --tl-file "/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/02_TL日频公式.xlsx" \
  --cb-file "$PWD/data/wind/current/03_可转债数据.xlsx" \
  --disable-llm --strict-audit
```

Expected: workflow success and independent audit PASS.

- [ ] **Step 3: Verify output invariants**

Run:

```bash
jq '.etf.strategy.strategy_id' outputs/latest/dashboard.json
jq '[.etf.historical_diagnostics[].horizon] | unique' outputs/latest/dashboard.json
jq '[.etfBuyCandidates[] | has("risk_overlay_summary")] | all' outputs/latest/dashboard.json
```

Expected: `"legacy_v1"`, `[1, 3, 5, 10, 20]`, and `true`. Add a focused Python regression assertion that candidate `(code, score)` ordering matches a direct legacy evaluation before claiming the invariant.

- [ ] **Step 4: Verify the ETF page**

Reload the local ETF page. Confirm that “中期趋势、短期入场” are hidden for legacy results, “风险辅助” is readable, and candidate ranking is unchanged.

- [ ] **Step 5: Final diff and commit**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and no uncommitted implementation files after the final verification commit.
