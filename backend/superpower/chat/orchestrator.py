from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from superpower.db import DatabaseRepository
from superpower.tools.llm import generate_text

from .access_policy import CHAT_MEMORY_PROMPT_TURNS
from .agent_runtime import AgentPreparation, ResearchAgentRuntime
from .guardrails import ChatGuardrails
from .router import ChatRouter
from .rulebook import rules_for_intent
from .schemas import AgentStep, ChatIntent, ChatRequest, ChatResponse, ChatTrace, EvidencePack, GuardrailResult
from .tools import ResearchToolbox
from .tool_registry import ResearchToolRegistry
from .trace import ChatTraceStore


class ChatOrchestrator:
    """Codex/OpenClaw-like, but tightly permissioned for investment research."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.router = ChatRouter()
        self.guardrails = ChatGuardrails()
        self.trace_store = ChatTraceStore(root_dir)

    def run(self, request: ChatRequest) -> ChatResponse:
        input_guard = self.guardrails.validate_input(request.question)
        if not input_guard.passed:
            intent = self.router.route(request.question, {})
            trace = ChatTrace.start(request, intent)
            trace.steps.append(AgentStep("InputGuardrail", "blocked", "输入未通过安全校验。"))
            trace.guardrail = input_guard
            self.trace_store.save(trace)
            return ChatResponse(
                answer=" ".join(input_guard.issues),
                intent=intent,
                steps=trace.steps,
                evidence=[],
                guardrail=input_guard,
                trace_id=trace.run_id,
                llm_used=False,
                llm_provider="local",
                llm_model="guardrail",
                llm_reason="input_guardrail_blocked",
            )

        compliance_answer = self._deterministic_compliance_answer(request.question)
        if compliance_answer:
            intent = ChatIntent("risk_review", 0.99, {})
            trace = ChatTrace.start(request, intent)
            trace.steps.append(AgentStep("ComplianceGuardrail", "success", "收益承诺类问题使用确定性合规回答。"))
            trace.guardrail = GuardrailResult(True, [], compliance_answer)
            self.trace_store.save(trace)
            return ChatResponse(
                answer=compliance_answer,
                intent=intent,
                steps=trace.steps,
                evidence=[],
                guardrail=trace.guardrail,
                trace_id=trace.run_id,
                llm_used=False,
                llm_provider="local",
                llm_model="compliance_guardrail",
                llm_reason="deterministic_compliance_answer",
            )

        dashboard = self._load_dashboard()
        repository = DatabaseRepository(self.root_dir)
        routing_question = self._question_with_short_term_memory(request.question, request.short_term_memory)
        intent = self.router.route(routing_question, dashboard)
        intent = self._enrich_intent_with_short_term_memory(request.question, intent, request.short_term_memory)
        intent = self._enrich_intent_with_database_entities(request.question, intent, repository)
        trace = ChatTrace.start(request, intent)
        trace.steps.append(AgentStep("ChatRouterAgent", "success", f"识别为 {intent.name}，置信度 {intent.confidence:.2f}。"))

        toolbox = ResearchToolbox(dashboard, repository)
        model_config = self._load_model_config()
        agent_preparation: AgentPreparation | None = None
        if self._should_prepare_agent(request, intent, model_config):
            runtime = ResearchAgentRuntime(ResearchToolRegistry(toolbox, repository))
            agent_preparation = runtime.prepare(
                request.question,
                intent,
                self._memory_context_for_prompt(request.short_term_memory),
                str(dashboard.get("reportDate", "--")),
                model_config,
            )
            trace.steps.extend(agent_preparation.steps)

        if agent_preparation and agent_preparation.planned:
            intent = agent_preparation.intent
            trace.intent = intent
            tools = agent_preparation.tools
            trace.steps.append(AgentStep("AgentEvidencePack", "success", f"Agent证据包包含 {len(tools)} 项结果。"))
        else:
            tools = toolbox.collect(intent)
            trace.steps.append(AgentStep("ResearchToolbox", "success", f"调用 {len(tools)} 个只读工具生成证据包。"))
        if intent.name == "etf_detail" and intent.entities.get("codes") and not any(
            tool.tool == "get_etf_multi_assets" for tool in tools
        ):
            tools.append(toolbox.get_etf_multi_assets(intent.entities["codes"]))
            trace.steps.append(AgentStep("MultiAssetEvidenceGuard", "success", "已补齐本轮全部ETF的逐只证据。"))
        trace.tools = tools

        strategy_params = self._strategy_params_from_tools(tools)

        evidence_pack = EvidencePack(
            report_date=str(dashboard.get("reportDate", "--")),
            intent=intent,
            rulebook=rules_for_intent(intent.name, strategy_params),
            tools=tools,
            memory_context=self._memory_context_for_prompt(request.short_term_memory),
        )

        agent_direct_answer = agent_preparation.clarification if agent_preparation and agent_preparation.planned else ""
        deterministic_answer = agent_direct_answer or self._deterministic_evidence_answer(request.question, evidence_pack)
        agent_planned = bool(agent_preparation and agent_preparation.planned)
        planner_llm_used = bool(agent_preparation and agent_preparation.planner_llm_used)
        answer_generated_by_llm = False
        if not agent_direct_answer and self._should_use_llm(request, deterministic_answer, intent.name, agent_planned):
            prompt = self._build_prompt(request.question, evidence_pack)
            answer_model_config = model_config if agent_planned else self._internal_review_model_config(model_config)
            llm = generate_text(
                prompt,
                answer_model_config,
                timeout_seconds=75 if agent_planned else 40,
                developer_text=self._developer_prompt(),
            )
            llm_used = llm.used or planner_llm_used
            llm_provider = llm.provider if llm.used else (agent_preparation.planner_provider if planner_llm_used else llm.provider)
            llm_model = llm.model if llm.used else (agent_preparation.planner_model if planner_llm_used else llm.model)
            llm_reason = llm.reason if llm.used else (
                f"answer_fallback_after_{agent_preparation.planner_reason}" if planner_llm_used and agent_preparation else llm.reason
            )
            if llm.used:
                trace.steps.append(AgentStep("LLMAnswerAgent", "success", f"{llm.provider}:{llm.model} 已基于本地证据生成解释。"))
                raw_answer = llm.text
                answer_generated_by_llm = True
            else:
                trace.steps.append(AgentStep("LLMAnswerAgent", "fallback", llm.reason))
                raw_answer = deterministic_answer or self._fallback_answer(request.question, evidence_pack, llm.reason)
        else:
            llm_used = planner_llm_used
            llm_provider = agent_preparation.planner_provider if planner_llm_used and agent_preparation else "local"
            llm_model = agent_preparation.planner_model if planner_llm_used and agent_preparation else "rule_engine_v2"
            llm_reason = (
                agent_preparation.planner_reason
                if planner_llm_used and agent_preparation
                else ("direct_evidence_answer" if deterministic_answer else "llm_disabled_by_user")
            )
            detail = (
                "Agent已完成规划和数据审查；最终数值由确定性规则直接回答，未做二次模型改写。"
                if planner_llm_used
                else "由后端规则引擎直接回答；无需调用大模型。"
            )
            trace.steps.append(AgentStep("DeterministicAnswerAgent", "success", detail))
            raw_answer = deterministic_answer or self._fallback_answer(request.question, evidence_pack, llm_reason)

        if answer_generated_by_llm and agent_planned:
            raw_answer, answer_review_step = self._review_generated_answer(
                request.question,
                raw_answer,
                evidence_pack,
                model_config,
                deterministic_answer,
            )
            trace.steps.append(answer_review_step)

        trace.llm_used = llm_used
        trace.llm_model = llm_model
        trace.llm_reason = llm_reason

        output_guard = self.guardrails.validate_output(raw_answer, intent, tools)
        trace.guardrail = output_guard
        trace.steps.append(
            AgentStep(
                "OutputGuardrail",
                "success" if output_guard.passed else "repaired",
                "输出已通过规则校验。" if output_guard.passed else "输出触发限制，已替换为保守口径。",
            )
        )
        self.trace_store.save(trace)

        return ChatResponse(
            answer=output_guard.text,
            intent=intent,
            steps=trace.steps,
            evidence=tools,
            guardrail=output_guard,
            trace_id=trace.run_id,
            llm_used=llm_used,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_reason=llm_reason,
        )

    def _strategy_params_from_tools(self, tools: list[Any]) -> dict[str, Any]:
        for tool in tools:
            if tool.tool == "get_rule_contract" and isinstance(tool.data, dict):
                params = tool.data.get("strategy_params")
                return params if isinstance(params, dict) else {}
        return {}

    def _should_prepare_agent(self, request: ChatRequest, intent: ChatIntent, model_config: dict[str, Any]) -> bool:
        if not request.allow_llm or not model_config.get("llm_enabled", False):
            return False
        if intent.name in {"conversation", "external_data_unavailable", "chat_data_scope"}:
            return False
        if intent.name in {"clarification", "risk_review"}:
            return True
        # Ranking explanations may need the supervisor to follow the ranking tool
        # with a single-asset lookup. Other clear intents already have deterministic
        # tool bundles, so running a multi-turn planner first only adds latency.
        return intent.name == "etf_ranking" and self._is_complex_question(request.question)

    def _should_use_llm(
        self,
        request: ChatRequest,
        deterministic_answer: str,
        intent_name: str = "",
        agent_planned: bool = False,
    ) -> bool:
        """Use the model only for questions that benefit from synthesis and only with user permission."""
        if intent_name == "conversation":
            return request.allow_llm
        if intent_name in {"external_data_unavailable", "clarification", "chat_data_scope"}:
            return False
        if not request.allow_llm:
            return False
        if intent_name == "etf_detail" and "这几只 ETF 的状态如下" in deterministic_answer:
            # 多标的状态核对属于确定性查询。直接返回逐只规则结果，避免模型把
            # no_entry 口语化成“进入观察”等不存在的状态，同时也显著降低等待时间。
            return False
        if agent_planned:
            if intent_name == "etf_ranking" and deterministic_answer and not self._is_complex_question(request.question):
                return False
            return self._is_complex_question(request.question) or not deterministic_answer
        if not self._is_complex_question(request.question):
            return False
        return True

    def _load_dashboard(self) -> dict[str, Any]:
        path = self.root_dir / "outputs" / "latest" / "dashboard.json"
        if not path.exists():
            raise FileNotFoundError("Missing latest dashboard data. Please refresh data first.")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_model_config(self) -> dict[str, Any]:
        path = self.root_dir / "configs" / "model_config.json"
        if not path.exists():
            return {"provider": "openai", "primary_model": "gpt-5.5", "llm_enabled": False}
        config = json.loads(path.read_text(encoding="utf-8"))
        return self._chat_model_config(config)

    def _chat_model_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply chat-only LLM overrides without changing daily report LLM config."""
        chat_config = config.get("chat") if isinstance(config.get("chat"), dict) else {}
        if not chat_config:
            return config
        merged = dict(config)
        for key, value in chat_config.items():
            if key == "opencode" and isinstance(value, dict):
                base_opencode = merged.get("opencode") if isinstance(merged.get("opencode"), dict) else {}
                merged["opencode"] = {**base_opencode, **value}
            else:
                merged[key] = value
        return merged

    def _developer_prompt(self) -> str:
        return (
            "你是本地 AI 投研工作台里的智能投研助理。"
            "你的工作方式像资深研究员：先确认问题对象，再检查本地数据覆盖，再用规则证据解释状态、风险、缺口和下一步复核重点。"
            "你有明确的金融分析思想：先看数据质量，再看趋势与动能是否同向，再看风险约束，最后才讨论动作；宁可说没有数据，也不能补猜。"
            "你只能使用工具返回的 EvidencePack 回答问题。"
            "当且仅当问题类型是 conversation 时，可以进行不涉及市场事实的自然交流和能力介绍；不得借闲聊编造行情、新闻或策略结论。"
            "你不能新增标的、改写交易信号、承诺收益、替用户下单或生成不受规则支持的建仓候选。"
            "所有买入、建仓、平仓、关注、不做交易结论必须来自 EvidencePack 中的确定性字段，不能来自你的主观判断。"
            "如果规则字段与直觉冲突，必须服从规则字段，并解释为什么规则没有触发。"
            "回答要像真人投研交流：先给直接结论，再解释原因，再提醒风险和下一步；语气自然、清楚、专业、克制、可审计。"
            "禁止表格、分割线、过度 Markdown。可以使用短段落和“1. 2. 3.”编号。"
        )

    def _investment_framework(self) -> dict[str, Any]:
        return {
            "name": "rules_first_research_framework",
            "philosophy": [
                "先判断数据是否足够，再判断信号是否满足；缺数据时不补猜。",
                "交易动作服从确定性规则，研究解释可以讨论缺口、风险和复核优先级。",
                "ETF 先看持仓路径，再看 MA5/MA10、MACD、量能是否同向确认。",
                "TL 先看周线是否硬否决，再看日线是否改善；日线不能覆盖周线风险。",
                "可转债先做风控分层，再看评分；高分不等于合格候选，弱观察和风险观察不能写成推荐。",
                "任何结论都要能回到 dashboard、SQLite、策略参数或数据质量记录。",
            ],
            "answer_style": [
                "先回答用户最关心的结论。",
                "解释当前证据，而不是泛泛讲市场常识。",
                "如果问题模糊，先用现有证据回答，再给出一个最关键的追问。",
                "如果用户问操作，改写为规则动作提示和人工复核清单，不给确定性投资建议。",
            ],
        }

    def _build_prompt(self, question: str, pack: EvidencePack) -> str:
        serializable_pack = {
            "report_date": pack.report_date,
            "intent": asdict(pack.intent),
            "memory_context": pack.memory_context,
            "investment_framework": self._investment_framework(),
            "rulebook": pack.rulebook,
            "tools": [asdict(tool) for tool in pack.tools],
        }
        wants_brief = any(token in question for token in ["简洁", "简单", "一句话", "直接说", "别太长"])
        length_instruction = (
            "用户明确要求简洁：控制在300个中文字符左右，只保留结论、两个关键原因和一个风险提醒。"
            if wants_brief
            else "默认控制在800个中文字符以内；只有用户明确要求详细报告时才展开。"
        )
        return (
            "请回答用户问题。必须严格遵守 investment_framework 和 rulebook，并只引用 tools 中的数据。"
            "回答必须按策略规则核对：先给结论，再解释规则条件是否满足，再列关键字段证据。"
            "不得使用未在 rulebook 或 Rule contract 中出现的新交易逻辑。"
            "不得用“技术偏强、趋势不错、可能机会”替代建仓条件。"
            "凡是买入、建仓、平仓、TL状态、可转债排名，都必须以 tools 中的 signal/state/rank/score 字段为准。"
            "若证据包没有数据，请明确说缺失；若只是关注池，不得说成建仓候选。"
            "回答单标的问题时必须在结论中点名标的名称；即使用户上下文很明确，也不能只回答‘没有’或省略主语。"
            "如果tools包含evidence_accuracy_review，必须先检查passed；有warnings时要在风险与缺口中说明，禁止绕过审查。"
            "如果 memory_context 提供了上一轮标的，用户说“它、这只、刚才那个”时可以沿用该标的，但必须说明沿用了上下文。"
            "如果用户要求列出数据库标的，必须完整列出 EvidencePack 里的 assets 名称和代码，不要只列关注池。"
            "如果用户问某只 ETF 今天表现，即使它不在建仓候选或关注池，也要使用 ETF single asset 工具里的 latest_bar 和 history 分析。"
            "如果用户一次询问多只ETF，必须逐只使用ETF multi-asset证据回答，不得只分析其中一只，也不得把已返回的其它标的写成缺少证据。"
            "如果用户问“怎么看、怎么操作、有没有问题”，只能输出规则动作提示、风险提示和人工复核重点，不能写建议买入或保证收益。"
            "如果证据显示没有该标的或该日期，必须明确回答没有数据，并说明需要先刷新或补充 Wind 文件。"
            "不得声称自己已经或可以执行刷新、写库、修改策略、下单等未开放动作，也不要主动征求执行这些动作的许可。"
            "不得把TL份额、可转债指标或其他资产数据写成ETF数据。"
            "复杂问题只需自然地写结论、依据和风险，不要汇报内部Agent流程，不要机械堆砌全部字段。"
            f"{length_instruction}"
            "回答末尾简短列出来源；只有确实缺少用户信息时才追问。"
            "\n\n"
            f"用户问题：{question}\n\n"
            f"EvidencePack JSON：{json.dumps(serializable_pack, ensure_ascii=False)}"
        )

    def _review_generated_answer(
        self,
        question: str,
        draft: str,
        pack: EvidencePack,
        model_config: dict[str, Any],
        deterministic_fallback: str,
    ) -> tuple[str, AgentStep]:
        payload = {
            "question": question,
            "draft_answer": draft,
            "report_date": pack.report_date,
            "intent": asdict(pack.intent),
            "evidence": [asdict(tool) for tool in pack.tools],
            "checks": [
                "每个数字、日期、代码、排名、状态和策略结论都必须能在证据中找到",
                "资产类别不能混淆，尤其不能把TL份额写成ETF份额",
                "不能把关注、辅助指标、历史诊断写成买入信号或正式回测",
                "不能承诺执行刷新、写库、修改策略、下单或其他未开放动作",
                "必须直接回答用户问题，并遵守用户对简洁程度的要求",
                "单标的回答必须明确写出标的名称；无数据时要写清是哪个标的、哪类本地数据缺失",
                "不能添加证据之外的市场原因、新闻或建议",
            ],
            "output_schema": {
                "passed": True,
                "issues": ["short public issue"],
                "revised_answer": "为空表示原文通过；不通过时给出已修正的完整回答",
            },
        }
        review = generate_text(
            json.dumps(payload, ensure_ascii=False),
            self._internal_review_model_config(model_config),
            timeout_seconds=45,
            developer_text=(
                "你是最终回答事实审查员。只根据证据检查草稿，不输出思维链。"
                "如果有任何事实、资产类别、权限或长度问题，返回修正后的完整回答。"
                "严格输出一个JSON对象。"
            ),
        )
        if not review.used:
            return draft, AgentStep("AnswerEvidenceReviewer", "fallback", "最终事实复核暂不可用，继续使用输出边界校验。")
        try:
            start = review.text.find("{")
            end = review.text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("missing json")
            result = json.loads(review.text[start : end + 1])
            if not isinstance(result, dict):
                raise ValueError("invalid json")
        except (ValueError, json.JSONDecodeError):
            return draft, AgentStep("AnswerEvidenceReviewer", "fallback", "最终事实复核格式无效，继续使用输出边界校验。")

        issues = result.get("issues") if isinstance(result.get("issues"), list) else []
        issue_text = "；".join(str(item) for item in issues[:3] if str(item).strip())
        if bool(result.get("passed")):
            anchored, repaired = self._ensure_subject_anchor(draft, pack, deterministic_fallback)
            status = "repaired" if repaired else "success"
            detail = "已补全单标的回答对象。" if repaired else "最终回答与证据、资产类别和权限边界一致。"
            return anchored, AgentStep("AnswerEvidenceReviewer", status, detail)
        revised = str(result.get("revised_answer") or "").strip()
        if revised:
            anchored, _ = self._ensure_subject_anchor(revised, pack, deterministic_fallback)
            return anchored, AgentStep("AnswerEvidenceReviewer", "repaired", f"已修正最终回答：{issue_text or '发现证据或表达偏差'}。")
        if deterministic_fallback:
            return deterministic_fallback, AgentStep("AnswerEvidenceReviewer", "repaired", "事实复核未通过，已退回确定性规则回答。")
        return draft, AgentStep("AnswerEvidenceReviewer", "fallback", f"事实复核发现问题但未返回修订：{issue_text or '未知问题'}。")

    @staticmethod
    def _internal_review_model_config(model_config: dict[str, Any]) -> dict[str, Any]:
        config = dict(model_config)
        economy_model = str(config.get("economy_model") or "").strip()
        if economy_model:
            config["primary_model"] = economy_model
        return config

    def _ensure_subject_anchor(
        self,
        answer: str,
        pack: EvidencePack,
        deterministic_fallback: str,
    ) -> tuple[str, bool]:
        name = str(pack.intent.entities.get("name") or "").strip()
        if not name or name in answer:
            return answer, False
        stripped = answer.strip().rstrip("。")
        no_data_shortcuts = {"没有", "无", "无数据", "没有数据", "查不到", "未查到"}
        if stripped in no_data_shortcuts and deterministic_fallback:
            return deterministic_fallback, True
        code = str(pack.intent.entities.get("code") or "").strip()
        subject = f"{name}（{code}）" if code else name
        return f"{subject}：{answer.strip()}", True

    def _question_with_short_term_memory(self, question: str, memory: dict[str, Any]) -> str:
        last_asset = self._last_memory_asset(memory)
        if not last_asset or not self._question_has_reference(question):
            return question
        name = str(last_asset.get("name") or "")
        code = str(last_asset.get("code") or "")
        asset_type = str(last_asset.get("asset_type") or "")
        suffix = " ".join(part for part in [name, code, asset_type] if part)
        return f"{question}（上下文标的：{suffix}）" if suffix else question

    def _enrich_intent_with_short_term_memory(self, question: str, intent: ChatIntent, memory: dict[str, Any]) -> ChatIntent:
        if intent.entities.get("code") or intent.entities.get("name"):
            return intent
        if not self._question_has_reference(question):
            return intent
        last_asset = self._last_memory_asset(memory)
        if not last_asset:
            return intent
        entities = dict(intent.entities)
        for key in ("code", "name", "asset_type"):
            if last_asset.get(key):
                entities[key] = str(last_asset[key])
        asset_type = str(entities.get("asset_type") or "")
        if asset_type == "ETF":
            intent_name = "etf_detail"
        elif asset_type == "TL":
            intent_name = "tl_timing"
        elif asset_type == "CONVERTIBLE":
            intent_name = "convertible_bond"
        else:
            intent_name = intent.name
        entities["from_short_term_memory"] = "true"
        return ChatIntent(intent_name, max(intent.confidence, 0.91), entities)

    def _memory_context_for_prompt(self, memory: dict[str, Any]) -> dict[str, Any]:
        last_asset = self._last_memory_asset(memory)
        turns = memory.get("turns") if isinstance(memory, dict) else []
        if not isinstance(turns, list):
            turns = []
        return {
            "enabled": bool(memory),
            "last_asset": last_asset,
            "last_intent": memory.get("lastIntent") if isinstance(memory, dict) else None,
            "recent_turns": turns[-CHAT_MEMORY_PROMPT_TURNS:],
            "policy": [
                "短期记忆只用于理解本轮对话指代，不是交易信号。",
                "如果沿用上一轮标的，需要在回答中说明。",
                "用户点击清除记忆后，不得继续使用历史上下文。",
            ],
        }

    def _last_memory_asset(self, memory: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(memory, dict):
            return {}
        asset = memory.get("lastAsset")
        return asset if isinstance(asset, dict) else {}

    def _question_has_reference(self, question: str) -> bool:
        return any(token in question for token in ["它", "这只", "这个", "刚才", "上面", "该标的", "该ETF", "该转债", "他"])

    def _fallback_answer(self, question: str, pack: EvidencePack, reason: str) -> str:
        if pack.intent.name == "conversation":
            if reason == "llm_disabled_by_user":
                return "AI自然对话尚未开启。请打开页面里的AI开关后再聊天；关闭AI时，系统只回答本地数据和策略规则支持的投研问题。"
            return "AI自然对话暂时不可用，请检查模型和Key连接状态。规则信号不受影响，仍可继续查询ETF、TL和可转债。"
        summaries = {tool.tool: tool for tool in pack.tools}
        deterministic = self._deterministic_evidence_answer(question, pack)
        if deterministic:
            return deterministic
        daily = summaries.get("get_daily_summary")
        tl = summaries.get("get_tl_state")
        etf = summaries.get("get_etf_signals")
        watch = summaries.get("get_etf_watchlist")

        lines = [f"当前 LLM 未完成调用，系统使用确定性证据包回答。原因：{reason}"]
        if self._is_complex_question(question):
            tool_titles = "、".join(tool.title for tool in pack.tools[:6]) or "本地日报摘要"
            lines.append(
                "分析过程（可审计版）：1. 先由 ChatRouterAgent 判断问题类型；"
                f"2. 再读取 {tool_titles}；"
                "3. 然后按系统 ETF/TL/可转债规则核对信号字段；"
                "4. 最后由 OutputGuardrail 检查是否把关注池误写成建仓、是否新增了规则外判断。"
            )
        if daily:
            lines.append(daily.summary)
        if etf:
            lines.append(etf.summary)
        if watch:
            lines.append(watch.summary)
        if tl:
            lines.append(tl.summary)
        lines.append("交易信号以策略信号页为准，AI 只解释不改写。")
        return "\n\n".join(lines)

    def _deterministic_evidence_answer(self, question: str, pack: EvidencePack) -> str:
        text = question.lower()
        tools = {tool.tool: tool for tool in pack.tools}

        if pack.intent.name == "conversation":
            return ""

        if pack.intent.name == "external_data_unavailable":
            return (
                "当前系统没有接入新闻或互联网数据源，所以不能回答最新新闻。"
                "它现在只能分析已经导入本地数据库的ETF、TL、可转债和策略结果。"
            )

        if pack.intent.name == "clarification":
            return "我没理解你想查哪一项。你可以直接说：某只ETF怎么样、当前TL状态、可转债前30名，或者今天有哪些策略信号。"

        chat_scope_answer = self._chat_data_scope_answer(pack)
        if chat_scope_answer:
            return chat_scope_answer

        data_quality_answer = self._data_quality_answer(pack)
        if data_quality_answer:
            return data_quality_answer

        etf_signal_answer = self._etf_signal_list_answer(pack)
        if etf_signal_answer:
            return etf_signal_answer

        daily_answer = self._daily_report_answer(pack)
        if daily_answer:
            return daily_answer

        risk_answer = self._risk_review_answer(pack)
        if risk_answer:
            return risk_answer

        etf_ranking_answer = self._etf_ranking_answer(pack)
        if etf_ranking_answer:
            return etf_ranking_answer

        etf_strategy_comparison = self._etf_strategy_comparison_answer(pack)
        if etf_strategy_comparison:
            return etf_strategy_comparison

        rule_contract = tools.get("get_rule_contract")
        params = {}
        if rule_contract and isinstance(rule_contract.data, dict):
            params = rule_contract.data.get("strategy_params") or {}

        strategy_answer = self._strategy_diagnosis_answer(pack, rule_contract)
        if strategy_answer:
            return strategy_answer

        missing_etf_answer = self._missing_etf_data_answer(pack)
        if missing_etf_answer:
            return missing_etf_answer

        multi_etf_answer = self._multi_etf_diagnosis_answer(pack)
        if multi_etf_answer:
            return multi_etf_answer

        etf_asset_answer = self._single_etf_diagnosis_answer(question, pack, params)
        if etf_asset_answer:
            return etf_asset_answer

        convertible_answer = self._single_convertible_diagnosis_answer(pack)
        if convertible_answer:
            return convertible_answer

        convertible_rank_answer = self._convertible_rank_answer(question, pack)
        if convertible_rank_answer:
            return convertible_rank_answer

        tl_answer = self._tl_diagnosis_answer(pack)
        if tl_answer:
            return tl_answer

        if pack.intent.name == "strategy_params":
            strategy_param_answer = self._strategy_param_answer(question, params)
            if strategy_param_answer:
                return strategy_param_answer

        if self._asks_etf_count(text):
            inventory = tools.get("get_database_inventory")
            daily = tools.get("get_daily_summary")
            counts = {}
            if inventory and isinstance(inventory.data, dict):
                counts = inventory.data.get("assetCounts") or {}
            summary_rows = daily.data if daily and isinstance(daily.data, list) else []
            etf_total = self._fmt_count(counts.get("ETF"))
            buy_count = self._fmt_count(self._summary_value(summary_rows, "ETF建仓候选数量"))
            watch_count = self._fmt_count(self._summary_value(summary_rows, "ETF关注池数量"))
            sell_count = self._fmt_count(self._summary_value(summary_rows, "ETF平仓提示数量"))
            return (
                f"截至报告日期 {pack.report_date}，当前数据库里的 ETF 标的一共 {etf_total} 只。\n\n"
                f"今天策略结果是：ETF 建仓候选 {buy_count} 只，关注池 {watch_count} 只，平仓提示 {sell_count} 只。\n\n"
                "这里的“ETF 标的一共多少”指本地模板纳入并已入库的 ETF 数量；"
                "建仓候选、关注池、平仓提示是按今日规则筛选后的结果，不是一回事。"
            )

        if self._asks_etf_signal_explanation(text):
            etf_tool = tools.get("get_etf_signals")
            watch_tool = tools.get("get_etf_watchlist")
            buy_candidates = []
            sell_alerts = []
            watchlist = []
            if etf_tool and isinstance(etf_tool.data, dict):
                buy_candidates = etf_tool.data.get("buy_candidates") or []
                sell_alerts = etf_tool.data.get("sell_alerts") or []
            if watch_tool and isinstance(watch_tool.data, dict):
                watchlist = watch_tool.data.get("watchlist") or []
            buy_volume = params.get("etf", {}).get("buy_volume_ratio_min", "--")
            return (
                f"结论：截至报告日期 {pack.report_date}，今日 ETF 建仓候选为 {len(buy_candidates)} 只，"
                f"关注池为 {len(watchlist)} 只，平仓提示为 {len(sell_alerts)} 只。\n\n"
                "分析过程：1. 系统先把问题归为 ETF 规则解释类问题；"
                "2. 读取 Daily summary、ETF signals、ETF watchlist 和 Rule contract；"
                "3. 按系统规则核对建仓A和建仓B，不用模型自行发明交易逻辑；"
                "4. 最后检查回答是否把关注池误写成建仓候选，或把未满足条件写成建仓候选。\n\n"
                f"关键规则：建仓A要求未持仓、MA5今日上穿MA10、MACD柱改善、量能倍数达到 {buy_volume}；"
                f"建仓B要求未持仓、DIF上穿DEA、MA5高于MA10、收盘价高于MA20、量能倍数达到 {buy_volume}。"
                "MA5高于MA20只能作为增强项，不能替代MA5上穿MA10。\n\n"
                "关键证据：ETF signals 当前没有返回 buy_candidates；"
                f"ETF watchlist 当前返回 {len(watchlist)} 条；"
                f"ETF sell_alerts 当前返回 {len(sell_alerts)} 条。"
                "因此系统不能给出ETF建仓候选，只能说当前没有满足完整建仓条件的标的。\n\n"
                "限制与下一步：如果你刚修改过量能阈值或其他策略参数，需要点击一键刷新后，"
                "建仓候选、关注池和日报才会按新参数重新计算。AI问答只解释当前已入库和当前配置证据，不改写信号。"
            )

        if "可转债" in question or "转债" in question:
            if any(token in question for token in ["多少", "几个", "数量", "有多少", "目前"]):
                cb_tool = tools.get("get_convertible_top10")
                if cb_tool and isinstance(cb_tool.data, dict):
                    raw_rows = self._fmt_count(cb_tool.data.get("raw_rows"))
                    candidates = self._fmt_count(cb_tool.data.get("ranked_candidates"))
                    top10 = self._fmt_count(cb_tool.data.get("top10_count"))
                    db_count = self._fmt_count(cb_tool.data.get("database_ranked_count"))
                    return (
                        f"截至报告日期 {pack.report_date}，可转债数据口径有三层：\n\n"
                        f"1. Excel 原始有效可转债行数：{raw_rows} 条。\n"
                        f"2. 经过价格、评级、强赎、YTM、溢价率等风控过滤后的正常候选：{candidates} 条。\n"
                        f"3. 每日报告展示的可转债 Top10：{top10} 条。\n\n"
                        f"SQLite 当前保存的可转债排序快照样本为 {db_count} 条。"
                    )

        return ""

    def _etf_signal_list_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name not in {"etf_entry", "etf_exit"}:
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_etf_signals"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        key = "buy_candidates" if pack.intent.name == "etf_entry" else "sell_alerts"
        label = "建仓候选" if pack.intent.name == "etf_entry" else "平仓提示"
        rows = data.get(key) if isinstance(data.get(key), list) else []
        if not rows:
            return f"截至报告日期 {pack.report_date}，当前没有 ETF {label}。这是规则计算结果，不代表之后不会变化。"
        details = []
        for index, row in enumerate(rows, start=1):
            name = row.get("name") or "--"
            code = row.get("code") or "--"
            score = self._fmt_metric(row.get("score"))
            reason = str(row.get("reason") or row.get("signal_reason") or "规则条件已触发")
            details.append(f"{index}. {name}（{code}），强弱分 {score}；{reason}")
        caution = (
            "建仓候选是当日规则信号，不等于次日必须买入；仍需结合成交价格和风险承受能力复核。"
            if pack.intent.name == "etf_entry"
            else "平仓提示来自当日规则状态，不代表系统会自动执行交易。"
        )
        return f"截至报告日期 {pack.report_date}，ETF {label}共 {len(rows)} 只：\n\n" + "\n".join(details) + f"\n\n{caution}"

    def _daily_report_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "daily_report":
            return ""
        tools = {item.tool: item for item in pack.tools}
        etf_data = tools.get("get_etf_signals").data if tools.get("get_etf_signals") and isinstance(tools.get("get_etf_signals").data, dict) else {}
        watch_data = tools.get("get_etf_watchlist").data if tools.get("get_etf_watchlist") and isinstance(tools.get("get_etf_watchlist").data, dict) else {}
        tl_data = tools.get("get_tl_state").data if tools.get("get_tl_state") and isinstance(tools.get("get_tl_state").data, dict) else {}
        cb_data = tools.get("get_convertible_top10").data if tools.get("get_convertible_top10") and isinstance(tools.get("get_convertible_top10").data, dict) else {}
        quality_data = tools.get("get_data_quality").data if tools.get("get_data_quality") and isinstance(tools.get("get_data_quality").data, dict) else {}
        tl_today = tl_data.get("today") if isinstance(tl_data.get("today"), list) else []
        tl_row = tl_today[0] if tl_today else {}
        tl_state = tl_row.get("display_status") or tl_row.get("state") or "暂无状态"
        quality_rows = quality_data.get("quality") if isinstance(quality_data.get("quality"), list) else []
        warning_count = self._quality_warning_count(quality_data, quality_rows)
        return (
            f"截至报告日期 {pack.report_date}：ETF 建仓候选 {len(etf_data.get('buy_candidates') or [])} 只，"
            f"关注池 {len(watch_data.get('watchlist') or [])} 只，平仓提示 {len(etf_data.get('sell_alerts') or [])} 只；"
            f"TL 当前为“{tl_state}”；可转债合格 Top 候选 {self._fmt_count(cb_data.get('top10_count'))} 只。\n\n"
            f"数据质检有 {warning_count} 项提醒。交易结论以各策略信号页为准，日报只汇总当前已计算结果。"
        )

    def _risk_review_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "risk_review":
            return ""
        tools = {item.tool: item for item in pack.tools}
        etf_data = tools.get("get_etf_signals").data if tools.get("get_etf_signals") and isinstance(tools.get("get_etf_signals").data, dict) else {}
        tl_data = tools.get("get_tl_state").data if tools.get("get_tl_state") and isinstance(tools.get("get_tl_state").data, dict) else {}
        cb_data = tools.get("get_convertible_top10").data if tools.get("get_convertible_top10") and isinstance(tools.get("get_convertible_top10").data, dict) else {}
        quality_data = tools.get("get_data_quality").data if tools.get("get_data_quality") and isinstance(tools.get("get_data_quality").data, dict) else {}
        tl_today = tl_data.get("today") if isinstance(tl_data.get("today"), list) else []
        tl_row = tl_today[0] if tl_today else {}
        tl_state = tl_row.get("display_status") or tl_row.get("state") or "暂无状态"
        quality_rows = quality_data.get("quality") if isinstance(quality_data.get("quality"), list) else []
        warning_count = self._quality_warning_count(quality_data, quality_rows)
        return (
            f"当前跨资产风险概览（截至 {pack.report_date}）：\n\n"
            f"1. ETF：建仓候选 {len(etf_data.get('buy_candidates') or [])} 只，平仓提示 {len(etf_data.get('sell_alerts') or [])} 只；候选不等于必须交易。\n"
            f"2. TL：当前状态为“{tl_state}”，没有确定性建仓信号时不能升级为买入。\n"
            f"3. 可转债：合格 Top 候选 {self._fmt_count(cb_data.get('top10_count'))} 只，风险观察 {len(cb_data.get('risk_watch') or [])} 只。\n\n"
            f"数据质检另有 {warning_count} 项提醒，日期或字段缺口会降低结论置信度，但不会由 AI 擅自改变原信号。"
        )

    def _chat_data_scope_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "chat_data_scope":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_chat_data_scope"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
        limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}

        def coverage_line(label: str, key: str) -> str:
            row = coverage.get(key) if isinstance(coverage.get(key), dict) else {}
            count = self._fmt_count(row.get("assetCount"))
            records = self._fmt_count(row.get("recordCount"))
            start = row.get("startDate") or "--"
            end = row.get("endDate") or "--"
            return f"{label}：{count}只，{records}条记录，{start} 至 {end}"

        return (
            "结论：AI不会直接访问整个数据库。后端先按白名单读取和计算，再把裁剪后的证据包交给AI解释。\n\n"
            f"当前本地数据覆盖：\n1. {coverage_line('ETF', 'ETF')}。\n"
            f"2. {coverage_line('TL', 'TL')}。\n"
            f"3. {coverage_line('可转债', 'CONVERTIBLE')}。\n\n"
            "单次问答上限：\n"
            f"- {limits.get('etf_detail', '--')}；{limits.get('etf_strategy_comparison', '--')}。\n"
            f"- {limits.get('tl', '--')}。\n"
            f"- {limits.get('convertible_bond', '--')}。\n"
            f"- {limits.get('memory', '--')}。\n\n"
            "不能访问：互联网和新闻、任意本地文件、交易账户和下单接口；也不能修改策略、评分、排名或交易信号。"
        )

    def _data_quality_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "data_quality":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_data_quality"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        rows = data.get("quality") if isinstance(data.get("quality"), list) else []
        visible_warnings = [
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("status") or "").upper() not in {"OK", "INFO", "SUCCESS"}
        ]
        warning_rows = data.get("warning_rows") if isinstance(data.get("warning_rows"), list) else visible_warnings
        warnings = [row for row in warning_rows if isinstance(row, dict)]
        total_count = self._coerce_nonnegative_int(data.get("total_count"), len(rows))
        warning_count = self._coerce_nonnegative_int(data.get("warning_count"), len(visible_warnings))
        if total_count == 0:
            return "当前没有读取到数据质检结果，请先确认日报数据是否已经生成。"
        if warning_count == 0:
            return f"截至报告日期 {pack.report_date}，本次 {total_count} 项数据质检均未发现需要处理的问题。"
        details = []
        for row in warnings[:6]:
            item = row.get("item") or row.get("check") or row.get("name") or "未命名检查"
            value = row.get("value")
            message = row.get("message") or row.get("detail") or ""
            suffix = f"：{value}" if value not in (None, "") else (f"：{message}" if message else "")
            details.append(f"{item}{suffix}")
        return (
            f"截至报告日期 {pack.report_date}，共检查 {total_count} 项，其中 {warning_count} 项需要关注。\n\n"
            f"主要提醒：{'；'.join(details)}。\n\n"
            "这些是数据完整性或日期口径提醒，不等同于策略风险；测试文件日期不同等已知情况可以人工确认后忽略。"
        )

    @staticmethod
    def _coerce_nonnegative_int(value: object, fallback: int) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return fallback

    def _quality_warning_count(self, data: dict[str, object], rows: list[object]) -> int:
        fallback = sum(
            str(row.get("status") or "").upper() not in {"OK", "INFO", "SUCCESS", "PASS"}
            for row in rows
            if isinstance(row, dict)
        )
        return self._coerce_nonnegative_int(data.get("warning_count"), fallback)

    def _etf_ranking_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "etf_ranking":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_etf_ranking"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        metric = str(data.get("metric") or "")
        if not metric:
            return (
                "ETF没有唯一的“最好”，还需要指定比较指标。你想看哪一种：强弱分、收盘价、量能倍数，还是份额变化？\n\n"
                "例如可以问：‘强弱分最高的 ETF’或‘收盘价最高的 ETF’。"
            )
        rows = data.get("rows") or []
        metric_label = str(data.get("metric_label") or metric)
        if not rows:
            return f"当前 ETF 数据里没有可用于比较“{metric_label}”的有效值。"

        direction = str(data.get("direction") or "desc")
        first = rows[0]
        name = str(first.get("name") or "--")
        code = str(first.get("code") or "--")
        value = self._fmt_metric(first.get("metric_value"))
        direction_label = "最低" if direction == "asc" else "最高"
        lines = [
            f"截至报告日期 {pack.report_date}，{metric_label}{direction_label}的 ETF 是{name}（{code}），{metric_label}为 {value}。"
        ]
        if len(rows) > 1:
            ranking = "；".join(
                f"{index}. {row.get('name') or '--'}（{row.get('code') or '--'}）{self._fmt_metric(row.get('metric_value'))}"
                for index, row in enumerate(rows, start=1)
            )
            lines.append(f"按同一口径排序：{ranking}。")
        if metric == "close":
            lines.append("提醒：收盘价只是每份基金的价格，不代表趋势更强或收益更好；如果想看策略强弱，应按强弱分排序。")
        elif metric == "vol_ratio60":
            lines.append("这里比较的是当日成交量相对前60日均量的倍数，不是绝对成交额。")
        elif metric == "share_change":
            lines.append("份额变化属于资金申购赎回辅助信息，不直接等同于买入信号。")
        else:
            lines.append("强弱分用于横向排序，不等同于建仓信号；是否入场仍以策略触发状态为准。")
        return "\n\n".join(lines)

    def _etf_strategy_comparison_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "etf_strategy_comparison":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_etf_strategy_comparison"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        if not data.get("available"):
            return f"暂时不能完成双策略对照：{data.get('reason') or '缺少该ETF的完整日频历史'}。"
        decisions = {str(item.get("strategy_id")): item for item in data.get("decisions") or []}
        legacy = decisions.get("legacy_v1") or {}
        v2 = decisions.get("trend_pullback_v2") or {}
        name = str(data.get("name") or "该ETF")
        code = str(data.get("code") or "--")

        legacy_state = "触发建仓候选" if legacy.get("buy_candidate") else "进入关注" if legacy.get("watch_candidate") else "未触发"
        v2_medium = self._etf_medium_status_label(v2.get("medium_status"))
        v2_short = self._etf_short_status_label(v2.get("short_entry_status"))
        both_support_entry = bool(legacy.get("buy_candidate") and v2.get("buy_candidate"))
        conclusion = (
            "两套策略都支持当前入场"
            if both_support_entry
            else "两套策略目前都不支持入场"
            if not legacy.get("buy_candidate") and not v2.get("buy_candidate")
            else "两套策略结论不一致，需要按所选策略执行"
        )
        legacy_reason = self._humanize_legacy_reason(str(legacy.get("short_entry_reason") or "未返回具体原因"))
        v2_hits = self._etf_v2_hit_labels(v2.get("rule_hits") or [])
        v2_reason = "、".join(v2_hits) if v2_hits else str(v2.get("medium_reason") or v2.get("short_entry_reason") or "未返回具体原因")
        metrics = legacy.get("metrics") if isinstance(legacy.get("metrics"), dict) else {}
        close = self._fmt_metric(metrics.get("close"))
        ma5 = self._fmt_metric(metrics.get("ma5"))
        ma10 = self._fmt_metric(metrics.get("ma10"))
        ma20 = self._fmt_metric(metrics.get("ma20"))
        volume = self._fmt_metric(metrics.get("vol_ratio60", metrics.get("volume_ratio_60")))
        macd = self._fmt_metric(metrics.get("macd_hist"))
        return (
            f"结论：不是说{name}本身‘不好’，而是截至 {data.get('as_of') or pack.report_date}，{conclusion}。\n\n"
            f"原策略 v1：{legacy_state}。主要缺口是{legacy_reason}。MACD柱和量能即使有所改善，也不能替代均线条件。\n\n"
            f"趋势回踩 2.0：中期为“{v2_medium}”，短期为“{v2_short}”。当前关键限制是{v2_reason}，所以还没有进入突破确认或回踩确认阶段。\n\n"
            f"当前数据：收盘 {close}，MA5 {ma5}，MA10 {ma10}，MA20 {ma20}，MACD柱 {macd}，量能倍数 {volume}。\n\n"
            "怎么观察：先看 MA20 是否走平、周MACD是否停止走弱，再看 MA5 上穿 MA10 和价格站回 MA20。"
            "原策略侧重当日触发，2.0先检查中期趋势，因此2.0会更保守。"
        )

    def _etf_medium_status_label(self, value: Any) -> str:
        return {
            "not_applicable": "不适用",
            "do_not_participate": "不参与",
            "trend_not_confirmed": "趋势未确认",
            "trend_confirmed": "趋势已确认",
            "data_unavailable": "数据不足",
        }.get(str(value or ""), str(value or "--"))

    def _etf_short_status_label(self, value: Any) -> str:
        return {
            "no_entry": "无入场",
            "close_watch": "密切观察",
            "overheated_do_not_chase": "过热不追",
            "waiting_confirmation": "等待确认",
            "waiting_pullback": "等待回踩",
            "can_enter": "可考虑入场",
            "data_unavailable": "数据不足",
        }.get(str(value or ""), str(value or "--"))

    def _etf_v2_hit_labels(self, values: list[Any]) -> list[str]:
        labels = {
            "ma20_slope_down": "MA20仍向下",
            "weekly_macd_green_widening": "周MACD绿柱扩大",
            "weekly_macd_red_weakening": "周MACD红柱缩短",
        }
        return [labels.get(str(value), str(value)) for value in values]

    def _humanize_legacy_reason(self, value: str) -> str:
        checks = []
        if "MA5今日未上穿MA10" in value:
            checks.append("MA5尚未上穿MA10")
        if "MA5未高于MA10" in value:
            checks.append("MA5仍低于MA10")
        if "收盘价未高于MA20" in value:
            checks.append("收盘尚未站上MA20")
        if checks:
            return "、".join(dict.fromkeys(checks))
        return value.replace("未触发建仓候选：", "").replace("规则A缺", "").replace("规则B缺", "")

    def _strategy_diagnosis_answer(self, pack: EvidencePack, rule_contract: Any) -> str:
        if pack.intent.name not in {"strategy_comparison", "strategy_stability", "historical_diagnostics"}:
            return ""
        contract = rule_contract.data if rule_contract and isinstance(rule_contract.data, dict) else {}
        etf_strategy = contract.get("etf_strategy") if isinstance(contract.get("etf_strategy"), dict) else {}
        active = str(etf_strategy.get("active_strategy") or "--")
        diagnostics_tool = next((tool for tool in pack.tools if tool.tool == "get_strategy_diagnostics"), None)
        diagnostic_rows = []
        boundary = []
        if diagnostics_tool and isinstance(diagnostics_tool.data, dict):
            diagnostic_rows = diagnostics_tool.data.get("rows") or []
            boundary = diagnostics_tool.data.get("boundary") or []

        ten_day = [
            row
            for row in diagnostic_rows
            if int(row.get("horizon") or 0) == 10 and str(row.get("state_type") or "can_enter") == "can_enter"
        ]
        metric_lines = []
        route_labels = {"breakout_confirmation": "突破确认", "pullback_confirmation": "回踩确认"}
        for row in ten_day[:4]:
            strategy_id = row.get("strategy_id") or "--"
            strategy_label = "原策略" if strategy_id == "legacy_v1" else "2.0"
            route = f"（{route_labels.get(str(row.get('entry_route')), row.get('entry_route'))}）" if row.get("entry_route") else ""
            samples = row.get("complete_horizon_count", row.get("sample_count", "--"))
            positive = row.get("positive_return_rate", row.get("positive_rate"))
            mean_return = row.get("mean_return", row.get("average_return"))
            adverse = row.get("mean_maximum_adverse_excursion", row.get("average_max_adverse_excursion"))
            false_reversal = row.get("false_reversal_10d_rate", row.get("false_reversal_rate"))
            metric_lines.append(
                f"{strategy_label}{route}：样本{samples}，正收益{self._fmt_percent(positive)}，"
                f"平均收益{self._fmt_percent(mean_return)}，平均最大不利波动{self._fmt_percent(adverse)}，"
                f"假反转{self._fmt_percent(false_reversal)}"
            )
        metrics = "；".join(metric_lines) if metric_lines else "当前没有可用的10日历史诊断汇总"

        if pack.intent.name == "strategy_comparison":
            return (
                f"这是两套ETF策略的通用比较，不是某只ETF的当前判断。当前默认ETF策略是 {active}。"
                "原策略偏向当日均线、MACD和量能共振；2.0增加了中期趋势确认、过热过滤以及突破/回踩两种入场路径。\n\n"
                f"现有历史诊断：{metrics}。\n\n"
                "不能只看一项正收益比例就断定哪个更好。2.0在设计上减少信号、强调入场质量，但现有诊断没有证明它整体优于原策略。"
                "如果要比较某只ETF今天的判断，请直接说标的名称，例如“黄金ETF双策略比较”。"
            )
        if pack.intent.name == "strategy_stability":
            return (
                f"工程上目前规则是稳定可复现的：当前启用 {active}，信号由固定代码和配置生成，AI不改信号。\n\n"
                f"历史证据方面：{metrics}。\n\n"
                "但这还不能证明策略能稳定盈利。现有数据属于信号事件诊断，不是包含仓位、交易成本和组合净值的完整回测；"
                "因此可以说规则运行稳定，不能说收益已经被验证稳定。"
            )
        return (
            f"历史诊断是回看每次信号出现后1、3、5、10、20个交易日的表现。当前10日摘要：{metrics}。\n\n"
            "主要看四项：有效样本、正收益比例、平均收益、期间平均最大不利波动；假反转只在设定口径下统计。\n\n"
            f"边界：{'；'.join(str(item) for item in boundary) if boundary else '它是信号诊断，不等同于完整组合回测。'}"
        )

    def _fmt_percent(self, value: Any) -> str:
        try:
            return f"{float(value) * 100:.2f}%"
        except (TypeError, ValueError):
            return "--"

    def _missing_etf_data_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "etf_detail":
            return ""
        entities = pack.intent.entities
        if entities.get("code"):
            return ""
        name = entities.get("name")
        if not name or entities.get("asset_type") != "ETF":
            return ""
        return (
            f"当前不知道{name}的情况：最新日报和数据库里没有这只 ETF 的有效数据。\n\n"
            "系统不会用库外信息补猜，也不会编造技术指标。请先确认 Wind ETF 文件包含该标的，并重新点击一键刷新。"
        )

    def _multi_etf_diagnosis_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "etf_detail":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_etf_multi_assets"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        assets = data.get("assets") or []
        if not assets:
            return ""
        lines = [f"截至 {pack.report_date}，这几只 ETF 的状态如下："]
        observed: list[str] = []
        confirmed: list[str] = []
        neither: list[str] = []
        for item in assets:
            asset = item.get("asset") or {}
            signal = item.get("dashboard_signal") or {}
            latest = item.get("latest_bar") or {}
            name = str(signal.get("name") or asset.get("name") or asset.get("code") or "该ETF")
            code = str(signal.get("code") or asset.get("code") or "--")
            medium = str(signal.get("medium_status") or "data_unavailable")
            short = str(signal.get("short_entry_status") or "data_unavailable")
            medium_label = self._etf_medium_status_label(medium)
            short_label = self._etf_short_status_label(short)
            reason = str(signal.get("medium_reason") or signal.get("short_entry_reason") or signal.get("signal_reason") or "未返回具体原因")
            raw_hits = signal.get("rule_hits") or []
            hit_values = re.split(r"[；;,，]", raw_hits) if isinstance(raw_hits, str) else list(raw_hits)
            hit_labels = self._etf_v2_hit_labels([item for item in hit_values if item])
            if hit_labels and medium != "trend_confirmed":
                reason = f"{reason}：{'、'.join(hit_labels)}"
            close = self._fmt_metric(signal.get("close", latest.get("close")))
            lines.append(
                f"{len(lines)}. {name}（{code}）：中期“{medium_label}”，短期“{short_label}”；"
                f"收盘 {close}。{reason}"
            )
            if short == "close_watch":
                observed.append(name)
            if medium == "trend_confirmed":
                confirmed.append(name)
            if short != "close_watch" and medium != "trend_confirmed":
                neither.append(name)
        conclusion_parts = []
        if confirmed:
            conclusion_parts.append(f"趋势确认：{'、'.join(confirmed)}")
        if observed:
            conclusion_parts.append(f"密切观察：{'、'.join(observed)}")
        if neither:
            conclusion_parts.append(f"尚未进入两种状态：{'、'.join(neither)}")
        if not conclusion_parts:
            conclusion_parts.append("目前没有标的进入密切观察或趋势确认")
        lines.append(f"结论：{'；'.join(conclusion_parts)}。趋势确认不等于短期建仓，仍以短期入场状态为准。")
        lines.append("来源：最新 dashboard.etf.all_signals 与 SQLite ETF 日频指标。")
        return "\n\n".join(lines)

    def _single_etf_diagnosis_answer(self, question: str, pack: EvidencePack, params: dict[str, Any]) -> str:
        tool = next((item for item in pack.tools if item.tool == "get_etf_single_asset"), None)
        if tool is None or not isinstance(tool.data, dict):
            return ""
        dashboard_signal = tool.data.get("dashboard_signal") or {}
        latest_bar = tool.data.get("latest_bar") or {}
        history = tool.data.get("history") or []
        asset = tool.data.get("asset") or {}
        if not dashboard_signal and not latest_bar:
            code = pack.intent.entities.get("code") or str(asset.get("code", ""))
            return f"当前数据库和最新日报都没有找到 {code or '该ETF'} 的有效指标记录。请先确认 Wind ETF 文件已包含该标的，并重新点击一键刷新。"

        code = str(dashboard_signal.get("code") or latest_bar.get("code") or asset.get("code") or pack.intent.entities.get("code") or "")
        name = str(dashboard_signal.get("name") or latest_bar.get("name") or asset.get("name") or code)
        action = str(dashboard_signal.get("display_action") or self._signal_action_text(dashboard_signal) or "未触发")
        position_status = str(dashboard_signal.get("position_status") or "--")
        reason = str(dashboard_signal.get("signal_reason") or dashboard_signal.get("reason") or dashboard_signal.get("missing_condition") or "--")
        score = self._fmt_metric(dashboard_signal.get("score"))
        close = self._fmt_metric(dashboard_signal.get("close", latest_bar.get("close")))
        ma5 = self._fmt_metric(dashboard_signal.get("ma5", latest_bar.get("ma5")))
        ma10 = self._fmt_metric(dashboard_signal.get("ma10", latest_bar.get("ma10")))
        ma20 = self._fmt_metric(dashboard_signal.get("ma20", latest_bar.get("ma20")))
        ma60 = self._fmt_metric(dashboard_signal.get("ma60", latest_bar.get("ma60")))
        vol = self._fmt_metric(dashboard_signal.get("vol_ratio60", latest_bar.get("vol_ratio60")))
        macd = self._fmt_metric(dashboard_signal.get("macd_hist", latest_bar.get("macd_hist")))
        dif = self._fmt_metric((dashboard_signal.get("metrics") or {}).get("dif", latest_bar.get("dif")))
        dea = self._fmt_metric((dashboard_signal.get("metrics") or {}).get("dea", latest_bar.get("dea")))
        trade_date = str(dashboard_signal.get("date") or latest_bar.get("trade_date") or pack.report_date)[:10]
        ma_signal = str(dashboard_signal.get("ma5_ma10_signal") or "--")
        ma20_status = str(dashboard_signal.get("ma5_ma20_status") or "--")
        volume_check = str(dashboard_signal.get("volume_check") or "--")
        watch_type = str(dashboard_signal.get("watch_type") or "")
        suggestion = self._etf_action_hint(dashboard_signal, params)
        recent_line = self._etf_recent_history_line(history)

        focused_metric = self._focused_etf_metric_answer(
            question,
            name=name,
            code=code,
            trade_date=trade_date,
            close=close,
            score=score,
            vol=vol,
            macd=macd,
            action=action,
            recent_line=recent_line,
        )
        if focused_metric:
            return focused_metric

        if not self._is_complex_question(question):
            change = f"{recent_line}\n\n" if recent_line else ""
            return (
                f"{name}（{code}）最新有效数据是 {trade_date}：收盘 {close}，评分 {score}，当前规则状态为“{action}”。\n\n"
                f"{change}主要指标：MA5 {ma5}，MA10 {ma10}，MA20 {ma20}，量能倍数 {vol}，MACD柱 {macd}。\n\n"
                "这是最新已导入数据，不是实时行情；交易状态仍以策略信号页为准。"
            )

        lines = [
            f"结论：{name}（{code}）截至 {trade_date} 的今日判断是：{action}。",
            (
                f"策略状态：{dashboard_signal.get('strategy_id') or '--'} · v{dashboard_signal.get('strategy_version') or '--'}；"
                f"中期趋势 {dashboard_signal.get('medium_status') or '--'}；短期入场 {dashboard_signal.get('short_entry_status') or '--'}。"
            ),
            (
                f"中短期证据：周MACD确认 {dashboard_signal.get('weekly_macd_confirmation_check') or '--'}；"
                f"MA20走平检查 {dashboard_signal.get('ma20_flat_check') or '--'}。"
            ),
            f"持仓路径：系统当前把它识别为“{position_status}”。持仓中才检查平仓提示；空仓或已平仓才检查建仓候选和关注池。",
            (
                f"今日指标：收盘 {close}，MA5 {ma5}，MA10 {ma10}，MA20 {ma20}，MA60 {ma60}，"
                f"量能倍数 {vol}，MACD柱 {macd}，DIF {dif}，DEA {dea}，评分 {score}。"
            ),
            f"规则证据：{ma_signal}；{ma20_status}；{volume_check}。判断理由：{reason}",
        ]
        if watch_type:
            lines.append(f"关注状态：{watch_type}。这只是观察池，不等于建仓候选。")
        if dashboard_signal.get("risk_overlay_summary"):
            lines.append(f"风险辅助：{dashboard_signal.get('risk_overlay_summary')}")
        if dashboard_signal.get("risk_notes"):
            lines.append(f"风险提示：{dashboard_signal.get('risk_notes')}")
        if recent_line:
            lines.append(recent_line)
        lines.append(f"规则动作提示：{suggestion}")
        lines.append("边界：以上是确定性规则状态和历史证据解释，不保证收益，也不构成自动交易指令。")
        lines.append("来源：最新 dashboard.etf.all_signals、SQLite 日频指标、configs/strategy_params.json。")
        return "\n\n".join(lines)

    def _focused_etf_metric_answer(
        self,
        question: str,
        *,
        name: str,
        code: str,
        trade_date: str,
        close: str,
        score: str,
        vol: str,
        macd: str,
        action: str,
        recent_line: str,
    ) -> str:
        text = question.lower().replace(" ", "")
        metric_label = ""
        metric_value = ""
        if any(token in text for token in ["收盘价", "收盘", "价格"]):
            metric_label, metric_value = "收盘价", close
        elif any(token in text for token in ["评分", "分数", "强弱分"]):
            metric_label, metric_value = "强弱分", score
        elif any(token in text for token in ["量能倍数", "量能", "量比"]):
            metric_label, metric_value = "量能倍数", vol
        elif any(token in text for token in ["macd柱", "macd"]):
            metric_label, metric_value = "MACD柱", macd
        if not metric_label or self._is_complex_question(question):
            return ""
        change = f"{recent_line}\n\n" if recent_line else ""
        return (
            f"{name}（{code}）最新有效交易日是 {trade_date}，{metric_label}为 {metric_value}。\n\n"
            f"{change}当前规则状态为“{action}”。该数值来自最新已导入数据，不是实时行情。"
        )

    def _signal_action_text(self, row: dict[str, Any]) -> str:
        mapping = {
            "buy_candidate": "模型触发建仓候选",
            "sell_alert": "模型触发平仓提示",
            "watch": "进入观察池",
            "neutral": "未触发",
            "data_unavailable": "数据不足，无法判断",
        }
        return mapping.get(str(row.get("signal_type") or row.get("action") or ""), "")

    def _etf_action_hint(self, row: dict[str, Any], params: dict[str, Any]) -> str:
        action = str(row.get("action") or row.get("signal_type") or "")
        position_status = str(row.get("position_status") or "")
        threshold = self._fmt_param((params.get("etf") or {}).get("buy_volume_ratio_min"))
        if action == "buy_candidate":
            return "规则已触发建仓候选，可进入人工复核名单；是否交易仍需结合组合约束和人工判断。"
        if action == "sell_alert":
            return "规则已触发平仓提示，可进入人工复核名单；该提示只对持仓标的生效。"
        if action == "watch":
            missing = row.get("missing_condition") or "仍有条件未确认"
            return f"规则提示关注，当前缺口是：{missing}。后续重点看量能是否达到 {threshold} 以及 MACD/均线条件是否继续确认。"
        if "持仓中" in position_status:
            return "当前未触发平仓提示；继续跟踪是否收盘跌破 MA10/MA5 并伴随放量。"
        return f"当前未触发建仓候选；继续跟踪今日缺口是否修复，尤其是 MA5 上穿、MACD 改善/金叉和量能倍数是否达到 {threshold}。"

    def _etf_recent_history_line(self, history: list[Any]) -> str:
        rows = [row for row in history if isinstance(row, dict)]
        if len(rows) < 2:
            return ""
        ordered = sorted(rows, key=lambda row: str(row.get("trade_date") or row.get("date") or ""))
        latest = ordered[-1]
        previous = ordered[-2]
        close = self._to_float(latest.get("close"))
        prev_close = self._to_float(previous.get("close"))
        if close is None or prev_close in {None, 0}:
            return ""
        change = close / prev_close - 1
        direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
        return f"最近一日变化：较上一有效交易日{direction} {change * 100:.2f}%，这只是行情事实，不改变今日规则判断。"

    def _single_convertible_diagnosis_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "convertible_bond":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_convertible_detail"), None)
        if tool is None or not isinstance(tool.data, dict):
            return ""
        asset = tool.data.get("asset") or {}
        snapshot = tool.data.get("snapshot") or {}
        row = tool.data.get("source_row") or tool.data.get("dashboard_row") or snapshot.get("payload_json") or {}
        code = str(row.get("bond_code") or row.get("code") or snapshot.get("bond_code") or asset.get("code") or pack.intent.entities.get("code") or "")
        name = str(row.get("bond_name") or row.get("name") or snapshot.get("bond_name") or asset.get("name") or code or "该转债")
        if not row and not snapshot:
            return f"当前最新日报、数据库和配置的 Wind 可转债文件都没有找到{name}（{code or '--'}）的有效转债详情；系统不会用库外信息补猜。"

        qualification = self._qualification_label(str(row.get("qualification") or ""))
        eligible = "是" if row.get("eligible_for_top") is True else "否"
        reason = str(row.get("not_top_reason") or row.get("excluded_reason") or row.get("rank_reason") or tool.summary or "--")
        price = self._fmt_metric(row.get("price", snapshot.get("price")))
        premium = self._fmt_metric(row.get("conversion_premium_rate", snapshot.get("conversion_premium_rate")))
        ytm = self._fmt_metric(row.get("ytm", snapshot.get("ytm")))
        rating = str(row.get("bond_rating") or row.get("rating") or "--")
        size = self._fmt_metric(row.get("remaining_size"))
        redemption = str(row.get("redemption_status") or "--")
        base_score = self._fmt_metric(row.get("base_score", row.get("score", snapshot.get("score"))))
        grade = str(row.get("base_grade") or row.get("score_grade") or "--")
        risk = str(row.get("risk_level") or "--")
        notes = self._fmt_notes(row.get("quality_notes") or row.get("risk_flags"))
        stock_return = self._fmt_metric(row.get("stock_daily_return"))
        bond_return = self._fmt_metric(row.get("bond_daily_return"))
        premium_change = self._fmt_metric(row.get("conversion_premium_change"))
        linkage_note = str(row.get("linkage_note") or "暂无异常提示")
        auxiliary_score = self._fmt_metric(row.get("auxiliary_score", row.get("dynamic_score")))
        auxiliary_state = str(row.get("auxiliary_state") or row.get("dynamic_state") or row.get("linkage_state") or "--")
        auxiliary_note = str(row.get("auxiliary_note") or row.get("dynamic_note") or linkage_note)
        source = str(row.get("detail_source") or ("sqlite_snapshot" if snapshot else "dashboard"))

        strategy_line = (
            f"当前基础策略：原策略 v1；基础分 {base_score}，基础等级 {grade}。"
            f"动态辅助：{auxiliary_state}，辅助分 {auxiliary_score}。{auxiliary_note}"
            "动态辅助不改变资格、动作和排名。"
        )

        return "\n\n".join(
            [
                f"结论：{name}（{code or '--'}）截至 {pack.report_date} 不进入合格 Top 候选。当前分层：{qualification}；是否可进合格 Top：{eligible}。",
                f"核心原因：{reason}",
                (
                    f"当前字段：价格 {price}，转股溢价率 {premium}，YTM {ytm}，评级 {rating}，"
                    f"存续规模 {size}，强赎状态 {redemption}，基础分 {base_score}，基础等级 {grade}，风险等级 {risk}。"
                ),
                f"风险备注：{notes or '--'}",
                strategy_line,
                f"动态辅助原始值：正股 {stock_return}%，转债 {bond_return}%，溢价率变化 {premium_change} 个百分点。",
                "规则口径：可转债先做价格、评级、强赎、YTM、溢价率、规模和基本面等风控，再做候选资格分层；弱观察和风险观察不补进合格 Top。",
                f"来源：{source}、dashboard.convertible_bond、SQLite asset_master、configs/strategy_params.json。",
            ]
        )

    def _convertible_rank_answer(self, question: str, pack: EvidencePack) -> str:
        if pack.intent.name != "convertible_bond":
            return ""
        match = re.search(r"第\s*(\d{1,3})\s*名", question)
        if not match:
            return ""
        requested_rank = int(match.group(1))
        tool = next((item for item in pack.tools if item.tool == "get_convertible_top10"), None)
        data = tool.data if tool and isinstance(tool.data, dict) else {}
        universe = data.get("analysis_universe") if isinstance(data.get("analysis_universe"), list) else []
        row = next(
            (item for item in universe if isinstance(item, dict) and str(item.get("rank") or "") == str(requested_rank)),
            None,
        )
        if not row:
            return f"当前问答分析池里没有第 {requested_rank} 名记录；单次只读取前30只可转债。"
        name = row.get("name") or "--"
        code = row.get("code") or "--"
        score = self._fmt_metric(row.get("score"))
        price = self._fmt_metric(row.get("price"))
        premium = self._fmt_metric(row.get("premium_rate"))
        ytm = self._fmt_metric(row.get("ytm"))
        top_count = self._fmt_count(data.get("top10_count"))
        reason = row.get("reason") or row.get("quality_notes")
        reason_line = f"当前排名证据记录的原因是：{reason}。" if reason else "当前排名记录没有返回完整排除原因，需要继续读取该转债详情才能准确解释。"
        return (
            f"分析池第 {requested_rank} 名是{name}（{code}），价格 {price}，转股溢价率 {premium}，YTM {ytm}，评分 {score}。\n\n"
            f"它的‘第{requested_rank}名’是前30只分析池排名，不等于合格Top候选排名；当前合格Top数量为 {top_count}。"
            f"{reason_line}"
        )

    def _tl_diagnosis_answer(self, pack: EvidencePack) -> str:
        if pack.intent.name != "tl_timing":
            return ""
        tool = next((item for item in pack.tools if item.tool == "get_tl_state"), None)
        if tool is None or not isinstance(tool.data, dict):
            return ""
        rows = tool.data.get("today") or []
        if not rows:
            return f"当前最新日报没有 TL 今日状态数据；系统不能用模型猜测 TL 信号。"
        row = rows[0]
        name = str(row.get("name") or "30年国债期货TL")
        code = str(row.get("code") or "TL.CFE")
        trade_date = str(row.get("date") or pack.report_date)[:10]
        state = str(row.get("display_status") or row.get("state") or row.get("action") or "--")
        close = self._fmt_metric(row.get("收盘价") or row.get("close") or (row.get("metrics") or {}).get("close"))
        ma5 = self._fmt_metric(row.get("ma5"))
        ma10 = self._fmt_metric(row.get("ma10"))
        ma20 = self._fmt_metric(row.get("ma20"))
        ma60 = self._fmt_metric(row.get("ma60"))
        vol_ratio = self._fmt_metric(row.get("vol_ratio60"))
        daily_macd = self._fmt_metric(row.get("macd_hist") or (row.get("metrics") or {}).get("daily_macd_hist"))
        daily_j = self._fmt_metric(row.get("kdj_j") or (row.get("metrics") or {}).get("daily_kdj_j"))
        weekly_macd = self._fmt_metric(row.get("week_macd_hist") or (row.get("metrics") or {}).get("weekly_macd_hist"))
        weekly_j = self._fmt_metric(row.get("week_kdj_j") or (row.get("metrics") or {}).get("weekly_kdj_j"))
        daily_macd_reason = str(row.get("daily_macd_reason") or "--")
        daily_kdj_check = str(row.get("daily_kdj_threshold_check") or "--")
        weekly_macd_reason = str(row.get("weekly_macd_reason") or "--")
        weekly_kdj_check = str(row.get("weekly_kdj_threshold_check") or "--")
        reason = str(row.get("reason") or "--")
        rule_hits = str(row.get("rule_hits") or "")
        risk_notes = str(row.get("risk_notes") or "")
        fund_flow_note = str(row.get("fund_flow_note") or "")
        action_hint = self._tl_action_hint(row)

        lines = [
            f"结论：{name}（{code}）截至 {trade_date} 的今日状态是：{state}。",
            f"今日指标：收盘 {close}，MA5 {ma5}，MA10 {ma10}，MA20 {ma20}，MA60 {ma60}，量能倍数 {vol_ratio}。",
            f"日线证据：MACD柱 {daily_macd}，KDJ J {daily_j}；日线MACD判断：{daily_macd_reason}；日线KDJ检查：{daily_kdj_check}",
            f"周线证据：MACD柱 {weekly_macd}，KDJ J {weekly_j}；周线MACD判断：{weekly_macd_reason}；周线KDJ检查：{weekly_kdj_check}",
            f"规则结论：{reason}",
        ]
        if fund_flow_note:
            lines.append(
                "资金辅助：当日份额变化 "
                f"{self._fmt_metric(row.get('fund_share_change_daily'))} 亿份（{row.get('fund_share_daily_level') or '--'}），"
                f"近5日累计 {self._fmt_metric(row.get('fund_share_5d_sum'))} 亿份；{fund_flow_note}"
            )
        if rule_hits:
            lines.append(f"规则命中：{rule_hits}")
        lines.append(f"动作提示：{action_hint}")
        if risk_notes:
            lines.append(f"边界说明：{risk_notes}")
        lines.append("来源：最新 dashboard.tlToday、dashboard.tlRecent、SQLite 日频指标、configs/strategy_params.json。")
        return "\n\n".join(lines)

    def _tl_action_hint(self, row: dict[str, Any]) -> str:
        if row.get("buy_signal") is True or str(row.get("status") or "") == "buy":
            return "规则已触发建仓候选，可进入人工复核；是否交易仍需结合期货换月、保证金、杠杆和组合约束。"
        if row.get("no_trade_signal") is True or str(row.get("status") or "") == "no_trade":
            return "当前属于不做交易路径；周线不做交易或KDJ低位反弹条件不满足时，日线改善不能单独升级为建仓。"
        if row.get("attention_signal") is True or str(row.get("status") or "") == "attention":
            return "当前属于关注交易路径；继续观察日线/周线KDJ低位反弹条件是否补齐。"
        return "当前未触发明确建仓候选；继续按日线/周线MACD与KDJ低位反弹条件跟踪。"

    def _fmt_metric(self, value: Any) -> str:
        number = self._to_float(value)
        if number is None:
            return "--"
        if abs(number) >= 100:
            return f"{number:.2f}"
        return f"{number:.4f}".rstrip("0").rstrip(".")

    def _fmt_notes(self, value: Any) -> str:
        if isinstance(value, list):
            return "；".join(str(item) for item in value if item not in {None, ""})
        return str(value or "")

    def _qualification_label(self, value: str) -> str:
        return {
            "qualified": "合格候选",
            "top10": "合格候选",
            "weak_watch": "弱观察候选",
            "risk_watch": "风险观察",
            "ranked_candidates": "候选池",
            "excluded": "排除列表",
        }.get(value, value or "--")

    def _to_float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _asks_etf_count(self, text: str) -> bool:
        return "etf" in text and any(token in text for token in ["一共", "多少", "几个", "数量", "有多少"])

    def _strategy_param_answer(self, question: str, params: dict[str, Any]) -> str:
        text = question.lower()
        etf = params.get("etf", {}) if isinstance(params, dict) else {}
        tl = params.get("tl", {}) if isinstance(params, dict) else {}
        cb = params.get("convertible_bond", {}) if isinstance(params, dict) else {}
        risk = params.get("risk", {}) if isinstance(params, dict) else {}
        etf_weights = etf.get("score_weights", {}) if isinstance(etf, dict) else {}
        cb_weights = cb.get("score_weights", {}) if isinstance(cb, dict) else {}

        if "策略" in question and any(token in question for token in ["现在", "当前", "使用", "启用", "默认"]):
            return (
                f"当前ETF默认策略是 {etf.get('active_strategy', '--')}；"
                f"可转债默认策略是 {cb.get('active_strategy', '--')}。\n\n"
                "TL没有单独的插件切换，使用技术规则，并把30年国债ETF份额变化作为辅助观察。"
            )

        catalog = self._parameter_catalog()
        if self._asks_parameter_catalog(question):
            return self._parameter_catalog_answer(params, catalog)
        if "etf" in text and "量能" in question and "权重" not in question and "ma10" not in text and "ma5" not in text:
            buy_volume = etf.get("buy_volume_ratio_min", "--")
            sell_ma10 = etf.get("sell_ma10_volume_ratio_min", "--")
            sell_ma5 = etf.get("sell_ma5_volume_ratio_min", "--")
            return (
                f"ETF 量能相关参数有三项：\n\n"
                f"1. 建仓量能倍数：{self._fmt_param(buy_volume)}。\n"
                f"2. 跌破 MA10 平仓量能：{self._fmt_param(sell_ma10)}。\n"
                f"3. 跌破 MA5 平仓量能：{self._fmt_param(sell_ma5)}。\n\n"
                "三者的量纲一致，都是当日成交量 / 前 60 个交易日平均成交量。"
                "参数保存后会立即写入配置；要让日报和信号结果变化，需要再点击一键刷新重新计算。"
            )
        catalog_match = self._parameter_catalog_match(question, params, catalog)
        if catalog_match:
            return catalog_match

        if "etf" in text:
            if "趋势" in question and "权重" in question:
                return self._param_line("ETF 趋势权重", etf_weights.get("trend"), "用于 ETF 建仓候选排序评分；0.35 表示 35%。")
            if "macd" in text and "权重" in question:
                return self._param_line("ETF MACD 权重", etf_weights.get("macd"), "用于 ETF 建仓候选排序评分；0.25 表示 25%。")
            if "量能权重" in question:
                return self._param_line("ETF 量能权重", etf_weights.get("volume"), "用于 ETF 建仓候选排序评分；0.25 表示 25%。")
            if "份额" in question or "share" in text:
                return self._param_line("ETF 份额变化权重", etf_weights.get("share_change"), "用于 ETF 排序增强项。")
            if ("ma10" in text or "ma 10" in text) and ("平仓" in question or "卖出" in question or "跌破" in question):
                return self._param_line("ETF 跌破 MA10 平仓量能", etf.get("sell_ma10_volume_ratio_min"), "含义：收盘跌破 MA10 时，成交量相对前 60 个交易日均量达到该倍数，才触发平仓提示。")
            if ("ma5" in text or "ma 5" in text) and ("平仓" in question or "卖出" in question or "跌破" in question):
                return self._param_line("ETF 跌破 MA5 平仓量能", etf.get("sell_ma5_volume_ratio_min"), "含义：收盘跌破 MA5 时，成交量相对前 60 个交易日均量达到该倍数，才触发平仓提示。")
            if "量能" in question or "倍数" in question:
                buy_volume = etf.get("buy_volume_ratio_min", "--")
                sell_ma10 = etf.get("sell_ma10_volume_ratio_min", "--")
                sell_ma5 = etf.get("sell_ma5_volume_ratio_min", "--")
                return (
                    f"ETF 建仓量能倍数当前是 {buy_volume}。\n\n"
                    "含义：今日成交量 / 前 60 个交易日平均成交量。"
                    f"当这个倍数达到 {buy_volume} 或以上时，才算满足 ETF 建仓里的量能确认条件。\n\n"
                    f"平仓侧量能参数是：跌破 MA10 平仓量能 {sell_ma10}，跌破 MA5 平仓量能 {sell_ma5}。"
                    "参数保存后会立即写入配置；要让日报和信号结果变化，需要再点击一键刷新重新计算。"
                )

        asks_cb = any(token in question for token in ["可转债", "转债", "基本面", "最低价格", "最低价", "价格上限", "到期收益", "溢价", "强赎", "评级", "信用", "剩余期限", "存续规模", "行业"])
        if asks_cb:
            if "基本面" in question:
                return self._param_line("可转债基本面权重", cb_weights.get("fundamental"), "用于可转债综合评分；对应扣非净利润增长、增长加速、利润为负等基本面因子。0.25 表示 25%。")
            if "最低价格" in question or "最低价" in question:
                return self._param_line("可转债最低价格配置", cb.get("min_price"), "低于该价格默认不进入正常排序，因为 100 元以下通常可能隐含信用风险。")
            if "最高价格" in question or "价格上限" in question or "最高价" in question:
                return self._param_line("可转债最高价格上限", cb.get("price_limit"), "高于或等于该价格不进入普通低估/性价比筛选。")
            if "溢价" in question:
                if "权重" in question:
                    return self._param_line("可转债转股溢价率权重", cb_weights.get("premium"), "用于综合评分；溢价率越高通常越需要扣分。")
                return (
                    f"可转债转股溢价率配置：评分权重 {self._fmt_param(cb_weights.get('premium'))}；"
                    f"高溢价扣分线 {self._fmt_param(cb.get('high_premium_penalty_threshold'))}%；"
                    f"高溢价硬排除线 {self._fmt_param(cb.get('high_premium_hard_exclude'))}%。"
                )
            if "到期收益" in question or "ytm" in text:
                if "权重" in question:
                    return self._param_line("可转债到期收益率权重", cb_weights.get("ytm"), "用于综合评分；负 YTM 会扣分，异常高 YTM 会被视作潜在信用风险。")
                return (
                    f"可转债 YTM 配置：评分权重 {self._fmt_param(cb_weights.get('ytm'))}；"
                    f"高 YTM 硬排除阈值 {self._fmt_param(cb.get('high_ytm_hard_exclude'))}%；"
                    f"严重负 YTM 硬排除阈值 {self._fmt_param(cb.get('severe_negative_ytm_hard_exclude'))}%；"
                    f"负 YTM 扣分 {self._fmt_param(cb.get('negative_ytm_penalty'))}。"
                )
            if "信用" in question or "评级" in question:
                ratings = cb.get("hard_exclude_ratings", [])
                return (
                    f"可转债信用评分权重是 {self._fmt_param(cb_weights.get('credit'))}。\n\n"
                    f"硬排除评级：{', '.join(ratings) if ratings else '--'}。"
                    "A+ 当前不在硬排除列表内，系统按中风险保留观察；A/A- 及以下默认硬排除。"
                )
            if "强赎" in question:
                return (
                    f"可转债强赎因子权重是 {self._fmt_param(cb_weights.get('redemption'))}。\n\n"
                    f"不强赎公告有效期配置为 {self._fmt_param(cb.get('no_redemption_valid_days'))} 天；"
                    f"触发强赎但未见有效公告是否硬排除：{self._bool_text(cb.get('exclude_unresolved_redemption_trigger'))}。"
                    "已发强赎公告的标的不进入正常打分范围。"
                )
            if "行业" in question:
                return (
                    f"可转债行业分散配置：申万一级行业最多 {self._fmt_param(cb.get('max_per_industry_l1'))} 只，"
                    f"申万二级行业最多 {self._fmt_param(cb.get('max_per_industry_l2'))} 只。"
                )
            if "剩余期限" in question or "期限" in question:
                return self._param_line("可转债剩余期限权重", cb_weights.get("term"), "用于综合评分。")
            if "规模" in question:
                return (
                    f"可转债规模因子权重是 {self._fmt_param(cb_weights.get('scale'))}；"
                    f"剩余规模硬排除下限是 {self._fmt_param(cb.get('min_remaining_size_hard_exclude'))}。"
                )
            if "top" in text or "前" in question or "数量" in question:
                return self._param_line("可转债输出数量", cb.get("top_n"), "日报默认输出综合评分 TopN。")
            if "增长" in question or "负利润" in question or "扣非" in question:
                return (
                    f"可转债基本面相关配置：基本面权重 {self._fmt_param(cb_weights.get('fundamental'))}；"
                    f"负增长扣分 {self._fmt_param(cb.get('negative_growth_penalty'))}；"
                    f"增长加速为负扣分 {self._fmt_param(cb.get('negative_acceleration_penalty'))}；"
                    f"扣非利润为负扣分 {self._fmt_param(cb.get('negative_profit_penalty'))}；"
                    f"极端增长截尾区间 {self._fmt_param(cb.get('growth_winsor_lower'))}% 到 {self._fmt_param(cb.get('growth_winsor_upper'))}%。"
                )

        if "tl" in text or "国债" in question or "30年" in question or "三十年" in question:
            if "日线" in question and "j" in text:
                return self._param_line("TL 日线 J 低位阈值", tl.get("daily_j_low_threshold"), "系统规则：日线 T-3 至 T-1 内 J 小于该阈值，并且 T 日 J 值回升，才满足日线 KDJ 低位反弹条件。")
            if "周线" in question and "j" in text:
                return self._param_line("TL 周线 J 低位阈值", tl.get("weekly_j_low_threshold"), "系统规则：周线 T-2 内 J 小于该阈值，并且 T 周 J 值回升，才满足周线 KDJ 低位反弹条件。")
            if "日线" in question and "窗口" in question:
                return self._param_line("TL 日线 KDJ 窗口", tl.get("daily_kdj_lookback"), "用于检查最近几日是否出现过 J 低位。")
            if "周线" in question and "窗口" in question:
                return self._param_line("TL 周线 KDJ 窗口", tl.get("weekly_kdj_lookback"), "用于检查最近几周是否出现过 J 低位。")

        if "参数" in question or "配置" in question:
            return (
                "当前主要策略参数：\n\n"
                f"ETF：建仓量能 {self._fmt_param(etf.get('buy_volume_ratio_min'))}，"
                f"跌破 MA10 平仓量能 {self._fmt_param(etf.get('sell_ma10_volume_ratio_min'))}，"
                f"跌破 MA5 平仓量能 {self._fmt_param(etf.get('sell_ma5_volume_ratio_min'))}。\n"
                f"可转债：最低价格 {self._fmt_param(cb.get('min_price'))}，最高价格 {self._fmt_param(cb.get('price_limit'))}，"
                f"基本面权重 {self._fmt_param(cb_weights.get('fundamental'))}，溢价率权重 {self._fmt_param(cb_weights.get('premium'))}，"
                f"YTM 权重 {self._fmt_param(cb_weights.get('ytm'))}。\n"
                f"TL：日线 J 阈值 {self._fmt_param(tl.get('daily_j_low_threshold'))}，周线 J 阈值 {self._fmt_param(tl.get('weekly_j_low_threshold'))}。"
            )

        return ""

    def _parameter_catalog(self) -> list[dict[str, Any]]:
        return [
            {"group": "ETF", "label": "ETF 建仓量能倍数", "path": "etf.buy_volume_ratio_min", "aliases": ["etf建仓量能", "建仓量能倍数", "买入量能", "量能倍数"], "note": "今日成交量 / 前60个交易日平均成交量，达到该倍数才满足建仓量能确认。"},
            {"group": "ETF", "label": "ETF 跌破 MA10 平仓量能", "path": "etf.sell_ma10_volume_ratio_min", "aliases": ["ma10平仓量能", "跌破ma10", "跌破 ma10", "ma10卖出", "ma10量能"], "note": "持仓 ETF 收盘跌破 MA10 时，同时要求成交量达到该倍数才提示平仓。"},
            {"group": "ETF", "label": "ETF 跌破 MA5 平仓量能", "path": "etf.sell_ma5_volume_ratio_min", "aliases": ["ma5平仓量能", "跌破ma5", "跌破 ma5", "ma5卖出", "ma5量能"], "note": "持仓 ETF 收盘跌破 MA5 时，同时要求更明显放量才提示平仓。"},
            {"group": "ETF", "label": "ETF 趋势权重", "path": "etf.score_weights.trend", "aliases": ["etf趋势权重", "趋势权重"], "note": "用于 ETF 排序评分，主要反映均线关系和价格位置。"},
            {"group": "ETF", "label": "ETF MACD 权重", "path": "etf.score_weights.macd", "aliases": ["etf macd权重", "macd权重"], "note": "用于 ETF 排序评分，反映 MACD 改善或金叉的重要性。"},
            {"group": "ETF", "label": "ETF 量能权重", "path": "etf.score_weights.volume", "aliases": ["etf量能权重", "量能权重"], "note": "用于 ETF 排序评分，反映放量确认的重要性。"},
            {"group": "ETF", "label": "ETF 份额变化权重", "path": "etf.score_weights.share_change", "aliases": ["份额变化权重", "份额权重", "share_change"], "note": "ETF 排序辅助项；当前份额数据不足时影响较弱。"},
            {"group": "TL", "label": "TL 日线 KDJ 窗口", "path": "tl.daily_kdj_lookback", "aliases": ["日线kdj窗口", "tl日线窗口", "日线窗口"], "note": "检查最近几日是否出现过日线 J 低位。"},
            {"group": "TL", "label": "TL 日线 J 低位阈值", "path": "tl.daily_j_low_threshold", "aliases": ["日线j阈值", "日线j低位", "tl日线j"], "note": "系统规则：日线近 N 日 J 小于该阈值后回升，才满足日线低位反弹条件。"},
            {"group": "TL", "label": "TL 周线 KDJ 窗口", "path": "tl.weekly_kdj_lookback", "aliases": ["周线kdj窗口", "tl周线窗口", "周线窗口"], "note": "检查最近几周是否出现过周线 J 低位。"},
            {"group": "TL", "label": "TL 周线 J 低位阈值", "path": "tl.weekly_j_low_threshold", "aliases": ["周线j阈值", "周线j低位", "tl周线j"], "note": "系统规则：周线近 N 周 J 小于该阈值后回升，才满足周线低位反弹条件。"},
            {"group": "TL", "label": "TL MACD 柱最小改善量", "path": "tl.macd_hist_min_delta", "aliases": ["macd柱最小改善", "macd改善量", "macd_hist_min_delta"], "note": "用于判断 MACD 柱是否改善；当前为 0，表示只要方向改善即可。"},
            {"group": "TL", "label": "TL 周线不做交易硬否决", "path": "tl.weekly_no_trade_hard_veto", "aliases": ["周线硬否决", "周线不做交易硬否决", "硬否决"], "note": "开启后，周线满足不做交易条件时，日线信号不能升级为建仓候选。"},
            {"group": "可转债风控", "label": "可转债最低价格", "path": "convertible_bond.min_price", "aliases": ["最低价格", "最低价", "100元以下"], "note": "低于该价格默认不进入普通排序，因为可能隐含信用风险。"},
            {"group": "可转债风控", "label": "可转债最高价格上限", "path": "convertible_bond.price_limit", "aliases": ["最高价格", "价格上限", "140"], "note": "高于或等于该价格不进入普通低估/性价比筛选。"},
            {"group": "可转债风控", "label": "可转债输出 TopN", "path": "convertible_bond.top_n", "aliases": ["topn", "top n", "输出数量", "top10", "top 10"], "note": "每日报告默认输出综合评分前 N 只。"},
            {"group": "可转债风控", "label": "高 YTM 硬排除", "path": "convertible_bond.high_ytm_hard_exclude", "aliases": ["高ytm硬排除", "高 ytm", "高到期收益"], "note": "到期收益率异常高时，通常说明市场担心信用或兑付风险。"},
            {"group": "可转债风控", "label": "严重负 YTM 硬排除", "path": "convertible_bond.severe_negative_ytm_hard_exclude", "aliases": ["严重负ytm", "负ytm硬排除", "严重负到期收益"], "note": "YTM 过低或严重为负时，普通性价比不足，默认排除。"},
            {"group": "可转债风控", "label": "高溢价扣分线", "path": "convertible_bond.high_premium_penalty_threshold", "aliases": ["高溢价扣分线", "溢价扣分线"], "note": "转股溢价率达到该水平后开始明显扣分。"},
            {"group": "可转债风控", "label": "高溢价硬排除线", "path": "convertible_bond.high_premium_hard_exclude", "aliases": ["高溢价硬排除", "溢价硬排除"], "note": "转股溢价率达到该水平后不进入普通 Top10。"},
            {"group": "可转债风控", "label": "剩余规模硬排除下限", "path": "convertible_bond.min_remaining_size_hard_exclude", "aliases": ["剩余规模下限", "存续规模下限", "规模硬排除"], "note": "剩余规模太小的标的流动性和条款风险更高。"},
            {"group": "可转债风控", "label": "一级行业最多数量", "path": "convertible_bond.max_per_industry_l1", "aliases": ["一级行业最多", "申万一级最多"], "note": "用于行业分散，避免 Top10 过度集中。"},
            {"group": "可转债风控", "label": "二级行业最多数量", "path": "convertible_bond.max_per_industry_l2", "aliases": ["二级行业最多", "申万二级最多"], "note": "用于更细行业分散控制。"},
            {"group": "可转债风控", "label": "不强赎公告有效天数", "path": "convertible_bond.no_redemption_valid_days", "aliases": ["不强赎公告有效", "不强赎有效天数"], "note": "触发强赎但有不强赎公告时，在有效期内可继续观察。"},
            {"group": "可转债风控", "label": "排除 ST 正股", "path": "convertible_bond.exclude_st_stock", "aliases": ["排除st", "st正股", "st"], "note": "开启后，正股 ST 的转债不进入普通排序。"},
            {"group": "可转债风控", "label": "强赎未明硬排除", "path": "convertible_bond.exclude_unresolved_redemption_trigger", "aliases": ["强赎未明", "触发强赎未公告", "未见有效公告"], "note": "触发强赎价但未见有效公告时，是否直接硬排除。"},
            {"group": "可转债风控", "label": "评级硬排除列表", "path": "convertible_bond.hard_exclude_ratings", "aliases": ["评级硬排除", "硬排除评级", "bbb+", "a评级"], "note": "列表内评级不进入普通 Top10；A+ 当前保留为中风险观察。"},
            {"group": "可转债扣分", "label": "负 YTM 扣分", "path": "convertible_bond.negative_ytm_penalty", "aliases": ["负ytm扣分", "负到期收益扣分"], "note": "YTM 为负但未触及硬排除线时按幅度扣分。"},
            {"group": "可转债扣分", "label": "高溢价扣分", "path": "convertible_bond.high_premium_penalty", "aliases": ["高溢价扣分"], "note": "高溢价但未触及硬排除线时扣分。"},
            {"group": "可转债扣分", "label": "2025 负增长扣分", "path": "convertible_bond.negative_growth_penalty", "aliases": ["2025负增长", "负增长扣分"], "note": "2025 年或最新增长表现为负时扣分。"},
            {"group": "可转债扣分", "label": "增长加速为负扣分", "path": "convertible_bond.negative_acceleration_penalty", "aliases": ["增长加速为负", "加速扣分"], "note": "2025 增速低于三年平均增速时扣分。"},
            {"group": "可转债扣分", "label": "扣非净利润为负扣分", "path": "convertible_bond.negative_profit_penalty", "aliases": ["扣非净利润为负", "利润为负扣分"], "note": "最新扣非净利润为负时，基本面降权并扣分。"},
            {"group": "可转债扣分", "label": "利润基数异常扣分", "path": "convertible_bond.unstable_growth_base_penalty", "aliases": ["利润基数异常", "基数异常扣分"], "note": "利润基数过小导致增长率失真时扣分。"},
            {"group": "可转债扣分", "label": "极端增长扣分", "path": "convertible_bond.extreme_growth_penalty", "aliases": ["极端增长扣分"], "note": "增长率绝对值过高时扣分，避免低基数爆发把分数顶满。"},
            {"group": "可转债增长率", "label": "增长率截尾下限", "path": "convertible_bond.growth_winsor_lower", "aliases": ["增长率截尾下限", "winsor下限"], "note": "基本面增长率评分前的下限截尾。"},
            {"group": "可转债增长率", "label": "增长率截尾上限", "path": "convertible_bond.growth_winsor_upper", "aliases": ["增长率截尾上限", "winsor上限"], "note": "基本面增长率评分前的上限截尾。"},
            {"group": "可转债增长率", "label": "极端增长阈值", "path": "convertible_bond.extreme_growth_threshold", "aliases": ["极端增长阈值"], "note": "超过该阈值视为极端增长，触发额外扣分。"},
            {"group": "可转债增长率", "label": "小利润基数阈值", "path": "convertible_bond.small_profit_base_threshold", "aliases": ["小利润基数", "利润基数阈值"], "note": "判断利润基数异常的阈值。"},
            {"group": "可转债权重", "label": "可转债基本面权重", "path": "convertible_bond.score_weights.fundamental", "aliases": ["基本面权重", "基本面是多少", "基本面"], "note": "对应扣非净利润增长、增长加速、利润为负等基本面因子。"},
            {"group": "可转债权重", "label": "可转债溢价率权重", "path": "convertible_bond.score_weights.premium", "aliases": ["溢价率权重", "转股溢价权重"], "note": "转股溢价率质量权重，溢价过高通常扣分。"},
            {"group": "可转债权重", "label": "可转债 YTM 权重", "path": "convertible_bond.score_weights.ytm", "aliases": ["ytm权重", "到期收益率权重"], "note": "到期收益率质量权重；不是越高越好，两端异常都会降分。"},
            {"group": "可转债权重", "label": "可转债剩余期限权重", "path": "convertible_bond.score_weights.term", "aliases": ["剩余期限权重", "期限权重"], "note": "剩余期限评分权重。"},
            {"group": "可转债权重", "label": "可转债信用权重", "path": "convertible_bond.score_weights.credit", "aliases": ["信用权重", "评级权重"], "note": "债项评级、价格、YTM 风险共同影响信用得分。"},
            {"group": "可转债权重", "label": "可转债强赎状态权重", "path": "convertible_bond.score_weights.redemption", "aliases": ["强赎权重", "强赎状态权重"], "note": "强赎风险状态评分权重。"},
            {"group": "可转债权重", "label": "可转债规模权重", "path": "convertible_bond.score_weights.scale", "aliases": ["规模权重", "存续规模权重"], "note": "存续规模和未转股比例综合得分权重。"},
            {"group": "组合风控", "label": "ETF 新建仓候选展示上限", "path": "risk.max_new_etf_candidates", "aliases": ["新建仓候选上限", "etf候选展示上限"], "note": "日报里最多重点展示的新建仓 ETF 数量。"},
            {"group": "组合风控", "label": "平仓提示展示上限", "path": "risk.max_sell_alerts_to_highlight", "aliases": ["平仓提示上限", "平仓展示上限"], "note": "日报里最多重点展示的平仓提示数量。"},
        ]

    def _asks_parameter_catalog(self, question: str) -> bool:
        text = question.lower()
        return any(token in text for token in ["还有哪些", "其他参数", "全部参数", "所有参数", "参数目录", "除了这个其他"])

    def _parameter_catalog_answer(self, params: dict[str, Any], catalog: list[dict[str, Any]]) -> str:
        groups: dict[str, list[str]] = {}
        for item in catalog:
            groups.setdefault(str(item["group"]), []).append(
                f"{item['label']}={self._fmt_param(self._get_param_path(params, item['path']))}"
            )
        lines = ["目前问答已覆盖这些策略参数："]
        for group, entries in groups.items():
            lines.append(f"{group}：" + "；".join(entries))
        lines.append("这些回答都来自 configs/strategy_params.json，走 deterministic_chat，不需要等大模型。")
        return "\n\n".join(lines)

    def _parameter_catalog_match(self, question: str, params: dict[str, Any], catalog: list[dict[str, Any]]) -> str:
        text = question.lower().replace(" ", "")
        for item in catalog:
            aliases = [str(item["label"])] + [str(alias) for alias in item.get("aliases", [])]
            if any(alias.lower().replace(" ", "") in text for alias in aliases):
                return self._param_line(
                    str(item["label"]),
                    self._get_param_path(params, str(item["path"])),
                    str(item["note"]),
                )
        return ""

    def _get_param_path(self, params: dict[str, Any], path: str) -> Any:
        current: Any = params
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _param_line(self, label: str, value: Any, note: str) -> str:
        return f"{label}当前是 {self._fmt_param(value)}。\n\n{note}\n\n参数保存后会立即写入配置；要让日报和信号结果变化，需要再点击一键刷新重新计算。"

    def _fmt_param(self, value: Any) -> str:
        if value is None or value == "":
            return "--"
        if isinstance(value, bool):
            return self._bool_text(value)
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    def _bool_text(self, value: Any) -> str:
        return "是" if bool(value) else "否"

    def _asks_etf_signal_explanation(self, text: str) -> bool:
        if "etf" not in text:
            return False
        return any(token in text for token in ["为什么", "原因", "分析", "解释", "没有建仓", "建仓候选", "没入选", "条件"])

    def _is_complex_question(self, question: str) -> bool:
        text = question.lower()
        complex_tokens = [
            "为什么",
            "怎么",
            "如何",
            "是否",
            "能不能",
            "分析",
            "解释",
            "原因",
            "风险",
            "稳定",
            "对比",
            "同时",
            "并且",
            "以及",
        ]
        return len(question.strip()) >= 28 or sum(token in text for token in complex_tokens) >= 1

    def _summary_value(self, rows: list[Any], item_name: str) -> Any:
        for row in rows:
            if isinstance(row, dict) and row.get("item") == item_name:
                return row.get("value")
        return None

    def _fmt_count(self, value: object) -> str:
        if value is None or value == "":
            return "--"
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value)

    def _deterministic_compliance_answer(self, question: str) -> str:
        lowered = question.lower()
        risky_terms = [
            "保证赚钱",
            "保证收益",
            "保证盈利",
            "保证绝对收益",
            "绝对收益",
            "一定赚钱",
            "稳赚",
            "稳赚不赔",
            "必涨",
            "无风险",
            "guaranteed return",
        ]
        if not any(term in lowered for term in risky_terms):
            return ""
        return (
            "不能保证赚钱，也不能承诺收益。"
            "这套系统的定位是把 Wind 数据、确定性策略规则、质检和AI解释串起来，帮助用户做更稳定的投研和复核。"
            "ETF、TL、可转债的信号必须以代码生成的 buy_signal、sell_signal、state、rank 和 score 为准，AI 只能解释证据和提示风险，不能替代投资决策。"
        )

    def _enrich_intent_with_database_entities(
        self,
        question: str,
        intent: Any,
        repository: DatabaseRepository,
    ) -> Any:
        if intent.entities.get("codes"):
            # Router 已识别多标的时保留完整列表和用户提及顺序；单标的解析器
            # 只能返回一只，继续解析会把 trace 和短期记忆错误覆盖成其中某只。
            return intent
        if intent.name in {
            "asset_list",
            "database_inventory",
            "data_quality",
            "agent_audit",
            "risk_review",
            "daily_report",
            "etf_entry",
            "etf_ranking",
            "strategy_params",
            "strategy_comparison",
            "etf_strategy_comparison",
            "strategy_stability",
            "historical_diagnostics",
            "chat_data_scope",
            "external_data_unavailable",
            "clarification",
        }:
            return intent
        if str(intent.entities.get("not_found") or "").lower() == "true":
            return intent

        asset = repository.resolve_asset(question)
        if not asset:
            return intent

        entities = dict(intent.entities)
        entities["name"] = str(asset.get("name", ""))
        entities["code"] = str(asset.get("code", ""))
        entities["asset_type"] = str(asset.get("asset_type", ""))

        if asset.get("asset_type") == "ETF" and intent.name != "etf_exit":
            intent_name = "etf_detail"
        elif asset.get("asset_type") == "TL":
            intent_name = "tl_timing"
        elif asset.get("asset_type") == "CONVERTIBLE":
            intent_name = "convertible_bond"
        else:
            intent_name = intent.name

        return type(intent)(intent_name, max(intent.confidence, 0.93), entities)
