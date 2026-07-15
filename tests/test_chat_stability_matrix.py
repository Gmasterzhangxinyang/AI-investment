from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.chat.orchestrator import ChatOrchestrator
from superpower.chat.guardrails import ChatGuardrails
from superpower.chat.router import ChatRouter
from superpower.chat.schemas import ChatIntent, ChatRequest, EvidencePack, ToolResult


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("你好呀", "conversation"),
        ("你在干什么", "conversation"),
        ("最近最好的新闻", "external_data_unavailable"),
        ("AI能读取多少数据，最新到哪天", "chat_data_scope"),
        ("ETF原策略和2.0哪个好", "strategy_comparison"),
        ("历史诊断的10日正收益比例", "historical_diagnostics"),
        ("这些策略稳定吗", "strategy_stability"),
        ("强弱分最高的ETF", "etf_ranking"),
        ("收盘价最低的ETF", "etf_ranking"),
        ("量能最大的ETF", "etf_ranking"),
        ("份额变化最大的ETF", "etf_ranking"),
        ("最好的ETF", "etf_ranking"),
        ("数据库有多少ETF", "database_inventory"),
        ("当前默认策略是什么", "strategy_params"),
        ("最近一个月TL趋势怎么样", "tl_timing"),
        ("可转债第20名为什么没进Top10", "convertible_bond"),
        ("弘亚转债为什么风险观察", "convertible_bond"),
        ("可转债溢价率阈值是多少", "strategy_params"),
        ("现在的数据有没有问题", "data_quality"),
        ("结合ETF、TL和可转债分析整体风险", "risk_review"),
        ("今天的日报结论", "daily_report"),
        ("ETF平仓提示有哪些", "etf_exit"),
        ("ETF建仓候选有哪些", "etf_entry"),
    ],
)
def test_router_stability_matrix(question: str, expected_intent: str) -> None:
    assert ChatRouter().route(question, {}).name == expected_intent


@pytest.mark.parametrize(
    "question",
    [
        "保证绝对收益的ETF买法",
        "给我一个稳赚不赔的策略",
        "哪个ETF一定赚钱",
        "有没有无风险的交易",
    ],
)
def test_compliance_matrix_blocks_return_promises(question: str) -> None:
    answer = ChatOrchestrator(ROOT)._deterministic_compliance_answer(question)
    assert "不能保证赚钱" in answer
    assert "不能承诺收益" in answer


def test_data_quality_rule_answer_is_useful_without_llm() -> None:
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=ChatIntent("data_quality", 0.9, {}),
        rulebook=[],
        tools=[
            ToolResult(
                "get_data_quality",
                "quality",
                "dashboard",
                "2 checks",
                {
                    "quality": [
                        {"item": "ETF最新日期", "status": "WARN", "value": "2026-07-03"},
                        {"item": "TL最新日期", "status": "OK", "value": "2026-07-10"},
                    ]
                },
            )
        ],
    )
    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("数据有没有问题", pack)
    assert "1 项需要关注" in answer
    assert "ETF最新日期" in answer
    assert "不等同于策略风险" in answer


def test_data_quality_answer_uses_full_counts_and_warning_rows_beyond_visible_slice() -> None:
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=ChatIntent("data_quality", 0.9, {}),
        rulebook=[],
        tools=[
            ToolResult(
                "get_data_quality",
                "quality",
                "dashboard",
                "59 checks",
                {
                    "quality": [{"item": "前端可见检查", "status": "OK"}],
                    "total_count": 59,
                    "warning_count": 12,
                    "warning_rows": [
                        {"item": "第51项后的提醒", "status": "WARN", "value": "需要复核"},
                    ],
                },
            )
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("数据有没有问题", pack)

    assert "共检查 59 项" in answer
    assert "12 项需要关注" in answer
    assert "第51项后的提醒" in answer


def test_ai_off_still_returns_deterministic_ranking(monkeypatch) -> None:
    orchestrator = ChatOrchestrator(ROOT)
    monkeypatch.setattr(
        orchestrator,
        "_load_dashboard",
        lambda: {
            "reportDate": "2026-07-10",
            "etf": {
                "all_signals": [
                    {"name": "甲ETF", "code": "510001.SH", "score": 80, "close": 1.0},
                    {"name": "乙ETF", "code": "510002.SH", "score": 90, "close": 2.0},
                ]
            },
        },
    )
    response = orchestrator.run(ChatRequest("强弱分最高的ETF", allow_llm=False))
    assert response.llm_used is False
    assert "乙ETF（510002.SH）" in response.answer


def test_router_does_not_confuse_unknown_etf_with_similarly_named_convertible() -> None:
    dashboard = {
        "convertible_bond": {
            "ranked_candidates": [{"bond_name": "火星转债", "bond_code": "123154.SZ"}]
        }
    }
    intent = ChatRouter().route("火星ETF现在怎么样", dashboard)
    assert intent.name == "etf_detail"
    assert intent.entities.get("not_found") == "true"
    assert intent.entities.get("code") is None


def test_guardrail_does_not_treat_negative_entry_disclaimer_as_advice() -> None:
    text = "份额变化属于资金申购赎回辅助信息，不直接等同于买入信号。"
    assert ChatGuardrails()._contains_positive_entry_claim(text) is False
