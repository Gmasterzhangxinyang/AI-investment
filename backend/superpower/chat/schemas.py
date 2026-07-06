from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ChatRequest:
    question: str
    session_id: str = "default"
    user_id: str = "local-user"
    short_term_memory: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatIntent:
    name: str
    confidence: float
    entities: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStep:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class ToolResult:
    tool: str
    title: str
    source: str
    summary: str
    data: Any


@dataclass(frozen=True)
class EvidencePack:
    report_date: str
    intent: ChatIntent
    rulebook: list[str]
    tools: list[ToolResult]
    memory_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuardrailResult:
    passed: bool
    issues: list[str]
    text: str


@dataclass
class ChatTrace:
    run_id: str
    question: str
    session_id: str
    user_id: str
    intent: ChatIntent
    started_at: str
    steps: list[AgentStep] = field(default_factory=list)
    tools: list[ToolResult] = field(default_factory=list)
    llm_used: bool = False
    llm_model: str = ""
    llm_reason: str = ""
    guardrail: GuardrailResult | None = None

    @classmethod
    def start(cls, request: ChatRequest, intent: ChatIntent) -> "ChatTrace":
        return cls(
            run_id=uuid4().hex,
            question=request.question,
            session_id=request.session_id,
            user_id=request.user_id,
            intent=intent,
            started_at=datetime.now().isoformat(timespec="seconds"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatResponse:
    answer: str
    intent: ChatIntent
    steps: list[AgentStep]
    evidence: list[ToolResult]
    guardrail: GuardrailResult
    trace_id: str
    llm_used: bool
    llm_provider: str
    llm_model: str
    llm_reason: str

    def to_payload(self) -> dict[str, Any]:
        public_evidence = [
            {
                "tool": item.tool,
                "title": item.title,
                "source": item.source,
                "summary": item.summary,
            }
            for item in self.evidence
        ]
        return {
            "status": "success",
            "answer": self.answer,
            "intent": asdict(self.intent),
            "steps": [asdict(step) for step in self.steps],
            "evidence": public_evidence,
            "guardrail": asdict(self.guardrail),
            "traceId": self.trace_id,
            "llmUsed": self.llm_used,
            "llmProvider": self.llm_provider,
            "llmModel": self.llm_model,
            "llmReason": self.llm_reason,
            "sources": [item["source"] for item in public_evidence],
        }
