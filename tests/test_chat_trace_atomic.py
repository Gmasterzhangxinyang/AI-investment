from __future__ import annotations

import json
from pathlib import Path

from superpower.chat import trace as trace_module
from superpower.chat.schemas import ChatIntent, ChatRequest, ChatTrace
from superpower.chat.trace import ChatTraceStore


def test_chat_trace_store_publishes_trace_and_latest_atomically(tmp_path: Path, monkeypatch) -> None:
    request = ChatRequest(question="黄金ETF收盘价")
    trace = ChatTrace.start(request, ChatIntent(name="etf_detail", confidence=1.0))
    writes: list[tuple[Path, str]] = []

    def capture_atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
        writes.append((path, content))
        return path

    monkeypatch.setattr(trace_module, "atomic_write_text", capture_atomic_write)
    monkeypatch.setattr(ChatTraceStore, "_save_to_database", lambda self, saved_trace: None)

    saved_path = ChatTraceStore(tmp_path).save(trace)

    assert saved_path.name == f"{trace.run_id}.json"
    assert [path.name for path, _ in writes] == [f"{trace.run_id}.json", "latest.json"]
    assert writes[0][1] == writes[1][1]
    assert json.loads(writes[0][1])["question"] == "黄金ETF收盘价"
