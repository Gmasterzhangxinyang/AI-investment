from __future__ import annotations

import numpy as np
import pandas as pd

from superpower.runtime.context import AgentContext


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        etf_raw = context.get("etf_market_raw")
        tl_raw = context.get("tl_market_raw")

        if etf_raw.empty:
            etf_indicators = _empty_indicators(etf_raw, "成交量（万股）")
        else:
            etf_indicators = pd.concat(
                [add_indicators(group, "成交量（万股）") for _, group in etf_raw.groupby(["name", "code"])],
                ignore_index=True,
            )
        if tl_raw.empty:
            tl_indicators = _empty_indicators(tl_raw, "成交量")
        else:
            tl_indicators = add_indicators(tl_raw, "成交量").sort_values("date").reset_index(drop=True)

        context.put("etf_indicators", etf_indicators)
        context.put("tl_indicators", tl_indicators)
        return {
            "etf_rows": len(etf_indicators),
            "tl_rows": len(tl_indicators),
        }


def add_indicators(group: pd.DataFrame, volume_field: str) -> pd.DataFrame:
    if group.empty:
        return _empty_indicators(group, volume_field)
    g = group.sort_values("date").copy()
    close = g["收盘价"].astype(float)
    high = g["最高价"].astype(float)
    low = g["最低价"].astype(float)
    volume = g[volume_field].astype(float)

    for window in (5, 10, 20, 60):
        g[f"ma{window}"] = close.rolling(window, min_periods=window).mean()

    volume_for_average = volume.where(volume > 0)
    g["vol_ma60"] = volume_for_average.shift(1).rolling(60, min_periods=20).mean()
    g["vol_ratio60"] = volume / g["vol_ma60"]

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    g["dif"] = ema12 - ema26
    g["dea"] = g["dif"].ewm(span=9, adjust=False, min_periods=9).mean()
    g["macd_hist"] = g["dif"] - g["dea"]

    low9 = low.rolling(9, min_periods=9).min()
    high9 = high.rolling(9, min_periods=9).max()
    rsv = ((close - low9) / (high9 - low9) * 100).replace([np.inf, -np.inf], np.nan).fillna(50)

    k_values: list[float] = []
    d_values: list[float] = []
    k_val = 50.0
    d_val = 50.0
    for value in rsv:
        k_val = 2 / 3 * k_val + 1 / 3 * float(value)
        d_val = 2 / 3 * d_val + 1 / 3 * k_val
        k_values.append(k_val)
        d_values.append(d_val)

    g["kdj_k"] = k_values
    g["kdj_d"] = d_values
    g["kdj_j"] = 3 * g["kdj_k"] - 2 * g["kdj_d"]
    return g


def _empty_indicators(frame: pd.DataFrame, volume_field: str) -> pd.DataFrame:
    out = frame.copy()
    for col in [
        "ma5",
        "ma10",
        "ma20",
        "ma60",
        "vol_ma60",
        "vol_ratio60",
        "dif",
        "dea",
        "macd_hist",
        "kdj_k",
        "kdj_d",
        "kdj_j",
    ]:
        if col not in out.columns:
            out[col] = pd.Series(dtype=float)
    if volume_field not in out.columns:
        out[volume_field] = pd.Series(dtype=float)
    return out
