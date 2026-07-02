from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentStatus = Literal["success", "warning", "failed", "skipped"]


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    status: AgentStatus
    message: str
    started_at: str
    finished_at: str
    duration_ms: int
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class WorkflowResult:
    run_id: str
    status: AgentStatus
    message: str
    results: list[AgentResult]
    artifacts: dict[str, str] = field(default_factory=dict)

