# Convertible Bond Linkage Overlay Implementation Plan

> 历史实施记录：本文保留当时的设计、测试步骤和 rollout 假设，不代表当前默认配置。当前运行口径请看 [当前系统事实清单](../../CURRENT_SYSTEM.md) 和 configs/strategy_params.json。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the four new convertible-bond linkage fields and add deterministic short-term warning labels without changing the existing score, rank, qualification, eligibility, action, or Top10 order.

**Architecture:** Extend the Excel normalization contract, then compute linkage guidance in a focused pure module. Attach the result after the existing ranking and qualification decisions are complete, so the overlay cannot feed back into the original strategy. Dashboard, frontend, and chat consume only the attached fields.

**Tech Stack:** Python 3.12, pandas, pytest, deterministic JSON dashboard, vanilla JavaScript frontend, Node test runner.

## Global Constraints

- Wind workbooks are read-only inputs and must never be modified.
- `score`, `rank`, `qualification`, `eligible_for_top`, `action`, exclusions, and Top10 order must remain identical with and without the four new fields.
- Blank linkage values remain missing and are never converted to zero.
- Only abnormal linkage states show list-level explanatory text.
- All thresholds live under `convertible_bond.linkage_overlay` in `configs/strategy_params.json`.
- Internal workbook date is authoritative; the filename date is not substituted.

---

### Task 1: Normalize the four new Excel fields

**Files:**
- Modify: `backend/superpower/tools/excel_reader.py`
- Create: `tests/test_cb_linkage_overlay.py`

**Interfaces:**
- Consumes: customer row-5 headers `正股当日涨幅（%）`, `转债当日涨幅`, `前日转股溢价率`, `转股溢价率当日变化`.
- Produces: nullable numeric columns `stock_daily_return`, `bond_daily_return`, `previous_conversion_premium_rate`, `conversion_premium_change` from `parse_convertible_bond_excel(path)`.

- [ ] **Step 1: Write the failing parser tests**

Create a compact workbook fixture with row-5 headers. Assert that all four headers map to their normalized names, numeric values remain numeric, and blank values remain `NaN`.

```python
def test_parser_keeps_convertible_linkage_fields(tmp_path: Path) -> None:
    path = write_cb_workbook(tmp_path, stock_return=3.2, bond_return=0.8, previous_premium=25.0, premium_change=-2.4)
    row = parse_convertible_bond_excel(path).iloc[0]
    assert row["stock_daily_return"] == 3.2
    assert row["bond_daily_return"] == 0.8
    assert row["previous_conversion_premium_rate"] == 25.0
    assert row["conversion_premium_change"] == -2.4

def test_parser_does_not_turn_blank_linkage_values_into_zero(tmp_path: Path) -> None:
    row = parse_convertible_bond_excel(write_cb_workbook(tmp_path)).iloc[0]
    assert pd.isna(row["stock_daily_return"])
    assert pd.isna(row["conversion_premium_change"])
```

- [ ] **Step 2: Run the parser tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py -q`

Expected: FAIL because the normalized columns do not exist.

- [ ] **Step 3: Add aliases, output columns, and numeric conversion**

Add these aliases in `_normalize_convertible_bond_frame`:

```python
"正股当日涨幅（%）": "stock_daily_return",
"转债当日涨幅": "bond_daily_return",
"前日转股溢价率": "previous_conversion_premium_rate",
"转股溢价率当日变化": "conversion_premium_change",
```

Add the four normalized names to the empty schema, optional-column initialization, final output list, and `_numeric_percent_safe` conversion list.

- [ ] **Step 4: Run the parser tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/superpower/tools/excel_reader.py tests/test_cb_linkage_overlay.py
git commit -m "feat: parse convertible bond linkage fields"
```

---

### Task 2: Implement the isolated linkage classifier

**Files:**
- Create: `backend/superpower/skills/convertible_bond_ranking/linkage.py`
- Modify: `configs/strategy_params.json`
- Modify: `tests/test_cb_linkage_overlay.py`

**Interfaces:**
- Consumes: a row mapping and `convertible_bond.linkage_overlay` configuration.
- Produces: `classify_linkage(row, config) -> dict[str, object]` with `linkage_state`, `linkage_note`, `linkage_is_abnormal`, and `linkage_data_quality`.

- [ ] **Step 1: Write failing boundary and priority tests**

Cover exact defaults and just-below boundaries for:

