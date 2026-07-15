from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent
from superpower.runtime.context import AgentContext
from superpower.runtime.result import AgentStatus


class RiskAgent(SkillBackedAgent):
    name = "risk-agent"
    description = "Create portfolio-level risk summary."
    success_message = "组合风控完成"
    warning_metric = "warn_items"
    spec = AgentSpec(
        role="组合风控 Agent",
        objective="把 ETF/TL 信号转成组合层风险提示，突出需要人工复核的持仓和候选数量。",
        skill_name="portfolio-risk-control",
        required_artifacts=(
            "skill_registry",
            "positions",
            "etf_buy_candidates",
            "etf_watchlist",
            "etf_sell_alerts",
            "tl_today",
            "cb_top10",
            "data_quality_report",
            "backtest_summary",
        ),
        produced_artifacts=("risk_summary",),
        quality_gates=(
            "平仓提示数量超过0时必须进入风控摘要",
            "TL 状态必须进入组合层摘要",
            "数据质量和历史诊断样本不足必须进入组合层摘要",
            "风控只汇总和分级，不更改策略信号",
        ),
        decision_policy="风控 Agent 可以把 workflow 标为 warning，但不能覆盖策略表。",
    )

    def evaluate_status(self, metrics: dict, context: AgentContext) -> AgentStatus:
        return "warning" if metrics.get("warn_items", 0) else "success"
