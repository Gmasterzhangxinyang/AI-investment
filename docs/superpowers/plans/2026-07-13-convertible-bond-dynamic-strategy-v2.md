# Convertible Bond Dynamic Strategy v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dynamic_v2` the default selectable convertible-bond strategy, combine the unchanged base-quality score with a validated short-term dynamic score, and keep `legacy_v1` available as an exact fallback.

**Architecture:** Add a small convertible-bond strategy configuration/registry boundary, keep the existing handler as the shared risk-gate and base-score engine, and apply a strategy result only after qualification is fixed. The dynamic scorer is a pure function; dashboard, settings, persistence, and deterministic chat consume its explicit fields.

**Tech Stack:** Python 3.12, pandas, pytest, JSON configuration, vanilla JavaScript, Node test runner, SQLite JSON snapshots.

## Global Constraints

- `dynamic_v2` is the default; `legacy_v1` remains selectable and exactly reproduces the current score and order.
- Qualification, hard exclusions, risk level, and action are computed from the base layer only.
- Dynamic data may reorder rows only inside the same qualification pool.
- Valid dynamic data uses `score = base_score * 0.8 + dynamic_score * 0.2`.
- Missing, inconsistent, or failed dynamic data uses `score = base_score`.
- Blank values are never converted to zero.
- The AI explains deterministic fields and never creates or changes a score.

---

### Task 1: Add the convertible-bond strategy contract and validated configuration

**Files:**
- Create: `backend/superpower/skills/convertible_bond_ranking/strategy.py`
- Modify: `configs/strategy_params.json`
- Modify: `backend/superpower/server/app.py`
- Create: `tests/test_cb_strategy_config.py`

**Interfaces:**
- Produces: `CBStrategyMetadata`, `CBConfigurationError`, `normalize_cb_config(params)`, `cb_strategy_metadata()`.
- Known IDs: `legacy_v1`, `dynamic_v2`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_dynamic_v2_is_default() -> None:
    config = normalize_cb_config({"convertible_bond": {}})
    assert config["active_strategy"] == "dynamic_v2"

def test_unknown_cb_strategy_is_rejected() -> None:
    with pytest.raises(CBConfigurationError, match="unknown active convertible-bond strategy"):
        normalize_cb_config({"convertible_bond": {"active_strategy": "missing"}})

