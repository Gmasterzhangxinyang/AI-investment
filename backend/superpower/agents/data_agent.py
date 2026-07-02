from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class DataAgent(SkillBackedAgent):
    name = "data-agent"
    description = "Load Wind Excel market data."
    success_message = "Wind Excel 数据读取完成"
    spec = AgentSpec(
        role="数据接入 Agent",
        objective="把 Wind 导出的 ETF/TL/可转债 Excel 快照解析成标准行情表，保持源字段可追溯。",
        skill_name="wind-excel-ingestion",
        required_artifacts=("skill_registry", "etf_file", "tl_file"),
        produced_artifacts=("etf_market_raw", "tl_market_raw", "cb_data"),
        quality_gates=(
            "只解析原始 Excel，不主动修补价格",
            "过滤成交量/开收盘价为 0 的非交易行",
            "保留日期、名称、代码、OHLCV 和可转债核心字段作为后续输入",
        ),
        decision_policy="数据 Agent 不产生投资观点，只负责把 Wind 快照标准化。",
    )
