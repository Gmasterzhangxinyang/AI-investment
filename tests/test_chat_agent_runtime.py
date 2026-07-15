from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.chat.agent_runtime import AgentPreparation, ResearchAgentRuntime
from superpower.chat.evidence_review import EvidenceAccuracyReviewer
from superpower.chat.orchestrator import ChatOrchestrator
from superpower.chat.schemas import AgentStep, ChatIntent, ChatRequest, EvidencePack, ToolResult
from superpower.tools.llm import LLMResult


class FakeRegistry:
    MAX_TOOL_CALLS = 5

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, str]]] = []

    def public_specs(self):
        return [
            {"name": "strategy_contract", "description": "rules", "arguments": {}},
            {"name": "tl_state", "description": "tl", "arguments": {}},
            {"name": "etf_ranking", "description": "rank", "arguments": {"metric": "score"}},
        ]

    def has_tool(self, name: str) -> bool:
        return name in {"strategy_contract", "tl_state", "etf_ranking"}

    def execute(self, name: str, arguments: dict[str, str]):
        self.executed.append((name, arguments))
        if name == "strategy_contract":
            return ToolResult(
                tool="get_rule_contract",
                title="rules",
                source="config",
                summary="ok",
                data={"etf_strategy": {"active_strategy": "legacy_v1"}},
            )
        if name == "tl_state":
            return ToolResult(
                tool="get_tl_state",
                title="tl",
                source="sqlite",
                summary="ok",
                data={
                    "today": [{"state": "观望"}],
                    "history": [
                        {"trade_date": "2026-07-10", "code": "TL.CFE", "close": 108.1},
                        {"trade_date": "2026-07-09", "code": "TL.CFE", "close": 108.0},
                    ],
                },
            )
        return ToolResult(
            tool="get_etf_ranking",
            title="ranking",
            source="dashboard",
            summary="ok",
            data={"metric": "score", "rows": [{"code": "510001.SH", "metric_value": 99.0}]},
        )


def test_agent_runtime_plans_executes_and_reviews(monkeypatch) -> None:
    registry = FakeRegistry()
    decisions = iter([
        {
            "action": "tool",
            "intent": "tl_timing",
            "entities": {},
            "tool": "tl_state",
            "arguments": {},
            "reason": "先读取TL状态",
        },
        {
            "action": "finish",
            "intent": "tl_timing",
            "entities": {},
            "reason": "证据已经覆盖当前状态和30日历史",
        },
        {
            "verdict": "pass",
            "tool": "",
            "arguments": {},
            "issues": [],
            "reason": "证据足够",
        },
    ])
    monkeypatch.setattr(
        "superpower.chat.agent_runtime.generate_text",
        lambda *args, **kwargs: LLMResult(True, "openai", "gpt-test", json.dumps(next(decisions), ensure_ascii=False), "ok"),
    )

    result = ResearchAgentRuntime(registry).prepare(
        "最近一个月TL怎么样",
        ChatIntent("tl_timing", 0.9, {}),
        {},
        "2026-07-10",
        {"llm_enabled": True},
    )

    assert result.planned is True
    assert result.review and result.review.passed is True
    assert [name for name, _ in registry.executed] == ["strategy_contract", "tl_state"]
    assert result.tools[-1].tool == "evidence_accuracy_review"
    assert result.agent_iterations == 2
    assert result.reflection_count == 1
    assert any(step.name == "ResearchSupervisorAgent" for step in result.steps)
    assert any(step.name == "EvidenceReflectionAgent" for step in result.steps)


