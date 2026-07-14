const CHAT_MEMORY_KEY = "ai_research_short_term_memory_v1";

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
  serverStrategyState: null,
  modelConfig: null,
  openaiModels: [],
  openaiModelSource: "",
  openaiModelMessage: "",
  openaiConnection: null,
  dbStatus: null,
  isChatting: false,
  aiChatEnabled: false,
  chatMemory: loadShortTermMemory(),
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
  data: "系统状态",
  settings: "策略设置",
  "param-guide": "规则说明",
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
  "ai-research-committee-agent": "生成审计摘要",
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
  if ((key === "stock_daily_return" || key === "bond_daily_return") && typeof value === "number") return `${value.toFixed(2)}%`;
  if (key.includes("return") && typeof value === "number") return `${(value * 100).toFixed(2)}%`;
  if (key === "medium_status" || key === "short_entry_status") return ETFStrategyConfig.strategyStateLabel(key, value);
  if (key === "linkage_state") return ETFStrategyConfig.linkageStateLabel(value);
  if (key === "auxiliary_state") return ETFStrategyConfig.auxiliaryStateLabel(value);
  if (key === "stock_bond_relative_gap" || key === "conversion_premium_change") return signedMetric(value, "pct");
  return formatNumber(value);
};

function numericMetric(value) {
  if (value === null || value === undefined || value === "") return Number.NaN;
  return Number(value);
}

function signedMetric(value, suffix = "") {
  const number = numericMetric(value);
  if (!Number.isFinite(number)) return "--";
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(2)}${suffix}`;
}

function convertibleAuxiliaryEvidence(row) {
  const stock = numericMetric(row.stock_daily_return);
  const bond = numericMetric(row.bond_daily_return);
  const premium = numericMetric(row.conversion_premium_change);
  const relative = Number.isFinite(stock) && Number.isFinite(bond) ? stock - bond : numericMetric(row.stock_bond_relative_gap);
  const score = numericMetric(row.auxiliary_score ?? row.dynamic_score);
  const factors = [
    `正股 ${signedMetric(stock, "%")}`,
    `转债 ${signedMetric(bond, "%")}`,
    `相对 ${signedMetric(relative, "pct")}`,
    `溢价 ${signedMetric(premium, "pct")}`,
  ];
  if (Number.isFinite(score)) factors.push(`辅助分 ${score.toFixed(2)}`);
  return factors.join(" · ");
}

function convertibleRowsForDisplay(rows) {
  return (rows || []).map((row) => ({
    ...row,
    auxiliary_evidence: convertibleAuxiliaryEvidence(row),
  }));
}

const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

const pick = (rows, item) => rows.find((row) => row.item === item)?.value ?? "--";

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return JSON.parse(text || "{}");
  } catch {
    throw new Error("接口返回的不是 JSON，请确认已从本地服务打开页面并重启后端。");
  }
}

function loadShortTermMemory() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(CHAT_MEMORY_KEY) || "{}");
    return {
      lastAsset: parsed.lastAsset || null,
      lastIntent: parsed.lastIntent || null,
      turns: Array.isArray(parsed.turns) ? parsed.turns.slice(-8) : [],
    };
  } catch {
    return { lastAsset: null, lastIntent: null, turns: [] };
  }
}

function saveShortTermMemory() {
  sessionStorage.setItem(CHAT_MEMORY_KEY, JSON.stringify(state.chatMemory || { turns: [] }));
  renderChatMemoryStatus();
}

function clearShortTermMemory() {
  state.chatMemory = { lastAsset: null, lastIntent: null, turns: [] };
  sessionStorage.removeItem(CHAT_MEMORY_KEY);
  renderChatMemoryStatus();
  appendMessage("assistant", "已清除本轮短期记忆。后续问题不会再沿用刚才的标的或上下文。", "AI");
}

function renderChatMemoryStatus() {
  const target = document.getElementById("chat-memory-status");
  if (!target) return;
  const asset = state.chatMemory?.lastAsset;
  const turns = state.chatMemory?.turns?.length || 0;
  target.textContent = asset?.name
    ? `短期记忆：${asset.name}${asset.code ? ` ${asset.code}` : ""} · ${turns}轮`
    : `短期记忆：${turns ? `${turns}轮` : "空"}`;
}

function rememberChatTurn(question, result, answer) {
  const intent = result?.intent || {};
  const entities = intent.entities || {};
  const mentionedAsset = findMentionedAsset(question);
  const lastAsset = entities.code || entities.name
    ? {
        code: entities.code || mentionedAsset?.code || "",
        name: entities.name || mentionedAsset?.name || "",
        asset_type: entities.asset_type || mentionedAsset?.asset_type || "",
      }
    : mentionedAsset || state.chatMemory?.lastAsset || null;
  const turn = {
    question: String(question || "").slice(0, 220),
    answer: String(answer || "").slice(0, 260),
    intent: intent.name || "local",
    asset: lastAsset,
    at: new Date().toISOString(),
  };
  state.chatMemory = {
    lastAsset,
    lastIntent: intent.name || state.chatMemory?.lastIntent || null,
    turns: [...(state.chatMemory?.turns || []), turn].slice(-8),
  };
  saveShortTermMemory();
}

function findMentionedAsset(text) {
  const query = String(text || "").toLowerCase();
  if (!query || !Array.isArray(state.assets)) return null;
  return state.assets.find((asset) => {
    const code = String(asset.code || "").toLowerCase();
    const rawCode = code.replace(".sh", "").replace(".sz", "");
    const name = String(asset.name || "").toLowerCase();
    const shortName = name.replace("etf", "").replace("转债", "");
    return (code && query.includes(code)) || (rawCode && query.includes(rawCode)) || (name && query.includes(name)) || (shortName && query.includes(shortName));
  }) || null;
}

async function loadDashboard() {
  const status = document.getElementById("data-status");
  try {
    const response = await fetch(`/outputs/latest/dashboard.json?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    const systemStatus = ETFStrategyConfig.systemStatusLabel(state.data);
    status.textContent = systemStatus;
    status.classList.toggle("ok", systemStatus === "数据已更新");
    status.classList.toggle("warn", systemStatus !== "数据已更新");
    render();
    loadDbStatus();
    loadAssets();
    loadStrategyParams();
    loadModelConfig();
  } catch (error) {
    status.textContent = "数据不可用";
    status.classList.remove("ok");
    status.classList.add("warn");
    document.getElementById("research-summary").textContent =
      "无法读取 /outputs/latest/dashboard.json。请先运行后端工作流，或从项目根目录启动本地服务。";
    loadStrategyParams();
    loadModelConfig();
  }
}

async function loadModelConfig() {
  try {
    const response = await fetch(`/api/model-config?ts=${Date.now()}`, { cache: "no-store" });
    const result = await readJsonResponse(response);
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.modelConfig = result.config || {};
    renderModelConfig();
    renderAiChatButton();
    if (state.data) render();
    loadOpenAiModels();
  } catch (error) {
    const status = document.getElementById("model-config-status");
    if (status) status.textContent = `模型配置读取失败：${error.message}`;
  }
}

async function loadOpenAiModels() {
  const status = document.getElementById("model-list-status");
  if (status) status.textContent = "正在读取 OpenAI 模型列表。";
  try {
    const response = await fetch(`/api/openai-models?ts=${Date.now()}`, { cache: "no-store" });
    const result = await readJsonResponse(response);
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.openaiModels = result.models || [];
    state.openaiModelSource = result.source || "";
    state.openaiModelMessage = result.message || "";
    renderModelConfig();
  } catch (error) {
    state.openaiModelMessage = `模型列表读取失败：${error.message}`;
    if (status) status.textContent = state.openaiModelMessage;
  }
}

