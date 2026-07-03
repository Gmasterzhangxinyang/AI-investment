from __future__ import annotations

import re
from typing import Any

from .schemas import ChatIntent


class ChatRouter:
    """Deterministic first-pass router. LLM never decides data permissions."""

    def route(self, question: str, dashboard: dict[str, Any]) -> ChatIntent:
        text = question.lower()
        entities = self._extract_entities(question, dashboard)

        if (entities.get("code") or entities.get("name")) and "etf" in text:
            if any(token in text for token in ["状态", "怎么样", "如何", "哪里", "问题", "量能", "趋势", "原因", "为什么", "触发", "分析", "解释"]):
                return ChatIntent("etf_detail", 0.94, entities)
        if any(token in text for token in ["数据库", "db", "sqlite"]):
            if any(token in text for token in ["标的", "名字", "名称", "名单", "有啥", "有什么", "所有", "列表", "列出"]):
                return ChatIntent("asset_list", 0.95, entities)
            return ChatIntent("database_inventory", 0.9, entities)
        if any(token in text for token in ["还有哪些", "其他参数", "全部参数", "所有参数", "参数目录", "除了这个其他"]):
            return ChatIntent("strategy_params", 0.94, entities)
        if any(token in text for token in ["参数", "阈值", "配置", "权重", "量能", "倍数", "指数", "扣分", "截尾", "上限", "下限", "窗口", "硬排除", "硬否决", "st", "topn", "top10"]):
            return ChatIntent("strategy_params", 0.92, entities)
        if any(token in text for token in ["基本面", "最低价格", "最低价", "价格上限", "到期收益", "ytm", "溢价", "强赎", "评级", "信用", "剩余规模", "存续规模"]):
            return ChatIntent("strategy_params", 0.9, entities)
        if "etf" in text and any(token in text for token in ["一共", "多少", "几个", "数量", "有多少"]):
            return ChatIntent("database_inventory", 0.92, entities)
        if any(token in text for token in ["列出", "名单", "名字", "名称", "所有标的", "标的名"]):
            return ChatIntent("asset_list", 0.9, entities)
        if any(token in text for token in ["tl", "国债", "30年", "三十年"]):
            return ChatIntent("tl_timing", 0.95, entities)
        if any(token in text for token in ["可转债", "转债", "convertible", "cb"]):
            return ChatIntent("convertible_bond", 0.92, entities)
        if "etf" in text and any(token in text for token in ["为什么", "原因", "分析", "解释", "没有建仓", "建仓候选", "没入选", "条件"]):
            return ChatIntent("etf_detail", 0.92, entities)
        if any(token in text for token in ["数据", "质检", "缺", "模板", "hash", "刷新", "wind", "文件"]):
            return ChatIntent("data_quality", 0.9, entities)
        if any(token in text for token in ["agent", "审计", "运行", "耗时", "trace", "日志"]):
            return ChatIntent("agent_audit", 0.9, entities)
        if any(token in text for token in ["日报", "报告", "客户", "总结", "结论"]):
            return ChatIntent("daily_report", 0.88, entities)
        if any(token in text for token in ["风险", "风控", "回撤", "仓位"]):
            return ChatIntent("risk_review", 0.86, entities)
        if any(token in text for token in ["关注池", "接近", "还差", "为什么", "没入选"]):
            return ChatIntent("etf_detail", 0.88, entities)
        if any(token in text for token in ["etf", "建仓", "买入", "平仓", "卖出", "创业板", "中证", "a500", "化工"]):
            if any(token in text for token in ["平仓", "卖出"]):
                return ChatIntent("etf_exit", 0.9, entities)
            return ChatIntent("etf_entry", 0.9, entities)
        return ChatIntent("daily_report", 0.62, entities)

    def _extract_entities(self, question: str, dashboard: dict[str, Any]) -> dict[str, str]:
        entities: dict[str, str] = {}
        code_match = re.search(r"\b\d{6}\.(?:sh|sz|SH|SZ)\b", question)
        if code_match:
            entities["code"] = code_match.group(0).upper()

        universe = []
        for key in ("etfWatchlist", "etfBuyCandidates", "etfSellAlerts"):
            universe.extend(dashboard.get(key, []))
        universe.extend((dashboard.get("etf") or {}).get("all_signals", []))
        for row in universe:
            name = str(row.get("name", ""))
            code = str(row.get("code", ""))
            aliases = {name}
            if name.endswith("ETF"):
                aliases.add(name.removesuffix("ETF"))
            aliases.add(name.replace("ETF", ""))
            aliases = {alias for alias in aliases if alias}
            if any(alias in question for alias in aliases):
                entities["name"] = name
                if code:
                    entities["code"] = code
                break
        return entities
