import pandas as pd
import pytest

from superpower.skills.etf_rotation_strategy.contracts import (
    ETFDecision,
    ETFHistory,
    MediumStatus,
    ShortEntryStatus,
)


def test_history_rejects_future_rows() -> None:
    rows = pd.DataFrame({"date": pd.to_datetime(["2026-07-01", "2026-07-02"])})

    with pytest.raises(ValueError, match="after as_of"):
        ETFHistory(
            code="510001",
            name="样例ETF",
            rows=rows,
            as_of=pd.Timestamp("2026-07-01"),
        )


def test_decision_has_stable_state_and_evidence_fields() -> None:
    decision = ETFDecision.unavailable(
        as_of=pd.Timestamp("2026-07-01"),
        code="510001",
        name="样例ETF",
        strategy_id="trend_pullback_v2",
        strategy_version="2.0.0",
        reason="history_rows=120; required=180",
    )

    assert decision.medium_status is MediumStatus.DATA_UNAVAILABLE
    assert decision.short_entry_status is ShortEntryStatus.DATA_UNAVAILABLE
    assert decision.buy_candidate is False
    assert decision.watch_candidate is False
    assert decision.sell_alert is False
    assert decision.metrics == {}
    assert decision.risk_notes == ("history_rows=120; required=180",)
