from __future__ import annotations

from typing import Any

import pandas as pd

from superpower.runtime.context import AgentContext
from superpower.tools.frame import records
from superpower.tools.llm import generate_text
from superpower.tools.text_cleaner import clean_llm_text
from superpower.utils.text_safety import sanitize_text


COMMITTEE_ROLES = [
    {
        "role": "DataQAAnalyst",
        "title": "数据质量审查员",
        "developer": "你是机构投研系统的数据质量审查员。只能基于给定数据质检表指出数据新鲜度、完整性、模板、历史长度风险；不得生成交易建议。禁止使用Markdown，不要使用#、**、表格、分割线、项目符号，只输出商务纯文本。",
        "focus": "检查源数据、模板、日期、历史长度、缺失项。输出：结论、必须人工确认项、是否影响今日报告。",
    },
    {
        "role": "StrategyReviewer",
        "title": "策略规则复核员",
        "developer": "你是机构投研系统的策略规则复核员。只能复核确定性 ETF/TL/可转债信号是否与规则描述一致；不得新增或删除任何信号。禁止使用Markdown，不要使用#、**、表格、分割线、项目符号，只输出商务纯文本。",
        "focus": "复核 ETF 建仓/关注/平仓、TL状态、可转债排序是否有明显解释风险。输出：规则一致性、需要进一步确认的参数。",
    },
    {
        "role": "RiskReviewer",
        "title": "风险审稿员",
        "developer": "你是机构投研系统的风险审稿员。只能根据风控摘要和回测诊断提示风险；不得承诺收益，不得建议绕过风控。禁止使用Markdown，不要使用#、**、表格、分割线、项目符号，只输出商务纯文本。",
        "focus": "指出短样本、数据缺失、集中风险、信号过少/过多、人工复核事项。输出：风险等级和风险话术。",
    },
    {
        "role": "ReportWriter",
        "title": "日报主笔",
        "developer": "你是机构投研系统的日报主笔。只能把已有表格结果写成客户可读中文，不得加入表格外标的、新闻或主观承诺。禁止使用Markdown，不要使用#、**、表格、分割线、项目符号，只输出商务纯文本。",
        "focus": "生成客户日报口径：今日结论、ETF、TL、可转债、风险提示。语气专业克制。",
    },
]

COMMITTEE_LLM_TIMEOUT_SECONDS = 18


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        payload = _payload(context)
        model_config = context.get("model_config")
        daily_report_llm_enabled = bool(model_config.get("daily_report_llm_enabled", False))
        rows: list[dict[str, Any]] = []
        for role in COMMITTEE_ROLES:
            prompt = _build_prompt(role, payload)
            fallback = _fallback_review(role, payload)
            if daily_report_llm_enabled:
                result = generate_text(
                    prompt,
                    model_config,
                    timeout_seconds=COMMITTEE_LLM_TIMEOUT_SECONDS,
                    developer_text=role["developer"],
                )
                llm_used = result.used
                provider = result.provider
                model = result.model
                reason = result.reason
                review = result.text if result.used else fallback
            else:
                llm_used = False
                provider = model_config.get("provider", "openai")
                model = model_config.get("primary_model", "gpt-5.5")
                reason = "daily_report_llm_disabled_for_refresh_stability"
                review = fallback
            rows.append(
                {
                    "role": role["role"],
                    "title": role["title"],
                    "llm_used": llm_used,
                    "provider": provider,
                    "model": model,
                    "reason": reason,
                    "review": sanitize_text(clean_llm_text(review)),
                }
            )

        reviews = pd.DataFrame(rows)
        context.put("ai_committee_reviews", reviews)
        return {
            "committee_roles": len(reviews),
            "committee_llm_used": int(reviews["llm_used"].sum()) if not reviews.empty else 0,
            "committee_fallback_roles": int((~reviews["llm_used"]).sum()) if not reviews.empty else 0,
        }


def _payload(context: AgentContext) -> dict[str, Any]:
    return {
        "data_quality": records(context.get("data_quality_report"), limit=30),
        "etf_buy_candidates": records(context.get("etf_buy_candidates"), limit=8),
        "etf_watchlist": records(context.get("etf_watchlist"), limit=8),
        "etf_sell_alerts": records(context.get("etf_sell_alerts"), limit=8),
        "tl_today": records(context.get("tl_today"), limit=1),
        "convertible_bond_top10": records(context.get("cb_top10"), limit=10),
        "backtest_summary": records(context.get("backtest_summary"), limit=12),
        "risk_summary": records(context.get("risk_summary"), limit=12),
        "hard_boundaries": [
            "不得改变任何 buy_signal、sell_signal、TL state、score、rank 或 risk level",
            "不得新增表格中不存在的标的",
            "不得承诺收益",
            "短样本只能称为历史诊断，不能称为策略有效性证明",
        ],
    }


def _build_prompt(role: dict[str, str], payload: dict[str, Any]) -> str:
    return (
        f"你的角色：{role['title']}。\n"
        f"复核重点：{role['focus']}\n"
        "请严格基于下面 JSON 数据输出中文复核意见，最多 6 条，必须可审计。\n"
        "输出格式要求：纯文本；不要 Markdown；不要标题符号；不要粗体；不要表格；不要分割线；可以用 1. 2. 3. 编号。\n\n"
        f"{payload}"
    )


def _fallback_review(role: dict[str, str], payload: dict[str, Any]) -> str:
    quality_warns = sum(1 for row in payload["data_quality"] if row.get("status") == "WARN")
    quality_fails = sum(1 for row in payload["data_quality"] if row.get("status") == "FAIL")
    etf_buys = len(payload["etf_buy_candidates"])
    etf_watch = len(payload["etf_watchlist"])
    etf_sells = len(payload["etf_sell_alerts"])
    cb_count = len(payload["convertible_bond_top10"])
    tl_state = payload["tl_today"][0].get("state", "--") if payload["tl_today"] else "--"
    backtest_warns = sum(1 for row in payload["backtest_summary"] if row.get("level") == "WARN")

    if role["role"] == "DataQAAnalyst":
        return f"模板复核：数据质检 WARN {quality_warns} 项、FAIL {quality_fails} 项。若 WARN 包含历史不足或可转债缺失，应在日报中明确披露。"
    if role["role"] == "StrategyReviewer":
        return f"模板复核：ETF建仓 {etf_buys} 个、关注 {etf_watch} 个、平仓 {etf_sells} 个；TL状态为{tl_state}；AI未改写任何信号。"
    if role["role"] == "RiskReviewer":
        return f"模板复核：回测诊断 WARN {backtest_warns} 项，可转债Top10 {cb_count} 个。当前不可把短样本结果包装成收益验证。"
    return f"模板复核：今日ETF建仓 {etf_buys}、关注 {etf_watch}、平仓 {etf_sells}，TL为{tl_state}，可转债Top10为{cb_count}。"
