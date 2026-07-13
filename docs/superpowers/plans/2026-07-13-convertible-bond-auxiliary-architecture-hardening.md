# Convertible Bond Auxiliary Architecture Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the existing convertible-bond risk, qualification, score and rank as the sole decision layer while turning the four new daily linkage fields into a non-ranking auxiliary overlay, then harden strategy identity, persistence, documentation, secrets and browser behavior.

**Architecture:** Split the current handler into a base-strategy registry and an auxiliary-overlay registry. `legacy_v1` remains the base decision plugin; `dynamic_v2` becomes the default enabled overlay and may emit only auxiliary fields. Dashboard and database records carry base/overlay identities plus a complete CB configuration hash, while the UI renders only actionable auxiliary warnings.

**Tech Stack:** Python 3.11+, pandas, SQLite, vanilla JavaScript, Node test runner, pytest, Playwright for browser smoke tests.

## Global Constraints

- Dynamic auxiliary data must never change exclusion, base score, base grade, qualification, action or rank.
- Do not add a combined/comprehensive score.
- Normal linkage is hidden from the main table; only `关注补涨`, `谨慎追涨`, `联动走弱` and `数据不足` are user-visible.
- Wind/Excel refresh workflow, ETF rules, TL rules and formal backtesting are out of scope.
- Old dashboard and database records must remain readable.
- Follow red-green-refactor for every production change.

---

### Task 1: Define base-strategy and auxiliary-overlay contracts

**Files:**
- Create: `backend/superpower/skills/convertible_bond_ranking/contracts.py`
- Create: `backend/superpower/skills/convertible_bond_ranking/registry.py`
- Modify: `backend/superpower/skills/convertible_bond_ranking/strategy.py`
- Test: `tests/test_cb_strategy_config.py`

**Interfaces:**
- Produces: `CBBaseStrategy`, `CBAuxiliaryOverlay`, `CBStrategyIdentity`, `CBStrategyRegistry`, `default_cb_registry()`, `cb_config_hash(config)`.
- Consumes: existing `CBStrategyMetadata` and normalized `convertible_bond` configuration.

- [ ] **Step 1: Write failing registry and hash tests**

```python
def test_default_cb_registry_has_legacy_base_and_dynamic_overlay() -> None:
    registry = default_cb_registry()
    assert registry.base("legacy_v1").strategy_id == "legacy_v1"
    assert registry.overlay("dynamic_v2").overlay_id == "dynamic_v2"


def test_cb_config_hash_changes_when_overlay_threshold_changes() -> None:
    left = cb_config_hash({"auxiliary_overlay": {"overlay_id": "dynamic_v2", "settings": {"stock_strong_threshold": 3}}})
    right = cb_config_hash({"auxiliary_overlay": {"overlay_id": "dynamic_v2", "settings": {"stock_strong_threshold": 4}}})
    assert left != right
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_cb_strategy_config.py`

Expected: import failure for the new registry/hash API.

- [ ] **Step 3: Implement immutable contracts and explicit registries**

```python
@dataclass(frozen=True)
class CBStrategyIdentity:
    strategy_id: str
    strategy_version: str
    overlay_id: str
    overlay_version: str
    overlay_enabled: bool
    config_hash: str


class CBAuxiliaryOverlay(Protocol):
    overlay_id: str
    version: str
    def evaluate(self, row: Mapping[str, Any], settings: Mapping[str, Any]) -> Mapping[str, Any]: ...
```

`CBStrategyRegistry` must reject duplicate IDs and unknown lookups. `cb_config_hash` must serialize normalized CB configuration with sorted keys and SHA-256.

- [ ] **Step 4: Normalize the new configuration shape**

```json
{
  "base_strategy": "legacy_v1",
  "auxiliary_overlay": {
    "enabled": true,
    "overlay_id": "dynamic_v2",
    "settings": {}
  }
}
```

Read old `active_strategy=dynamic_v2` as `base_strategy=legacy_v1` plus enabled `dynamic_v2` overlay. Preserve old `legacy_v1` as the same base with the overlay disabled.

