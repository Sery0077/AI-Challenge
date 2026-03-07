from __future__ import annotations

from dataclasses import dataclass, field

from chat_agent_cli import cli
from chat_agent_cli.config import Settings
from chat_agent_cli.llm import ChatReply, ResponseUsage
from chat_agent_cli.storage import ChatStorage


class FakeConsole:
    def __init__(self, inputs: list[str]) -> None:
        self._inputs = iter(inputs)
        self.print_calls: list[str] = []

    def input(self, _prompt: str) -> str:
        return next(self._inputs)

    def print(self, *args, **_kwargs) -> None:
        self.print_calls.append(" ".join(str(arg) for arg in args))


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
class FakeModel:
    text: str = "ok"
    usage: ResponseUsage | None = field(
        default_factory=lambda: ResponseUsage(
            input_tokens=10,
            output_tokens=4,
            total_tokens=14,
        )
    )
    error: Exception | None = None

    def reply_stream(self, _messages, on_delta):
        if self.error is not None:
            raise self.error
        on_delta(self.text)
        return ChatReply(text=self.text, usage=self.usage)


def _settings(
    limit: int = 128000,
    model: str = "gpt-4.1-mini",
    model_alias: str | None = None,
    available_model_aliases: tuple[str, ...] = (),
) -> Settings:
    return Settings(
        api_key="test",
        base_url=None,
        model=model,
        system_prompt="You are test assistant.",
        storage_path=":memory:",
        model_context_limit=limit,
        input_cost_per_1m=1.0,
        output_cost_per_1m=2.0,
        model_alias=model_alias,
        available_model_aliases=available_model_aliases,
    )


def test_safe_console_text_replaces_surrogates() -> None:
    sanitized = cli._safe_console_text("\udcd0broken")
    assert "\udcd0" not in sanitized
    assert "broken" in sanitized


def test_chat_loop_debug_and_stats(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)

    fake_console = FakeConsole(inputs=["/debug", "hello", "/stats", "/exit"])
    model = FakeModel(text="answer")
    settings = _settings()

    stats_calls: list[int] = []
    debug_calls: list[tuple[str, int, str]] = []

    def _capture_stats(stats, _pricing) -> None:
        stats_calls.append(stats.message_count)

    def _capture_debug_snapshot(*, storage, session_id, session_config, message_records) -> None:
        debug_calls.append((session_id, len(message_records), session_config.strategy))

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "_print_session_stats", _capture_stats)
    monkeypatch.setattr(cli, "_print_debug_snapshot", _capture_debug_snapshot)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=settings)

    assert any("Current model:" in line for line in fake_console.print_calls)
    assert any("Token debug enabled." in line for line in fake_console.print_calls)
    assert any("tokens: request=" in line for line in fake_console.print_calls)
    assert debug_calls == [
        (session_id, 1, "full"),
        (session_id, 3, "full"),
    ]
    assert stats_calls == [3]


def test_chat_loop_sanitizes_surrogate_user_input(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)

    fake_console = FakeConsole(inputs=["Числа \udcd1поездки 10.09-15.09", "/exit"])
    model = FakeModel(text="answer")
    settings = _settings()

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=settings)

    records = storage.load_message_records(session_id)
    user_messages = [row.content for row in records if row.role == "user"]

    assert user_messages == ["Числа ?поездки 10.09-15.09"]


def test_chat_loop_summary_command(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.append_message(session_id, "user", "hello", token_count=2)
    records = storage.load_message_records(session_id)
    start_id = records[1].id
    assert start_id is not None
    storage.append_session_summary(
        session_id=session_id,
        start_message_id=start_id,
        end_message_id=start_id,
        summary_text="user: hello",
        token_count=2,
    )

    fake_console = FakeConsole(inputs=["/summary", "/exit"])
    model = FakeModel(text="answer")
    settings = _settings()
    summary_calls: list[int] = []

    def _capture_summaries(summaries) -> None:
        summary_calls.append(len(summaries))

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(cli, "_print_session_summaries", _capture_summaries)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=settings)

    assert summary_calls == [1]


def test_chat_loop_compact_replaces_summary(monkeypatch, tmp_path) -> None:
    @dataclass
    class CompactFakeModel:
        summary_text: str = "llm compact summary"

        def reply(self, _messages):
            return ChatReply(text=self.summary_text, usage=None)

        def reply_stream(self, _messages, on_delta):
            on_delta("answer")
            return ChatReply(text="answer", usage=None)

    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sum",
        summary_trigger_user_messages=5,
    )
    storage.append_message(session_id, "user", "old info", token_count=3)
    records = storage.load_message_records(session_id)
    old_id = records[1].id
    assert old_id is not None
    storage.append_session_summary(
        session_id=session_id,
        start_message_id=old_id,
        end_message_id=old_id,
        summary_text="old summary",
        token_count=2,
    )

    fake_console = FakeConsole(inputs=["/compact", "/summary", "/exit"])
    summary_calls: list[list[str]] = []

    def _capture_summaries(summaries) -> None:
        summary_calls.append([item.content for item in summaries])

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(cli, "_print_session_summaries", _capture_summaries)

    cli._chat_loop(
        model=CompactFakeModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert any("History compacted into one summary." in line for line in fake_console.print_calls)
    assert summary_calls == [["llm compact summary"]]


def test_chat_loop_model_command_switches_model(monkeypatch, tmp_path) -> None:
    @dataclass
    class SwitchedModel:
        text: str

        def reply_stream(self, _messages, on_delta):
            on_delta(self.text)
            return ChatReply(text=self.text, usage=None)

    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        model_alias="remote",
    )

    fake_console = FakeConsole(inputs=["/model local", "hello", "/exit"])
    create_calls: list[str | None] = []

    def _fake_load_settings(selected_model: str | None = None) -> Settings:
        assert selected_model == "local"
        return _settings(
            model="qwen-local",
            model_alias="local",
            available_model_aliases=("remote", "local"),
        )

    def _fake_create_chat_model(settings: Settings) -> SwitchedModel:
        create_calls.append(settings.model_alias)
        return SwitchedModel(text=f"answer-{settings.model_alias}")

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(cli, "load_settings", _fake_load_settings)
    monkeypatch.setattr(cli, "_create_chat_model", _fake_create_chat_model)

    cli._chat_loop(
        model=FakeModel(text="initial"),
        storage=storage,
        session_id=session_id,
        settings=_settings(
            model_alias="remote",
            available_model_aliases=("remote", "local"),
        ),
    )

    assert create_calls == ["local"]
    assert storage.get_session_model_alias(session_id) == "local"
    assert any("Model switched to local (qwen-local)." in line for line in fake_console.print_calls)
    assert any("answer-local" in line for line in fake_console.print_calls)


