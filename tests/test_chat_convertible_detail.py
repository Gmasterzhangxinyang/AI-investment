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


def test_router_resolves_convertible_from_excluded_dashboard_rows() -> None:
    dashboard = {
        "cbExcluded": [
            {
                "bond_name": "国投转债",
                "bond_code": "110073.SH",
                "qualification": "excluded",
                "excluded_reason": "转股溢价率54.61%过高",
            }
        ]
    }

    intent = ChatRouter().route("国投转债怎么样？", dashboard)

    assert intent.name == "convertible_bond"
    assert intent.entities["name"] == "国投转债"
    assert intent.entities["code"] == "110073.SH"


def test_single_convertible_answer_uses_dashboard_exclusion_reason_without_llm() -> None:
    pack = EvidencePack(
        report_date="2026-06-26",
        intent=ChatIntent("convertible_bond", 0.94, {"name": "国投转债", "code": "110073.SH", "asset_type": "CONVERTIBLE"}),
        rulebook=[],
        tools=[
            ToolResult(
                tool="get_convertible_detail",
                title="Convertible bond detail",
                source="dashboard.convertible_bond",
                summary="国投转债 当前分层 excluded。",
                data={
                    "asset": {"name": "国投转债", "code": "110073.SH", "asset_type": "CONVERTIBLE"},
                    "snapshot": None,
                    "dashboard_row": {
                        "bond_name": "国投转债",
                        "bond_code": "110073.SH",
                        "price": 104.9969,
                        "conversion_premium_rate": 54.611,
                        "ytm": 1.8422,
                        "bond_rating": "AAA",
                        "remaining_size": 79.99026038,
                        "redemption_status": "未触发强赎价",
                        "qualification": "excluded",
                        "eligible_for_top": False,
                        "score_grade": "E",
                        "not_top_reason": "转股溢价率54.61%过高",
                        "quality_notes": ["转股溢价率54.61%过高"],
                    },
                    "source_row": {
                        "bond_name": "国投转债",
                        "bond_code": "110073.SH",
                        "price": 104.9969,
                        "conversion_premium_rate": 54.611,
                        "ytm": 1.8422,
                        "bond_rating": "AAA",
                        "remaining_size": 79.99026038,
                        "redemption_status": "未触发强赎价",
                        "qualification": "excluded",
                        "eligible_for_top": False,
                        "score_grade": "E",
                        "not_top_reason": "转股溢价率54.61%过高",
                        "quality_notes": ["转股溢价率54.61%过高"],
                        "detail_source": "dashboard",
                    },
                },
            )
        ],
    )

    answer = ChatOrchestrator(ROOT)._deterministic_evidence_answer("国投转债怎么样？", pack)

    assert "国投转债（110073.SH）" in answer
    assert "当前分层：排除列表" in answer
    assert "是否可进合格 Top：否" in answer
    assert "转股溢价率54.61%过高" in answer
    assert "弱观察和风险观察不补进合格 Top" in answer