- [ ] **Step 5: Run focused tests and commit**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_cb_strategy_config.py`

Expected: PASS.

Commit: `git add backend/superpower/skills/convertible_bond_ranking/contracts.py backend/superpower/skills/convertible_bond_ranking/registry.py backend/superpower/skills/convertible_bond_ranking/strategy.py tests/test_cb_strategy_config.py && git commit -m "refactor: define convertible strategy registries"`

---

### Task 2: Make dynamic v2 auxiliary-only and repair score semantics

**Files:**
- Create: `backend/superpower/skills/convertible_bond_ranking/strategies/__init__.py`
- Create: `backend/superpower/skills/convertible_bond_ranking/strategies/legacy_v1.py`
- Create: `backend/superpower/skills/convertible_bond_ranking/overlays/__init__.py`
- Create: `backend/superpower/skills/convertible_bond_ranking/overlays/dynamic_v2.py`
- Modify: `backend/superpower/skills/convertible_bond_ranking/handler.py`
- Modify: `backend/superpower/skills/convertible_bond_ranking/linkage.py`
- Test: `tests/test_cb_linkage_overlay.py`
- Test: `tests/test_cb_ranking_output.py`

**Interfaces:**
- Produces base fields `base_score`, `score`, `base_grade`, `qualification`, `eligible_for_top`, `not_top_reason`, `rank`.
- Produces auxiliary fields `auxiliary_score`, `auxiliary_state`, `auxiliary_note`, `auxiliary_data_quality`, `auxiliary_components`.
- Preserves legacy read aliases only in compatibility serialization, not in current UI columns.

- [ ] **Step 1: Add a failing invariance test**

```python
def test_auxiliary_overlay_never_changes_base_decision_or_rank() -> None:
    without_overlay = rank_convertible_bonds(frame(), params(auxiliary_enabled=False))
    with_overlay = rank_convertible_bonds(frame(), params(auxiliary_enabled=True))
    protected = ["bond_code", "score", "base_score", "base_grade", "qualification", "eligible_for_top", "action", "rank"]
    pd.testing.assert_frame_equal(without_overlay[protected], with_overlay[protected])
    assert with_overlay["auxiliary_score"].notna().any()
```

- [ ] **Step 2: Add a failing language-consistency test**

```python
def test_low_score_reason_names_the_base_score() -> None:
    row = ranked_row(base_score=22.49, auxiliary_score=60.62)
    assert row["score"] == 22.49
    assert row["base_grade"] == "E"
    assert "基础分低于30" in row["not_top_reason"]
    assert "综合分" not in row["not_top_reason"]
```

- [ ] **Step 3: Run focused tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_cb_linkage_overlay.py tests/test_cb_ranking_output.py`

Expected: failures because current dynamic score changes `score` and rank.

- [ ] **Step 4: Extract the base plugin and overlay implementation**

Move dynamic evaluation behind:

```python
overlay_result = registry.overlay(identity.overlay_id).evaluate(row, overlay_settings)
```

The handler must calculate qualification and rank from `base_score`, set `score = base_score`, then attach auxiliary fields after rank is final. Remove the `if active_strategy == "dynamic_v2"` branch.

- [ ] **Step 5: Rename user-facing base semantics**

Set `base_grade = _score_grade(base_score)` and change reasons to `基础分低于30` and `基础分低于50`. Keep `score_grade` as a deprecated payload alias for old consumers, but current dashboard/UI must prefer `base_grade`.

