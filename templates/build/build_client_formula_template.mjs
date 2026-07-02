import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const buildDir = path.resolve(".");
const seed = JSON.parse(await fs.readFile(path.join(buildDir, "seed_data.json"), "utf8"));
const outputDir = path.join(buildDir, "output");
const outputPath = path.join(outputDir, "Wind公式填报模板-AI投研系统-客户版.xlsx");

const workbook = Workbook.create();

const colors = {
  ink: "#17202A",
  blue: "#1D4ED8",
  green: "#15803D",
  red: "#B91C1C",
  panel: "#E7F5F2",
  header: "#DDE8F0",
  input: "#FFF2CC",
  line: "#D5DEE7",
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

function safeFormat(fn) {
  try {
    fn();
  } catch (err) {
    console.warn(`format skipped: ${err.message}`);
  }
}

function base(sheet) {
  safeFormat(() => {
    sheet.showGridLines = false;
  });
}

function title(sheet, main, sub) {
  sheet.getRange("A1").values = [[main]];
  sheet.getRange("A2").values = [[sub]];
  safeFormat(() => {
    sheet.getRange("A1:H1").format.fill.color = colors.panel;
    sheet.getRange("A2:H2").format.fill.color = colors.panel;
    sheet.getRange("A1").format.font.bold = true;
    sheet.getRange("A1").format.font.size = 16;
    sheet.getRange("A1:H2").format.borders = { preset: "outside", style: "thin", color: colors.line };
  });
}

function table(sheet, address, headerRows = 1) {
  safeFormat(() => {
    const range = sheet.getRange(address);
    range.format.borders = { preset: "all", style: "thin", color: colors.line };
    range.format.font.size = 10;
    range.format.wrapText = true;
    const [start, end] = address.split(":");
    const startMatch = start.match(/([A-Z]+)(\d+)/);
    const endMatch = end.match(/([A-Z]+)(\d+)/);
    if (startMatch && endMatch) {
      const startRow = Number(startMatch[2]);
      const headerRange = sheet.getRange(`${startMatch[1]}${startRow}:${endMatch[1]}${startRow + headerRows - 1}`);
      headerRange.format.fill.color = colors.header;
      headerRange.format.font.bold = true;
    }
  });
}

function widths(sheet, map) {
  safeFormat(() => {
    for (const [col, width] of Object.entries(map)) {
      sheet.getRange(`${col}:${col}`).format.columnWidth = width;
    }
  });
}

function validation(sheet, range, values) {
  safeFormat(() => {
    sheet.getRange(range).dataValidation = { rule: { type: "list", values } };
  });
}

const home = workbook.worksheets.add("00_每日操作台");
base(home);
title(home, "AI投研系统 Wind公式填报模板", "客户按本模板插入/刷新Wind公式；系统读取后自动生成ETF、TL、可转债日报。");
writeMatrix(
  home,
  [
    ["步骤", "客户要做什么", "在哪张表做", "完成标准"],
    ["1", "维护ETF代码池、客户持仓、TL配置、可转债池", "02-05 客户填表", "蓝字/黄色区域填写完"],
    ["2", "用Wind插件把公式放到指定数据区", "10/11/12 Wind公式区", "第4行开始有日期和行情数值"],
    ["3", "点Wind刷新数据并保存Excel", "Wind选项卡", "最新日期更新到昨天或最新收盘日"],
    ["4", "检查数据校验", "07_数据校验", "除样本数量提示外，关键项OK"],
    ["5", "打开AI投研系统前端，点击Refresh Data", "系统前端", "生成日报Excel/PDF"],
    [null, null, null, null],
    ["重要提醒", "说明", "原因", "是否可改"],
    ["不要改系统区前三行", "第1行名称、第2行代码、第3行字段名", "系统按这个结构读取", "不可改"],
    ["不要把ETF成分股填成持仓", "持仓是客户账户持有的ETF", "决定是否触发平仓提示", "不可混淆"],
    ["MACD/KDJ不用写Excel公式", "系统代码统一计算", "避免公式漂移", "不可改"],
    ["Wind公式可以由客户现有模板迁移", "只要落到指定sheet和字段", "兼容实际Wind权限", "可迁移"],
  ],
  4,
  0,
);
table(home, "A5:D16");
widths(home, { A: 16, B: 46, C: 30, D: 52 });
safeFormat(() => {
  home.getRange("B6:C10").format.fill.color = colors.input;
  home.getRange("B6:C10").format.font.color = colors.blue;
});

const guide = workbook.worksheets.add("01_填写说明");
base(guide);
title(guide, "填写说明", "客户只维护前台输入表和Wind公式区；系统参数和字段名尽量不要改。");
writeMatrix(
  guide,
  [
    ["Sheet", "客户动作", "维护频率", "说明"],
    ["02_ETF代码池", "填ETF代码、名称、分类、enabled", "首次配置/调整池子", "生产建议30-50只；enabled=Y才参与筛选。"],
    ["03_ETF持仓", "填客户账户持有ETF", "有交易后更新", "holding进入平仓提示；closed重新进入建仓筛选。"],
    ["04_TL配置", "确认TL代码和频率", "首次配置", "第一版日频；60分钟等分钟数据确认后再启用。"],
    ["05_可转债池", "填转债代码、正股代码、价格上限", "首次配置/调整池子", "系统输出140元以下性价比排名。"],
    ["06_策略参数", "一般不动；复盘后才调", "低频", "ETF/转债权重合计必须为100%。"],
    ["10_Wind_ETF日频", "放ETF日频Wind公式", "每日刷新", "第4行开始是日期和行情，字段名保持中文标准名。"],
    ["11_Wind_TL日频", "放TL日频Wind公式", "每日刷新", "第4行开始是日期和行情。"],
    ["12_Wind_可转债", "放可转债估值/正股字段", "每日刷新", "字段按表头填写或用Wind公式填充。"],
  ],
  4,
  0,
);
table(guide, "A5:D13");
widths(guide, { A: 24, B: 42, C: 20, D: 68 });

const etfPool = workbook.worksheets.add("02_ETF代码池");
base(etfPool);
title(etfPool, "ETF代码池", "客户维护30-50只ETF。后面的ETF Wind公式区会自动引用这里的代码和名称。");
const etfHeaders = ["enabled", "code", "name", "category", "risk_bucket", "benchmark", "data_start", "notes"];
const etfRows = seed.etf_universe.map((row) => [
  row.enabled,
  row.code,
  row.name,
  "",
  "中",
  "",
  new Date("2021-01-01T00:00:00"),
  "样例代码，可替换/扩充",
]);
while (etfRows.length < 50) etfRows.push(["", "", "", "", "中", "", "", ""]);
writeMatrix(etfPool, [etfHeaders, ...etfRows], 4, 0);
table(etfPool, "A5:H55");
widths(etfPool, { A: 10, B: 16, C: 18, D: 18, E: 12, F: 18, G: 14, H: 38 });
safeFormat(() => {
  etfPool.freezePanes.freezeRows(5);
  etfPool.getRange("A6:H55").format.font.color = colors.blue;
  etfPool.getRange("A6:H55").format.fill.color = colors.input;
  etfPool.getRange("G6:G55").setNumberFormat("yyyy-mm-dd");
});
validation(etfPool, "A6:A55", ["Y", "N", ""]);
validation(etfPool, "E6:E55", ["低", "中", "高"]);

const positions = workbook.worksheets.add("03_ETF持仓");
base(positions);
title(positions, "ETF持仓", "这里填客户账户当前持仓状态，不是ETF成分股。");
const posHeaders = ["code", "name", "status", "entry_date", "entry_price", "quantity", "cost_amount", "last_update", "notes"];
const posRows = [
  ["510880.SH", "红利ETF", "holding", new Date("2026-05-20T00:00:00"), 3.25, 100000, 325000, new Date("2026-06-17T00:00:00"), "示例，可替换"],
  ["512760.SH", "芯片", "closed", new Date("2026-05-18T00:00:00"), 1.2, 0, 0, new Date("2026-06-17T00:00:00"), "示例，可替换"],
];
while (posRows.length < 80) posRows.push(["", "", "", "", "", "", "", "", ""]);
writeMatrix(positions, [posHeaders, ...posRows], 4, 0);
table(positions, "A5:I85");
widths(positions, { A: 16, B: 18, C: 14, D: 14, E: 14, F: 14, G: 16, H: 14, I: 44 });
safeFormat(() => {
  positions.freezePanes.freezeRows(5);
  positions.getRange("A6:I85").format.font.color = colors.blue;
  positions.getRange("A6:I85").format.fill.color = colors.input;
  positions.getRange("D6:D85").setNumberFormat("yyyy-mm-dd");
  positions.getRange("H6:H85").setNumberFormat("yyyy-mm-dd");
  positions.getRange("E6:G85").setNumberFormat("#,##0.00");
});
validation(positions, "C6:C85", ["holding", "closed", "watch", ""]);

const tl = workbook.worksheets.add("04_TL配置");
base(tl);
title(tl, "TL配置", "确认30年国债期货TL代码和频率。第一版建议使用日频。");
writeMatrix(
  tl,
  [
    ["enabled", "code", "name", "frequency", "contract_policy", "start_date", "notes"],
    ["Y", "TL.CFE", "30年国债期货TL", "daily", "主力/连续合约由客户确认", new Date("2021-01-01T00:00:00"), "第一版日频；不做平仓提示"],
    ["N", "", "备用60分钟数据", "60m", "后续扩展", "", "需要Wind能导出60分钟OHLCV"],
  ],
  4,
  0,
);
table(tl, "A5:G7");
widths(tl, { A: 10, B: 16, C: 24, D: 14, E: 34, F: 14, G: 70 });
safeFormat(() => {
  tl.getRange("A6:G7").format.font.color = colors.blue;
  tl.getRange("A6:G7").format.fill.color = colors.input;
  tl.getRange("F6:F7").setNumberFormat("yyyy-mm-dd");
});
validation(tl, "A6:A20", ["Y", "N"]);
validation(tl, "D6:D20", ["daily", "60m"]);

const cbPool = workbook.worksheets.add("05_可转债池");
base(cbPool);
title(cbPool, "可转债池", "客户维护可转债池；系统后续输出140元以下性价比最高的10只。");
writeMatrix(cbPool, [["enabled", "bond_code", "bond_name", "stock_code", "stock_name", "max_price", "include", "notes"]], 4, 0);
const cbRows = Array.from({ length: 120 }, () => ["", "", "", "", "", 140, "Y", ""]);
writeMatrix(cbPool, cbRows, 5, 0);
table(cbPool, "A5:H125");
widths(cbPool, { A: 10, B: 16, C: 18, D: 16, E: 18, F: 12, G: 10, H: 44 });
safeFormat(() => {
  cbPool.freezePanes.freezeRows(5);
  cbPool.getRange("A6:H125").format.font.color = colors.blue;
  cbPool.getRange("A6:H125").format.fill.color = colors.input;
  cbPool.getRange("F6:F125").setNumberFormat("#,##0.00");
});
validation(cbPool, "A6:A125", ["Y", "N", ""]);
validation(cbPool, "G6:G125", ["Y", "N"]);

const params = workbook.worksheets.add("06_策略参数");
base(params);
title(params, "策略参数", "客户平时不需要改。调整前建议先回测/复盘。");
const paramRows = [
  ["module", "parameter", "value", "unit", "editable", "notes"],
  ["ETF", "buy_volume_ratio_min", 1.1, "倍", "Y", "建仓候选要求成交量达到前60日均量倍数"],
  ["ETF", "sell_ma10_volume_ratio_min", 1.2, "倍", "Y", "收盘价低于MA10时的放量阈值"],
  ["ETF", "sell_ma5_volume_ratio_min", 1.5, "倍", "Y", "收盘价低于MA5时的放量阈值"],
  ["ETF", "score_weight_trend", 0.35, "%", "Y", "ETF评分趋势权重"],
  ["ETF", "score_weight_macd", 0.25, "%", "Y", "ETF评分MACD权重"],
  ["ETF", "score_weight_volume", 0.25, "%", "Y", "ETF评分量能权重"],
  ["ETF", "score_weight_share_change", 0.15, "%", "Y", "ETF评分份额变化权重"],
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
table(params, "A5:F21");
widths(params, { A: 12, B: 30, C: 14, D: 10, E: 10, F: 74 });
safeFormat(() => {
  params.getRange("C6:C21").format.font.color = colors.blue;
  params.getRange("C6:C21").format.fill.color = colors.input;
  params.getRange("C9:C12").setNumberFormat("0.0%");
  params.getRange("C18:C21").setNumberFormat("0.0%");
});
validation(params, "E6:E21", ["Y", "N"]);

const qa = workbook.worksheets.add("07_数据校验");
base(qa);
title(qa, "数据校验", "Wind公式放好并刷新后，先看这里再跑系统。");
writeMatrix(
  qa,
  [
    ["检查项", "实际值/公式", "标准", "状态"],
    ["ETF启用数量", null, "生产30-50只", null],
    ["ETF持仓holding数量", null, "按客户真实账户填写", "用于平仓提示"],
    ["ETF日频公式区首行日期", null, "A4有日期，说明Wind公式已开始落表", null],
    ["TL日频公式区首行日期", null, "A4有日期，说明Wind公式已开始落表", null],
    ["可转债池启用数量", null, "按客户转债池填写", "未接入前可为空"],
    ["ETF评分权重合计", null, "100%", null],
    ["可转债评分权重合计", null, "100%", null],
    ["系统结构", "10/11/12表前三行保留", "不可改", "OK"],
  ],
  4,
  0,
);
qa.getRange("B6").formulas = [["=COUNTIF('02_ETF代码池'!A6:A55,\"Y\")"]];
qa.getRange("D6").formulas = [["=IF(B6>=30,\"OK\",\"生产前请扩到30-50只\")"]];
qa.getRange("B7").formulas = [["=COUNTIF('03_ETF持仓'!C6:C85,\"holding\")"]];
qa.getRange("B10").formulas = [["=COUNTIFS('05_可转债池'!A6:A125,\"Y\",'05_可转债池'!G6:G125,\"Y\")"]];
qa.getRange("B11").formulas = [["=SUM('06_策略参数'!C9:C12)"]];
qa.getRange("D11").formulas = [["=IF(ABS(B11-1)<0.0001,\"OK\",\"请检查ETF评分权重\")"]];
qa.getRange("B12").formulas = [["=SUM('06_策略参数'!C18:C21)"]];
qa.getRange("D12").formulas = [["=IF(ABS(B12-1)<0.0001,\"OK\",\"请检查可转债评分权重\")"]];
table(qa, "A5:D13");
widths(qa, { A: 26, B: 28, C: 42, D: 44 });
safeFormat(() => {
  qa.getRange("B11:B12").setNumberFormat("0.0%");
  qa.getRange("D6:D13").format.font.bold = true;
});

const windGuide = workbook.worksheets.add("08_Wind公式指南");
base(windGuide);
title(windGuide, "Wind公式指南", "客户用Wind向导或现有公式，把结果落到10/11/12三张表。");
writeMatrix(
  windGuide,
  [
    ["数据区", "公式放置位置", "固定表头", "建议字段", "说明"],
    ["ETF日频", "10_Wind_ETF日频：A4开始日期，B4开始第1只ETF数据", "第1行名称、第2行代码、第3行字段", "开盘价/收盘价/最低价/最高价/成交量（万股）/成交额(亿元）/份额变化（亿份）", "ETF代码和名称已从02表自动带出；客户只需要用Wind填第4行以下数据。"],
    ["TL日频", "11_Wind_TL日频：A4开始日期，B4开始TL数据", "第1行名称、第2行代码、第3行字段", "开盘价/收盘价/最低价/最高价/成交量/成交额(亿元）/持仓量/持仓量变化", "第一版只用日频；60分钟后续单独加表。"],
    ["可转债", "12_Wind_可转债：第6行开始", "第5行为字段名", "价格/剩余期限/转股溢价率/到期收益率/正股扣非净利润增长率", "可以用Wind公式，也可以从Wind导出后粘贴值。"],
    ["公式示例", "仅供实施参考", "以客户Wind插件实际插入为准", "'=WSD(\"510300.SH\",\"open,close,low,high,volume,amt\",\"2021-01-01\",\"2026-06-17\",\"\")", "不要强行照抄字段名，Wind账号字段权限可能不同。"],
  ],
  4,
  0,
);
table(windGuide, "A5:E9");
widths(windGuide, { A: 14, B: 46, C: 36, D: 78, E: 72 });
safeFormat(() => {
  windGuide.getRange("B6:B9").format.fill.color = colors.input;
  windGuide.getRange("B6:B9").format.font.color = colors.blue;
});

const dict = workbook.worksheets.add("09_字段字典");
base(dict);
title(dict, "字段字典", "系统读取字段口径。字段名不要随意改。");
writeMatrix(
  dict,
  [
    ["sheet", "字段", "含义", "必需", "备注"],
    ["10_Wind_ETF日频", "开盘价", "ETF日开盘价", "Y", "过滤异常行/指标计算"],
    ["10_Wind_ETF日频", "收盘价", "ETF日收盘价", "Y", "MA/MACD/KDJ"],
    ["10_Wind_ETF日频", "最低价", "ETF日最低价", "Y", "KDJ"],
    ["10_Wind_ETF日频", "最高价", "ETF日最高价", "Y", "KDJ"],
    ["10_Wind_ETF日频", "成交量（万股）", "ETF成交量", "Y", "前60日均量倍数"],
    ["10_Wind_ETF日频", "成交额(亿元）", "ETF成交额", "N", "报告展示/扩展"],
    ["10_Wind_ETF日频", "份额变化（亿份）", "ETF份额变化", "N", "评分增强项"],
    ["11_Wind_TL日频", "成交量", "TL成交量", "Y", "过滤有效交易行"],
    ["12_Wind_可转债", "conversion_premium", "转股溢价率", "Y", "越低越好"],
    ["12_Wind_可转债", "ytm", "到期收益率", "Y", "为负扣分"],
  ],
  4,
  0,
);
table(dict, "A5:E15");
widths(dict, { A: 22, B: 24, C: 32, D: 10, E: 54 });

const etfRaw = workbook.worksheets.add("10_Wind_ETF日频");
base(etfRaw);
const etfFields = ["开盘价", "收盘价", "最低价", "最高价", "成交量（万股）", "成交额(亿元）", "份额变化（亿份）"];
etfRaw.getRange("A1").values = [["日期"]];
etfRaw.getRange("A3").values = [["日期"]];
const etfFormulaColCount = 50 * etfFields.length;
const etfRow1 = [];
const etfRow2 = [];
const etfRow3 = [];
for (let slot = 0; slot < 50; slot += 1) {
  const row = 6 + slot;
  for (let fieldIdx = 0; fieldIdx < etfFields.length; fieldIdx += 1) {
    etfRow1.push(fieldIdx === 0 ? `=IF('02_ETF代码池'!B${row}="","",'02_ETF代码池'!C${row})` : '=""');
    etfRow2.push(`=IF('02_ETF代码池'!B${row}="","",'02_ETF代码池'!B${row})`);
    etfRow3.push(etfFields[fieldIdx]);
  }
}
etfRaw.getRange(`B1:${colLetter(etfFormulaColCount)}2`).formulas = [etfRow1, etfRow2];
etfRaw.getRange(`B3:${colLetter(etfFormulaColCount)}3`).values = [etfRow3];
safeFormat(() => {
  etfRaw.freezePanes.freezeRows(3);
  etfRaw.freezePanes.freezeColumns(1);
  etfRaw.getRange(`A1:${colLetter(etfFormulaColCount)}3`).format.fill.color = colors.header;
  etfRaw.getRange(`A1:${colLetter(etfFormulaColCount)}3`).format.font.bold = true;
  etfRaw.getRange("A:A").format.columnWidth = 12;
  etfRaw.getRange("B:Z").format.columnWidth = 13;
  etfRaw.getRange("A4:A3000").setNumberFormat("yyyy-mm-dd");
  etfRaw.getRange("B4:Z120").format.fill.color = colors.input;
});

const tlRaw = workbook.worksheets.add("11_Wind_TL日频");
base(tlRaw);
const tlFields = ["开盘价", "收盘价", "最低价", "最高价", "成交量", "成交额(亿元）", "持仓量", "持仓量变化"];
tlRaw.getRange("A1").values = [["日期"]];
tlRaw.getRange("A3").values = [["日期"]];
tlRaw.getRange("B1").formulas = [["=IF('04_TL配置'!B6=\"\",\"TL\",'04_TL配置'!C6)"]];
tlRaw.getRange("B2:I2").formulas = [tlFields.map(() => "=IF('04_TL配置'!B6=\"\",\"TL.CFE\",'04_TL配置'!B6)")];
tlRaw.getRange("B3:I3").values = [tlFields];
safeFormat(() => {
  tlRaw.freezePanes.freezeRows(3);
  tlRaw.freezePanes.freezeColumns(1);
  tlRaw.getRange("A1:I3").format.fill.color = colors.header;
  tlRaw.getRange("A1:I3").format.font.bold = true;
  tlRaw.getRange("A:A").format.columnWidth = 12;
  tlRaw.getRange("B:I").format.columnWidth = 14;
  tlRaw.getRange("A4:A3000").setNumberFormat("yyyy-mm-dd");
  tlRaw.getRange("B4:I3000").format.fill.color = colors.input;
});

// These cross-sheet formulas are written after the Wind sheets exist.
qa.getRange("B8").formulas = [["=IF('10_Wind_ETF日频'!A4=\"\",\"\",'10_Wind_ETF日频'!A4)"]];
qa.getRange("D8").formulas = [["=IF(B8=\"\",\"待插入/刷新ETF日频Wind公式\",\"OK\")"]];
qa.getRange("B9").formulas = [["=IF('11_Wind_TL日频'!A4=\"\",\"\",'11_Wind_TL日频'!A4)"]];
qa.getRange("D9").formulas = [["=IF(B9=\"\",\"待插入/刷新TL日频Wind公式\",\"OK\")"]];

const cbData = workbook.worksheets.add("12_Wind_可转债");
base(cbData);
title(cbData, "Wind可转债数据", "第6行开始放Wind公式或Wind导出值。");
const cbHeaders = ["date", "bond_code", "bond_name", "close_price", "remaining_years", "conversion_premium", "ytm", "stock_code", "stock_name", "deducted_profit_growth", "notes"];
writeMatrix(cbData, [cbHeaders], 4, 0);
writeMatrix(cbData, Array.from({ length: 300 }, () => Array(11).fill("")), 5, 0);
table(cbData, "A5:K305");
widths(cbData, { A: 14, B: 16, C: 18, D: 14, E: 16, F: 18, G: 12, H: 16, I: 18, J: 24, K: 36 });
safeFormat(() => {
  cbData.freezePanes.freezeRows(5);
  cbData.getRange("A6:K305").format.fill.color = colors.input;
  cbData.getRange("A6:A305").setNumberFormat("yyyy-mm-dd");
  cbData.getRange("D6:G305").setNumberFormat("0.00");
  cbData.getRange("J6:J305").setNumberFormat("0.0%");
});

await fs.mkdir(outputDir, { recursive: true });
const inspect = await workbook.inspect({
  kind: "table",
  range: "07_数据校验!A5:D13",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 5,
});
console.log(inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

for (const [sheetName, range] of [
  ["00_每日操作台", "A1:D16"],
  ["01_填写说明", "A1:D13"],
  ["02_ETF代码池", "A1:H18"],
  ["07_数据校验", "A1:D13"],
  ["08_Wind公式指南", "A1:E9"],
  ["10_Wind_ETF日频", "A1:Z12"],
  ["11_Wind_TL日频", "A1:I12"],
]) {
  const blob = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  await fs.writeFile(path.join(outputDir, `${sheetName}.png`), bytes);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
