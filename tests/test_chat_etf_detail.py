from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.chat.orchestrator import ChatOrchestrator
from superpower.chat.guardrails import ChatGuardrails
from superpower.chat.router import ChatRouter
from superpower.chat.schemas import ChatIntent, ChatRequest, EvidencePack, ToolResult


def test_router_resolves_etf_from_all_signals_before_parameter_questions() -> None:
    dashboard = {"etf": {"all_signals": [{"name": "芯片ETF", "code": "512760.SH"}]}}

    intent = ChatRouter().route("芯片ETF量能怎么样？", dashboard)

    assert intent.name == "etf_detail"
    assert intent.entities["name"] == "芯片ETF"
    assert intent.entities["code"] == "512760.SH"


def test_router_treats_bare_known_etf_name_as_single_asset_detail() -> None:
    dashboard = {
        "etf": {
            "all_signals": [
                {"name": "黄金ETF", "code": "159934.SZ", "asset_type": "ETF"},
            ]
        }
    }

    for question in ["etf黄金", "黄金etf", "黄金etf今天"]:
        intent = ChatRouter().route(question, dashboard)
        assert intent.name == "etf_detail"
        assert intent.entities["name"] == "黄金ETF"
        assert intent.entities["code"] == "159934.SZ"


def test_router_keeps_explicit_named_etf_signal_queries_scoped() -> None:
    dashboard = {
        "etf": {
            "all_signals": [
                {"name": "黄金ETF", "code": "159934.SZ", "asset_type": "ETF"},
            ]
        }
    }

    assert ChatRouter().route("黄金ETF建仓候选", dashboard).name == "etf_entry"
    assert ChatRouter().route("黄金ETF平仓提示", dashboard).name == "etf_exit"


def test_router_preserves_every_named_etf_in_multi_asset_question() -> None:
    dashboard = {
        "etf": {
            "all_signals": [
                {"name": "创新药ETF", "code": "159992.SZ", "asset_type": "ETF"},
                {"name": "酒ETF", "code": "512690.SH", "asset_type": "ETF"},
                {"name": "中证500ETF", "code": "510500.SH", "asset_type": "ETF"},
            ]
        }
    }

    intent = ChatRouter().route("看下酒etf、创新药etf和中证500etf有没有进入观测或者趋势确认", dashboard)

    assert intent.name == "etf_detail"
    assert intent.entities["codes"] == "512690.SH|159992.SZ|510500.SH"
    assert intent.entities["names"] == "酒ETF|创新药ETF|中证500ETF"
    assert intent.entities["asset_count"] == "3"
    assert intent.entities["asset_type"] == "ETF"


