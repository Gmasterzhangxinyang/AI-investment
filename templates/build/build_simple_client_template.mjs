import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const buildDir = path.resolve(".");
const outputDir = path.join(buildDir, "output");
const outputPath = path.join(outputDir, "Wind公式填报模板-AI投研系统-极简客户版.xlsx");

const workbook = Workbook.create();

const colors = {
  ink: "#17202A",
  blue: "#1D4ED8",
  green: "#15803D",
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

function safe(fn) {
  try {
    fn();
  } catch (err) {
    console.warn(`format skipped: ${err.message}`);
  }
}

function base(sheet) {
  safe(() => {
    sheet.showGridLines = false;
  });
}

function title(sheet, main, sub) {
  sheet.getRange("A1").values = [[main]];
  sheet.getRange("A2").values = [[sub]];
  safe(() => {
    sheet.getRange("A1:H1").format.fill.color = colors.panel;
    sheet.getRange("A2:H2").format.fill.color = colors.panel;
    sheet.getRange("A1").format.font.bold = true;
    sheet.getRange("A1").format.font.size = 16;
    sheet.getRange("A1:H2").format.borders = { preset: "outside", style: "thin", color: colors.line };
  });
}

function table(sheet, address) {
  safe(() => {
    const range = sheet.getRange(address);
    range.format.borders = { preset: "all", style: "thin", color: colors.line };
    range.format.font.size = 10;
    range.format.wrapText = true;
    const [start, end] = address.split(":");
    const startMatch = start.match(/([A-Z]+)(\d+)/);
    const endMatch = end.match(/([A-Z]+)(\d+)/);
    if (startMatch && endMatch) {
      const headerRange = sheet.getRange(`${startMatch[1]}${startMatch[2]}:${endMatch[1]}${startMatch[2]}`);
      headerRange.format.fill.color = colors.header;
      headerRange.format.font.bold = true;
    }
  });
}

function widths(sheet, map) {
  safe(() => {
    for (const [col, width] of Object.entries(map)) {
      sheet.getRange(`${col}:${col}`).format.columnWidth = width;
    }
  });
}

function validation(sheet, range, values) {
  safe(() => {
    sheet.getRange(range).dataValidation = { rule: { type: "list", values } };
  });
}

const home = workbook.worksheets.add("00_先看这里");
base(home);
title(home, "AI投研系统 Wind公式填报模板", "客户只需要维护前几张中文表，把Wind公式放到后面公式区，然后保存。");
writeMatrix(
  home,
  [
    ["每天怎么做", "操作", "位置", "完成标准"],
    ["1", "打开Excel，确认Wind已登录", "Wind插件", "能刷新数据"],
    ["2", "维护ETF、TL、可转债信息", "01-04", "黄色区域填好"],
    ["3", "把Wind公式放到公式区并刷新", "10-12", "A4/A6开始出现最新数据"],
    ["4", "检查模板状态", "05_检查", "关键项OK"],
    ["5", "系统前端点击 Refresh Data", "AI投研系统", "生成日报"],
    [null, null, null, null],
    ["客户只改哪里", "用途", "是否每天维护", "说明"],
    ["01_ETF清单和持仓", "ETF标的池 + 客户持仓状态", "需要", "一张表看全ETF"],
    ["02_TL设置", "确认TL代码和频率", "通常不改", "第一版日频"],
    ["03_可转债清单", "转债池", "需要", "用于140元以下排名"],
    ["04_参数设置", "阈值和权重", "少改", "复盘后再调"],
  ],
  4,
  0,
);
table(home, "A5:D16");
widths(home, { A: 18, B: 42, C: 24, D: 46 });
safe(() => {
  home.getRange("B6:C10").format.fill.color = colors.input;
  home.getRange("B6:C10").format.font.color = colors.blue;
});

const etf = workbook.worksheets.add("01_ETF清单和持仓");
base(etf);
title(etf, "ETF清单和持仓", "客户在这一张表维护ETF标的池和账户持仓状态。示例只放几只，生产请扩到30-50只。");
const etfHeaders = ["是否纳入", "ETF代码", "ETF名称", "分类", "客户状态", "持仓数量", "买入日期", "备注"];
const etfExamples = [
  ["Y", "510300.SH", "沪深300ETF", "宽基", "空仓", "", "", "示例，可替换"],
  ["Y", "510500.SH", "中证500ETF", "宽基", "空仓", "", "", "示例，可替换"],
  ["Y", "159949.SZ", "创业板50ETF", "宽基", "空仓", "", "", "示例，可替换"],
  ["Y", "510880.SH", "红利ETF", "红利", "持有", 100000, new Date("2026-05-20T00:00:00"), "示例持仓"],
  ["Y", "512760.SH", "芯片ETF", "行业", "已平仓", "", "", "示例已平仓"],
];
const etfRows = [...etfExamples];
while (etfRows.length < 50) etfRows.push(["", "", "", "", "", "", "", ""]);
writeMatrix(etf, [etfHeaders, ...etfRows], 4, 0);
table(etf, "A5:H55");
widths(etf, { A: 12, B: 16, C: 18, D: 14, E: 14, F: 14, G: 14, H: 38 });
safe(() => {
  etf.freezePanes.freezeRows(5);
  etf.getRange("A6:H55").format.fill.color = colors.input;
  etf.getRange("A6:H55").format.font.color = colors.blue;
  etf.getRange("G6:G55").setNumberFormat("yyyy-mm-dd");
  etf.getRange("F6:F55").setNumberFormat("#,##0");
});
validation(etf, "A6:A55", ["Y", "N", ""]);
validation(etf, "E6:E55", ["空仓", "持有", "已平仓", "观察", ""]);

const tl = workbook.worksheets.add("02_TL设置");
base(tl);
title(tl, "TL设置", "30年国债期货TL设置。第一版先用日频，不填持仓。");
writeMatrix(
  tl,
  [
    ["是否启用", "代码", "名称", "频率", "开始日期", "备注"],
    ["Y", "TL.CFE", "30年国债期货TL", "日频", new Date("2021-01-01T00:00:00"), "先做日频；60分钟后续扩展"],
  ],
  4,
  0,
);
table(tl, "A5:F6");
widths(tl, { A: 12, B: 16, C: 24, D: 12, E: 14, F: 54 });
safe(() => {
  tl.getRange("A6:F6").format.fill.color = colors.input;
  tl.getRange("A6:F6").format.font.color = colors.blue;
  tl.getRange("E6").setNumberFormat("yyyy-mm-dd");
});
validation(tl, "A6:A20", ["Y", "N"]);
validation(tl, "D6:D20", ["日频", "60分钟"]);

const cb = workbook.worksheets.add("03_可转债清单");
base(cb);
title(cb, "可转债清单", "客户维护转债池。系统后续筛选140元以下性价比最高的10只。");
writeMatrix(cb, [["是否纳入", "转债代码", "转债名称", "正股代码", "正股名称", "价格上限", "备注"]], 4, 0);
const cbRows = Array.from({ length: 80 }, () => ["", "", "", "", "", 140, ""]);
writeMatrix(cb, cbRows, 5, 0);
table(cb, "A5:G85");
widths(cb, { A: 12, B: 16, C: 18, D: 16, E: 18, F: 12, G: 42 });
safe(() => {
  cb.freezePanes.freezeRows(5);
  cb.getRange("A6:G85").format.fill.color = colors.input;
  cb.getRange("A6:G85").format.font.color = colors.blue;
  cb.getRange("F6:F85").setNumberFormat("#,##0.00");
});
validation(cb, "A6:A85", ["Y", "N", ""]);

const params = workbook.worksheets.add("04_参数设置");
base(params);
title(params, "参数设置", "一般不用改。只有策略复盘后再调整。");
writeMatrix(
  params,
  [
    ["模块", "参数", "数值", "说明"],
    ["ETF", "建仓放量倍数", 1.1, "成交量达到前60日均量的倍数"],
    ["ETF", "平仓MA10放量倍数", 1.2, "跌破MA10时的放量阈值"],
    ["ETF", "平仓MA5放量倍数", 1.5, "跌破MA5时的放量阈值"],
    ["转债", "正股利润增长权重", 0.3, "越高越好"],
    ["转债", "剩余期限权重", 0.3, "按策略规则打分"],
    ["转债", "转股溢价率权重", 0.3, "越低越好"],
    ["转债", "到期收益率权重", 0.1, "负值扣分"],
  ],
  4,
  0,
);
table(params, "A5:D12");
widths(params, { A: 12, B: 24, C: 12, D: 52 });
safe(() => {
  params.getRange("C6:C12").format.fill.color = colors.input;
  params.getRange("C6:C12").format.font.color = colors.blue;
  params.getRange("C9:C12").setNumberFormat("0.0%");
});

const check = workbook.worksheets.add("05_检查");
base(check);
title(check, "检查", "刷新Wind后先看这里；如果提示待刷新，就先回到10/11/12放公式或刷新。");
writeMatrix(
  check,
  [
    ["检查项", "结果", "说明"],
    ["ETF纳入数量", null, "生产建议30-50只"],
    ["ETF公式区首行日期", null, "10_ETF日频公式区 A4有日期才算已填"],
    ["TL公式区首行日期", null, "11_TL日频公式区 A4有日期才算已填"],
    ["转债权重合计", null, "应为100%"],
    ["模板结构", "OK", "不要改10/11/12前三行表头"],
  ],
  4,
  0,
);
check.getRange("B6").formulas = [["=COUNTIF('01_ETF清单和持仓'!A6:A55,\"Y\")"]];
check.getRange("B9").formulas = [["=SUM('04_参数设置'!C9:C12)"]];
table(check, "A5:C10");
widths(check, { A: 24, B: 24, C: 56 });
safe(() => {
  check.getRange("B9").setNumberFormat("0.0%");
  check.getRange("B6:B10").format.font.bold = true;
});

const windGuide = workbook.worksheets.add("06_Wind公式说明");
base(windGuide);
title(windGuide, "Wind公式说明", "客户只要把Wind时间序列结果落到后面公式区，字段名和前三行结构不要改。");
writeMatrix(
  windGuide,
  [
    ["数据", "放在哪里", "最简单理解", "必须字段"],
    ["ETF日频", "10_ETF日频公式区：A4开始日期，B4开始行情", "A列日期，后面每7列是一只ETF", "开盘价、收盘价、最低价、最高价、成交量（万股）、成交额(亿元）、份额变化（亿份）"],
    ["TL日频", "11_TL日频公式区：A4开始日期，B4开始行情", "A列日期，后面是TL行情", "开盘价、收盘价、最低价、最高价、成交量、成交额(亿元）、持仓量、持仓量变化"],
    ["可转债", "12_转债公式区：第6行开始", "一行一只转债", "价格、剩余期限、转股溢价率、到期收益率、正股扣非净利润增长率"],
  ],
  4,
  0,
);
table(windGuide, "A5:D8");
widths(windGuide, { A: 14, B: 42, C: 34, D: 86 });

const etfRaw = workbook.worksheets.add("10_ETF日频公式区");
base(etfRaw);
const etfFields = ["开盘价", "收盘价", "最低价", "最高价", "成交量（万股）", "成交额(亿元）", "份额变化（亿份）"];
etfRaw.getRange("A1").values = [["日期"]];
etfRaw.getRange("A3").values = [["日期"]];
const slotCount = 50;
const row1 = [];
const row2 = [];
const row3 = [];
for (let slot = 0; slot < slotCount; slot += 1) {
  const srcRow = 6 + slot;
  for (let i = 0; i < etfFields.length; i += 1) {
    row1.push(i === 0 ? `=IF('01_ETF清单和持仓'!B${srcRow}="","",'01_ETF清单和持仓'!C${srcRow})` : '=""');
    row2.push(`=IF('01_ETF清单和持仓'!B${srcRow}="","",'01_ETF清单和持仓'!B${srcRow})`);
    row3.push(etfFields[i]);
  }
}
const etfLastCol = colLetter(slotCount * etfFields.length);
etfRaw.getRange(`B1:${etfLastCol}2`).formulas = [row1, row2];
etfRaw.getRange(`B3:${etfLastCol}3`).values = [row3];
safe(() => {
  etfRaw.freezePanes.freezeRows(3);
  etfRaw.freezePanes.freezeColumns(1);
  etfRaw.getRange(`A1:${etfLastCol}3`).format.fill.color = colors.header;
  etfRaw.getRange(`A1:${etfLastCol}3`).format.font.bold = true;
  etfRaw.getRange("A:A").format.columnWidth = 12;
  etfRaw.getRange("B:Z").format.columnWidth = 13;
  etfRaw.getRange("A4:A3000").setNumberFormat("yyyy-mm-dd");
  etfRaw.getRange("B4:Z120").format.fill.color = colors.input;
});

const tlRaw = workbook.worksheets.add("11_TL日频公式区");
base(tlRaw);
const tlFields = ["开盘价", "收盘价", "最低价", "最高价", "成交量", "成交额(亿元）", "持仓量", "持仓量变化"];
tlRaw.getRange("A1").values = [["日期"]];
tlRaw.getRange("A3").values = [["日期"]];
tlRaw.getRange("B1").formulas = [["='02_TL设置'!C6"]];
tlRaw.getRange("B2:I2").formulas = [tlFields.map(() => "='02_TL设置'!B6")];
tlRaw.getRange("B3:I3").values = [tlFields];
safe(() => {
  tlRaw.freezePanes.freezeRows(3);
  tlRaw.freezePanes.freezeColumns(1);
  tlRaw.getRange("A1:I3").format.fill.color = colors.header;
  tlRaw.getRange("A1:I3").format.font.bold = true;
  tlRaw.getRange("A:A").format.columnWidth = 12;
  tlRaw.getRange("B:I").format.columnWidth = 14;
  tlRaw.getRange("A4:A3000").setNumberFormat("yyyy-mm-dd");
  tlRaw.getRange("B4:I3000").format.fill.color = colors.input;
});

// Cross-sheet formulas are written after the formula-zone sheets exist.
check.getRange("B7").formulas = [["=IF('10_ETF日频公式区'!A4=\"\",\"待填Wind公式\",'10_ETF日频公式区'!A4)"]];
check.getRange("B8").formulas = [["=IF('11_TL日频公式区'!A4=\"\",\"待填Wind公式\",'11_TL日频公式区'!A4)"]];

const cbRaw = workbook.worksheets.add("12_转债公式区");
base(cbRaw);
title(cbRaw, "转债公式区", "第6行开始放Wind公式或粘贴Wind导出值。");
writeMatrix(
  cbRaw,
  [["日期", "转债代码", "转债名称", "价格", "剩余期限", "转股溢价率", "到期收益率", "正股代码", "正股名称", "扣非净利润增长率", "备注"]],
  4,
  0,
);
writeMatrix(cbRaw, Array.from({ length: 200 }, () => Array(11).fill("")), 5, 0);
table(cbRaw, "A5:K205");
widths(cbRaw, { A: 14, B: 16, C: 18, D: 12, E: 14, F: 16, G: 14, H: 16, I: 18, J: 20, K: 32 });
safe(() => {
  cbRaw.freezePanes.freezeRows(5);
  cbRaw.getRange("A6:K205").format.fill.color = colors.input;
  cbRaw.getRange("A6:A205").setNumberFormat("yyyy-mm-dd");
  cbRaw.getRange("F6:G205").setNumberFormat("0.00%");
  cbRaw.getRange("J6:J205").setNumberFormat("0.0%");
});

await fs.mkdir(outputDir, { recursive: true });

const inspect = await workbook.inspect({
  kind: "table",
  range: "05_检查!A5:C10",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 4,
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
  ["00_先看这里", "A1:D16"],
  ["01_ETF清单和持仓", "A1:H16"],
  ["05_检查", "A1:C10"],
  ["06_Wind公式说明", "A1:D8"],
  ["10_ETF日频公式区", "A1:Z12"],
  ["11_TL日频公式区", "A1:I12"],
]) {
  const blob = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  await fs.writeFile(path.join(outputDir, `${sheetName}.png`), bytes);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