async function saveModelConfig() {
  if (!state.modelConfig) return;
  const status = document.getElementById("model-config-status");
  try {
    syncModelConfigFromForm();
    const response = await fetch("/api/model-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: state.modelConfig }),
    });
    const result = await readJsonResponse(response);
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.modelConfig = result.config;
    if (status) status.textContent = "AI 模型配置已保存。下一次 AI 智能问答生效。";
    renderModelConfig();
    if (state.data) render();
    loadOpenAiModels();
  } catch (error) {
    if (status) status.textContent = `保存失败：${error.message}`;
  }
}

async function verifyOpenAiConnection() {
  if (!state.modelConfig) return;
  const status = document.getElementById("model-config-status");
  const apiKey = (document.getElementById("openai-api-key")?.value || "").trim();
  if (status) status.textContent = "正在验证 OpenAI 连通性。";
  try {
    const response = await fetch("/api/model-config/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey }),
    });
    const result = await readJsonResponse(response);
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.openaiConnection = result.connected ? "ok" : "warn";
    state.openaiModelMessage = result.message || "";
    if (Array.isArray(result.models) && result.models.length) state.openaiModels = result.models;
    if (result.api_key_masked) {
      state.modelConfig.api_key_configured = true;
      state.modelConfig.api_key_masked = result.api_key_masked;
    }
    renderModelConfig();
    if (state.data) render();
  } catch (error) {
    state.openaiConnection = "warn";
    state.openaiModelMessage = `验证失败：${error.message}`;
    renderModelConfig();
    if (state.data) render();
  }
}

async function saveOpenAiKey() {
  if (!state.modelConfig) return;
  const input = document.getElementById("openai-api-key");
  const apiKey = (input?.value || "").trim();
  const status = document.getElementById("model-config-status");
  if (!apiKey) {
    if (status) status.textContent = "请先在 OpenAI Key 输入框中粘贴 Key。";
    input?.focus();
    return;
  }
  if (status) status.textContent = "正在验证并保存 Key。";
  try {
    const response = await fetch("/api/model-config/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey }),
    });
    const result = await readJsonResponse(response);
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    if (!result.connected) {
      state.openaiConnection = "warn";
      state.openaiModelMessage = result.message || "Key 验证失败，尚未保存。";
      if (status) status.textContent = state.openaiModelMessage;
      return;
    }
    state.openaiConnection = "ok";
    state.openaiModelMessage = result.message || "Key 已安全保存在本机。";
    state.modelConfig.api_key_configured = true;
    state.modelConfig.api_key_masked = result.api_key_masked || "已遮挡";
    if (Array.isArray(result.models) && result.models.length) state.openaiModels = result.models;
    if (input) input.value = "";
    renderModelConfig();
    if (status) status.textContent = state.openaiModelMessage;
    if (state.data) render();
  } catch (error) {
    state.openaiConnection = "warn";
    if (status) status.textContent = `保存失败：${error.message}`;
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
    renderSystemStatus({});
  }
}

function renderDbStatus(result) {
  const container = document.getElementById("db-status-grid");
  const latest = result.latestRun || {};
  const counts = result.tableCounts || {};
  const items = [
    ["本地存储", result.exists ? "已连接" : "未连接"],
    ["最近更新编号", latest.run_id || "--"],
    ["数据日期", latest.report_date || "--"],
    ["写入结果", latest.status === "success" ? "已写入" : latest.status || "--"],
    ["标的档案", counts.asset_master ?? 0],
    ["行情记录", counts.market_daily_indicators ?? 0],
    ["ETF记录", counts.etf_daily_bars ?? 0],
    ["TL记录", counts.tl_daily_signals ?? 0],
    ["可转债记录", counts.convertible_bond_snapshots ?? 0],
  ];
  container.innerHTML = items
    .map((item) => `<div class="context-item"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`)
    .join("");
  renderSystemStatus(result);
}

function renderSystemStatus(result = state.dbStatus || {}) {
  const container = document.getElementById("system-status-grid");
  const attention = document.getElementById("system-attention-list");
  if (!container || !attention || !state.data) return;
  const data = state.data;
  const sources = data.sourceManifest || [];
  const etfCount = Number(data.etf?.counts?.all_signals ?? data.etf?.all_signals?.length ?? 0);
  const tlRecentCount = Number(data.tl?.recent?.length ?? data.tlRecent?.length ?? 0);
  const tlHistoryDays = ETFStrategyConfig.qualityMetric(
    data.dataQuality || data.data_quality?.checks || [],
    "TL有效交易日",
    tlRecentCount,
  );
  const cbCounts = data.convertible_bond?.counts || {};
  const cbCount = Number(cbCounts.ranked_candidates || 0) + Number(cbCounts.excluded || 0);
  const statusLabel = ETFStrategyConfig.systemStatusLabel(data);
  const generatedAt = String(data.run_info?.generated_at || "--").replace("T", " ").slice(0, 19);
  const items = [
    ["更新结果", statusLabel],
    ["最近更新时间", generatedAt],
    ["ETF数据", `已读取 ${etfCount} 只`],
    ["TL数据", `历史 ${tlHistoryDays} 个交易日`],
    ["可转债数据", `已读取 ${cbCount} 只`],
    ["源文件", `${sources.filter((row) => row.exists).length}/${sources.length || 3} 已读取`],
  ];
  container.innerHTML = items
    .map((item) => `<div class="context-item"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`)
    .join("");

  const notices = ETFStrategyConfig.actionableSystemNotices(data.run_info?.warnings || []);
  attention.innerHTML = notices.length
    ? `<strong>需要处理</strong><ul>${notices.map((notice) => `<li>${escapeHtml(notice)}</li>`).join("")}</ul>`
    : `<strong>无需处理</strong><p>三类数据均已读取，可以正常查看本次结果。</p>`;
  attention.classList.toggle("has-warning", notices.length > 0);
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
    state.serverStrategyState = ETFStrategyConfig.normalizeStrategyResponse(result);
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
    syncEtfStrategyFromForm();
    syncCbStrategyFromForm();
    const response = await fetch("/api/strategy-params", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: state.strategyParams }),
    });
    const result = await response.json();
    if (!response.ok || result.status !== "success") throw new Error(result.message || `HTTP ${response.status}`);
    state.strategyParams = result.params;
    state.serverStrategyState = ETFStrategyConfig.normalizeStrategyResponse(result);
    if (status) status.textContent = "参数已保存。下一次刷新数据时生效。";
    renderStrategyParams();
  } catch (error) {
    if (state.serverStrategyState) {
      state.strategyParams = JSON.parse(JSON.stringify(state.serverStrategyState.params));
      renderStrategyParams();
    }
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
    cbRow.stock_bond_relative_gap = Number.isFinite(numericMetric(cbRow.stock_daily_return)) && Number.isFinite(numericMetric(cbRow.bond_daily_return))
      ? numericMetric(cbRow.stock_daily_return) - numericMetric(cbRow.bond_daily_return)
      : cbRow.stock_bond_relative_gap;
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
      ["基础分", cbRow.base_score ?? cbRow.score],
      ["基础等级", cbRow.base_grade ?? cbRow.score_grade],
      ["价格", cbRow.price],
      ["评级", cbRow.bond_rating || cbRow.rating],
      ["行业", cbRow.sw_l1],
      ["存续规模", cbRow.remaining_size],
      ["转股溢价率", cbRow.conversion_premium_rate],
      ["到期收益率", cbRow.ytm],
      ["强赎状态", cbRow.redemption_status],
      ["风险等级", cbRow.risk_level],
      ["风险提示", cbRow.quality_notes || cbRow.risk_flags],
      ["正股当日涨幅", cbRow.stock_daily_return],
      ["转债当日涨幅", cbRow.bond_daily_return],
      ["股债相对强弱", `正股-转债 ${signedMetric(cbRow.stock_bond_relative_gap, " 个百分点")}`],
      ["溢价率当日变化", cbRow.conversion_premium_change],
      ["动态辅助分", cbRow.auxiliary_score ?? cbRow.dynamic_score],
      ["动态判断", ETFStrategyConfig.auxiliaryStateLabel(cbRow.auxiliary_state ?? cbRow.dynamic_state)],
      ["辅助说明", cbRow.auxiliary_note || cbRow.dynamic_note || "暂无异常提示；不改变基础排名"],
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
      ["stock_daily_return", "正股当日涨幅"],
      ["bond_daily_return", "转债当日涨幅"],
      ["stock_bond_relative_gap", "股债相对强弱"],
      ["conversion_premium_change", "溢价率变化"],
      ["auxiliary_score", "动态辅助分"],
      ["auxiliary_state", "动态判断"],
      ["linkage_state", "短期联动"],
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
    ["excluded", [...(cb.excluded || []), ...(state.data?.cbExcluded || [])]],
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
  renderEtfStrategySelector();
  renderCbStrategySelector();
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
  renderParameterGuide();
}

