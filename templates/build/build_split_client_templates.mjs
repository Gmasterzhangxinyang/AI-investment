import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve("output/客户模板拆分版");

const colors = {
  ink: "#17202A",
  blue: "#1D4ED8",
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

async function saveWorkbook(workbook, name) {
  await fs.mkdir(outputDir, { recursive: true });
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: `${name} formula scan`,
  });
  console.log(errors.ndjson);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const filePath = path.join(outputDir, name);
  await output.save(filePath);
  console.log(filePath);
}

async function buildEtf() {
  const wb = Workbook.create();
  const list = wb.worksheets.add("ETF清单和持仓");
  base(list);
  title(list, "ETF清单和持仓", "客户只填这张表：ETF代码、是否纳入、客户状态。后面一张公式区会自动带出代码。");
  const headers = ["是否纳入", "ETF代码", "ETF名称", "分类", "客户状态", "持仓数量", "买入日期", "备注"];
  const examples = [
    ["Y", "510300.SH", "沪深300ETF", "宽基", "空仓", "", "", "示例，可替换"],
    ["Y", "510500.SH", "中证500ETF", "宽基", "空仓", "", "", "示例，可替换"],
    ["Y", "159949.SZ", "创业板50ETF", "宽基", "空仓", "", "", "示例，可替换"],
    ["Y", "510880.SH", "红利ETF", "红利", "持有", 100000, new Date("2026-05-20T00:00:00"), "示例持仓"],
    ["Y", "512760.SH", "芯片ETF", "行业", "已平仓", "", "", "示例已平仓"],
  ];
  const rows = [...examples];
  while (rows.length < 50) rows.push(["", "", "", "", "", "", "", ""]);
  writeMatrix(list, [headers, ...rows], 4, 0);
  table(list, "A5:H55");
  widths(list, { A: 12, B: 16, C: 18, D: 14, E: 14, F: 14, G: 14, H: 38 });
  safe(() => {
    list.freezePanes.freezeRows(5);
    list.getRange("A6:H55").format.fill.color = colors.input;
    list.getRange("A6:H55").format.font.color = colors.blue;
    list.getRange("G6:G55").setNumberFormat("yyyy-mm-dd");
    list.getRange("F6:F55").setNumberFormat("#,##0");
  });
  validation(list, "A6:A55", ["Y", "N", ""]);
  validation(list, "E6:E55", ["空仓", "持有", "已平仓", "观察", ""]);

  const raw = wb.worksheets.add("ETF日频公式区");
  base(raw);
  const fields = ["开盘价", "收盘价", "最低价", "最高价", "成交量（万股）", "成交额(亿元）", "份额变化（亿份）"];
  raw.getRange("A1").values = [["日期"]];
  raw.getRange("A3").values = [["日期"]];
  const row1 = [];
  const row2 = [];
  const row3 = [];
  for (let slot = 0; slot < 50; slot += 1) {
    const srcRow = 6 + slot;
    for (let i = 0; i < fields.length; i += 1) {
      row1.push(i === 0 ? `=IF('ETF清单和持仓'!B${srcRow}="","",'ETF清单和持仓'!C${srcRow})` : '=""');
      row2.push(`=IF('ETF清单和持仓'!B${srcRow}="","",'ETF清单和持仓'!B${srcRow})`);
      row3.push(fields[i]);
    }
  }
  const lastCol = colLetter(50 * fields.length);
  raw.getRange(`B1:${lastCol}2`).formulas = [row1, row2];
  raw.getRange(`B3:${lastCol}3`).values = [row3];
  safe(() => {
    raw.freezePanes.freezeRows(3);
    raw.freezePanes.freezeColumns(1);
    raw.getRange(`A1:${lastCol}3`).format.fill.color = colors.header;
    raw.getRange(`A1:${lastCol}3`).format.font.bold = true;
    raw.getRange("A:A").format.columnWidth = 12;
    raw.getRange("B:Z").format.columnWidth = 13;
    raw.getRange("A4:A3000").setNumberFormat("yyyy-mm-dd");
    raw.getRange("A4:Z120").format.fill.color = colors.input;
  });
  const blob = await wb.render({ sheetName: "ETF清单和持仓", range: "A1:H16", scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, "01_ETF预览.png"), new Uint8Array(await blob.arrayBuffer()));
  await saveWorkbook(wb, "01_ETF清单和日频公式.xlsx");
}

async function buildTl() {
  const wb = Workbook.create();
  const tl = wb.worksheets.add("TL日频公式区");
  base(tl);
  const fields = ["开盘价", "收盘价", "最低价", "最高价", "成交量", "成交额(亿元）", "持仓量", "持仓量变化"];
  tl.getRange("A1").values = [["TL"]];
  tl.getRange("B1").values = [["30年国债期货TL"]];
  tl.getRange("B2:I2").values = [fields.map(() => "TL.CFE")];
  tl.getRange("A3").values = [["日期"]];
  tl.getRange("B3:I3").values = [fields];
  safe(() => {
    tl.freezePanes.freezeRows(3);
    tl.freezePanes.freezeColumns(1);
    tl.getRange("A1:I3").format.fill.color = colors.header;
    tl.getRange("A1:I3").format.font.bold = true;
    tl.getRange("A:A").format.columnWidth = 12;
    tl.getRange("B:I").format.columnWidth = 14;
    tl.getRange("A4:I3000").format.fill.color = colors.input;
    tl.getRange("A4:A3000").setNumberFormat("yyyy-mm-dd");
  });
  await saveWorkbook(wb, "02_TL日频公式.xlsx");
}

async function buildCb() {
  const wb = Workbook.create();
  const cb = wb.worksheets.add("可转债数据");
  base(cb);
  title(cb, "可转债数据", "一行一只转债。可以用Wind公式，也可以从Wind导出后粘贴。");
  writeMatrix(
    cb,
    [["是否纳入", "日期", "转债代码", "转债名称", "价格", "剩余期限", "转股溢价率", "到期收益率", "正股代码", "正股名称", "扣非净利润增长率", "备注"]],
    4,
    0,
  );
  writeMatrix(cb, Array.from({ length: 120 }, () => ["", "", "", "", "", "", "", "", "", "", "", ""]), 5, 0);
  table(cb, "A5:L125");
  widths(cb, { A: 10, B: 14, C: 16, D: 18, E: 12, F: 14, G: 16, H: 14, I: 16, J: 18, K: 20, L: 32 });
  safe(() => {
    cb.freezePanes.freezeRows(5);
    cb.getRange("A6:L125").format.fill.color = colors.input;
    cb.getRange("A6:L125").format.font.color = colors.blue;
    cb.getRange("B6:B125").setNumberFormat("yyyy-mm-dd");
    cb.getRange("G6:H125").setNumberFormat("0.00%");
    cb.getRange("K6:K125").setNumberFormat("0.0%");
  });
  validation(cb, "A6:A125", ["Y", "N", ""]);
  await saveWorkbook(wb, "03_可转债数据.xlsx");
}

await fs.mkdir(outputDir, { recursive: true });
await buildEtf();
await buildTl();
await buildCb();
