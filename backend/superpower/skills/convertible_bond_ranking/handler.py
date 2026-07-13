from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.skills.convertible_bond_ranking.linkage import classify_linkage, score_dynamic_linkage
from superpower.skills.convertible_bond_ranking.strategy import cb_strategy_version, normalize_cb_config


OUTPUT_COLUMNS = [
    "rank",
    "date",
    "bond_code",
    "bond_name",
    "code",
    "name",
    "price",
    "remaining_years",
    "conversion_premium_rate",
    "premium_rate",
    "stock_daily_return",
    "bond_daily_return",
    "previous_conversion_premium_rate",
    "conversion_premium_change",
    "linkage_state",
    "linkage_note",
    "linkage_is_abnormal",
    "linkage_data_quality",
    "ytm",
    "stock_code",
    "stock_name",
    "bond_rating",
    "rating",
    "sw_l1",
    "sw_l2",
    "stock_price",
    "conversion_price",
    "redemption_trigger_ratio",
    "redemption_trigger_price",
    "redemption_triggered",
    "redemption_announcement_date",
    "no_redemption_announcement_date",
    "redemption_status",
    "issue_size",
    "remaining_size",
    "unconverted_ratio",
    "deducted_profit_growth",
    "profit_growth_acceleration",
    "profit_growth_25_vs_24",
    "latest_half_profit_growth",
    "growth_score",
    "term_score",
    "premium_score",
    "ytm_score",
    "credit_score",
    "redemption_score",
    "scale_score",
    "risk_penalty",
    "strategy_id",
    "strategy_version",
    "strategy_fallback_reason",
    "base_score",
    "dynamic_score",
    "dynamic_state",
    "dynamic_note",
    "dynamic_data_quality",
    "dynamic_components",
    "score",
    "risk_level",
    "risk_flags",
    "rank_reason",
    "score_breakdown",
    "action",
    "reason",
    "metrics",
    "rule_hits",
    "risk_notes",
    "qualification",
    "score_grade",
    "eligible_for_top",
    "not_top_reason",
    "quality_notes",
    "confidence",
    "data_quality",
    "notes",
]

EXCLUDED_COLUMNS = [
    "date",
    "bond_code",
    "bond_name",
    "code",
    "name",
    "price",
    "ytm",
    "conversion_premium_rate",
    "bond_rating",
    "rating",
    "sw_l1",
    "remaining_size",
    "redemption_status",
    "excluded_reason",
    "qualification",
    "score_grade",
    "eligible_for_top",
    "not_top_reason",
    "quality_notes",
]


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        cb_data = context.maybe("cb_data", pd.DataFrame())
        params = context.get("strategy_params")
        if cb_data.empty:
            empty = _empty_output()
            context.put("cb_ranked", empty)
            context.put("cb_top10", empty)
            context.put("cb_excluded", _empty_excluded())
            context.put("cb_qualified", empty)
            context.put("cb_weak_watch", empty)
            context.put("cb_risk_watch", empty)
            context.put("cb_quality_summary", _qualification_summary(empty, empty, empty, _empty_excluded()))
            return {"cb_rows": 0, "cb_candidates": 0, "cb_top10": 0, "status": "waiting_for_data"}

        ranked, excluded = rank_convertible_bonds(cb_data, params, include_excluded=True)
        config = params.get("convertible_bond", {})
        qualified, weak_watch, risk_watch = split_candidate_qualification(ranked)
        top10 = _select_diversified_top(
            qualified,
            top_n=int(config.get("top_n", 10)),
            max_per_l1=int(config.get("max_per_industry_l1", 2)),
            max_per_l2=int(config.get("max_per_industry_l2", 2)),
        )
        quality_summary = _qualification_summary(qualified, weak_watch, risk_watch, excluded)
        context.put("cb_ranked", ranked)
        context.put("cb_top10", top10)
        context.put("cb_excluded", excluded)
        context.put("cb_qualified", qualified)
        context.put("cb_weak_watch", weak_watch)
        context.put("cb_risk_watch", risk_watch)
        context.put("cb_quality_summary", quality_summary)
        return {
            "cb_rows": len(cb_data),
            "cb_candidates": len(ranked),
            "cb_top10": len(top10),
            "cb_excluded": len(excluded),
            "status": "success" if not ranked.empty else "no_candidate_after_risk_filters",
        }


