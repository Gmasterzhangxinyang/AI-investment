from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.utils.text_safety import DISCLAIMER, safety_issues, sanitize_text, with_disclaimer


def test_text_safety_replaces_forbidden_investment_wording() -> None:
    text = sanitize_text("强烈买入，这是确定性机会")
    assert "强烈买入" not in text
    assert "确定性机会" not in text
    assert "模型触发建仓候选" in text


def test_disclaimer_is_added_once() -> None:
    text = with_disclaimer("模型触发建仓候选")
    assert text.count(DISCLAIMER) == 1
    assert with_disclaimer(text).count(DISCLAIMER) == 1


def test_negated_compliance_phrases_are_preserved() -> None:
    for source in ["本报告不构成收益承诺。", "系统不承诺收益。", "禁止收益承诺。"]:
        cleaned = sanitize_text(source)
        assert "需人工复核" not in cleaned
        assert source.rstrip("。") in cleaned


def test_positive_forbidden_phrases_are_replaced() -> None:
    cleaned = sanitize_text("这里是收益承诺，且稳赚。")
    assert "收益承诺" not in cleaned
    assert "稳赚" not in cleaned
    assert "需人工复核" in cleaned


def test_safety_issues_detect_unnegated_phrase_after_negated_phrase() -> None:
    issues = safety_issues("本报告不构成收益承诺。这里是收益承诺。")
    assert "收益承诺" in issues