function renderParameterGuide() {
  if (!state.strategyParams) return;
  const guide = ETFStrategyConfig.parameterGuideModel(state.strategyParams);
  const etfTarget = document.getElementById("etf-guide-content");
  const tlTarget = document.getElementById("tl-guide-content");
  const cbBaseTarget = document.getElementById("cb-base-guide-content");
  const cbAuxiliaryTarget = document.getElementById("cb-auxiliary-guide-content");
  const cbAuxiliaryStatus = document.getElementById("cb-auxiliary-guide-status");

  if (etfTarget) {
    etfTarget.innerHTML = guide.etfStrategies.map((strategy) => `
      <section class="guide-strategy-panel ${strategy.isActive ? "is-active" : ""}">
        <div class="guide-title-row">
          <strong>${escapeHtml(strategy.title)}</strong>
          <span class="status-pill ${strategy.isActive ? "ok" : ""}">${strategy.isActive ? "当前配置" : "可选插件"}</span>
        </div>
        <div class="param-guide-grid">${renderGuideItems(strategy.items)}</div>
      </section>
    `).join("");
  }
  if (tlTarget) tlTarget.innerHTML = renderGuideItems(guide.tlItems);
  if (cbBaseTarget) cbBaseTarget.innerHTML = renderGuideItems(guide.cbBaseItems);
  if (cbAuxiliaryTarget) cbAuxiliaryTarget.innerHTML = renderGuideItems(guide.cbAuxiliary.items);
  if (cbAuxiliaryStatus) {
    cbAuxiliaryStatus.textContent = guide.cbAuxiliary.enabled ? "已启用" : "未启用";
    cbAuxiliaryStatus.classList.toggle("ok", guide.cbAuxiliary.enabled);
  }
}

function renderGuideItems(items) {
  return (items || []).map((item) => {
    const [title, ...detailParts] = String(item).split("：");
    return `<div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detailParts.join("："))}</span></div>`;
  }).join("");
}

function renderEtfStrategySelector() {
  const strategyState = state.serverStrategyState;
  const select = document.getElementById("etf-strategy-select");
  const diagnostics = document.getElementById("etf-diagnostics-enabled");
  if (!strategyState || !select) return;
  select.innerHTML = strategyState.strategies
    .map((item) => `<option value="${escapeHtml(item.strategy_id)}" ${item.strategy_id === strategyState.confirmedStrategyId ? "selected" : ""}>${escapeHtml(item.display_name)} · v${escapeHtml(item.version)}</option>`)
    .join("");
  if (diagnostics) diagnostics.checked = (state.strategyParams?.etf?.diagnostic_strategies || []).length > 1;
  const generated = state.data?.run_info?.etf_strategy || state.data?.runInfo?.etf_strategy || null;
  const generatedTarget = document.getElementById("etf-generated-strategy");
  if (generatedTarget) generatedTarget.textContent = generated
    ? `当前页面结果：${generated.strategy_id} · v${generated.strategy_version}`
    : "当前页面尚无策略身份记录";
  const refreshState = ETFStrategyConfig.generatedResultState(strategyState, generated);
  const refreshTarget = document.getElementById("etf-strategy-refresh-state");
  if (refreshTarget) refreshTarget.textContent = refreshState.label;
  renderEtfProfileControls();
}

