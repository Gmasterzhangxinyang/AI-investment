const test = require("node:test");
const assert = require("node:assert/strict");
const { deepMerge, normalizeStrategyResponse, generatedResultState } = require("../../frontend/assets/strategy-config.js");

test("deepMerge preserves dormant profiles and replaces arrays", () => {
  const current = { etf: { diagnostic_strategies: ["legacy_v1"], strategy_profiles: { future_v3: { kept: true } } } };
  const merged = deepMerge(current, { etf: { diagnostic_strategies: ["trend_pullback_v2"] } });
  assert.deepEqual(merged.etf.diagnostic_strategies, ["trend_pullback_v2"]);
  assert.deepEqual(merged.etf.strategy_profiles.future_v3, { kept: true });
});

test("normalizeStrategyResponse keeps server-confirmed selection", () => {
  const result = normalizeStrategyResponse({
    params: { etf: { active_strategy: "legacy_v1" } },
    etfStrategies: [{ strategy_id: "legacy_v1", display_name: "原始策略", version: "1.0.0" }],
    etfConfigHash: "abc",
  });
  assert.equal(result.confirmedStrategyId, "legacy_v1");
  assert.equal(result.confirmedStrategyVersion, "1.0.0");
  assert.equal(result.savedConfigHash, "abc");
});

test("saved config newer than dashboard waits for refresh", () => {
  assert.equal(generatedResultState(
    { savedConfigHash: "new", confirmedStrategyId: "trend_pullback_v2" },
    { config_hash: "old", strategy_id: "legacy_v1", strategy_version: "1.0.0" },
  ).status, "saved_waiting_refresh");
});

test("matching identity is current", () => {
  assert.equal(generatedResultState(
    { savedConfigHash: "same", confirmedStrategyId: "trend_pullback_v2", confirmedStrategyVersion: "2.0.0" },
    { config_hash: "same", strategy_id: "trend_pullback_v2", strategy_version: "2.0.0" },
  ).status, "current");
});