def test_agent_runtime_reflects_and_fetches_missing_evidence(monkeypatch) -> None:
    registry = FakeRegistry()
    decisions = iter([
        {
            "action": "tool",
            "intent": "risk_review",
            "entities": {"metric": "score"},
            "tool": "etf_ranking",
            "arguments": {"metric": "score"},
            "reason": "先看ETF排序",
        },
        {
            "action": "finish",
            "intent": "risk_review",
            "entities": {},
            "reason": "准备综合",
        },
        {
            "verdict": "tool",
            "tool": "tl_state",
            "arguments": {},
            "issues": ["还缺TL状态"],
            "reason": "需要补充跨资产证据",
        },
        {
            "action": "finish",
            "intent": "risk_review",
            "entities": {},
            "reason": "ETF和TL证据齐全",
        },
        {
            "verdict": "pass",
            "tool": "",
            "arguments": {},
            "issues": [],
            "reason": "证据足够",
        },
    ])
    monkeypatch.setattr(
        "superpower.chat.agent_runtime.generate_text",
        lambda *args, **kwargs: LLMResult(True, "openai", "gpt-test", json.dumps(next(decisions), ensure_ascii=False), "ok"),
    )

    result = ResearchAgentRuntime(registry).prepare(
        "综合ETF和TL风险",
        ChatIntent("risk_review", 0.8, {}),
        {},
        "2026-07-10",
        {"llm_enabled": True},
    )

    assert result.planned is True
    assert [name for name, _ in registry.executed] == ["etf_ranking", "strategy_contract", "tl_state"]
    assert result.reflection_count == 2
    assert any(step.status == "replan" for step in result.steps if step.name == "EvidenceReflectionAgent")


def test_agent_runtime_recovers_from_malformed_supervisor_output(monkeypatch) -> None:
    registry = FakeRegistry()
    responses = iter(
        [
            LLMResult(True, "openai", "gpt-test", "这不是JSON", "ok"),
            LLMResult(
                True,
                "openai",
                "gpt-test",
                json.dumps(
                    {
                        "action": "tool",
                        "intent": "tl_timing",
                        "entities": {},
                        "tool": "tl_state",
                        "arguments": {},
                        "reason": "读取TL历史",
                    },
                    ensure_ascii=False,
                ),
                "ok",
            ),
            LLMResult(
                True,
                "openai",
                "gpt-test",
                json.dumps(
                    {
                        "action": "finish",
                        "intent": "tl_timing",
                        "entities": {},
                        "reason": "证据完整",
                    },
                    ensure_ascii=False,
                ),
                "ok",
            ),
            LLMResult(
                True,
                "openai",
                "gpt-test",
                json.dumps(
                    {"verdict": "pass", "tool": "", "arguments": {}, "issues": [], "reason": "通过"},
                    ensure_ascii=False,
                ),
                "ok",
            ),
        ]
    )
    monkeypatch.setattr("superpower.chat.agent_runtime.generate_text", lambda *args, **kwargs: next(responses))

    result = ResearchAgentRuntime(registry).prepare(
        "最近一个月TL怎么样",
        ChatIntent("tl_timing", 0.9, {}),
        {},
        "2026-07-10",
        {"llm_enabled": True},
    )

    assert result.planned is True
    assert result.planner_reason == "react_completed"
    assert any(step.status == "replan" and "格式无效" in step.detail for step in result.steps)
    assert [name for name, _ in registry.executed] == ["strategy_contract", "tl_state"]


def test_agent_runtime_keeps_audited_evidence_when_llm_fails_mid_loop(monkeypatch) -> None:
    registry = FakeRegistry()
    responses = iter(
        [
            LLMResult(
                True,
                "openai",
                "gpt-test",
                json.dumps(
                    {
                        "action": "tool",
                        "intent": "tl_timing",
                        "entities": {},
                        "tool": "tl_state",
                        "arguments": {},
                        "reason": "读取TL历史",
                    },
                    ensure_ascii=False,
                ),
                "ok",
            ),
            LLMResult(False, "openai", "gpt-test", "", "timeout"),
        ]
    )
    monkeypatch.setattr("superpower.chat.agent_runtime.generate_text", lambda *args, **kwargs: next(responses))

    result = ResearchAgentRuntime(registry).prepare(
        "最近一个月TL怎么样",
        ChatIntent("tl_timing", 0.9, {}),
        {},
        "2026-07-10",
        {"llm_enabled": True},
    )

    assert result.planned is True
    assert result.planner_reason == "react_partial_fallback:timeout"
    assert result.review and result.review.passed is True
    assert [name for name, _ in registry.executed] == ["strategy_contract", "tl_state"]
    assert any(step.status == "fallback" for step in result.steps if step.name == "ResearchSupervisorAgent")


