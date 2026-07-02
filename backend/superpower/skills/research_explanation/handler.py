from __future__ import annotations

import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.tools.frame import records
from superpower.tools.llm import generate_text
from superpower.tools.text_cleaner import clean_llm_text
from superpower.utils.text_safety import with_disclaimer


EXPLANATION_LLM_TIMEOUT_SECONDS = 25


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        buys = context.get("etf_buy_candidates")
        watchlist = context.get("etf_watchlist")
        sells = context.get("etf_sell_alerts")
        tl_today = context.get("tl_today")
        cb_top10 = context.get("cb_top10")
        backtest_summary = context.get("backtest_summary")
        ai_committee_reviews = context.get("ai_committee_reviews")
        model_config = context.get("model_config")
        tl_state = str(tl_today.iloc[0]["state"])

        fallback_text, fallback_line_count = deterministic_summary(buys, watchlist, sells, tl_today, cb_top10, backtest_summary)
        prompt = build_prompt(buys, watchlist, sells, tl_today, cb_top10, backtest_summary, ai_committee_reviews)
        daily_report_llm_enabled = bool(model_config.get("daily_report_llm_enabled", False))
        if daily_report_llm_enabled:
            llm_result = generate_text(prompt, model_config, timeout_seconds=EXPLANATION_LLM_TIMEOUT_SECONDS)
            llm_used = llm_result.used
            llm_provider = llm_result.provider
            llm_model = llm_result.model
            llm_reason = llm_result.reason
            content_source = llm_result.text if llm_result.used else fallback_text
        else:
            llm_used = False
            llm_provider = model_config.get("provider", "openai")
            llm_model = model_config.get("primary_model", "gpt-5.5")
            llm_reason = "daily_report_llm_disabled_for_refresh_stability"
            content_source = fallback_text
        content = with_disclaimer(clean_llm_text(content_source))

        summary = pd.DataFrame({"section": ["summary"], "content": [content]})
        context.put("research_summary", summary)
        context.put("llm_usage", {
            "llm_used": llm_used,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_reason": llm_reason,
        })
        return {
            "summary_lines": content.count("\n") + 1,
            "fallback_summary_lines": fallback_line_count,
            "llm_used": llm_used,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_reason": llm_reason,
        }


def deterministic_summary(
    buys: pd.DataFrame,
    watchlist: pd.DataFrame,
    sells: pd.DataFrame,
    tl_today: pd.DataFrame,
    cb_top10: pd.DataFrame,
    backtest_summary: pd.DataFrame,
) -> tuple[str, int]:
    tl_state = str(tl_today.iloc[0]["state"])
    lines = [
        f"ETF建仓候选 {len(buys)} 个，关注池 {len(watchlist)} 个，平仓提示 {len(sells)} 个。",
        f"TL日频状态为“{tl_state}”。",
        f"可转债Top10数量为 {len(cb_top10)} 个。",
        "当前解释由确定性模板生成；配置开启且存在 OPENAI_API_KEY 后，可由大模型生成解释文本，但交易信号仍由规则代码生成。",
    ]
    if not buys.empty:
        top = buys.iloc[0]
        lines.append(f"ETF建仓候选中评分最高的是{top['name']}，触发因素：{top['signal_reason']}。")
    if not watchlist.empty:
        top_watch = watchlist.iloc[0]
        lines.append(
            f"关注池评分最高的是{top_watch['name']}，类型：{top_watch['watch_type']}，"
            f"还差条件：{top_watch['missing_condition']}。"
        )
    if not sells.empty:
        top_sell = sells.iloc[0]
        lines.append(f"当前持仓中触发平仓提示的是{top_sell['name']}，触发因素：{top_sell['signal_reason']}。")
    if not cb_top10.empty:
        top_cb = cb_top10.iloc[0]
        lines.append(f"可转债评分最高的是{top_cb['bond_name']}，评分{top_cb['score']}，原因：{top_cb['rank_reason']}。")
    if not backtest_summary.empty:
        warn_count = int((backtest_summary["level"] == "WARN").sum())
        lines.append(f"历史诊断共有 {warn_count} 个 WARN；短样本时只能说明流程与信号频率，不能作为正式收益验证。")
    tl_row = tl_today.iloc[0]
    lines.append(
        "TL判定口径："
        f"周线MACD为“{tl_row.get('weekly_macd_reason', '未知')}”，"
        f"周线KDJ为“{tl_row.get('weekly_kdj_threshold_check', '未知')}”，"
        f"日线KDJ为“{tl_row.get('daily_kdj_threshold_check', '未知')}”。"
    )
    return "\n".join(lines), len(lines)


def build_prompt(
    buys: pd.DataFrame,
    watchlist: pd.DataFrame,
    sells: pd.DataFrame,
    tl_today: pd.DataFrame,
    cb_top10: pd.DataFrame,
    backtest_summary: pd.DataFrame,
    ai_committee_reviews: pd.DataFrame,
) -> str:
    payload = {
        "etf_buy_candidates": records(buys, limit=5),
        "etf_watchlist": records(watchlist, limit=5),
        "etf_sell_alerts": records(sells, limit=5),
        "tl_today": records(tl_today, limit=1),
        "convertible_bond_top10": records(cb_top10, limit=10),
        "backtest_summary": records(backtest_summary, limit=12),
        "ai_committee_reviews": records(ai_committee_reviews, limit=4),
        "hard_rules": [
            "不得新增表格中不存在的标的",
            "不得改写 buy_signal、sell_signal、TL state 或 score",
            "不得承诺收益",
            "必须说明 TL 周线硬风控是否覆盖日线建仓倾向",
            "短历史回测只能表述为诊断，不得表述为策略已经有效",
        ],
    }
    return (
        "请根据下面的确定性策略输出，写一段日报投研解释，分为：今日结论、ETF信号、TL信号、可转债、历史诊断、风险提示。\n"
        "请只解释这些数据，不要引入外部新闻或新增判断。\n\n"
        "输出格式要求：纯文本；不要 Markdown；不要 # 标题；不要 ** 粗体；不要表格；不要分割线；不要项目符号。\n"
        "可以用短段落和 1. 2. 3. 编号，适合直接放入前端和PDF。\n\n"
        f"{payload}"
    )