def test_multi_etf_answer_reports_each_asset_without_false_missing_evidence() -> None:
    pack = EvidencePack(
        report_date="20260715",
        intent=ChatIntent(
            "etf_detail",
            0.94,
            {
                "codes": "512690.SH|159992.SZ|510500.SH",
                "names": "酒ETF|创新药ETF|中证500ETF",
            },
        ),
        rulebook=[],
        tools=[
            ToolResult(
                tool="get_etf_multi_assets",
                title="ETF multi-asset status",
                source="dashboard.etf.all_signals",
                summary="3只ETF",
                data={
                    "assets": [
                        {
                            "asset": {"name": "酒ETF", "code": "512690.SH"},
                            "dashboard_signal": {
                                "name": "酒ETF", "code": "512690.SH", "medium_status": "do_not_participate",
                                "short_entry_status": "no_entry", "medium_reason": "中期趋势存在硬性否决条件",
                                "rule_hits": "ma20_slope_down", "close": 0.416,
                            },
                        },
                        {
                            "asset": {"name": "创新药ETF", "code": "159992.SZ"},
                            "dashboard_signal": {
                                "name": "创新药ETF", "code": "159992.SZ", "medium_status": "trend_confirmed",
                                "short_entry_status": "no_entry", "medium_reason": "中期趋势已确认", "close": 0.912,
                            },
                        },
                        {
                            "asset": {"name": "中证500ETF", "code": "510500.SH"},
                            "dashboard_signal": {
                                "name": "中证500ETF", "code": "510500.SH", "medium_status": "do_not_participate",
                                "short_entry_status": "no_entry", "medium_reason": "中期趋势存在硬性否决条件",
                                "rule_hits": "weekly_macd_green_widening", "close": 8.151,
                            },
                        },
                    ]
                },
            )
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("三只ETF有没有进入观测或者趋势确认", pack)

    assert "酒ETF（512690.SH）" in answer
    assert "创新药ETF（159992.SZ）" in answer
    assert "中证500ETF（510500.SH）" in answer
    assert "趋势确认：创新药ETF" in answer
    assert "尚未进入两种状态：酒ETF、中证500ETF" in answer
    assert "缺少证据" not in answer


def test_multi_etf_status_answer_stays_deterministic_when_llm_is_enabled() -> None:
    orchestrator = ChatOrchestrator(ROOT)

    use_llm = orchestrator._should_use_llm(
        ChatRequest(question="对比三只ETF当前状态", allow_llm=True),
        "截至 20260715，这几只 ETF 的状态如下：",
        "etf_detail",
    )

    assert not use_llm


def test_ai_enabled_single_etf_trend_question_uses_model_but_exact_metric_does_not() -> None:
    orchestrator = ChatOrchestrator(ROOT)

    assert orchestrator._should_use_llm(
        ChatRequest(question="查下黄金ETF中期趋势", allow_llm=True),
        "规则兜底回答",
        "etf_detail",
    )
    assert not orchestrator._should_use_llm(
        ChatRequest(question="黄金ETF收盘价", allow_llm=True),
        "规则精确数值回答",
        "etf_detail",
    )
    assert not orchestrator._should_use_llm(
        ChatRequest(question="查下黄金ETF中期趋势", allow_llm=False),
        "规则兜底回答",
        "etf_detail",
    )


def test_frustrated_followup_keeps_previous_asset_context() -> None:
    orchestrator = ChatOrchestrator(ROOT)
    memory = {
        "lastAsset": {"name": "黄金ETF", "code": "159934.SZ", "asset_type": "ETF"},
        "lastIntent": "etf_detail",
        "turns": [{"question": "查下黄金ETF中期趋势", "intent": "etf_detail"}],
    }

    routed_question = orchestrator._question_with_short_term_memory("我让你查啊", memory)
    intent = ChatRouter().route(
        routed_question,
        {"etf": {"all_signals": [{"name": "黄金ETF", "code": "159934.SZ"}]}},
    )
    enriched = orchestrator._enrich_intent_with_short_term_memory("我让你查啊", intent, memory)

    assert enriched.name == "etf_detail"
    assert enriched.entities["code"] == "159934.SZ"


def test_ai_prompt_separates_rule_result_from_independent_ai_analysis() -> None:
    pack = EvidencePack(
        report_date="2026-07-15",
        intent=ChatIntent("etf_detail", 0.94, {"name": "黄金ETF", "code": "159934.SZ"}),
        rulebook=["规则状态必须来自确定性字段"],
        tools=[],
    )

    prompt = ChatOrchestrator(ROOT)._build_prompt("查下黄金ETF中期趋势", pack)

    assert "系统规则结果" in prompt
    assert "AI分析" in prompt
    assert "可以说明是否赞同规则" in prompt


def test_unknown_named_etf_routes_to_no_data_answer() -> None:
    dashboard = {"etf": {"all_signals": [{"name": "芯片ETF", "code": "512760.SH"}]}}

    intent = ChatRouter().route("纳指ETF量能怎么样？", dashboard)

    assert intent.name == "etf_detail"
    assert intent.entities["name"] == "纳指ETF"
    assert intent.entities["not_found"] == "true"


def test_unknown_named_etf_answer_does_not_guess() -> None:
    pack = EvidencePack(
        report_date="2026-06-26",
        intent=ChatIntent("etf_detail", 0.91, {"name": "纳指ETF", "asset_type": "ETF", "not_found": "true"}),
        rulebook=[],
        tools=[
            ToolResult(
                tool="get_rule_contract",
                title="Rule contract",
                source="configs.strategy_params",
                summary="",
                data={"strategy_params": {"etf": {"buy_volume_ratio_min": 1.1}}},
            ),
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("纳指ETF量能怎么样？", pack)

    assert "没有这只 ETF 的有效数据" in answer
    assert "不会用库外信息补猜" in answer
    assert "量能倍数" not in answer


def test_guardrail_allows_position_path_entry_candidate_wording() -> None:
    text = "持仓路径：系统当前把它识别为“持仓中”。持仓中才检查平仓提示；空仓或已平仓才检查建仓候选和关注池。"

    result = ChatGuardrails().validate_output(text, ChatIntent("etf_detail", 0.93, {}), [])

    assert result.passed
    assert result.text == text


def test_guardrail_still_blocks_entry_advice_without_signal() -> None:
    text = "建议建仓这只ETF。"

    result = ChatGuardrails().validate_output(text, ChatIntent("etf_detail", 0.93, {}), [])

    assert not result.passed
    assert "ETF 建仓/买入表述缺少确定性 entry 信号依据。" in result.issues


def test_guardrail_allows_waiting_for_entry_conditions() -> None:
    text = "可以继续观察，等待建仓条件确认。"

    result = ChatGuardrails().validate_output(text, ChatIntent("etf_detail", 0.93, {}), [])

    assert result.passed
    assert result.text == text


def test_single_etf_answer_uses_rule_evidence_from_dashboard_signal() -> None:
    pack = EvidencePack(
        report_date="2026-06-26",
        intent=ChatIntent("etf_detail", 0.94, {"name": "芯片ETF", "code": "512760.SH", "asset_type": "ETF"}),
        rulebook=[],
        tools=[
            ToolResult(
                tool="get_rule_contract",
                title="Rule contract",
                source="configs.strategy_params",
                summary="",
                data={"strategy_params": {"etf": {"buy_volume_ratio_min": 1.1}}},
            ),
            ToolResult(
                tool="get_etf_single_asset",
                title="ETF single asset",
                source="dashboard.etf.all_signals",
                summary="",
                data={
                    "asset": {"name": "芯片ETF", "code": "512760.SH"},
                    "dashboard_signal": {
                        "date": "2026-06-26",
                        "name": "芯片ETF",
                        "code": "512760.SH",
                        "display_action": "未触发",
                        "position_status": "未持仓/已平仓",
                        "score": 85.93,
                        "close": 1.462,
                        "ma5": 1.408,
                        "ma10": 1.3098,
                        "ma20": 1.2185,
                        "ma60": 1.0603,
                        "vol_ratio60": 1.4742,
                        "macd_hist": 0.0311,
                        "metrics": {"dif": 0.0806, "dea": 0.0496},
                        "ma5_ma10_signal": "MA5高于MA10",
                        "ma5_ma20_status": "MA5高于MA20（增强项）",
                        "volume_check": "前60日均量倍数1.4742，阈值1.1，达标",
                        "signal_reason": "未触发建仓候选：规则A缺MA5今日未上穿MA10；规则B缺DIF今日未上穿DEA",
                        "risk_overlay_level": "caution",
                        "risk_overlay_summary": "MA20仍向下；仅作风险辅助，不改变原策略评分和排名",
                    },
                    "latest_bar": {},
                    "history": [
                        {"trade_date": "2026-06-25", "close": 1.48},
                        {"trade_date": "2026-06-26", "close": 1.462},
                    ],
                },
            ),
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("芯片ETF量能怎么样？", pack)

    assert "今日判断是：未触发" in answer
    assert "量能倍数 1.4742" in answer
    assert "规则A缺MA5今日未上穿MA10" in answer
    assert "风险辅助：MA20仍向下" in answer
    assert "不改变原策略评分和排名" in answer
    assert "来源：最新 dashboard.etf.all_signals" in answer


def test_single_etf_close_question_returns_focused_fast_answer() -> None:
    pack = EvidencePack(
        report_date="2026-07-10",
        intent=ChatIntent("etf_detail", 0.94, {"name": "黄金ETF", "code": "159934.SZ", "asset_type": "ETF"}),
        rulebook=[],
        tools=[
            ToolResult(
                tool="get_etf_single_asset",
                title="ETF single asset",
                source="dashboard.etf.all_signals",
                summary="",
                data={
                    "asset": {"name": "黄金ETF", "code": "159934.SZ"},
                    "dashboard_signal": {
                        "date": "2026-07-03",
                        "name": "黄金ETF",
                        "code": "159934.SZ",
                        "display_action": "未触发",
                        "close": 9.056,
                        "score": 47.37,
                    },
                    "latest_bar": {},
                    "history": [
                        {"trade_date": "2026-07-02", "close": 8.85},
                        {"trade_date": "2026-07-03", "close": 9.056},
                    ],
                },
            )
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("黄金ETF收盘价", pack)

    assert "收盘价为 9.056" in answer
    assert "最新有效交易日是 2026-07-03" in answer
    assert "不是实时行情" in answer
    assert "策略状态" not in answer
