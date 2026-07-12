from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_etf_page_uses_trend_signal_label_not_rotation_claim() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "ETF 趋势信号" in html
    assert "ETF 轮动信号" not in html
