from __future__ import annotations

import json

from superpower.chat.orchestrator import ChatOrchestrator
from superpower.tools import llm


def test_openai_provider_still_uses_responses_api(monkeypatch) -> None:
    calls = []

    def fake_send_json(request, timeout_seconds):
        calls.append(
            {
                "url": request.full_url,
                "auth": request.get_header("Authorization"),
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout_seconds,
            }
        )
        return {"output_text": "openai answer"}

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(llm, "_send_json", fake_send_json)

    result = llm.generate_text(
        "question",
        {"provider": "openai", "primary_model": "gpt-test", "llm_enabled": True},
        timeout_seconds=12,
        developer_text="developer",
    )

    assert result.used is True
    assert result.provider == "openai"
    assert result.model == "gpt-test"
    assert result.text == "openai answer"
    assert calls[0]["url"] == "https://api.openai.com/v1/responses"
    assert calls[0]["auth"] == "Bearer test-openai-key"
    assert calls[0]["body"]["model"] == "gpt-test"
    assert calls[0]["body"]["input"][0]["content"][0]["text"] == "developer"
    assert calls[0]["timeout"] == 12


def test_opencode_provider_creates_session_and_posts_message(monkeypatch) -> None:
    calls = []

    def fake_send_json(request, timeout_seconds):
        body = json.loads(request.data.decode("utf-8"))
        calls.append({"url": request.full_url, "auth": request.get_header("Authorization"), "body": body})
        if request.full_url.endswith("/session"):
            return {"id": "session-1"}
        return {"parts": [{"type": "text", "text": "opencode answer"}]}

    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "server-pass")
    monkeypatch.setattr(llm, "_send_json", fake_send_json)

    result = llm.generate_text(
        "question",
        {
            "provider": "opencode",
            "primary_model": "fallback-model",
            "llm_enabled": True,
            "opencode": {
                "base_url": "http://127.0.0.1:4096",
                "provider_id": "openai",
                "model_id": "gpt-test",
                "server_username": "opencode",
            },
        },
        developer_text="developer",
    )

    assert result.used is True
    assert result.provider == "opencode"
    assert result.text == "opencode answer"
    assert calls[0]["url"] == "http://127.0.0.1:4096/session"
    assert calls[1]["url"] == "http://127.0.0.1:4096/session/session-1/message"
    assert calls[1]["body"]["system"] == "developer"
    assert calls[1]["body"]["parts"] == [{"type": "text", "text": "question"}]
    assert calls[1]["body"]["model"] == {"providerID": "openai", "modelID": "gpt-test"}
    assert calls[1]["body"]["tools"]["bash"] is False
    assert calls[1]["auth"].startswith("Basic ")


def test_opencode_provider_can_use_existing_session(monkeypatch) -> None:
    calls = []

    def fake_send_json(request, timeout_seconds):
        calls.append(request.full_url)
        return {"text": "existing session answer"}

    monkeypatch.setattr(llm, "_send_json", fake_send_json)

    result = llm.generate_text(
        "question",
        {
            "provider": "opencode",
            "primary_model": "gpt-test",
            "llm_enabled": True,
            "opencode": {"base_url": "http://localhost:4096", "session_id": "existing"},
        },
    )

    assert result.used is True
    assert result.text == "existing session answer"
    assert calls == ["http://localhost:4096/session/existing/message"]


def test_chat_model_config_uses_chat_only_provider_override(tmp_path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "model_config.json").write_text(
        json.dumps(
            {
                "provider": "openai",
                "primary_model": "daily-model",
                "llm_enabled": True,
                "api_key_env": "OPENAI_API_KEY",
                "opencode": {
                    "base_url": "http://127.0.0.1:4096",
                    "provider_id": "anthropic",
                    "model_id": "shared-model",
                    "tools": {"bash": False},
                },
                "chat": {
                    "provider": "opencode",
                    "primary_model": "chat-model",
                    "opencode": {"provider_id": "openai", "model_id": "chat-opencode-model"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = ChatOrchestrator(tmp_path)._load_model_config()

    assert loaded["provider"] == "opencode"
    assert loaded["primary_model"] == "chat-model"
    assert loaded["llm_enabled"] is True
    assert loaded["api_key_env"] == "OPENAI_API_KEY"
    assert loaded["opencode"]["base_url"] == "http://127.0.0.1:4096"
    assert loaded["opencode"]["provider_id"] == "openai"
    assert loaded["opencode"]["model_id"] == "chat-opencode-model"
    assert loaded["opencode"]["tools"] == {"bash": False}
