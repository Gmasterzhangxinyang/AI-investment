from __future__ import annotations

from pathlib import Path

import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.runtime.artifact_store import ArtifactStore
from superpower.tools.excel_writer import write_workbook
from superpower.tools.frame import agent_audit_frame, records


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
        backtest_summary = context.get("backtest_summary")
        backtest_trades = context.get("backtest_trades")
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
        write_workbook(
            report_path,
            {
                "今日总览": dashboard,
                "AI解释": research_summary,
                "ETF建仓候选": etf_buys,
                "ETF关注池": etf_watchlist,
                "ETF详情近8日": etf_details,
                "ETF平仓提示": etf_sells,
                "ETF全量信号": etf_all,
                "TL今日状态": tl_today,
                "TL近期状态": tl_recent,
                "可转债Top10": cb_top10,
                "可转债全量排序": cb_ranked,
                "历史诊断摘要": backtest_summary,
                "ETF回测交易": backtest_trades,
                "ETF次日验证近30日": backtest_next_day_checks,
                "AI研究委员会": ai_committee_reviews,
                "组合风控": risk,
                "数据校验": quality,
                "源文件Manifest": source_manifest,
                "Agent审计": agent_audit,
            },
        )

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
        market_indicators = _market_indicator_records(etf_indicators, tl_indicators)
        market_indicators_path = store.save_json("market_indicators", {"rows": market_indicators})
        dashboard_payload["marketIndicatorsPath"] = str(market_indicators_path)
        dashboard_path = store.save_json("dashboard", dashboard_payload)

        context.put("report_path", report_path)
        context.put("dashboard_json_path", dashboard_path)
        context.put("market_indicators_json_path", market_indicators_path)
        return {
            "report_path": str(report_path),
            "dashboard_json_path": str(dashboard_path),
            "market_indicators_json_path": str(market_indicators_path),
            "sheets": 19,
        }


def _report_date(context: AgentContext) -> str:
    etf = context.get("etf_indicators")
    tl = context.get("tl_indicators")
    return max(etf["date"].max(), tl["date"].max()).strftime("%Y%m%d")


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
    tl_row = tl_today.iloc[0]
    llm_status = _daily_report_llm_status(llm_usage)
    backtest_warns = int((backtest_summary["level"] == "WARN").sum()) if not backtest_summary.empty else 0
    return pd.DataFrame(
        [
            {"item": "报告日期", "value": report_date},
            {"item": "ETF建仓候选数量", "value": len(buys)},
            {"item": "ETF关注池数量", "value": len(watchlist)},
            {"item": "ETF平仓提示数量", "value": len(sells)},
            {"item": "可转债Top10数量", "value": len(cb_top10)},
            {"item": "TL今日状态", "value": tl_row["state"]},
            {"item": "TL收盘价", "value": round(float(tl_row["收盘价"]), 4)},
            {"item": "TL日线MACD柱", "value": round(float(tl_row["macd_hist"]), 6)},
            {"item": "TL日线KDJ J", "value": round(float(tl_row["kdj_j"]), 4)},
            {"item": "回测诊断WARN数量", "value": backtest_warns},
            {"item": "日报解释状态", "value": llm_status},
            {"item": "日报解释模型", "value": llm_usage.get("llm_model", "未配置")},
            {"item": "系统已识别风险项", "value": int((quality["status"] != "OK").sum())},
        ]
    )


def _daily_report_llm_status(llm_usage: dict) -> str:
    if llm_usage.get("llm_used"):
        return "深度模式已启用"
    reason = str(llm_usage.get("llm_reason", "unknown"))
    if reason == "daily_report_llm_disabled_for_refresh_stability":
        return "稳定模式（深度复核未启用）"
    return f"稳定模式（{reason}）"


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
        }
    )
    return out
