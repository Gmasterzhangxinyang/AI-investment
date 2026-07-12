# TL ETF Fund Flow Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily and rolling five-session 30-year Treasury ETF share-flow diagnostics to TL without changing any existing TL trading state.

**Architecture:** A focused `fund_flow.py` module classifies raw share changes, excludes review-only statistical extremes from rolling calculations, and attaches structured fields after the existing TL state machine has finished. Dashboard, Excel, SQLite payloads, chat and frontend consume those fields directly. Old TL workbooks without the new column remain valid.

**Tech Stack:** Python 3.12, pandas, pytest, vanilla JavaScript, Node test runner, JSON/Excel report pipeline.

## Global Constraints

- Never modify the customer source workbook.
- Never change existing TL `status`, `buy_signal`, `attention_signal` or `no_trade_signal` values.
- Keep raw values above `0.20` but mark them for review and exclude them from rolling direction.
- Treat blank as missing and numeric zero as a real zero; warn after three consecutive zero observations.
- Use five valid trading rows rather than calendar weeks.
- Do not add futures open interest or convertible-bond fields to this change.
- Do not claim predictive power or executable backtest returns.

---

### Task 1: Fund Flow Classification Module

**Files:**
- Create: `backend/superpower/skills/tl_timing_strategy/fund_flow.py`
- Create: `tests/test_tl_fund_flow.py`
- Modify: `configs/strategy_params.json`

**Interfaces:**
- Produces `attach_fund_flow_diagnostics(frame: pd.DataFrame, tl_params: Mapping[str, Any]) -> pd.DataFrame`.
- Adds the nine `fund_*` fields defined in the design without mutating signal columns.

- [ ] Write failing boundary tests for `0`, `0.03`, `0.05`, `0.07`, `0.20`, values above `0.20`, missing values and five-session sums.
- [ ] Run `PYTHONPATH=backend .venv/bin/pytest -q tests/test_tl_fund_flow.py` and verify failure because the module is absent.
- [ ] Implement defaults and classification:

```python
DEFAULT_FUND_FLOW = {
    "light_threshold": 0.03,
    "large_threshold": 0.05,
    "extreme_threshold": 0.07,
    "review_threshold": 0.20,
    "rolling_days": 5,
    "rolling_direction_threshold": 0.08,
    "minimum_valid_days": 3,
    "zero_stale_days": 3,
}
```

- [ ] Add matching `tl.fund_flow` values to `configs/strategy_params.json`.
- [ ] Re-run the focused tests and require all cases to pass.
- [ ] Commit with `feat: add TL ETF fund flow diagnostics`.

### Task 2: Preserve the Existing TL State Machine

**Files:**
- Modify: `backend/superpower/skills/tl_timing_strategy/handler.py`
- Modify: `tests/test_tl_status_output.py`

**Interfaces:**
- Calls `attach_fund_flow_diagnostics` only after current status columns are calculated.
- Keeps empty and insufficient-history contracts compatible.

- [ ] Write a failing regression test that computes the same TL fixture with and without `份额变化（亿份）` and asserts identical `status`, `buy_signal`, `attention_signal`, `no_trade_signal`, `reason` and `rule_hits`.
- [ ] Add test cases for technical/flow combinations: improvement+inflow, improvement+outflow, no-trade+outflow and no-trade+inflow.
- [ ] Run the focused test and verify missing fund fields fail before integration.
- [ ] Attach diagnostics to normal, insufficient and unavailable results; add fund values to the existing `metrics` dictionary.
- [ ] Run `PYTHONPATH=backend .venv/bin/pytest -q tests/test_tl_status_output.py tests/test_tl_fund_flow.py` and require all cases to pass.
- [ ] Commit with `feat: attach fund flow guidance to TL states`.

### Task 3: Deliver the Same Fields Everywhere

**Files:**
- Modify: `frontend/assets/app.js`
- Modify: `frontend/assets/strategy-config.js`
- Modify: `tests/frontend/strategy-config.test.js`
- Modify: `backend/superpower/chat/orchestrator.py`
- Modify: `tests/test_chat_tl_detail.py`
- Modify: `backend/superpower/skills/report_generation/handler.py`
- Modify: `tests/test_dashboard_schema.py`

**Interfaces:**
- Reads `fund_share_change_daily`, `fund_share_daily_level`, `fund_share_5d_sum`, `fund_flow_state`, `fund_flow_relation`, `fund_flow_note` and `fund_flow_data_quality` from TL rows.
- SQLite receives the same fields through existing `tl_daily_signals.payload_json` ingestion.

- [ ] Write failing frontend tests that mark `fund_flow_note` as long text and failing chat tests that require a “资金辅助” paragraph.
- [ ] Extend TL today metrics with daily share change, daily level, five-day sum, relation and note.
- [ ] Extend TL recent tables with daily change, five-day sum and relation only.
- [ ] Include the fund note in deterministic backend chat and local frontend TL answers.
- [ ] Verify dashboard serialization preserves the fields and the report sheets receive the expanded TL dataframes.
- [ ] Run `node --test tests/frontend/strategy-config.test.js` plus the focused Python chat/dashboard tests.
- [ ] Commit with `feat: expose TL fund flow guidance`.

### Task 4: Real Workbook and Full Verification

**Files:**
- Modify only files from Tasks 1–3 if verification finds a defect.

**Interfaces:**
- Uses `/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/02_TL日频公式-0710快照.xlsx` explicitly for validation.

- [ ] Run all Python tests, Node tests and JavaScript syntax checks.
- [ ] Run `superpower.cli.run_daily` with the normal ETF and convertible-bond sources and the new TL snapshot, with `--disable-llm --strict-audit`.
- [ ] Verify dashboard TL state remains the direct-rule state while all fund-flow fields exist.
- [ ] Confirm raw `±2.9` observations remain in source-derived history, are marked review-only and do not enter five-session sums.
- [ ] Reload the TL page and visually confirm readable cards and recent-state columns.
- [ ] Run `git diff --check`, ensure a clean working tree after commit, and report the measured result without promising returns.