def test_agent_runtime_asks_for_missing_ranking_metric(monkeypatch) -> None:
    registry = FakeRegistry()
    payload = {
        "action": "clarify",
        "intent": "etf_ranking",
        "entities": {},
        "clarification_question": "你想按强弱分、收盘价、量能还是份额变化比较？",
        "reason": "缺少ETF评价指标",
    }
    monkeypatch.setattr(
        "superpower.chat.agent_runtime.generate_text",
        lambda *args, **kwargs: LLMResult(True, "openai", "gpt-test", json.dumps(payload, ensure_ascii=False), "ok"),
    )

    result = ResearchAgentRuntime(registry).prepare(
        "最好的ETF",
        ChatIntent("etf_ranking", 0.8, {}),
        {},
        "2026-07-10",
        {"llm_enabled": True},
    )

    assert result.planned is True
    assert result.intent.name == "clarification"
    assert "强弱分" in result.clarification
    assert registry.executed == []


def test_evidence_review_blocks_duplicate_or_oversized_data() -> None:
    rows = [{"code": f"11{index:04d}.SH"} for index in range(31)]
    rows[-1]["code"] = rows[0]["code"]
    review = EvidenceAccuracyReviewer().review(
        [
            ToolResult(
                tool="get_convertible_top10",
                title="cb",
                source="sqlite",
                summary="cb",
                data={"analysis_universe": rows, "as_of": "2026-07-10"},
            )
        ],
        ["convertible_rankings"],
        "2026-07-10",
    )

    assert review.passed is False
    assert any("超过30只" in issue for issue in review.issues)
    assert any("重复代码" in issue for issue in review.issues)


def test_orchestrator_marks_agent_planning_without_changing_rule_answer(tmp_path: Path, monkeypatch) -> None:
    ranking_tool = ToolResult(
        tool="get_etf_ranking",
        title="ETF ranking",
        source="dashboard",
        summary="ok",
        data={
            "metric": "score",
            "metric_label": "强弱分",
            "direction": "desc",
            "rows": [{"name": "测试ETF", "code": "510001.SH", "metric_value": 99.0}],
        },
    )
    preparation = AgentPreparation(
        planned=True,
        intent=ChatIntent("etf_ranking", 0.97, {"metric": "score"}),
        tools=[ranking_tool],
        steps=[AgentStep("ResearchSupervisorAgent", "success", "planned")],
        clarification="",
        planner_llm_used=True,
        planner_provider="openai",
        planner_model="gpt-test",
        planner_reason="react_completed",
    )
    monkeypatch.setattr(ResearchAgentRuntime, "prepare", lambda *args, **kwargs: preparation)

    orchestrator = ChatOrchestrator(tmp_path)
    monkeypatch.setattr(orchestrator, "_load_dashboard", lambda: {"reportDate": "2026-07-10", "etf": {"all_signals": []}})
    monkeypatch.setattr(orchestrator, "_load_model_config", lambda: {"llm_enabled": True, "provider": "openai", "primary_model": "gpt-test"})
    response = orchestrator.run(ChatRequest("强弱分最高的ETF为什么排第一", allow_llm=True))

    assert response.answer.startswith("截至报告日期 2026-07-10，强弱分最高的 ETF 是测试ETF")
    assert response.llm_used is True
    assert response.llm_reason == "answer_fallback_after_react_completed"
    assert any(step.name == "ResearchSupervisorAgent" for step in response.steps)


def test_orchestrator_uses_fast_lane_for_clear_single_asset_query(tmp_path: Path, monkeypatch) -> None:
    orchestrator = ChatOrchestrator(tmp_path)
    model_config = {
        "llm_enabled": True,
        "provider": "openai",
        "primary_model": "gpt-test",
        "economy_model": "gpt-mini",
    }

    assert orchestrator._should_prepare_agent(
        ChatRequest("黄金ETF今天", allow_llm=True),
        ChatIntent("etf_detail", 0.94, {"name": "黄金ETF", "code": "159934.SZ"}),
        model_config,
    ) is False
    assert orchestrator._should_prepare_agent(
        ChatRequest("结合ETF、TL和可转债分析整体风险", allow_llm=True),
        ChatIntent("risk_review", 0.97, {}),
        model_config,
    ) is True


