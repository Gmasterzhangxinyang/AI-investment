from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_etf_page_uses_trend_signal_label_not_rotation_claim() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "ETF 趋势信号" in html
    assert "ETF 轮动信号" not in html


def test_etf_candidate_and_exit_tables_use_full_width_cards() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert '<article class="card span-2">\n                <h3>建仓候选</h3>' in html
    assert '<article class="card span-2">\n                <h3>平仓提示</h3>' in html


def test_etf_main_page_does_not_show_historical_diagnostics() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "历史表现诊断" not in html
    assert "etf-history-highlights" not in html
    assert "etf-history-table" not in html


def test_convertible_page_explains_dynamic_and_legacy_ranking_boundaries() -> None:
    app = (ROOT / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")

    assert '["linkage_state", "短期联动"]' in app
    assert '["linkage_note", "联动提示"]' in app
    assert "动态层不会改变资格和硬风控，只可调整同一资格池内顺序" in app
    assert "短期联动只作提示，不进入原策略排名" in app
