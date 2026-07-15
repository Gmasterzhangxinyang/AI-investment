from __future__ import annotations

import json
from pathlib import Path

from superpower.db.connection import get_connection
from superpower.db.migrations import ensure_database
from superpower.runtime.artifact_store import atomic_write_text

from .schemas import ChatTrace


class ChatTraceStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def save(self, trace: ChatTrace) -> Path:
        trace_dir = self.root_dir / "outputs" / "latest" / "chat_traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / f"{trace.run_id}.json"
        content = json.dumps(trace.to_dict(), ensure_ascii=False, indent=2)
        atomic_write_text(path, content)
        latest_path = trace_dir / "latest.json"
        atomic_write_text(latest_path, content)
        self._save_to_database(trace)
        return path

    def _save_to_database(self, trace: ChatTrace) -> None:
        try:
            ensure_database(self.root_dir)
            payload = trace.to_dict()
            guardrail_passed = 1 if trace.guardrail and trace.guardrail.passed else 0
            answer = trace.guardrail.text if trace.guardrail else ""
            with get_connection(self.root_dir) as connection:
                connection.execute(
                    """
                    INSERT INTO chat_traces(
                      trace_id, run_id, session_id, user_id, question, intent, answer,
                      guardrail_passed, llm_used, llm_model, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trace_id) DO UPDATE SET
                      answer=excluded.answer,
                      guardrail_passed=excluded.guardrail_passed,
                      llm_used=excluded.llm_used,
                      llm_model=excluded.llm_model,
                      payload_json=excluded.payload_json
                    """,
                    (
                        trace.run_id,
                        trace.run_id,
                        trace.session_id,
                        trace.user_id,
                        trace.question,
                        trace.intent.name,
                        answer,
                        guardrail_passed,
                        1 if trace.llm_used else 0,
                        trace.llm_model,
                        json.dumps(payload, ensure_ascii=False, indent=2),
                    ),
                )
        except Exception:
            return
