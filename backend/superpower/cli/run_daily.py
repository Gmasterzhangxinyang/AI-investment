from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from superpower.agents import build_daily_workflow
from superpower.audit.latest import audit_latest
from superpower.db import ingest_dashboard
from superpower.runtime import AgentContext, AgentOrchestrator, SkillRegistry
from superpower.runtime.audit_logger import AuditLogger


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
    context.put("skill_registry", SkillRegistry(root_dir / "backend" / "superpower" / "skills"))

    workflow_result = AgentOrchestrator(build_daily_workflow(), progress_callback=_emit_progress).run(context)
    audit_path = AuditLogger(log_dir).write(run_id, workflow_result.results)

    print(f"status={workflow_result.status}", flush=True)
    print(f"message={workflow_result.message}", flush=True)
    print(f"audit={audit_path}", flush=True)
    if context.maybe("report_path"):
        print(f"report={context.get('report_path')}", flush=True)
    if context.maybe("dashboard_json_path"):
        print(f"dashboard_json={context.get('dashboard_json_path')}", flush=True)

    if workflow_result.status == "failed":
        raise SystemExit(1)

    if not args.skip_audit:
        _emit_phase("phase_started", 15, 16, "qa-audit", "Run independent report audit.", "Running QA audit")
        qa_result = audit_latest(root_dir, args.etf_file, args.tl_file, cb_file)
        _emit_phase("phase_finished", 15, 16, "qa-audit", "Run independent report audit.", qa_result["status"])
        print(f"qa_status={qa_result['status']}", flush=True)
        print(f"qa_report={root_dir / 'outputs' / 'latest' / 'audit.json'}", flush=True)
        if qa_result["status"] != "PASS":
            raise SystemExit(1)

    if context.maybe("dashboard_json_path"):
        _emit_phase("phase_started", 16, 16, "database-ingest", "Persist dashboard output into SQLite.", "Writing SQLite")
        ingest_result = ingest_dashboard(root_dir, run_id, Path(context.get("dashboard_json_path")))
        _emit_phase("phase_finished", 16, 16, "database-ingest", "Persist dashboard output into SQLite.", ingest_result["status"])
        print(f"db_status={ingest_result['status']}", flush=True)
        print(f"db_path={ingest_result['dbPath']}", flush=True)
        if ingest_result.get("backupPath"):
            print(f"db_backup={ingest_result['backupPath']}", flush=True)


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
