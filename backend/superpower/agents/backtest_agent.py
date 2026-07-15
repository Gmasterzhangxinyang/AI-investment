from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class BacktestAgent(SkillBackedAgent):
    name = "backtest-agent"
    description = "Run deterministic strategy diagnostics on available history."
    success_message = "历史诊断完成"
    spec = AgentSpec(
        role="历史诊断 Agent",
        objective="用当前可用历史数据对 ETF 和 TL 规则做可复现诊断，输出交易次数、胜率、收益分布和历史长度风险。",
        skill_name="strategy-backtest",
        required_artifacts=("skill_registry", "etf_indicators", "tl_indicators", "strategy_params"),
        produced_artifacts=(
            "backtest_summary",
            "backtest_trades",
            "etf_historical_state_traces",
            "etf_historical_diagnostic_events",
            "etf_historical_diagnostics",
        ),
        quality_gates=(
            "历史诊断使用确定性规则，不允许 LLM 参与",
            "信号日收盘后生成，模拟交易使用下一交易日开盘价",
            "历史不足时必须明确标记，不包装成正式有效性结论",
        ),
        decision_policy="历史诊断 Agent 只描述历史事件，不承诺未来收益，也不改变今日信号。",
    )
