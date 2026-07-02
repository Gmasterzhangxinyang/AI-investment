from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class AIResearchCommitteeAgent(SkillBackedAgent):
    name = "ai-research-committee-agent"
    description = "Run LLM research committee review."
    success_message = "AI研究委员会复核完成"
    spec = AgentSpec(
        role="AI研究委员会 Agent",
        objective="用多个受约束的大模型研究角色复核数据、策略、风险和客户报告表达，但不允许改写任何确定性交易信号。",
        skill_name="ai-research-committee",
        required_artifacts=(
            "skill_registry",
            "data_quality_report",
            "etf_buy_candidates",
            "etf_watchlist",
            "etf_sell_alerts",
            "tl_today",
            "cb_top10",
            "backtest_summary",
            "risk_summary",
            "model_config",
        ),
        produced_artifacts=("ai_committee_reviews",),
        quality_gates=(
            "每个 AI 角色只能输出文本复核意见",
            "不得新增标的、不得修改 score、不得修改 ETF/TL/可转债信号",
            "无 API Key 时必须降级为确定性模板复核，并披露未调用原因",
        ),
        decision_policy="AI研究委员会是复核和表达层，不是信号生成层；所有买卖建议仍由确定性策略 Agent 产生。",
    )
