from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.utils.text_safety import DISCLAIMER, sanitize_text, with_disclaimer


def test_text_safety_replaces_forbidden_investment_wording() -> None:
    text = sanitize_text("强烈买入，这是确定性机会")
    assert "强烈买入" not in text
    assert "确定性机会" not in text
    assert "模型触发建仓候选" in text


def test_disclaimer_is_added_once() -> None:
    text = with_disclaimer("模型触发建仓候选")
    assert text.count(DISCLAIMER) == 1
    assert with_disclaimer(text).count(DISCLAIMER) == 1

