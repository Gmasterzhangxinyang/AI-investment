from __future__ import annotations

import re
from typing import Any

from .schemas import ChatIntent


class ChatRouter:
    """Deterministic first-pass router. LLM never decides data permissions."""

    def route(self, question: str, dashboard: dict[str, Any]) -> ChatIntent:
        text = question.lower()
        entities = self._extract_entities(question, dashboard)

        if self._is_conversation(question):
            return ChatIntent("conversation", 0.99, {})

        if self._asks_external_data(question):
            return ChatIntent("external_data_unavailable", 0.99, {})

        if self._asks_chat_data_scope(question):
            return ChatIntent("chat_data_scope", 0.99, {})

        mentioned_asset_groups = sum(
            [
                "etf" in text,
                any(token in text for token in ["tl", "国债", "30年", "三十年"]),
                any(token in text for token in ["可转债", "转债", "convertible", "cb"]),
            ]
        )
        if mentioned_asset_groups >= 2 and any(token in text for token in ["风险", "风控", "综合", "整体", "跨资产"]):
            return ChatIntent("risk_review", 0.97, entities)

        if self._asks_etf_strategy_comparison(question, entities):
            return ChatIntent("etf_strategy_comparison", 0.98, entities)

        if self._asks_generic_etf_strategy_comparison(question):
            return ChatIntent("strategy_comparison", 0.97, entities)

        if (
            any(token in text for token in ["原策略", "2.0", "v2", "趋势回踩"])
            and any(token in text for token in ["哪个", "对比", "相比", "区别", "更好", "差别"])
        ):
            return ChatIntent("strategy_comparison", 0.96, entities)
        if any(token in text for token in ["历史诊断", "历史判断", "历史表现", "回测", "胜率", "正收益比例", "最大回撤", "假反转"]):
            return ChatIntent("historical_diagnostics", 0.95, entities)
        if any(token in text for token in ["策略稳定", "策略可靠吗", "策略可靠", "策略效果", "策略好不好", "这些策略稳定"]):
            return ChatIntent("strategy_stability", 0.94, entities)
        if "策略" in text and any(token in text for token in ["现在使用", "当前使用", "启用哪个", "默认策略"]):
            return ChatIntent("strategy_params", 0.95, entities)

        ranking_entities = self._etf_ranking_entities(question)
        if ranking_entities is not None:
            return ChatIntent("etf_ranking", 0.96, {**entities, **ranking_entities})

        if "etf" in text and not (entities.get("code") or entities.get("name")):
            if any(token in text for token in ["建仓候选", "买入候选", "买入信号"]):
                return ChatIntent("etf_entry", 0.97, entities)
            if any(token in text for token in ["平仓提示", "平仓信号", "卖出提示", "卖出信号"]):
                return ChatIntent("etf_exit", 0.97, entities)

        if any(token in text for token in ["可转债", "转债", "convertible", "cb"]):
            ranking_or_detail = ["第", "排名", "排行", "top", "前十", "前10", "没进", "未进", "没入选", "为什么"]
            if any(token in text for token in ranking_or_detail):
                return ChatIntent("convertible_bond", 0.96, entities)

        if (entities.get("code") or entities.get("name")) and "etf" in text:
            if any(token in text for token in ["平仓提示", "平仓信号", "卖出提示", "卖出信号"]):
                return ChatIntent("etf_exit", 0.97, entities)
            if any(token in text for token in ["建仓候选", "买入候选", "买入信号"]):
                return ChatIntent("etf_entry", 0.97, entities)
            return ChatIntent("etf_detail", 0.94, entities)
        unknown_etf_name = self._unknown_etf_name(question)
        if unknown_etf_name and any(token in text for token in ["今天", "状态", "怎么样", "如何", "哪里", "问题", "量能", "趋势", "原因", "为什么", "触发", "分析", "解释"]):
            return ChatIntent("etf_detail", 0.91, {"name": unknown_etf_name, "asset_type": "ETF", "not_found": "true"})
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
        return ChatIntent("clarification", 0.62, entities)

    def _is_conversation(self, question: str) -> bool:
        normalized = re.sub(r"[\s，。！？!?、~～]+", "", question).lower()
        if question.strip() and not normalized:
            return True
        return normalized in {
            "你好",
            "你好呀",
            "您好",
            "嗨",
            "哈喽",
            "hello",
            "hi",
            "在吗",
            "谢谢",
            "谢谢你",
            "你在干啥",
            "你在干嘛",
            "你在干什么",
            "你在做什么",
            "你是干嘛的",
            "你是谁",
            "说话",
            "回话",
            "怎么不说话",
            "啥情况",
        }

    def _asks_external_data(self, question: str) -> bool:
        text = question.lower().replace(" ", "")
        return any(token in text for token in ["新闻", "资讯", "快讯", "热搜", "实时消息", "最新消息"])

    def _asks_chat_data_scope(self, question: str) -> bool:
        text = question.lower().replace(" ", "")
        explicit_phrases = [
            "能访问多少数据",
            "可以访问多少数据",
            "能读取多少数据",
            "可以读取多少数据",
            "读取多少数据",
            "能查多久",
            "可以查多久",
            "能查哪些数据",
            "可以查哪些数据",
            "问答数据范围",
            "问答数据权限",
            "ai数据范围",
            "ai数据权限",
            "数据访问范围",
        ]
        if any(phrase in text for phrase in explicit_phrases):
            return True
        asks_scope = any(token in text for token in ["范围", "权限", "多久", "多少", "哪些"])
        mentions_chat = any(token in text for token in ["ai", "问答", "模型", "聊天"])
        mentions_data = any(token in text for token in ["数据", "历史", "数据库"])
        asks_latest_boundary = mentions_data and any(token in text for token in ["最新到哪天", "最新到哪一天", "最新日期", "数据到哪天"])
        return asks_latest_boundary or (asks_scope and mentions_chat and mentions_data)

    def _asks_etf_strategy_comparison(self, question: str, entities: dict[str, str]) -> bool:
        text = question.lower().replace(" ", "")
        if "etf" not in text or not (entities.get("code") or entities.get("name")):
            return False
        comparison_tokens = [
            "双策略",
            "两个策略",
            "两套策略",
            "两个etf策略",
            "原策略和2.0",
            "原策略与2.0",
            "v1和v2",
            "v1与v2",
            "分别分析",
        ]
        return any(token in text for token in comparison_tokens)

    def _asks_generic_etf_strategy_comparison(self, question: str) -> bool:
        text = question.lower().replace(" ", "")
        if "etf" not in text:
            return False
        comparison_tokens = ["双策略", "两个策略", "两套策略", "策略对比", "策略比较", "原策略和2.0", "原策略与2.0"]
        return any(token in text for token in comparison_tokens)

    def _etf_ranking_entities(self, question: str) -> dict[str, str] | None:
        text = question.lower().replace(" ", "")
        if "etf" not in text:
            return None
        ranking_tokens = [
            "最高",
            "最低",
            "最大",
            "最小",
            "最强",
            "最弱",
            "最好",
            "最佳",
            "排名",
            "排行",
            "第一",
            "top",
            "前几",
            "前十",
            "前10",
        ]
        if not any(token in text for token in ranking_tokens):
            return None

        metric = ""
        if any(token in text for token in ["收盘", "价格", "净值"]):
            metric = "close"
        elif any(token in text for token in ["量能", "量比", "成交量"]):
            metric = "vol_ratio60"
        elif any(token in text for token in ["份额", "申购", "赎回"]):
            metric = "share_change"
        elif any(token in text for token in ["评分", "分数", "强弱", "排名", "最强", "最弱"]):
            metric = "score"

        direction = "asc" if any(token in text for token in ["最低", "最小", "最弱", "倒数"]) else "desc"
        limit_match = re.search(r"(?:top|前)\s*(\d{1,2})", text, flags=re.I)
        limit = min(max(int(limit_match.group(1)), 1), 10) if limit_match else 3
        return {"metric": metric, "direction": direction, "limit": str(limit)}

    def _extract_entities(self, question: str, dashboard: dict[str, Any]) -> dict[str, str]:
        entities: dict[str, str] = {}
        code_match = re.search(r"\b\d{6}\.(?:sh|sz|SH|SZ)\b", question)
        if code_match:
            entities["code"] = code_match.group(0).upper()

        universe = []
        for key in ("etfWatchlist", "etfBuyCandidates", "etfSellAlerts"):
            universe.extend(dashboard.get(key, []))
        universe.extend((dashboard.get("etf") or {}).get("all_signals", []))
        cb = dashboard.get("convertible_bond") or {}
        for key in ("top10", "qualified", "weak_watch", "risk_watch", "candidates", "ranked_candidates", "excluded"):
            universe.extend(cb.get(key, []))
        for key in ("cbTop10", "cbRanked", "cbExcluded"):
            universe.extend(dashboard.get(key, []))
        for row in universe:
            name = str(row.get("name") or row.get("bond_name") or "")
            code = str(row.get("code") or row.get("bond_code") or "")
            row_type = str(row.get("asset_type") or "").upper()
            asks_etf = "etf" in question.lower()
            asks_convertible = "可转债" in question or "转债" in question
            is_convertible = row_type == "CONVERTIBLE" or name.endswith("转债") or bool(row.get("bond_code"))
            is_etf = row_type == "ETF" or "ETF" in name.upper()
            if asks_etf and is_convertible:
                continue
            if asks_convertible and is_etf:
                continue
            aliases = {name}
            if name.endswith("ETF"):
                aliases.add(name.removesuffix("ETF"))
            aliases.add(name.replace("ETF", ""))
            if name.endswith("转债"):
                aliases.add(name.removesuffix("转债"))
            aliases.add(code.replace(".SH", "").replace(".SZ", ""))
            aliases = {alias for alias in aliases if alias}
            if any(alias in question for alias in aliases):
                entities["name"] = name
                if code:
                    entities["code"] = code
                break
        return entities

    def _unknown_etf_name(self, question: str) -> str:
        for match in re.findall(r"([A-Za-z0-9\u4e00-\u9fff]{1,24}?ETF)", question, flags=re.IGNORECASE):
            name = match.strip()
            if name.upper() == "ETF":
                continue
            return name
        return ""
