from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.chat.orchestrator import ChatOrchestrator
from superpower.chat.router import ChatRouter
from superpower.chat.schemas import ChatIntent, EvidencePack, ToolResult


def test_router_resolves_etf_from_all_signals_before_parameter_questions() -> None:
    dashboard = {"etf": {"all_signals": [{"name": "芯片ETF", "code": "512760.SH"}]}}

    intent = ChatRouter().route("芯片ETF量能怎么样？", dashboard)

    assert intent.name == "etf_detail"
    assert intent.entities["name"] == "芯片ETF"
    assert intent.entities["code"] == "512760.SH"


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
    assert "来源：最新 dashboard.etf.all_signals" in answer
