from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
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
    natural_ambiguous = router.route("最好的ETF", {})
    assert natural_ambiguous.name == "etf_ranking"
    assert natural_ambiguous.entities["metric"] == ""
    assert router.route("你能读取多少数据，最新到哪天？", {}).name == "chat_data_scope"
    assert router.route("可转债第20名为什么没有进入Top10？", {}).name == "convertible_bond"


def test_router_understands_generic_and_named_dual_etf_strategy_comparison() -> None:
    router = ChatRouter()

    assert router.route("ETF双策略比较", {}).name == "strategy_comparison"
    dashboard = {"etf": {"all_signals": [{"name": "黄金ETF", "code": "159934.SZ"}]}}
    named = router.route("黄金ETF双策略比较", dashboard)
    assert named.name == "etf_strategy_comparison"
    assert named.entities["code"] == "159934.SZ"


def test_router_keeps_casual_chat_and_external_news_out_of_daily_report() -> None:
    router = ChatRouter()
    orchestrator = ChatOrchestrator(ROOT)

    for question in ("你在干啥", "？", "说话"):
        intent = router.route(question, {})
        assert intent.name == "conversation"
        pack = EvidencePack(report_date="2026-07-10", intent=intent, rulebook=[], tools=[])
        answer = orchestrator._deterministic_evidence_answer(question, pack)
        assert "日报日期" not in answer
        assert answer == ""
        assert "AI自然对话尚未开启" in orchestrator._fallback_answer(question, pack, "llm_disabled_by_user")
        assert orchestrator._should_use_llm(ChatRequest(question, allow_llm=True), answer, intent.name) is True
        assert orchestrator._should_use_llm(ChatRequest(question, allow_llm=False), answer, intent.name) is False

    news_intent = router.route("最好的新闻", {})
    assert news_intent.name == "external_data_unavailable"
    news_pack = EvidencePack(report_date="2026-07-10", intent=news_intent, rulebook=[], tools=[])
    news_answer = orchestrator._deterministic_evidence_answer("最好的新闻", news_pack)
    assert "没有接入新闻" in news_answer
    assert "日报日期" not in news_answer

    unknown_intent = router.route("随便说点什么", {})
    assert unknown_intent.name == "clarification"
    unknown_pack = EvidencePack(report_date="2026-07-10", intent=unknown_intent, rulebook=[], tools=[])
    assert "没理解" in orchestrator._deterministic_evidence_answer("随便说点什么", unknown_pack)


def test_chat_data_scope_is_deterministic_and_reports_exact_limits() -> None:
    class ScopeRepository:
        def research_coverage(self):
            return {
                "ETF": {"assetCount": 30, "recordCount": 39579, "startDate": "2020-01-02", "endDate": "2026-07-03"},
                "TL": {"assetCount": 1, "recordCount": 779, "startDate": "2023-04-21", "endDate": "2026-07-10"},
                "CONVERTIBLE": {"assetCount": 307, "recordCount": 614, "startDate": "2026-07-06", "endDate": "2026-07-10"},
            }

    intent = ChatRouter().route("AI问答能访问多少数据？", {})
    assert intent.name == "chat_data_scope"
    tools = ResearchToolbox({}, ScopeRepository()).collect(intent)
    pack = EvidencePack(report_date="2026-07-10", intent=intent, rulebook=[], tools=tools)
    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("AI问答能访问多少数据？", pack)

    assert "ETF：30只，39579条记录，2020-01-02 至 2026-07-03" in answer
    assert "最近30个交易日" in answer
    assert "最近400个交易日" in answer
    assert "AI不会直接访问整个数据库" in answer
    assert ChatOrchestrator(ROOT)._should_use_llm(ChatRequest("AI问答能访问多少数据？", allow_llm=True), answer, intent.name) is False


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
    assert "没有唯一的“最好”" in answer
    assert "强弱分" in answer and "收盘价" in answer


def test_named_etf_two_strategy_question_runs_both_plugins(tmp_path: Path) -> None:
    class HistoryRepository:
        root_dir = tmp_path

        def resolve_asset(self, query: str):
            return {"name": "测试ETF", "code": "111111.SH", "asset_type": "ETF"}

        def get_market_history(self, code: str, limit: int = 400):
            rows = []
            start = date(2025, 1, 1)
            for index in range(220):
                close = 1.0 + index * 0.002
                rows.append(
                    {
                        "trade_date": str(start + timedelta(days=index)),
                        "code": code,
                        "name": "测试ETF",
                        "open": close - 0.002,
                        "high": close + 0.005,
                        "low": close - 0.005,
                        "close": close,
                        "volume": 1000 + index,
                        "payload_json": {"fund_share_change": 0.0},
                    }
                )
            return list(reversed(rows))

    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "strategy_params.json").write_text("{}", encoding="utf-8")
    dashboard = {"etf": {"all_signals": [{"name": "测试ETF", "code": "111111.SH", "position_status": "未持仓/已平仓"}]}}
    router = ChatRouter()
    intent = router.route("为什么测试ETF不好，根据两个策略分析", dashboard)
    assert intent.name == "etf_strategy_comparison"

    tools = ResearchToolbox(dashboard, HistoryRepository()).collect(intent)
    comparison = next(item for item in tools if item.tool == "get_etf_strategy_comparison")
    assert comparison.data["available"] is True
    assert {item["strategy_id"] for item in comparison.data["decisions"]} == {"legacy_v1", "trend_pullback_v2"}

    pack = EvidencePack(report_date="2026-07-10", intent=intent, rulebook=[], tools=tools)
    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("为什么测试ETF不好，根据两个策略分析", pack)
    assert "原策略 v1" in answer
    assert "趋势回踩 2.0" in answer
    assert "不是说测试ETF本身" in answer
    assert ChatOrchestrator(ROOT)._should_use_llm(
        ChatRequest("为什么测试ETF不好，根据两个策略分析", allow_llm=True),
        answer,
        "etf_strategy_comparison",
        agent_planned=True,
    ) is True


def test_absolute_return_request_is_blocked_deterministically() -> None:
    answer = ChatOrchestrator(ROOT)._deterministic_compliance_answer("给我一个保证绝对收益的ETF买法")

    assert "不能保证赚钱" in answer
    assert "不能承诺收益" in answer


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


def test_chat_analysis_range_is_independent_from_page_display_range() -> None:
    class AnalysisRepository:
        def get_market_history(self, code: str, limit: int = 30):
            assert code == "TL.CFE"
            assert limit == 30
            return [{"trade_date": f"2026-06-{index:02d}", "code": code, "close": index} for index in range(1, 31)]

        def get_convertible_rankings(self, limit: int = 30):
            assert limit == 30
            return [
                {"bond_name": f"测试转债{index}", "bond_code": f"11{index:04d}.SH", "rank": index, "score": 100 - index}
                for index in range(1, 31)
            ]

    dashboard = {
        "tlToday": [{"state": "观望"}],
        "tlRecent": [{"date": f"2026-07-{index:02d}", "state": "观望"} for index in range(1, 13)],
        "convertible_bond": {
            "top10": [{"bond_name": f"页面转债{index}", "bond_code": f"12{index:04d}.SH"} for index in range(1, 11)],
            "summary": {},
        },
    }
    toolbox = ResearchToolbox(dashboard, AnalysisRepository())

    tl = toolbox.get_tl_state().data
    convertible = toolbox.get_convertible_top10().data

    assert len(tl["recent"]) == 8
    assert len(tl["history"]) == 30
    assert len(convertible["top10"]) == 10
    assert len(convertible["analysis_universe"]) == 30


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
