from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class ExplanationAgent(SkillBackedAgent):
    name = "explanation-agent"
    description = "Generate professional report commentary."
    success_message = "投研解释生成完成"
    spec = AgentSpec(
        role="LLM投研解释 Agent",
        objective="在不改变确定性信号的前提下，调用大模型生成客户可读的投研说明；无API Key时降级为模板解释。",
        skill_name="research-explanation",
        required_artifacts=(
            "skill_registry",
            "etf_buy_candidates",
            "etf_watchlist",
            "etf_sell_alerts",
            "tl_today",
            "cb_top10",
            "backtest_summary",
            "ai_committee_reviews",
            "model_config",
        ),
        produced_artifacts=("research_summary",),
        quality_gates=(
            "解释必须引用已有信号表，不允许编造新标的",
            "LLM 若开启也只能写文字，不能改信号、评分、TL状态和风控标识",
            "必须披露第一版仍基于样例数据和确定性指标",
        ),
        decision_policy="解释 Agent 是叙事层，不是交易决策层；AI研究委员会和解释 Agent 都不能改写确定性信号。",
    )
