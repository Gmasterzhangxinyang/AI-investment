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
    const cbConfirmedStrategyId = params.convertible_bond?.base_strategy || "legacy_v1";
    const cbBaseStrategies = payload.cbBaseStrategies || (payload.cbStrategies || []).filter((item) => item.strategy_id === "legacy_v1");
    const cbSelected = cbBaseStrategies.find((item) => item.strategy_id === cbConfirmedStrategyId);
    const cbOverlay = params.convertible_bond?.auxiliary_overlay || { enabled: false, overlay_id: "dynamic_v2" };
    return {
      params,
      strategies: clone(payload.etfStrategies || []),
      confirmedStrategyId,
      confirmedStrategyVersion: selected?.version || "",
      savedConfigHash: payload.etfConfigHash || "",
      cb: {
        strategies: clone(cbBaseStrategies),
        overlays: clone(payload.cbAuxiliaryOverlays || []),
        confirmedStrategyId: cbConfirmedStrategyId,
        confirmedStrategyVersion: cbSelected?.version || "",
        overlayId: cbOverlay.overlay_id || "dynamic_v2",
        overlayEnabled: Boolean(cbOverlay.enabled),
        savedConfigHash: payload.cbConfigHash || "",
      },
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

  function showLegacyRiskOverlay(generated) {
    return generated?.strategy_id === "legacy_v1";
  }

  function showCbDynamicColumns(generated) {
    return generated?.strategy_id === "dynamic_v2";
  }

  function showCbLegacyLinkageColumns(generated) {
    return generated?.strategy_id !== "dynamic_v2";
  }

  function tableColumnClass(key) {
    return ["signal_reason", "watch_type", "missing_condition", "suggested_action", "decision_reason", "risk_overlay_summary", "fund_flow_note", "linkage_note", "auxiliary_evidence"].includes(key)
      ? "long-text-column"
      : "";
  }

  function linkageStateLabel(value) {
    return ["正常联动", "数据不足", "未启用", "", null, undefined].includes(value) ? "--" : value;
  }

  function auxiliaryStateLabel(value) {
    return ["未启用", "", null, undefined].includes(value) ? "--" : value;
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

  function historicalComparisonRows(rows) {
    const groups = new Map();
    (rows || [])
      .filter((row) => row.state_type === "can_enter" && [1, 3, 5, 10, 20].includes(Number(row.horizon)))
      .forEach((row) => {
        const horizon = Number(row.horizon);
        const key = `${row.strategy_id}|${horizon}`;
        const current = groups.get(key) || {
          strategy_id: row.strategy_id,
          horizon,
          event_count: 0,
          complete_horizon_count: 0,
          weighted_positive: 0,
          weighted_return: 0,
          weighted_adverse: 0,
          false_reversal_10d_count: 0,
        };
        const complete = Number(row.complete_horizon_count || 0);
        current.event_count += Number(row.event_count || 0);
        current.complete_horizon_count += complete;
        current.weighted_positive += Number(row.positive_return_rate || 0) * complete;
        current.weighted_return += Number(row.mean_return || 0) * complete;
        current.weighted_adverse += Number(row.mean_maximum_adverse_excursion || 0) * complete;
        current.false_reversal_10d_count += Number(row.false_reversal_10d_count || 0);
        groups.set(key, current);
      });
    return Array.from(groups.values())
      .map((row) => {
        const denominator = row.complete_horizon_count || 1;
        return {
          strategy_id: row.strategy_id,
          horizon: row.horizon,
          event_count: row.event_count,
          complete_horizon_count: row.complete_horizon_count,
          positive_return_rate: Number((row.weighted_positive / denominator).toFixed(12)),
          mean_return: Number((row.weighted_return / denominator).toFixed(12)),
          mean_maximum_adverse_excursion: Number((row.weighted_adverse / denominator).toFixed(12)),
          false_reversal_10d_count: row.false_reversal_10d_count,
          false_reversal_10d_rate: row.horizon === 10
            ? Number((row.false_reversal_10d_count / denominator).toFixed(12))
            : null,
        };
      })
      .sort((left, right) => left.horizon - right.horizon || left.strategy_id.localeCompare(right.strategy_id));
  }

  function actionableSystemNotices(warnings) {
    const hiddenPatterns = [
      "最新日期",
      "最新日期一致",
      "无效交易行过滤数",
      "数据质检WARN数量",
      "历史诊断WARN数量",
      "回测诊断WARN数量",
    ];
    const actionablePatterns = ["源文件", "数据接入", "必要字段", "数据不足", "读取失败", "缺失", "不存在", "无法生成"];
    return (warnings || []).filter((warning) => {
      const text = String(warning || "");
      return text
        && actionablePatterns.some((pattern) => text.includes(pattern))
        && !hiddenPatterns.some((pattern) => text.includes(pattern));
    });
  }

  function systemStatusLabel(data) {
    const runStatus = String(data?.run_info?.status || "").toLowerCase();
    const qualityStatus = String(data?.data_quality?.overall_status || "").toUpperCase();
    const notices = actionableSystemNotices(data?.run_info?.warnings || []);
    if (["failed", "error"].includes(runStatus) || qualityStatus === "ERROR" || notices.length) return "需要处理";
    return "数据已更新";
  }

  function qualityMetric(rows, item, fallback = 0) {
    const row = (rows || []).find((entry) => String(entry?.item || "") === item);
    const value = Number(row?.detail ?? row?.value);
    return Number.isFinite(value) ? value : fallback;
  }

  function parameterGuideModel(params = {}) {
    const etf = params.etf || {};
    const activeStrategyId = etf.active_strategy || "legacy_v1";
    const v2 = etf.strategy_profiles?.trend_pullback_v2 || {};
    const medium = v2.medium_trend || {};
    const short = v2.short_entry || {};
    const tl = params.tl || {};
    const flow = tl.fund_flow || {};
    const cb = params.convertible_bond || {};
    const auxiliary = cb.auxiliary_overlay || { enabled: false, overlay_id: "dynamic_v2" };
    const number = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;
    const percent = (value, fallback) => `${(number(value, fallback) * 100).toFixed(2)}%`;
    const decimal = (value, fallback) => number(value, fallback).toFixed(2);

    return {
      etfStrategies: [
        {
          strategyId: "legacy_v1",
          title: "原策略",
          isActive: activeStrategyId === "legacy_v1",
          items: [
            "策略定位：沿用原有强弱评分和趋势共振筛选，适合观察 ETF 的中短线趋势机会。",
            `建仓候选：主要看 MA5/MA10、日 MACD 和量能是否共振；当前建仓量能阈值为 ${decimal(etf.buy_volume_ratio_min, 1.1)} 倍。`,
            `退出提示：持仓后跌破 MA10 或 MA5，并分别达到 ${decimal(etf.sell_ma10_volume_ratio_min, 1.2)} / ${decimal(etf.sell_ma5_volume_ratio_min, 1.2)} 倍量能时提示风险。`,
            "风险辅助：MA20 方向、周 MACD、短期过热和假反转只作风险提示，不改变原策略候选、评分和排名。",
          ],
        },
        {
          strategyId: "trend_pullback_v2",
          title: "2.0 趋势回踩策略",
          isActive: activeStrategyId === "trend_pullback_v2",
          items: [
            `中期趋势：至少需要 ${number(medium.minimum_history_rows, 180)} 个交易日；按最近 ${number(medium.ma20_slope_lookback, 5)} 个交易日计算 MA20 斜率，变化在 ±${percent(medium.ma20_flat_tolerance, 0.003)} 内视为走平。MA20 向下或周 MACD 绿柱扩大时暂不参与。`,
            "密切观察：MA5 已在 MA10 上方，同时日 MACD 绿柱缩短或转红；系统再提示周 MACD 是否改善、MA20 是否走平。",
            "趋势确认：价格和 MA5 位于 MA20 上方、MA20 走平或向上，并且周 MACD 与日 MACD 均为红柱。",
            `过热不追：单日涨幅达到 ${percent(short.overheat_daily_return_min, 0.04)}、阳线实体占比达到 ${percent(short.overheat_body_ratio_min, 0.6)}、量能达到 ${decimal(short.overheat_volume_ratio_min, 1.8)} 倍且价格高于 MA5 达到 ${percent(short.overheat_ma5_distance_min, 0.03)} 时，进入 ${number(short.overheat_cooldown_days, 3)} 个交易日冷却。`,
            `入场确认：趋势确认后，可等待后续突破趋势确认日高点，或等待缩量回踩 MA5/MA10 后重新站稳；最长观察 ${number(short.pullback_max_age, 10)} 个交易日。排名和退出规则继续沿用原策略。`,
          ],
        },
      ],
      tlItems: [
        `技术状态：日线回看 ${number(tl.daily_kdj_lookback, 3)} 日、周线回看 ${number(tl.weekly_kdj_lookback, 2)} 周，结合 KDJ 与 MACD 判断；周线不利时${tl.weekly_no_trade_hard_veto === false ? "仅提示风险" : "不升级为建仓候选"}。`,
        `份额分级：30 年国债 ETF 当日份额变化以亿份计，绝对值低于 ${decimal(flow.light_threshold, 0.03)} 为正常，${decimal(flow.light_threshold, 0.03)}～${decimal(flow.large_threshold, 0.05)} 为轻度，${decimal(flow.large_threshold, 0.05)}～${decimal(flow.extreme_threshold, 0.07)} 为明显，达到 ${decimal(flow.extreme_threshold, 0.07)} 为极端。正数表示净申购，负数表示净赎回。`,
        `近 ${number(flow.rolling_days, 5)} 日方向：累计变化达到 ±${decimal(flow.rolling_direction_threshold, 0.08)} 亿份才判断为持续流入或持续流出，用于观察技术状态与资金是否背离。`,
        `数据边界：单日绝对值超过 ${decimal(flow.review_threshold, 0.2)} 亿份时提示核验，并且不计入近 ${number(flow.rolling_days, 5)} 日方向；份额变化只作辅助，不改变原 TL 状态。`,
      ],
      cbBaseItems: [
        `候选范围：价格在 ${decimal(cb.min_price, 100)}～${decimal(cb.price_limit, 140)} 元之间，并通过 ST、评级、强赎、规模和行业集中度等硬风控。`,
        `YTM 风控：高于 ${decimal(cb.high_ytm_hard_exclude, 15)}% 或低于 ${decimal(cb.severe_negative_ytm_hard_exclude, -5)}% 时排除，避免把信用风险或严重负收益误当成机会。`,
        `溢价率风控：达到 ${decimal(cb.high_premium_penalty_threshold, 35)}% 开始扣分，达到 ${decimal(cb.high_premium_hard_exclude, 50)}% 时排除。`,
        "基础评分：综合基本面、溢价率、YTM、剩余期限、信用、强赎状态和剩余规模；Top 表只展示通过资格检查的候选。",
      ],
      cbAuxiliary: {
        enabled: Boolean(auxiliary.enabled),
        title: "四项短期动态辅助",
        items: [
          "观察内容：正股涨跌、转债涨跌、相对强弱差和溢价率变化，用于识别补涨、追涨及联动走弱。",
          "使用边界：动态辅助只增加观察提示，不改变原始分数和排名，也不会单独生成买卖指令。",
        ],
      },
    };
  }

  return { deepMerge, normalizeStrategyResponse, generatedResultState, showV2StateColumns, showLegacyRiskOverlay, showCbDynamicColumns, showCbLegacyLinkageColumns, tableColumnClass, strategyStateLabel, linkageStateLabel, auxiliaryStateLabel, historicalComparisonRows, actionableSystemNotices, systemStatusLabel, qualityMetric, parameterGuideModel };
});
