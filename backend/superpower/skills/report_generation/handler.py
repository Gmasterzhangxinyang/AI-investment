from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.runtime.artifact_store import ArtifactStore
from superpower.tools.excel_writer import write_workbook
from superpower.tools.frame import agent_audit_frame, records
from superpower.tools.report_date import report_date_text
from superpower.utils.text_safety import DISCLAIMER, sanitize_dashboard, sanitize_frame, scan_frame


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        output_dir = context.get("output_dir")
        latest_dir = output_dir / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)

        etf_buys = context.get("etf_buy_candidates")
        etf_sells = context.get("etf_sell_alerts")
        etf_watchlist = context.get("etf_watchlist")
        etf_details = context.get("etf_detail_history")
        etf_all = context.get("etf_signal_table")
        etf_indicators = context.get("etf_indicators")
        tl_today = context.get("tl_today")
        tl_recent = context.get("tl_recent")
        tl_indicators = context.get("tl_indicators")
        cb_top10 = context.get("cb_top10")
        cb_ranked = context.get("cb_ranked")
        cb_excluded = context.maybe("cb_excluded", pd.DataFrame())
        cb_qualified = context.maybe("cb_qualified", cb_top10)
        cb_weak_watch = context.maybe("cb_weak_watch", pd.DataFrame())
        cb_risk_watch = context.maybe("cb_risk_watch", pd.DataFrame())
        cb_quality_summary = context.maybe("cb_quality_summary", {})
        backtest_summary = context.get("backtest_summary")
        backtest_trades = context.get("backtest_trades")
        historical_diagnostics = context.maybe("etf_historical_diagnostics", pd.DataFrame())
        historical_events = context.maybe("etf_historical_diagnostic_events", pd.DataFrame())
        backtest_next_day_checks = _recent_next_day_checks(
            context.maybe("backtest_next_day_checks", pd.DataFrame()),
            etf_indicators,
            window=30,
        )
        ai_committee_reviews = context.get("ai_committee_reviews")
        source_manifest = context.get("source_manifest")
        source_manifest_path = context.get("source_manifest_path")
        quality = context.get("data_quality_report")
        risk = context.get("risk_summary")
        research_summary = context.get("research_summary")
        llm_usage = context.maybe("llm_usage", {})
        agent_audit = agent_audit_frame(context.maybe("agent_results", []))

        report_date = _report_date(context)
        dashboard = _dashboard_frame(report_date, etf_buys, etf_watchlist, etf_sells, tl_today, cb_top10, backtest_summary, quality, llm_usage)
        report_path = output_dir / f"AI投研日报-Superpower-{report_date}.xlsx"
        workbook_sheets = {
            "今日总览": dashboard,
            "AI解释": research_summary,
            "ETF建仓候选": etf_buys,
            "ETF关注池": etf_watchlist,
            "ETF详情近8日": etf_details,
            "ETF平仓提示": etf_sells,
            "ETF全量信号": etf_all,
            "ETF策略状态说明": _etf_strategy_manual(context.maybe("etf_strategy_run", {})),
            "ETF历史表现诊断": historical_diagnostics,
            "ETF诊断事件": historical_events,
            "TL今日状态": tl_today,
            "TL近期状态": tl_recent,
            "可转债Top10": cb_top10,
            "可转债弱观察": cb_weak_watch,
            "可转债风险观察": cb_risk_watch,
            "可转债全量排序": cb_ranked,
            "可转债排除清单": cb_excluded,
            "历史诊断摘要": backtest_summary,
            "ETF回测交易": backtest_trades,
            "短期方向诊断近30日": backtest_next_day_checks,
            "AI研究委员会": ai_committee_reviews,
            "组合风控": risk,
            "数据校验": quality,
            "源文件Manifest": source_manifest,
            "Agent审计": agent_audit,
        }
        safety_scan = _text_safety_scan(workbook_sheets)
        workbook_sheets["文本安全扫描"] = safety_scan
        workbook_sheets = {name: sanitize_frame(frame) for name, frame in workbook_sheets.items()}
        write_workbook(report_path, workbook_sheets)

        store = ArtifactStore(latest_dir)
        dashboard_payload = {
            "reportDate": report_date,
            "summary": records(dashboard),
            "researchSummary": records(research_summary),
            "etfBuyCandidates": records(etf_buys),
            "etfWatchlist": records(etf_watchlist),
            "etfDetailHistory": records(etf_details),
            "etfSellAlerts": records(etf_sells),
            "tlToday": records(tl_today),
            "tlRecent": records(tl_recent),
            "cbTop10": records(cb_top10),
            "cbRanked": records(cb_ranked),
            "cbExcluded": records(cb_excluded),
            "backtestSummary": records(backtest_summary),
            "backtestTrades": records(backtest_trades, limit=100),
            "backtestNextDayChecks": records(backtest_next_day_checks, limit=200),
            "aiCommitteeReviews": records(ai_committee_reviews),
            "riskSummary": records(risk),
            "dataQuality": records(quality),
            "sourceManifest": records(source_manifest),
            "sourceManifestPath": str(source_manifest_path),
            "agentAudit": records(agent_audit),
            "llmUsage": llm_usage,
            "reportPath": str(report_path),
        }
        dashboard_payload.update(
            _stable_dashboard_schema(
                context=context,
                report_date=report_date,
                dashboard=dashboard,
                quality=quality,
                etf_buys=etf_buys,
                etf_watchlist=etf_watchlist,
                etf_sells=etf_sells,
                etf_all=etf_all,
                tl_today=tl_today,
                tl_recent=tl_recent,
                cb_top10=cb_top10,
                cb_ranked=cb_ranked,
                cb_excluded=cb_excluded,
                cb_qualified=cb_qualified,
                cb_weak_watch=cb_weak_watch,
                cb_risk_watch=cb_risk_watch,
                cb_quality_summary=cb_quality_summary,
                backtest_summary=backtest_summary,
                backtest_next_day_checks=backtest_next_day_checks,
                risk=risk,
                llm_usage=llm_usage,
                safety_scan=safety_scan,
            )
        )
        dashboard_payload["etf"].update(
            {
                "strategy": context.maybe("etf_strategy_run", {}),
                "all_signals": records(etf_all),
                "historical_diagnostics": records(historical_diagnostics),
                "historical_diagnostic_events": records(historical_events, limit=1000),
            }
        )
        dashboard_payload["run_info"]["etf_strategy"] = context.maybe("etf_strategy_run", {})
        market_indicators = _market_indicator_records(etf_indicators, tl_indicators)
        market_indicators_path = store.save_json("market_indicators", {"rows": market_indicators})
        dashboard_payload["marketIndicatorsPath"] = str(market_indicators_path)
        dashboard_payload = sanitize_dashboard(dashboard_payload)
        dashboard_path = store.save_json("dashboard", dashboard_payload)

        context.put("report_path", report_path)
        context.put("dashboard_json_path", dashboard_path)
        context.put("market_indicators_json_path", market_indicators_path)
        return {
            "report_path": str(report_path),
            "dashboard_json_path": str(dashboard_path),
            "market_indicators_json_path": str(market_indicators_path),
            "sheets": len(workbook_sheets),
        }