```python
DEFAULT_CONFIG = {
    "validation_tolerance": 0.05,
    "stock_strong_threshold": 3.0,
    "stock_weak_threshold": -3.0,
    "bond_strong_threshold": 3.0,
    "bond_weak_threshold": -2.0,
    "relative_gap_threshold": 2.0,
    "premium_expand_threshold": 2.0,
    "premium_compress_threshold": -2.0,
}
```

Required results:

```python
assert classify_linkage(catch_up_row, DEFAULT_CONFIG)["linkage_state"] == "关注补涨"
assert classify_linkage(chase_row, DEFAULT_CONFIG)["linkage_state"] == "谨慎追涨"
assert classify_linkage(weak_row, DEFAULT_CONFIG)["linkage_state"] == "联动走弱"
assert classify_linkage(normal_row, DEFAULT_CONFIG)["linkage_state"] == "正常联动"
assert classify_linkage(missing_row, DEFAULT_CONFIG)["linkage_state"] == "数据不足"
assert classify_linkage(inconsistent_row, DEFAULT_CONFIG)["linkage_state"] == "数据待核验"
```

Also prove priority: data inconsistency wins over every market state; joint weakness wins over chase/catch-up.

- [ ] **Step 2: Run classifier tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py -q`

Expected: FAIL because `linkage.py` and `classify_linkage` do not exist.

- [ ] **Step 3: Implement the pure classifier**

Implement finite-number checks, the premium identity check, priority ordering, and concise Chinese notes. The normal state must set `linkage_is_abnormal=False`; all warning and data-quality states set it to `True` except `数据不足`, which remains non-directional.

- [ ] **Step 4: Add configuration defaults**

Add `convertible_bond.linkage_overlay` with `enabled: true` and the exact thresholds above. Do not alter any existing weight or risk threshold.

- [ ] **Step 5: Run classifier tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/superpower/skills/convertible_bond_ranking/linkage.py configs/strategy_params.json tests/test_cb_linkage_overlay.py
git commit -m "feat: classify convertible bond linkage"
```

---

### Task 3: Attach guidance without changing the original strategy

**Files:**
- Modify: `backend/superpower/skills/convertible_bond_ranking/handler.py`
- Modify: `tests/test_cb_linkage_overlay.py`
- Modify: `tests/test_cb_ranking_output.py`

**Interfaces:**
- Consumes: ranked eligible rows after score, qualification, action, and order are finalized.
- Produces: the four raw linkage columns plus `linkage_state`, `linkage_note`, `linkage_is_abnormal`, `linkage_data_quality` in ranked and selected outputs.

- [ ] **Step 1: Write the failing regression test**

Rank identical base rows twice, once without linkage data and once with linkage data. Assert exact equality for:

```python
protected = ["bond_code", "score", "rank", "qualification", "eligible_for_top", "action"]
pd.testing.assert_frame_equal(base_ranked[protected], overlay_ranked[protected])
assert list(base_top10["bond_code"]) == list(overlay_top10["bond_code"])
```

Also assert that the overlay run contains the expected deterministic label.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py tests/test_cb_ranking_output.py -q`

Expected: FAIL because ranked output does not expose linkage fields.

- [ ] **Step 3: Attach the overlay after original decisions**

Extend `OUTPUT_COLUMNS` and `_ensure_columns` with the new raw/output fields. Call `classify_linkage` only after the existing score, risk, qualification, and action columns are final. Do not include linkage fields in `sort_values`, `_qualification`, `_risk_penalty`, or exclusion logic.

- [ ] **Step 4: Preserve fields through Top10 and dashboard records**

Verify `_select_diversified_top` and `records(...)` retain the added columns without changing selection.

- [ ] **Step 5: Run integration tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py tests/test_cb_ranking_output.py tests/test_dashboard_schema.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/superpower/skills/convertible_bond_ranking/handler.py tests/test_cb_linkage_overlay.py tests/test_cb_ranking_output.py
git commit -m "feat: attach convertible linkage guidance"
```

---

### Task 4: Surface the overlay in the page and deterministic chat

**Files:**
- Modify: `frontend/assets/app.js`
- Modify: `frontend/assets/strategy-config.js`
- Modify: `backend/superpower/chat/orchestrator.py`
- Modify: `tests/test_chat_convertible_detail.py`
- Modify: `tests/test_frontend_etf_label.py`
- Modify: `tests/frontend/strategy-config.test.js`

