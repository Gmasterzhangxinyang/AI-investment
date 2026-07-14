from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.chat.orchestrator import ChatOrchestrator
from superpower.chat.router import ChatRouter
from superpower.chat.schemas import ChatIntent, ChatRequest, EvidencePack
from superpower.chat.tools import ResearchToolbox


class ConfigRepository:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir


def test_router_understands_strategy_comparison_stability_and_diagnostics() -> None:
    router = ChatRouter()

    assert router.route("原策略和2.0哪个好？", {}).name == "strategy_comparison"
    assert router.route("这些策略稳定吗？", {}).name == "strategy_stability"
    assert router.route("历史诊断怎么看？", {}).name == "historical_diagnostics"


def test_router_handles_greetings_and_etf_metric_rankings() -> None:
    router = ChatRouter()

    assert router.route("你好呀", {}).name == "conversation"
    explicit = router.route("查下收盘价最高的ETF", {})
    assert explicit.name == "etf_ranking"
    assert explicit.entities["metric"] == "close"
    ambiguous = router.route("查下最高的ETF", {})
    assert ambiguous.name == "etf_ranking"
    assert ambiguous.entities["metric"] == ""


def test_etf_ranking_uses_full_dashboard_and_answers_directly() -> None:
    dashboard = {
        "reportDate": "2026-07-10",
        "etf": {
            "all_signals": [
                {"name": "低价ETF", "code": "111111.SH", "close": 1.2, "score": 90},
                {"name": "高价ETF", "code": "222222.SH", "close": 9.1, "score": 40},
                {"name": "中价ETF", "code": "333333.SH", "close": 4.8, "score": 70},
            ]
        },
    }
    intent = ChatRouter().route("查下收盘价最高的ETF", dashboard)
    tools = ResearchToolbox(dashboard).collect(intent)
    pack = EvidencePack(report_date="2026-07-10", intent=intent, rulebook=[], tools=tools)

    assert tools[0].data["rows"][0]["code"] == "222222.SH"
    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("查下收盘价最高的ETF", pack)
    assert "高价ETF（222222.SH）" in answer
    assert "9.1" in answer
    assert "不代表趋势更强" in answer


def test_ambiguous_etf_ranking_asks_for_a_metric() -> None:
    dashboard = {"etf": {"all_signals": [{"name": "测试ETF", "code": "111111.SH", "close": 1.2}]}}
    intent = ChatRouter().route("查下最高的ETF", dashboard)
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=intent,
        rulebook=[],
        tools=ResearchToolbox(dashboard).collect(intent),
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("查下最高的ETF", pack)
    assert "还缺少比较指标" in answer
    assert "强弱分" in answer and "收盘价" in answer


def test_rule_contract_follows_active_etf_strategy(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "strategy_params.json").write_text(
        json.dumps(
            {
                "etf": {
                    "active_strategy": "trend_pullback_v2",
                    "strategy_profiles": {
                        "trend_pullback_v2": {
                            "medium_trend": {"ma20_slope_lookback": 5, "ma20_flat_tolerance": 0.003},
                            "short_entry": {"overheat_daily_return_min": 0.04, "overheat_ma5_distance_min": 0.03},
                        }
                    },
                },
                "tl": {"fund_flow": {"large_threshold": 0.05, "extreme_threshold": 0.07}},
                "convertible_bond": {"auxiliary_overlay": {"enabled": True, "overlay_id": "dynamic_v2"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    contract = ResearchToolbox({}, ConfigRepository(tmp_path)).get_rule_contract().data
    etf_rules = " ".join(contract["etf_rules"])

    assert contract["etf_strategy"]["active_strategy"] == "trend_pullback_v2"
    assert "MA20" in etf_rules and "回踩" in etf_rules and "过热" in etf_rules
    assert "建仓A" not in etf_rules
    assert "份额变化只作辅助" in " ".join(contract["tl_rules"])
    assert "不改变原始分数和排名" in " ".join(contract["convertible_bond_rules"])


def test_evidence_planner_keeps_convertible_question_compact() -> None:
    noisy_rows = [
        {
            "bond_name": f"测试转债{index}",
            "bond_code": f"11{index:04d}.SH",
            "score": 50 + index / 100,
            "qualification": "weak_watch",
            "not_top_reason": "溢价率偏高",
            "unused_payload": "x" * 1200,
        }
        for index in range(307)
    ]
    dashboard = {
        "reportDate": "2026-07-10",
        "summary": [],
        "convertible_bond": {"weak_watch": noisy_rows, "qualified": [], "risk_watch": [], "summary": {}},
    }
    tools = ResearchToolbox(dashboard).collect(ChatIntent("convertible_bond", 0.92, {}))
    payload_chars = len(json.dumps([asdict(tool) for tool in tools], ensure_ascii=False))

    assert "get_research_snapshot" not in [tool.tool for tool in tools]
    assert payload_chars < 30_000


def test_convertible_evidence_keeps_all_four_dynamic_factors() -> None:
    row = {
        "bond_name": "测试转债",
        "bond_code": "123456.SZ",
        "stock_daily_return": -1.68,
        "bond_daily_return": -0.72,
        "conversion_premium_change": 0.98,
        "auxiliary_score": 37.64,
        "auxiliary_state": "正常联动",
        "auxiliary_note": "四项处于正常联动范围",
    }

    compact = ResearchToolbox({})._compact_cb_row(row)

    assert compact["stock_daily_return"] == -1.68
    assert compact["bond_daily_return"] == -0.72
    assert compact["stock_bond_relative_gap"] == -0.96
    assert compact["conversion_premium_change"] == 0.98
    assert compact["auxiliary_score"] == 37.64
    assert compact["auxiliary_state"] == "正常联动"


def test_llm_is_only_used_for_complex_questions_when_user_enables_it() -> None:
    orchestrator = ChatOrchestrator(ROOT)

    assert orchestrator._should_use_llm(ChatRequest("为什么这个ETF没有入选？", allow_llm=True), "确定性回答")
    assert not orchestrator._should_use_llm(ChatRequest("当前TL状态？", allow_llm=True), "确定性回答")
    assert not orchestrator._should_use_llm(ChatRequest("为什么这个ETF没有入选？", allow_llm=False), "确定性回答")


def test_current_strategy_question_has_a_direct_backend_answer() -> None:
    pack = ResearchToolbox({}, ConfigRepository(ROOT)).collect(ChatIntent("strategy_params", 0.95, {}))
    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer(
        "现在使用哪个策略？",
        EvidencePack(
            report_date="2026-07-14",
            intent=ChatIntent("strategy_params", 0.95, {}),
            rulebook=[],
            tools=pack,
        ),
    )

    assert "ETF默认策略是 legacy_v1" in answer
    assert "可转债默认策略是 dynamic_v2" in answer
