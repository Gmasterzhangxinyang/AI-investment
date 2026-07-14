from superpower.server.app import (
    _load_local_environment,
    _merge_model_config_secrets,
    _public_model_config,
    _write_local_env_secret,
)


def test_merge_model_config_drops_plaintext_api_key() -> None:
    merged = _merge_model_config_secrets(
        {"api_key": "old-secret", "api_key_env": "OPENAI_API_KEY"},
        {"api_key": "new-secret", "api_key_env": "OPENAI_API_KEY"},
    )

    assert "api_key" not in merged
    assert merged["api_key_env"] == "OPENAI_API_KEY"


def test_public_model_config_reports_environment_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-environment-secret")

    public = _public_model_config({"api_key_env": "OPENAI_API_KEY"})

    assert public["api_key_configured"] is True
    assert public["api_key_masked"] == "sk-envi...cret"
    assert "api_key" not in public


def test_local_env_secret_is_saved_outside_model_config(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER_SETTING=kept\nOPENAI_API_KEY=old-key\n", encoding="utf-8")

    _write_local_env_secret(tmp_path, "OPENAI_API_KEY", "sk-proj-new-key")

    assert env_path.read_text(encoding="utf-8") == "OTHER_SETTING=kept\nOPENAI_API_KEY=sk-proj-new-key\n"
    assert env_path.stat().st_mode & 0o777 == 0o600


def test_local_environment_is_loaded_without_overriding_process_value(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-local-key\nQUOTED_SETTING='quoted value'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-process-key")
    monkeypatch.delenv("QUOTED_SETTING", raising=False)

    _load_local_environment(tmp_path)

    assert __import__("os").environ["OPENAI_API_KEY"] == "sk-process-key"
    assert __import__("os").environ["QUOTED_SETTING"] == "quoted value"
