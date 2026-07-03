const state = {
  data: null,
  isRefreshing: false,
  refreshJobId: null,
  refreshJob: null,
  selectedWatchCode: null,
  assets: [],
  selectedAssetCode: null,
  assetDetail: null,
  strategyParams: null,
  dbStatus: null,
  isChatting: false,
  isDeepReviewing: false,
};

const pageTitles = {
  chat: "投研问答",
  report: "每日报告",
  etf: "ETF",
  tl: "TL",
  cb: "可转债",
  signals: "今日信号",
  watchlist: "关注池",
  assets: "标的档案",
  data: "数据状态",
  agents: "运行审计",
  settings: "策略参数",
};

const refreshStepLabels = {
  "config-agent": "读取策略参数",
  "source-archive-agent": "检查并归档源文件",
  "data-agent": "读取 Wind Excel 数据",
  "portfolio-agent": "读取 ETF 持仓状态",
  "qa-agent": "检查数据完整性",
  "indicator-agent": "计算均线、MACD、KDJ 和量能",
  "etf-agent": "生成 ETF 建仓/平仓/关注信号",
  "tl-agent": "生成 TL 日频交易状态",
  "convertible-bond-agent": "筛选并打分可转债",
  "backtest-agent": "执行运行诊断",
  "risk-agent": "生成组合风险提示",
  "ai-research-committee-agent": "生成 AI 复核意见",
  "explanation-agent": "生成客户可读解释",
  "report-agent": "生成日报文件和前端数据",
  "qa-audit": "复核日报数据是否一致",
  "database-ingest": "写入本地数据库",
};

const integerParamPaths = new Set([
  "tl.daily_kdj_lookback",
  "tl.weekly_kdj_lookback",
  "convertible_bond.max_per_industry_l1",
  "convertible_bond.max_per_industry_l2",
  "convertible_bond.no_redemption_valid_days",
]);

const formatNumber = (value) => {
  if (Array.isArray(value)) return value.filter((item) => item !== null && item !== undefined && item !== "").join("；") || "--";
  if (value && typeof value === "object") return JSON.stringify(value);
  if (typeof value !== "number") return value ?? "--";
  if (Math.abs(value) >= 100) return value.toFixed(2);
  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
};

