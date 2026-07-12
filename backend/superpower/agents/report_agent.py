from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent
from superpower.runtime.context import AgentContext


class ReportAgent(SkillBackedAgent):
    name = "report-agent"
    description = "Generate Excel report and frontend JSON payload."
    success_message = "报告生成完成"
    spec = AgentSpec(
        role="报告生产 Agent",
        objective="把策略、解释、风控、QA 和 Agent 审计结果打包成 Excel 日报和前端 dashboard 数据。",
        skill_name="report-generation",
        required_artifacts=(
            "skill_registry",
            "etf_buy_candidates",
            "etf_watchlist",
            "etf_detail_history",
            "etf_sell_alerts",
            "etf_signal_table",
            "etf_indicators",
            "tl_today",
            "tl_recent",
            "tl_indicators",
            "cb_top10",
            "cb_ranked",
            "backtest_summary",
            "backtest_trades",
            "ai_committee_reviews",
            "source_manifest",
            "source_manifest_path",
            "data_quality_report",
            "risk_summary",
            "research_summary",
            "etf_strategy_run",
            "etf_historical_diagnostics",
            "etf_historical_diagnostic_events",
        ),
        produced_artifacts=("report_path", "dashboard_json_path", "market_indicators_json_path"),
        quality_gates=(
            "Excel 和 dashboard 必须来自同一批 context 产物",
            "源文件、可转债和回测诊断必须进入报告",
            "AI研究委员会复核必须进入报告，但不得改变信号",
            "Agent 审计必须进入报告",
            "报告生成后由 audit_daily 独立重算校验",
        ),
        decision_policy="报告 Agent 只负责发布，不重新计算信号。",
    )

    def collect_artifacts(self, context: AgentContext) -> dict[str, str]:
        artifacts = {
            "report": str(context.get("report_path")),
            "dashboard_json": str(context.get("dashboard_json_path")),
            "market_indicators_json": str(context.get("market_indicators_json_path")),
        }
        return artifacts
