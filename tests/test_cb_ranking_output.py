from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.runtime.context import AgentContext
from superpower.skills.convertible_bond_ranking.handler import OUTPUT_COLUMNS, Skill, rank_convertible_bonds, split_candidate_qualification


def test_strategy_params_enable_unresolved_redemption_exclusion() -> None:
    params = json.loads((ROOT / "configs" / "strategy_params.json").read_text(encoding="utf-8"))

    assert params["convertible_bond"]["exclude_unresolved_redemption_trigger"] is True


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


def _candidate(**overrides: object) -> dict[str, object]:
    row = {column: None for column in OUTPUT_COLUMNS}
    row.update(
        {
            "rank": 1,
            "date": "2026-06-26",
            "bond_code": "Q",
            "bond_name": "合格转债",
            "code": "Q",
            "name": "合格转债",
            "price": 112,
            "remaining_years": 2,
            "conversion_premium_rate": 20,
            "premium_rate": 20,
            "ytm": 1,
            "bond_rating": "AA+",
            "rating": "AA+",
            "sw_l1": "电子",
            "sw_l2": "消费电子",
            "remaining_size": 8,
            "score": 62,
            "risk_level": "低",
            "risk_flags": "",
            "risk_notes": ["无明显风控扣分项"],
            "rank_reason": "测试候选",
            "action": "进入可转债Top10候选池",
            "quality_notes": ["无明显风控扣分项"],
        }
    )
    row.update(overrides)
    return row


def test_score_zero_bond_cannot_enter_top_candidates() -> None:
    ranked = pd.DataFrame([_candidate(bond_code="Z", score=0)])

    qualified, _, risk_watch = split_candidate_qualification(ranked)

    assert qualified.empty
    assert risk_watch.iloc[0]["bond_code"] == "Z"
    assert not bool(risk_watch.iloc[0]["eligible_for_top"])


def test_high_risk_bond_cannot_enter_top_candidates() -> None:
    ranked = pd.DataFrame([_candidate(bond_code="H", risk_level="高", risk_flags="转股溢价率偏高，已扣分")])

    qualified, _, risk_watch = split_candidate_qualification(ranked)

    assert qualified.empty
    assert risk_watch.iloc[0]["bond_code"] == "H"


def test_score_below_50_cannot_enter_top_candidates() -> None:
    ranked = pd.DataFrame([_candidate(bond_code="W", score=45)])

    qualified, weak_watch, risk_watch = split_candidate_qualification(ranked)

    assert qualified.empty
    assert risk_watch.empty
    assert weak_watch.iloc[0]["bond_code"] == "W"
    assert "评分低于50" in weak_watch.iloc[0]["not_top_reason"]


def test_top10_does_not_backfill_from_watch_buckets(tmp_path: Path) -> None:
    data = pd.DataFrame(
        [
            {"date": "2026-06-26", "bond_code": "Q", "bond_name": "合格转债", "price": 112, "remaining_years": 2, "conversion_premium_rate": 20, "ytm": 0.01, "stock_name": "正股Q", "bond_rating": "AA+", "remaining_size": 8, "sw_l1": "电子"},
            {"date": "2026-06-26", "bond_code": "W", "bond_name": "弱观察转债", "price": 118, "remaining_years": 2, "conversion_premium_rate": 20, "ytm": 0.01, "stock_name": "正股W", "bond_rating": "AA+", "remaining_size": 4, "sw_l1": "电子"},
            {"date": "2026-06-26", "bond_code": "R", "bond_name": "风险转债", "price": 120, "remaining_years": 2, "conversion_premium_rate": 45, "ytm": 0.01, "stock_name": "正股R", "bond_rating": "AA+", "remaining_size": 8, "sw_l1": "电子"},
        ]
    )
    context = AgentContext("test", tmp_path, {"cb_data": data, "strategy_params": {"convertible_bond": {"top_n": 10}}})

    Skill().run(context)

    top10 = context.get("cb_top10")
    assert list(top10["bond_code"]) == ["Q"]
    assert len(context.get("cb_weak_watch")) >= 1
    assert len(context.get("cb_risk_watch")) >= 1


def test_no_qualified_candidates_sets_quality_message() -> None:
    ranked = pd.DataFrame([_candidate(bond_code="W", score=45)])
    qualified, weak_watch, risk_watch = split_candidate_qualification(ranked)

    from superpower.skills.convertible_bond_ranking.handler import _empty_excluded, _qualification_summary

    summary = _qualification_summary(qualified, weak_watch, risk_watch, _empty_excluded())

    assert qualified.empty
    assert "今日无合格可转债 Top 候选" in summary["quality_message"]


def test_legacy_top10_contains_only_qualified(tmp_path: Path) -> None:
    data = pd.DataFrame(
        [
            {"date": "2026-06-26", "bond_code": "Q", "bond_name": "合格转债", "price": 112, "remaining_years": 2, "conversion_premium_rate": 20, "ytm": 0.01, "stock_name": "正股Q", "bond_rating": "AA+", "remaining_size": 8, "sw_l1": "电子"},
            {"date": "2026-06-26", "bond_code": "W", "bond_name": "弱观察转债", "price": 118, "remaining_years": 2, "conversion_premium_rate": 20, "ytm": 0.01, "stock_name": "正股W", "bond_rating": "AA+", "remaining_size": 4, "sw_l1": "电子"},
        ]
    )
    context = AgentContext("test", tmp_path, {"cb_data": data, "strategy_params": {"convertible_bond": {"top_n": 10}}})

    Skill().run(context)

    assert "cb_top10" in context.artifacts
    assert list(context.get("cb_top10")["bond_code"]) == list(context.get("cb_qualified")["bond_code"])
