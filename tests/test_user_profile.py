from __future__ import annotations

import json
import re
from dataclasses import dataclass

from typer.testing import CliRunner

from chat_agent_cli import cli
from chat_agent_cli.config import load_app_settings
from chat_agent_cli.context import ContextManager
from chat_agent_cli.llm import ChatReply, ResponseUsage
from chat_agent_cli.storage import ChatStorage
from chat_agent_cli.user_profile import (
    UserProfile,
    load_user_profile,
    save_user_profile,
    set_user_profile_value,
)


class FakeConsole:
    def __init__(self, inputs: list[str]) -> None:
        self._inputs = iter(inputs)

    def input(self, _prompt: str) -> str:
        return next(self._inputs)

    def print(self, *args, **_kwargs) -> None:
        return None


class FakeTokenCounter:
    def __init__(self, _model: str) -> None:
        self._fallback = False

    @property
    def fallback(self) -> bool:
        return self._fallback

    def count_text(self, text: str) -> int:
        return max(1, len(text) // 2) if text else 0

    def count_messages(self, messages) -> int:
        total = 2
        for message in messages:
            total += self.count_text(message.get("content", ""))
            total += 4
        return total


@dataclass
class ProfileAwareFakeModel:
    token_counter: FakeTokenCounter

    def reply_stream(self, messages, on_delta):
        answer = self._answer(messages)
        on_delta(answer)
        input_tokens = self.token_counter.count_messages(messages)
        output_tokens = self.token_counter.count_text(answer)
        return ChatReply(
            text=answer,
            usage=ResponseUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    @staticmethod
    def _answer(messages: list[dict[str, str]]) -> str:
        profile_text = next(
            (
                message.get("content", "")
                for message in messages
                if message.get("role") == "system"
                and "User profile:" in message.get("content", "")
            ),
            "",
        )
        tone = _extract_profile_value(profile_text, "tone") or "UNKNOWN"
        verbosity = _extract_profile_value(profile_text, "verbosity") or "UNKNOWN"
        language = _extract_profile_value(profile_text, "answer_language") or "UNKNOWN"
        return f"tone={tone}; verbosity={verbosity}; language={language}"


def _extract_profile_value(profile_text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^- {re.escape(key)}: (.+)$", profile_text)
    if match is None:
        return None
    return match.group(1).strip()


def test_load_app_settings_exposes_user_profile_path(monkeypatch, tmp_path) -> None:
    profile_path = tmp_path / "user_profile.json"
    monkeypatch.setenv("CHAT_USER_PROFILE_PATH", str(profile_path))

    app_settings = load_app_settings()

    assert app_settings.user_profile_path == str(profile_path)


def test_user_profile_roundtrip_and_set_value(tmp_path) -> None:
    profile_path = tmp_path / "user_profile.json"
    save_user_profile(
        str(profile_path),
        UserProfile(
            user_id="default",
            name="Alex",
            preferences={
                "style": {"tone": "neutral"},
                "constraints": {"no_emojis": True},
            },
        ),
    )

    updated = set_user_profile_value(str(profile_path), "format.prefer_bullets", "true")
    loaded = load_user_profile(str(profile_path))

    assert updated.normalized_preferences()["format"]["prefer_bullets"] is True
    assert loaded.name == "Alex"
    assert loaded.normalized_preferences()["constraints"]["no_emojis"] is True
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    assert raw["preferences"]["format"]["prefer_bullets"] is True


def test_context_manager_injects_profile_message(tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.append_message(session_id, "user", "hello", token_count=2)

    manager = ContextManager(
        storage=storage,
        token_counter=FakeTokenCounter("gpt-4.1-mini"),
        user_profile=UserProfile(
            name="Maria",
            preferences={
                "style": {"tone": "neutral", "verbosity": "short"},
                "constraints": {"answer_language": "ru"},
            },
        ),
    )

    built = manager.build_messages(session_id, storage.load_message_records(session_id))

    assert built.messages[1]["role"] == "system"
    assert "User profile:" in built.messages[1]["content"]
    assert "- tone: neutral" in built.messages[1]["content"]
    assert "- answer_language: ru" in built.messages[1]["content"]


def test_chat_loop_applies_different_profiles_automatically(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    profile_path = tmp_path / "user_profile.json"
    monkeypatch.setenv("CHAT_USER_PROFILE_PATH", str(profile_path))

    monkeypatch.setattr(cli, "console", FakeConsole(inputs=["ответь с учетом профиля", "/exit"]))
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    first_session_id = storage.create_session("You are test assistant.", token_count=5)
    save_user_profile(
        str(profile_path),
        UserProfile(
            preferences={
                "style": {"tone": "neutral", "verbosity": "short"},
                "constraints": {"answer_language": "ru"},
            }
        ),
    )
    cli._chat_loop(
        model=ProfileAwareFakeModel(token_counter=FakeTokenCounter("gpt-4.1-mini")),
        storage=storage,
        session_id=first_session_id,
        settings=cli.Settings(
            api_key="test",
            base_url=None,
            model="gpt-4.1-mini",
            system_prompt="You are test assistant.",
            storage_path=":memory:",
            model_context_limit=128000,
            input_cost_per_1m=1.0,
            output_cost_per_1m=2.0,
        ),
    )

    monkeypatch.setattr(cli, "console", FakeConsole(inputs=["ответь с учетом профиля", "/exit"]))
    second_session_id = storage.create_session("You are test assistant.", token_count=5)
    save_user_profile(
        str(profile_path),
        UserProfile(
            preferences={
                "style": {"tone": "friendly", "verbosity": "detailed"},
                "constraints": {"answer_language": "en"},
            }
        ),
    )
    cli._chat_loop(
        model=ProfileAwareFakeModel(token_counter=FakeTokenCounter("gpt-4.1-mini")),
        storage=storage,
        session_id=second_session_id,
        settings=cli.Settings(
            api_key="test",
            base_url=None,
            model="gpt-4.1-mini",
            system_prompt="You are test assistant.",
            storage_path=":memory:",
            model_context_limit=128000,
            input_cost_per_1m=1.0,
            output_cost_per_1m=2.0,
        ),
    )

    first_answer = [row.content for row in storage.load_message_records(first_session_id) if row.role == "assistant"][-1]
    second_answer = [row.content for row in storage.load_message_records(second_session_id) if row.role == "assistant"][-1]

    assert first_answer == "tone=neutral; verbosity=short; language=ru"
    assert second_answer == "tone=friendly; verbosity=detailed; language=en"


def test_profile_cli_show_and_set(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    profile_path = tmp_path / "user_profile.json"
    monkeypatch.setenv("CHAT_USER_PROFILE_PATH", str(profile_path))

    result = runner.invoke(cli.app, ["profile-set", "style.verbosity", "short"])

    assert result.exit_code == 0
    assert "Updated profile field 'style.verbosity'." in result.stdout

    shown = runner.invoke(cli.app, ["profile-show"])

    assert shown.exit_code == 0
    assert "User profile path:" in shown.stdout
    assert "- verbosity: short" in shown.stdout
