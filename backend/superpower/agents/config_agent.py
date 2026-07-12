from __future__ import annotations

import json

from superpower.skills.etf_rotation_strategy.config import etf_config_hash, normalize_etf_config

from superpower.runtime.agent import AgentSpec, BaseAgent
from superpower.runtime.context import AgentContext
from superpower.runtime.result import AgentStatus


class ConfigAgent(BaseAgent):
    name = "config-agent"
    description = "Load strategy, universe, model, delivery, and path configuration."
    spec = AgentSpec(
        role="配置治理 Agent",
        objective="读取策略参数、标的池、模型边界和投递设置，并把配置作为后续 Agent 的唯一可信输入。",
        required_artifacts=("strategy_params_file", "universe_file", "model_config_file", "delivery_file"),
        produced_artifacts=("strategy_params", "universe", "model_config", "delivery"),
        quality_gates=(
            "配置文件必须存在且为合法 JSON",
            "LLM 开关只影响解释文本，不允许影响交易信号",
            "所有阈值由配置驱动，避免写死在策略里",
        ),
        decision_policy="只加载配置，不做市场判断；策略信号只能由后续确定性 Agent 产生。",
    )

    def execute(self, context: AgentContext) -> tuple[str, dict, dict, AgentStatus]:
        for key in ["strategy_params_file", "universe_file", "model_config_file", "delivery_file"]:
            path = context.get(key)
            context.put(key.replace("_file", ""), json.loads(path.read_text(encoding="utf-8")))

        if context.maybe("disable_llm", False):
            model_config = dict(context.get("model_config"))
            model_config["llm_enabled"] = False
            model_config["disabled_reason"] = "fast_refresh"
            context.put("model_config", model_config)

        etf_snapshot = normalize_etf_config(context.get("strategy_params"))
        context.put("etf_config_snapshot", etf_snapshot)
        context.put("etf_config_hash", etf_config_hash(etf_snapshot))

        return "配置读取完成", {
            "config_sections": 4,
            "llm_enabled": context.get("model_config").get("llm_enabled", False),
        }, {}, "success"
