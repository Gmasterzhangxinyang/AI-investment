from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.cli import run_daily
from superpower.runtime.artifact_store import atomic_copy_file, atomic_write_text


def test_atomic_write_text_replaces_complete_json_without_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "dashboard.json"
    target.write_text('{"version": 1}', encoding="utf-8")

    atomic_write_text(target, json.dumps({"version": 2, "rows": list(range(100))}))

    assert json.loads(target.read_text(encoding="utf-8"))["version"] == 2
    assert list(tmp_path.glob(".*.tmp")) == []


def test_publish_validates_snapshot_and_switches_dashboard_last(tmp_path: Path, monkeypatch) -> None:
    staging = tmp_path / "staging"
    public_latest = tmp_path / "outputs" / "latest"
    staging.mkdir(parents=True)
    public_latest.mkdir(parents=True)
    staged_dashboard = staging / "dashboard.json"
    staged_market = staging / "market_indicators.json"
    staged_audit = staging / "audit.json"
    staged_report = staging / "report.xlsx"
    public_dashboard = public_latest / "dashboard.json"
    public_market = public_latest / "market_indicators.json"
    public_audit = public_latest / "audit.json"
    public_report = tmp_path / "outputs" / "report.xlsx"

    staged_dashboard.write_text(
        json.dumps({"reportDate": "20260710", "reportPath": "staging", "marketIndicatorsPath": "staging"}),
        encoding="utf-8",
    )
    staged_market.write_text(json.dumps({"rows": [{"code": "510001.SH"}]}), encoding="utf-8")
    staged_audit.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    staged_report.write_bytes(b"complete workbook")
    public_dashboard.write_text(json.dumps({"reportDate": "OLD"}), encoding="utf-8")

    events: list[tuple[str, str]] = []

    def recording_copy(source: Path, target: Path) -> Path:
        events.append(("copy", target.name))
        return atomic_copy_file(source, target)

    def recording_write(target: Path, content: str, **kwargs) -> Path:
        events.append(("write", target.name))
        return atomic_write_text(target, content, **kwargs)

    monkeypatch.setattr(run_daily, "atomic_copy_file", recording_copy)
    monkeypatch.setattr(run_daily, "atomic_write_text", recording_write)

    run_daily._publish_latest_snapshot(
        staged_dashboard_path=staged_dashboard,
        staged_report_path=staged_report,
        staged_market_path=staged_market,
        staged_audit_path=staged_audit,
        public_dashboard_path=public_dashboard,
        public_report_path=public_report,
        public_market_path=public_market,
        public_audit_path=public_audit,
    )

    published = json.loads(public_dashboard.read_text(encoding="utf-8"))
    assert events[-1] == ("write", "dashboard.json")
    assert published["reportDate"] == "20260710"
    assert published["reportPath"] == str(public_report)
    assert published["marketIndicatorsPath"] == str(public_market)
    assert public_report.read_bytes() == b"complete workbook"
    assert json.loads(public_audit.read_text(encoding="utf-8"))["status"] == "PASS"


def test_invalid_staged_snapshot_keeps_previous_public_dashboard(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    public_latest = tmp_path / "outputs" / "latest"
    staging.mkdir(parents=True)
    public_latest.mkdir(parents=True)
    staged_dashboard = staging / "dashboard.json"
    staged_market = staging / "market_indicators.json"
    staged_audit = staging / "audit.json"
    staged_report = staging / "report.xlsx"
    public_dashboard = public_latest / "dashboard.json"

    staged_dashboard.write_text("{broken", encoding="utf-8")
    staged_market.write_text(json.dumps({"rows": []}), encoding="utf-8")
    staged_audit.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    staged_report.write_bytes(b"new")
    public_dashboard.write_text(json.dumps({"reportDate": "OLD"}), encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        run_daily._publish_latest_snapshot(
            staged_dashboard_path=staged_dashboard,
            staged_report_path=staged_report,
            staged_market_path=staged_market,
            staged_audit_path=staged_audit,
            public_dashboard_path=public_dashboard,
            public_report_path=tmp_path / "outputs" / "report.xlsx",
            public_market_path=public_latest / "market_indicators.json",
            public_audit_path=public_latest / "audit.json",
        )

    assert json.loads(public_dashboard.read_text(encoding="utf-8"))["reportDate"] == "OLD"