def test_chat_loop_model_command_interactive_switch(monkeypatch, tmp_path) -> None:
    @dataclass
    class SwitchedModel:
        text: str

        def reply_stream(self, _messages, on_delta):
            on_delta(self.text)
            return ChatReply(text=self.text, usage=None)

    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        model_alias="remote",
    )

    fake_console = FakeConsole(inputs=["/model", "hello", "/exit"])
    selection_calls: list[str | None] = []

    def _fake_choose_model_interactive(settings: Settings) -> str | None:
        selection_calls.append(settings.model_alias)
        return "local"

    def _fake_load_settings(selected_model: str | None = None) -> Settings:
        assert selected_model == "local"
        return _settings(
            model="qwen-local",
            model_alias="local",
            available_model_aliases=("remote", "local"),
        )

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(cli, "_choose_model_interactive", _fake_choose_model_interactive)
    monkeypatch.setattr(cli, "load_settings", _fake_load_settings)
    monkeypatch.setattr(cli, "_create_chat_model", lambda settings: SwitchedModel(text=f"answer-{settings.model_alias}"))

    cli._chat_loop(
        model=FakeModel(text="initial"),
        storage=storage,
        session_id=session_id,
        settings=_settings(
            model_alias="remote",
            available_model_aliases=("remote", "local"),
        ),
    )

    assert selection_calls == ["remote"]
    assert storage.get_session_model_alias(session_id) == "local"
    assert any("Model switched to local (qwen-local)." in line for line in fake_console.print_calls)
    assert any("answer-local" in line for line in fake_console.print_calls)


def test_build_model_prefers_session_model_alias(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        model_alias="local",
    )

    selected_models: list[str | None] = []

    def _fake_load_settings(selected_model: str | None = None) -> Settings:
        selected_models.append(selected_model)
        return _settings(model="qwen-local", model_alias="local")

    monkeypatch.setattr(cli, "load_settings", _fake_load_settings)
    monkeypatch.setattr(cli, "_create_chat_model", lambda settings: FakeModel(text=settings.model))

    model, returned_storage, settings = cli._build_model(
        session_id=session_id,
        storage=storage,
    )

    assert isinstance(model, FakeModel)
    assert returned_storage is storage
    assert settings.model_alias == "local"
    assert selected_models == ["local"]


def test_chat_loop_memory_command(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="memory",
        context_window_messages=4,
    )

    fake_console = FakeConsole(inputs=["owner=Maria", "/memory", "/exit"])
    model = FakeModel(text="answer")
    memory_calls: list[tuple[str, int, int]] = []

    def _capture_memory_layers(*, storage, session_id, message_records, window_messages) -> None:
        memory_calls.append((session_id, len(message_records), window_messages))

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(cli, "_print_memory_layers", _capture_memory_layers)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=_settings())

    assert memory_calls == [(session_id, 3, 4)]


def test_chat_loop_debug_shows_memory_layers(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="memory",
        context_window_messages=4,
    )

    fake_console = FakeConsole(inputs=["owner=Maria", "/debug", "/exit"])
    model = FakeModel(text="answer")
    debug_calls: list[tuple[str, int, str]] = []

    def _capture_debug_snapshot(*, storage, session_id, session_config, message_records) -> None:
        debug_calls.append((session_id, len(message_records), session_config.strategy))

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(cli, "_print_debug_snapshot", _capture_debug_snapshot)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=_settings())

    assert debug_calls == [(session_id, 3, "memory")]


def test_chat_loop_context_overflow(monkeypatch, tmp_path) -> None:
    class DummyBadRequestError(Exception):
        pass

    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)

    fake_console = FakeConsole(inputs=["очень длинный запрос для переполнения", "/exit"])
    model = FakeModel(error=DummyBadRequestError("context_length_exceeded"))
    settings = _settings(limit=10)

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "BadRequestError", DummyBadRequestError)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=settings)

    assert any("Token warning" in line for line in fake_console.print_calls)
    assert any("context length exceeded" in line for line in fake_console.print_calls)


def test_token_demo_command(monkeypatch) -> None:
    called = {"value": False}

    def _fake_build_model():
        return object(), object(), _settings()

    def _fake_print_scenarios(_settings_obj: Settings) -> None:
        called["value"] = True

    monkeypatch.setattr(cli, "_build_model", _fake_build_model)
    monkeypatch.setattr(cli, "_print_token_scenarios", _fake_print_scenarios)

    cli.token_demo()
    assert called["value"] is True