const formatValue = (key, value) => {
  if ((key === "date" || key.endsWith("_date")) && typeof value === "string") return value.slice(0, 10);
  if (key.includes("return") && typeof value === "number") return `${(value * 100).toFixed(2)}%`;
  return formatNumber(value);
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

const pick = (rows, item) => rows.find((row) => row.item === item)?.value ?? "--";

async function loadDashboard() {
  const status = document.getElementById("data-status");
  try {
    const response = await fetch(`/outputs/latest/dashboard.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    status.textContent = "数据正常";
    status.classList.add("ok");
    status.classList.remove("warn");
    render();
    loadDbStatus();
    loadAssets();
    loadStrategyParams();
  } catch (error) {
    status.textContent = "数据不可用";
    status.classList.remove("ok");
    status.classList.add("warn");
    document.getElementById("research-summary").textContent =
      "无法读取 /outputs/latest/dashboard.json。请先运行后端工作流，或从项目根目录启动本地服务。";
  }
}

async function loadDbStatus() {
  const container = document.getElementById("db-status-grid");
  if (!container) return;
  try {
    const response = await fetch(`/api/db/status?ts=${Date.now()}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || `HTTP ${response.status}`);
    state.dbStatus = result;
    renderDbStatus(result);
    render();
  } catch (error) {
    state.dbStatus = null;
    container.innerHTML = `<div class="context-item"><span>状态</span><strong>不可用</strong></div><div class="context-item"><span>原因</span><strong>${escapeHtml(error.message)}</strong></div>`;
  }
}

function renderDbStatus(result) {
  const container = document.getElementById("db-status-grid");
  const latest = result.latestRun || {};
  const counts = result.tableCounts || {};
  const items = [
    ["数据库文件", result.exists ? "已连接" : "缺失"],
    ["日志模式", result.pragmas?.journal_mode || "--"],
    ["结构版本", result.pragmas?.user_version ?? "--"],
    ["最近运行", latest.run_id || "--"],
    ["报告日期", latest.report_date || "--"],
    ["运行状态", latest.status || "--"],
    ["标的数量", counts.asset_master ?? 0],
    ["行情指标行", counts.market_daily_indicators ?? 0],
    ["ETF明细行", counts.etf_daily_bars ?? 0],
    ["ETF信号行", counts.etf_daily_signals ?? 0],
    ["TL信号行", counts.tl_daily_signals ?? 0],
    ["可转债行", counts.convertible_bond_snapshots ?? 0],
    ["刷新任务", counts.refresh_jobs ?? 0],
    ["质检记录", counts.data_quality_checks ?? 0],
    ["运行审计", counts.agent_runs ?? 0],
  ];
  container.innerHTML = items
    .map((item) => `<div class="context-item"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`)
    .join("");
}

async function loadAssets() {
  try {
    const response = await fetch(`/api/assets?ts=${Date.now()}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.assets = result.assets || [];
    if (!state.selectedAssetCode && state.assets.length) {
      state.selectedAssetCode = state.assets[0].code;
    }
    renderAssets();
    if (state.selectedAssetCode) loadAssetDetail(state.selectedAssetCode);
  } catch (error) {
    renderTable("asset-table", [], [["code", "代码"]]);
    document.getElementById("asset-detail-title").textContent = `标的列表不可用：${error.message}`;
  }
}

async function loadAssetDetail(code) {
  if (!code) return;
  state.selectedAssetCode = code;
  try {
    const response = await fetch(`/api/assets/detail?code=${encodeURIComponent(code)}&ts=${Date.now()}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.assetDetail = result.detail || null;
    renderAssets();
    renderAssetDetail();
  } catch (error) {
    document.getElementById("asset-detail-title").textContent = `读取失败：${error.message}`;
  }
}

async function loadStrategyParams() {
  try {
    const response = await fetch(`/api/strategy-params?ts=${Date.now()}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.strategyParams = result.params || {};
    renderStrategyParams();
  } catch (error) {
    const status = document.getElementById("params-status");
    if (status) status.textContent = `参数读取失败：${error.message}`;
  }
}

async function saveStrategyParams() {
  if (!state.strategyParams) return;
  const status = document.getElementById("params-status");
  try {
    syncParamsFromForm();
    const response = await fetch("/api/strategy-params", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: state.strategyParams }),
    });
    const result = await response.json();
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.strategyParams = result.params;
    if (status) status.textContent = "参数已保存。下一次刷新数据时生效。";
    renderStrategyParams();
  } catch (error) {
    if (status) status.textContent = `保存失败：${error.message}`;
  }
}

function renderAssets() {
  const query = (document.getElementById("asset-search")?.value || "").trim().toLowerCase();
  const rows = state.assets
    .filter((asset) => {
      if (!query) return true;
      return `${asset.code || ""} ${asset.name || ""} ${asset.asset_type || ""}`.toLowerCase().includes(query);
    })
    .slice(0, 260);
  renderTable("asset-table", rows, [
    ["asset_type", "类型"],
    ["name", "名称"],
    ["code", "代码"],
    ["last_seen_date", "最新日期"],
  ]);
  document.querySelectorAll("#asset-table tbody tr").forEach((tr, index) => {
    const row = rows[index];
    if (!row) return;
    tr.classList.toggle("selected", row.code === state.selectedAssetCode);
    tr.addEventListener("click", () => loadAssetDetail(row.code));
  });
}

function renderAssetDetail() {
  const detail = state.assetDetail || {};
  const asset = detail.asset || {};
  document.getElementById("asset-detail-title").textContent = `${asset.name || "--"} ${asset.code || ""}`;
  if (asset.asset_type === "CONVERTIBLE") {
    const snapshot = detail.convertibleSnapshot || {};
    const dashboardHit = findConvertibleDashboardRow(asset.code);
    if (!snapshot.bond_code && !snapshot.report_date && !dashboardHit) {
      renderMetricList("asset-detail-metrics", [
        ["类型", "可转债"],
        ["当前状态", detail.convertibleMessage || "当前报告未提供该转债排序快照"],
        ["说明", "通常表示该标的未进入当前可转债候选池，或已被价格、评级、强赎、YTM、规模等风控条件过滤。"],
      ]);
      renderTable("asset-history-table", [], [["item", "暂无当前快照"]]);
      return;
    }
    const payload = snapshot.payload_json || {};
    const cbRow = mergeRecords(dashboardHit?.row || {}, payload, snapshot);
    const qualification = cbRow.qualification || dashboardHit?.bucket || "";
    cbRow.detail_date = cbRow.report_date || String(cbRow.date || "").slice(0, 10);
    cbRow.qualification_display = qualificationLabel(qualification);
    cbRow.eligible_for_top_text = cbRow.eligible_for_top === true ? "是" : "否";
    const metrics = [
      ["类型", "可转债"],
      ["当前分层", cbRow.qualification_display],
      ["是否可进合格 Top", cbRow.eligible_for_top_text],
      ["未入 Top 原因", cbRow.not_top_reason || cbRow.excluded_reason || detail.convertibleMessage],
      ["排名", cbRow.rank],
      ["评分", cbRow.score],
      ["评分等级", cbRow.score_grade],
      ["价格", cbRow.price],
      ["评级", cbRow.bond_rating || cbRow.rating],
      ["行业", cbRow.sw_l1],
      ["存续规模", cbRow.remaining_size],
      ["转股溢价率", cbRow.conversion_premium_rate],
      ["到期收益率", cbRow.ytm],
      ["强赎状态", cbRow.redemption_status],
      ["风险等级", cbRow.risk_level],
      ["风险提示", cbRow.quality_notes || cbRow.risk_flags],
      ["评分依据", cbRow.rank_reason],
      ["数据来源", snapshot.bond_code ? "数据库快照" : "当前 dashboard"],
    ];
    renderMetricList("asset-detail-metrics", metrics);
    renderTable("asset-history-table", [cbRow], [
      ["detail_date", "数据日"],
      ["rank", "排名"],
      ["qualification_display", "分层"],
      ["eligible_for_top_text", "可进Top"],
      ["not_top_reason", "未入Top原因"],
      ["excluded_reason", "排除原因"],
      ["price", "价格"],
      ["conversion_premium_rate", "转股溢价率"],
      ["ytm", "到期收益率"],
      ["deducted_profit_growth", "扣非增速"],
      ["score", "评分"],
    ]);
    return;
  }

  const latest = detail.latestMarketBar || {};
  const metrics = [
    ["类型", asset.asset_type || "--"],
    ["最新日期", latest.trade_date],
    ["收盘", latest.close],
    ["MA5", latest.ma5],
    ["MA10", latest.ma10],
    ["MA20", latest.ma20],
    ["量能倍数", latest.vol_ratio60],
    ["MACD柱", latest.macd_hist],
    ["KDJ J", latest.kdj_j],
  ];
  if (detail.tlState) {
    metrics.push(["TL状态", detail.tlState.state], ["周线MACD", detail.tlState.weekly_macd_reason]);
  }
  renderMetricList("asset-detail-metrics", metrics);
  renderTable("asset-history-table", detail.marketHistory || [], [
    ["trade_date", "日期"],
    ["close", "收盘"],
    ["ma5", "MA5"],
    ["ma10", "MA10"],
    ["ma20", "MA20"],
    ["vol_ratio60", "量能倍数"],
    ["macd_hist", "MACD柱"],
    ["kdj_j", "KDJ J"],
  ]);
}

function findConvertibleDashboardRow(code) {
  const normalized = String(code || "").trim();
  if (!normalized) return null;
  const cb = state.data?.convertible_bond || {};
  const buckets = [
    ["qualified", cb.qualified || cb.top10 || state.data?.cbTop10 || []],
    ["weak_watch", cb.weak_watch || []],
    ["risk_watch", cb.risk_watch || []],
    ["ranked_candidates", cb.candidates || cb.ranked_candidates || state.data?.cbRanked || []],
    ["excluded", cb.excluded || state.data?.cbExcluded || []],
  ];
  for (const [bucket, rows] of buckets) {
    const row = (rows || []).find((item) => String(item.bond_code || item.code || "").trim() === normalized);
    if (row) return { bucket, row };
  }
  return null;
}

function mergeRecords(...records) {
  const merged = {};
  records.forEach((record) => {
    Object.entries(record || {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") merged[key] = value;
    });
  });
  return merged;
}

function qualificationLabel(value) {
  const labels = {
    qualified: "合格候选",
    weak_watch: "弱观察候选",
    risk_watch: "风险观察",
    excluded: "排除列表",
    ranked_candidates: "候选池",
  };
  return labels[value] || value || "--";
}

function renderMetricList(id, metrics) {
  document.getElementById(id).innerHTML = metrics
    .map((item) => `<div><dt>${escapeHtml(item[0])}</dt><dd>${escapeHtml(formatNumber(item[1]))}</dd></div>`)
    .join("");
}

function renderStrategyParams() {
  const params = state.strategyParams;
  const form = document.getElementById("params-form");
  const status = document.getElementById("params-status");
  if (!params || !form) return;
  if (status) status.textContent = "参数已载入。修改后点击 Save Params。";
  const fields = [
    ["ETF", [
      ["etf.buy_volume_ratio_min", "建仓量能倍数", "number"],
      ["etf.sell_ma10_volume_ratio_min", "跌破MA10平仓量能", "number"],
      ["etf.sell_ma5_volume_ratio_min", "跌破MA5平仓量能", "number"],
      ["etf.score_weights.trend", "趋势权重", "number"],
      ["etf.score_weights.macd", "MACD权重", "number"],
      ["etf.score_weights.volume", "量能权重", "number"],
    ]],
    ["TL", [
      ["tl.daily_kdj_lookback", "日线KDJ窗口", "number"],
      ["tl.daily_j_low_threshold", "日线J低位阈值", "number"],
      ["tl.weekly_kdj_lookback", "周线KDJ窗口", "number"],
      ["tl.weekly_j_low_threshold", "周线J低位阈值", "number"],
      ["tl.weekly_no_trade_hard_veto", "周线不做交易硬否决", "checkbox"],
    ]],
    ["可转债", [
      ["convertible_bond.min_price", "最低价格", "number"],
      ["convertible_bond.price_limit", "最高价格上限", "number"],
      ["convertible_bond.high_ytm_hard_exclude", "高YTM硬排除", "number"],
      ["convertible_bond.severe_negative_ytm_hard_exclude", "严重负YTM硬排除", "number"],
      ["convertible_bond.high_premium_penalty_threshold", "高溢价扣分线", "number"],
      ["convertible_bond.high_premium_hard_exclude", "高溢价硬排除", "number"],
      ["convertible_bond.max_per_industry_l1", "一级行业最多", "number"],
      ["convertible_bond.max_per_industry_l2", "二级行业最多", "number"],
      ["convertible_bond.no_redemption_valid_days", "不强赎公告有效天数", "number"],
      ["convertible_bond.exclude_st_stock", "排除ST正股", "checkbox"],
      ["convertible_bond.exclude_unresolved_redemption_trigger", "强赎未明硬排除", "checkbox"],
      ["convertible_bond.negative_ytm_penalty", "负YTM扣分", "number"],
      ["convertible_bond.high_premium_penalty", "高溢价扣分", "number"],
      ["convertible_bond.negative_growth_penalty", "2025负增长扣分", "number"],
      ["convertible_bond.negative_profit_penalty", "扣非净利润为负扣分", "number"],
      ["convertible_bond.unstable_growth_base_penalty", "利润基数异常扣分", "number"],
      ["convertible_bond.growth_winsor_upper", "增长率截尾上限", "number"],
    ]],
    ["可转债权重", [
      ["convertible_bond.score_weights.fundamental", "基本面权重", "number"],
      ["convertible_bond.score_weights.premium", "溢价率权重", "number"],
      ["convertible_bond.score_weights.ytm", "YTM质量权重", "number"],
      ["convertible_bond.score_weights.term", "剩余期限权重", "number"],
      ["convertible_bond.score_weights.credit", "信用权重", "number"],
      ["convertible_bond.score_weights.redemption", "强赎状态权重", "number"],
      ["convertible_bond.score_weights.scale", "规模权重", "number"],
    ]],
  ];
  form.innerHTML = fields
    .map(([group, groupFields]) => `
      <section class="param-group">
        <h3>${escapeHtml(group)}</h3>
        <div class="param-grid">
          ${groupFields.map(([path, label, type]) => renderParamField(path, label, type)).join("")}
        </div>
      </section>
    `)
    .join("");
}

function renderParamField(path, label, type) {
  const value = getByPath(state.strategyParams, path);
  const hint = path.includes("score_weights") ? `<small>小数权重，0.25 = 25%</small>` : "";
  if (type === "checkbox") {
    return `
      <div class="param-field">
        <label>${escapeHtml(label)}</label>
        <input data-param="${escapeHtml(path)}" type="checkbox" ${value ? "checked" : ""} />
        ${hint}
      </div>
    `;
  }
  return `
    <div class="param-field">
      <label>${escapeHtml(label)}</label>
      <input data-param="${escapeHtml(path)}" type="${type}" step="0.01" value="${escapeHtml(value ?? "")}" />
      ${hint}
    </div>
  `;
}

function syncParamsFromForm() {
  document.querySelectorAll("[data-param]").forEach((input) => {
    const path = input.dataset.param;
    const value = input.type === "checkbox" ? input.checked : Number(input.value);
    setByPath(state.strategyParams, path, integerParamPaths.has(path) ? Math.trunc(value) : value);
  });
}

function getByPath(object, path) {
  return path.split(".").reduce((current, key) => (current ? current[key] : undefined), object);
}

function setByPath(object, path, value) {
  const parts = path.split(".");
  const last = parts.pop();
  let cursor = object;
  parts.forEach((part) => {
    if (!cursor[part]) cursor[part] = {};
    cursor = cursor[part];
  });
  cursor[last] = value;
}

async function refreshData() {
  if (state.isRefreshing) return;
  state.isRefreshing = true;
  const status = document.getElementById("data-status");
  const button = document.getElementById("refresh-data");
  button.disabled = true;
  button.textContent = "排队中";
  status.textContent = "排队中";
  status.classList.remove("ok", "warn");

  try {
    const response = await fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const result = await response.json();
    if (!response.ok || !["accepted", "success"].includes(result.status)) {
      const message = result.message || `HTTP ${response.status}`;
      throw new Error(message);
    }
    const job = result.job || {};
    state.refreshJobId = job.job_id;
    state.refreshJob = job;
    updateRefreshMonitor(job);
    button.textContent = "刷新中";
    status.textContent = "刷新中";
    const finishedJob = await pollRefreshJob(job.job_id);
    updateRefreshMonitor(finishedJob);
    await loadDashboard();
    status.textContent = "已更新";
    status.classList.add("ok");
  } catch (error) {
    status.textContent = "刷新失败";
    status.classList.add("warn");
    appendMessage("assistant", `刷新失败：${error.message}\n请确认 Excel 文件路径仍然有效。`, "System");
  } finally {
    state.isRefreshing = false;
    button.disabled = false;
    button.textContent = "一键刷新";
  }
}

async function pollRefreshJob(jobId) {
  if (!jobId) throw new Error("缺少刷新任务ID。");
  const status = document.getElementById("data-status");
  for (let attempt = 0; attempt < 900; attempt += 1) {
    const response = await fetch(`/api/refresh/job/${encodeURIComponent(jobId)}?ts=${Date.now()}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || result.status !== "success") {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
    const job = result.job || {};
    state.refreshJob = job;
    updateRefreshMonitor(job);
    status.textContent = job.status === "running" ? "刷新中" : translateJobStatus(job.status || "queued");
    if (job.status === "success") return job;
    if (job.status === "failed") {
      throw new Error(job.message || job.stderr_tail || "刷新任务失败");
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("刷新任务等待超时。");
}

function updateRefreshMonitor(job) {
  const monitor = document.getElementById("refresh-monitor");
  const stage = document.getElementById("refresh-stage");
  const percent = document.getElementById("refresh-percent");
  const fill = document.getElementById("refresh-bar-fill");
  const log = document.getElementById("refresh-log");
  if (!monitor || !stage || !percent || !fill || !log || !job) return;

  monitor.hidden = false;
  const payload = job.payload_json || {};
  const progress = payload.lastProgress || {};
  const events = Array.isArray(payload.progressEvents) ? payload.progressEvents : [];
  const total = Number(progress.total || events.find((item) => item.total)?.total || 0);
  const index = Number(progress.index || 0);
  const computedPercent = total > 0 ? Math.min(100, Math.max(0, Math.round((index / total) * 100))) : 0;
  const statusText = translateJobStatus(job.status);
  const agent = businessStepName(progress.agent) || "等待运行进度";
  const message = job.message || progress.message || "--";

  stage.textContent = `${statusText} · ${agent} · ${businessMessage(message)}`;
  percent.textContent = job.status === "success" ? "100%" : `${computedPercent}%`;
  percent.classList.toggle("ok", job.status === "success");
  percent.classList.toggle("warn", job.status === "failed");
  fill.style.width = job.status === "success" ? "100%" : `${computedPercent}%`;

  const visibleEvents = events.slice(-8).map((item) => {
    const mark = eventLabel(item.event);
    const duration = item.durationMs ? ` · ${Math.round(item.durationMs / 100) / 10}s` : "";
    return `${item.timestamp || "--"}  ${item.index || "-"}/${item.total || "-"}  ${mark}  ${businessStepName(item.agent)}${duration}`;
  });
  if (!visibleEvents.length) {
    visibleEvents.push(`${job.updated_at || "--"}  ${job.status || "--"}  ${job.message || "--"}`);
  }
  if (job.stderr_tail) visibleEvents.push(`stderr: ${job.stderr_tail.slice(-500)}`);
  log.textContent = visibleEvents.join("\n");
}

function businessStepName(agent) {
  return refreshStepLabels[agent] || agent || "系统流程";
}

function translateJobStatus(status) {
  if (status === "success") return "完成";
  if (status === "failed") return "失败";
  if (status === "queued") return "排队中";
  if (status === "running") return "运行中";
  return status || "等待中";
}

function eventLabel(event) {
  if (event === "agent_started" || event === "phase_started") return "开始";
  if (event === "agent_finished" || event === "phase_finished") return "完成";
  if (event === "workflow_completed") return "主流程完成";
  if (event === "workflow_failed") return "失败";
  return event || "日志";
}

function businessMessage(message) {
  if (!message) return "--";
  return String(message)
    .replace(/^Agent \d+\/\d+ running: /, "正在处理：")
    .replace(/^Agent \d+\/\d+ success: /, "已完成：")
    .replace(/^Phase \d+\/\d+ running: /, "正在处理：")
    .replace(/^Phase \d+\/\d+ success: /, "已完成：")
    .replace("Workflow completed", "主流程已完成，正在做最终校验")
    .replace("Refresh completed", "刷新完成");
}

async function exportPdf() {
  const status = document.getElementById("data-status");
  const button = document.getElementById("export-pdf");
  button.disabled = true;
  button.textContent = "导出中";
  status.textContent = "正在导出 PDF";
  status.classList.remove("ok", "warn");

  try {
    const response = await fetch("/api/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const result = await response.json();
    if (!response.ok || result.status !== "success") {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
    window.open(result.pdfUrl, "_blank");
    status.textContent = "PDF 已生成";
    status.classList.add("ok");
  } catch (error) {
    status.textContent = "PDF 失败";
    status.classList.add("warn");
    appendMessage("assistant", `PDF 导出失败：${error.message}`, "System");
  } finally {
    button.disabled = false;
    button.textContent = "导出 PDF";
  }
}

function render() {
  const data = state.data;
  const summary = data.summary || [];
  document.getElementById("report-date").textContent = data.reportDate || "--";
  document.getElementById("rail-date").textContent = data.reportDate ? `日期 ${data.reportDate}` : "--";
  document.getElementById("report-link").href = data.reportPath ? reportUrl(data.reportPath) : "#";
  document.getElementById("research-summary").textContent = data.researchSummary?.[0]?.content || "暂无解释。";

  renderKpis(summary);
  renderContext(summary);
  const etfBuyColumns = [
    ["name", "标的"],
    ["code", "代码"],
    ["close", "收盘"],
    ["ma5_ma10_signal", "MA5/MA10"],
    ["vol_ratio60", "量能倍数"],
    ["volume_check", "量能检查"],
    ["score", "评分"],
    ["signal_reason", "触发原因"],
  ];
  const etfSellColumns = [
    ["name", "标的"],
    ["code", "代码"],
    ["close", "收盘"],
    ["ma5_ma10_signal", "MA5/MA10"],
    ["vol_ratio60", "量能倍数"],
    ["score", "评分"],
    ["signal_reason", "触发原因"],
  ];
  const etfWatchColumns = [
    ["name", "标的"],
    ["code", "代码"],
    ["close", "收盘"],
    ["ma5_ma10_signal", "MA5/MA10"],
    ["vol_ratio60", "量能倍数"],
    ["watch_type", "关注原因"],
    ["missing_condition", "缺口"],
    ["suggested_action", "动作"],
  ];
  const etfAllColumns = [
    ["rank", "排名"],
    ["name", "标的"],
    ["code", "代码"],
    ["position_status", "持仓状态"],
    ["display_action", "触发状态"],
    ["score", "强弱分"],
    ["close", "收盘"],
    ["ma5_ma10_signal", "MA5/MA10"],
    ["ma5_ma20_status", "MA5/MA20"],
    ["volume_check", "量能检查"],
    ["decision_reason", "判断理由"],
  ];
  const tlRecentColumns = [
    ["date", "日期"],
    ["state", "状态"],
    ["daily_macd_reason", "日线MACD"],
    ["daily_kdj_threshold_check", "日线KDJ"],
    ["weekly_macd_reason", "周线MACD"],
  ];
  const cbColumns = [
    ["rank", "排名"],
    ["bond_name", "转债"],
    ["bond_code", "代码"],
    ["price", "价格"],
    ["bond_rating", "评级"],
    ["sw_l1", "行业"],
    ["redemption_status", "强赎状态"],
    ["risk_level", "风险"],
    ["remaining_size", "存续规模"],
    ["conversion_premium_rate", "转股溢价率"],
    ["ytm", "到期收益率"],
    ["deducted_profit_growth", "三年扣非增速"],
    ["profit_growth_acceleration", "25年加速"],
    ["score", "评分"],
    ["score_grade", "等级"],
    ["qualification", "资格"],
    ["not_top_reason", "未入Top原因"],
    ["risk_flags", "风险提示"],
    ["rank_reason", "评分依据"],
  ];
  const cb = data.convertible_bond || {};
  const cbSummary = cb.summary || {};
  const cbTopRows = cb.top10 || data.cbTop10 || [];
  const cbRankedRows = cb.candidates || cb.ranked_candidates || data.cbRanked || [];
  renderModuleKpis(summary);
  renderTable("buy-table", data.etfBuyCandidates || [], etfBuyColumns, "buy");
  renderTable("sell-table", data.etfSellAlerts || [], etfSellColumns, "sell");
  renderTable("etf-buy-table", data.etfBuyCandidates || [], etfBuyColumns, "buy");
  renderTable("etf-sell-table", data.etfSellAlerts || [], etfSellColumns, "sell");
  renderTable("etf-watch-table", data.etfWatchlist || [], etfWatchColumns, "watch");
  renderTable("etf-all-table", rankedEtfRows(data.etf?.all_signals || data.etfAllSignals || []), etfAllColumns);
  renderWatchlist(data.etfWatchlist || [], data.etfDetailHistory || []);
  renderTL(data.tlToday?.[0] || {});
  renderTLPanel(data.tlToday?.[0] || {});
  renderTable("tl-recent-table", data.tlRecent || [], tlRecentColumns);
  renderTable("tl-panel-recent-table", data.tlRecent || [], tlRecentColumns);
  renderCbSummary(cbSummary);
  renderTable("cb-table", cbTopRows, cbColumns, "watch");
  renderTable("cb-top-table", cbTopRows, cbColumns, "watch");
  renderTable("cb-ranked-table", cbRankedRows, cbColumns, "watch");
  renderTable(
    "cb-quality-table",
    (data.dataQuality || []).filter((row) => String(row.item || "").includes("可转债") || String(row.item || "").includes("强赎") || String(row.item || "").includes("YTM") || String(row.item || "").includes("评级")),
    [["item", "识别项"], ["status", "状态"], ["detail", "详情"], ["note", "处理说明"]],
  );
  renderAICommittee(data.aiCommitteeReviews || []);
  renderTable("quality-table", data.dataQuality || [], [
    ["item", "识别项"],
    ["status", "状态"],
    ["detail", "详情"],
    ["note", "处理说明"],
  ]);
  renderTable("source-table", data.sourceManifest || [], [
    ["source_type", "类型"],
    ["exists", "存在"],
    ["modified_at", "修改时间"],
    ["size_bytes", "大小"],
    ["sha256", "SHA256"],
    ["archive_path", "归档路径"],
  ]);
  renderTable("risk-table", data.riskSummary || [], [
    ["item", "风险项"],
    ["value", "值"],
    ["level", "级别"],
  ]);
  const auditRows = (data.agentAudit || []).map((row) => ({
    ...row,
    agent: businessStepName(row.agent),
  }));
  renderTable("agent-table", auditRows, [
    ["agent", "流程"],
    ["metric_role", "职责"],
    ["metric_skill", "能力"],
    ["status", "状态"],
    ["message", "说明"],
    ["metric_outputs", "输出合同"],
    ["duration_ms", "耗时ms"],
  ]);
}

function renderContext(summary) {
  const data = state.data;
  const items = [
    ["报告日期", data.reportDate || "--"],
    ["ETF建仓", pick(summary, "ETF建仓候选数量")],
    ["ETF关注", pick(summary, "ETF关注池数量")],
    ["ETF平仓", pick(summary, "ETF平仓提示数量")],
    ["TL状态", pick(summary, "TL今日状态")],
    ["转债Top10", pick(summary, "可转债Top10数量")],
    ["已识别风险", pickSummary(summary, "系统已识别风险项", "数据校验异常项")],
    ["日报解释", dailyReportMode(summary)],
    ["聊天模型", chatModelStatus()],
  ];
  document.getElementById("context-grid").innerHTML = items
    .map((item) => `<div class="context-item"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`)
    .join("");

  const sources = [
    "ETF信号矩阵",
    "TL MACD/KDJ择时",
    "可转债排序",
    "数据质检",
    "复核意见",
    "运行审计日志",
  ];
  document.getElementById("context-sources").innerHTML = sources.map((item) => `<li>${item}</li>`).join("");
}

function renderKpis(summary) {
  const items = [
    ["ETF 建仓候选", pick(summary, "ETF建仓候选数量")],
    ["ETF 关注池", pick(summary, "ETF关注池数量")],
    ["ETF 平仓提示", pick(summary, "ETF平仓提示数量")],
    ["可转债 Top10", pick(summary, "可转债Top10数量")],
    ["TL 状态", pick(summary, "TL今日状态")],
    ["日报解释", dailyReportMode(summary)],
    ["聊天模型", chatModelStatus()],
    ["已识别风险项", pickSummary(summary, "系统已识别风险项", "数据校验异常项")],
  ];
  document.getElementById("kpi-grid").innerHTML = items
    .map((item) => `<div class="kpi"><div class="label">${escapeHtml(item[0])}</div><div class="value">${escapeHtml(item[1])}</div></div>`)
    .join("");
}

function renderModuleKpis(summary) {
  const etfItems = [
    ["持仓中", (state.data?.etf?.all_signals || []).filter((row) => row.position_status === "持仓中").length],
    ["建仓候选", pick(summary, "ETF建仓候选数量")],
    ["关注池", pick(summary, "ETF关注池数量")],
    ["平仓提示", pick(summary, "ETF平仓提示数量")],
  ];
  const cbItems = [
    ["合格候选", state.data?.convertible_bond?.summary?.qualified_count ?? pick(summary, "可转债Top10数量")],
    ["弱观察", state.data?.convertible_bond?.summary?.weak_watch_count ?? "--"],
    ["风险观察", state.data?.convertible_bond?.summary?.risk_watch_count ?? "--"],
    ["候选池", state.data?.convertible_bond?.candidates?.length ?? state.data?.cbRanked?.length ?? "--"],
    ["质检提醒", (state.data?.dataQuality || []).filter((row) => String(row.item || "").includes("可转债") && row.status !== "OK").length],
  ];
  const renderItems = (id, items) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.innerHTML = items
      .map((item) => `<div class="kpi"><div class="label">${escapeHtml(item[0])}</div><div class="value">${escapeHtml(item[1])}</div></div>`)
      .join("");
  };
  renderItems("etf-module-kpis", etfItems);
  renderItems("cb-module-kpis", cbItems);
}

function renderCbSummary(summary) {
  const title = document.getElementById("cb-top-title");
  const message = document.getElementById("cb-quality-message");
  if (title) title.textContent = summary.top_display_title || "可转债 Top10 候选";
  if (message) message.textContent = summary.quality_message || "";
}

function renderAICommittee(rows) {
  const container = document.getElementById("ai-committee-list");
  if (!rows.length) {
    container.innerHTML = `<div class="empty-state">暂无复核结果</div>`;
    return;
  }
  container.innerHTML = rows
    .map((row) => {
      const statusClass = row.llm_used ? "ok" : "warn";
      const statusText = row.llm_used ? "已复核" : "规则模板";
      const reviewBasis = row.reason || row.model || "--";
      return `
        <article class="ai-note">
          <div class="ai-note-head">
            <div>
              <div class="ai-role">${escapeHtml(row.title || row.role)}</div>
              <div class="ai-model">${escapeHtml(reviewBasis)}</div>
            </div>
            <span class="tag ${statusClass}">${statusText}</span>
          </div>
          <p>${escapeHtml(row.review || "")}</p>
        </article>
      `;
    })
    .join("");
}

function pickSummary(rows, item, fallbackItem) {
  const value = pick(rows, item);
  if (value !== "--") return value;
  return fallbackItem ? pick(rows, fallbackItem) : "--";
}

function dailyReportMode(summary) {
  const value = pickSummary(summary, "日报解释状态", "LLM调用状态");
  if (value === "未调用：daily_report_llm_disabled_for_refresh_stability") {
    return "稳定模式";
  }
  if (String(value).includes("daily_report_llm_disabled_for_refresh_stability")) {
    return "稳定模式";
  }
  return value;
}

function chatModelStatus() {
  const latest = state.dbStatus?.chatModel?.latest;
  const fallbackModel = state.data?.llmUsage?.llm_model || pick(state.data?.summary || [], "日报解释模型") || pick(state.data?.summary || [], "LLM模型");
  if (latest?.llm_used) return `已连接 ${latest.llm_model || fallbackModel || ""}`.trim();
  return fallbackModel && fallbackModel !== "--" ? `已配置 ${fallbackModel}` : "待验证";
}

function renderWatchlist(rows, history) {
  if (!state.selectedWatchCode && rows.length) {
    state.selectedWatchCode = rows[0].code;
  }
  renderTable("watch-table", rows, [
    ["name", "标的"],
    ["code", "代码"],
    ["watch_type", "关注类型"],
    ["ma5_ma10_signal", "MA5/MA10"],
    ["vol_ratio60", "量能倍数"],
    ["score", "评分"],
    ["suggested_action", "建议动作"],
  ], "watch");

  document.querySelectorAll("#watch-table tbody tr").forEach((tr, index) => {
    const row = rows[index];
    if (!row) return;
    tr.classList.toggle("selected", row.code === state.selectedWatchCode);
    tr.addEventListener("click", () => {
      state.selectedWatchCode = row.code;
      renderWatchlist(rows, history);
    });
  });

  const selected = rows.find((row) => row.code === state.selectedWatchCode) || rows[0];
  if (!selected) {
    document.getElementById("watch-detail-title").textContent = "暂无关注标的";
    document.getElementById("watch-selected-name").textContent = "ETF 详情";
    document.getElementById("watch-selected-metrics").innerHTML = "";
    renderTable("watch-history-table", [], [["date", "日期"]]);
    return;
  }

  document.getElementById("watch-detail-title").textContent = `${selected.name} ${selected.code}`;
  document.getElementById("watch-selected-name").textContent = selected.watch_type || "ETF 详情";
  const metrics = [
    ["还差条件", selected.missing_condition],
    ["建议动作", selected.suggested_action],
    ["MA5/MA20", selected.ma5_ma20_status],
    ["MACD柱", selected.macd_hist],
    ["评分", selected.score],
  ];
  document.getElementById("watch-selected-metrics").innerHTML = metrics
    .map((item) => `<div><dt>${escapeHtml(item[0])}</dt><dd>${escapeHtml(formatNumber(item[1]))}</dd></div>`)
    .join("");

  const selectedHistory = history.filter((row) => row.code === selected.code);
  renderTable("watch-history-table", selectedHistory, [
    ["date", "日期"],
    ["close", "收盘"],
    ["ma5", "MA5"],
    ["ma10", "MA10"],
    ["ma20", "MA20"],
    ["vol_ratio60", "量能倍数"],
    ["macd_hist", "MACD柱"],
    ["kdj_j", "KDJ J"],
  ]);
}

function renderTL(row) {
  document.getElementById("tl-state").textContent = row.state || "--";
  const metrics = [
    ["收盘价", row["收盘价"]],
    ["MACD柱", row.macd_hist],
    ["KDJ J", row.kdj_j],
    ["周线MACD柱", row.week_macd_hist],
    ["周线MACD判定", row.weekly_macd_reason],
    ["周线近2周J最低值", row.weekly_kdj_low_window],
    ["周线KDJ条件", row.weekly_kdj_threshold_check],
    ["日线MACD判定", row.daily_macd_reason],
    ["日线近3日J最低值", row.daily_kdj_low_window],
    ["日线KDJ条件", row.daily_kdj_threshold_check],
    ["日线关注", row.daily_attention ? "是" : "否"],
    ["日线KDJ反弹", row.daily_kdj_rebound ? "是" : "否"],
  ];
  document.getElementById("tl-metrics").innerHTML = metrics
    .map((item) => `<div><dt>${escapeHtml(item[0])}</dt><dd>${escapeHtml(formatNumber(item[1]))}</dd></div>`)
    .join("");
}

function renderTLPanel(row) {
  const stateNode = document.getElementById("tl-panel-state");
  const metricsNode = document.getElementById("tl-panel-metrics");
  if (!stateNode || !metricsNode) return;
  stateNode.textContent = row.state || "--";
  const metrics = [
    ["收盘价", row["收盘价"]],
    ["日线MACD", row.daily_macd_reason],
    ["日线KDJ", row.daily_kdj_threshold_check],
    ["周线MACD", row.weekly_macd_reason],
    ["周线KDJ", row.weekly_kdj_threshold_check],
    ["说明", "当前TL第一版只做状态诊断，不模拟平仓收益"],
  ];
  metricsNode.innerHTML = metrics
    .map((item) => `<div><dt>${escapeHtml(item[0])}</dt><dd>${escapeHtml(formatNumber(item[1]))}</dd></div>`)
    .join("");
}

function renderTable(id, rows, columns, mode) {
  const table = document.getElementById(id);
  if (!table) return;
  if (!rows.length) {
    table.innerHTML = `<thead><tr><th>暂无数据</th></tr></thead>`;
    return;
  }
  const thead = `<thead><tr>${columns.map((col) => `<th>${escapeHtml(col[1])}</th>`).join("")}</tr></thead>`;
  const tbody = rows
    .map((row) => {
      const cells = columns
        .map(([key]) => {
          const value = row[key];
          if (key === "status" || key === "level" || key === "exists" || key === "result") {
            const tagClass =
              value === "OK" || value === "INFO" || value === "success" || value === true || value === "对" ? "ok" : "warn";
            return `<td><span class="tag ${tagClass}">${escapeHtml(value)}</span></td>`;
          }
          if (key === "signal_reason" || key === "watch_type") {
            const tagClass = mode === "sell" ? "sell" : mode === "watch" ? "watch" : "buy";
            return `<td><span class="tag ${tagClass}">${escapeHtml(value)}</span></td>`;
          }
          return `<td>${escapeHtml(formatValue(key, value))}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  table.innerHTML = `${thead}<tbody>${tbody}</tbody>`;
}

function rankedEtfRows(rows) {
  return [...rows]
    .sort((left, right) => Number(right.score ?? -Infinity) - Number(left.score ?? -Infinity))
    .map((row, index) => ({
      ...row,
      rank: index + 1,
      decision_reason: row.signal_reason || row.reason || row.missing_condition || row.risk_notes || "--",
    }));
}

async function submitChat(question) {
  if (!question || state.isChatting) return;
  state.isChatting = true;
  let timeoutId = null;
  appendMessage("user", question, "You");
  const thinking = appendMessage("assistant", "正在读取最新投研上下文并生成回答。", "AI");
  const liveStream = createThinkingStream(thinking, question);
  liveStream.start();
  renderAgentRuntime({
    steps: [
      { name: "ChatRouterAgent", status: "running", detail: "正在识别问题意图。" },
      { name: "ResearchToolbox", status: "queued", detail: "等待工具调用。" },
    ],
    evidence: [],
    traceId: "--",
  });

  try {
    const localResult = localDeterministicChat(question);
    if (localResult) {
      liveStream.finish(localResult);
      await streamAnswer(thinking, localResult.answer);
      thinking.querySelector(".message-body span").textContent = `Trace ${localResult.traceId} · ${localResult.intent.name} · ${localResult.llmModel}`;
      attachAnalysisDetails(thinking, localResult, question);
      renderAgentRuntime(localResult);
      return;
    }

    const controller = new AbortController();
    timeoutId = window.setTimeout(() => controller.abort(), 20000);
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, sessionId: "local-dashboard", userId: "local-user" }),
      signal: controller.signal,
    });
    window.clearTimeout(timeoutId);
    timeoutId = null;
    const result = await response.json();
    if (!response.ok || result.status !== "success") {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
    liveStream.finish(result);
    await streamAnswer(thinking, result.answer);
    thinking.querySelector(".message-body span").textContent =
      `Trace ${result.traceId} · ${result.intent?.name || "agent"} · ${result.llmModel || (result.llmUsed ? "llm" : "deterministic")}`;
    attachAnalysisDetails(thinking, result, question);
    renderAgentRuntime(result);
  } catch (error) {
    const message = error.name === "AbortError" ? "请求超过 20 秒，已使用本地确定性摘要回答" : error.message;
    liveStream.error(message);
    await streamAnswer(thinking, localAnswer(question));
    thinking.querySelector(".message-body span").textContent = `来源：本地 dashboard 摘要 · ${message}`;
    const fallbackResult = {
      steps: [{ name: "Fallback", status: "fallback", detail: message }],
      evidence: [],
      traceId: "--",
      llmUsed: false,
      llmReason: message,
      intent: { name: "local_fallback", confidence: 1 },
      guardrail: { passed: true, issues: [] },
    };
    attachAnalysisDetails(thinking, fallbackResult, question);
    renderAgentRuntime(fallbackResult);
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
    state.isChatting = false;
  }
}

async function runDeepReview() {
  if (state.isDeepReviewing) return;
  state.isDeepReviewing = true;
  const button = document.getElementById("deep-review");
  const status = document.getElementById("deep-review-status");
  const originalText = button?.textContent || "AI 深度复核";
  if (button) {
    button.disabled = true;
    button.textContent = "复核中";
  }
  if (status) status.textContent = "正在启动四角色深度复核。该过程只解释和审稿，不会改写任何策略信号。";

  try {
    const response = await fetch("/api/deep-review", { method: "POST" });
    const result = await response.json();
    if (!response.ok || result.status !== "success") {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
    state.data.aiCommitteeReviews = result.reviews || [];
    renderAICommittee(state.data.aiCommitteeReviews);
    if (status) status.textContent = "AI 深度复核已完成。结果只作为审稿意见，不改变信号和排名。";
  } catch (error) {
    if (status) status.textContent = `AI 深度复核未完成：${error.message}。日报仍使用稳定模式。`;
  } finally {
    state.isDeepReviewing = false;
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

function renderAgentRuntime(result) {
  const runtime = document.getElementById("agent-runtime");
  const evidence = document.getElementById("evidence-list");
  if (!runtime || !evidence) return;

  const steps = result.steps || [];
  runtime.innerHTML = steps.length
    ? steps
        .map(
          (step) => `
            <div>
              <span>${escapeHtml(step.status)}</span>
              <strong>${escapeHtml(step.name)}</strong>
              <small>${escapeHtml(step.detail || "")}</small>
            </div>
          `,
        )
        .join("")
    : `<div><span>Idle</span><strong>等待问题</strong></div>`;

  const items = result.evidence || [];
  evidence.innerHTML = items.length
    ? items
        .map(
          (item) => `
            <div>
              <strong>${escapeHtml(item.title || item.tool)}</strong>
              <span>${escapeHtml(item.summary || "")}</span>
              <small>${escapeHtml(item.source || "")}</small>
            </div>
          `,
        )
        .join("")
    : `<div>提问后显示本次调用的数据工具和来源。</div>`;
}

function createThinkingStream(article, question) {
  const body = article?.querySelector(".message-body");
  const log = document.getElementById("chat-log");
  const baseSteps = [
    ["接收问题", "已接收用户问题，准备进入受控投研链路。"],
    ["识别意图", "判断是参数、ETF、TL、可转债、数据质量还是日报问题。"],
    ["读取证据", "读取本地 dashboard、SQLite、策略参数和规则说明。"],
    ["规则核对", "按客户规则核对字段，不新增交易信号。"],
    ["生成回答", "组织成客户可读结论和证据说明。"],
    ["输出校验", "检查是否误写买入、建仓、平仓或收益承诺。"],
  ];
  if (!body) {
    return { start() {}, finish() {}, error() {} };
  }

  body.querySelector(".thinking-stream")?.remove();
  const stream = document.createElement("div");
  stream.className = "thinking-stream is-live";
  stream.innerHTML = `
    <div class="thinking-head">
      <span class="thinking-dot" aria-hidden="true"></span>
      <span class="thinking-current">接收问题</span>
      <small>可审计过程</small>
    </div>
    <details class="thinking-details">
      <summary>查看分析步骤</summary>
      <ol>
      ${baseSteps
        .map(
          (step, index) => `
            <li class="${index === 0 ? "active" : ""}">
              <strong>${escapeHtml(step[0])}</strong>
              <span>${escapeHtml(step[1])}</span>
            </li>
          `,
        )
        .join("")}
      </ol>
    </details>
  `;
  body.appendChild(stream);

  let index = 0;
  let timer = null;
  const setStep = (nextIndex) => {
    const items = [...stream.querySelectorAll("li")];
    items.forEach((item, itemIndex) => {
      item.classList.toggle("done", itemIndex < nextIndex);
      item.classList.toggle("active", itemIndex === nextIndex);
    });
    const current = stream.querySelector(".thinking-current");
    if (current) current.textContent = baseSteps[nextIndex]?.[0] || "分析中";
    log.scrollTop = log.scrollHeight;
  };

  return {
    start() {
      timer = window.setInterval(() => {
        index = Math.min(index + 1, baseSteps.length - 1);
        setStep(index);
      }, isComplexQuestion(question) ? 850 : 520);
    },
    finish(result) {
      if (timer) window.clearInterval(timer);
      const steps = (result.steps || []).slice(0, 8);
      stream.classList.remove("is-live");
      stream.classList.add("is-complete");
      stream.innerHTML = `
        <div class="thinking-head">
          <span class="thinking-check" aria-hidden="true"></span>
          <span class="thinking-current">分析完成</span>
          <small>${escapeHtml(result.intent?.name || "agent")} · ${escapeHtml(result.llmModel || "deterministic")}</small>
        </div>
        <details class="thinking-details">
          <summary>查看 ${steps.length || baseSteps.length} 个步骤</summary>
          <ol>
          ${
            steps.length
              ? steps
                  .map(
                    (step) => `
                      <li class="done">
                        <strong>${escapeHtml(step.name || "--")}</strong>
                        <span>${escapeHtml(step.status || "--")} · ${escapeHtml(step.detail || "")}</span>
                      </li>
                    `,
                  )
                  .join("")
              : baseSteps
                  .map(
                    (step) => `
                      <li class="done">
                        <strong>${escapeHtml(step[0])}</strong>
                        <span>${escapeHtml(step[1])}</span>
                      </li>
                    `,
                  )
                  .join("")
          }
          </ol>
        </details>
      `;
      log.scrollTop = log.scrollHeight;
    },
    error(message) {
      if (timer) window.clearInterval(timer);
      stream.classList.remove("is-live");
      stream.classList.add("is-error");
      const current = stream.querySelector(".thinking-current");
      if (current) current.textContent = "已切换本地兜底";
      const last = stream.querySelector("li.active") || stream.querySelector("li:last-child");
      if (last) {
        last.classList.add("done");
        last.querySelector("span").textContent = `进入本地兜底：${message}`;
      }
      log.scrollTop = log.scrollHeight;
    },
  };
}

async function streamAnswer(article, answer) {
  const target = article?.querySelector(".message-body > p");
  const log = document.getElementById("chat-log");
  if (!target) return;
  const text = String(answer || "");
  target.textContent = "";
  if (!text) return;
  const chunkSize = text.length > 900 ? 18 : text.length > 360 ? 10 : 5;
  const delay = text.length > 900 ? 8 : 14;
  for (let index = 0; index < text.length; index += chunkSize) {
    target.textContent += text.slice(index, index + chunkSize);
    log.scrollTop = log.scrollHeight;
    await new Promise((resolve) => window.setTimeout(resolve, delay));
  }
}

function initialAnalysisResult() {
  return {
    status: "running",
    intent: { name: "classifying", confidence: 1 },
    steps: [
      { name: "ChatRouterAgent", status: "running", detail: "正在识别问题类型和可用数据权限。" },
      { name: "ResearchToolbox", status: "queued", detail: "准备读取日报、数据库、策略规则和相关信号。" },
      { name: "RuleCheck", status: "queued", detail: "将按客户规则核对 ETF、TL、可转债字段，不新增规则外判断。" },
      { name: "OutputGuardrail", status: "queued", detail: "等待最终回答后检查是否误写交易信号或收益承诺。" },
    ],
    evidence: [
      { title: "本地投研上下文", summary: "等待后端返回精确证据包。", source: "dashboard + sqlite + strategy params" },
    ],
    traceId: "pending",
    llmUsed: false,
    llmModel: "pending",
    llmReason: "analysis_process_started",
    guardrail: { passed: true, issues: [] },
  };
}

function isComplexQuestion(question) {
  const text = String(question || "").toLowerCase();
  const tokens = ["为什么", "怎么", "如何", "是否", "能不能", "分析", "解释", "原因", "风险", "稳定", "对比", "同时", "并且", "以及"];
  return text.trim().length >= 28 || tokens.some((token) => text.includes(token));
}

function attachAnalysisDetails(article, result, question = "") {
  const body = article?.querySelector(".message-body");
  if (!body) return;
  body.querySelector(".analysis-disclosure")?.remove();

  const steps = result.steps || [];
  const evidence = result.evidence || [];
  const intent = result.intent || {};
  const guardrail = result.guardrail || {};
  const complex = isComplexQuestion(question);
  const confidence = Number.isFinite(Number(intent.confidence)) ? `${Math.round(Number(intent.confidence) * 100)}%` : "--";
  const modelStatus = result.llmUsed
    ? `${result.llmModel || "--"} 已调用`
    : `稳定/降级模式：${result.llmReason || "未调用模型"}`;
  const guardrailText = guardrail.passed === false
    ? `已修正：${(guardrail.issues || []).join("；") || "触发输出限制"}`
    : "通过，答案未改变信号或排名";

  const details = document.createElement("details");
  details.className = `analysis-disclosure${complex ? " is-expanded" : ""}`;
  if (complex) details.open = true;
  details.innerHTML = `
    <summary>
      <span>${complex ? "分析过程" : "分析依据"}</span>
      <small>${complex ? "已展开 · 分类 · 证据 · 校验" : "分类 · 证据 · 校验"}</small>
    </summary>
    ${
      complex
        ? `<p class="analysis-lede">这是可审计分析过程：展示系统如何分类问题、读取证据、套用客户规则和做输出校验，不展示模型隐藏思考。</p>`
        : ""
    }
    <div class="analysis-grid">
      <div><strong>问题分类</strong><span>${escapeHtml(intent.name || "--")} · ${escapeHtml(confidence)}</span></div>
      <div><strong>模型状态</strong><span>${escapeHtml(modelStatus)}</span></div>
      <div><strong>输出校验</strong><span>${escapeHtml(guardrailText)}</span></div>
      <div><strong>Trace</strong><span>${escapeHtml(result.traceId || "--")}</span></div>
    </div>
    <div class="analysis-section">
      <strong>执行链路</strong>
      ${
        steps.length
          ? `<ol>${steps
              .map((step) => `<li><span>${escapeHtml(step.name || "--")}</span><small>${escapeHtml(step.status || "--")} · ${escapeHtml(step.detail || "")}</small></li>`)
              .join("")}</ol>`
          : `<p>本次未返回执行步骤。</p>`
      }
    </div>
    <div class="analysis-section">
      <strong>证据来源</strong>
      ${
        evidence.length
          ? `<ol>${evidence
              .map((item) => `<li><span>${escapeHtml(item.title || item.tool || "--")}</span><small>${escapeHtml(item.summary || "")}${item.source ? ` · ${escapeHtml(item.source)}` : ""}</small></li>`)
              .join("")}</ol>`
          : `<p>本次使用本地摘要或降级回答，没有额外工具证据。</p>`
      }
    </div>
    <p class="analysis-note">这里展示的是可审计分析依据，不展示模型内部隐藏思考。交易信号、排名和风险标记仍以确定性规则结果为准。</p>
  `;
  body.appendChild(details);
}

function appendMessage(role, text, source) {
  const log = document.getElementById("chat-log");
  const panel = document.getElementById("transcript-panel");
  if (panel?.classList.contains("is-empty")) {
    log.innerHTML = "";
    panel.classList.remove("is-empty");
  }
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="message-avatar">${role === "user" ? "你" : "AI"}</div>
    <div class="message-body">
      <p>${escapeHtml(text)}</p>
      <span>${escapeHtml(source || "")}</span>
    </div>
  `;
  log.appendChild(article);
  log.scrollTop = log.scrollHeight;
  return article;
}

function localDeterministicChat(question) {
  const text = question.toLowerCase();
  const summary = state.data?.summary || [];
  const isEtf = text.includes("etf");
  const asksCount = ["一共", "多少", "几个", "数量", "有多少"].some((token) => question.includes(token));

  if (isEtf && asksCount) {
    const etfAssets = state.assets.filter((asset) => asset.asset_type === "ETF");
    if (etfAssets.length) {
      const buyCount = pick(summary, "ETF建仓候选数量");
      const watchCount = pick(summary, "ETF关注池数量");
      const sellCount = pick(summary, "ETF平仓提示数量");
      return {
        status: "success",
        answer: `当前数据库里的 ETF 标的一共 ${etfAssets.length} 只。\n\n今天策略结果是：ETF 建仓候选 ${buyCount} 只，关注池 ${watchCount} 只，平仓提示 ${sellCount} 只。\n\n这里的“ETF 一共多少”指客户模板纳入并已入库的 ETF 数量；建仓候选、关注池、平仓提示是今日规则筛选后的结果。`,
        intent: { name: "database_inventory", confidence: 1 },
        steps: [
          { name: "LocalDashboard", status: "success", detail: "从当前页面已加载的资产清单和日报摘要直接读取。" },
          { name: "DeterministicAnswerAgent", status: "success", detail: "数量类问题不调用模型。" },
        ],
        evidence: [
          { title: "Asset inventory", summary: `当前页面资产清单包含 ETF ${etfAssets.length} 只。`, source: "frontend.state.assets" },
          { title: "Daily summary", summary: "建仓、关注、平仓数量来自最新日报摘要。", source: "outputs/latest/dashboard.json" },
        ],
        traceId: "local",
        llmUsed: false,
        llmModel: "local_deterministic",
        llmReason: "simple_inventory_answer",
        guardrail: { passed: true, issues: [] },
      };
    }
  }

  return null;
}

function localAnswer(question) {
  const data = state.data || {};
  const summary = data.summary || [];
  const tl = data.tlToday?.[0] || {};
  const buyCount = pick(summary, "ETF建仓候选数量");
  const watchCount = pick(summary, "ETF关注池数量");
  const sellCount = pick(summary, "ETF平仓提示数量");
  const riskItems = pickSummary(summary, "系统已识别风险项", "数据校验异常项");
  const etfParams = state.strategyParams?.etf || {};
  const cbParams = state.strategyParams?.convertible_bond || {};
  const cbWeights = cbParams.score_weights || {};
  const etfWeights = etfParams.score_weights || {};
  const asksParam = ["参数", "配置", "权重", "量能", "基本面", "最低价格", "最低价", "到期收益", "ytm", "溢价", "强赎", "评级", "信用"].some((token) =>
    question.toLowerCase().includes(token),
  );
  if (asksParam) {
    if (question.includes("基本面")) {
      return `可转债基本面权重当前是 ${cbWeights.fundamental ?? "--"}。\n\n对应扣非净利润增长、增长加速、利润为负等基本面因子。`;
    }
    if (question.includes("最低价格") || question.includes("最低价")) {
      return `可转债最低价格配置当前是 ${cbParams.min_price ?? "--"}。\n\n低于该价格默认不进入正常排序，因为客户认为 100 元以下通常可能隐含信用风险。`;
    }
    if (question.includes("趋势权重")) {
      return `ETF 趋势权重当前是 ${etfWeights.trend ?? "--"}。`;
    }
    if (question.includes("MA10") || question.includes("ma10")) {
      return `ETF 跌破 MA10 平仓量能当前是 ${etfParams.sell_ma10_volume_ratio_min ?? "--"}。`;
    }
    if (question.includes("MA5") || question.includes("ma5")) {
      return `ETF 跌破 MA5 平仓量能当前是 ${etfParams.sell_ma5_volume_ratio_min ?? "--"}。`;
    }
    if (question.includes("量能")) {
      return `ETF 建仓量能倍数当前是 ${etfParams.buy_volume_ratio_min ?? "--"}；跌破 MA10 平仓量能 ${etfParams.sell_ma10_volume_ratio_min ?? "--"}；跌破 MA5 平仓量能 ${etfParams.sell_ma5_volume_ratio_min ?? "--"}。`;
    }
    if (question.includes("到期收益") || question.toLowerCase().includes("ytm")) {
      return `可转债 YTM 权重当前是 ${cbWeights.ytm ?? "--"}；高 YTM 硬排除阈值 ${cbParams.high_ytm_hard_exclude ?? "--"}%；严重负 YTM 硬排除阈值 ${cbParams.severe_negative_ytm_hard_exclude ?? "--"}%。`;
    }
  }
  if (question.includes("TL") || question.includes("tl")) {
    return `TL 当前状态为 ${tl.state || "--"}。日线 MACD 判定：${tl.daily_macd_reason || "--"}。日线 KDJ 条件：${tl.daily_kdj_threshold_check || "--"}。周线 MACD 判定：${tl.weekly_macd_reason || "--"}。`;
  }
  if (question.includes("ETF") || question.includes("etf")) {
    if (isComplexQuestion(question)) {
      const buyVolume = etfParams.buy_volume_ratio_min ?? "--";
      return `结论：当前 ETF 建仓候选数量为 ${buyCount}，关注池数量为 ${watchCount}，平仓提示数量为 ${sellCount}。\n\n分析过程：1. 系统先识别为 ETF 规则解释问题；2. 读取本地日报摘要、策略参数和 ETF 信号结果；3. 按客户规则核对建仓A和建仓B；4. 输出时校验不能把关注池说成买入建议。\n\n关键规则：建仓A要求未持仓、MA5今日上穿MA10、MACD柱改善、量能倍数达到 ${buyVolume}；建仓B要求未持仓、DIF上穿DEA、MA5高于MA10、收盘价高于MA20、量能倍数达到 ${buyVolume}。\n\n限制与下一步：如果刚修改过量能阈值，需要点击一键刷新后，策略信号和日报才会按新参数重新计算。`;
    }
    return `当前 ETF 建仓候选数量为 ${buyCount}，关注池数量为 ${watchCount}，平仓提示数量为 ${sellCount}。具体标的和触发字段可在“策略信号”和“关注池”页面查看。`;
  }
  if (question.includes("数据") || question.includes("质量")) {
    return `当前系统已识别风险项为 ${riskItems}。这些不是系统错误，而是按客户规则识别出的强赎、信用、低价、高YTM、低评级或覆盖范围提示。请到“数据状态”查看具体处理说明。`;
  }
  return data.researchSummary?.[0]?.content || "当前没有可用摘要，请先刷新数据。";
}

function reportUrl(path) {
  const filename = path.split("/").pop();
  return `/outputs/${encodeURIComponent(filename)}`;
}

function setActiveView() {
  const id = (window.location.hash || "#chat").slice(1);
  const activeId = pageTitles[id] ? id : "chat";
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === activeId);
  });
  document.querySelectorAll(".nav a").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("href") === `#${activeId}`);
  });
  document.body.dataset.view = activeId;
  document.getElementById("page-title").textContent = pageTitles[activeId];
  if (window.location.hash !== `#${activeId}`) {
    history.replaceState(null, "", `#${activeId}`);
  }
  window.scrollTo({ top: 0, behavior: "auto" });
}

document.getElementById("refresh-data").addEventListener("click", refreshData);
document.getElementById("deep-review").addEventListener("click", runDeepReview);
document.getElementById("export-pdf").addEventListener("click", exportPdf);
document.getElementById("save-params")?.addEventListener("click", saveStrategyParams);
document.getElementById("asset-search")?.addEventListener("input", renderAssets);
document.getElementById("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  input.value = "";
  submitChat(question);
});
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    submitChat(button.dataset.question);
  });
});
window.addEventListener("hashchange", setActiveView);

setActiveView();
loadDashboard();