def test_internal_agent_and_reviewer_use_economy_model() -> None:
    config = {"primary_model": "gpt-main", "economy_model": "gpt-mini", "llm_enabled": True}

    assert ResearchAgentRuntime._internal_model_config(config)["primary_model"] == "gpt-mini"
    assert ChatOrchestrator._internal_review_model_config(config)["primary_model"] == "gpt-mini"
    assert config["primary_model"] == "gpt-main"


def test_focused_ai_answer_uses_economy_model(tmp_path: Path, monkeypatch) -> None:
    seen_models: list[str] = []

    def fake_generate_text(*args, **kwargs):
        model_config = args[1]
        seen_models.append(str(model_config.get("primary_model")))
        return LLMResult(True, "openai", str(model_config.get("primary_model")), "黄金ETF当前未触发。", "ok")

    monkeypatch.setattr("superpower.chat.orchestrator.generate_text", fake_generate_text)
    orchestrator = ChatOrchestrator(tmp_path)
    monkeypatch.setattr(
        orchestrator,
        "_load_dashboard",
        lambda: {
            "reportDate": "2026-07-10",
            "etf": {"all_signals": [{"name": "黄金ETF", "code": "159934.SZ", "display_action": "未触发"}]},
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_model_config",
        lambda: {
            "llm_enabled": True,
            "provider": "openai",
            "primary_model": "gpt-main",
            "economy_model": "gpt-mini",
        },
    )

    response = orchestrator.run(ChatRequest("黄金ETF为什么没触发", allow_llm=True))

    assert response.llm_used is True
    assert response.llm_model == "gpt-mini"
    assert seen_models == ["gpt-mini"]


def test_final_answer_reviewer_repairs_unsupported_action(monkeypatch) -> None:
    revised = "当前证据只支持观望，系统不会自动刷新或执行交易。"
    monkeypatch.setattr(
        "superpower.chat.orchestrator.generate_text",
        lambda *args, **kwargs: LLMResult(
            True,
            "openai",
            "gpt-test",
            json.dumps(
                {
                    "passed": False,
                    "issues": ["草稿承诺了未开放的刷新动作"],
                    "revised_answer": revised,
                },
                ensure_ascii=False,
            ),
            "ok",
        ),
    )
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=ChatIntent("risk_review", 0.9, {}),
        rulebook=[],
        tools=[ToolResult("get_risk_summary", "risk", "dashboard", "ok", [])],
    )

    answer, step = ChatOrchestrator(ROOT)._review_generated_answer(
        "简洁分析风险",
        "我先帮你刷新数据再分析。",
        pack,
        {"llm_enabled": True},
        "",
    )

    assert answer == revised
    assert step.name == "AnswerEvidenceReviewer"
    assert step.status == "repaired"


def test_final_answer_subject_anchor_names_single_asset() -> None:
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=ChatIntent("convertible_bond", 0.9, {"name": "弘亚转债", "code": "127041.SZ"}),
        rulebook=[],
        tools=[],
    )
    answer, repaired = ChatOrchestrator(ROOT)._ensure_subject_anchor(
        "因为存在三项风险提示。",
        pack,
        "",
    )
    assert repaired is True
    assert answer.startswith("弘亚转债（127041.SZ）：")


def test_final_answer_subject_anchor_uses_clear_no_data_fallback() -> None:
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=ChatIntent("etf_detail", 0.9, {"name": "火星ETF", "not_found": "true"}),
        rulebook=[],
        tools=[],
    )
    fallback = "当前不知道火星ETF的情况：本地没有这只ETF的数据。"
    answer, repaired = ChatOrchestrator(ROOT)._ensure_subject_anchor("没有", pack, fallback)
    assert repaired is True
    assert answer == fallback
