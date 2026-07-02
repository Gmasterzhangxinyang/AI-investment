from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class IndicatorAgent(SkillBackedAgent):
    name = "indicator-agent"
    description = "Compute deterministic technical indicators."
    success_message = "技术指标计算完成"
    spec = AgentSpec(
        role="指标计算 Agent",
        objective="对每个标的独立计算 MA、MACD、KDJ、前60日量能倍数，向策略层提供不可变指标表。",
        skill_name="technical-indicators",
        required_artifacts=("skill_registry", "etf_market_raw", "tl_market_raw"),
        produced_artifacts=("etf_indicators", "tl_indicators"),
        quality_gates=(
            "ETF/TL 分组独立计算，避免跨标的污染",
            "量能倍数使用前60个交易日均量，不包含当日",
            "指标层不输出买卖建议，只输出数值",
        ),
        decision_policy="确定性指标计算；不允许 LLM 参与或改写数值。",
    )
