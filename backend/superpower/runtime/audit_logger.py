from __future__ import annotations

import json
from pathlib import Path

from .result import AgentResult


class AuditLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write(self, run_id: str, results: list[AgentResult]) -> Path:
        path = self.log_dir / f"agent_audit_{run_id}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for result in results:
                f.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")
        return path

