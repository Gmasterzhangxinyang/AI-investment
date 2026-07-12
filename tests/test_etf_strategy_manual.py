from __future__ import annotations

from superpower.skills.report_generation.handler import _etf_strategy_manual


def test_legacy_manual_explains_non_blocking_risk_overlay() -> None:
    manual = _etf_strategy_manual(
        {
            "strategy_id": "legacy_v1",
            "strategy_version": "1.0.0",
            "config_hash": "a" * 64,
        }
    )

    risk = manual.loc[manual["项目"] == "风险辅助", "说明"].iloc[0]
    assert "不改变原策略候选、评分和排名" in risk


def test_v2_manual_remains_an_independent_strategy_explanation() -> None:
    manual = _etf_strategy_manual(
        {
            "strategy_id": "trend_pullback_v2",
            "strategy_version": "2.0.0",
            "config_hash": "b" * 64,
        }
    )

    assert "中期趋势" in set(manual["项目"])
    assert "短期入场" in set(manual["项目"])
    assert "风险辅助" not in set(manual["项目"])
