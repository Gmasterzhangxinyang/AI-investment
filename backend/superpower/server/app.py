from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from uuid import uuid4

from superpower.chat import ChatOrchestrator
from superpower.chat.schemas import ChatRequest
from superpower.db import DatabaseRepository
from superpower.skills.ai_research_committee.handler import COMMITTEE_LLM_TIMEOUT_SECONDS, COMMITTEE_ROLES
from superpower.tools.llm import generate_text
from superpower.tools.pdf_report import write_research_pdf
from superpower.tools.text_cleaner import clean_llm_text


class ResearchDashboardHandler(SimpleHTTPRequestHandler):
    root_dir: Path
    etf_file: Path
    tl_file: Path
    cb_file: Path | None
    chat_orchestrator: ChatOrchestrator | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(self.root_dir), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/config"):
            self._send_json(
                {
                    "etfFile": str(self.etf_file),
                    "tlFile": str(self.tl_file),
                    "cbFile": str(self.cb_file) if self.cb_file else "",
                    "etfFileExists": self.etf_file.exists(),
                    "tlFileExists": self.tl_file.exists(),
                    "cbFileExists": self.cb_file.exists() if self.cb_file else False,
                }
            )
            return
        if path.startswith("/api/db/status"):
            self._send_json(DatabaseRepository(self.root_dir).status())
            return
        if path.startswith("/api/refresh/job/"):
            job_id = path.rsplit("/", 1)[-1]
            job = DatabaseRepository(self.root_dir).get_refresh_job(job_id)
            if not job:
                self._send_json({"status": "failed", "message": "Refresh job not found."}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json({"status": "success", "job": job})
            return
        if path.startswith("/api/refresh/latest"):
            self._send_json({"status": "success", "job": DatabaseRepository(self.root_dir).latest_refresh_job()})
            return
        if path.startswith("/api/strategy-params"):
            self._send_json({"status": "success", "params": self._load_strategy_params()})
            return
        if path.startswith("/api/assets/detail"):
            query = parse_qs(parsed.query)
            code = (query.get("code") or [""])[0].strip()
            if not code:
                self._send_json({"status": "failed", "message": "Missing code."}, status=HTTPStatus.BAD_REQUEST)
                return
            detail = DatabaseRepository(self.root_dir).asset_detail(code)
            self._send_json({"status": "success", "detail": detail})
            return
        if path.startswith("/api/assets"):
            query = parse_qs(parsed.query)
            asset_type = (query.get("type") or [None])[0]
            assets = DatabaseRepository(self.root_dir).list_assets(asset_type)
            self._send_json({"status": "success", "assets": assets})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/refresh"):
            self._start_refresh()
            return
        if path.startswith("/api/strategy-params"):
            self._save_strategy_params()
            return
        if path.startswith("/api/export-pdf"):
            self._export_pdf()
            return
        if path.startswith("/api/deep-review"):
            self._deep_review()
            return
        if path.startswith("/api/chat"):
            self._chat()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _start_refresh(self) -> None:
        if not self.etf_file.exists() or not self.tl_file.exists():
            self._send_json(
                {
                    "status": "failed",
                    "message": "Configured source Excel files are missing.",
                    "etfFile": str(self.etf_file),
                    "tlFile": str(self.tl_file),
                    "etfFileExists": self.etf_file.exists(),
                    "tlFileExists": self.tl_file.exists(),
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        repository = DatabaseRepository(self.root_dir)
        latest = repository.latest_refresh_job()
        if _job_is_active(latest):
            self._send_json({"status": "accepted", "job": latest, "message": "Refresh already running."}, status=HTTPStatus.ACCEPTED)
            return

        command = [
            sys.executable,
            str(self.root_dir / "run_daily.py"),
            "--etf-file",
            str(self.etf_file),
            "--tl-file",
            str(self.tl_file),
            "--root-dir",
            str(self.root_dir),
        ]
        if self.cb_file is not None:
            command.extend(["--cb-file", str(self.cb_file)])

        job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
        job = repository.create_refresh_job(job_id, command)
        worker = Thread(target=self._run_refresh_job, args=(job_id, command), daemon=True)
        worker.start()
        self._send_json({"status": "accepted", "job": job}, status=HTTPStatus.ACCEPTED)

    def _run_refresh_job(self, job_id: str, command: list[str]) -> None:
        repository = DatabaseRepository(self.root_dir)
        progress_events: list[dict[str, Any]] = []
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        repository.update_refresh_job(
            job_id,
            status="running",
            message="Refresh running",
            started_at=datetime.now().isoformat(timespec="seconds"),
            payload_json=json.dumps({"phase": "running", "progressEvents": []}, ensure_ascii=False),
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=self.root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            stream_queue: queue.Queue[tuple[str, str]] = queue.Queue()
            stdout_thread = Thread(target=_read_process_stream, args=("stdout", process.stdout, stream_queue), daemon=True)
            stderr_thread = Thread(target=_read_process_stream, args=("stderr", process.stderr, stream_queue), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            deadline = monotonic() + 1800
            while True:
                if monotonic() > deadline and process.poll() is None:
                    process.kill()
                    raise subprocess.TimeoutExpired(command, 1800)

                try:
                    stream_name, line = stream_queue.get(timeout=0.5)
                except queue.Empty:
                    if process.poll() is not None and stream_queue.empty():
                        break
                    continue

                if stream_name == "stdout":
                    stdout_lines.append(line)
                    progress = _progress_from_stdout_line(line)
                    if progress:
                        progress_events.append(progress)
                        repository.update_refresh_job(
                            job_id,
                            status="running",
                            message=_progress_message(progress),
                            stdout_tail="".join(stdout_lines)[-12000:],
                            stderr_tail="".join(stderr_lines)[-12000:],
                            payload_json=json.dumps(
                                {
                                    "phase": "running",
                                    "lastProgress": progress,
                                    "progressEvents": progress_events[-80:],
                                },
                                ensure_ascii=False,
                            ),
                        )
                else:
                    stderr_lines.append(line)

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            return_code = process.wait(timeout=5)
            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)
            status = "success" if return_code == 0 else "failed"
            audit_path = _parse_cli_line(stdout, "audit=")
            payload = {
                "phase": "completed" if status == "success" else "failed",
                "lastProgress": progress_events[-1] if progress_events else None,
                "progressEvents": progress_events[-80:],
                "stdout": stdout[-12000:],
                "stderr": stderr[-12000:],
            }
            repository.update_refresh_job(
                job_id,
                status=status,
                message="Refresh completed" if status == "success" else "Refresh failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                return_code=return_code,
                stdout_tail=stdout[-12000:],
                stderr_tail=stderr[-12000:],
                dashboard_path=_parse_cli_line(stdout, "dashboard_json=") or str(self.root_dir / "outputs" / "latest" / "dashboard.json"),
                audit_path=_parse_cli_line(stdout, "qa_report=") or str(self.root_dir / "outputs" / "latest" / "audit.json"),
                run_id=_run_id_from_audit_path(audit_path),
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        except subprocess.TimeoutExpired as exc:
            repository.update_refresh_job(
                job_id,
                status="failed",
                message="Refresh timed out after 1800 seconds",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                stdout_tail="".join(stdout_lines)[-12000:],
                stderr_tail="".join(stderr_lines)[-12000:],
                payload_json=json.dumps(
                    {
                        "phase": "failed",
                        "timeout": 1800,
                        "lastProgress": progress_events[-1] if progress_events else None,
                        "progressEvents": progress_events[-80:],
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            repository.update_refresh_job(
                job_id,
                status="failed",
                message=str(exc),
                finished_at=datetime.now().isoformat(timespec="seconds"),
                stdout_tail="".join(stdout_lines)[-12000:],
                stderr_tail="".join(stderr_lines)[-12000:],
                payload_json=json.dumps(
                    {
                        "phase": "failed",
                        "error": str(exc),
                        "lastProgress": progress_events[-1] if progress_events else None,
                        "progressEvents": progress_events[-80:],
                    },
                    ensure_ascii=False,
                ),
            )

    def _export_pdf(self) -> None:
        dashboard_path = self.root_dir / "outputs" / "latest" / "dashboard.json"
        if not dashboard_path.exists():
            self._send_json(
                {
                    "status": "failed",
                    "message": "Missing latest dashboard data. Please refresh data first.",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
            pdf_path = write_research_pdf(self.root_dir, dashboard)
        except Exception as exc:
            self._send_json(
                {
                    "status": "failed",
                    "message": str(exc),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json(
            {
                "status": "success",
                "pdfPath": str(pdf_path),
                "pdfUrl": f"/outputs/{quote(pdf_path.name)}",
            }
        )

    def _deep_review(self) -> None:
        dashboard_path = self.root_dir / "outputs" / "latest" / "dashboard.json"
        if not dashboard_path.exists():
            self._send_json(
                {"status": "failed", "message": "Missing latest dashboard data. Please refresh data first."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
            model_config = self._load_model_config()
            payload = _deep_review_payload(dashboard)
            reviews = []
            for role in COMMITTEE_ROLES:
                prompt = _deep_review_prompt(role, payload)
                result = generate_text(
                    prompt,
                    model_config,
                    timeout_seconds=COMMITTEE_LLM_TIMEOUT_SECONDS,
                    developer_text=role["developer"],
                )
                reviews.append(
                    {
                        "role": role["role"],
                        "title": role["title"],
                        "llm_used": result.used,
                        "provider": result.provider,
                        "model": result.model,
                        "reason": result.reason,
                        "review": clean_llm_text(result.text if result.used else _deep_review_fallback(role, payload)),
                    }
                )
            output_path = self.root_dir / "outputs" / "latest" / "deep_review.json"
            output_path.write_text(json.dumps({"reviews": reviews}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            self._send_json({"status": "failed", "message": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"status": "success", "reviews": reviews})

    def _chat(self) -> None:
        try:
            payload = self._read_json_body()
            question = str(payload.get("question", "")).strip()
            session_id = str(payload.get("sessionId", "default")).strip() or "default"
            user_id = str(payload.get("userId", "local-user")).strip() or "local-user"
        except Exception:
            self._send_json({"status": "failed", "message": "Invalid JSON body."}, status=HTTPStatus.BAD_REQUEST)
            return

        if not question:
            self._send_json({"status": "failed", "message": "Missing question."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            orchestrator = self.chat_orchestrator or ChatOrchestrator(self.root_dir)
            response = orchestrator.run(ChatRequest(question=question, session_id=session_id, user_id=user_id))
        except FileNotFoundError as exc:
            self._send_json({"status": "failed", "message": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"status": "failed", "message": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(response.to_payload())

    def _load_strategy_params(self) -> dict[str, Any]:
        path = self.root_dir / "configs" / "strategy_params.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_model_config(self) -> dict[str, Any]:
        path = self.root_dir / "configs" / "model_config.json"
        if not path.exists():
            return {"provider": "openai", "primary_model": "gpt-5.5", "llm_enabled": False}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_strategy_params(self) -> None:
        try:
            payload = self._read_json_body()
            params = payload.get("params", payload)
            if not isinstance(params, dict):
                raise ValueError("Strategy params must be a JSON object.")
            _validate_strategy_params(params)
            path = self.root_dir / "configs" / "strategy_params.json"
            tmp_path = path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp_path.replace(path)
        except Exception as exc:
            self._send_json({"status": "failed", "message": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"status": "success", "params": params})

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body or "{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Superpower research dashboard server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root-dir", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--etf-file", type=Path, default=None)
    parser.add_argument("--tl-file", type=Path, default=None)
    args = parser.parse_args()

    root_dir = args.root_dir.resolve()
    sources = load_data_sources(root_dir)
    etf_file = _resolve_config_path(root_dir, args.etf_file or Path(sources["etf_file"]))
    tl_file = _resolve_config_path(root_dir, args.tl_file or Path(sources["tl_file"]))
    cb_file = _resolve_config_path(root_dir, Path(sources["convertible_bond_file"])) if sources.get("convertible_bond_file") else None

    handler = type(
        "ConfiguredResearchDashboardHandler",
        (ResearchDashboardHandler,),
        {
            "root_dir": root_dir,
            "etf_file": etf_file,
            "tl_file": tl_file,
            "cb_file": cb_file,
            "chat_orchestrator": ChatOrchestrator(root_dir),
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"server=http://{args.host}:{args.port}/frontend/")
    print(f"refresh_endpoint=http://{args.host}:{args.port}/api/refresh")
    print(f"etf_file={etf_file}")
    print(f"tl_file={tl_file}")
    print(f"cb_file={cb_file}")
    server.serve_forever()


def load_data_sources(root_dir: Path) -> dict[str, str]:
    path = root_dir / "configs" / "data_sources.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing data source config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_config_path(root_dir: Path, path: Path) -> Path:
    expanded = path.expanduser()
    return expanded.resolve() if expanded.is_absolute() else (root_dir / expanded).resolve()


def _deep_review_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": dashboard.get("summary", []),
        "data_quality": dashboard.get("dataQuality", [])[:30],
        "etf_buy_candidates": dashboard.get("etfBuyCandidates", [])[:8],
        "etf_watchlist": dashboard.get("etfWatchlist", [])[:8],
        "etf_sell_alerts": dashboard.get("etfSellAlerts", [])[:8],
        "tl_today": dashboard.get("tlToday", [])[:1],
        "convertible_bond_top10": dashboard.get("cbTop10", [])[:10],
        "backtest_summary": dashboard.get("backtestSummary", [])[:12],
        "risk_summary": dashboard.get("riskSummary", [])[:12],
        "hard_boundaries": [
            "不得改变任何 buy_signal、sell_signal、TL state、score、rank 或 risk level",
            "不得新增表格中不存在的标的",
            "不得承诺收益",
            "短样本只能称为历史诊断，不能作为收益结论",
        ],
    }


def _deep_review_prompt(role: dict[str, str], payload: dict[str, Any]) -> str:
    return (
        f"你的角色：{role['title']}。\n"
        f"复核重点：{role['focus']}\n"
        "请严格基于下面 JSON 数据输出中文复核意见，最多 6 条，必须引用具体证据项或数量。\n"
        "输出格式要求：纯文本；不要 Markdown；不要标题符号；不要粗体；不要表格；不要分割线；可以用 1. 2. 3. 编号。\n\n"
        f"{payload}"
    )


def _deep_review_fallback(role: dict[str, str], payload: dict[str, Any]) -> str:
    data_quality = payload.get("data_quality", [])
    etf_buys = payload.get("etf_buy_candidates", [])
    etf_watch = payload.get("etf_watchlist", [])
    etf_sells = payload.get("etf_sell_alerts", [])
    cb_top10 = payload.get("convertible_bond_top10", [])
    tl_today = payload.get("tl_today", [])
    backtest = payload.get("backtest_summary", [])
    warn_count = sum(1 for row in data_quality if row.get("status") == "WARN")
    tl_state = tl_today[0].get("state", "--") if tl_today else "--"
    if role["role"] == "DataQAAnalyst":
        return f"深度复核未完成模型调用，使用规则摘要：系统已识别风险项 {warn_count} 项，需在报告中按规则风险而非系统异常披露。"
    if role["role"] == "StrategyReviewer":
        return f"深度复核未完成模型调用，使用规则摘要：ETF建仓 {len(etf_buys)} 个、关注 {len(etf_watch)} 个、平仓 {len(etf_sells)} 个；TL状态为{tl_state}。"
    if role["role"] == "RiskReviewer":
        backtest_warns = sum(1 for row in backtest if row.get("level") == "WARN")
        return f"深度复核未完成模型调用，使用规则摘要：回测诊断 WARN {backtest_warns} 项，可转债Top10 {len(cb_top10)} 个。"
    return f"深度复核未完成模型调用，使用规则摘要：今日 ETF建仓 {len(etf_buys)}、关注 {len(etf_watch)}、平仓 {len(etf_sells)}，TL为{tl_state}，可转债Top10为{len(cb_top10)}。"


def _parse_cli_line(stdout: str, prefix: str) -> str:
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _read_process_stream(stream_name: str, stream: Any, stream_queue: queue.Queue[tuple[str, str]]) -> None:
    if stream is None:
        return
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            stream_queue.put((stream_name, line))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _progress_from_stdout_line(line: str) -> dict[str, Any] | None:
    prefix = "progress_json="
    if not line.startswith(prefix):
        return None
    try:
        payload = json.loads(line[len(prefix) :].strip())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _progress_message(progress: dict[str, Any]) -> str:
    index = progress.get("index", "?")
    total = progress.get("total", "?")
    agent = progress.get("agent") or "workflow"
    event = progress.get("event") or "running"
    status = progress.get("status") or "running"
    if event == "agent_started":
        return f"Agent {index}/{total} running: {agent}"
    if event == "agent_finished":
        return f"Agent {index}/{total} {status}: {agent}"
    if event == "phase_started":
        return f"Phase {index}/{total} running: {agent}"
    if event == "phase_finished":
        return f"Phase {index}/{total} {status}: {agent}"
    if event == "workflow_completed":
        return "Workflow completed"
    if event == "workflow_failed":
        return f"Workflow failed at Agent {index}/{total}: {agent}"
    return f"Agent {index}/{total}: {agent}"


def _run_id_from_audit_path(audit_path: str) -> str:
    if not audit_path:
        return ""
    stem = Path(audit_path).stem
    return stem.removeprefix("agent_audit_")


def _job_is_active(job: dict[str, Any] | None) -> bool:
    if not job or job.get("status") not in {"queued", "running"}:
        return False
    updated_at = str(job.get("updated_at") or job.get("created_at") or "")
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    return datetime.now() - updated < timedelta(hours=2)


def _validate_strategy_params(params: dict[str, Any]) -> None:
    required = {"etf", "tl", "convertible_bond", "risk"}
    missing = required - set(params)
    if missing:
        raise ValueError(f"Missing strategy sections: {sorted(missing)}")
    etf = params.get("etf", {})
    cb = params.get("convertible_bond", {})
    for section_name, section in [("etf", etf), ("convertible_bond", cb)]:
        if not isinstance(section, dict):
            raise ValueError(f"{section_name} must be an object.")
    if float(etf.get("buy_volume_ratio_min", 0)) <= 0:
        raise ValueError("ETF buy_volume_ratio_min must be positive.")
    if float(cb.get("min_price", 0)) >= float(cb.get("price_limit", 0)):
        raise ValueError("Convertible bond min_price must be below price_limit.")
