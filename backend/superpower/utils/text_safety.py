from __future__ import annotations

from typing import Any

import pandas as pd


DISCLAIMER = "本报告仅为规则模型生成的投研辅助结果，不构成投资建议或收益承诺。"

BANNED_PHRASES = [
    "一定上涨",
    "稳赚",
    "无风险",
    "保本",
    "收益承诺",
    "强烈买入",
    "强烈推荐",
    "确定性机会",
]

REPLACEMENTS = {
    "建议买入": "模型触发建仓候选",
    "强烈买入": "模型触发建仓候选",
    "强烈推荐": "需人工复核",
    "买入建议": "建仓候选",
    "卖出建议": "平仓提示",
    "建议卖出": "模型触发平仓提示",
    "建议平仓": "模型触发平仓提示",
    "建议建仓": "模型触发建仓候选",
    "看好": "进入观察池",
    "策略有效": "历史诊断显示",
    "AI认为可以买": "规则模型触发建仓候选",
    "收益稳定": "收益表现需继续验证",
}


def sanitize_text(value: Any) -> str:
    """Return customer-safe investment-report wording."""
    text = "" if value is None else str(value)
    protected = "__SUPERPOWER_DISCLAIMER__"
    text = text.replace(DISCLAIMER, protected)
    for original, replacement in REPLACEMENTS.items():
        text = text.replace(original, replacement)
    for phrase in BANNED_PHRASES:
        text = _replace_unsafe_phrase(text, phrase, "需人工复核")
    return text.replace(protected, DISCLAIMER)


def safety_issues(value: Any) -> list[str]:
    text = "" if value is None else str(value)
    text = text.replace(DISCLAIMER, "")
    issues: list[str] = []
    for phrase in BANNED_PHRASES:
        if _has_unnegated_phrase(text, phrase):
            issues.append(phrase)
    return issues


def _has_unnegated_phrase(text: str, phrase: str) -> bool:
    cursor = 0
    while True:
        idx = text.find(phrase, cursor)
        if idx < 0:
            return False
        sentence_start = max(text.rfind(mark, 0, idx) for mark in ("。", "！", "？", "?", "!", "\n", "；", ";"))
        sentence = text[sentence_start + 1 : idx + len(phrase)]
        if not _is_negated_compliance_context(sentence, phrase):
            return True
        cursor = idx + len(phrase)


def _is_negated_compliance_context(text: str, phrase: str) -> bool:
    start = text.find(phrase)
    if start < 0:
        return False
    left = text[max(0, start - 12) : start]
    return any(token in left for token in ["不构成", "不承诺", "不得", "不能", "禁止", "避免", "无任何"])


def _replace_unsafe_phrase(text: str, phrase: str, replacement: str) -> str:
    cursor = 0
    parts: list[str] = []
    while True:
        idx = text.find(phrase, cursor)
        if idx < 0:
            parts.append(text[cursor:])
            break
        parts.append(text[cursor:idx])
        sentence_start = max(text.rfind(mark, 0, idx) for mark in ("。", "！", "？", "?", "!", "\n", "；", ";"))
        sentence = text[sentence_start + 1 : idx + len(phrase)]
        parts.append(phrase if _is_negated_compliance_context(sentence, phrase) else replacement)
        cursor = idx + len(phrase)
    return "".join(parts)


def sanitize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    object_columns = out.select_dtypes(include=["object"]).columns
    for column in object_columns:
        out[column] = out[column].map(sanitize_text)
    return out


def scan_frame(frame: pd.DataFrame, label: str) -> list[dict[str, object]]:
    if frame.empty:
        return []
    issues: list[dict[str, object]] = []
    object_columns = frame.select_dtypes(include=["object"]).columns
    for column in object_columns:
        for idx, value in frame[column].items():
            hits = safety_issues(value)
            if hits:
                issues.append({"sheet": label, "row": int(idx) + 2, "column": column, "phrases": "、".join(hits)})
    return issues


def sanitize_dashboard(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_dashboard(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_dashboard(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def with_disclaimer(text: str) -> str:
    cleaned = sanitize_text(text)
    if DISCLAIMER in cleaned:
        return cleaned
    return f"{DISCLAIMER}\n{cleaned}" if cleaned else DISCLAIMER
