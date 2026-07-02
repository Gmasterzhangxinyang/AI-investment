from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from .agent import BaseAgent
from .context import AgentContext
from .result import AgentResult, WorkflowResult

ProgressCallback = Callable[[dict[str, Any]], None]


class AgentOrchestrator:
    """Deterministic workflow orchestrator.

    First release runs Agents sequentially. The interface is intentionally
    compatible with future DAG/parallel execution after QA and indicators pass.
    """

    def __init__(self, agents: list[BaseAgent], progress_callback: ProgressCallback | None = None) -> None:
        self.agents = agents
        self.progress_callback = progress_callback

    def run(self, context: AgentContext) -> WorkflowResult:
        results: list[AgentResult] = []
        total = len(self.agents)
        for index, agent in enumerate(self.agents, start=1):
            context.put("agent_results", results.copy())
            self._emit_progress("agent_started", index, total, agent)
            result = agent.run(context)
            results.append(result)
            self._emit_progress("agent_finished", index, total, agent, result)
            if result.status == "failed":
                context.put("agent_results", results)
                self._emit_progress("workflow_failed", index, total, agent, result)
                return WorkflowResult(
                    run_id=context.run_id,
                    status="failed",
                    message=f"Workflow stopped at {result.agent_name}: {result.message}",
                    results=results,
                )

        context.put("agent_results", results)
        self._emit_progress("workflow_completed", total, total, self.agents[-1] if self.agents else None)
        return WorkflowResult(
            run_id=context.run_id,
            status="success",
            message="Workflow completed",
            results=results,
            artifacts={
                key: str(value)
                for key, value in context.artifacts.items()
                if key.endswith("_path")
            },
        )

    def _emit_progress(
        self,
        event: str,
        index: int,
        total: int,
        agent: BaseAgent | None,
        result: AgentResult | None = None,
    ) -> None:
        if self.progress_callback is None:
            return
        payload: dict[str, Any] = {
            "event": event,
            "index": index,
            "total": total,
            "agent": agent.name if agent is not None else "",
            "agentDescription": agent.description if agent is not None else "",
            "status": result.status if result is not None else "running",
            "message": result.message if result is not None else "Running",
            "durationMs": result.duration_ms if result is not None else None,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.progress_callback(payload)
