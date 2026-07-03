from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.server.app import _any_configured_source_file_exists


def test_refresh_allows_single_missing_source_excel(tmp_path: Path) -> None:
    etf_file = tmp_path / "etf.xlsx"
    tl_file = tmp_path / "tl.xlsx"
    cb_file = tmp_path / "cb.xlsx"
    etf_file.write_bytes(b"placeholder")

    assert _any_configured_source_file_exists(etf_file, tl_file, cb_file)


def test_refresh_rejects_only_when_all_core_source_excels_missing(tmp_path: Path) -> None:
    assert not _any_configured_source_file_exists(
        tmp_path / "missing_etf.xlsx",
        tmp_path / "missing_tl.xlsx",
        tmp_path / "missing_cb.xlsx",
    )