def test_metadata_exposes_two_plugins() -> None:
    assert [item.strategy_id for item in cb_strategy_metadata()] == ["legacy_v1", "dynamic_v2"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_strategy_config.py -q`

Expected: collection fails because `strategy.py` does not exist.

- [ ] **Step 3: Implement the contract and defaults**

Implement immutable metadata with display names `原策略` and `动态策略`, versions `1.0.0` and `2.0.0`. `normalize_cb_config` copies the input section, defaults to `dynamic_v2`, rejects unknown explicit IDs, and normalizes `base_weight=0.8`, `dynamic_weight=0.2` so they sum to one.

Add to `configs/strategy_params.json`:

```json
"active_strategy": "dynamic_v2",
"strategy_profiles": {
  "legacy_v1": {},
  "dynamic_v2": {"base_weight": 0.8, "dynamic_weight": 0.2}
}
```

Extend `_validate_strategy_params` and `_strategy_params_payload` so the API rejects unknown IDs and returns `cbStrategies`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_strategy_config.py tests/test_etf_strategy_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/superpower/skills/convertible_bond_ranking/strategy.py backend/superpower/server/app.py configs/strategy_params.json tests/test_cb_strategy_config.py
git commit -m "feat: add convertible bond strategy plugins"
```

---

### Task 2: Build the pure dynamic scorer

**Files:**
- Modify: `backend/superpower/skills/convertible_bond_ranking/linkage.py`
- Modify: `configs/strategy_params.json`
- Modify: `tests/test_cb_linkage_overlay.py`

**Interfaces:**
- Produces: `score_dynamic_linkage(row, config) -> dict[str, object]`.
- Output keys: `dynamic_score`, `dynamic_state`, `dynamic_note`, `dynamic_data_quality`, `dynamic_components`.

- [ ] **Step 1: Replace the uncommitted temporary ±3/±5 tests with failing 0–100 scorer tests**

```python
def test_dynamic_scorer_rewards_valid_catch_up() -> None:
    result = score_dynamic_linkage(catch_up_row(), DYNAMIC_CONFIG)
    assert result["dynamic_state"] == "关注补涨"
    assert result["dynamic_score"] > 50

def test_dynamic_scorer_penalizes_chase_and_joint_weakness() -> None:
    assert score_dynamic_linkage(chase_row(), DYNAMIC_CONFIG)["dynamic_score"] < 50
    assert score_dynamic_linkage(weak_row(), DYNAMIC_CONFIG)["dynamic_score"] < 50

def test_dynamic_scorer_returns_none_when_data_is_missing_or_inconsistent() -> None:
    assert score_dynamic_linkage(missing_row(), DYNAMIC_CONFIG)["dynamic_score"] is None
    assert score_dynamic_linkage(inconsistent_row(), DYNAMIC_CONFIG)["dynamic_score"] is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py -q`

Expected: FAIL because `score_dynamic_linkage` is missing.

- [ ] **Step 3: Implement the scorer**

Use bounded piecewise scores around neutral `50` for stock return, bond return, relative return (`bond_return - stock_return`), and premium change. Combine component scores with weights `0.20`, `0.15`, `0.30`, `0.35`, clip to `[0, 100]`, and retain the existing validation identity/tolerance. Classification priority remains `数据待核验 > 联动走弱 > 谨慎追涨 > 关注补涨 > 正常联动`.

Store all component thresholds and weights under `convertible_bond.dynamic_scoring`; do not use hidden constants for market thresholds.

- [ ] **Step 4: Run boundary tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_linkage_overlay.py -q`

Expected: PASS, including exact-threshold, just-below-threshold, missing, and inconsistent cases.

- [ ] **Step 5: Commit**

```bash
git add backend/superpower/skills/convertible_bond_ranking/linkage.py configs/strategy_params.json tests/test_cb_linkage_overlay.py
git commit -m "feat: score convertible bond daily linkage"
```

---

### Task 3: Integrate v1/v2 without weakening qualification

**Files:**
- Modify: `backend/superpower/skills/convertible_bond_ranking/handler.py`
- Modify: `tests/test_cb_ranking_output.py`
- Modify: `tests/test_cb_linkage_overlay.py`

**Interfaces:**
- Adds output fields: `strategy_id`, `strategy_version`, `base_score`, `dynamic_score`, `dynamic_state`, `dynamic_note`, `dynamic_data_quality`, `dynamic_components`.
- `score` remains the final sortable score.

- [ ] **Step 1: Write failing characterization and integration tests**

```python
def test_legacy_v1_exactly_preserves_current_results() -> None:
    expected = rank_with_pre_v2_fixture()
    actual = rank_convertible_bonds(data, params(active_strategy="legacy_v1"))
    pd.testing.assert_frame_equal(actual[PROTECTED_COLUMNS], expected[PROTECTED_COLUMNS])

def test_dynamic_v2_blends_scores_but_preserves_qualification() -> None:
    legacy = rank_convertible_bonds(data, params(active_strategy="legacy_v1"))
    dynamic = rank_convertible_bonds(data, params(active_strategy="dynamic_v2"))
    row = dynamic.set_index("bond_code").loc["A"]
    assert row["score"] == round(row["base_score"] * 0.8 + row["dynamic_score"] * 0.2, 2)
    assert qualification_map(dynamic) == qualification_map(legacy)
    assert action_map(dynamic) == action_map(legacy)

def test_dynamic_v2_falls_back_per_row() -> None:
    row = rank_convertible_bonds(missing_dynamic_data, params(active_strategy="dynamic_v2")).iloc[0]
    assert row["dynamic_score"] is pd.NA or pd.isna(row["dynamic_score"])
    assert row["score"] == row["base_score"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_ranking_output.py tests/test_cb_linkage_overlay.py -q`

Expected: FAIL because strategy identity and layered scores are absent.

- [ ] **Step 3: Implement layered scoring in the handler**

Save the original computed score to `base_score`. Compute `score_grade`, `qualification`, `eligible_for_top`, risk level, and action from `base_score`. For `legacy_v1`, set `score=base_score` and dynamic fields empty. For `dynamic_v2`, call the pure scorer and blend only valid rows. Sort by qualification bucket first, then final `score`, credit, redemption, and premium so dynamic data cannot cross qualification pools.

On a whole-plugin exception, rerun the strategy application as `legacy_v1`, set `strategy_fallback_reason`, and preserve the base outputs.

- [ ] **Step 4: Run focused regression tests and verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_cb_ranking_output.py tests/test_cb_linkage_overlay.py tests/test_commercial_components.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/superpower/skills/convertible_bond_ranking/handler.py tests/test_cb_ranking_output.py tests/test_cb_linkage_overlay.py
git commit -m "feat: rank convertibles with dynamic strategy v2"
```

---

### Task 4: Expose strategy identity, persistence, and page controls

**Files:**
- Modify: `backend/superpower/skills/report_generation/handler.py`
- Modify: `backend/superpower/db/ingest.py`
- Modify: `frontend/index.html`
- Modify: `frontend/assets/app.js`
- Modify: `frontend/assets/strategy-config.js`
- Modify: `tests/test_dashboard_schema.py`
- Modify: `tests/test_cb_strategy_config.py`
- Modify: `tests/frontend/strategy-config.test.js`

**Interfaces:**
- Dashboard `convertible_bond.strategy`: `strategy_id`, `strategy_version`, `display_name`, `fallback_reason`.
- API `cbStrategies`: selectable metadata.

- [ ] **Step 1: Write failing dashboard/frontend tests**

Assert that the dashboard records strategy identity, the API exposes both plugins, `normalizeStrategyResponse` keeps CB state, and `showCbDynamicColumns` is true only for generated `dynamic_v2` results.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONPATH=backend .venv/bin/pytest tests/test_dashboard_schema.py tests/test_cb_strategy_config.py -q
node --test tests/frontend/strategy-config.test.js
```

Expected: FAIL on missing CB strategy metadata and helpers.

- [ ] **Step 3: Implement dashboard and settings UI**

Add a `可转债当前策略` selector beside the ETF selector. Saving writes `convertible_bond.active_strategy`; refreshed dashboard identity determines which columns render. Under `dynamic_v2`, show `基础分`, `动态分`, `综合分`, `动态状态`; under `legacy_v1`, show only the original `评分` and hide dynamic columns.

Keep raw dynamic values and all score fields inside `payload_json`; `_upsert_convertibles` already persists the complete row JSON, so no destructive schema migration is required.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
PYTHONPATH=backend .venv/bin/pytest tests/test_dashboard_schema.py tests/test_cb_strategy_config.py tests/test_etf_strategy_api.py -q
node --test tests/frontend/strategy-config.test.js
node --check frontend/assets/app.js
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/superpower/skills/report_generation/handler.py backend/superpower/db/ingest.py frontend/index.html frontend/assets/app.js frontend/assets/strategy-config.js tests/test_dashboard_schema.py tests/test_cb_strategy_config.py tests/frontend/strategy-config.test.js
git commit -m "feat: expose convertible dynamic strategy controls"
```

---

### Task 5: Update deterministic explanations and verify the real workflow

**Files:**
- Modify: `backend/superpower/chat/orchestrator.py`
- Modify: `frontend/assets/app.js`
- Modify: `backend/superpower/skills/convertible_bond_ranking/SKILL.md`
- Modify: `tests/test_chat_convertible_detail.py`
- Modify: `tests/test_frontend_etf_label.py`

**Interfaces:**
- Chat explains current strategy and score layers from the dashboard/tool row only.

- [ ] **Step 1: Write failing explanation tests**

For `dynamic_v2`, require `基础分`, `动态分`, `综合分`, and the deterministic dynamic state. For `legacy_v1`, require `原策略` and forbid invented dynamic values. For fallback rows, require the recorded fallback reason.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest tests/test_chat_convertible_detail.py tests/test_frontend_etf_label.py -q`

Expected: FAIL because the old copy still says the overlay never changes rank.

- [ ] **Step 3: Implement strategy-aware explanations**

Replace `不改变原排名` with the correct v2 explanation: qualification and hard risk remain based on the base layer, while the dynamic layer can adjust order inside the same qualification pool. Keep the old explanation for `legacy_v1` only.

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
PYTHONPATH=backend .venv/bin/pytest -q
node --test tests/frontend/*.test.js
node --check frontend/assets/app.js
git diff --check
```

Expected: all tests pass, syntax checks exit `0`, and `git diff --check` is empty.

- [ ] **Step 5: Run the customer snapshot workflow and inspect output**

Run the existing daily workflow against the configured customer snapshot. Verify the audit is `PASS`, dashboard strategy is `dynamic_v2`, every valid row satisfies the 80/20 formula, missing rows fall back to base score, and `legacy_v1` remains selectable without changing its fixture output.

- [ ] **Step 6: Commit**

```bash
git add backend/superpower/chat/orchestrator.py frontend/assets/app.js backend/superpower/skills/convertible_bond_ranking/SKILL.md tests/test_chat_convertible_detail.py tests/test_frontend_etf_label.py
git commit -m "feat: explain convertible dynamic scores"
```
