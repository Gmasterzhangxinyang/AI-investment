from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.chat.orchestrator import ChatOrchestrator
from superpower.chat.schemas import ChatIntent, EvidencePack, ToolResult


def test_tl_answer_uses_daily_and_weekly_rule_evidence() -> None:
    pack = EvidencePack(
        report_date="2026-06-26",
        intent=ChatIntent("tl_timing", 0.95, {"name": "30年国债期货TL", "code": "TL.CFE", "asset_type": "TL"}),
        rulebook=[],
        tools=[
            ToolResult(
                tool="get_tl_state",
                title="TL timing",
                source="dashboard.tlToday",
                summary="TL 当前状态 不做交易。",
                data={
                    "today": [
                        {
                            "date": "2026-06-26T00:00:00.000",
                            "name": "30年国债期货TL",
                            "code": "TL.CFE",
                            "收盘价": 114.04,
                            "ma5": 113.82,
                            "ma10": 113.724,
                            "ma20": 113.754,
                            "ma60": 113.1197,
                            "vol_ratio60": 1.0512,
                            "macd_hist": 0.0033,
                            "kdj_j": 86.4665,
                            "week_macd_hist": 0.3201,
                            "week_kdj_j": 87.612,
                            "daily_macd_reason": "绿转红阶段",
                            "daily_kdj_threshold_check": "日线近3日J值最低值：69.7480，未低于5，KDJ低位反弹条件不满足",
                            "weekly_macd_reason": "红柱T日短于T-1日",
                            "weekly_kdj_threshold_check": "周线近2周J值最低值：71.7775，未低于20，KDJ低位反弹条件不满足",
                            "state": "不做交易",
                            "display_status": "不做交易",
                            "status": "no_trade",
                            "no_trade_signal": True,
                            "reason": "红柱T日短于T-1日；日线KDJ低位反弹条件不满足",
                            "rule_hits": "满足TL不做交易规则",
                            "risk_notes": "TL 当前仅做状态诊断，不模拟期货连续合约、换月、杠杆、保证金、滑点和完整平仓收益。",
                        }
                    ],
                    "recent": [],
                    "history": [],
                },
            )
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("TL当前状态怎么样？", pack)

    assert "今日状态是：不做交易" in answer
    assert "日线证据" in answer
    assert "周线证据" in answer
    assert "红柱T日短于T-1日" in answer
    assert "当前属于不做交易路径" in answer
