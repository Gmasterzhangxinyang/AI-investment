from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentContext:
    """Shared blackboard for one workflow run.

    Agents communicate through named artifacts instead of calling each other
    directly. This keeps each Agent replaceable and makes the run auditable.
    """

    run_id: str
    root_dir: Path
    artifacts: dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def get(self, key: str) -> Any:
        if key not in self.artifacts:
            raise KeyError(f"Missing context artifact: {key}")
        return self.artifacts[key]

    def maybe(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def require_all(self, keys: list[str]) -> None:
        missing = [key for key in keys if key not in self.artifacts]
        if missing:
            raise KeyError(f"Missing required context artifacts: {missing}")