def rank_convertible_bonds(
    cb_data: pd.DataFrame,
    params: dict[str, Any],
    include_excluded: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """Rank v2 convertible-bond rows with risk gates before scoring.

    The model is intentionally deterministic: LLMs can explain these rows, but
    cannot add/remove candidates or change scores.
    """
    config = params.get("convertible_bond", {})
    strategy_config = normalize_cb_config({"convertible_bond": config})
    price_limit = float(config.get("price_limit", 140))
    min_price = float(config.get("min_price", 100))
    high_ytm_hard_exclude = float(config.get("high_ytm_hard_exclude", 15))
    severe_negative_ytm_hard_exclude = float(config.get("severe_negative_ytm_hard_exclude", -5))
    high_premium_penalty_threshold = float(config.get("high_premium_penalty_threshold", 35))
    high_premium_hard_exclude = float(config.get("high_premium_hard_exclude", 50))
    low_remaining_size_hard_exclude = float(config.get("min_remaining_size_hard_exclude", 0.5))
    bad_ratings = {str(item).upper() for item in config.get("hard_exclude_ratings", _default_bad_ratings())}
    exclude_st_stock = bool(config.get("exclude_st_stock", True))
    exclude_unresolved_redemption = bool(config.get("exclude_unresolved_redemption_trigger", True))
    negative_ytm_penalty = float(config.get("negative_ytm_penalty", 28))
    high_premium_penalty = float(config.get("high_premium_penalty", 28))
    negative_growth_penalty = float(config.get("negative_growth_penalty", 8))
    negative_acceleration_penalty = float(config.get("negative_acceleration_penalty", 5))
    negative_profit_penalty = float(config.get("negative_profit_penalty", 14))
    unstable_growth_base_penalty = float(config.get("unstable_growth_base_penalty", 10))
    extreme_growth_penalty = float(config.get("extreme_growth_penalty", 6))
    growth_winsor_lower = float(config.get("growth_winsor_lower", -100))
    growth_winsor_upper = float(config.get("growth_winsor_upper", 150))
    extreme_growth_threshold = float(config.get("extreme_growth_threshold", growth_winsor_upper))
    small_profit_base_threshold = float(config.get("small_profit_base_threshold", 1))
    stale_no_redemption_days = int(config.get("no_redemption_valid_days", 180))
    weights = _normalise_weights(
        config.get(
            "score_weights",
            {
                "fundamental": 0.25,
                "premium": 0.2,
                "ytm": 0.15,
                "term": 0.1,
                "credit": 0.15,
                "redemption": 0.1,
                "scale": 0.05,
            },
        )
    )

    df = _ensure_columns(cb_data.copy())
    if df.empty:
        empty = _empty_output()
        return (empty, _empty_excluded()) if include_excluded else empty
    df["code"] = df["bond_code"]
    df["name"] = df["bond_name"]
    df["rating"] = df["bond_rating"]
    df["premium_rate"] = df["conversion_premium_rate"]

    report_date = _report_date(df)
    df["redemption_trigger_ratio_normalized"] = _normalise_trigger_ratio(df["redemption_trigger_ratio"])
    df["redemption_trigger_price"] = df["conversion_price"] * df["redemption_trigger_ratio_normalized"]
    computed_triggered = (
        df["stock_price"].notna()
        & df["conversion_price"].notna()
        & df["redemption_trigger_ratio_normalized"].notna()
        & (df["stock_price"] >= df["redemption_trigger_price"])
    )
    df["redemption_data_missing"] = (
        df["stock_price"].isna()
        | df["conversion_price"].isna()
        | df["redemption_trigger_ratio_normalized"].isna()
    )
    df["redemption_triggered"] = df["redemption_triggered"].fillna(False).astype(bool) | computed_triggered.fillna(False)

    df["rating_key"] = df["bond_rating"].map(_rating_key)
    df["is_st_stock"] = df["stock_name"].astype(str).str.upper().str.contains(r"\*?ST", regex=True, na=False)
    df["has_redeem_announcement"] = df["redemption_announcement_date"].notna()
    df["has_no_redeem_announcement"] = df["no_redemption_announcement_date"].notna()
    df["no_redeem_is_stale"] = _is_no_redeem_stale(df["no_redemption_announcement_date"], report_date, stale_no_redemption_days)
    df["growth_base_unstable"] = _growth_base_unstable(df, small_profit_base_threshold)
    df["latest_profit_negative"] = _latest_profit_negative(df)
    df["redemption_status"] = [
        _redemption_status(row) for _, row in df.iterrows()
    ]

    df["exclusion_reason"] = [
        _exclusion_reason(
            row,
            price_limit=price_limit,
            min_price=min_price,
            high_ytm_hard_exclude=high_ytm_hard_exclude,
            severe_negative_ytm_hard_exclude=severe_negative_ytm_hard_exclude,
            high_premium_hard_exclude=high_premium_hard_exclude,
            low_remaining_size_hard_exclude=low_remaining_size_hard_exclude,
            bad_ratings=bad_ratings,
            exclude_st_stock=exclude_st_stock,
            exclude_unresolved_redemption=exclude_unresolved_redemption,
        )
        for _, row in df.iterrows()
    ]
    excluded = _excluded_output(df)
    eligible = df[df["exclusion_reason"] == ""].copy()
    if eligible.empty:
        empty = _empty_output()
        return (empty, excluded) if include_excluded else empty

    eligible["growth_score"] = _fundamental_score(
        eligible,
        growth_winsor_lower=growth_winsor_lower,
        growth_winsor_upper=growth_winsor_upper,
    )
    eligible["term_score"] = _lower_better(eligible["remaining_years"])
    eligible["premium_score"] = _premium_quality_score(
        eligible["conversion_premium_rate"],
        high_premium_penalty_threshold=high_premium_penalty_threshold,
        high_premium_hard_exclude=high_premium_hard_exclude,
    )
    eligible["ytm_score"] = _ytm_quality_score(eligible["ytm"], high_ytm_hard_exclude)
    eligible["credit_score"] = eligible.apply(_credit_score, axis=1)
    eligible["redemption_score"] = eligible.apply(_redemption_score, axis=1)
    eligible["scale_score"] = _scale_score(eligible["remaining_size"], eligible["unconverted_ratio"])
    eligible["risk_penalty"] = eligible.apply(
        lambda row: _risk_penalty(
            row,
            negative_ytm_penalty=negative_ytm_penalty,
            high_premium_penalty=high_premium_penalty,
            high_premium_penalty_threshold=high_premium_penalty_threshold,
            high_premium_hard_exclude=high_premium_hard_exclude,
            negative_growth_penalty=negative_growth_penalty,
            negative_acceleration_penalty=negative_acceleration_penalty,
            negative_profit_penalty=negative_profit_penalty,
            unstable_growth_base_penalty=unstable_growth_base_penalty,
            extreme_growth_penalty=extreme_growth_penalty,
            extreme_growth_threshold=extreme_growth_threshold,
        ),
        axis=1,
    )
    eligible["score"] = (
        eligible["growth_score"] * weights["fundamental"]
        + eligible["term_score"] * weights["term"]
        + eligible["premium_score"] * weights["premium"]
        + eligible["ytm_score"] * weights["ytm"]
        + eligible["credit_score"] * weights["credit"]
        + eligible["redemption_score"] * weights["redemption"]
        + eligible["scale_score"] * weights["scale"]
        - eligible["risk_penalty"]
    ).round(2)
    eligible["score"] = eligible["score"].clip(lower=0, upper=100)
    eligible["base_score"] = eligible["score"]
    eligible["risk_flags"] = [
        risk_flags
        for _, risk_flags in eligible.apply(
            lambda row: _risk_flags(
                row,
                high_premium_penalty_threshold=high_premium_penalty_threshold,
                extreme_growth_threshold=extreme_growth_threshold,
            ),
            axis=1,
        ).items()
    ]
    eligible["risk_level"] = eligible["risk_flags"].map(_risk_level)
    eligible["rank_reason"] = [_rank_reason(row) for _, row in eligible.iterrows()]
    eligible["code"] = eligible["bond_code"]
    eligible["name"] = eligible["bond_name"]
    eligible["rating"] = eligible["bond_rating"]
    eligible["premium_rate"] = eligible["conversion_premium_rate"]
    eligible["score_breakdown"] = [_score_breakdown(row) for _, row in eligible.iterrows()]
    eligible["action"] = "进入可转债Top10候选池"
    eligible["reason"] = eligible["rank_reason"]
    eligible["metrics"] = [_metrics(row) for _, row in eligible.iterrows()]
    eligible["rule_hits"] = [_rule_hits(row) for _, row in eligible.iterrows()]
    eligible["risk_notes"] = eligible["risk_flags"].map(_risk_note_list)
    eligible["score_grade"] = eligible["score"].map(_score_grade)
    eligible["quality_notes"] = [_quality_notes(row) for _, row in eligible.iterrows()]
    qualification = [_qualification(row) for _, row in eligible.iterrows()]
    eligible["qualification"] = [item["qualification"] for item in qualification]
    eligible["eligible_for_top"] = [item["eligible_for_top"] for item in qualification]
    eligible["not_top_reason"] = [item["not_top_reason"] for item in qualification]
    eligible["data_quality"] = "OK"
    eligible["confidence"] = eligible["risk_level"].map({"低": "high", "中": "medium", "高": "low"}).fillna("medium")
    eligible.loc[eligible["redemption_data_missing"].fillna(False).astype(bool), "confidence"] = "low"
    eligible.loc[eligible["qualification"] == "qualified", "action"] = "进入可转债Top10候选池"
    eligible.loc[eligible["qualification"] == "weak_watch", "action"] = "弱观察候选，仅代表相对排序靠前，不构成高质量候选"
    eligible.loc[eligible["qualification"] == "risk_watch", "action"] = "风险观察，不进入Top候选"

    linkage_config = config.get("linkage_overlay", {})
    linkage_results = [
        classify_linkage(row, linkage_config)
        for _, row in eligible.iterrows()
    ] if bool(linkage_config.get("enabled", True)) else [
        {
            "linkage_state": "未启用",
            "linkage_note": "",
            "linkage_is_abnormal": False,
            "linkage_data_quality": "DISABLED",
        }
        for _ in range(len(eligible))
    ]
    for field in ("linkage_state", "linkage_note", "linkage_is_abnormal", "linkage_data_quality"):
        eligible[field] = [result[field] for result in linkage_results]

    active_strategy = str(strategy_config["active_strategy"])
    eligible["strategy_id"] = active_strategy
    eligible["strategy_version"] = cb_strategy_version(active_strategy)
    eligible["strategy_fallback_reason"] = ""
    eligible["dynamic_score"] = np.nan
    eligible["dynamic_state"] = ""
    eligible["dynamic_note"] = ""
    eligible["dynamic_data_quality"] = "DISABLED"
    eligible["dynamic_components"] = [{} for _ in range(len(eligible))]
    if active_strategy == "dynamic_v2":
        try:
            dynamic_results = [
                score_dynamic_linkage(row, config.get("dynamic_scoring", {}))
                for _, row in eligible.iterrows()
            ]
            for field in ("dynamic_score", "dynamic_state", "dynamic_note", "dynamic_data_quality", "dynamic_components"):
                eligible[field] = [result[field] for result in dynamic_results]
            profile = strategy_config["strategy_profiles"]["dynamic_v2"]
            valid_dynamic = pd.to_numeric(eligible["dynamic_score"], errors="coerce").notna()
            eligible.loc[valid_dynamic, "score"] = (
                eligible.loc[valid_dynamic, "base_score"] * float(profile["base_weight"])
                + pd.to_numeric(eligible.loc[valid_dynamic, "dynamic_score"], errors="coerce")
                * float(profile["dynamic_weight"])
            ).round(2)
            eligible.loc[~valid_dynamic, "score"] = eligible.loc[~valid_dynamic, "base_score"]
        except Exception as exc:
            eligible["strategy_id"] = "legacy_v1"
            eligible["strategy_version"] = cb_strategy_version("legacy_v1")
            eligible["strategy_fallback_reason"] = f"dynamic_v2_failed: {type(exc).__name__}"
            eligible["score"] = eligible["base_score"]
            eligible["dynamic_data_quality"] = "FALLBACK"

    output = eligible[OUTPUT_COLUMNS].copy()
    if active_strategy == "dynamic_v2" and (output["strategy_id"] == "dynamic_v2").all():
        output["_qualification_order"] = output["qualification"].map(
            {"qualified": 0, "weak_watch": 1, "risk_watch": 2}
        ).fillna(3)
        output = output.sort_values(
            ["_qualification_order", "score", "credit_score", "redemption_score", "conversion_premium_rate"],
            ascending=[True, False, False, False, True],
        ).drop(columns="_qualification_order").reset_index(drop=True)
    else:
        output = output.sort_values(
            ["score", "credit_score", "redemption_score", "conversion_premium_rate"],
            ascending=[False, False, False, True],
        ).reset_index(drop=True)
    output["rank"] = np.arange(1, len(output) + 1)
    return (output, excluded) if include_excluded else output


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in OUTPUT_COLUMNS + [
        "enabled",
        "profit_growth_23_vs_22",
        "profit_growth_24_vs_23",
        "deducted_profit_2022",
        "deducted_profit_2023",
        "deducted_profit_2024",
        "deducted_profit_2025",
        "deducted_profit_h1_2025",
        "deducted_profit_h1_2026",
        "rating_key",
        "has_redeem_announcement",
        "has_no_redeem_announcement",
        "no_redeem_is_stale",
        "is_st_stock",
        "growth_base_unstable",
        "latest_profit_negative",
        "exclusion_reason",
        "redemption_data_missing",
    ]:
        if col not in df.columns:
            df[col] = pd.NA
    for col in [
        "price",
        "remaining_years",
        "conversion_premium_rate",
        "stock_daily_return",
        "bond_daily_return",
        "previous_conversion_premium_rate",
        "conversion_premium_change",
        "ytm",
        "stock_price",
        "conversion_price",
        "redemption_trigger_ratio",
        "issue_size",
        "remaining_size",
        "unconverted_ratio",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "profit_growth_23_vs_22",
        "profit_growth_24_vs_23",
        "profit_growth_25_vs_24",
        "latest_half_profit_growth",
        "deducted_profit_2022",
        "deducted_profit_2023",
        "deducted_profit_2024",
        "deducted_profit_2025",
        "deducted_profit_h1_2025",
        "deducted_profit_h1_2026",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    _normalise_percent_point_columns(df)
    for col in ["date", "redemption_announcement_date", "no_redemption_announcement_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["redemption_triggered"] = _bool_series(df["redemption_triggered"])
    df["bond_code"] = df["bond_code"].astype(str).str.strip()
    df["bond_name"] = df["bond_name"].astype(str).str.strip()
    df = df[(df["bond_code"] != "") & (df["bond_code"].str.lower() != "nan")]
    return df.reset_index(drop=True)


def _normalise_percent_point_columns(df: pd.DataFrame) -> None:
    percent_columns = [
        "conversion_premium_rate",
        "ytm",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "profit_growth_23_vs_22",
        "profit_growth_24_vs_23",
        "profit_growth_25_vs_24",
        "latest_half_profit_growth",
    ]
    for col in percent_columns:
        values = pd.to_numeric(df[col], errors="coerce")
        sample = values.dropna().abs()
        if sample.empty:
            continue
        if sample.quantile(0.75) <= 1.5 and sample.max() <= 5:
            df[col] = values * 100


def _normalise_weights(raw: dict[str, Any]) -> dict[str, float]:
    legacy_map = {
        "deducted_profit_growth": "fundamental",
        "remaining_years": "term",
        "conversion_premium_rate": "premium",
    }
    weights = {
        "fundamental": 0.25,
        "premium": 0.2,
        "ytm": 0.15,
        "term": 0.1,
        "credit": 0.15,
        "redemption": 0.1,
        "scale": 0.05,
    }
    for key, value in raw.items():
        mapped = legacy_map.get(key, key)
        if mapped in weights:
            weights[mapped] = float(value)
    total = sum(max(value, 0) for value in weights.values())
    if total <= 0:
        return weights
    return {key: max(value, 0) / total for key, value in weights.items()}


def _normalise_trigger_ratio(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values <= 10, values / 100)


def _report_date(df: pd.DataFrame) -> pd.Timestamp:
    latest = pd.to_datetime(df["date"], errors="coerce").max()
    if pd.isna(latest):
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(latest).normalize()


def _is_no_redeem_stale(series: pd.Series, report_date: pd.Timestamp, valid_days: int) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce")
    if valid_days <= 0:
        return pd.Series(False, index=series.index)
    return dates.notna() & ((report_date - dates).dt.days > valid_days)


def _redemption_status(row: pd.Series) -> str:
    if bool(row.get("has_redeem_announcement")):
        return "已发强赎公告，剔除"
    if bool(row.get("redemption_data_missing")):
        return "强赎字段不足，需人工复核"
    if not bool(row.get("redemption_triggered")):
        return "未触发强赎价"
    if bool(row.get("has_no_redeem_announcement")) and not bool(row.get("no_redeem_is_stale")):
        return "触发强赎价但有不强赎公告，观察"
    if bool(row.get("has_no_redeem_announcement")) and bool(row.get("no_redeem_is_stale")):
        return "触发强赎价，不强赎公告可能过期"
    return "触发强赎价，未见有效公告"


def _exclusion_reason(
    row: pd.Series,
    *,
    price_limit: float,
    min_price: float,
    high_ytm_hard_exclude: float,
    severe_negative_ytm_hard_exclude: float,
    high_premium_hard_exclude: float,
    low_remaining_size_hard_exclude: float,
    bad_ratings: set[str],
    exclude_st_stock: bool,
    exclude_unresolved_redemption: bool,
) -> str:
    reasons: list[str] = []
    price = _num(row.get("price"))
    ytm = _num(row.get("ytm"))
    premium = _num(row.get("conversion_premium_rate"))
    remaining_size = _num(row.get("remaining_size"))
    if pd.isna(price):
        reasons.append("价格缺失")
    elif price < min_price:
        reasons.append(f"价格低于{min_price:.0f}元")
    elif price >= price_limit:
        reasons.append(f"价格不低于{price_limit:.0f}元")
    if bool(row.get("has_redeem_announcement")):
        reasons.append("已发布强赎公告")
    if row.get("rating_key") in bad_ratings:
        reasons.append(f"债项评级{row.get('bond_rating')}低于风控线")
    if exclude_st_stock and bool(row.get("is_st_stock")):
        reasons.append("正股ST")
    if pd.notna(ytm) and ytm >= high_ytm_hard_exclude:
        reasons.append(f"到期收益率{ytm:.2f}%异常偏高")
    if pd.notna(ytm) and ytm <= severe_negative_ytm_hard_exclude:
        reasons.append(f"到期收益率{ytm:.2f}%严重为负")
    if pd.notna(premium) and premium >= high_premium_hard_exclude:
        reasons.append(f"转股溢价率{premium:.2f}%过高")
    if pd.notna(remaining_size) and remaining_size < low_remaining_size_hard_exclude:
        reasons.append(f"存续规模低于{low_remaining_size_hard_exclude:g}")
    if exclude_unresolved_redemption and row.get("redemption_status") in {
        "触发强赎价，未见有效公告",
        "触发强赎价，不强赎公告可能过期",
    }:
        reasons.append(row.get("redemption_status"))
    return "；".join(reasons)


def _fundamental_score(
    df: pd.DataFrame,
    *,
    growth_winsor_lower: float,
    growth_winsor_upper: float,
) -> pd.Series:
    growth = _higher_better(_winsorized_growth(df["deducted_profit_growth"], growth_winsor_lower, growth_winsor_upper))
    acceleration = _higher_better(_winsorized_growth(df["profit_growth_acceleration"], growth_winsor_lower, growth_winsor_upper))
    latest = _higher_better(_winsorized_growth(df["profit_growth_25_vs_24"], growth_winsor_lower, growth_winsor_upper))
    score = growth * 0.35 + acceleration * 0.25 + latest * 0.4
    score = score.where(~df["growth_base_unstable"].fillna(False).astype(bool), score * 0.72)
    score = score.where(~df["latest_profit_negative"].fillna(False).astype(bool), score * 0.55)
    return score.fillna(50).clip(0, 100)


def _premium_quality_score(
    series: pd.Series,
    *,
    high_premium_penalty_threshold: float,
    high_premium_hard_exclude: float,
) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    scores = pd.Series(50.0, index=values.index)
    scores.loc[values <= 0] = 95
    mask = (values > 0) & (values <= 15)
    scores.loc[mask] = 100 - values.loc[mask] / 15 * 8
    mask = (values > 15) & (values <= 30)
    scores.loc[mask] = 88 - (values.loc[mask] - 15) / 15 * 18
    mask = (values > 30) & (values <= high_premium_penalty_threshold)
    scores.loc[mask] = 68 - (values.loc[mask] - 30) / max(high_premium_penalty_threshold - 30, 1) * 18
    mask = (values > high_premium_penalty_threshold) & (values < high_premium_hard_exclude)
    scores.loc[mask] = 42 - (values.loc[mask] - high_premium_penalty_threshold) / max(high_premium_hard_exclude - high_premium_penalty_threshold, 1) * 32
    scores.loc[values >= high_premium_hard_exclude] = 0
    return scores.fillna(50).clip(0, 100)


def _winsorized_growth(series: pd.Series, lower: float, upper: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.clip(lower=lower, upper=upper)


def _growth_base_unstable(df: pd.DataFrame, threshold: float) -> pd.Series:
    threshold = max(float(threshold), 0)
    base_columns = [
        "deducted_profit_2022",
        "deducted_profit_2023",
        "deducted_profit_2024",
        "deducted_profit_h1_2025",
    ]
    masks = []
    for col in base_columns:
        values = pd.to_numeric(df.get(col, pd.Series(pd.NA, index=df.index)), errors="coerce")
        masks.append(values.notna() & ((values <= 0) | (values.abs() < threshold)))
    if not masks:
        return pd.Series(False, index=df.index)
    unstable = masks[0]
    for mask in masks[1:]:
        unstable = unstable | mask
    return unstable.fillna(False)


def _latest_profit_negative(df: pd.DataFrame) -> pd.Series:
    latest = pd.to_numeric(df.get("deducted_profit_2025", pd.Series(pd.NA, index=df.index)), errors="coerce")
    half = pd.to_numeric(df.get("deducted_profit_h1_2026", pd.Series(pd.NA, index=df.index)), errors="coerce")
    return ((latest.notna() & (latest < 0)) | (half.notna() & (half < 0))).fillna(False)


def _credit_score(row: pd.Series) -> float:
    rating_score = _rating_score(row.get("rating_key"))
    price = _num(row.get("price"))
    ytm = _num(row.get("ytm"))
    adjustments = 0.0
    if pd.notna(price):
        if price < 105:
            adjustments -= 12
        elif price < 110:
            adjustments -= 6
    if pd.notna(ytm):
        if ytm > 8:
            adjustments -= 18
        elif ytm > 3:
            adjustments -= 8
    return float(np.clip(rating_score + adjustments, 0, 100))


def _redemption_score(row: pd.Series) -> float:
    status = str(row.get("redemption_status", ""))
    if status == "未触发强赎价":
        return 100.0
    if status == "触发强赎价但有不强赎公告，观察":
        return 68.0
    if status == "触发强赎价，不强赎公告可能过期":
        return 42.0
    if status == "触发强赎价，未见有效公告":
        return 25.0
    if status == "强赎字段不足，需人工复核":
        return 35.0
    return 0.0


def _scale_score(remaining_size: pd.Series, unconverted_ratio: pd.Series) -> pd.Series:
    size_score = _higher_better(remaining_size)
    ratio = pd.to_numeric(unconverted_ratio, errors="coerce")
    ratio_score = _percentile_score(ratio, ascending=True)
    return (size_score * 0.7 + ratio_score * 0.3).fillna(50).clip(0, 100)


def _ytm_quality_score(series: pd.Series, high_ytm_hard_exclude: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    scores = pd.Series(50.0, index=values.index)
    scores.loc[values < -8] = 10
    mask = (values >= -8) & (values < 0)
    scores.loc[mask] = 35 + (values.loc[mask] + 8) / 8 * 40
    mask = (values >= 0) & (values <= 3)
    scores.loc[mask] = 82 + values.loc[mask] / 3 * 18
    mask = (values > 3) & (values <= 8)
    scores.loc[mask] = 82 - (values.loc[mask] - 3) / 5 * 25
    mask = (values > 8) & (values < high_ytm_hard_exclude)
    scores.loc[mask] = 45 - (values.loc[mask] - 8) / max(high_ytm_hard_exclude - 8, 1) * 25
    return scores.fillna(50).clip(0, 100)


def _risk_penalty(
    row: pd.Series,
    *,
    negative_ytm_penalty: float,
    high_premium_penalty: float,
    high_premium_penalty_threshold: float,
    high_premium_hard_exclude: float,
    negative_growth_penalty: float,
    negative_acceleration_penalty: float,
    negative_profit_penalty: float,
    unstable_growth_base_penalty: float,
    extreme_growth_penalty: float,
    extreme_growth_threshold: float,
) -> float:
    penalty = 0.0
    ytm = _num(row.get("ytm"))
    premium = _num(row.get("conversion_premium_rate"))
    growth_25 = _num(row.get("profit_growth_25_vs_24"))
    acceleration = _num(row.get("profit_growth_acceleration"))
    growth = _num(row.get("deducted_profit_growth"))
    remaining_size = _num(row.get("remaining_size"))
    if pd.notna(ytm) and ytm < 0:
        severity = max(min(abs(ytm) / 5, 1), 0.25)
        penalty += negative_ytm_penalty * severity
    if pd.notna(premium) and premium > high_premium_penalty_threshold:
        span = max(high_premium_hard_exclude - high_premium_penalty_threshold, 1)
        premium_severity = min((premium - high_premium_penalty_threshold) / span, 1)
        penalty += min(high_premium_penalty, high_premium_penalty * (0.5 + premium_severity))
    if pd.notna(growth_25) and growth_25 < 0:
        penalty += negative_growth_penalty
    if pd.notna(acceleration) and acceleration < 0:
        penalty += negative_acceleration_penalty
    if bool(row.get("latest_profit_negative")):
        penalty += negative_profit_penalty
    elif bool(row.get("growth_base_unstable")):
        penalty += unstable_growth_base_penalty
    if any(pd.notna(value) and abs(value) > extreme_growth_threshold for value in [growth, acceleration, growth_25]):
        penalty += extreme_growth_penalty
    if row.get("redemption_status") == "触发强赎价，未见有效公告":
        penalty += 12
    elif row.get("redemption_status") == "触发强赎价，不强赎公告可能过期":
        penalty += 8
    elif row.get("redemption_status") == "触发强赎价但有不强赎公告，观察":
        penalty += 4
    if pd.notna(remaining_size) and remaining_size < 2:
        penalty += 5
    return float(penalty)


def _risk_flags(
    row: pd.Series,
    *,
    high_premium_penalty_threshold: float,
    extreme_growth_threshold: float,
) -> str:
    flags: list[str] = []
    if str(row.get("redemption_status", "")).startswith("触发强赎价"):
        flags.append(row.get("redemption_status"))
    if _num(row.get("conversion_premium_rate")) > high_premium_penalty_threshold:
        flags.append("转股溢价率偏高，已扣分")
    if _num(row.get("profit_growth_25_vs_24")) < 0:
        flags.append("2025扣非增速为负")
    if _num(row.get("profit_growth_acceleration")) < 0:
        flags.append("2025增速低于三年均值")
    if bool(row.get("latest_profit_negative")):
        flags.append("最新扣非净利润为负，基本面降权")
    elif bool(row.get("growth_base_unstable")):
        flags.append("利润基数异常，增长率降权")
    if any(
        pd.notna(value) and abs(value) > extreme_growth_threshold
        for value in [
            _num(row.get("deducted_profit_growth")),
            _num(row.get("profit_growth_acceleration")),
            _num(row.get("profit_growth_25_vs_24")),
        ]
    ):
        flags.append("增长率极端，评分已截尾")
    if _num(row.get("ytm")) < 0:
        flags.append("到期收益率为负，意味着按当前价格持有到期并不具备正收益保护，需要依赖正股上涨或转股价值改善，已扣分（按幅度）")
    if _num(row.get("remaining_size")) < 2:
        flags.append("存续规模偏小")
    if bool(row.get("redemption_data_missing")):
        flags.append("强赎字段不足，置信度降为low")
    rating_key = row.get("rating_key")
    if rating_key in {"A+", "A", "A-"}:
        flags.append(f"评级{row.get('bond_rating')}偏低")
    return "；".join([flag for flag in flags if flag])


def _risk_level(flags: str) -> str:
    if not flags:
        return "低"
    high_tokens = [
        "未见有效公告",
        "可能过期",
        "评级A偏低",
        "评级A-偏低",
        "存续规模偏小",
        "转股溢价率偏高",
        "最新扣非净利润为负",
    ]
    if any(token in flags for token in high_tokens):
        return "高"
    return "中"


def _risk_note_list(flags: object) -> list[str]:
    text = "" if flags is None or pd.isna(flags) else str(flags)
    notes = [part for part in text.split("；") if part]
    return notes or ["无明显风控扣分项"]


def _score_breakdown(row: pd.Series) -> dict[str, float | None]:
    return {
        "fundamental": _safe_float(row.get("growth_score")),
        "premium": _safe_float(row.get("premium_score")),
        "ytm": _safe_float(row.get("ytm_score")),
        "term": _safe_float(row.get("term_score")),
        "credit": _safe_float(row.get("credit_score")),
        "redemption": _safe_float(row.get("redemption_score")),
        "scale": _safe_float(row.get("scale_score")),
        "risk_penalty": _safe_float(row.get("risk_penalty")),
        "total": _safe_float(row.get("score")),
    }


def _metrics(row: pd.Series) -> dict[str, float | str | None]:
    return {
        "price": _safe_float(row.get("price")),
        "remaining_years": _safe_float(row.get("remaining_years")),
        "conversion_premium_rate": _safe_float(row.get("conversion_premium_rate")),
        "ytm": _safe_float(row.get("ytm")),
        "bond_rating": None if pd.isna(row.get("bond_rating")) else str(row.get("bond_rating")),
        "remaining_size": _safe_float(row.get("remaining_size")),
        "deducted_profit_growth": _safe_float(row.get("deducted_profit_growth")),
        "profit_growth_acceleration": _safe_float(row.get("profit_growth_acceleration")),
        "profit_growth_25_vs_24": _safe_float(row.get("profit_growth_25_vs_24")),
        "redemption_status": str(row.get("redemption_status", "")),
    }


def _rule_hits(row: pd.Series) -> str:
    hits = [
        "通过价格区间过滤",
        f"强赎状态：{row.get('redemption_status', '未知')}",
        f"债项评级：{row.get('bond_rating', '--')}",
        f"行业：{row.get('sw_l1', '--')}",
        "已计算基本面、溢价率、YTM、期限、信用、强赎、规模分项得分",
    ]
    return "；".join(hits)


def _excluded_output(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "exclusion_reason" not in df.columns:
        return _empty_excluded()
    excluded = df[df["exclusion_reason"].astype(str).str.strip() != ""].copy()
    if excluded.empty:
        return _empty_excluded()
    excluded["excluded_reason"] = excluded["exclusion_reason"]
    excluded["qualification"] = "excluded"
    excluded["score_grade"] = "E"
    excluded["eligible_for_top"] = False
    excluded["not_top_reason"] = excluded["excluded_reason"]
    excluded["quality_notes"] = excluded["excluded_reason"].map(lambda value: [part for part in str(value).split("；") if part])
    return excluded[EXCLUDED_COLUMNS].sort_values(["excluded_reason", "bond_code"]).reset_index(drop=True)


def split_candidate_qualification(ranked: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if ranked.empty:
        empty = _empty_output()
        return empty, empty, empty
    ranked = _ensure_qualification_columns(ranked)
    qualified = ranked[ranked["qualification"] == "qualified"].copy().reset_index(drop=True)
    weak_watch = ranked[ranked["qualification"] == "weak_watch"].copy().reset_index(drop=True)
    risk_watch = ranked[ranked["qualification"] == "risk_watch"].copy().reset_index(drop=True)
    for frame in (qualified, weak_watch, risk_watch):
        if not frame.empty:
            frame["rank"] = np.arange(1, len(frame) + 1)
    return qualified[OUTPUT_COLUMNS] if not qualified.empty else _empty_output(), weak_watch[OUTPUT_COLUMNS] if not weak_watch.empty else _empty_output(), risk_watch[OUTPUT_COLUMNS] if not risk_watch.empty else _empty_output()


def _ensure_qualification_columns(ranked: pd.DataFrame) -> pd.DataFrame:
    ranked = ranked.copy()
    if "score_grade" not in ranked.columns:
        ranked["score_grade"] = ranked.get("score", pd.Series(dtype=float)).map(_score_grade)
    if "quality_notes" not in ranked.columns:
        ranked["quality_notes"] = [_quality_notes(row) for _, row in ranked.iterrows()]
    needs_qualification = (
        not {"qualification", "eligible_for_top", "not_top_reason"}.issubset(set(ranked.columns))
        or ranked["qualification"].isna().any()
        or ranked["eligible_for_top"].isna().any()
    )
    if needs_qualification:
        qualification = [_qualification(row) for _, row in ranked.iterrows()]
        ranked["qualification"] = [item["qualification"] for item in qualification]
        ranked["eligible_for_top"] = [item["eligible_for_top"] for item in qualification]
        ranked["not_top_reason"] = [item["not_top_reason"] for item in qualification]
    for column in OUTPUT_COLUMNS:
        if column not in ranked.columns:
            ranked[column] = None
    return ranked


def _qualification_summary(
    qualified: pd.DataFrame,
    weak_watch: pd.DataFrame,
    risk_watch: pd.DataFrame,
    excluded: pd.DataFrame,
) -> dict[str, Any]:
    qualified_count = len(qualified)
    if qualified_count >= 10:
        title = "可转债 Top10 候选"
        message = f"今日合格可转债候选 {qualified_count} 只，首页展示前10只。"
    elif qualified_count > 0:
        title = "可转债合格候选（不足 10 只）"
        message = f"今日合格可转债候选 {qualified_count} 只，不从弱观察或风险观察候选中补足Top10。"
    else:
        title = "今日无合格可转债 Top 候选"
        max_score = _max_score(weak_watch, risk_watch)
        if max_score is None:
            message = "今日无合格可转债 Top 候选，候选池整体质量偏弱。"
        else:
            message = f"今日无合格可转债 Top 候选；最高分仅 {max_score:.2f}，未达到合格候选阈值；候选池整体质量偏弱。"
    return {
        "qualified_count": qualified_count,
        "weak_watch_count": len(weak_watch),
        "risk_watch_count": len(risk_watch),
        "excluded_count": len(excluded),
        "top_display_title": title,
        "quality_message": message,
    }


def _max_score(*frames: pd.DataFrame) -> float | None:
    values: list[float] = []
    for frame in frames:
        if not frame.empty and "score" in frame.columns:
            values.extend(pd.to_numeric(frame["score"], errors="coerce").dropna().astype(float).tolist())
    return max(values) if values else None


def _qualification(row: pd.Series) -> dict[str, Any]:
    score = _num(row.get("score"))
    premium = _num(row.get("conversion_premium_rate"))
    ytm = _num(row.get("ytm"))
    remaining_size = _num(row.get("remaining_size"))
    risk_notes = _risk_note_list(row.get("risk_flags"))
    risk_note_count = 0 if risk_notes == ["无明显风控扣分项"] else len(risk_notes)
    top_reasons = _top_ineligible_reasons(row)
    risk_watch_reasons = _risk_watch_reasons(row, risk_note_count)
    if risk_watch_reasons:
        return {
            "qualification": "risk_watch",
            "eligible_for_top": False,
            "not_top_reason": "；".join(risk_watch_reasons),
        }
    if pd.notna(score) and score >= 50 and not top_reasons:
        return {"qualification": "qualified", "eligible_for_top": True, "not_top_reason": ""}
    weak_reasons: list[str] = []
    if pd.notna(score) and score < 50:
        weak_reasons.append("评分低于50，仅可弱观察")
    weak_reasons.extend(top_reasons)
    return {
        "qualification": "weak_watch",
        "eligible_for_top": False,
        "not_top_reason": "；".join(weak_reasons or ["弱观察候选，仅代表相对排序靠前，不构成高质量候选"]),
    }


def _top_ineligible_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    score = _num(row.get("score"))
    premium = _num(row.get("conversion_premium_rate"))
    ytm = _num(row.get("ytm"))
    remaining_size = _num(row.get("remaining_size"))
    flags = str(row.get("risk_flags") or "")
    if pd.isna(score) or score < 50:
        reasons.append("评分低于50")
    if str(row.get("risk_level")) == "高":
        reasons.append("风险等级为高")
    if pd.notna(premium) and premium > 35:
        reasons.append("转股溢价率高于35%")
    if pd.notna(ytm) and ytm < -3:
        reasons.append("到期收益率低于-3%")
    if pd.notna(remaining_size) and remaining_size < 5:
        reasons.append("存续规模低于5")
    if "最新扣非净利润为负" in flags:
        reasons.append("最新扣非净利润为负")
    if "增长率极端，评分已截尾" in flags:
        reasons.append("增长率极端，评分已截尾")
    return reasons


def _risk_watch_reasons(row: pd.Series, risk_note_count: int) -> list[str]:
    reasons: list[str] = []
    score = _num(row.get("score"))
    premium = _num(row.get("conversion_premium_rate"))
    ytm = _num(row.get("ytm"))
    remaining_size = _num(row.get("remaining_size"))
    if pd.notna(score) and score < 30:
        reasons.append("评分低于30")
    if pd.notna(score) and score == 0:
        reasons.append("评分为0")
    if str(row.get("risk_level")) == "高":
        reasons.append("风险等级为高")
    if risk_note_count >= 3:
        reasons.append("风险提示不少于3项")
    if pd.notna(premium) and premium >= 40:
        reasons.append("转股溢价率不低于40%")
    if pd.notna(ytm) and ytm < -3:
        reasons.append("到期收益率低于-3%")
    if pd.notna(remaining_size) and remaining_size < 3:
        reasons.append("存续规模低于3")
    return reasons


def _score_grade(score: Any) -> str:
    value = _num(score)
    if pd.isna(value):
        return "E"
    if value >= 70:
        return "A"
    if value >= 55:
        return "B"
    if value >= 40:
        return "C"
    if value >= 25:
        return "D"
    return "E"


def _quality_notes(row: pd.Series) -> list[str]:
    notes = _risk_note_list(row.get("risk_flags"))
    if notes == ["无明显风控扣分项"]:
        notes = []
    if bool(row.get("latest_profit_negative")) and not any("最新扣非净利润为负" in note for note in notes):
        notes.append("最新扣非净利润为负")
    if bool(row.get("growth_base_unstable")) and not any("利润基数异常" in note for note in notes):
        notes.append("利润基数异常")
    if not notes:
        notes.append("无明显风控扣分项")
    return notes


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _select_diversified_top(ranked: pd.DataFrame, top_n: int, max_per_l1: int, max_per_l2: int) -> pd.DataFrame:
    if ranked.empty:
        return _empty_output()
    selected: list[int] = []
    l1_counts: dict[str, int] = {}
    l2_counts: dict[str, int] = {}
    for index, row in ranked.iterrows():
        l1 = _text_or_default(row.get("sw_l1"), "未分类")
        l2 = _text_or_default(row.get("sw_l2"), "未分类")
        if l1_counts.get(l1, 0) >= max_per_l1 or l2_counts.get(l2, 0) >= max_per_l2:
            continue
        selected.append(index)
        l1_counts[l1] = l1_counts.get(l1, 0) + 1
        l2_counts[l2] = l2_counts.get(l2, 0) + 1
        if len(selected) >= top_n:
            break

    if len(selected) < top_n:
        for index in ranked.index:
            if index not in selected:
                selected.append(index)
            if len(selected) >= top_n:
                break

    top = ranked.loc[selected].copy().reset_index(drop=True)
    top["rank"] = np.arange(1, len(top) + 1)
    return top[OUTPUT_COLUMNS]


def _text_or_default(value: Any, default: str) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    return str(value)


def _higher_better(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return _percentile_score(values, ascending=True)


def _lower_better(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return _percentile_score(values, ascending=False)


def _percentile_score(values: pd.Series, ascending: bool) -> pd.Series:
    if values.notna().sum() == 0:
        return pd.Series(50.0, index=values.index)
    ranks = values.rank(method="average", pct=True, ascending=ascending)
    return (ranks.fillna(0.5) * 100).clip(0, 100)


def _rating_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).upper().replace("STI", "").strip()
    return text


def _bool_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip().str.upper()
    return text.isin({"Y", "YES", "TRUE", "1", "是", "满足"})


def _rating_score(rating_key: Any) -> float:
    mapping = {
        "AAA": 100,
        "AA+": 92,
        "AA": 82,
        "AA-": 72,
        "A+": 56,
        "A": 44,
        "A-": 32,
        "BBB+": 18,
        "BBB": 12,
        "BB+": 5,
        "CCC": 0,
        "CC": 0,
    }
    return float(mapping.get(str(rating_key or "").upper(), 50))


def _default_bad_ratings() -> list[str]:
    return ["A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C", "D"]


def _rank_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    reasons.append(str(row.get("redemption_status") or "强赎状态未知"))
    if pd.notna(row.get("bond_rating")):
        reasons.append(f"债项评级{row['bond_rating']}")
    if pd.notna(row.get("sw_l1")):
        reasons.append(f"行业{row['sw_l1']}")
    if pd.notna(row.get("price")):
        reasons.append(f"转债价格{float(row['price']):.2f}")
    if pd.notna(row.get("remaining_size")):
        reasons.append(f"存续规模{float(row['remaining_size']):.2f}")
    if pd.notna(row.get("deducted_profit_growth")):
        reasons.append(f"三年平均扣非增速{_pct(row['deducted_profit_growth'])}")
    if pd.notna(row.get("profit_growth_acceleration")):
        reasons.append(f"25年增速较三年均值{_pct(row['profit_growth_acceleration'])}")
    if pd.notna(row.get("profit_growth_25_vs_24")):
        reasons.append(f"25年扣非增速{_pct(row['profit_growth_25_vs_24'])}")
    if pd.notna(row.get("conversion_premium_rate")):
        reasons.append(f"转股溢价率{_pct(row['conversion_premium_rate'])}")
    if pd.notna(row.get("ytm")):
        reasons.append(f"到期收益率{_pct(row['ytm'])}")
    if str(row.get("risk_flags") or ""):
        reasons.append(f"风险提示：{row['risk_flags']}")
    return "；".join(reasons) or "字段不足，按中性分处理"


def _pct(value: float) -> str:
    if pd.isna(value):
        return "缺失"
    return f"{float(value):.2f}%"


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _empty_output() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _empty_excluded() -> pd.DataFrame:
    return pd.DataFrame(columns=EXCLUDED_COLUMNS)
