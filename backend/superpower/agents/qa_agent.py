from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent
from superpower.runtime.context import AgentContext
from superpower.runtime.result import AgentStatus


class QAAgent(SkillBackedAgent):
    name = "qa-agent"
    description = "Validate data quality before strategy execution."
    success_message = "数据质量校验完成"
    warning_metric = "warn_count"
    spec = AgentSpec(
        role="数据质量 Agent",
        objective="在指标和策略运行前检查 ETF/TL/可转债数据覆盖、最新日期、模板字段、持仓状态和异常项，防止脏数据进入信号层。",
        skill_name="data-quality-gate",
        required_artifacts=("skill_registry", "etf_market_raw", "tl_market_raw", "cb_data", "source_manifest", "positions", "universe"),
        produced_artifacts=("data_quality_report",),
        quality_gates=(
            "ETF 标的数不能低于配置要求",
            "ETF/TL 有效交易日数量必须足够计算指标",
            "客户模板字段、源文件存在性和持仓状态必须进入报告",
            "最新交易日期必须进入报告摘要",
        ),
        decision_policy="QA Agent 可以发 warning，但不修改市场数据。",
    )

    def evaluate_status(self, metrics: dict, context: AgentContext) -> AgentStatus:
        return "warning" if metrics.get("warn_count", 0) or metrics.get("fail_count", 0) else "success"
