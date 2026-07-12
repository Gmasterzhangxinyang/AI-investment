from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from .handler import add_indicators


def classify_ma20_slope(value: float, tolerance: float) -> str:
    if pd.isna(value):
        return "data_unavailable"
    if value < -tolerance:
        return "down"
    if value > tolerance:
        return "up"
    return "flat"


def classify_weekly_macd(hist: float, previous: float) -> str:
    if pd.isna(hist) or pd.isna(previous):
        return "data_unavailable"
    if hist == 0:
        return "neutral_zero"
    if hist > 0:
        return "red_strengthening" if hist >= previous else "red_weakening"
    return "green_narrowing" if hist > previous else "green_widening"


def add_etf_indicators(
    group: pd.DataFrame,
    volume_field: str,
    medium_profile: Mapping[str, Any],
    *,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if group.empty:
        return group.copy()
    rows = group.copy()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    if as_of is not None:
        rows = rows[rows["date"] <= pd.Timestamp(as_of)]
    rows = rows.sort_values("date").reset_index(drop=True)
    if "ma20" not in rows.columns or "macd_hist" not in rows.columns:
        rows = add_indicators(rows, volume_field).reset_index(drop=True)

    lookback = int(medium_profile.get("ma20_slope_lookback", 5))
    tolerance = float(medium_profile.get("ma20_flat_tolerance", 0.003))
    rows["ma20_slope_5d"] = rows["ma20"] / rows["ma20"].shift(lookback) - 1
    rows["ma20_slope_state"] = rows["ma20_slope_5d"].map(
        lambda value: classify_ma20_slope(value, tolerance)
    )

    week_end = rows["date"].map(_week_end)
    weekly = (
        pd.DataFrame(
            {
                "week_end": week_end,
                "close": pd.to_numeric(rows["收盘价"], errors="coerce"),
            }
        )
        .dropna(subset=["week_end", "close"])
        .groupby("week_end", as_index=False)
        .agg(close=("close", "last"))
        .sort_values("week_end")
        .reset_index(drop=True)
    )
    weekly = _weekly_macd(weekly)

    official_hist: list[float] = []
    official_prev_hist: list[float] = []
    official_state: list[str] = []
    preview_hist: list[float] = []
    preview_state: list[str] = []
    completed_dates: list[pd.Timestamp | pd.NaT] = []
    weekly_ends = weekly["week_end"].to_numpy(dtype="datetime64[ns]")

    for index, row in rows.iterrows():
        current_week_end = _week_end(row["date"])
        position = int(
            np.searchsorted(
                weekly_ends,
                np.datetime64(current_week_end),
                side="left",
            )
            - 1
        )
        if position >= 0:
            completed = weekly.iloc[position]
            hist = float(completed["hist"]) if pd.notna(completed["hist"]) else np.nan
            previous = (
                float(weekly.iloc[position - 1]["hist"])
                if position > 0 and pd.notna(weekly.iloc[position - 1]["hist"])
                else np.nan
            )
            completed_date: pd.Timestamp | pd.NaT = pd.Timestamp(completed["week_end"])
        else:
            hist = np.nan
            previous = np.nan
            completed_date = pd.NaT
        preview = _preview_histogram(
            weekly=weekly,
            completed_position=position,
            candidate_close=float(row["收盘价"]),
        )
        official_hist.append(hist)
        official_prev_hist.append(previous)
        official_state.append(classify_weekly_macd(hist, previous))
        preview_hist.append(preview)
        preview_state.append(classify_weekly_macd(preview, hist))
        completed_dates.append(completed_date)

    rows["weekly_macd_hist"] = official_hist
    rows["weekly_macd_prev_hist"] = official_prev_hist
    rows["weekly_macd_state"] = official_state
    rows["weekly_macd_preview"] = preview_hist
    rows["weekly_macd_preview_state"] = preview_state
    rows["weekly_completed_date"] = completed_dates
    previous_daily = rows["macd_hist"].shift(1)
    rows["daily_macd_state"] = [
        classify_weekly_macd(current, previous)
        for current, previous in zip(rows["macd_hist"], previous_daily, strict=False)
    ]
    return rows


def _week_end(value: Any) -> pd.Timestamp:
    return pd.Timestamp(value).to_period("W-FRI").end_time.normalize()


def _weekly_macd(weekly: pd.DataFrame) -> pd.DataFrame:
    result = weekly.copy()
    close = result["close"].astype(float)
    result["ema12_state"] = close.ewm(span=12, adjust=False).mean()
    result["ema26_state"] = close.ewm(span=26, adjust=False).mean()
    count = pd.Series(np.arange(1, len(result) + 1), index=result.index)
    dif_state = result["ema12_state"] - result["ema26_state"]
    result["dif"] = dif_state.where(count >= 26)
    result["dea_state"] = result["dif"].ewm(span=9, adjust=False).mean()
    valid_dif_count = (count - 25).clip(lower=0)
    result["dea"] = result["dea_state"].where(valid_dif_count >= 9)
    result["hist"] = result["dif"] - result["dea"]
    return result


def _preview_histogram(
    *,
    weekly: pd.DataFrame,
    completed_position: int,
    candidate_close: float,
) -> float:
    completed_count = completed_position + 1
    if completed_position >= 0:
        previous = weekly.iloc[completed_position]
        ema12 = _next_ema(float(previous["ema12_state"]), candidate_close, 12)
        ema26 = _next_ema(float(previous["ema26_state"]), candidate_close, 26)
    else:
        ema12 = candidate_close
        ema26 = candidate_close
    total_count = completed_count + 1
    if total_count < 26:
        return np.nan
    dif = ema12 - ema26
    prior_valid_dif = max(completed_count - 25, 0)
    if prior_valid_dif == 0:
        dea = dif
    else:
        previous_dea = weekly.iloc[completed_position]["dea_state"]
        if pd.isna(previous_dea):
            dea = dif
        else:
            dea = _next_ema(float(previous_dea), dif, 9)
    total_valid_dif = max(total_count - 25, 0)
    return dif - dea if total_valid_dif >= 9 else np.nan


def _next_ema(previous: float, value: float, span: int) -> float:
    alpha = 2 / (span + 1)
    return alpha * value + (1 - alpha) * previous
