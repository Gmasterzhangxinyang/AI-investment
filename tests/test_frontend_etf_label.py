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
