from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class TLAgent(SkillBackedAgent):
    name = "tl-agent"
    description = "Run TL daily timing strategy."
    success_message = "TL策略运行完成"
    spec = AgentSpec(
        role="TL 择时 Agent",
        objective="根据30年国债期货 TL 的 MACD 柱和 KDJ 规则输出不做交易、关注交易或建议建仓。",
        skill_name="tl-timing-strategy",
        required_artifacts=("skill_registry", "tl_indicators", "strategy_params"),
        produced_artifacts=("tl_today", "tl_recent"),
        quality_gates=(
            "红柱为正，绿柱为负；柱长短按当前 MACD 柱与上一期比较",
            "周线红柱变短、绿柱变长或红转绿时提示不做交易",
            "周线近2周 J 最低值必须低于20才算低位条件",
            "日线近3日 J 最低值必须低于5才算低位条件",
            "TL 第一版不做平仓提示，只做建仓时机状态",
        ),
        decision_policy="周线不做交易是硬风控；日线建仓倾向不能覆盖周线硬风控。",
    )
