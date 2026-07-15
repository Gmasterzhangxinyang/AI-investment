from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from superpower.tools.llm import LLMResult, generate_text

from .evidence_review import EvidenceAccuracyReviewer, EvidenceReview
from .schemas import AgentStep, ChatIntent, ToolResult
from .tool_registry import ResearchToolRegistry


@dataclass(frozen=True)
class PlannedToolCall:
    name: str
    arguments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentDecision:
    action: str
    intent: str
    entities: dict[str, str]
    tool_name: str
    arguments: dict[str, str]
    clarification_question: str
    reason: str


@dataclass(frozen=True)
class ReflectionDecision:
    verdict: str
    tool_name: str
    arguments: dict[str, str]
    clarification_question: str
    issues: list[str]
    reason: str


@dataclass(frozen=True)
class AgentPreparation:
    planned: bool
    intent: ChatIntent
    tools: list[ToolResult]
    steps: list[AgentStep]
    clarification: str
    planner_llm_used: bool
    planner_provider: str
    planner_model: str
    planner_reason: str
    review: EvidenceReview | None = None
    agent_iterations: int = 0
    reflection_count: int = 0


class ResearchAgentRuntime:
    """Bounded ReAct supervisor: reason -> act -> observe -> reflect -> answer."""

    MAX_ITERATIONS = 8
    MAX_REFLECTIONS = 2
    ALLOWED_INTENTS = {
        "conversation",
        "chat_data_scope",
        "database_inventory",
        "asset_list",
        "strategy_params",
        "strategy_comparison",
        "strategy_stability",
        "historical_diagnostics",
        "etf_ranking",
        "etf_entry",
        "etf_exit",
        "etf_detail",
        "etf_strategy_comparison",
        "tl_timing",
        "convertible_bond",
        "data_quality",
        "risk_review",
        "daily_report",
        "clarification",
    }
    RULE_DEPENDENT_TOOLS = {
        "strategy_diagnostics",
        "etf_signals",
        "etf_watchlist",
        "etf_single_asset",
        "etf_multi_assets",
        "etf_strategy_comparison",
        "tl_state",
        "convertible_rankings",
        "convertible_detail",
        "risk_summary",
    }

    def __init__(self, registry: ResearchToolRegistry, reviewer: EvidenceAccuracyReviewer | None = None) -> None:
        self.registry = registry
        self.reviewer = reviewer or EvidenceAccuracyReviewer()

    def prepare(
        self,
        question: str,
        routed_intent: ChatIntent,
        memory_context: dict[str, Any],
        report_date: str,
        model_config: dict[str, Any],
    ) -> AgentPreparation:
        steps: list[AgentStep] = []
        tools: list[ToolResult] = []
        executed_names: list[str] = []
        executed_calls: set[tuple[str, str]] = set()
        intent = routed_intent
        last_observation: dict[str, Any] = {
            "status": "start",
            "message": "尚未调用工具，请判断完成问题需要的第一项证据。",
        }
        provider = str(model_config.get("provider") or "local")
        model = str(model_config.get("primary_model") or "--")
        planner_reason = "react_not_started"
        llm_used = False
        reflection_count = 0
        last_review: EvidenceReview | None = None
        internal_model_config = self._internal_model_config(model_config)

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            llm = generate_text(
                self._supervisor_prompt(
                    question,
                    intent,
                    memory_context,
                    report_date,
                    tools,
                    last_observation,
                    iteration,
                    len(executed_names),
                ),
                internal_model_config,
                timeout_seconds=45,
                developer_text=self._supervisor_developer_prompt(),
            )
            provider, model = llm.provider, llm.model
            if not llm.used:
                steps.append(AgentStep("ResearchSupervisorAgent", "fallback", self._human_llm_failure(llm.reason)))
                if not tools:
                    return AgentPreparation(
                        False,
                        routed_intent,
                        [],
                        steps,
                        "",
                        llm_used,
                        provider,
                        model,
                        llm.reason,
                        agent_iterations=iteration,
                        reflection_count=reflection_count,
                    )
                return self._finalize(
                    intent,
                    tools,
                    executed_names,
                    steps,
                    report_date,
                    provider,
                    model,
                    f"react_partial_fallback:{llm.reason}",
                    True,
                    iteration,
                    reflection_count,
                )
            llm_used = True

            try:
                decision = self._parse_decision(llm.text, intent)
            except ValueError as exc:
                steps.append(AgentStep("ResearchSupervisorAgent", "replan", f"第{iteration}轮格式无效，重新规划：{exc}。"))
                last_observation = {"status": "invalid_decision", "message": str(exc)}
                planner_reason = "react_invalid_decision"
                continue

            intent = ChatIntent(decision.intent, 0.97, decision.entities)
            action_labels = {"tool": "调用工具", "clarify": "请求补充", "finish": "准备回答"}
            steps.append(
                AgentStep(
                    "ResearchSupervisorAgent",
                    "success",
                    f"第{iteration}轮·{action_labels[decision.action]}：{decision.reason or '根据现有证据决定下一步'}。",
                )
            )

            if decision.action == "clarify":
                question_text = decision.clarification_question or "请补充要查询的标的、指标或时间范围。"
                steps.append(AgentStep("ClarificationAgent", "success", "主Agent判断必要信息不足，先向用户追问。"))
                return AgentPreparation(
                    True,
                    ChatIntent("clarification", 0.99, decision.entities),
                    tools,
                    steps,
                    question_text,
                    True,
                    provider,
                    model,
                    "react_clarification",
                    last_review,
                    iteration,
                    reflection_count,
                )

            if decision.action == "finish":
                if not tools:
                    steps.append(AgentStep("EvidenceReflectionAgent", "replan", "尚无证据，不能直接结束研究。"))
                    last_observation = {
                        "status": "insufficient_evidence",
                        "message": "尚未调用任何工具。请选择工具或向用户追问。",
                    }
                    continue

                reflection = self._reflect(
                    question,
                    intent,
                    tools,
                    report_date,
                    internal_model_config,
                    executed_names,
                )
                if not reflection[0].used:
                    steps.append(AgentStep("EvidenceReflectionAgent", "fallback", "反思模型暂不可用，使用确定性数据审查收口。"))
                    return self._finalize(
                        intent,
                        tools,
                        executed_names,
                        steps,
                        report_date,
                        provider,
                        model,
                        "react_reflection_fallback",
                        True,
                        iteration,
                        reflection_count,
                    )

                reflection_count += 1
                reflection_decision = reflection[1]
                issue_text = "；".join(reflection_decision.issues[:3]) or reflection_decision.reason or "证据覆盖已检查"
                status = "success" if reflection_decision.verdict == "pass" else "replan"
                steps.append(
                    AgentStep(
                        "EvidenceReflectionAgent",
                        status,
                        f"第{reflection_count}次反思：{issue_text}。",
                    )
                )

                if reflection_decision.verdict == "clarify":
                    question_text = reflection_decision.clarification_question or "还需要你补充一个关键条件。"
                    return AgentPreparation(
                        True,
                        ChatIntent("clarification", 0.99, intent.entities),
                        tools,
                        steps,
                        question_text,
                        True,
                        provider,
                        model,
                        "react_reflection_clarification",
                        last_review,
                        iteration,
                        reflection_count,
                    )
                if reflection_decision.verdict == "pass" or reflection_count >= self.MAX_REFLECTIONS:
                    return self._finalize(
                        intent,
                        tools,
                        executed_names,
                        steps,
                        report_date,
                        provider,
                        model,
                        "react_completed",
                        True,
                        iteration,
                        reflection_count,
                    )

                decision = AgentDecision(
                    action="tool",
                    intent=intent.name,
                    entities=intent.entities,
                    tool_name=reflection_decision.tool_name,
                    arguments=reflection_decision.arguments,
                    clarification_question="",
                    reason=reflection_decision.reason or "反思发现证据缺口",
                )

            queue = self._tool_queue(decision, executed_names)
            if not queue:
                last_observation = {"status": "invalid_tool", "message": "没有可执行的工具。"}
                continue

            for call in queue:
                if len(executed_names) >= self.registry.MAX_TOOL_CALLS:
                    last_observation = {
                        "status": "tool_limit_reached",
                        "message": f"已达到{self.registry.MAX_TOOL_CALLS}个工具的上限，请基于现有证据结束。",
                    }
                    break
                arguments = self._merge_arguments(intent.entities, call.arguments)
                identity = (call.name, json.dumps(arguments, ensure_ascii=False, sort_keys=True))
                if identity in executed_calls:
                    steps.append(AgentStep("ReadOnlyToolExecutor", "replan", f"跳过重复调用：{call.name}。"))
                    last_observation = {
                        "status": "duplicate_tool_call",
                        "message": f"{call.name}及相同参数已经执行，请换工具或结束。",
                    }
                    continue
                try:
                    result = self.registry.execute(call.name, arguments)
                except ValueError as exc:
                    steps.append(AgentStep("ReadOnlyToolExecutor", "replan", f"{call.name}参数无效：{exc}。"))
                    last_observation = {
                        "status": "tool_validation_failed",
                        "tool": call.name,
                        "message": str(exc),
                    }
                    continue

                tools.append(result)
                executed_names.append(call.name)
                executed_calls.add(identity)
                steps.append(AgentStep("ReadOnlyToolExecutor", "success", f"已执行：{call.name}。"))
                last_review = self.reviewer.review([result], [call.name], report_date)
                steps.append(
                    AgentStep(
                        "EvidenceAccuracyReviewer",
                        "success" if last_review.passed else "blocked",
                        f"已审查{call.name}：阻断问题{len(last_review.issues)}项，提醒{len(last_review.warnings)}项。",
                    )
                )
                last_observation = {
                    "status": "tool_succeeded" if last_review.passed else "evidence_blocked",
                    "tool": call.name,
                    "summary": result.summary,
                    "review_issues": last_review.issues,
                    "review_warnings": last_review.warnings,
                }
                if not last_review.passed:
                    audit_tools = [*tools, last_review.as_tool_result()]
                    return AgentPreparation(
                        True,
                        intent,
                        audit_tools,
                        steps,
                        f"数据准确性审查未通过：{'；'.join(last_review.issues)}。请先刷新或补齐数据后再分析。",
                        True,
                        provider,
                        model,
                        "evidence_review_blocked",
                        last_review,
                        iteration,
                        reflection_count,
                    )

        if tools:
            steps.append(AgentStep("ResearchSupervisorAgent", "fallback", "已达到研究循环上限，使用已审查证据收口。"))
            return self._finalize(
                intent,
                tools,
                executed_names,
                steps,
                report_date,
                provider,
                model,
                "react_iteration_limit",
                llm_used,
                self.MAX_ITERATIONS,
                reflection_count,
            )
        return AgentPreparation(
            False,
            routed_intent,
            [],
            steps,
            "",
            llm_used,
            provider,
            model,
            planner_reason,
            agent_iterations=self.MAX_ITERATIONS,
            reflection_count=reflection_count,
        )

    @staticmethod
    def _internal_model_config(model_config: dict[str, Any]) -> dict[str, Any]:
        config = dict(model_config)
        economy_model = str(config.get("economy_model") or "").strip()
        if economy_model:
            config["primary_model"] = economy_model
        return config

    def _finalize(
        self,
        intent: ChatIntent,
        tools: list[ToolResult],
        executed_names: list[str],
        steps: list[AgentStep],
        report_date: str,
        provider: str,
        model: str,
        reason: str,
        llm_used: bool,
        iterations: int,
        reflections: int,
    ) -> AgentPreparation:
        evidence_tools = [tool for tool in tools if tool.tool != "evidence_accuracy_review"]
        review = self.reviewer.review(evidence_tools, executed_names, report_date)
        final_tools = [*evidence_tools, review.as_tool_result()]
        steps.append(
            AgentStep(
                "EvidenceAccuracyReviewer",
                "success" if review.passed else "blocked",
                f"最终审查{len(review.reviewed_tools)}个工具结果：阻断问题{len(review.issues)}项，提醒{len(review.warnings)}项。",
            )
        )
        clarification = ""
        if not review.passed:
            clarification = f"数据准确性审查未通过：{'；'.join(review.issues)}。请先刷新或补齐数据后再分析。"
        return AgentPreparation(
            True,
            intent,
            final_tools,
            steps,
            clarification,
            llm_used,
            provider,
            model,
            reason if review.passed else "evidence_review_blocked",
            review,
            iterations,
            reflections,
        )

    def _supervisor_prompt(
        self,
        question: str,
        intent: ChatIntent,
        memory_context: dict[str, Any],
        report_date: str,
        tools: list[ToolResult],
        last_observation: dict[str, Any],
        iteration: int,
        tool_count: int,
    ) -> str:
        payload = {
            "question": question,
            "report_date": report_date,
            "iteration": iteration,
            "tool_calls_used": tool_count,
            "tool_call_limit": self.registry.MAX_TOOL_CALLS,
            "router_hint_only": {"intent": intent.name, "entities": intent.entities},
            "memory": memory_context,
            "available_tools": self.registry.public_specs(),
            "evidence_observed": [self._tool_payload(tool) for tool in tools],
            "last_observation": last_observation,
            "allowed_intents": sorted(self.ALLOWED_INTENTS),
            "policy": [
                "你是主Agent，router_hint_only只是提示，你必须根据问题和观察结果自行决定下一步。",
                "每轮只能选择tool、clarify、finish中的一个动作；tool动作每次只调用一个白名单工具。",
                "拿到工具观察后重新判断，不要预先一次性列出全部工具。",
                "如果证据不足就继续调用工具；必要信息缺失才clarify；证据足够才finish。",
                "最好、最高但没有评价指标时必须clarify，不得擅自选指标。",
                "新闻、互联网、写库、刷新、下单和修改策略不在权限内。",
                "不得创造工具、SQL、路径、交易信号或不存在的能力。",
                "reason只写一句可公开的行动理由，不输出隐藏思维过程。",
            ],
            "output_schema": {
                "action": "tool|clarify|finish",
                "intent": "allowed intent",
                "entities": {"code": "optional", "name": "optional", "codes": "optional", "names": "optional", "asset_type": "optional", "metric": "optional"},
                "tool": "required only for tool action",
                "arguments": {},
                "clarification_question": "required only for clarify action",
                "reason": "one short public sentence",
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    def _supervisor_developer_prompt(self) -> str:
        return (
            "你是受控投研系统的主Research Agent。使用ReAct方式工作：观察现有证据，只决定下一步动作。"
            "你只能调用给定的只读白名单工具，不能访问SQL、文件、网络、账户或写操作。"
            "交易信号始终服从确定性代码。严格输出一个JSON对象，不要回答用户，不要输出思维链。"
        )

    def _reflect(
        self,
        question: str,
        intent: ChatIntent,
        tools: list[ToolResult],
        report_date: str,
        model_config: dict[str, Any],
        executed_names: list[str],
    ) -> tuple[LLMResult, ReflectionDecision]:
        payload = {
            "question": question,
            "report_date": report_date,
            "intent": asdict(intent),
            "executed_tools": executed_names,
            "remaining_tool_budget": max(self.registry.MAX_TOOL_CALLS - len(executed_names), 0),
            "available_tools": self.registry.public_specs(),
            "evidence": [self._tool_payload(tool) for tool in tools],
            "review_checklist": [
                "是否真正回答了用户问题，而不是只回答关键词",
                "具体标的、比较对象、时间范围和指标是否完整",
                "数字、资产类别、策略身份和信号状态是否有证据",
                "是否存在矛盾或需要另一个工具交叉核对",
                "是否误把历史诊断当回测，或把辅助指标当交易信号",
                "是否需要用户补充无法从工具获得的信息",
            ],
            "output_schema": {
                "verdict": "pass|tool|clarify",
                "tool": "required only when verdict=tool",
                "arguments": {},
                "clarification_question": "required only when verdict=clarify",
                "issues": ["short public issue"],
                "reason": "one short public sentence",
            },
        }
        llm = generate_text(
            json.dumps(payload, ensure_ascii=False),
            model_config,
            timeout_seconds=40,
            developer_text=(
                "你是投研证据Critic，只检查证据是否足以回答问题。"
                "如果缺证据，选择一个白名单工具；如果必须由用户提供，选择clarify；否则pass。"
                "不要回答问题，不要输出思维链，只输出JSON。"
            ),
        )
        if not llm.used:
            return llm, ReflectionDecision("pass", "", {}, "", [], "反思模型不可用")
        try:
            return llm, self._parse_reflection(llm.text)
        except ValueError:
            return llm, ReflectionDecision("pass", "", {}, "", ["反思结果格式无效，使用确定性审查"], "")

    def _parse_decision(self, text: str, current_intent: ChatIntent) -> AgentDecision:
        payload = self._extract_json(text)
        action = str(payload.get("action") or "").strip().lower()

        # Backward-compatible parsing for an older one-shot plan response.
        if not action and isinstance(payload.get("tool_calls"), list):
            if payload.get("needs_clarification"):
                action = "clarify"
            elif payload["tool_calls"]:
                action = "tool"
                first = payload["tool_calls"][0]
                if isinstance(first, dict):
                    payload["tool"] = first.get("name")
                    payload["arguments"] = first.get("arguments")
            else:
                action = "finish"
        if action not in {"tool", "clarify", "finish"}:
            raise ValueError("action必须是tool、clarify或finish")

        intent = str(payload.get("intent") or current_intent.name)
        if intent not in self.ALLOWED_INTENTS:
            raise ValueError("意图不在允许范围")
        entities = dict(current_intent.entities)
        raw_entities = payload.get("entities") if isinstance(payload.get("entities"), dict) else {}
        for key in ("code", "name", "codes", "names", "asset_type", "metric", "direction", "limit"):
            value = raw_entities.get(key)
            if value is not None and str(value).strip():
                entities[key] = str(value).strip()[:120]

        tool_name = str(payload.get("tool") or "").strip()
        if action == "tool" and not self.registry.has_tool(tool_name):
            raise ValueError(f"工具{tool_name or '--'}未授权")
        raw_arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        arguments = {str(key): str(value)[:120] for key, value in raw_arguments.items() if value is not None}
        question = str(payload.get("clarification_question") or "").strip()[:240]
        if action == "clarify" and not question:
            question = "请补充要查询的标的、指标或时间范围。"
        return AgentDecision(
            action,
            intent,
            entities,
            tool_name,
            arguments,
            question,
            str(payload.get("reason") or "").strip()[:240],
        )

    def _parse_reflection(self, text: str) -> ReflectionDecision:
        payload = self._extract_json(text)
        verdict = str(payload.get("verdict") or "pass").strip().lower()
        if verdict not in {"pass", "tool", "clarify"}:
            raise ValueError("反思结论无效")
        tool_name = str(payload.get("tool") or "").strip()
        if verdict == "tool" and not self.registry.has_tool(tool_name):
            raise ValueError("反思请求了未授权工具")
        raw_arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        arguments = {str(key): str(value)[:120] for key, value in raw_arguments.items() if value is not None}
        raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        issues = [str(value).strip()[:180] for value in raw_issues if str(value).strip()][:5]
        return ReflectionDecision(
            verdict,
            tool_name,
            arguments,
            str(payload.get("clarification_question") or "").strip()[:240],
            issues,
            str(payload.get("reason") or "").strip()[:240],
        )

    def _tool_queue(self, decision: AgentDecision, executed_names: list[str]) -> list[PlannedToolCall]:
        if decision.action != "tool" or not decision.tool_name:
            return []
        queue: list[PlannedToolCall] = []
        if decision.tool_name in self.RULE_DEPENDENT_TOOLS and "strategy_contract" not in executed_names:
            queue.append(PlannedToolCall("strategy_contract", {}))
        queue.append(PlannedToolCall(decision.tool_name, decision.arguments))
        return queue

    def _merge_arguments(self, entities: dict[str, str], arguments: dict[str, str]) -> dict[str, str]:
        merged = {
            key: value
            for key, value in entities.items()
            if key in {"code", "name", "codes", "names", "metric", "direction", "limit"} and value
        }
        merged.update(arguments)
        return merged

    def _tool_payload(self, tool: ToolResult) -> dict[str, Any]:
        return {
            "tool": tool.tool,
            "title": tool.title,
            "source": tool.source,
            "summary": tool.summary,
            "data": tool.data,
        }

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("没有JSON对象")
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("JSON格式错误") from exc
        if not isinstance(payload, dict):
            raise ValueError("结果不是对象")
        return payload

    def _human_llm_failure(self, reason: str) -> str:
        if reason in {"llm_enabled=false", "missing OPENAI_API_KEY"}:
            return "主Agent未启用，使用确定性规则问答。"
        return "主Agent暂不可用，使用确定性规则问答。"
