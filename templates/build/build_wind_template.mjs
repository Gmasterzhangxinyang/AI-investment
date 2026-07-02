import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const buildDir = path.resolve(".");
const seed = JSON.parse(await fs.readFile(path.join(buildDir, "seed_data.json"), "utf8"));
const outputDir = path.join(buildDir, "output");
const outputPath = path.join(outputDir, "Wind数据模板-AI投研系统-客户交付版.xlsx");

const workbook = Workbook.create();

const colors = {
  ink: "#17202A",
  muted: "#5D6D7E",
  teal: "#0F766E",
  tealDark: "#115E59",
  blue: "#1D4ED8",
  amber: "#F59E0B",
  green: "#15803D",
  red: "#B91C1C",
  surface: "#F8FAFC",
  panel: "#E7F5F2",
  header: "#DDE8F0",
  input: "#FFF2CC",
  line: "#D5DEE7",
  dark: "#153243",
};

function colLetter(idx) {
  let n = idx + 1;
  let s = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function rangeAddress(rowCount, colCount, startRow = 0, startCol = 0) {
  return `${colLetter(startCol)}${startRow + 1}:${colLetter(startCol + colCount - 1)}${startRow + rowCount}`;
}

function writeMatrix(sheet, matrix, startRow = 0, startCol = 0) {
  const maxCols = Math.max(...matrix.map((row) => row.length));
  const normalized = matrix.map((row) => {
    const out = row.slice();
    while (out.length < maxCols) out.push(null);
    return out;
  });
  const range = sheet.getRange(rangeAddress(normalized.length, maxCols, startRow, startCol));
  range.values = normalized;
  return range;
}

function asDateMatrix(matrix) {
  return matrix.map((row, rowIdx) => {
    if (rowIdx < 3) return row;
    const out = row.slice();
    if (typeof out[0] === "string" && /^\d{4}-\d{2}-\d{2}$/.test(out[0])) {
      out[0] = new Date(`${out[0]}T00:00:00`);
    }
    return out;
  });
}

function safeFormat(fn) {
  try {
    fn();
  } catch (err) {
    console.warn(`format skipped: ${err.message}`);
  }
}

function styleSheetBase(sheet) {
  safeFormat(() => {
    sheet.showGridLines = false;
  });
}

function styleTitle(sheet, title, subtitle) {
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A2").values = [[subtitle]];
  safeFormat(() => {
    sheet.getRange("A1:H1").format.fill.color = colors.panel;
    sheet.getRange("A1:H1").format.font.color = colors.ink;
    sheet.getRange("A1:H1").format.font.bold = true;
    sheet.getRange("A1:H1").format.font.size = 16;
    sheet.getRange("A2:H2").format.fill.color = colors.panel;
    sheet.getRange("A2:H2").format.font.color = colors.ink;
    sheet.getRange("A2:H2").format.font.size = 11;
    sheet.getRange("A1:H2").format.borders = { preset: "outside", style: "thin", color: colors.line };
  });
  if (!sheet.getRange("A1").values?.[0]?.[0]) {
    sheet.getRange("A1").values = [[title]];
    sheet.getRange("A2").values = [[subtitle]];
  }
}

function styleTable(sheet, rangeAddressText, headerRows = 1) {
  safeFormat(() => {
    const range = sheet.getRange(rangeAddressText);
    range.format.borders = { preset: "all", style: "thin", color: colors.line };
    range.format.font.size = 10;
    range.format.wrapText = true;
    const [start, end] = rangeAddressText.split(":");
    const startMatch = start.match(/([A-Z]+)(\d+)/);
    const endMatch = end.match(/([A-Z]+)(\d+)/);
    if (startMatch && endMatch) {
      const startRow = Number(startMatch[2]);
      const startCol = startMatch[1];
      const endCol = endMatch[1];
      const headerRange = sheet.getRange(`${startCol}${startRow}:${endCol}${startRow + headerRows - 1}`);
      headerRange.format.fill.color = colors.header;
      headerRange.format.font.bold = true;
      headerRange.format.font.color = colors.ink;
    }
  });
}

function setWidths(sheet, widths) {
  safeFormat(() => {
    for (const [col, width] of Object.entries(widths)) {
      sheet.getRange(`${col}:${col}`).format.columnWidth = width;
    }
  });
}

function applyValidation(sheet, range, values) {
  safeFormat(() => {
    sheet.getRange(range).dataValidation = { rule: { type: "list", values } };
  });
}

function makeRawSheet(sheetName, matrix, dateFormatRange, headerCols) {
  const sheet = workbook.worksheets.add(sheetName);
  writeMatrix(sheet, asDateMatrix(matrix));
  safeFormat(() => {
    sheet.freezePanes.freezeRows(3);
    sheet.getRange(`A1:${colLetter(headerCols - 1)}3`).format.fill.color = colors.header;
    sheet.getRange(`A1:${colLetter(headerCols - 1)}3`).format.font.bold = true;
    sheet.getRange(`A1:${colLetter(headerCols - 1)}3`).format.borders = { preset: "all", style: "thin", color: colors.line };
    sheet.getRange(dateFormatRange).setNumberFormat("yyyy-mm-dd");
    sheet.getRange("A:A").format.columnWidth = 12;
    sheet.getRange(`B:${colLetter(headerCols - 1)}`).format.columnWidth = 13;
  });
  return sheet;
}

const control = workbook.worksheets.add("00_每日操作台");
styleSheetBase(control);
styleTitle(control, "AI投研系统 Wind 数据模板", "客户每日只需要维护前几张“客户填”表，Wind刷新后保存，系统会读取固定数据区生成日报。");
const controlRows = [
  ["区域", "当前状态", "客户动作", "备注"],
  ["模板版本", "v1.1 客户交付版", "不用改", "前台维护区和后台数据区已分开"],
  ["每日流程 1", "打开本Excel并确认Wind已登录", "Wind -> 刷新数据", "刷新完成后保存文件"],
  ["每日流程 2", "检查 07_每日数据校验", "只处理非OK项", "样本期ETF数量低于30是正常提示"],
  ["每日流程 3", "打开AI投研系统前端", "点击 Refresh Data", "系统重新跑ETF/TL/转债逻辑并导出日报"],
  ["ETF代码池", "客户维护", "新增/删除ETF代码", "生产建议30-50只，enabled=Y才纳入分析"],
  ["ETF持仓", "客户维护", "更新holding/closed", "这是客户账户持仓，不是ETF成分股权重"],
  ["TL配置", "客户确认", "确认TL代码与频率", "第一版日频；60分钟等分钟数据到位后扩展"],
  ["可转债池", "客户维护", "填写转债代码", "系统按140元以下和打分权重排序"],
  ["策略参数", "一般不改", "需要调阈值时再改", "权重合计必须为100%"],
  ["系统数据区", "不要手工改结构", "只允许Wind刷新/覆盖数值", "第1行名称、第2行代码、第3行字段名必须保留"],
];
writeMatrix(control, controlRows, 4, 0);
styleTable(control, "A5:D15");
setWidths(control, { A: 22, B: 36, C: 32, D: 64 });
safeFormat(() => {
  control.freezePanes.freezeRows(5);
  control.getRange("C7:C15").format.font.color = colors.blue;
  control.getRange("C7:C15").format.fill.color = colors.input;
});

const guide = workbook.worksheets.add("01_维护说明");
styleSheetBase(guide);
styleTitle(guide, "维护说明", "这张表是给客户和实施同事看的维护边界。客户只改蓝字/黄色输入区。");
const guideRows = [
  ["类型", "Sheet", "客户是否需要维护", "维护方法", "不要做什么"],
  ["每日必看", "00_每日操作台", "看", "按流程操作", "不要改流程文字"],
  ["客户输入", "02_客户填_ETF代码池", "需要", "填写ETF代码、名称、分类，enabled=Y表示纳入分析", "不要把ETF成分股填到这里"],
  ["客户输入", "03_客户填_ETF持仓", "需要", "客户账户持仓填holding，已平仓填closed", "不要把holding理解为ETF内部权重"],
  ["客户输入", "04_客户填_TL配置", "首次确认，后续少改", "确认TL代码、日频/60分钟频率", "没有60分钟数据前不要启用60m"],
  ["客户输入", "05_客户填_可转债池", "需要", "填写转债代码、正股代码、价格上限", "不要把超过140元的转债强行纳入低估池"],
  ["客户输入", "06_客户可调_策略参数", "通常不改", "只在策略复盘后调整阈值或权重", "不要让权重合计不等于100%"],
  ["每日校验", "07_每日数据校验", "看", "刷新后确认关键项OK", "不要忽略非OK项"],
  ["实施说明", "08_Wind刷新说明", "首次配置看", "用Wind向导把数据落到后面系统区", "不要改系统区前三行结构"],
  ["系统区", "10/11/12_Wind数据", "不手工维护", "Wind刷新或覆盖数值", "不要插入空行、合并单元格、改字段名"],
];
writeMatrix(guide, guideRows, 4, 0);
styleTable(guide, "A5:E15");
setWidths(guide, { A: 14, B: 26, C: 18, D: 56, E: 56 });
safeFormat(() => {
  guide.getRange("D6:D15").format.font.color = colors.blue;
});

const etfPool = workbook.worksheets.add("02_客户填_ETF代码池");
styleSheetBase(etfPool);
styleTitle(etfPool, "ETF代码池", "客户维护30-50只ETF。系统只分析 enabled=Y 的标的；空行可保留。");
const etfHeaders = ["enabled", "asset_type", "code", "name", "category", "risk_bucket", "benchmark", "data_start", "notes"];
const etfRows = seed.etf_universe.map((row) => [
  row.enabled,
  row.asset_type,
  row.code,
  row.name,
  "",
  "中",
  "",
  new Date("2025-01-01T00:00:00"),
  "当前样本",
]);
while (etfRows.length < 80) etfRows.push(["", "ETF", "", "", "", "中", "", "", ""]);
writeMatrix(etfPool, [etfHeaders, ...etfRows], 4, 0);
styleTable(etfPool, "A5:I85");
setWidths(etfPool, { A: 10, B: 12, C: 16, D: 18, E: 16, F: 12, G: 18, H: 14, I: 36 });
safeFormat(() => {
  etfPool.freezePanes.freezeRows(5);
  etfPool.getRange("A6:I85").format.fill.color = "#FFFFFF";
  etfPool.getRange("A6:H85").format.font.color = colors.blue;
  etfPool.getRange("H6:H85").setNumberFormat("yyyy-mm-dd");
});
applyValidation(etfPool, "A6:A85", ["Y", "N"]);
applyValidation(etfPool, "F6:F85", ["低", "中", "高"]);

const position = workbook.worksheets.add("03_客户填_ETF持仓");
styleSheetBase(position);
styleTitle(position, "ETF持仓表", "客户账户持仓状态表。holding进入平仓提示路径，closed/空仓重新进入建仓筛选。");
const posHeaders = ["asset_type", "code", "name", "status", "entry_date", "entry_price", "quantity", "cost_amount", "last_update", "notes"];
const posRows = [
  ["ETF", "510880.SH", "红利ETF", "holding", new Date("2026-05-20T00:00:00"), 3.25, 100000, 325000, new Date("2026-06-17T00:00:00"), "样例持仓：用于测试平仓提示"],
  ["ETF", "512760.SH", "芯片", "closed", new Date("2026-05-18T00:00:00"), 1.2, 0, 0, new Date("2026-06-17T00:00:00"), "样例已平仓：重新进入建仓池"],
];
while (posRows.length < 80) posRows.push(["ETF", "", "", "", "", "", "", "", "", ""]);
writeMatrix(position, [posHeaders, ...posRows], 4, 0);
styleTable(position, "A5:J85");
setWidths(position, { A: 12, B: 16, C: 18, D: 14, E: 14, F: 14, G: 14, H: 16, I: 14, J: 44 });
safeFormat(() => {
  position.freezePanes.freezeRows(5);
  position.getRange("A6:J85").format.fill.color = "#FFFFFF";
  position.getRange("B6:I85").format.font.color = colors.blue;
  position.getRange("E6:E85").setNumberFormat("yyyy-mm-dd");
  position.getRange("I6:I85").setNumberFormat("yyyy-mm-dd");
  position.getRange("F6:H85").setNumberFormat("#,##0.00");
});
applyValidation(position, "D6:D85", ["holding", "closed", "watch", ""]);

const tlConfig = workbook.worksheets.add("04_客户填_TL配置");
styleSheetBase(tlConfig);
styleTitle(tlConfig, "TL配置", "30年国债期货TL第一版使用日频；60分钟频率等客户提供Wind分钟数据后扩展。");
const tlRows = [
  ["enabled", "asset_type", "code", "name", "frequency", "contract_policy", "start_date", "notes"],
  ["Y", "TL", "TL.CFE", "30年国债期货TL", "daily", "主力/连续合约由客户确认", new Date("2025-01-01T00:00:00"), "第一版不做平仓提示，只输出不做交易/关注交易/建议建仓"],
  ["N", "TL", "", "备用60分钟数据", "60m", "后续扩展", "", "需要Wind能导出60分钟OHLCV"],
];
writeMatrix(tlConfig, tlRows, 4, 0);
styleTable(tlConfig, "A5:H7");
setWidths(tlConfig, { A: 10, B: 12, C: 16, D: 22, E: 14, F: 32, G: 14, H: 72 });
safeFormat(() => {
  tlConfig.getRange("A6:H7").format.font.color = colors.blue;
  tlConfig.getRange("G6:G7").setNumberFormat("yyyy-mm-dd");
});
applyValidation(tlConfig, "A6:A20", ["Y", "N"]);
applyValidation(tlConfig, "E6:E20", ["daily", "60m"]);

const cbPool = workbook.worksheets.add("05_客户填_可转债池");
styleSheetBase(cbPool);
styleTitle(cbPool, "可转债代码池", "用于140元以下低估/性价比排序。客户维护代码池，Wind刷新估值和正股字段。");
const cbHeaders = ["enabled", "bond_code", "bond_name", "stock_code", "stock_name", "max_price", "include", "notes"];
const cbRows = [];
for (let i = 0; i < 120; i++) cbRows.push(["", "", "", "", "", 140, "Y", ""]);
writeMatrix(cbPool, [cbHeaders, ...cbRows], 4, 0);
styleTable(cbPool, "A5:H125");
setWidths(cbPool, { A: 10, B: 16, C: 18, D: 16, E: 18, F: 12, G: 10, H: 44 });
safeFormat(() => {
  cbPool.freezePanes.freezeRows(5);
  cbPool.getRange("A6:H125").format.font.color = colors.blue;
  cbPool.getRange("F6:F125").setNumberFormat("#,##0.00");
});
applyValidation(cbPool, "A6:A125", ["Y", "N", ""]);
applyValidation(cbPool, "G6:G125", ["Y", "N"]);

const params = workbook.worksheets.add("06_客户可调_策略参数");
styleSheetBase(params);
styleTitle(params, "策略参数", "蓝字为可调参数。建议客户平时不要改，只有复盘确认后再调整。");
const paramRows = [
  ["module", "parameter", "value", "unit", "editable", "notes"],
  ["ETF", "buy_volume_ratio_min", 1.1, "倍", "Y", "建仓候选要求成交量达到前60日均量倍数"],
  ["ETF", "sell_ma10_volume_ratio_min", 1.2, "倍", "Y", "收盘价低于MA10时的放量阈值"],
  ["ETF", "sell_ma5_volume_ratio_min", 1.5, "倍", "Y", "收盘价低于MA5时的放量阈值"],
  ["ETF", "score_weight_trend", 0.35, "%", "Y", "ETF技术评分趋势权重"],
  ["ETF", "score_weight_macd", 0.25, "%", "Y", "ETF技术评分MACD权重"],
  ["ETF", "score_weight_volume", 0.25, "%", "Y", "ETF技术评分量能权重"],
  ["ETF", "score_weight_share_change", 0.15, "%", "Y", "ETF技术评分份额变化权重"],
  ["TL", "daily_kdj_lookback", 3, "日", "Y", "日线T-3至T-1查找J<5低点"],
  ["TL", "daily_j_low_threshold", 5, "J值", "Y", "日线低位阈值"],
  ["TL", "weekly_kdj_lookback", 2, "周", "Y", "周线T-2内查找J<20低点"],
  ["TL", "weekly_j_low_threshold", 20, "J值", "Y", "周线低位阈值"],
  ["TL", "weekly_no_trade_hard_veto", "TRUE", "布尔", "Y", "周线不做交易条件是否覆盖日线建仓倾向"],
  ["CB", "weight_profit_growth", 0.3, "%", "Y", "正股扣非净利润增长率权重"],
  ["CB", "weight_remaining_years", 0.3, "%", "Y", "剩余期限权重"],
  ["CB", "weight_conversion_premium", 0.3, "%", "Y", "转股溢价率权重；越低越好"],
  ["CB", "weight_ytm", 0.1, "%", "Y", "到期收益率权重；负值扣分"],
];
writeMatrix(params, paramRows, 4, 0);
styleTable(params, "A5:F21");
setWidths(params, { A: 12, B: 30, C: 14, D: 10, E: 10, F: 70 });
safeFormat(() => {
  params.getRange("C6:C21").format.font.color = colors.blue;
  params.getRange("C9:C12").setNumberFormat("0.0%");
  params.getRange("C18:C21").setNumberFormat("0.0%");
});
applyValidation(params, "E6:E21", ["Y", "N"]);

const checks = workbook.worksheets.add("07_每日数据校验");
styleSheetBase(checks);
styleTitle(checks, "每日数据校验", "刷新Wind后先看这里。除样本期ETF数量提示外，生产环境建议全部OK再跑日报。");
const checkRows = [
  ["检查项", "实际值/公式", "标准", "状态/说明"],
  ["ETF启用数量", null, "生产30-50只；当前样本可低于30", null],
  ["ETF持仓holding数量", null, "按客户真实账户填写", "仅用于平仓提示路径"],
  ["可转债启用数量", null, "生产按客户转债池填写", "未接入前可为空"],
  ["ETF行情字段", "开盘价、收盘价、最低价、最高价、成交量（万股）、成交额(亿元）、份额变化（亿份）", "必须完整", "OK"],
  ["TL行情字段", "开盘价、收盘价、最低价、最高价、成交量、成交额(亿元）、持仓量、持仓量变化", "必须完整", "OK"],
  ["ETF持仓状态", "holding / closed / watch / 空", "仅使用下拉值", "OK"],
  ["ETF评分权重合计", null, "100%", null],
  ["可转债评分权重合计", null, "100%", null],
  ["TL收盘确认", "MACD柱长短必须等T日收盘后确定", "T日收盘后运行", "OK"],
  ["系统读取约束", "固定sheet名 + 固定前三行结构", "不可改", "OK"],
];
writeMatrix(checks, checkRows, 4, 0);
checks.getRange("B6").formulas = [["=COUNTIF('02_客户填_ETF代码池'!A6:A85,\"Y\")"]];
checks.getRange("D6").formulas = [["=IF(B6>=30,\"OK\",\"样本/试运行可用；生产前扩到30-50只\")"]];
checks.getRange("B7").formulas = [["=COUNTIF('03_客户填_ETF持仓'!D6:D85,\"holding\")"]];
checks.getRange("B8").formulas = [["=COUNTIFS('05_客户填_可转债池'!A6:A125,\"Y\",'05_客户填_可转债池'!G6:G125,\"Y\")"]];
checks.getRange("B12").formulas = [["=SUM('06_客户可调_策略参数'!C9:C12)"]];
checks.getRange("D12").formulas = [["=IF(ABS(B12-1)<0.0001,\"OK\",\"请检查ETF评分权重\")"]];
checks.getRange("B13").formulas = [["=SUM('06_客户可调_策略参数'!C18:C21)"]];
checks.getRange("D13").formulas = [["=IF(ABS(B13-1)<0.0001,\"OK\",\"请检查可转债评分权重\")"]];
styleTable(checks, "A5:D15");
setWidths(checks, { A: 24, B: 78, C: 30, D: 52 });
safeFormat(() => {
  checks.getRange("B12:B13").setNumberFormat("0.0%");
  checks.getRange("D6:D15").format.font.bold = true;
});

const formulaSheet = workbook.worksheets.add("08_Wind刷新说明");
styleSheetBase(formulaSheet);
styleTitle(formulaSheet, "Wind刷新说明", "实施时用Wind插件/向导把行情落到后面三张Wind数据表。公式以客户Wind终端实际插入为准。");
const formulaRows = [
  ["模块", "客户动作", "建议字段", "落表位置", "关键要求"],
  ["ETF日频", "Wind -> 时间序列 -> 批量代码刷新", "open,close,low,high,volume,amt,unit_total", "10_Wind_ETF日频数据", "第1行名称，第2行代码，第3行字段名，第4行开始日期；字段名需映射为中文标准名。"],
  ["TL日频", "Wind -> 时间序列 -> TL.CFE", "open,close,low,high,volume,amt,oi,oi_chg", "11_Wind_TL日频数据", "第一版日频；60分钟数据单独扩展，不混在日频表。"],
  ["可转债", "Wind -> 多维数据/条件选股后粘贴", "close,remaining_years,conversion_premium,ytm,deducted_profit_growth", "12_Wind_可转债数据", "用于140元以下和性价比排序，字段缺失则该模块不出正式排名。"],
  ["刷新后", "保存Excel", "不改Sheet名、不改前三行结构", "整本工作簿", "系统前端点击 Refresh Data 后重新跑日报。"],
  ["公式示例", "仅供实施参考", "'=WSD(\"510300.SH\",\"open,close,low,high,volume,amt\",\"2021-01-01\",\"2026-06-17\",\"\")", "对应Wind表", "不同Wind账号字段可能不同，最终以终端插入公式为准。"],
];
writeMatrix(formulaSheet, formulaRows, 4, 0);
styleTable(formulaSheet, "A5:E10");
setWidths(formulaSheet, { A: 14, B: 34, C: 58, D: 24, E: 80 });
safeFormat(() => {
  formulaSheet.getRange("B6:B10").format.font.color = colors.blue;
  formulaSheet.getRange("C10").format.font.name = "Consolas";
  formulaSheet.getRange("C10").format.font.color = colors.green;
});

const dictionary = workbook.worksheets.add("09_字段字典");
styleSheetBase(dictionary);
styleTitle(dictionary, "字段字典", "系统读取字段口径，字段名保持一致即可。");
const dictRows = [
  ["sheet", "字段", "含义", "是否必需", "备注"],
  ["10_Wind_ETF日频数据", "开盘价", "ETF日开盘价", "Y", "用于过滤异常非交易行"],
  ["10_Wind_ETF日频数据", "收盘价", "ETF日收盘价", "Y", "用于MA/MACD/KDJ"],
  ["10_Wind_ETF日频数据", "最低价", "ETF日最低价", "Y", "用于KDJ"],
  ["10_Wind_ETF日频数据", "最高价", "ETF日最高价", "Y", "用于KDJ"],
  ["10_Wind_ETF日频数据", "成交量（万股）", "ETF成交量", "Y", "用于前60日均量倍数"],
  ["10_Wind_ETF日频数据", "成交额(亿元）", "ETF成交额", "N", "报告展示/扩展"],
  ["10_Wind_ETF日频数据", "份额变化（亿份）", "ETF份额变化", "N", "用于ETF评分增强项"],
  ["11_Wind_TL日频数据", "成交量", "TL成交量", "Y", "过滤有效交易行"],
  ["11_Wind_TL日频数据", "持仓量", "TL持仓量", "N", "报告展示/扩展"],
  ["12_Wind_可转债数据", "conversion_premium", "转股溢价率", "Y", "越低评分越高"],
  ["12_Wind_可转债数据", "ytm", "到期收益率", "Y", "为负则扣分"],
  ["12_Wind_可转债数据", "deducted_profit_growth", "正股扣非净利润增长率", "Y", "越高评分越高"],
];
writeMatrix(dictionary, dictRows, 4, 0);
styleTable(dictionary, "A5:E17");
setWidths(dictionary, { A: 26, B: 24, C: 36, D: 12, E: 58 });

const etfRaw = makeRawSheet("10_Wind_ETF日频数据", seed.etf_matrix, `A4:A${seed.etf_matrix.length}`, seed.etf_matrix[0].length);
const tlRaw = makeRawSheet("11_Wind_TL日频数据", seed.tl_matrix, `A4:A${seed.tl_matrix.length}`, seed.tl_matrix[0].length);

const cbData = workbook.worksheets.add("12_Wind_可转债数据");
styleSheetBase(cbData);
styleTitle(cbData, "Wind可转债数据", "可转债字段区。第一版可为空；接入可转债Agent时按这些字段读取和打分。");
const cbDataRows = [
  ["date", "bond_code", "bond_name", "close_price", "remaining_years", "conversion_premium", "ytm", "stock_code", "stock_name", "deducted_profit_growth", "notes"],
];
for (let i = 0; i < 300; i++) cbDataRows.push(["", "", "", "", "", "", "", "", "", "", ""]);
writeMatrix(cbData, cbDataRows, 4, 0);
styleTable(cbData, "A5:K305");
setWidths(cbData, { A: 14, B: 16, C: 18, D: 14, E: 16, F: 18, G: 12, H: 16, I: 18, J: 24, K: 36 });
safeFormat(() => {
  cbData.freezePanes.freezeRows(5);
  cbData.getRange("A6:A305").setNumberFormat("yyyy-mm-dd");
  cbData.getRange("D6:G305").setNumberFormat("0.00");
  cbData.getRange("J6:J305").setNumberFormat("0.0%");
});

const source = workbook.worksheets.add("13_源文件记录");
styleSheetBase(source);
styleTitle(source, "源文件记录", "记录本模板生成时使用的样本来源，方便审计。");
const sourceRows = [
  ["类型", "路径", "说明"],
  ["ETF样本", seed.source_files.etf, "客户提供的Wind导出ETF数据"],
  ["TL样本", seed.source_files.tl, "客户提供的Wind导出TL数据"],
  ["模板说明", "AI投研系统第一版数据模板", "本模板是数据入口，不承诺策略收益，策略有效性需回测和实盘跟踪验证。"],
];
writeMatrix(source, sourceRows, 4, 0);
styleTable(source, "A5:C8");
setWidths(source, { A: 16, B: 92, C: 70 });

// Light raw sheet cleanup after adding user-facing tabs.
safeFormat(() => {
  etfRaw.getRange("A1:A3").format.fill.color = colors.header;
  tlRaw.getRange("A1:A3").format.fill.color = colors.header;
});

await fs.mkdir(outputDir, { recursive: true });

// Compact workbook inspection and render verification.
const check = await workbook.inspect({
  kind: "table",
  range: "07_每日数据校验!A5:D15",
  include: "values,formulas",
  tableMaxRows: 14,
  tableMaxCols: 6,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

for (const [sheetName, range] of [
  ["00_每日操作台", "A1:D15"],
  ["01_维护说明", "A1:E15"],
  ["02_客户填_ETF代码池", "A1:I18"],
  ["03_客户填_ETF持仓", "A1:J15"],
  ["04_客户填_TL配置", "A1:H8"],
  ["05_客户填_可转债池", "A1:H18"],
  ["06_客户可调_策略参数", "A1:F21"],
  ["07_每日数据校验", "A1:D15"],
  ["08_Wind刷新说明", "A1:E10"],
  ["09_字段字典", "A1:E17"],
  ["10_Wind_ETF日频数据", "A1:M12"],
  ["11_Wind_TL日频数据", "A1:K12"],
]) {
  const blob = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  await fs.writeFile(path.join(outputDir, `${sheetName.replaceAll("/", "_")}.png`), bytes);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
