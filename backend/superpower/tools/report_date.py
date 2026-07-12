from __future__ import annotations

from datetime import datetime

import pandas as pd


def latest_market_date(*frames: pd.DataFrame) -> pd.Timestamp | None:
    candidates: list[pd.Timestamp] = []
    for frame in frames:
        if frame.empty or "date" not in frame.columns:
            continue
        value = pd.to_datetime(frame["date"], errors="coerce").max()
        if pd.notna(value):
            candidates.append(pd.Timestamp(value).normalize())
    return max(candidates) if candidates else None


def report_date_text(*frames: pd.DataFrame, now: datetime | None = None) -> str:
    value = latest_market_date(*frames)
    if value is not None:
        return value.strftime("%Y%m%d")
    return (now or datetime.now()).strftime("%Y%m%d")
