const test = require("node:test");
const assert = require("node:assert/strict");
const { deepMerge, normalizeStrategyResponse, generatedResultState, showV2StateColumns, showLegacyRiskOverlay, showCbDynamicColumns, showCbLegacyLinkageColumns, tableColumnClass, strategyStateLabel, linkageStateLabel, historicalComparisonRows } = require("../../frontend/assets/strategy-config.js");

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

test("normalizeStrategyResponse keeps convertible strategy selection", () => {
  const result = normalizeStrategyResponse({
    params: { etf: { active_strategy: "legacy_v1" }, convertible_bond: { active_strategy: "dynamic_v2" } },
    etfStrategies: [{ strategy_id: "legacy_v1", display_name: "原始策略", version: "1.0.0" }],
    cbStrategies: [
      { strategy_id: "legacy_v1", display_name: "原策略", version: "1.0.0" },
      { strategy_id: "dynamic_v2", display_name: "动态策略", version: "2.0.0" },
    ],
    etfConfigHash: "abc",
  });

  assert.equal(result.cb.confirmedStrategyId, "dynamic_v2");
  assert.equal(result.cb.confirmedStrategyVersion, "2.0.0");
  assert.equal(result.cb.strategies.length, 2);
});

test("convertible dynamic columns follow generated result identity", () => {
  assert.equal(showCbDynamicColumns({ strategy_id: "dynamic_v2", strategy_version: "2.0.0" }), true);
  assert.equal(showCbDynamicColumns({ strategy_id: "legacy_v1", strategy_version: "1.0.0" }), false);
  assert.equal(showCbDynamicColumns(null), false);
});

test("legacy linkage columns are hidden for dynamic v2", () => {
  assert.equal(showCbLegacyLinkageColumns({ strategy_id: "dynamic_v2" }), false);
  assert.equal(showCbLegacyLinkageColumns({ strategy_id: "legacy_v1" }), true);
  assert.equal(showCbLegacyLinkageColumns(null), true);
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

test("medium and short state columns only show for generated v2 results", () => {
  assert.equal(showV2StateColumns({ strategy_id: "legacy_v1", strategy_version: "1.0.0" }), false);
  assert.equal(showV2StateColumns({ strategy_id: "trend_pullback_v2", strategy_version: "2.0.0" }), true);
  assert.equal(showV2StateColumns(null), false);
});

test("legacy result shows risk overlay while v2 keeps its own state columns", () => {
  assert.equal(showLegacyRiskOverlay({ strategy_id: "legacy_v1", strategy_version: "1.0.0" }), true);
  assert.equal(showLegacyRiskOverlay({ strategy_id: "trend_pullback_v2", strategy_version: "2.0.0" }), false);
  assert.equal(showLegacyRiskOverlay(null), false);
});

test("ETF explanation columns receive a wrapping class", () => {
  assert.equal(tableColumnClass("watch_type"), "long-text-column");
  assert.equal(tableColumnClass("signal_reason"), "long-text-column");
  assert.equal(tableColumnClass("suggested_action"), "long-text-column");
  assert.equal(tableColumnClass("risk_overlay_summary"), "long-text-column");
  assert.equal(tableColumnClass("fund_flow_note"), "long-text-column");
  assert.equal(tableColumnClass("linkage_note"), "long-text-column");
  assert.equal(tableColumnClass("score"), "");
});

test("convertible linkage state hides normal noise and keeps warnings", () => {
  assert.equal(linkageStateLabel("正常联动"), "--");
  assert.equal(linkageStateLabel("数据不足"), "--");
  assert.equal(linkageStateLabel("关注补涨"), "关注补涨");
  assert.equal(linkageStateLabel("谨慎追涨"), "谨慎追涨");
});

test("strategy state codes render as concise Chinese labels", () => {
  assert.equal(strategyStateLabel("medium_status", "trend_confirmed"), "趋势已确认");
  assert.equal(strategyStateLabel("short_entry_status", "overheated_do_not_chase"), "过热不追");
  assert.equal(strategyStateLabel("short_entry_status", "can_enter"), "可考虑入场");
});

test("historical comparison combines v2 entry routes with weighted metrics", () => {
  const rows = historicalComparisonRows([
    { strategy_id: "legacy_v1", state_type: "can_enter", entry_route: "", horizon: 10, event_count: 10, complete_horizon_count: 10, positive_return_rate: 0.5, mean_return: 0.02, mean_maximum_adverse_excursion: -0.03, false_reversal_10d_count: 5 },
    { strategy_id: "trend_pullback_v2", state_type: "can_enter", entry_route: "breakout_confirmation", horizon: 10, event_count: 4, complete_horizon_count: 4, positive_return_rate: 0.75, mean_return: 0.03, mean_maximum_adverse_excursion: -0.02, false_reversal_10d_count: 1 },
    { strategy_id: "trend_pullback_v2", state_type: "can_enter", entry_route: "pullback_confirmation", horizon: 10, event_count: 6, complete_horizon_count: 6, positive_return_rate: 0.5, mean_return: 0.01, mean_maximum_adverse_excursion: -0.04, false_reversal_10d_count: 3 },
    { strategy_id: "trend_pullback_v2", state_type: "close_watch", entry_route: "", horizon: 10, event_count: 99, complete_horizon_count: 99, positive_return_rate: 1 },
  ]);
  assert.equal(rows.length, 2);
  const v2 = rows.find((row) => row.strategy_id === "trend_pullback_v2");
  assert.equal(v2.complete_horizon_count, 10);
  assert.equal(v2.positive_return_rate, 0.6);
  assert.equal(v2.mean_return, 0.018);
  assert.equal(v2.mean_maximum_adverse_excursion, -0.032);
  assert.equal(v2.false_reversal_10d_count, 4);
  assert.equal(v2.false_reversal_10d_rate, 0.4);
});

test("historical comparison keeps 1 3 5 10 and 20 trading day horizons", () => {
  const rows = [1, 3, 5, 10, 20].map((horizon) => ({
    strategy_id: "legacy_v1",
    state_type: "can_enter",
    horizon,
    complete_horizon_count: 10,
    positive_return_rate: 0.5,
  }));
  assert.deepEqual(historicalComparisonRows(rows).map((row) => row.horizon), [1, 3, 5, 10, 20]);
});