function renderEtfProfileControls() {
  const target = document.getElementById("etf-strategy-params");
  const strategyState = state.serverStrategyState;
  const strategyId = document.getElementById("etf-strategy-select")?.value || strategyState?.confirmedStrategyId;
  const metadata = strategyState?.strategies?.find((item) => item.strategy_id === strategyId);
  if (!target || !metadata || strategyId === "legacy_v1") {
    if (target) target.innerHTML = "<p class=\"plain-text\">原始策略继续使用下方 ETF 量能和评分参数。</p>";
    return;
  }
  const groups = Object.entries(metadata.parameter_schema || {});
  target.innerHTML = groups.map(([group, fields]) => `
    <section class="param-group"><h3>${group === "medium_trend" ? "中期趋势" : "短期入场"}</h3><div class="param-grid">
      ${Object.entries(fields).map(([key, spec]) => {
        const path = `etf.strategy_profiles.${strategyId}.${group}.${key}`;
        const value = getByPath(state.strategyParams, path) ?? spec.default;
        return `<div class="param-field"><label>${escapeHtml(spec.label || key)}</label><input data-param="${escapeHtml(path)}" type="number" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${escapeHtml(value ?? "")}" /></div>`;
      }).join("")}
    </div></section>`).join("");
}

function syncEtfStrategyFromForm() {
  const selected = document.getElementById("etf-strategy-select")?.value;
  if (!selected || !state.strategyParams?.etf) return;
  state.strategyParams.etf.active_strategy = selected;
  state.strategyParams.etf.diagnostic_strategies = document.getElementById("etf-diagnostics-enabled")?.checked
    ? ["legacy_v1", "trend_pullback_v2"]
    : [selected];
}

function renderCbStrategySelector() {
  const cbState = state.serverStrategyState?.cb;
  const enabled = document.getElementById("cb-auxiliary-enabled");
  if (!cbState || !enabled) return;
  enabled.checked = cbState.overlayEnabled;
  const generated = state.data?.convertible_bond?.strategy || null;
  const generatedTarget = document.getElementById("cb-generated-strategy");
  if (generatedTarget) generatedTarget.textContent = generated
    ? `当前页面结果：${generated.display_name || "原策略"} · v${generated.strategy_version}${generated.overlay_enabled ? " + 动态辅助" : ""}`
    : "当前页面尚无可转债策略身份记录";
  const refreshTarget = document.getElementById("cb-strategy-refresh-state");
  if (refreshTarget) refreshTarget.textContent = ETFStrategyConfig.generatedResultState(cbState, generated).label;
}

function syncCbStrategyFromForm() {
  if (!state.strategyParams?.convertible_bond) return;
  const enabled = Boolean(document.getElementById("cb-auxiliary-enabled")?.checked);
  state.strategyParams.convertible_bond.base_strategy = "legacy_v1";
  state.strategyParams.convertible_bond.auxiliary_overlay = {
    ...(state.strategyParams.convertible_bond.auxiliary_overlay || {}),
    enabled,
    overlay_id: "dynamic_v2",
    settings: state.strategyParams.convertible_bond.auxiliary_overlay?.settings || {},
  };
}

function renderModelConfig() {
  const config = state.modelConfig || {};
  const form = document.getElementById("model-config-form");
  const status = document.getElementById("model-config-status");
  if (!form) return;
  const chat = config.chat || {};
  const chatModel = chat.primary_model || config.primary_model || "";
  const candidates = Array.from(new Set([
    ...(state.openaiModels || []),
    config.primary_model,
    config.economy_model,
    chat.primary_model,
    "gpt-5.5",
    "gpt-5.4-mini",
  ].filter(Boolean)));
  const selectedKnownModel = candidates.includes(chatModel) ? chatModel : "__custom__";
  const customValue = selectedKnownModel === "__custom__" ? chatModel : "";
  const keyLine = config.api_key_configured
    ? `Key 已配置：${config.api_key_masked || "已遮挡"}`
    : "Key 未配置";
  if (status) status.textContent = `当前 AI 智能问答：OpenAI · ${chatModel || "--"} · ${keyLine}`;
  const keyStatusClass = state.openaiConnection === "ok" ? "is-ok" : state.openaiConnection === "warn" ? "is-warn" : "";
  const keyStatusText = state.openaiConnection === "ok"
    ? "连通正常"
    : state.openaiConnection === "warn"
      ? "未连通"
      : config.api_key_configured
        ? "已配置"
        : "未配置";
  form.innerHTML = `
    <div class="model-config-grid">
      <div class="param-field">
        <label>OpenAI 模型</label>
        <select id="chat-model-select">
          ${candidates.map((model) => `<option value="${escapeHtml(model)}" ${selectedKnownModel === model ? "selected" : ""}>${escapeHtml(model)}</option>`).join("")}
          <option value="__custom__" ${selectedKnownModel === "__custom__" ? "selected" : ""}>自定义模型名</option>
        </select>
        <small>下次 AI 智能问答调用时生效。</small>
      </div>
      <div class="param-field">
        <label>自定义模型名</label>
        <input id="chat-model-custom" type="text" value="${escapeHtml(customValue)}" placeholder="例如 gpt-5.5" />
        <small>选择“自定义模型名”时使用。</small>
      </div>
      <div class="param-field span-2">
        <label>OpenAI Key <span class="key-health ${keyStatusClass}">${escapeHtml(keyStatusText)}</span></label>
        <div class="key-control-row">
          <input id="openai-api-key" type="password" autocomplete="new-password" spellcheck="false" placeholder="${config.api_key_configured ? `已配置 ${escapeHtml(config.api_key_masked || "") }，粘贴新 Key 可替换` : "粘贴 OpenAI API Key"}" />
          <button id="save-openai-key" class="button primary" type="button">保存并验证</button>
          <button id="verify-openai-key" class="button" type="button">仅验证</button>
        </div>
        <small>Key 仅保存在这台电脑的本地环境文件中，不会写入模型配置，也不会在页面中显示明文。</small>
      </div>
      <p id="model-list-status" class="plain-text span-2">${escapeHtml(state.openaiModelMessage || "模型列表会按当前 key 自动读取。")}</p>
    </div>
  `;
}

function syncModelConfigFromForm() {
  const config = state.modelConfig || {};
  const selectedModel = document.getElementById("chat-model-select")?.value || "";
  const customModel = (document.getElementById("chat-model-custom")?.value || "").trim();
  const model = selectedModel === "__custom__" ? customModel : selectedModel;
  config.provider = config.provider || "openai";
  config.primary_model = config.primary_model || model || "gpt-5.5";
  config.api_key_env = config.api_key_env || "OPENAI_API_KEY";
  delete config.api_key_configured;
  delete config.api_key_masked;
  delete config.api_key;
  config.chat = {
    ...(config.chat || {}),
    provider: "openai",
    primary_model: model || config.primary_model || "gpt-5.5",
    llm_enabled: true,
  };
  state.modelConfig = config;
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
  const generatedEtfStrategy = data.etf?.strategy || data.run_info?.etf_strategy || null;
  const etfStateColumns = ETFStrategyConfig.showV2StateColumns(generatedEtfStrategy)
    ? [["medium_status", "中期趋势"], ["short_entry_status", "短期入场"]]
    : [];
  const etfRiskColumns = ETFStrategyConfig.showLegacyRiskOverlay(generatedEtfStrategy)
    ? [["risk_overlay_summary", "风险辅助"]]
    : [];
  document.getElementById("report-date").textContent = data.reportDate || "--";
  document.getElementById("rail-date").textContent = data.reportDate ? `日期 ${data.reportDate}` : "--";
  document.getElementById("report-link").href = data.reportPath ? reportUrl(data.reportPath) : "#";
  document.getElementById("research-summary").textContent = dailyDecisionText(data);

  renderKpis(summary);
  renderContext(summary);
  const etfBuyColumns = [
    ["name", "标的"],
    ["code", "代码"],
    ...etfStateColumns,
    ["close", "收盘"],
    ["score", "评分"],
    ...etfRiskColumns,
    ["signal_reason", "触发原因"],
  ];
  const etfSellColumns = [
    ["name", "标的"],
    ["code", "代码"],
    ...etfStateColumns,
    ["close", "收盘"],
    ["score", "评分"],
    ...etfRiskColumns,
    ["signal_reason", "触发原因"],
  ];
  const etfWatchColumns = [
    ["name", "标的"],
    ["code", "代码"],
    ...etfStateColumns,
    ["close", "收盘"],
    ...etfRiskColumns,
    ["watch_type", "关注原因"],
    ["suggested_action", "下一步"],
  ];
  const etfAllColumns = [
    ["rank", "排名"],
    ["name", "标的"],
    ["code", "代码"],
    ["position_status", "持仓状态"],
    ...etfStateColumns,
    ["display_action", "触发状态"],
    ["score", "强弱分"],
    ...etfRiskColumns,
    ["close", "收盘"],
    ["ma5_ma10_signal", "MA5/MA10"],
    ["ma5_ma20_status", "MA5/MA20"],
    ["volume_check", "量能检查"],
    ["decision_reason", "判断理由"],
  ];
  const tlRecentColumns = [
    ["date", "日期"],
    ["state", "状态"],
    ["fund_share_change_daily", "ETF当日份额"],
    ["fund_share_5d_sum", "ETF近5日累计"],
    ["fund_flow_relation", "资金关系"],
    ["daily_macd_reason", "日线MACD"],
    ["daily_kdj_threshold_check", "日线KDJ"],
    ["weekly_macd_reason", "周线MACD"],
  ];
  const cb = data.convertible_bond || {};
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
    ["base_score", "基础分"],
    ["base_grade", "基础等级"],
    ["qualification", "资格"],
    ["not_top_reason", "未入Top原因"],
    ["risk_flags", "风险提示"],
    ["auxiliary_state", "动态判断"],
    ["auxiliary_evidence", "四项依据"],
    ["rank_reason", "评分依据"],
  ];
  const cbSummary = cb.summary || {};
  const cbTopRows = cb.top10 || data.cbTop10 || [];
  const cbRankedRows = cb.candidates || cb.ranked_candidates || data.cbRanked || [];
  renderDailyWorkbench(data, summary);
  renderModuleKpis(summary);
  renderTable("buy-table", data.etfBuyCandidates || [], etfBuyColumns, "buy");
  renderTable("sell-table", data.etfSellAlerts || [], etfSellColumns, "sell");
  renderTable("etf-buy-table", data.etfBuyCandidates || [], etfBuyColumns, "buy");
  renderTable("etf-sell-table", data.etfSellAlerts || [], etfSellColumns, "sell");
  renderTable("etf-watch-table", data.etfWatchlist || [], etfWatchColumns, "watch");
  renderEtfHistoricalDiagnostics(data.etf?.historical_diagnostics || []);
  renderTable("etf-all-table", rankedEtfRows(data.etf?.all_signals || data.etfAllSignals || []), etfAllColumns);
  renderWatchlist(data.etfWatchlist || [], data.etfDetailHistory || []);
  renderTL(data.tlToday?.[0] || {});
  renderTLPanel(data.tlToday?.[0] || {});
  renderTable("tl-recent-table", data.tlRecent || [], tlRecentColumns);
  renderTable("tl-panel-recent-table", data.tlRecent || [], tlRecentColumns);
  renderCbSummary(cbSummary);
  renderTable("cb-table", convertibleRowsForDisplay(cbTopRows), cbColumns, "watch");
  renderTable("cb-top-table", convertibleRowsForDisplay(cbTopRows), cbColumns, "watch");
  renderTable("cb-ranked-table", convertibleRowsForDisplay(cbRankedRows), cbColumns, "watch");
  renderTable(
    "cb-quality-table",
    (data.dataQuality || []).filter((row) => String(row.item || "").includes("可转债") || String(row.item || "").includes("强赎") || String(row.item || "").includes("YTM") || String(row.item || "").includes("评级")),
    [["item", "识别项"], ["status", "状态"], ["detail", "详情"], ["note", "处理说明"]],
  );
  renderTable("quality-table", data.dataQuality || [], [
    ["item", "检查项"],
    ["status", "结果"],
    ["detail", "当前值"],
    ["note", "说明"],
  ]);
  renderTable("source-table", data.sourceManifest || [], [
    ["source_type", "数据类型"],
    ["exists", "是否找到"],
    ["modified_at", "修改时间"],
    ["size_bytes", "文件大小"],
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
    status_label: row.status === "success" ? "完成" : row.status === "warning" ? "有提示" : row.status === "failed" ? "失败" : row.status,
    duration_text: Number.isFinite(Number(row.duration_ms)) ? `${(Number(row.duration_ms) / 1000).toFixed(1)}秒` : "--",
  }));
  renderTable("agent-table", auditRows, [
    ["agent", "步骤"],
    ["status_label", "结果"],
    ["message", "说明"],
    ["duration_text", "耗时"],
  ]);
}

function renderEtfHistoricalDiagnostics(rows) {
  const comparison = ETFStrategyConfig.historicalComparisonRows(rows);
  const strategyName = (strategyId) => strategyId === "trend_pullback_v2" ? "2.0 趋势回踩" : "原策略";
  const percent = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : "--";
  const displayRows = comparison.map((row) => ({
    strategy_name: strategyName(row.strategy_id),
    horizon_text: `${row.horizon}日`,
    sample_count: row.complete_horizon_count,
    positive_rate_text: percent(row.positive_return_rate),
    mean_return_text: percent(row.mean_return),
    adverse_text: percent(row.mean_maximum_adverse_excursion),
    false_reversal_text: row.horizon === 10
      ? `${row.false_reversal_10d_count}（${percent(row.false_reversal_10d_rate)}）`
      : "仅10日统计",
  }));
  renderTable("etf-history-table", displayRows, [
    ["strategy_name", "策略"],
    ["horizon_text", "观察周期"],
    ["sample_count", "有效样本"],
    ["positive_rate_text", "正收益比例"],
    ["mean_return_text", "平均收益"],
    ["adverse_text", "期间平均最大不利波动"],
    ["false_reversal_text", "假反转次数"],
  ]);
  const highlights = document.getElementById("etf-history-highlights");
  if (!highlights) return;
  const tenDay = comparison.filter((row) => row.horizon === 10);
  highlights.innerHTML = tenDay.length
    ? tenDay.map((row) => `
      <div class="history-highlight">
        <span>${escapeHtml(strategyName(row.strategy_id))} · 10日</span>
        <strong>${escapeHtml(percent(row.positive_return_rate))}</strong>
        <small>正收益比例 · 样本 ${escapeHtml(row.complete_horizon_count)} · 最大不利波动 ${escapeHtml(percent(row.mean_maximum_adverse_excursion))} · 假反转 ${escapeHtml(row.false_reversal_10d_count)}（${escapeHtml(percent(row.false_reversal_10d_rate))}）</small>
      </div>
    `).join("")
    : `<p class="plain-text">暂无完整历史诊断，请刷新数据后查看。</p>`;
}

function renderContext(summary) {
  const data = state.data;
  const items = [
    ["AI模式", state.aiChatEnabled ? "已开启" : "未开启"],
    ["当前模型", chatModelStatus()],
    ["报告日期", data.reportDate || "--"],
    ["ETF建仓", pick(summary, "ETF建仓候选数量")],
    ["ETF关注", pick(summary, "ETF关注池数量")],
    ["ETF平仓", pick(summary, "ETF平仓提示数量")],
    ["TL状态", pick(summary, "TL今日状态")],
    ["转债Top10", pick(summary, "可转债Top10数量")],
    ["已识别风险", pickSummary(summary, "系统已识别风险项", "数据校验异常项")],
    ["日报解释", dailyReportMode(summary)],
  ];
  document.getElementById("context-grid").innerHTML = items
    .map((item) => `<div class="context-item"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`)
    .join("");

  const sources = [
    "ETF信号矩阵",
    "TL MACD/KDJ择时",
    "可转债排序",
    "数据质检",
    "系统运行记录",
  ];
  document.getElementById("context-sources").innerHTML = sources.map((item) => `<li>${item}</li>`).join("");
}

function renderKpis(summary) {
  const node = document.getElementById("kpi-grid");
  if (!node) return;
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
  node.innerHTML = items
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

function renderDailyWorkbench(data, summary) {
  const cb = data.convertible_bond || {};
  const cbSummary = cb.summary || {};
  const etfRows = rankedEtfRows(data.etf?.all_signals || data.etfAllSignals || []);
  const tl = data.tlToday?.[0] || {};
  const buyCount = Number(pick(summary, "ETF建仓候选数量")) || 0;
  const watchCount = Number(pick(summary, "ETF关注池数量")) || 0;
  const sellCount = Number(pick(summary, "ETF平仓提示数量")) || 0;
  const qualifiedCount = Number(cbSummary.qualified_count ?? 0);
  const weakCount = Number(cbSummary.weak_watch_count ?? 0);
  const riskCount = Number(cbSummary.risk_watch_count ?? 0);
  const excludedCount = Number(cbSummary.excluded_count ?? 0);
  const canReviewCount = buyCount + sellCount + qualifiedCount;
  const watchOnlyCount = watchCount + weakCount + riskCount + (tl.attention_signal ? 1 : 0);
  const noActionCount = excludedCount + (tl.no_trade_signal ? 1 : 0);

  renderReportActions([
    ["今日主线", reportRegime(canReviewCount, watchOnlyCount, tl)],
    ["可复核", `${canReviewCount} 项`],
    ["仅观察", `${watchOnlyCount} 项`],
    ["不操作/排除", `${noActionCount} 项`],
  ]);
  renderReportAssetCards([
    {
      title: "ETF",
      state: buyCount ? "有建仓候选" : sellCount ? "有平仓提示" : watchCount ? "仅观察" : "未触发",
      body: `建仓 ${buyCount}，关注 ${watchCount}，平仓 ${sellCount}。${etfRows.length ? `强弱分最高：${etfRows[0].name} ${formatNumber(etfRows[0].score)}。` : "暂无全量评分。"}`,
      href: "#etf",
    },
    {
      title: "TL",
      state: tl.state || "--",
      body: `${tl.reason || "暂无规则原因"}。资金辅助：${tl.fund_flow_relation || "数据不足"}；${tl.fund_flow_note || "暂无份额数据"}。`,
      href: "#tl",
    },
    {
      title: "可转债",
      state: qualifiedCount ? "有合格候选" : "无合格候选",
      body: `合格 ${qualifiedCount}，弱观察 ${weakCount}，风险观察 ${riskCount}，排除 ${excludedCount}。${cbSummary.quality_message || ""}`,
      href: "#cb",
    },
  ]);
  renderReportWorklist([
    ["可复核", canReviewCount ? "查看 ETF 建仓/平仓和可转债合格候选，进入人工复核。" : "今日没有满足完整规则的候选。"],
    ["仅观察", watchOnlyCount ? "关注接近触发的 ETF、TL 日线改善和可转债弱/风险观察。" : "今日观察项较少。"],
    ["不操作", noActionCount ? "被排除转债和 TL 不做交易状态不进入交易候选。" : "暂无明确排除项。"],
  ]);
  renderTable("report-etf-near-table", reportEtfNearRows(etfRows), [
    ["rank", "排名"],
    ["name", "ETF"],
    ["score", "强弱分"],
    ["display_action", "触发"],
    ["volume_check", "量能"],
    ["decision_reason", "缺口/原因"],
  ]);
  renderTable("report-cb-risk-table", reportCbRiskRows(data), [
    ["bond_name", "转债"],
    ["bond_code", "代码"],
    ["qualification_label", "分层"],
    ["price", "价格"],
    ["conversion_premium_rate", "溢价率"],
    ["ytm", "YTM"],
    ["risk_reason", "原因"],
  ]);
  renderReportRiskList(data, summary);
}

function dailyDecisionText(data) {
  const summary = data.summary || [];
  const cbSummary = data.convertible_bond?.summary || {};
  const tl = data.tlToday?.[0] || {};
  const buyCount = Number(pick(summary, "ETF建仓候选数量")) || 0;
  const watchCount = Number(pick(summary, "ETF关注池数量")) || 0;
  const sellCount = Number(pick(summary, "ETF平仓提示数量")) || 0;
  const qualifiedCount = Number(cbSummary.qualified_count ?? 0);
  const actionCount = buyCount + sellCount + qualifiedCount;
  if (actionCount > 0) {
    return `今日存在 ${actionCount} 项可进入人工复核的规则候选。先核对 ETF 建仓/平仓和可转债合格候选，再看组合约束；AI 不改写信号。`;
  }
  return `今日无满足完整规则的交易候选。ETF 建仓 ${buyCount}、关注 ${watchCount}、平仓 ${sellCount}；TL 为“${tl.state || "--"}”；可转债无合格 Top 候选。今天重点是观察缺口和确认风险排除原因。`;
}

function reportRegime(actionCount, watchCount, tl) {
  if (actionCount > 0) return "有规则候选，进入人工复核";
  if (tl.no_trade_signal) return "防守观察，TL 不做交易";
  if (watchCount > 0) return "无候选，观察接近触发项";
  return "无候选，等待规则条件修复";
}

function renderReportActions(items) {
  const node = document.getElementById("daily-action-grid");
  if (!node) return;
  node.innerHTML = items
    .map((item) => `<div class="report-action"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`)
    .join("");
}

function renderReportAssetCards(cards) {
  const node = document.getElementById("report-asset-cards");
  if (!node) return;
  node.innerHTML = cards
    .map(
      (card) => `
        <article class="report-asset-card">
          <div><span>${escapeHtml(card.title)}</span><strong>${escapeHtml(card.state)}</strong></div>
          <p>${escapeHtml(card.body)}</p>
          <a href="${escapeHtml(card.href)}">查看明细</a>
        </article>
      `,
    )
    .join("");
}

function renderReportWorklist(items) {
  const node = document.getElementById("report-worklist");
  if (!node) return;
  node.innerHTML = items
    .map((item) => `<div><strong>${escapeHtml(item[0])}</strong><span>${escapeHtml(item[1])}</span></div>`)
    .join("");
}

function reportEtfNearRows(rows) {
  return rows
    .filter((row) => row.display_action !== "模型触发建仓候选" && row.display_action !== "模型触发平仓提示")
    .slice(0, 6);
}

function reportCbRiskRows(data) {
  const cb = data.convertible_bond || {};
  const rows = [
    ...(cb.risk_watch || []),
    ...(cb.weak_watch || []),
    ...(cb.excluded || []),
    ...(data.cbExcluded || []),
  ];
  const seen = new Set();
  return rows
    .filter((row) => {
      const code = row.bond_code || row.code;
      if (!code || seen.has(code)) return false;
      seen.add(code);
      return true;
    })
    .slice(0, 8)
    .map((row) => ({
      ...row,
      qualification_label: qualificationLabel(row.qualification),
      risk_reason: row.not_top_reason || row.excluded_reason || row.rank_reason || formatNumber(row.quality_notes || row.risk_flags || "--"),
    }));
}

function renderReportRiskList(data, summary) {
  const node = document.getElementById("report-risk-list");
  if (!node) return;
  const riskItems = pickSummary(summary, "系统已识别风险项", "数据校验异常项");
  const auditWarns = pick(summary, "回测诊断WARN数量");
  const llmMode = dailyReportMode(summary);
  const qualityWarns = (data.dataQuality || []).filter((row) => !["OK", "INFO", "SUCCESS"].includes(String(row.status || "").toUpperCase())).slice(0, 3);
  const items = [
    ["风险项", `${riskItems} 项已识别，需在交易前确认。`],
    ["历史诊断", `WARN ${auditWarns}，只用于流程诊断，不作为收益验证。`],
    ["日报解释", `${llmMode}；规则结果不依赖 AI。`],
    ...qualityWarns.map((row) => [row.item || "数据质量", row.note || row.detail || row.status || "--"]),
  ];
  node.innerHTML = items
    .map((item) => `<div><strong>${escapeHtml(item[0])}</strong><span>${escapeHtml(item[1])}</span></div>`)
    .join("");
}

function renderCbSummary(summary) {
  const title = document.getElementById("cb-top-title");
  const message = document.getElementById("cb-quality-message");
  if (title) title.textContent = summary.top_display_title || "可转债 Top10 候选";
  if (message) message.textContent = summary.quality_message || "";
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
  if (!state.aiChatEnabled) return "规则模式";
  const config = state.modelConfig || {};
  const chat = config.chat || {};
  const provider = chat.provider || config.provider || "openai";
  const providerLabel = provider === "openai" ? "OpenAI" : provider;
  const model = chat.primary_model || config.primary_model || "";
  const keyStatus = config.api_key_configured ? "Key已配置" : "Key未配置";
  const connection = state.openaiConnection === "ok" ? "连通正常" : keyStatus;
  if (model) return `${providerLabel} · ${model} · ${connection}`;
  const latest = state.dbStatus?.chatModel?.latest;
  const fallbackModel = state.data?.llmUsage?.llm_model || pick(state.data?.summary || [], "日报解释模型") || pick(state.data?.summary || [], "LLM模型");
  if (latest?.llm_used) return `已连接 ${latest.llm_model || fallbackModel || ""}`.trim();
  return fallbackModel && fallbackModel !== "--" ? `已配置 ${fallbackModel}` : "待验证";
}

function renderAiChatButton() {
  const button = document.getElementById("ai-chat-toggle");
  if (!button) return;
  const modelName = (state.modelConfig?.chat || {}).primary_model || state.modelConfig?.primary_model || "";
  button.classList.toggle("is-on", state.aiChatEnabled);
  button.textContent = state.aiChatEnabled ? "AI 已开启" : "AI 智能问答";
  button.title = state.aiChatEnabled && modelName ? `当前模型：${modelName}` : "";
}

function toggleAiChatMode() {
  if (!state.aiChatEnabled) {
    const ok = window.confirm("开启 AI 智能问答后，系统才会调用大模型解释本地证据。交易信号、排名和风险分层仍以规则代码为准。确认开启？");
    if (!ok) return;
    state.aiChatEnabled = true;
  } else {
    state.aiChatEnabled = false;
  }
  renderAiChatButton();
  render();
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
    ["ETF当日份额变化（亿份）", row.fund_share_change_daily],
    ["ETF当日资金等级", row.fund_share_daily_level],
    ["ETF近5日累计（亿份）", row.fund_share_5d_sum],
    ["ETF资金关系", row.fund_flow_relation],
    ["ETF资金提示", row.fund_flow_note],
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
    ["ETF当日份额变化（亿份）", row.fund_share_change_daily],
    ["ETF当日资金等级", row.fund_share_daily_level],
    ["ETF近5日累计（亿份）", row.fund_share_5d_sum],
    ["ETF资金关系", row.fund_flow_relation],
    ["资金辅助提示", row.fund_flow_note],
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
  const thead = `<thead><tr>${columns.map(([key, label]) => `<th class="${ETFStrategyConfig.tableColumnClass(key)}" data-column="${escapeHtml(key)}">${escapeHtml(label)}</th>`).join("")}</tr></thead>`;
  const tbody = rows
    .map((row) => {
      const cells = columns
        .map(([key]) => {
          const value = row[key];
          const columnClass = ETFStrategyConfig.tableColumnClass(key);
          if (key === "status" || key === "level" || key === "exists" || key === "result") {
            const tagClass =
              value === "OK" || value === "INFO" || value === "success" || value === true || value === "对" ? "ok" : "warn";
            return `<td class="${columnClass}" data-column="${escapeHtml(key)}"><span class="tag ${tagClass}">${escapeHtml(value)}</span></td>`;
          }
          if (key === "auxiliary_state") {
            const label = ETFStrategyConfig.auxiliaryStateLabel(value);
            const tagClass = label === "正常联动" ? "ok" : label === "数据不足" ? "warn" : /走弱|追涨/.test(label) ? "sell" : "watch";
            return `<td class="${columnClass}" data-column="${escapeHtml(key)}"><span class="tag ${tagClass}">${escapeHtml(label)}</span></td>`;
          }
          if (key === "signal_reason" || key === "watch_type") {
            const tagClass = mode === "sell" ? "sell" : mode === "watch" ? "watch" : "buy";
            return `<td class="${columnClass}" data-column="${escapeHtml(key)}"><span class="tag ${tagClass}">${escapeHtml(value)}</span></td>`;
          }
          return `<td class="${columnClass}" data-column="${escapeHtml(key)}">${escapeHtml(formatValue(key, value))}</td>`;
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
  const thinking = appendMessage("assistant", "正在由后端规则引擎读取最新投研证据。", "AI");
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
    if (window.location.protocol === "file:") {
      const answer = [
        "现在这个页面是直接用 file:// 打开的，所以不能调用后端的 /api/chat，也就不会真正进入 AI 模型。",
        "",
        "请先双击“启动AI投研.command”，然后从 http://127.0.0.1:8766/frontend/#chat 打开投研问答。这样 AI 智能问答才会读取本地数据库和 dashboard 证据包，再调用大模型组织回答。",
        "",
        "当前我不会把本地规则模板伪装成 AI 回答。"
      ].join("\n");
      const fileResult = localChatResult(answer, "ai_backend_unavailable", "file_protocol", "AI backend unavailable", "frontend.runtime");
      liveStream.finish(fileResult);
      await streamAnswer(thinking, fileResult.answer);
      thinking.querySelector(".message-body span").textContent = "AI 后端未连接 · 当前是 file:// 页面";
      attachAnalysisDetails(thinking, fileResult, question);
      renderAgentRuntime(fileResult);
      rememberChatTurn(question, fileResult, fileResult.answer);
      return;
    }

    const controller = new AbortController();
    timeoutId = window.setTimeout(() => controller.abort(), 90000);
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        sessionId: "local-dashboard",
        userId: "local-user",
        shortTermMemory: state.chatMemory || {},
        allowLlm: state.aiChatEnabled,
      }),
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
    rememberChatTurn(question, result, result.answer);
  } catch (error) {
    const message = error.name === "AbortError" ? "请求超过 90 秒，已使用本地确定性摘要回答" : error.message;
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
    rememberChatTurn(question, fallbackResult, thinking.querySelector(".message-body > p")?.textContent || "");
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
    state.isChatting = false;
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
    ["规则核对", "按系统规则核对字段，不新增交易信号。"],
    ["生成回答", "组织成用户可读结论和证据说明。"],
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
      { name: "RuleCheck", status: "queued", detail: "将按系统规则核对 ETF、TL、可转债字段，不新增规则外判断。" },
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
        ? `<p class="analysis-lede">这是可审计分析过程：展示系统如何分类问题、读取证据、套用系统规则和做输出校验，不展示模型隐藏思考。</p>`
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

  const etfAnswer = localEtfAssetAnswer(question);
  if (etfAnswer) return localChatResult(etfAnswer, "etf_detail", "local_etf_detail_answer", "Local ETF detail", "frontend.dashboard.etf.all_signals");

  const cbAnswer = localConvertibleAnswer(question);
  if (cbAnswer) return localChatResult(cbAnswer, "convertible_bond", "local_convertible_detail_answer", "Local convertible detail", "frontend.dashboard.convertible_bond + cbExcluded");

  const tlAnswer = localTlAnswer(question);
  if (tlAnswer) return localChatResult(tlAnswer, "tl_timing", "local_tl_detail_answer", "Local TL timing", "frontend.dashboard.tlToday");

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

function localChatResult(answer, intentName, reason, title, source) {
  return {
    status: "success",
    answer,
    intent: { name: intentName, confidence: 1 },
    steps: [
      { name: "LocalDashboard", status: "success", detail: "从当前页面已加载的 dashboard 读取确定性证据。" },
      { name: "DeterministicAnswerAgent", status: "success", detail: "按本地规则字段生成回答，不调用模型补猜。" },
      { name: "OutputGuardrail", status: "success", detail: "未改写信号、排名或风险分层。" },
    ],
    evidence: [{ title, summary: "当前回答来自本地日报数据和规则字段。", source }],
    traceId: "local",
    llmUsed: false,
    llmModel: "local_deterministic",
    llmReason: reason,
    guardrail: { passed: true, issues: [] },
  };
}

function localEtfAssetAnswer(question) {
  const row = findLocalEtfRow(question);
  if (!row) return "";
  const threshold = state.strategyParams?.etf?.buy_volume_ratio_min ?? "--";
  const name = row.name || "--";
  const code = row.code || "--";
  const date = String(row.date || row.trade_date || state.data?.reportDate || "").slice(0, 10);
  const action = row.display_action || signalActionText(row) || "未触发";
  const reason = row.signal_reason || row.reason || row.missing_condition || "--";
  const recent = localEtfRecentLine(code);
  const lines = [
    `结论：${name}（${code}）截至 ${date || "--"} 的今日判断是：${action}。`,
    `持仓路径：系统当前把它识别为“${row.position_status || "--"}”。持仓中才检查平仓提示；空仓或已平仓才检查建仓候选和关注池。`,
    `今日指标：收盘 ${formatNumber(row.close)}，MA5 ${formatNumber(row.ma5)}，MA10 ${formatNumber(row.ma10)}，MA20 ${formatNumber(row.ma20)}，MA60 ${formatNumber(row.ma60)}，量能倍数 ${formatNumber(row.vol_ratio60)}，MACD柱 ${formatNumber(row.macd_hist)}，DIF ${formatNumber(row.metrics?.dif)}，DEA ${formatNumber(row.metrics?.dea)}，评分 ${formatNumber(row.score)}。`,
    `规则证据：${row.ma5_ma10_signal || "--"}；${row.ma5_ma20_status || "--"}；${row.volume_check || "--"}。判断理由：${reason}`,
  ];
  if (recent) lines.push(recent);
  lines.push(`动作提示：当前未触发建仓候选时，继续跟踪 MA5 上穿、MACD 改善/金叉和量能倍数是否达到 ${threshold}。`);
  lines.push("来源：本地 dashboard.etf.all_signals、策略参数。");
  return lines.join("\n\n");
}

function findLocalEtfRow(question) {
  const rows = state.data?.etf?.all_signals || state.data?.etfAllSignals || [];
  return rows.find((row) => localRowMatchesQuestion(row, question, "ETF")) || null;
}

function signalActionText(row) {
  const mapping = {
    buy_candidate: "模型触发建仓候选",
    sell_alert: "模型触发平仓提示",
    watch: "进入观察池",
    neutral: "未触发",
    data_unavailable: "数据不足，无法判断",
  };
  return mapping[row.signal_type || row.action] || "";
}

function localEtfRecentLine(code) {
  const rows = (state.data?.etfDetailHistory || []).filter((row) => row.code === code);
  if (rows.length < 2) return "";
  const sorted = [...rows].sort((left, right) => String(left.date || left.trade_date).localeCompare(String(right.date || right.trade_date)));
  const latest = sorted[sorted.length - 1];
  const previous = sorted[sorted.length - 2];
  const close = Number(latest.close ?? latest["收盘价"]);
  const prevClose = Number(previous.close ?? previous["收盘价"]);
  if (!Number.isFinite(close) || !Number.isFinite(prevClose) || prevClose === 0) return "";
  const change = close / prevClose - 1;
  const direction = change > 0 ? "上涨" : change < 0 ? "下跌" : "持平";
  return `最近一日变化：较上一有效交易日${direction} ${(change * 100).toFixed(2)}%，这只是行情事实，不改变今日规则判断。`;
}

function localConvertibleAnswer(question) {
  const hit = findLocalConvertibleRow(question);
  if (!hit) return "";
  const row = hit.row;
  const name = row.bond_name || row.name || "--";
  const code = row.bond_code || row.code || "--";
  const reason = row.not_top_reason || row.excluded_reason || row.rank_reason || "--";
  const strategyLine = `当前基础策略：原策略 v1；基础分 ${formatNumber(row.base_score ?? row.score)}。动态判断：${ETFStrategyConfig.auxiliaryStateLabel(row.auxiliary_state ?? row.dynamic_state)}，辅助分 ${formatNumber(row.auxiliary_score ?? row.dynamic_score)}。${row.auxiliary_note || row.dynamic_note || ""}动态辅助不改变资格、动作和排名。`;
  return [
    `结论：${name}（${code}）截至 ${state.data?.reportDate || "--"} 不进入合格 Top 候选。当前分层：${qualificationLabel(row.qualification || hit.bucket)}；是否可进合格 Top：${row.eligible_for_top === true ? "是" : "否"}。`,
    `核心原因：${reason}`,
    `当前字段：价格 ${formatNumber(row.price)}，转股溢价率 ${formatNumber(row.conversion_premium_rate)}，YTM ${formatNumber(row.ytm)}，评级 ${row.bond_rating || row.rating || "--"}，存续规模 ${formatNumber(row.remaining_size)}，强赎状态 ${row.redemption_status || "--"}，基础分 ${formatNumber(row.base_score ?? row.score)}，基础等级 ${row.base_grade || row.score_grade || "--"}，风险等级 ${row.risk_level || "--"}。`,
    `风险备注：${formatNumber(row.quality_notes || row.risk_flags || "--")}`,
    strategyLine,
    `动态辅助四项依据：${convertibleAuxiliaryEvidence(row)}。`,
    "规则口径：可转债先做价格、评级、强赎、YTM、溢价率、规模和基本面等风控，再做候选资格分层；弱观察和风险观察不补进合格 Top。",
    "来源：本地 dashboard.convertible_bond、cbExcluded、策略参数。",
  ].join("\n\n");
}

function findLocalConvertibleRow(question) {
  const cb = state.data?.convertible_bond || {};
  const buckets = [
    ["qualified", cb.qualified || cb.top10 || state.data?.cbTop10 || []],
    ["weak_watch", cb.weak_watch || []],
    ["risk_watch", cb.risk_watch || []],
    ["ranked_candidates", [...(cb.candidates || []), ...(cb.ranked_candidates || []), ...(state.data?.cbRanked || [])]],
    ["excluded", [...(cb.excluded || []), ...(state.data?.cbExcluded || [])]],
  ];
  for (const [bucket, rows] of buckets) {
    const row = rows.find((item) => localRowMatchesQuestion({ ...item, name: item.bond_name || item.name, code: item.bond_code || item.code }, question, "转债"));
    if (row) return { bucket, row };
  }
  return null;
}

function localTlAnswer(question) {
  if (!question.includes("TL") && !question.includes("tl") && !question.includes("国债")) return "";
  const row = state.data?.tlToday?.[0];
  if (!row) return "";
  const date = String(row.date || state.data?.reportDate || "").slice(0, 10);
  return [
    `结论：${row.name || "30年国债期货TL"}（${row.code || "TL.CFE"}）截至 ${date || "--"} 的今日状态是：${row.display_status || row.state || row.action || "--"}。`,
    `今日指标：收盘 ${formatNumber(row["收盘价"])}，MA5 ${formatNumber(row.ma5)}，MA10 ${formatNumber(row.ma10)}，MA20 ${formatNumber(row.ma20)}，MA60 ${formatNumber(row.ma60)}，量能倍数 ${formatNumber(row.vol_ratio60)}。`,
    `日线证据：MACD柱 ${formatNumber(row.macd_hist)}，KDJ J ${formatNumber(row.kdj_j)}；日线MACD判断：${row.daily_macd_reason || "--"}；日线KDJ检查：${row.daily_kdj_threshold_check || "--"}`,
    `周线证据：MACD柱 ${formatNumber(row.week_macd_hist)}，KDJ J ${formatNumber(row.week_kdj_j)}；周线MACD判断：${row.weekly_macd_reason || "--"}；周线KDJ检查：${row.weekly_kdj_threshold_check || "--"}`,
    `资金辅助：当日份额变化 ${formatNumber(row.fund_share_change_daily)} 亿份（${row.fund_share_daily_level || "数据不足"}），近5日累计 ${formatNumber(row.fund_share_5d_sum)} 亿份；${row.fund_flow_note || "份额变化数据不足，不影响原TL状态"}`,
    `规则结论：${row.reason || "--"}`,
    row.rule_hits ? `规则命中：${row.rule_hits}` : "",
    `动作提示：${row.no_trade_signal ? "当前属于不做交易路径；周线不做交易或KDJ低位反弹条件不满足时，日线改善不能单独升级为建仓。" : row.attention_signal ? "当前属于关注交易路径；继续观察日线/周线KDJ低位反弹条件是否补齐。" : "当前未触发明确建仓候选。"}`,
    row.risk_notes ? `边界说明：${row.risk_notes}` : "",
    "来源：本地 dashboard.tlToday、dashboard.tlRecent、策略参数。",
  ].filter(Boolean).join("\n\n");
}

function localRowMatchesQuestion(row, question, suffix) {
  const rawName = String(row.name || "");
  const code = String(row.code || "");
  const aliases = [rawName, code, code.replace(".SH", "").replace(".SZ", "")];
  if (suffix && rawName.endsWith(suffix)) aliases.push(rawName.slice(0, -suffix.length));
  if (suffix === "ETF") aliases.push(rawName.replace("ETF", ""));
  return aliases.filter(Boolean).some((alias) => question.includes(alias));
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
    return `当前系统已识别风险项为 ${riskItems}。这些不是系统错误，而是按客户规则识别出的强赎、信用、低价、高YTM、低评级或覆盖范围提示。请到“系统状态”查看具体处理说明。`;
  }
  return data.researchSummary?.[0]?.content || "当前没有可用摘要，请先刷新数据。";
}

function reportUrl(path) {
  const filename = path.split("/").pop();
  return `/outputs/${encodeURIComponent(filename)}`;
}

function setActiveView() {
  const requestedId = (window.location.hash || "#chat").slice(1);
  const id = requestedId === "agents" ? "data" : requestedId;
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
document.getElementById("export-pdf").addEventListener("click", exportPdf);
document.getElementById("ai-chat-toggle")?.addEventListener("click", toggleAiChatMode);
document.getElementById("clear-chat-memory")?.addEventListener("click", clearShortTermMemory);
document.getElementById("save-params")?.addEventListener("click", saveStrategyParams);
document.getElementById("etf-strategy-select")?.addEventListener("change", renderEtfProfileControls);
document.getElementById("save-model-config")?.addEventListener("click", saveModelConfig);
document.getElementById("refresh-openai-models")?.addEventListener("click", loadOpenAiModels);
document.getElementById("model-config-form")?.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.id === "verify-openai-key") {
    event.preventDefault();
    verifyOpenAiConnection();
  }
  if (target.id === "save-openai-key") {
    event.preventDefault();
    saveOpenAiKey();
  }
});
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
renderChatMemoryStatus();
loadDashboard();