def _report_date(context: AgentContext) -> str:
    return report_date_text(
        context.maybe("etf_indicators", pd.DataFrame()),
        context.maybe("tl_indicators", pd.DataFrame()),
        context.maybe("cb_ranked", pd.DataFrame()),
    )


def _dashboard_frame(
    report_date: str,
    buys: pd.DataFrame,
    watchlist: pd.DataFrame,
    sells: pd.DataFrame,
    tl_today: pd.DataFrame,
    cb_top10: pd.DataFrame,
    backtest_summary: pd.DataFrame,
    quality: pd.DataFrame,
    llm_usage: dict,
) -> pd.DataFrame:
    tl_row = tl_today.iloc[0] if not tl_today.empty else pd.Series(dtype=object)
    llm_status = _daily_report_llm_status(llm_usage)
    backtest_warns = int((backtest_summary["level"] == "WARN").sum()) if not backtest_summary.empty else 0
    quality_warns = int((quality["status"] != "OK").sum()) if not quality.empty and "status" in quality.columns else 0
    return pd.DataFrame(
        [
            {"item": "免责声明", "value": DISCLAIMER},
            {"item": "报告日期", "value": report_date},
            {"item": "ETF建仓候选数量", "value": len(buys)},
            {"item": "ETF关注池数量", "value": len(watchlist)},
            {"item": "ETF平仓提示数量", "value": len(sells)},
            {"item": "可转债Top10数量", "value": len(cb_top10)},
            {"item": "TL今日状态", "value": tl_row.get("display_status", tl_row.get("state", "数据不足，无法判断"))},
            {"item": "TL收盘价", "value": _round_or_blank(tl_row.get("收盘价"), 4)},
            {"item": "TL日线MACD柱", "value": _round_or_blank(tl_row.get("macd_hist"), 6)},
            {"item": "TL日线KDJ J", "value": _round_or_blank(tl_row.get("kdj_j"), 4)},
            {"item": "回测诊断WARN数量", "value": backtest_warns},
            {"item": "日报解释状态", "value": llm_status},
            {"item": "日报解释模型", "value": llm_usage.get("llm_model", "未配置")},
            {"item": "系统已识别风险项", "value": quality_warns},
        ]
    )


