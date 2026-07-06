from __future__ import annotations

import base64
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
    provider = str(model_config.get("provider", "openai")).strip().lower()
    model = str(model_config.get("primary_model", "gpt-5.5")).strip() or "gpt-5.5"

    if not model_config.get("llm_enabled", False):
        return LLMResult(False, provider, model, "", "llm_enabled=false")
    if provider == "openai":
        return _generate_openai_text(prompt, model_config, timeout_seconds, developer_text, provider, model)
    if provider == "opencode":
        return _generate_opencode_text(prompt, model_config, timeout_seconds, developer_text, provider, model)
    return LLMResult(False, provider, model, "", f"unsupported provider: {provider}")


def _generate_openai_text(
    prompt: str,
    model_config: dict[str, Any],
    timeout_seconds: int,
    developer_text: str | None,
    provider: str,
    model: str,
) -> LLMResult:
    _load_local_env()
    api_key = _config_secret(model_config, "api_key", "api_key_env", "OPENAI_API_KEY")
    if not api_key:
        return LLMResult(False, provider, model, "", "missing OPENAI_API_KEY")

    payload = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": developer_text or _default_developer_text()}],
            },
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        body = _send_json(request, timeout_seconds)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return LLMResult(False, provider, model, "", f"OpenAI HTTP {exc.code}: {detail[:240]}")
    except Exception as exc:
        return LLMResult(False, provider, model, "", f"OpenAI request failed: {exc}")

    text = _extract_openai_text(body).strip()
    if not text:
        return LLMResult(False, provider, model, "", "OpenAI response contained no text")
    return LLMResult(True, provider, model, text, "ok")


def _generate_opencode_text(
    prompt: str,
    model_config: dict[str, Any],
    timeout_seconds: int,
    developer_text: str | None,
    provider: str,
    model: str,
) -> LLMResult:
    _load_local_env()
    opencode_config = model_config.get("opencode") if isinstance(model_config.get("opencode"), dict) else {}
    base_url = str(opencode_config.get("base_url") or os.environ.get("OPENCODE_BASE_URL") or "http://127.0.0.1:4096").rstrip("/")
    headers = _opencode_headers(opencode_config)

    try:
        session_id = str(opencode_config.get("session_id") or "").strip()
        if not session_id:
            session = _opencode_post(
                f"{base_url}/session",
                {"title": str(opencode_config.get("session_title") or "AI 投研问答")},
                headers,
                timeout_seconds,
            )
            session_id = str(session.get("id") or session.get("sessionID") or session.get("session_id") or "").strip()
        if not session_id:
            return LLMResult(False, provider, model, "", "OpenCode session response contained no id")

        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": prompt}],
            "system": developer_text or _default_developer_text(),
            "tools": _opencode_tool_policy(opencode_config),
        }
        model_payload = _opencode_model_payload(opencode_config, model)
        if model_payload:
            body["model"] = model_payload
        agent = str(opencode_config.get("agent") or "").strip()
        if agent:
            body["agent"] = agent

        message = _opencode_post(f"{base_url}/session/{session_id}/message", body, headers, timeout_seconds)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return LLMResult(False, provider, model, "", f"OpenCode HTTP {exc.code}: {detail[:240]}")
    except Exception as exc:
        return LLMResult(False, provider, model, "", f"OpenCode request failed: {exc}")

    text = _extract_opencode_text(message).strip()
    if not text:
        return LLMResult(False, provider, model, "", "OpenCode response contained no text")
    return LLMResult(True, provider, model, text, "ok")


def _opencode_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = _config_secret(config, "api_key", "api_key_env", "OPENCODE_API_KEY")
    if token:
        scheme = str(config.get("auth_scheme") or "bearer").strip().lower()
        headers["Authorization"] = f"Basic {token}" if scheme == "basic-token" else f"Bearer {token}"
    password = _config_secret(config, "server_password", "server_password_env", "OPENCODE_SERVER_PASSWORD")
    if password:
        username = str(config.get("server_username") or os.environ.get("OPENCODE_SERVER_USERNAME") or "opencode")
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    return headers


def _opencode_model_payload(config: dict[str, Any], default_model: str) -> Any:
    configured_model = config.get("model")
    if configured_model:
        return configured_model
    provider_id = str(config.get("provider_id") or "").strip()
    model_id = str(config.get("model_id") or default_model or "").strip()
    if provider_id and model_id:
        return {"providerID": provider_id, "modelID": model_id}
    if model_id:
        return model_id
    return None


def _opencode_tool_policy(config: dict[str, Any]) -> dict[str, bool]:
    tools = config.get("tools")
    if isinstance(tools, dict):
        return {str(key): bool(value) for key, value in tools.items()}
    return {
        "bash": False,
        "edit": False,
        "write": False,
        "apply_patch": False,
        "shell": False,
        "webfetch": False,
        "websearch": False,
    }


def _opencode_post(url: str, body: dict[str, Any], headers: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    response = _send_json(request, timeout_seconds)
    return response if isinstance(response, dict) else {}


def _send_json(request: urllib.request.Request, timeout_seconds: int) -> Any:
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_openai_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def _extract_opencode_text(response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for part in response.get("parts", []) or []:
        if not isinstance(part, dict):
            continue
        for key in ("text", "content", "message"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value)
        data = part.get("data")
        if isinstance(data, dict):
            for key in ("text", "content", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    chunks.append(value)
    text = response.get("text")
    if isinstance(text, str) and text.strip():
        chunks.append(text)
    return "\n".join(chunks)


def _config_secret(config: dict[str, Any], value_key: str, env_key: str, default_env: str) -> str:
    value = str(config.get(value_key) or "").strip()
    if value:
        return value
    env_name = str(config.get(env_key) or default_env).strip()
    return os.environ.get(env_name, "").strip() if env_name else ""


def _default_developer_text() -> str:
    return (
        "你是机构投研系统里的解释型研究 Agent。"
        "只能解释用户给定的确定性信号，不得新增标的、改写信号、承诺收益或给出未经表格支持的结论。"
        "输出中文，专业、克制、可审计。"
        "禁止使用 Markdown，不要使用 #、**、表格、分割线、项目符号。"
        "请使用商务纯文本段落，必要时用“1. 2. 3.”编号。"
    )


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
