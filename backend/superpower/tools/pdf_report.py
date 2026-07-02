from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FONT_NAME = "STSong-Light"


def write_research_pdf(root_dir: Path, dashboard: dict[str, Any]) -> Path:
    """Create a Chinese-safe PDF report from the latest dashboard payload."""
    pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

    report_date = dashboard.get("reportDate", "latest")
    output_path = root_dir / "outputs" / f"AI投研日报-Superpower-{report_date}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=14 * mm,
        title=f"AI投研日报-Superpower-{report_date}",
        author="Superpower AI Research",
    )
    styles = _styles()
    story: list[Any] = []

    story.append(Paragraph("AI 投研日报", styles["TitleCn"]))
    story.append(Paragraph(f"报告日期：{report_date}", styles["Muted"]))
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("今日总览", styles["Section"]))
    story.append(_simple_table([["项目", "数值"]] + [[row["item"], row["value"]] for row in dashboard.get("summary", [])]))
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("投研解释", styles["Section"]))
    summary_text = dashboard.get("researchSummary", [{}])[0].get("content", "暂无解释。")
    for paragraph in str(summary_text).splitlines():
        story.append(Paragraph(escape(paragraph), styles["BodyCn"]))
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("ETF 建仓候选", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("etfBuyCandidates", []),
            [
                ("name", "标的"),
                ("code", "代码"),
                ("close", "收盘"),
                ("vol_ratio60", "量能倍数"),
                ("score", "评分"),
                ("signal_reason", "触发原因"),
            ],
            empty_text="暂无建仓候选。",
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("ETF 关注池", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("etfWatchlist", []),
            [
                ("name", "标的"),
                ("code", "代码"),
                ("watch_type", "关注类型"),
                ("vol_ratio60", "量能倍数"),
                ("score", "评分"),
                ("missing_condition", "还差条件"),
            ],
            empty_text="暂无关注池标的。",
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("ETF 平仓提示", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("etfSellAlerts", []),
            [
                ("name", "标的"),
                ("code", "代码"),
                ("close", "收盘"),
                ("vol_ratio60", "量能倍数"),
                ("score", "评分"),
                ("signal_reason", "触发原因"),
            ],
            empty_text="暂无平仓提示。",
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("可转债 Top10", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("cbTop10", []),
            [
                ("bond_name", "转债"),
                ("bond_code", "代码"),
                ("price", "价格"),
                ("remaining_years", "期限"),
                ("score", "评分"),
                ("rank_reason", "评分原因"),
            ],
            empty_text="暂无可转债数据或暂无140元以下候选。",
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("TL 日频状态", styles["Section"]))
    tl_row = dashboard.get("tlToday", [{}])[0]
    story.append(
        _simple_table(
            [
                ["项目", "数值"],
                ["状态", tl_row.get("state", "--")],
                ["收盘价", tl_row.get("收盘价", "--")],
                ["日线 MACD 柱", tl_row.get("macd_hist", "--")],
                ["日线 KDJ J", tl_row.get("kdj_j", "--")],
                ["周线 MACD 柱", tl_row.get("week_macd_hist", "--")],
                ["周线 MACD 判定", tl_row.get("weekly_macd_reason", "--")],
                ["周线近2周 J 最低值", tl_row.get("weekly_kdj_low_window", "--")],
                ["周线 KDJ 条件", tl_row.get("weekly_kdj_threshold_check", "--")],
                ["日线 MACD 判定", tl_row.get("daily_macd_reason", "--")],
                ["日线近3日 J 最低值", tl_row.get("daily_kdj_low_window", "--")],
                ["日线 KDJ 条件", tl_row.get("daily_kdj_threshold_check", "--")],
                ["日线关注", "是" if tl_row.get("daily_attention") else "否"],
                ["日线 KDJ 反弹", "是" if tl_row.get("daily_kdj_rebound") else "否"],
            ]
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("数据校验", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("dataQuality", []),
            [("item", "校验项"), ("status", "状态"), ("detail", "详情")],
            empty_text="暂无数据校验结果。",
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("历史诊断", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("backtestSummary", []),
            [("item", "指标"), ("value", "值"), ("level", "级别"), ("note", "说明")],
            empty_text="暂无历史诊断。",
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("AI研究委员会", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("aiCommitteeReviews", []),
            [("title", "角色"), ("llm_used", "调用"), ("model", "模型"), ("review", "复核意见")],
            empty_text="暂无AI复核结果。",
        )
    )
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("组合风控", styles["Section"]))
    story.append(
        _records_table(
            dashboard.get("riskSummary", []),
            [("item", "风险项"), ("value", "值"), ("level", "级别")],
            empty_text="暂无组合风控结果。",
        )
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output_path


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "TitleCn": ParagraphStyle(
            "TitleCn",
            parent=sample["Title"],
            fontName=FONT_NAME,
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#172033"),
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "Section": ParagraphStyle(
            "Section",
            parent=sample["Heading2"],
            fontName=FONT_NAME,
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#172033"),
            spaceBefore=4,
            spaceAfter=6,
        ),
        "BodyCn": ParagraphStyle(
            "BodyCn",
            parent=sample["BodyText"],
            fontName=FONT_NAME,
            fontSize=10,
            leading=16,
            textColor=colors.HexColor("#30394a"),
            wordWrap="CJK",
        ),
        "Muted": ParagraphStyle(
            "Muted",
            parent=sample["BodyText"],
            fontName=FONT_NAME,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#657084"),
        ),
        "Cell": ParagraphStyle(
            "Cell",
            parent=sample["BodyText"],
            fontName=FONT_NAME,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#263044"),
            wordWrap="CJK",
        ),
    }


def _simple_table(rows: list[list[Any]]) -> Table:
    styles = _styles()
    table_rows = [[Paragraph(escape(_format_value(cell)), styles["Cell"]) for cell in row] for row in rows]
    table = Table(table_rows, colWidths=[42 * mm, 122 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _records_table(records: list[dict[str, Any]], columns: list[tuple[str, str]], empty_text: str) -> Table:
    if not records:
        return _simple_table([["说明", empty_text]])

    styles = _styles()
    header = [label for _, label in columns]
    rows = [header]
    for record in records:
        rows.append([record.get(key, "") for key, _ in columns])

    table_rows = [[Paragraph(escape(_format_value(cell)), styles["Cell"]) for cell in row] for row in rows]
    if len(columns) >= 6:
        widths = [20 * mm, 26 * mm, 18 * mm, 22 * mm, 17 * mm, 61 * mm]
    elif len(columns) == 4:
        widths = [42 * mm, 26 * mm, 22 * mm, 74 * mm]
    elif len(columns) == 3:
        widths = [44 * mm, 22 * mm, 98 * mm]
    else:
        widths = [164 * mm / len(columns)] * len(columns)
    table = Table(table_rows, colWidths=widths, repeatRows=1)
    table.setStyle(_table_style())
    return table


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f4f8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#172033")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#cbd5e1")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dce2ea")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )


def _footer(canvas: Any, doc: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#657084"))
    canvas.drawRightString(195 * mm, 8 * mm, f"Superpower AI Research - {doc.page}")
    canvas.restoreState()


def _format_value(value: Any) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "--"
        if abs(value) >= 100:
            return f"{value:.2f}"
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)