def _daily_report_llm_status(llm_usage: dict) -> str:
    if llm_usage.get("llm_used"):
        return "深度模式已启用"
    reason = str(llm_usage.get("llm_reason", "unknown"))
    if reason == "daily_report_llm_disabled_for_refresh_stability":
        return "稳定模式（深度复核未启用）"
    return f"稳定模式（{reason}）"


def _stable_dashboard_schema(
    *,
    context: AgentContext,
    report_date: str,
    dashboard: pd.DataFrame,
    quality: pd.DataFrame,
    etf_buys: pd.DataFrame,
    etf_watchlist: pd.DataFrame,
    etf_sells: pd.DataFrame,
    etf_all: pd.DataFrame,
    tl_today: pd.DataFrame,
    tl_recent: pd.DataFrame,
    cb_top10: pd.DataFrame,
    cb_ranked: pd.DataFrame,
    cb_excluded: pd.DataFrame,
    cb_qualified: pd.DataFrame,
    cb_weak_watch: pd.DataFrame,
    cb_risk_watch: pd.DataFrame,
    cb_quality_summary: dict[str, Any],
    backtest_summary: pd.DataFrame,
    backtest_next_day_checks: pd.DataFrame,
    risk: pd.DataFrame,
    llm_usage: dict[str, Any],
    safety_scan: pd.DataFrame,
) -> dict[str, Any]:
    quality_status = _overall_quality_status(quality)
    risk_notes = _top_risk_notes(quality, risk, safety_scan)
    run_warnings = _run_warnings(quality, risk, safety_scan)
    return {
        "run_info": {
            "run_id": context.run_id,
            "trade_date": report_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status": "success" if quality_status == "OK" else "partial_success",
            "warnings": run_warnings,
            "llm_enabled": bool(llm_usage.get("llm_used", False)),
            "disclaimer": DISCLAIMER,
            "etf_strategy": context.maybe("etf_strategy_run", {}),
        },
        "data_quality": {
            "overall_status": quality_status,
            "etf": _quality_module_summary(quality, "ETF"),
            "tl": _quality_module_summary(quality, "TL"),
            "convertible_bond": _quality_module_summary(quality, "可转债"),
            "checks": records(quality),
            "errors": _quality_rows(quality, {"ERROR", "FAIL"}),
            "warnings": _quality_rows(quality, {"WARN"}),
        },
        "etf": {
            "status": _module_status(etf_all, quality, "ETF"),
            "counts": {
                "buy_candidates": len(etf_buys),
                "watch": len(etf_watchlist),
                "sell_alerts": len(etf_sells),
                "all_signals": len(etf_all),
            },
            "strategy": context.maybe("etf_strategy_run", {}),
            "historical_diagnostics": records(
                context.maybe("etf_historical_diagnostics", pd.DataFrame())
            ),
            "historical_diagnostic_events": records(
                context.maybe("etf_historical_diagnostic_events", pd.DataFrame()),
                limit=1000,
            ),
            "buy_candidates": records(etf_buys),
            "watchlist": records(etf_watchlist),
            "sell_alerts": records(etf_sells),
            "all_signals": records(etf_all),
            "signals": records(etf_all),
            "warnings": _quality_module_warnings(quality, "ETF"),
            "backtest_diagnostics": {
                "label": "历史回测诊断",
                "execution_assumption": "T日收盘后生成信号，T+1开盘模拟执行；未计入真实滑点、冲击成本、容量和税费差异。",
                "summary": records(backtest_summary),
                "short_term_direction_checks": records(backtest_next_day_checks, limit=200),
            },
        },
        "tl": {
            "status": _first_value(tl_today, "status", "unavailable"),
            "display_status": _first_value(tl_today, "display_status", "数据不足，无法判断"),
            "reason": _first_value(tl_today, "reason", "数据不足，无法判断"),
            "metrics": _first_value(tl_today, "metrics", {}),
            "rule_hits": _split_notes(_first_value(tl_today, "rule_hits", "")),
            "risk_notes": _split_notes(_first_value(tl_today, "risk_notes", "")),
            "warnings": _quality_module_warnings(quality, "TL"),
            "today": records(tl_today),
            "recent": records(tl_recent, limit=30),
            "note": "TL 当前仅做状态诊断，不模拟期货连续合约、换月、杠杆、保证金、滑点和完整平仓收益。",
        },
        "convertible_bond": {
            "status": _module_status(cb_ranked, quality, "可转债"),
            "counts": {
                "top10": len(cb_top10),
                "qualified": len(cb_qualified),
                "weak_watch": len(cb_weak_watch),
                "risk_watch": len(cb_risk_watch),
                "ranked_candidates": len(cb_ranked),
                "excluded": len(cb_excluded),
            },
            "top10": records(cb_top10),
            "qualified": records(cb_qualified, limit=100),
            "weak_watch": records(cb_weak_watch, limit=100),
            "risk_watch": records(cb_risk_watch, limit=100),
            "candidates": records(cb_ranked, limit=100),
            "ranked_candidates": records(cb_ranked, limit=100),
            "excluded": records(cb_excluded, limit=200),
            "summary": cb_quality_summary or {
                "qualified_count": len(cb_qualified),
                "weak_watch_count": len(cb_weak_watch),
                "risk_watch_count": len(cb_risk_watch),
                "excluded_count": len(cb_excluded),
                "top_display_title": "可转债 Top10 候选" if len(cb_qualified) >= 10 else "可转债合格候选（不足 10 只）" if len(cb_qualified) else "今日无合格可转债 Top 候选",
                "quality_message": "今日无合格可转债 Top 候选，候选池整体质量偏弱。" if not len(cb_qualified) else "",
            },
            "warnings": _quality_module_warnings(quality, "可转债") + _industry_warning_items(cb_top10),
            "industry_concentration_warning": _industry_warning(cb_top10),
        },
        "report_summary": {
            "headline": _summary_headline(dashboard),
            "key_points": _summary_key_points(dashboard),
            "key_metrics": records(dashboard),
            "risk_notes": risk_notes[:3],
            "top_risk_notes": risk_notes[:3],
            "text_safety": {
                "status": "OK" if safety_scan.empty else "WARN",
                "issues": records(safety_scan),
            },
        },
    }


