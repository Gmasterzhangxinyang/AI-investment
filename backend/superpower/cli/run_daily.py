from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from superpower.agents import build_daily_workflow
from superpower.audit.latest import audit_latest
from superpower.db import ingest_dashboard
from superpower.runtime import AgentContext, AgentOrchestrator, SkillRegistry
from superpower.runtime.audit_logger import AuditLogger
from superpower.runtime.artifact_store import atomic_copy_file, atomic_write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Superpower AI daily research workflow.")
    parser.add_argument("--etf-file", type=Path, required=True)
    parser.add_argument("--tl-file", type=Path, required=True)
    parser.add_argument("--cb-file", type=Path, default=None)
    parser.add_argument("--root-dir", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument(
        "--strict-audit",
        action="store_true",
        help="Exit with non-zero status when the independent QA audit is not PASS.",
    )
    parser.add_argument(
        "--disable-llm",
        action="store_true",
        help="Disable optional LLM commentary for fast deterministic refresh runs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = args.root_dir.resolve()
    output_dir = args.output_dir or root_dir / "outputs"
    log_dir = args.log_dir or root_dir / "logs"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_dir = output_dir / ".staging" / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    cb_file = args.cb_file or _configured_cb_file(root_dir)

    context = AgentContext(run_id=run_id, root_dir=root_dir)
    context.put("etf_file", args.etf_file)
    context.put("tl_file", args.tl_file)
    context.put("cb_file", cb_file)
    context.put("positions_file", root_dir / "configs" / "positions.csv")
    context.put("strategy_params_file", root_dir / "configs" / "strategy_params.json")
    context.put("universe_file", root_dir / "configs" / "universe_etf.json")
    context.put("model_config_file", root_dir / "configs" / "model_config.json")
    context.put("disable_llm", args.disable_llm)
    context.put("delivery_file", root_dir / "configs" / "delivery.json")
    context.put("output_dir", output_dir)
    context.put("latest_work_dir", staging_dir)
    context.put("report_work_dir", staging_dir)
    context.put("skill_registry", SkillRegistry(root_dir / "backend" / "superpower" / "skills"))

    workflow_result = AgentOrchestrator(build_daily_workflow(), progress_callback=_emit_progress).run(context)
    audit_path = AuditLogger(log_dir).write(run_id, workflow_result.results)

    print(f"status={workflow_result.status}", flush=True)
    print(f"message={workflow_result.message}", flush=True)
    print(f"audit={audit_path}", flush=True)
    if workflow_result.status == "failed":
        raise SystemExit(1)

    staged_dashboard_path = Path(context.get("dashboard_json_path"))
    staged_report_path = Path(context.get("report_path"))
    staged_market_path = Path(context.get("market_indicators_json_path"))
    staged_audit_path = staging_dir / "audit.json"
    public_latest_dir = output_dir / "latest"
    public_dashboard_path = public_latest_dir / "dashboard.json"
    public_market_path = public_latest_dir / "market_indicators.json"
    public_audit_path = public_latest_dir / "audit.json"
    public_report_path = output_dir / staged_report_path.name

    if not args.skip_audit:
        _emit_phase("phase_started", 15, 16, "qa-audit", "Run independent report audit.", "Running QA audit")
        qa_result = _run_latest_audit(
            root_dir,
            args.etf_file,
            args.tl_file,
            cb_file,
            dashboard_path=staged_dashboard_path,
            audit_path=staged_audit_path,
        )
        _emit_phase("phase_finished", 15, 16, "qa-audit", "Run independent report audit.", qa_result["status"])
        print(f"qa_status={qa_result['status']}", flush=True)
        print(f"qa_report={public_audit_path}", flush=True)
        if context.maybe("dashboard_json_path"):
            _append_audit_warnings(Path(context.get("dashboard_json_path")), qa_result)
        if _audit_requires_exit(qa_result, args.strict_audit):
            raise SystemExit(1)
    else:
        atomic_write_text(
            staged_audit_path,
            json.dumps(
                {
                    "status": "SKIPPED",
                    "checks": [],
                    "source": {"dashboardPath": str(staged_dashboard_path)},
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    if context.maybe("dashboard_json_path"):
        _emit_phase("phase_started", 16, 16, "database-ingest", "Persist dashboard output into SQLite.", "Writing SQLite")
        ingest_result = ingest_dashboard(
            root_dir,
            run_id,
            staged_dashboard_path,
            published_dashboard_path=public_dashboard_path,
            published_report_path=public_report_path,
            published_market_indicators_path=public_market_path,
        )
        _emit_phase("phase_finished", 16, 16, "database-ingest", "Persist dashboard output into SQLite.", ingest_result["status"])
        print(f"db_status={ingest_result['status']}", flush=True)
        print(f"db_path={ingest_result['dbPath']}", flush=True)
        if ingest_result.get("backupPath"):
            print(f"db_backup={ingest_result['backupPath']}", flush=True)

    _publish_latest_snapshot(
        staged_dashboard_path=staged_dashboard_path,
        staged_report_path=staged_report_path,
        staged_market_path=staged_market_path,
        staged_audit_path=staged_audit_path,
        public_dashboard_path=public_dashboard_path,
        public_report_path=public_report_path,
        public_market_path=public_market_path,
        public_audit_path=public_audit_path,
    )
    shutil.rmtree(staging_dir, ignore_errors=True)
    context.put("dashboard_json_path", public_dashboard_path)
    context.put("report_path", public_report_path)
    context.put("market_indicators_json_path", public_market_path)
    print(f"report={public_report_path}", flush=True)
    print(f"dashboard_json={public_dashboard_path}", flush=True)


def _configured_cb_file(root_dir: Path) -> Path | None:
    sources_path = root_dir / "configs" / "data_sources.json"
    if not sources_path.exists():
        return None
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    cb_value = sources.get("convertible_bond_file")
    return _resolve_config_path(root_dir, Path(cb_value)) if cb_value else None


def _resolve_config_path(root_dir: Path, path: Path) -> Path:
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else root_dir / expanded


def _run_latest_audit(
    root_dir: Path,
    etf_file: Path,
    tl_file: Path,
    cb_file: Path | None,
    *,
    dashboard_path: Path,
    audit_path: Path,
) -> dict[str, object]:
    try:
        return audit_latest(
            root_dir,
            etf_file,
            tl_file,
            cb_file,
            dashboard_path=dashboard_path,
            audit_path=audit_path,
        )
    except Exception as exc:
        payload: dict[str, object] = {
            "status": "FAIL",
            "checks": [
                {
                    "name": "qa audit execution",
                    "status": "FAIL",
                    "detail": str(exc),
                }
            ],
            "source": {
                "etfFile": str(etf_file),
                "tlFile": str(tl_file),
                "cbFile": str(cb_file) if cb_file else "",
            },
        }
        atomic_write_text(audit_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return payload


def _append_audit_warnings(dashboard_path: Path, qa_result: dict[str, object]) -> None:
    if not dashboard_path.exists():
        return
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    run_info = dashboard.setdefault("run_info", {})
    warnings = run_info.setdefault("warnings", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    checks = qa_result.get("checks", [])
    failed_checks = [
        f"QA audit {check.get('status')}: {check.get('name')} - {check.get('detail')}"
        for check in checks
        if isinstance(check, dict) and str(check.get("status", "")).upper() != "PASS"
    ]
    if str(qa_result.get("status", "")).upper() != "PASS":
        warnings.append(f"QA audit status={qa_result.get('status')}")
        warnings.extend(failed_checks)
        run_info["status"] = "partial_success"
    run_info["warnings"] = warnings
    atomic_write_text(dashboard_path, json.dumps(dashboard, ensure_ascii=False, indent=2, default=str))


def _publish_latest_snapshot(
    *,
    staged_dashboard_path: Path,
    staged_report_path: Path,
    staged_market_path: Path,
    staged_audit_path: Path | None,
    public_dashboard_path: Path,
    public_report_path: Path,
    public_market_path: Path,
    public_audit_path: Path,
) -> None:
    """Publish a fully generated refresh; dashboard is switched last."""
    dashboard = json.loads(staged_dashboard_path.read_text(encoding="utf-8"))
    market_payload = json.loads(staged_market_path.read_text(encoding="utf-8"))
    if not isinstance(dashboard, dict) or not isinstance(market_payload, dict):
        raise ValueError("Refresh staging payload is not a JSON object")
    if staged_audit_path is not None:
        audit_payload = json.loads(staged_audit_path.read_text(encoding="utf-8"))
        if not isinstance(audit_payload, dict):
            raise ValueError("Refresh audit payload is not a JSON object")

    atomic_copy_file(staged_report_path, public_report_path)
    atomic_copy_file(staged_market_path, public_market_path)
    if staged_audit_path is not None:
        atomic_copy_file(staged_audit_path, public_audit_path)

    dashboard["reportPath"] = str(public_report_path)
    dashboard["marketIndicatorsPath"] = str(public_market_path)
    atomic_write_text(
        public_dashboard_path,
        json.dumps(dashboard, ensure_ascii=False, indent=2, default=str),
    )


def _audit_requires_exit(qa_result: dict[str, object], strict_audit: bool) -> bool:
    return bool(strict_audit and str(qa_result.get("status", "")).upper() != "PASS")


def _emit_progress(payload: dict[str, object]) -> None:
    print(f"progress_json={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}", flush=True)


def _emit_phase(event: str, index: int, total: int, agent: str, description: str, message: str) -> None:
    _emit_progress(
        {
            "event": event,
            "index": index,
            "total": total,
            "agent": agent,
            "agentDescription": description,
            "status": "running" if event.endswith("started") else "success",
            "message": message,
            "durationMs": None,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )


if __name__ == "__main__":
    main()
