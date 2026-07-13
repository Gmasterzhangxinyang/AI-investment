from superpower.server.app import _merge_model_config_secrets, _public_model_config


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
