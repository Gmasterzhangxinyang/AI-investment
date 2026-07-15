from __future__ import annotations

import re

from superpower.tools.text_cleaner import clean_llm_text
from superpower.utils.text_safety import BANNED_PHRASES, sanitize_text

from .schemas import ChatIntent, GuardrailResult, ToolResult


class ChatGuardrails:
    forbidden_patterns = [
        r"保证(?:收益|赚钱|盈利)",
        r"稳赚",
        r"必涨",
        r"一定(?:买入|卖出|上涨|盈利)",
        r"无风险",
    ]
    forbidden_phrases = BANNED_PHRASES

    def validate_input(self, question: str) -> GuardrailResult:
        text = question.strip()
        issues: list[str] = []
        if len(text) > 1200:
            issues.append("问题过长，请拆成更小的问题。")
        if re.search(r"(删除|覆盖|清空|reset|rm\s+-rf)", text, flags=re.I):
            issues.append("聊天入口不允许执行破坏性操作。")
        return GuardrailResult(not issues, issues, text)

    def validate_output(self, text: str, intent: ChatIntent, tools: list[ToolResult] | None = None) -> GuardrailResult:
        cleaned = sanitize_text(clean_llm_text(text))
        issues = []
        for pattern in self.forbidden_patterns:
            if self._has_unnegated_forbidden_claim(cleaned, pattern):
                issues.append(f"命中禁止表述：{pattern}")
        for phrase in self.forbidden_phrases:
            if phrase in cleaned:
                issues.append(f"命中禁止表述：{phrase}")

        tools = tools or []
        if intent.name == "tl_timing" and self._contains_positive_entry_claim(cleaned) and not self._has_tl_buy_signal(tools):
            issues.append("TL 建仓表述缺少确定性 buy_signal 依据。")
        if intent.name.startswith("etf") and self._contains_positive_entry_claim(cleaned) and not self._has_etf_entry_signal(tools):
            issues.append("ETF 建仓/买入表述缺少确定性 entry 信号依据。")
        if self._confuses_watchlist_with_entry_signal(cleaned):
            issues.append("关注池和买入信号区分不够清楚。")

        if issues:
            cleaned = (
                "系统已拦截一段可能不够稳健的 AI 表述。"
                "请以确定性信号页面为准：ETF、TL、可转债信号均由代码生成，AI 只负责解释。"
            )
        return GuardrailResult(not issues, issues, cleaned)

    def _contains_positive_entry_claim(self, text: str) -> bool:
        negative_patterns = [
            r"(没有|无|未|不|不能|不得|不可|尚未|并非).{0,10}(买入|建仓|入场|entry)",
            r"(买入|建仓|入场|entry).{0,10}(没有|无|未|不|不能|不得|不可|尚未|并非)",
            r"(买入|建仓).{0,8}(候选|信号|建议).{0,8}(0|零|无|没有)",
            r"(0|零|无|没有).{0,8}(买入|建仓).{0,8}(候选|信号|建议)",
        ]
        if any(re.search(pattern, text, flags=re.I) for pattern in negative_patterns):
            return False
        explicit_advice_patterns = [
            r"(建议|直接|立即|马上|应当|应该).{0,10}(买入|建仓|入场)",
            r"(买入|建仓|入场).{0,10}(建议执行|可以执行|立即执行)",
        ]
        if any(re.search(pattern, text, flags=re.I) for pattern in explicit_advice_patterns):
            return True
        cautious_patterns = [
            r"(观察|等待).{0,16}(买入|建仓|入场).{0,8}(条件|确认)",
            r"(买入|建仓|入场).{0,8}(条件|确认).{0,16}(等待|未满足|未确认)",
        ]
        if any(re.search(pattern, text, flags=re.I) for pattern in cautious_patterns):
            return False
        positive_patterns = [
            r"(建议|可以|可考虑|适合|触发|满足|给出).{0,12}(买入|建仓|入场)",
            r"(买入|建仓|入场).{0,12}(建议|信号|条件满足|触发)",
        ]
        return any(re.search(pattern, text, flags=re.I) for pattern in positive_patterns)

    def _confuses_watchlist_with_entry_signal(self, text: str) -> bool:
        if "关注池" not in text or ("买入信号" not in text and "建仓信号" not in text):
            return False
        clear_negative_patterns = [
            r"关注池.{0,16}(不是|不等同|不代表|不能视为|不能说成|并非).{0,16}(买入信号|建仓信号)",
            r"(买入信号|建仓信号).{0,16}(不是|不等同|不代表|不能视为|不能说成|并非).{0,16}关注池",
            r"关注池.{0,16}(不得|不能|不可).{0,16}(说成|表述为|升级为).{0,16}(买入|建仓)",
        ]
        if any(re.search(pattern, text) for pattern in clear_negative_patterns):
            return False
        confusing_patterns = [
            r"关注池.{0,12}(就是|等同|属于|视为|可以作为).{0,12}(买入信号|建仓信号)",
            r"(买入信号|建仓信号).{0,12}(来自|包括|包含).{0,12}关注池",
        ]
        return any(re.search(pattern, text) for pattern in confusing_patterns)

    def _has_unnegated_forbidden_claim(self, text: str, pattern: str) -> bool:
        for match in re.finditer(pattern, text):
            sentence = self._sentence_around(text, match.start(), match.end())
            if re.search(r"(不|不能|无法|不会|不可|不得|并非|没有|不承诺|不能承诺|不保证|无法保证).{0,30}" + pattern, sentence):
                continue
            if re.search(pattern + r".{0,20}(不成立|不可能|不可取|不能承诺|不能作为|不能保证)", sentence):
                continue
            if re.search(r"(吗|是否|能不能).{0,12}[？?]", sentence):
                continue
            return True
        return False

    def _sentence_around(self, text: str, start: int, end: int) -> str:
        left_boundaries = [text.rfind(mark, 0, start) for mark in ("。", "！", "？", "?", "!", "\n", "；", ";")]
        left = max(left_boundaries)
        right_candidates = [idx for mark in ("。", "！", "？", "?", "!", "\n", "；", ";") if (idx := text.find(mark, end)) != -1]
        right = min(right_candidates) if right_candidates else len(text)
        return text[left + 1 : right + 1]

    def _has_etf_entry_signal(self, tools: list[ToolResult]) -> bool:
        for tool in tools:
            if tool.tool == "get_etf_signals":
                data = tool.data if isinstance(tool.data, dict) else {}
                if data.get("buy_candidates"):
                    return True
            if tool.tool == "get_etf_single_asset":
                data = tool.data if isinstance(tool.data, dict) else {}
                for signal in data.get("signals", []) or []:
                    if str(signal.get("signal_bucket", "")).lower() == "entry" and self._truthy(signal.get("buy_signal")):
                        return True
            if tool.tool == "get_etf_strategy_comparison":
                data = tool.data if isinstance(tool.data, dict) else {}
                if any(self._truthy(item.get("buy_candidate")) for item in data.get("decisions", []) or []):
                    return True
        return False

    def _has_tl_buy_signal(self, tools: list[ToolResult]) -> bool:
        for tool in tools:
            if tool.tool != "get_tl_state" or not isinstance(tool.data, dict):
                continue
            for row in tool.data.get("today", []) or []:
                if (
                    self._truthy(row.get("buy_signal"))
                    or str(row.get("status", "")) == "entry_candidate"
                    or str(row.get("state", "")) == "模型触发建仓候选"
                ):
                    return True
        return False

    def _truthy(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False
