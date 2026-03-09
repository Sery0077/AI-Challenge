from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from chat_agent_cli.config import load_app_settings, load_settings


def test_load_app_settings_uses_home_chat_agent_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CHAT_STORAGE_PATH", raising=False)
    monkeypatch.delenv("CHAT_USER_PROFILE_PATH", raising=False)

    app_settings = load_app_settings()

    assert app_settings.storage_path == str(tmp_path / ".chat-agent" / "history.db")
    assert app_settings.user_profile_path == str(tmp_path / ".chat-agent" / "user_profile.json")


def test_load_settings_uses_model_profiles_from_toml(monkeypatch, tmp_path) -> None:
    models_path = tmp_path / "models.toml"
    models_path.write_text(
        textwrap.dedent(
            """
            default = "local"

            [models.remote]
            api_key_env = "REMOTE_API_KEY"
            base_url = "https://api.example.com/v1"
            model = "gpt-4.1-mini"
            context_limit = 64000
            input_cost_per_1m = 0.4
            output_cost_per_1m = 1.6

            [models.local]
            api_key = "ollama"
            base_url = "http://localhost:11434/v1"
            model = "qwen2.5:14b-instruct"
            context_limit = 32000
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CHAT_MODELS_PATH", str(models_path))
    monkeypatch.setenv("SYSTEM_PROMPT", "Prompt from env")
    monkeypatch.setenv("CHAT_STORAGE_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("REMOTE_API_KEY", "remote-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_settings()

    assert settings.model_alias == "local"
    assert settings.model == "qwen2.5:14b-instruct"
    assert settings.api_key == "ollama"
    assert settings.base_url == "http://localhost:11434/v1"
    assert settings.model_context_limit == 32000
    assert settings.available_model_aliases == ("remote", "local")


def test_load_settings_prefers_local_profile_by_default(monkeypatch, tmp_path) -> None:
    models_path = tmp_path / "models.toml"
    models_path.write_text(
        textwrap.dedent(
            """
            [models.remote]
            api_key_env = "REMOTE_API_KEY"
            base_url = "https://api.example.com/v1"
            model = "gpt-4.1-mini"

            [models.local]
            api_key = "lm-studio"
            base_url = "http://localhost:1234/v1"
            model = "qwen/qwen3.5-9b"
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CHAT_MODELS_PATH", str(models_path))
    monkeypatch.setenv("REMOTE_API_KEY", "remote-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CHAT_DEFAULT_MODEL", raising=False)

    settings = load_settings()

    assert settings.model_alias == "remote"
    assert settings.base_url == "https://api.example.com/v1"
    assert settings.model == "gpt-4.1-mini"


def test_load_settings_explicit_default_overrides_local_preference(monkeypatch, tmp_path) -> None:
    models_path = tmp_path / "models.toml"
    models_path.write_text(
        textwrap.dedent(
            """
            default = "remote"

            [models.remote]
            api_key_env = "REMOTE_API_KEY"
            base_url = "https://api.example.com/v1"
            model = "gpt-4.1-mini"

            [models.local]
            api_key = "lm-studio"
            base_url = "http://localhost:1234/v1"
            model = "qwen/qwen3.5-9b"
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CHAT_MODELS_PATH", str(models_path))
    monkeypatch.setenv("REMOTE_API_KEY", "remote-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_settings()

    assert settings.model_alias == "remote"
    assert settings.base_url == "https://api.example.com/v1"


def test_load_settings_supports_legacy_default_model_key(monkeypatch, tmp_path) -> None:
    models_path = tmp_path / "models.toml"
    models_path.write_text(
        textwrap.dedent(
            """
            default_model = "local"

            [models.remote]
            api_key_env = "REMOTE_API_KEY"
            base_url = "https://api.example.com/v1"
            model = "gpt-4.1-mini"

            [models.local]
            api_key = "lm-studio"
            base_url = "http://localhost:1234/v1"
            model = "qwen/qwen3.5-9b"
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CHAT_MODELS_PATH", str(models_path))
    monkeypatch.setenv("REMOTE_API_KEY", "remote-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_settings()

    assert settings.model_alias == "local"
    assert settings.base_url == "http://localhost:1234/v1"


def test_load_settings_uses_home_chat_agent_models_path_by_default(monkeypatch, tmp_path) -> None:
    models_dir = tmp_path / ".chat-agent"
    models_dir.mkdir(parents=True)
    models_path = models_dir / "models.toml"
    models_path.write_text(
        textwrap.dedent(
            """
            default = "routerai"

            [models.routerai]
            api_key = "secret"
            base_url = "https://routerai.ru/api/v1"
            model = "deepseek/deepseek-v3.2"
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CHAT_MODELS_PATH", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_settings()

    assert settings.model_alias == "routerai"
    assert settings.model == "deepseek/deepseek-v3.2"
    assert settings.base_url == "https://routerai.ru/api/v1"


def test_load_settings_falls_back_to_env_for_raw_model_override(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MODELS_PATH", "/tmp/nonexistent-models.toml")
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    settings = load_settings(selected_model="gpt-4o-mini")

    assert settings.model_alias == "gpt-4o-mini"
    assert settings.model == "gpt-4o-mini"
    assert settings.api_key == "env-secret"
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.available_model_aliases == ()


def test_load_settings_raises_for_unknown_profile(monkeypatch, tmp_path) -> None:
    models_path = tmp_path / "models.toml"
    models_path.write_text(
        textwrap.dedent(
            """
            [models.remote]
            api_key = "secret"
            model = "gpt-4.1-mini"
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CHAT_MODELS_PATH", str(models_path))

    with pytest.raises(ValueError, match="Model profile 'missing' not found"):
        load_settings(selected_model="missing")
