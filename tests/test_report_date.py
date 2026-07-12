from datetime import datetime

import pandas as pd

from superpower.tools.report_date import latest_market_date, report_date_text


def frame(*dates: str) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(list(dates))})


def test_latest_market_date_includes_convertible_bond_frame() -> None:
    result = latest_market_date(
        frame("2026-07-03"),
        frame("2026-07-03"),
        frame("2026-07-06"),
    )

    assert result == pd.Timestamp("2026-07-06")
    assert report_date_text(frame("2026-07-03"), frame("2026-07-06")) == "20260706"


def test_latest_market_date_ignores_empty_and_invalid_frames() -> None:
    assert latest_market_date(pd.DataFrame(), pd.DataFrame({"date": ["bad"]})) is None
    assert report_date_text(
        pd.DataFrame(),
        now=datetime(2026, 7, 12, 9, 0),
    ) == "20260712"
