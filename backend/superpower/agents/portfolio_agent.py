from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class PortfolioAgent(SkillBackedAgent):
    name = "portfolio-agent"
    description = "Load customer positions and classify holding state."
    success_message = "持仓状态读取完成"
    spec = AgentSpec(
        role="组合状态 Agent",
        objective="读取客户持仓/已平仓状态，决定 ETF 是进入平仓提示路径还是重新进入建仓筛选。",
        skill_name="portfolio-state-machine",
        required_artifacts=("skill_registry", "positions_file"),
        produced_artifacts=("positions",),
        quality_gates=(
            "持仓是客户账户状态，不是 ETF 成分股权重",
            "已平仓标的不再触发平仓提示",
            "持仓状态只影响路径，不修改策略指标",
        ),
        decision_policy="组合状态 Agent 不判断行情，只给策略 Agent 提供状态机输入。",
    )
