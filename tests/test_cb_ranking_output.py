from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.skills.convertible_bond_ranking.handler import rank_convertible_bonds


def test_convertible_ranking_returns_score_breakdown_and_excluded_list() -> None:
    data = pd.DataFrame(
        [
            {"date": "2026-06-26", "bond_code": "A", "bond_name": "A转债", "price": 112, "remaining_years": 2, "conversion_premium_rate": 0.20, "ytm": 0.01, "stock_name": "正股A", "bond_rating": "AAA", "remaining_size": 5, "sw_l1": "银行"},
            {"date": "2026-06-26", "bond_code": "B", "bond_name": "B转债", "price": 95, "remaining_years": 2, "conversion_premium_rate": 0.20, "ytm": 0.01, "stock_name": "正股B", "bond_rating": "AAA", "remaining_size": 5, "sw_l1": "银行"},
        ]
    )
    ranked, excluded = rank_convertible_bonds(data, {"convertible_bond": {}}, include_excluded=True)
    assert ranked.iloc[0]["bond_code"] == "A"
    assert "score_breakdown" in ranked.columns
    assert isinstance(ranked.iloc[0]["risk_notes"], list)
    assert ranked.iloc[0]["action"] == "进入可转债Top10候选池"
    assert excluded.iloc[0]["bond_code"] == "B"
    assert "价格低于" in excluded.iloc[0]["excluded_reason"]


def test_unresolved_redemption_trigger_is_excluded_by_default() -> None:
    data = pd.DataFrame(
        [
            {
                "date": "2026-06-26",
                "bond_code": "R",
                "bond_name": "强赎转债",
                "price": 112,
                "remaining_years": 2,
                "conversion_premium_rate": 0.20,
                "ytm": 0.01,
                "stock_name": "正股R",
                "bond_rating": "AAA",
                "remaining_size": 5,
                "sw_l1": "银行",
                "stock_price": 13,
                "conversion_price": 10,
                "redemption_trigger_ratio": 1.3,
            }
        ]
    )

    ranked, excluded = rank_convertible_bonds(data, {"convertible_bond": {}}, include_excluded=True)

    assert ranked.empty
    assert excluded.iloc[0]["bond_code"] == "R"
    assert "触发强赎价" in excluded.iloc[0]["excluded_reason"]
