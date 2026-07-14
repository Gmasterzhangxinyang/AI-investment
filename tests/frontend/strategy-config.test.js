const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { deepMerge, normalizeStrategyResponse, generatedResultState, showV2StateColumns, showLegacyRiskOverlay, showCbDynamicColumns, showCbLegacyLinkageColumns, tableColumnClass, strategyStateLabel, linkageStateLabel, auxiliaryStateLabel, historicalComparisonRows, actionableSystemNotices, systemStatusLabel } = require("../../frontend/assets/strategy-config.js");

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
    params: {
      etf: { active_strategy: "legacy_v1" },
      convertible_bond: {
        base_strategy: "legacy_v1",
        auxiliary_overlay: { enabled: true, overlay_id: "dynamic_v2", settings: {} },
      },
    },
    etfStrategies: [{ strategy_id: "legacy_v1", display_name: "原始策略", version: "1.0.0" }],
    cbBaseStrategies: [{ strategy_id: "legacy_v1", display_name: "原策略", version: "1.0.0" }],
    cbAuxiliaryOverlays: [{ overlay_id: "dynamic_v2", display_name: "动态辅助", version: "2.0.0" }],
    cbConfigHash: "cb-hash",
    etfConfigHash: "abc",
  });

  assert.equal(result.cb.confirmedStrategyId, "legacy_v1");
  assert.equal(result.cb.confirmedStrategyVersion, "1.0.0");
  assert.equal(result.cb.overlayId, "dynamic_v2");
  assert.equal(result.cb.overlayEnabled, true);
  assert.equal(result.cb.savedConfigHash, "cb-hash");
});

test("convertible result waits for refresh when config hash differs", () => {
  assert.equal(generatedResultState(
    { savedConfigHash: "new", confirmedStrategyId: "legacy_v1", confirmedStrategyVersion: "1.0.0" },
    { config_hash: "old", strategy_id: "legacy_v1", strategy_version: "1.0.0" },
  ).status, "saved_waiting_refresh");
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

test("convertible auxiliary state hides normal noise but shows missing data", () => {
  assert.equal(auxiliaryStateLabel("正常联动"), "--");
  assert.equal(auxiliaryStateLabel("数据不足"), "数据不足");
  assert.equal(auxiliaryStateLabel("关注补涨"), "关注补涨");
  assert.equal(auxiliaryStateLabel("谨慎追涨"), "谨慎追涨");
  assert.equal(auxiliaryStateLabel("联动走弱"), "联动走弱");
});

test("convertible table source contains no combined-score or dynamic-state labels", () => {
  const source = fs.readFileSync(path.join(__dirname, "../../frontend/assets/app.js"), "utf8");
  assert.equal(source.includes('["score", "综合分"]'), false);
  assert.equal(source.includes('["dynamic_state", "动态状态"]'), false);
});

test("model settings never accept or persist a plaintext OpenAI key", () => {
  const source = fs.readFileSync(path.join(__dirname, "../../frontend/assets/app.js"), "utf8");
  assert.equal(source.includes('id="openai-api-key"'), false);
  assert.equal(source.includes("config.api_key ="), false);
  assert.equal(source.includes('id="edit-openai-key"'), false);
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

test("system notices hide test-environment date differences and technical row noise", () => {
  const warnings = [
    "ETF最新日期：2026-07-03。若不是上一交易日附近，需确认 Wind 是否刷新",
    "ETF/TL最新日期一致：ETF=2026-07-03 TL=2026-07-10。两者不一致时报告仍可出，但需人工复核",
    "ETF无效交易行过滤数：43835。空模板行不进入指标计算",
    "ETF源文件不存在",
  ];
  assert.deepEqual(actionableSystemNotices(warnings), ["ETF源文件不存在"]);
});

test("system status uses plain user-facing labels", () => {
  assert.equal(systemStatusLabel({ run_info: { status: "partial_success" }, data_quality: { overall_status: "WARN" } }), "数据已更新");
  assert.equal(systemStatusLabel({ run_info: { status: "failed" }, data_quality: { overall_status: "ERROR" } }), "需要处理");
});

test("system navigation hides raw agent audit and exposes technical details on demand", () => {
  const html = fs.readFileSync(path.join(__dirname, "../../frontend/index.html"), "utf8");
  const styles = fs.readFileSync(path.join(__dirname, "../../frontend/assets/styles.css"), "utf8");
  assert.equal(html.includes('<a href="#agents">运行审计</a>'), false);
  assert.equal(html.includes('href="#data">系统状态</a>'), true);
  assert.equal(html.includes('id="technical-details"'), true);
  assert.equal(html.includes("今日更新状态"), true);
  assert.equal(styles.includes(".system-technical-details:not([open]) > .technical-sections"), true);
});
