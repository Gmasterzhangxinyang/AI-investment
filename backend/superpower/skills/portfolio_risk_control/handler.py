from __future__ import annotations

import pandas as pd

from superpower.runtime.context import AgentContext


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        positions = context.get("positions")
        buys = context.get("etf_buy_candidates")
        watchlist = context.get("etf_watchlist")
        sells = context.get("etf_sell_alerts")
        tl_today = context.get("tl_today")
        cb_top10 = context.get("cb_top10")
        quality = context.get("data_quality_report")
        backtest_summary = context.get("backtest_summary")

        holding_count = 0
        if not positions.empty:
            holding_count = int(((positions["asset_type"] == "ETF") & (positions["status"] == "holding")).sum())
        tl_state = str(tl_today.iloc[0]["state"])
        quality_warns = int((quality["status"] == "WARN").sum()) if not quality.empty else 0
        quality_fails = int((quality["status"] == "FAIL").sum()) if not quality.empty else 0
        backtest_warns = int((backtest_summary["level"] == "WARN").sum()) if not backtest_summary.empty else 0

        risk_summary = pd.DataFrame(
            [
                {"item": "ETF持仓数量", "value": holding_count, "level": "INFO"},
                {"item": "ETF建仓候选数量", "value": len(buys), "level": "INFO"},
                {"item": "ETF关注池数量", "value": len(watchlist), "level": "INFO"},
                {"item": "ETF平仓提示数量", "value": len(sells), "level": "WARN" if len(sells) else "INFO"},
                {"item": "TL今日状态", "value": tl_state, "level": "INFO" if tl_state != "不做交易" else "WARN"},
                {"item": "可转债Top10数量", "value": len(cb_top10), "level": "INFO" if len(cb_top10) else "WARN"},
                {"item": "数据质检WARN数量", "value": quality_warns, "level": "WARN" if quality_warns else "INFO"},
                {"item": "数据质检FAIL数量", "value": quality_fails, "level": "ERROR" if quality_fails else "INFO"},
                {"item": "历史诊断WARN数量", "value": backtest_warns, "level": "WARN" if backtest_warns else "INFO"},
            ]
        )
        context.put("risk_summary", risk_summary)
        return {"risk_items": len(risk_summary), "warn_items": int((risk_summary["level"].isin(["WARN", "ERROR"])).sum())}