**Interfaces:**
- Consumes: dashboard rows with linkage values and deterministic labels.
- Produces: concise abnormal-only table label, detail values, and chat explanation that explicitly says the original rank is unchanged.

- [ ] **Step 1: Write failing frontend and chat tests**

Assert that:

- CB tables include a `短期联动` column bound to `linkage_state`.
- `linkage_note` receives a wrapping text class.
- normal states render as `--` in list context.
- single-bond chat includes raw stock/bond returns, premium change, linkage note, and `不改变原排名`.

- [ ] **Step 2: Run UI/chat tests and verify RED**

Run:

```bash
PYTHONPATH=backend .venv/bin/pytest tests/test_chat_convertible_detail.py tests/test_frontend_etf_label.py -q
node --test tests/frontend/strategy-config.test.js
```

Expected: FAIL on missing linkage presentation.

- [ ] **Step 3: Add table and detail presentation**

Add `linkage_state` and `linkage_note` to CB display data. Use a formatter that returns `--` for `正常联动` and `数据不足`, while preserving `关注补涨`, `谨慎追涨`, `联动走弱`, and `数据待核验`.

- [ ] **Step 4: Extend deterministic chat**

In `_single_convertible_diagnosis_answer`, add one separate sentence:

```python
f"短期联动：正股 {stock_return}%，转债 {bond_return}%，溢价率变化 {premium_change} 个百分点；{linkage_note or '暂无异常提示'}。该提示不改变原排名。"
```

Mirror the same meaning in local frontend chat fallback.

- [ ] **Step 5: Run UI/chat tests and verify GREEN**

Run:

```bash
PYTHONPATH=backend .venv/bin/pytest tests/test_chat_convertible_detail.py tests/test_frontend_etf_label.py -q
node --test tests/frontend/strategy-config.test.js
node --check frontend/assets/app.js
node --check frontend/assets/strategy-config.js
```

Expected: PASS with clean syntax.

- [ ] **Step 6: Commit Task 4**

```bash
git add frontend/assets/app.js frontend/assets/strategy-config.js backend/superpower/chat/orchestrator.py tests/test_chat_convertible_detail.py tests/test_frontend_etf_label.py tests/frontend/strategy-config.test.js
git commit -m "feat: show convertible linkage guidance"
```

---

### Task 5: Run the customer snapshot and complete regression verification

**Files:**
- Runtime input: `data/wind/current/03_可转债数据.xlsx` (ignored customer data copy)
- Verify: `outputs/latest/dashboard.json`
- Verify: `outputs/latest/audit.json`

**Interfaces:**
- Consumes: `03_可转债数据-v2-20260710-快照.xlsx` copied to the configured runtime filename.
- Produces: refreshed dashboard/report with linkage guidance and an audit trail.

- [ ] **Step 1: Copy the customer snapshot to the configured local input path**

```bash
cp "/Users/bobby/Desktop/ai money/ai_research_superpower/data/wind/current/03_可转债数据-v2-20260710-快照.xlsx" "data/wind/current/03_可转债数据.xlsx"
```

- [ ] **Step 2: Run the daily workflow with strict audit**

```bash
PYTHONPATH=backend .venv/bin/python -m superpower.cli.run_daily \
  --root-dir "$PWD" \
  --etf-file "$PWD/data/wind/current/01_ETF清单和日频公式.xlsx" \
  --tl-file "$PWD/data/wind/current/02_TL日频公式.xlsx" \
  --cb-file "$PWD/data/wind/current/03_可转债数据.xlsx" \
  --disable-llm --strict-audit
```

Expected: workflow success and `outputs/latest/audit.json` status `PASS`.

- [ ] **Step 3: Compare original rankings against the pre-overlay baseline**

Check the protected fields and Top10 codes against the same workbook parsed with linkage disabled. Expected: exact equality.

- [ ] **Step 4: Run complete verification**

```bash
PYTHONPATH=backend .venv/bin/pytest -q
node --test tests/frontend/strategy-config.test.js
node --check frontend/assets/app.js
node --check frontend/assets/strategy-config.js
git diff --check
```

Expected: zero failures and no diff whitespace errors.

- [ ] **Step 5: Reload the local preview and visually inspect CB tables**

Confirm that abnormal linkage labels remain readable, normal rows show no verbose note, and the original ranking/order is unchanged.
