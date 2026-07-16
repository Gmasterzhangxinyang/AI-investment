from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_current_strategy_ids_are_documented_from_live_config() -> None:
    params = json.loads(_read("configs/strategy_params.json"))
    etf_strategy = params["etf"]["active_strategy"]
    cb_strategy = params["convertible_bond"]["active_strategy"]

    current = _read("docs/CURRENT_SYSTEM.md")
    readme = _read("README.md")
    etf_model = _read("docs/ETF_MODEL.md")
    cb_model = _read("docs/CONVERTIBLE_BOND_MODEL.md")

    assert etf_strategy == "trend_pullback_v2"
    assert cb_strategy == "dynamic_v2"
    assert all(etf_strategy in text for text in (current, readme, etf_model))
    assert all(cb_strategy in text for text in (current, readme, cb_model))


def test_current_docs_describe_agent_and_multi_asset_evidence() -> None:
    runtime = _read("docs/CHAT_AGENT_RUNTIME.md")
    current = _read("docs/CURRENT_SYSTEM.md")

    for token in ("ReAct", "etf_multi_assets", "EvidenceAccuracyReviewer", "OutputGuardrail"):
        assert token in runtime or token in current
    assert "2 至 10 只" in runtime
    assert "最近 30 个交易日" in runtime
    assert "400 个交易日" in runtime


def test_current_docs_do_not_present_old_product_state_as_current() -> None:
    core = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "docs/CURRENT_SYSTEM.md",
            "docs/CLIENT_PRODUCT_GUIDE.md",
            "docs/ETF_MODEL.md",
            "docs/STRATEGY_LOGIC.md",
        )
    )

    assert "V1.1" not in core
    assert "完整交易历史诊断" not in core
    assert "跌破 MA5 平仓量能 | 1.5" not in core
    assert "score = base_score" in core


def test_historical_plans_are_marked_as_non_current() -> None:
    historical = sorted((ROOT / "docs" / "superpowers" / "plans").glob("*.md"))
    historical += sorted((ROOT / "docs" / "superpowers" / "specs").glob("*.md"))

    assert historical
    for path in historical:
        assert "历史实施记录" in path.read_text(encoding="utf-8"), path
