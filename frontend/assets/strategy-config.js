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

  function showV2StateColumns(generated) {
    return generated?.strategy_id === "trend_pullback_v2";
  }

  function tableColumnClass(key) {
    return ["signal_reason", "watch_type", "missing_condition", "suggested_action", "decision_reason"].includes(key)
      ? "long-text-column"
      : "";
  }

  function strategyStateLabel(key, value) {
    const labels = {
      medium_status: {
        trend_confirmed: "趋势已确认",
        trend_not_confirmed: "趋势未确认",
        do_not_participate: "暂不参与",
        data_unavailable: "数据不足",
        not_applicable: "原策略不适用",
      },
      short_entry_status: {
        can_enter: "可考虑入场",
        close_watch: "密切观察",
        overheated_do_not_chase: "过热不追",
        waiting_confirmation: "等待确认",
        waiting_pullback: "等待回踩",
        no_entry: "暂无入场",
        data_unavailable: "数据不足",
        legacy_buy: "原策略建仓候选",
        legacy_watch: "原策略观察",
        legacy_neutral: "原策略未触发",
      },
    };
    return labels[key]?.[value] || value || "--";
  }

  return { deepMerge, normalizeStrategyResponse, generatedResultState, showV2StateColumns, tableColumnClass, strategyStateLabel };
});
