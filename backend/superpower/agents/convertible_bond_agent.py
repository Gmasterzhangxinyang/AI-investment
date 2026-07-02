from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class ConvertibleBondAgent(SkillBackedAgent):
    name = "convertible-bond-agent"
    description = "Rank convertible bonds after redemption, credit, fundamental, scale and industry risk gates."
    success_message = "可转债排序完成"
    spec = AgentSpec(
        role="可转债性价比 Agent",
        objective="先排除强赎、信用、价格和规模等明显风险，再按基本面增长、溢价率、YTM质量、剩余期限、信用、强赎状态和规模输出风控后的Top10。",
        skill_name="convertible-bond-ranking",
        required_artifacts=("skill_registry", "cb_data", "strategy_params"),
        produced_artifacts=("cb_ranked", "cb_top10"),
        quality_gates=(
            "100元以下和不低于140元的转债默认不进入正常候选",
            "已发布强赎公告、正股ST、低评级和高YTM异常标的默认剔除",
            "触发强赎价但未见有效公告或只有不强赎公告的标的必须进入风险提示和扣分",
            "基本面增长、剩余期限、转股溢价率、YTM质量、信用、强赎状态、存续规模按配置权重打分",
            "Top10需要尽量满足行业分散约束",
            "无可转债数据时输出空表和等待状态，不阻断 ETF/TL 日报",
        ),
        decision_policy="可转债排序由确定性权重产生；LLM 只能解释排序，不能改分数。",
    )