def _text_safety_scan(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    issues: list[dict[str, object]] = []
    for name, frame in sheets.items():
        issues.extend(scan_frame(frame, name))
    if not issues:
        return pd.DataFrame(columns=["sheet", "row", "column", "phrases", "status", "note"])
    out = pd.DataFrame(issues)
    out["status"] = "WARN"
    out["note"] = "已在最终输出中替换为保守口径"
    return out


def _overall_quality_status(quality: pd.DataFrame) -> str:
    if quality.empty or "status" not in quality.columns:
        return "WARN"
    statuses = set(quality["status"].astype(str).str.upper())
    if statuses & {"ERROR", "FAIL"}:
        return "ERROR"
    if "WARN" in statuses:
        return "WARN"
    return "OK"


def _quality_rows(quality: pd.DataFrame, statuses: set[str]) -> list[dict[str, Any]]:
    if quality.empty or "status" not in quality.columns:
        return []
    rows = quality[quality["status"].astype(str).str.upper().isin(statuses)]
    return records(rows)


def _run_warnings(quality: pd.DataFrame, risk: pd.DataFrame, safety_scan: pd.DataFrame) -> list[str]:
    return _top_risk_notes(quality, risk, safety_scan)


def _quality_module_summary(quality: pd.DataFrame, label: str) -> dict[str, Any]:
    rows = _quality_module_rows(quality, label)
    status = _overall_quality_status(pd.DataFrame(rows)) if rows else "OK"
    return {
        "status": status,
        "warnings": [row for row in rows if str(row.get("status", "")).upper() == "WARN"],
        "errors": [row for row in rows if str(row.get("status", "")).upper() in {"ERROR", "FAIL"}],
    }


def _quality_module_warnings(quality: pd.DataFrame, label: str) -> list[str]:
    rows = _quality_module_rows(quality, label)
    return [
        f"{row.get('item')}：{row.get('detail')}。{row.get('note', '')}".strip()
        for row in rows
        if str(row.get("status", "")).upper() in {"WARN", "ERROR", "FAIL"}
    ]


def _quality_module_rows(quality: pd.DataFrame, label: str) -> list[dict[str, Any]]:
    if quality.empty or "item" not in quality.columns:
        return []
    mask = quality["item"].astype(str).str.contains(label, na=False)
    return records(quality[mask])


def _module_status(frame: pd.DataFrame, quality: pd.DataFrame, label: str) -> str:
    if frame.empty:
        return "unavailable"
    if not quality.empty and "item" in quality.columns and "status" in quality.columns:
        related = quality[quality["item"].astype(str).str.contains(label, na=False)]
        if related["status"].astype(str).str.upper().isin(["ERROR", "FAIL"]).any():
            return "degraded"
        if related["status"].astype(str).str.upper().eq("WARN").any():
            return "degraded"
    return "ok"


def _top_risk_notes(quality: pd.DataFrame, risk: pd.DataFrame, safety_scan: pd.DataFrame) -> list[str]:
    notes: list[str] = []
    if not quality.empty:
        for _, row in quality[quality["status"].astype(str) != "OK"].head(6).iterrows():
            notes.append(f"{row.get('item')}：{row.get('detail')}。{row.get('note', '')}")
    if not risk.empty:
        for _, row in risk[risk["level"].astype(str).isin(["WARN", "ERROR"])].head(3).iterrows():
            notes.append(f"{row.get('item')}：{row.get('value')}")
    if not safety_scan.empty:
        notes.append("文本安全扫描发现风险表述，已替换为保守口径")
    return [str(note).strip() for note in notes if str(note).strip()]


def _industry_warning(top10: pd.DataFrame) -> str:
    if top10.empty or "sw_l1" not in top10.columns:
        return "暂无可转债行业分散数据"
    counts = top10["sw_l1"].fillna("未分类").astype(str).value_counts()
    if counts.empty:
        return "暂无可转债行业分散数据"
    top_industry = counts.index[0]
    top_count = int(counts.iloc[0])
    if top_count >= 3:
        return f"Top10中{top_industry}行业有{top_count}只，需关注行业集中度"
    return "Top10行业集中度未触发明显警示"


def _industry_warning_items(top10: pd.DataFrame) -> list[str]:
    warning = _industry_warning(top10)
    if "需关注" in warning:
        return [f"{warning}；候选结果存在行业集中，需人工复核组合分散度。"]
    return []


def _summary_headline(dashboard: pd.DataFrame) -> str:
    values = {str(row["item"]): row["value"] for _, row in dashboard.iterrows()} if not dashboard.empty else {}
    return (
        f"ETF建仓候选{values.get('ETF建仓候选数量', 0)}个，"
        f"ETF关注池{values.get('ETF关注池数量', 0)}个，"
        f"TL为{values.get('TL今日状态', '数据不足，无法判断')}，"
        f"可转债Top10为{values.get('可转债Top10数量', 0)}个。"
    )


def _summary_key_points(dashboard: pd.DataFrame) -> list[str]:
    if dashboard.empty:
        return []
    return [f"{row['item']}：{row['value']}" for _, row in dashboard.head(8).iterrows()]


def _split_notes(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, dict):
        return [str(value)]
    text = "" if value is None else str(value)
    if not text or text.lower() in {"nan", "none"}:
        return []
    return [part for part in text.split("；") if part]


def _first_value(frame: pd.DataFrame, column: str, default: Any) -> Any:
    if frame.empty or column not in frame.columns:
        return default
    value = frame.iloc[0].get(column, default)
    if isinstance(value, (dict, list)):
        return value
    return default if pd.isna(value) else value


def _round_or_blank(value: Any, digits: int) -> Any:
    try:
        if pd.isna(value):
            return "--"
        return round(float(value), digits)
    except (TypeError, ValueError):
        return "--"


def _recent_next_day_checks(checks: pd.DataFrame, etf_indicators: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    columns = [
        "signal_date",
        "next_date",
        "signal_type",
        "name",
        "code",
        "expected_direction",
        "next_open",
        "next_close",
        "next_day_return",
        "result",
        "reason",
    ]
    if checks.empty or etf_indicators.empty:
        return pd.DataFrame(columns=columns)

    trade_dates = sorted(pd.to_datetime(etf_indicators["date"].dropna().unique()))
    if not trade_dates:
        return pd.DataFrame(columns=columns)

    window_dates = set(trade_dates[-window:])
    recent = checks[pd.to_datetime(checks["signal_date"]).isin(window_dates)].copy()
    if recent.empty:
        return pd.DataFrame(columns=columns)

    recent["result"] = recent["hit"].map(lambda value: "对" if bool(value) else "错")
    recent = recent.sort_values(["signal_date", "signal_type", "name", "code"])
    return recent[columns].reset_index(drop=True)


def _market_indicator_records(etf_indicators: pd.DataFrame, tl_indicators: pd.DataFrame) -> list[dict[str, object]]:
    etf_rows = _normalise_market_indicators(etf_indicators, asset_type="ETF", volume_field="成交量（万股）")
    tl_rows = _normalise_market_indicators(tl_indicators, asset_type="TL", volume_field="成交量")
    frames = [frame for frame in (etf_rows, tl_rows) if not frame.empty]
    if not frames:
        return []
    compact_frames = [frame.dropna(axis=1, how="all") for frame in frames]
    return records(pd.concat(compact_frames, ignore_index=True, sort=False))


def _normalise_market_indicators(frame: pd.DataFrame, asset_type: str, volume_field: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "asset_type": asset_type,
            "date": frame["date"],
            "code": frame["code"],
            "name": frame["name"],
            "open": frame.get("开盘价"),
            "high": frame.get("最高价"),
            "low": frame.get("最低价"),
            "close": frame.get("收盘价"),
            "volume": frame.get(volume_field),
            "amount": frame.get("成交额（亿元）", frame.get("成交额")),
            "open_interest": frame.get("持仓量"),
            "open_interest_change": frame.get("持仓量变化"),
            "fund_share_change": frame.get("份额变化（亿份）"),
            "ma5": frame.get("ma5"),
            "ma10": frame.get("ma10"),
            "ma20": frame.get("ma20"),
            "ma60": frame.get("ma60"),
            "vol_ratio60": frame.get("vol_ratio60"),
            "dif": frame.get("dif"),
            "dea": frame.get("dea"),
            "macd_hist": frame.get("macd_hist"),
            "kdj_k": frame.get("kdj_k"),
            "kdj_d": frame.get("kdj_d"),
            "kdj_j": frame.get("kdj_j"),
            "ma20_slope_5d": frame.get("ma20_slope_5d"),
            "ma20_slope_state": frame.get("ma20_slope_state"),
            "weekly_macd_hist": frame.get("weekly_macd_hist"),
            "weekly_macd_state": frame.get("weekly_macd_state"),
            "weekly_macd_preview": frame.get("weekly_macd_preview"),
            "daily_macd_state": frame.get("daily_macd_state"),
        }
    )
    return out


def _etf_strategy_manual(strategy: dict[str, Any]) -> pd.DataFrame:
    strategy_id = str(strategy.get("strategy_id") or "legacy_v1")
    rows = [
        {"项目": "当前策略", "说明": strategy_id},
        {"项目": "版本", "说明": strategy.get("strategy_version", "")},
        {"项目": "配置指纹", "说明": strategy.get("config_hash", "")},
    ]
    if strategy_id == "trend_pullback_v2":
        rows.extend(
            [
                {"项目": "中期趋势", "说明": "MA20斜率、价格与均线结构、周MACD和日MACD共同确认；MA20向下或周MACD绿柱扩大时不参与。"},
                {"项目": "密切观察", "说明": "MA5已在MA10上方，日MACD绿柱缩小或转红；同时提示周MACD与MA20走平情况。"},
                {"项目": "短期入场", "说明": "中期确认后等待突破或缩量回踩承接；巨量长阳过热时不追，进入冷却。"},
            ]
        )
    else:
        rows.extend(
            [
                {"项目": "规则", "说明": "保留原有MA5/MA10、MACD与量能共振规则；中期趋势状态不适用。"},
                {"项目": "风险辅助", "说明": "MA20、周MACD、短期过热和假反转只作提示，不改变原策略候选、评分和排名。"},
            ]
        )
    rows.append({"项目": "边界", "说明": "所有状态均为规则筛选和历史表现诊断，不承诺收益，不等于自动交易指令。"})
    return pd.DataFrame(rows)