- [ ] **Step 6: Run focused tests and commit**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_cb_linkage_overlay.py tests/test_cb_ranking_output.py tests/test_cb_strategy_config.py`

Expected: PASS.

Commit: `git add backend/superpower/skills/convertible_bond_ranking tests/test_cb_linkage_overlay.py tests/test_cb_ranking_output.py && git commit -m "refactor: make convertible dynamics auxiliary only"`

---

### Task 3: Publish complete strategy identity and configuration freshness

**Files:**
- Modify: `backend/superpower/skills/report_generation/handler.py`
- Modify: `backend/superpower/server/app.py`
- Modify: `frontend/assets/strategy-config.js`
- Test: `tests/test_dashboard_schema.py`
- Test: `tests/test_cb_strategy_config.py`
- Test: `tests/frontend/strategy-config.test.js`

**Interfaces:**
- Dashboard `convertible_bond.strategy` gains `base_strategy_id`, `base_strategy_version`, `overlay_id`, `overlay_version`, `overlay_enabled`, `config_hash`, `source_date`.
- `/api/strategy-params` returns `cbConfigHash` and base/overlay metadata.

- [ ] **Step 1: Write failing dashboard and frontend identity tests**

```javascript
test("convertible result waits for refresh when config hash differs", () => {
  const saved = { savedConfigHash: "new", confirmedStrategyId: "legacy_v1", confirmedStrategyVersion: "1.0.0" };
  const generated = { config_hash: "old", strategy_id: "legacy_v1", strategy_version: "1.0.0" };
  assert.equal(generatedResultState(saved, generated).status, "saved_waiting_refresh");
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_dashboard_schema.py tests/test_cb_strategy_config.py && node --test tests/frontend/strategy-config.test.js`

Expected: CB config hash assertion fails.

- [ ] **Step 3: Add identity to report and API payloads**

Use the same `cb_config_hash(normalize_cb_config(params))` function in both code paths. Do not compute hashes independently in JavaScript.

- [ ] **Step 4: Use the shared freshness helper for CB**

Replace the hand-written strategy-ID-only check in `renderCbStrategySelector()` with `generatedResultState(cbState, generated)`.

- [ ] **Step 5: Run tests and commit**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_dashboard_schema.py tests/test_cb_strategy_config.py && node --test tests/frontend/strategy-config.test.js`

Expected: PASS.

Commit: `git add backend/superpower/skills/report_generation/handler.py backend/superpower/server/app.py frontend/assets/strategy-config.js tests/test_dashboard_schema.py tests/test_cb_strategy_config.py tests/frontend/strategy-config.test.js && git commit -m "feat: track convertible strategy configuration identity"`

---

### Task 4: Simplify the convertible-bond page and move detail out of the table

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/assets/app.js`
- Modify: `frontend/assets/strategy-config.js`
- Modify: `frontend/assets/styles.css`
- Test: `tests/frontend/strategy-config.test.js`

**Interfaces:**
- Settings expose `基础策略：原策略` and `动态辅助：启用/关闭`.
- Main table shows `基础分`, `基础等级`, and `辅助提示`; it does not show comprehensive score, dynamic grade, normal linkage or duplicated linkage columns.

- [ ] **Step 1: Write failing column-visibility tests**

```javascript
test("normal auxiliary state is hidden while actionable warnings remain", () => {
  assert.equal(auxiliaryStateLabel("正常联动"), "--");
  assert.equal(auxiliaryStateLabel("关注补涨"), "关注补涨");
  assert.equal(auxiliaryStateLabel("数据不足"), "数据不足");
});
```

Add a source assertion that the current CB column definition contains neither `综合分` nor `动态状态`.

- [ ] **Step 2: Run the frontend test and verify RED**

Run: `node --test tests/frontend/strategy-config.test.js`

Expected: missing helper or forbidden label assertion failure.

- [ ] **Step 3: Replace the strategy selector and table columns**

Render a fixed base-strategy description and an overlay checkbox. Current rows use:

```javascript
["base_score", "基础分"],
["base_grade", "基础等级"],
["auxiliary_state", "辅助提示"],
["not_top_reason", "未入选原因"]
```

Hide `正常联动`; show a concise state pill only for actionable states or missing data.

- [ ] **Step 4: Add an expandable details control**

The details panel contains raw daily stock/bond returns, premium change, auxiliary score/components, full risk reasons and ranking breakdown. Long text must not remain in narrow main-table cells.

- [ ] **Step 5: Add width and wrapping safeguards**

Use a CB-specific minimum table width, horizontal scrolling and normal word wrapping. Do not use fixed narrow widths for explanation fields.

- [ ] **Step 6: Run frontend tests and commit**

Run: `node --test tests/frontend/strategy-config.test.js`

Expected: PASS.

Commit: `git add frontend/index.html frontend/assets/app.js frontend/assets/strategy-config.js frontend/assets/styles.css tests/frontend/strategy-config.test.js && git commit -m "feat: simplify convertible auxiliary guidance"`

---

### Task 5: Persist the complete convertible-bond universe with source dates

**Files:**
- Modify: `backend/superpower/db/schema.sql`
- Modify: `backend/superpower/db/migrations.py`
- Modify: `backend/superpower/db/ingest.py`
- Modify: `backend/superpower/db/repositories.py`
- Create: `tests/test_db_ingest.py`
- Test: `tests/test_etf_db_payload.py`

**Interfaces:**
- `convertible_bond_snapshots` stores every ranked and excluded row for a report date.
- New columns: `source_date`, `record_status`, `base_strategy_id`, `base_strategy_version`, `overlay_id`, `overlay_version`, `overlay_enabled`, `config_hash`, `base_score`, `base_grade`, `auxiliary_score`, `auxiliary_state`.

- [ ] **Step 1: Write a failing all-universe ingest test**

```python
def test_ingest_persists_ranked_and_excluded_convertibles(tmp_path: Path) -> None:
    ingest_dashboard(tmp_path, "run-1", dashboard_with_one_ranked_and_two_excluded())
    rows = query_all_convertibles(tmp_path, "2026-07-10")
    assert len(rows) == 3
    assert {row["record_status"] for row in rows} == {"ranked", "excluded"}
    assert {row["source_date"] for row in rows} == {"2026-07-06"}
```

- [ ] **Step 2: Run DB tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_db_ingest.py tests/test_etf_db_payload.py`

Expected: only ranked rows are present or new columns are missing.

- [ ] **Step 3: Add schema version 2 migration**

Increment `SCHEMA_VERSION` to 2. Add columns only if absent using `PRAGMA table_info`, so existing databases migrate in place.

- [ ] **Step 4: Ingest ranked and excluded rows in one transaction**

Build rows from both `cbRanked` and `cbExcluded`, add `record_status`, preserve each row's actual `date` as `source_date`, and retain the complete row in `payload_json`.

- [ ] **Step 5: Keep repository reads backward compatible**

Missing new values from old records return `None` or safe defaults. Latest date queries continue using `report_date`, while responses expose `source_date` separately.

- [ ] **Step 6: Run DB tests and commit**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_db_ingest.py tests/test_etf_db_payload.py`

Expected: PASS.

Commit: `git add backend/superpower/db tests/test_db_ingest.py tests/test_etf_db_payload.py && git commit -m "feat: persist full convertible daily universe"`

---

### Task 6: Update reports, deterministic chat and strategy manuals

**Files:**
- Modify: `backend/superpower/chat/orchestrator.py`
- Modify: `backend/superpower/skills/report_generation/handler.py`
- Modify: `backend/superpower/skills/convertible_bond_ranking/SKILL.md`
- Modify: `docs/CONVERTIBLE_BOND_MODEL.md`
- Modify: `docs/DATA_CONTRACT.md`
- Modify: `docs/DASHBOARD_SCHEMA.md`
- Create: `docs/strategies/CB-legacy-v1.md`
- Create: `docs/strategies/CB-dynamic-v2-auxiliary.md`
- Test: `tests/test_chat_convertible_detail.py`
- Test: `tests/test_dashboard_schema.py`

**Interfaces:**
- Chat must call the score `基础分` and the overlay `动态辅助`.
- Excel/dashboard current outputs use auxiliary field names but may read deprecated dynamic aliases from old records.

- [ ] **Step 1: Write failing chat wording tests**

```python
assert "基础分" in answer
assert "动态辅助" in answer
assert "综合分" not in answer
assert "不改变资格和排名" in answer
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_chat_convertible_detail.py tests/test_dashboard_schema.py`

- [ ] **Step 3: Update serializers and deterministic explanations**

Current output names use `auxiliary_*`; compatibility readers map old `dynamic_*` fields when current names are absent. Report summaries must not say a combined score failed a qualification threshold.

- [ ] **Step 4: Write two short user manuals**

Each manual must state purpose, inputs, outputs, what it does not change, data timing, and limitations. Keep the user-facing section under two pages of Markdown per strategy.

- [ ] **Step 5: Run tests and commit**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_chat_convertible_detail.py tests/test_dashboard_schema.py`

Expected: PASS.

Commit: `git add backend/superpower/chat/orchestrator.py backend/superpower/skills/report_generation/handler.py backend/superpower/skills/convertible_bond_ranking/SKILL.md docs tests/test_chat_convertible_detail.py tests/test_dashboard_schema.py && git commit -m "docs: explain convertible base and auxiliary layers"`

---

### Task 7: Stop saving plaintext model keys and lock Python dependencies

**Files:**
- Modify: `backend/superpower/server/app.py`
- Modify: `frontend/assets/app.js`
- Modify: `frontend/index.html`
- Modify: `.env.example`
- Modify: `初始化环境.command`
- Create: `requirements.lock`
- Create: `tests/test_model_config_api.py`
- Test: `tests/frontend/strategy-config.test.js`

**Interfaces:**
- Model config save accepts model/provider settings but never persists `api_key`.
- Runtime secrets come from `OPENAI_API_KEY` or the configured environment-variable name.

- [ ] **Step 1: Write a failing secret-persistence test**

```python
def test_merge_model_config_drops_plaintext_api_key() -> None:
    merged = _merge_model_config_secrets({"api_key": "old"}, {"api_key": "new", "primary_model": "gpt-5.5"})
    assert "api_key" not in merged
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_model_config_api.py`

- [ ] **Step 3: Remove key entry from the settings page**

Show only whether the environment variable is available and provide the `.env.example` variable name. Keep verification endpoints able to use a one-time key supplied in the request without writing it to disk.

- [ ] **Step 4: Pin the tested environment**

Create `requirements.lock` with exact direct versions used by the verified environment:

```text
numpy==2.5.1
pandas==3.0.3
openpyxl==3.1.5
reportlab==5.0.0
pytest==8.4.2
```

Update initialization instructions to install `requirements.lock`.

- [ ] **Step 5: Run focused tests and commit**

Run: `PYTHONPATH=backend .venv/bin/pytest -q tests/test_model_config_api.py && node --test tests/frontend/strategy-config.test.js`

Expected: PASS.

Commit: `git add backend/superpower/server/app.py frontend/assets/app.js frontend/index.html .env.example 初始化环境.command requirements.lock tests/test_model_config_api.py tests/frontend/strategy-config.test.js && git commit -m "security: keep model keys out of config files"`

---

### Task 8: Add browser smoke coverage and perform full verification

**Files:**
- Create: `package.json`
- Create: `tests/browser/cb-auxiliary.spec.js`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Browser test uses the local server and confirms settings identity plus main-table semantics.

- [ ] **Step 1: Add Playwright as an isolated dev dependency**

```json
{
  "private": true,
  "scripts": {"test:browser": "playwright test tests/browser/cb-auxiliary.spec.js"},
  "devDependencies": {"@playwright/test": "1.61.1"}
}
```

Install with `npm install` and `npx playwright install chromium` only after network approval if the package or browser is not already cached.

- [ ] **Step 2: Write the browser smoke test**

```javascript
test("CB page presents base decisions and auxiliary warnings without combined score", async ({ page }) => {
  await page.goto("http://127.0.0.1:8771/frontend/index.html#cb");
  await expect(page.getByText("基础分")).toBeVisible();
  await expect(page.getByText("基础等级")).toBeVisible();
  await expect(page.getByText("综合分")).toHaveCount(0);
  await expect(page.getByText("动态状态")).toHaveCount(0);
});
```

- [ ] **Step 3: Run all automated verification**

Run:

```bash
PYTHONPATH=backend .venv/bin/pytest -q
node --test tests/frontend/*.test.js
npm run test:browser
git diff --check
```

Expected: all tests pass and `git diff --check` prints no output.

- [ ] **Step 4: Run a real daily refresh against the current workbooks**

Verify audit PASS, confirm base score/rank invariance against `legacy_v1`, confirm auxiliary warnings do not change qualification, confirm the database row count equals ranked plus excluded rows, and record the CB source date separately from the report date.

- [ ] **Step 5: Manually inspect the local CB page**

At desktop width, verify no explanation text renders one character per line, normal linkage is absent, actionable warnings are concise, and strategy freshness changes to current only after refresh.

- [ ] **Step 6: Commit verification assets**

Commit: `git add package.json package-lock.json tests/browser .gitignore README.md && git commit -m "test: cover convertible auxiliary workflow"`
