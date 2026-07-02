from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any

from .context import AgentContext
from .result import AgentResult, AgentStatus


class BaseAgent:
    """Base class for all production Agents."""

    name = "base-agent"
    description = "Base Agent"
    spec = None

    def run(self, context: AgentContext) -> AgentResult:
        started_at_dt = datetime.now()
        started = perf_counter()
        status: AgentStatus
        try:
            spec = self.agent_spec()
            context.require_all(list(spec.required_artifacts))
            message, metrics, artifacts, status = self.execute(context)
            missing_outputs = [key for key in spec.produced_artifacts if key not in context.artifacts]
            if missing_outputs:
                raise KeyError(f"{self.name} did not produce expected artifacts: {missing_outputs}")
            metrics = self._with_contract_metrics(metrics)
            error = ""
        except Exception as exc:
            message = str(exc)
            metrics = self._with_contract_metrics({})
            artifacts = {}
            status = "failed"
            error = traceback.format_exc(limit=8)

        finished_at_dt = datetime.now()
        return AgentResult(
            agent_name=self.name,
            status=status,
            message=message,
            started_at=started_at_dt.strftime("%Y-%m-%d %H:%M:%S"),
            finished_at=finished_at_dt.strftime("%Y-%m-%d %H:%M:%S"),
            duration_ms=int((perf_counter() - started) * 1000),
            metrics=metrics,
            artifacts=artifacts,
            error=error,
        )

    def execute(
        self,
        context: AgentContext,
    ) -> tuple[str, dict[str, Any], dict[str, str], AgentStatus]:
        raise NotImplementedError

    def agent_spec(self) -> "AgentSpec":
        if isinstance(self.spec, AgentSpec):
            return self.spec
        return AgentSpec(
            role=self.description,
            objective=self.description,
        )

    def _with_contract_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        spec = self.agent_spec()
        contract = {
            "role": spec.role,
            "objective": spec.objective,
            "skill": spec.skill_name or "custom",
            "inputs": ", ".join(spec.required_artifacts) or "none",
            "outputs": ", ".join(spec.produced_artifacts) or "none",
            "quality_gates": " | ".join(spec.quality_gates) or "none",
            "decision_policy": spec.decision_policy,
        }
        return {**contract, **metrics}


@dataclass(frozen=True)
class AgentSpec:
    role: str
    objective: str
    skill_name: str | None = None
    required_artifacts: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    quality_gates: tuple[str, ...] = ()
    decision_policy: str = "Deterministic; no LLM can alter signal tables."


class SkillBackedAgent(BaseAgent):
    success_message = "Agent completed."
    warning_metric: str | None = None
    warning_threshold = 0

    def execute(self, context: AgentContext) -> tuple[str, dict[str, Any], dict[str, str], AgentStatus]:
        spec = self.agent_spec()
        if not spec.skill_name:
            raise ValueError(f"{self.name} is missing skill_name in AgentSpec.")
        metrics = context.get("skill_registry").run(spec.skill_name, context)
        status = self.evaluate_status(metrics, context)
        return self.success_message, metrics, self.collect_artifacts(context), status

    def evaluate_status(self, metrics: dict[str, Any], context: AgentContext) -> AgentStatus:
        if self.warning_metric and metrics.get(self.warning_metric, 0) > self.warning_threshold:
            return "warning"
        return "success"

    def collect_artifacts(self, context: AgentContext) -> dict[str, str]:
        return {}
