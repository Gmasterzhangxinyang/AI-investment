from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMResult:
    used: bool
    provider: str
    model: str
    text: str
    reason: str


def generate_text(
    prompt: str,
    model_config: dict[str, Any],
    timeout_seconds: int = 60,
    developer_text: str | None = None,
) -> LLMResult:
    provider = model_config.get("provider", "openai")
    model = model_config.get("primary_model", "gpt-5.5")

    if not model_config.get("llm_enabled", False):
        return LLMResult(False, provider, model, "", "llm_enabled=false")
    if provider != "openai":
        return LLMResult(False, provider, model, "", f"unsupported provider: {provider}")

    _load_local_env()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return LLMResult(False, provider, model, "", "missing OPENAI_API_KEY")

    payload = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": developer_text or (
                            "你是机构投研系统里的解释型研究 Agent。"
                            "只能解释用户给定的确定性信号，不得新增标的、改写信号、承诺收益或给出未经表格支持的结论。"
                            "输出中文，专业、克制、可审计。"
                            "禁止使用 Markdown，不要使用 #、**、表格、分割线、项目符号。"
                            "请使用商务纯文本段落，必要时用“1. 2. 3.”编号。"
                        ),
                    }
                ],
            },
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return LLMResult(False, provider, model, "", f"OpenAI HTTP {exc.code}: {detail[:240]}")
    except Exception as exc:
        return LLMResult(False, provider, model, "", f"OpenAI request failed: {exc}")

    text = _extract_text(body).strip()
    if not text:
        return LLMResult(False, provider, model, "", "OpenAI response contained no text")
    return LLMResult(True, provider, model, text, "ok")


def _extract_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def _load_local_env() -> None:
    """Load project .env values without overriding real environment variables."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
