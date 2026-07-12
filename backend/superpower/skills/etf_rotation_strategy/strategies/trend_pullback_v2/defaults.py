from __future__ import annotations


STRATEGY_ID = "trend_pullback_v2"
STRATEGY_VERSION = "2.0.0"

DEFAULT_PROFILE = {
    "medium_trend": {
        "minimum_history_rows": 180,
        "ma20_slope_lookback": 5,
        "ma20_flat_tolerance": 0.003,
    },
    "short_entry": {
        "confirmation_window": 3,
        "overheat_daily_return_min": 0.04,
        "overheat_body_ratio_min": 0.60,
        "overheat_volume_ratio_min": 1.80,
        "overheat_ma5_distance_min": 0.03,
        "overheat_cooldown_days": 3,
        "pullback_support_tolerance": 0.005,
        "pullback_max_intraday_break": 0.010,
        "pullback_max_age": 10,
    },
    "exit": {"policy": "legacy_v1"},
    "ranking": {"policy": "legacy_v1"},
}

PARAMETER_SCHEMA = {
    "medium_trend": {
        "minimum_history_rows": {
            "type": "integer",
            "label": "最少历史交易日",
            "min": 180,
            "max": 1000,
            "step": 1,
        },
        "ma20_slope_lookback": {
            "type": "integer",
            "label": "MA20斜率回看日",
            "min": 2,
            "max": 20,
            "step": 1,
        },
        "ma20_flat_tolerance": {
            "type": "number",
            "label": "MA20走平容差",
            "min": 0.0,
            "max": 0.05,
            "step": 0.0005,
        },
    },
    "short_entry": {
        "confirmation_window": {
            "type": "integer",
            "label": "突破确认窗口",
            "min": 1,
            "max": 5,
            "step": 1,
        },
        "overheat_daily_return_min": {
            "type": "number",
            "label": "过热日涨幅",
            "min": 0.01,
            "max": 0.20,
            "step": 0.005,
        },
        "overheat_body_ratio_min": {
            "type": "number",
            "label": "过热阳线实体比例",
            "min": 0.10,
            "max": 1.0,
            "step": 0.05,
        },
        "overheat_volume_ratio_min": {
            "type": "number",
            "label": "过热量能倍数",
            "min": 1.0,
            "max": 5.0,
            "step": 0.1,
        },
        "overheat_ma5_distance_min": {
            "type": "number",
            "label": "偏离MA5比例",
            "min": 0.005,
            "max": 0.20,
            "step": 0.005,
        },
        "overheat_cooldown_days": {
            "type": "integer",
            "label": "过热冷却日",
            "min": 1,
            "max": 10,
            "step": 1,
        },
        "pullback_support_tolerance": {
            "type": "number",
            "label": "回踩触及容差",
            "min": 0.0,
            "max": 0.03,
            "step": 0.001,
        },
        "pullback_max_intraday_break": {
            "type": "number",
            "label": "盘中最大跌破",
            "min": 0.001,
            "max": 0.05,
            "step": 0.001,
        },
        "pullback_max_age": {
            "type": "integer",
            "label": "回踩最长等待日",
            "min": 3,
            "max": 30,
            "step": 1,
        },
    },
}
