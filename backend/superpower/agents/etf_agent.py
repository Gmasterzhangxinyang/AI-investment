from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class ETFAgent(SkillBackedAgent):
    name = "etf-agent"
    description = "Run the configured ETF trend screening strategy."
    success_message = "ETF策略运行完成"
    spec = AgentSpec(
        role="ETF 趋势筛选 Agent",
        objective="在客户未持仓/已平仓 ETF 中筛选建仓候选，在客户持仓 ETF 中筛选平仓提示，并给出排序评分。",
        skill_name="etf-rotation-strategy",
        required_artifacts=("skill_registry", "etf_indicators", "positions", "strategy_params"),
        produced_artifacts=("etf_signal_table", "etf_buy_candidates", "etf_watchlist", "etf_detail_history", "etf_sell_alerts"),
        quality_gates=(
            "建仓只针对未持仓/已平仓标的",
            "平仓只针对客户当前持仓标的",
            "均线硬条件以MA5/MA10关系为核心，MA20仅作为增强项",
            "关注池收录趋势改善但量能/MACD尚未确认的未持仓标的",
            "输出必须包含触发原因、量能倍数、量能检查、MACD/均线相关数值和评分",
        ),
        decision_policy="ETF 信号由确定性技术规则和配置权重产生，LLM 只能解释不能改表。",
    )
