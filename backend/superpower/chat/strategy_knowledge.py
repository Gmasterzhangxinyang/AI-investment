from __future__ import annotations

from typing import Any, Mapping


def build_rule_contract(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build one user-facing rule contract from the active strategy configuration."""
    config = dict(params or {})
    etf = config.get("etf") if isinstance(config.get("etf"), dict) else {}
    tl = config.get("tl") if isinstance(config.get("tl"), dict) else {}
    cb = config.get("convertible_bond") if isinstance(config.get("convertible_bond"), dict) else {}

    active_etf = str(etf.get("active_strategy") or "legacy_v1")
    profiles = etf.get("strategy_profiles") if isinstance(etf.get("strategy_profiles"), dict) else {}
    active_profile = profiles.get(active_etf) if isinstance(profiles.get(active_etf), dict) else {}

    if active_etf == "trend_pullback_v2":
        medium = active_profile.get("medium_trend") if isinstance(active_profile.get("medium_trend"), dict) else {}
        short = active_profile.get("short_entry") if isinstance(active_profile.get("short_entry"), dict) else {}
        etf_rules = [
            "密切观察：MA5已在MA10上方，且日MACD绿柱缩短或转红；此时只进入观察，不等于建仓。",
            (
                "中期确认：检查MA20是否走平或向上、价格和MA5是否站上MA20，并核对周MACD是否绿柱缩短或红柱加长；"
                "MA20继续向下或周MACD绿柱扩大时不能当成稳定反转。"
            ),
            (
                "短期过热过滤：长期下跌后的巨量长阳不直接追入；单日涨幅、阳线实体、量能和价格偏离MA5达到配置阈值时，"
                f"进入冷却观察。当前价格偏离MA5阈值为{_pct(short.get('overheat_ma5_distance_min'))}。"
            ),
            (
                "真正入场只看两类：趋势确认后的后续突破，或回踩MA5/MA10/突破位后承接稳定；"
                f"回踩支撑容差为{_pct(short.get('pullback_support_tolerance'))}，确认窗口为{short.get('confirmation_window', '--')}个交易日。"
            ),
            "平仓仍只对持仓生效；观察、允许入场和实际交易是三个不同层级，任何状态都不保证收益。",
        ]
    else:
        buy_volume = active_profile.get("buy_volume_ratio_min", etf.get("buy_volume_ratio_min", "--"))
        etf_rules = [
            f"建仓A：未持仓 + MA5今日上穿MA10 + MACD柱较昨日改善 + 前60日量能倍数达到{buy_volume}。",
            f"建仓B：未持仓 + DIF今日上穿DEA + MA5高于MA10 + 收盘价高于MA20 + 前60日量能倍数达到{buy_volume}。",
            "MA5高于MA20只是增强项，不能替代上穿条件；关注池不是建仓候选。",
            "平仓只对持仓生效：收盘跌破MA10且放量，或收盘跌破MA5且明显放量。",
            "MA20方向、周MACD和短期过热作为风险辅助提示，不改变原策略评分和排名。",
        ]

    fund_flow = tl.get("fund_flow") if isinstance(tl.get("fund_flow"), dict) else {}
    tl_rules = [
        "TL仅输出不做交易、关注交易、模型触发建仓候选；不做平仓提示。",
        "不做交易：周线红柱缩短、绿柱变长，或红转绿阶段。",
        "关注交易：周线红柱变长、绿柱缩短，或绿转红阶段；日线MACD改善只能作为辅助关注。",
        (
            "模型触发建仓候选：周线关注且近"
            f"{tl.get('weekly_kdj_lookback', '--')}周J<{tl.get('weekly_j_low_threshold', '--')}后回升，或日线关注且近"
            f"{tl.get('daily_kdj_lookback', '--')}日J<{tl.get('daily_j_low_threshold', '--')}后回升；周线硬否决开启时不能升级。"
        ),
        (
            "30年国债ETF份额变化只作辅助，不改变原TL状态；"
            f"单日约±{fund_flow.get('large_threshold', '--')}亿份视为较大变化，约±{fund_flow.get('extreme_threshold', '--')}亿份视为极端变化，"
            "用于提示资金方向是否与技术信号背离或可能出现拐点。"
        ),
    ]

    hard_ratings = cb.get("hard_exclude_ratings") if isinstance(cb.get("hard_exclude_ratings"), list) else []
    active_cb = str(cb.get("active_strategy") or "legacy_v1")
    cb_rules = [
        (
            f"先做风控排除，再做综合打分；价格低于{cb.get('min_price', '--')}元或不低于{cb.get('price_limit', '--')}元、"
            f"已发强赎公告、正股ST、评级在配置排除列表（{', '.join(map(str, hard_ratings)) or '--'}）及YTM异常的标的不进入普通排序。"
        ),
        "基础分综合基本面、转股溢价率、YTM、剩余期限、信用、强赎、规模和行业分散，不得只按单一指标解释排名。",
        (
            "动态辅助观察正股涨跌、转债涨跌、股债相对强弱和转股溢价率变化；"
            "它用于补充历史变化信息，但不改变原始分数和排名，只形成辅助状态与风险说明。"
        ),
        "AI可以基于行情与风险证据独立分析，但不得新增候选、改写代码给出的rank、score、qualification或主观调整排名。",
    ]

    return {
        "policy": {
            "signal_owner": "deterministic_code_only",
            "llm_permission": "explain_only",
            "llm_forbidden": ["新增交易信号", "把观察说成建仓", "承诺收益", "主观改写排名"],
        },
        "etf_strategy": {
            "active_strategy": active_etf,
            "active_profile": active_profile,
            "diagnostic_strategies": etf.get("diagnostic_strategies") or [],
        },
        "tl_strategy": {"active_strategy": "technical_with_fund_flow_auxiliary", "fund_flow": fund_flow},
        "convertible_bond_strategy": {"active_strategy": active_cb, "dynamic_scoring": cb.get("dynamic_scoring") or {}},
        "strategy_params": config,
        "etf_rules": etf_rules,
        "tl_rules": tl_rules,
        "convertible_bond_rules": cb_rules,
    }


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:g}%"
    except (TypeError, ValueError):
        return "--"
