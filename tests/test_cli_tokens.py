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


def _settings(limit: int = 128000) -> Settings:
    return Settings(
        api_key="test",
        base_url=None,
        model="gpt-4.1-mini",
        system_prompt="You are test assistant.",
        storage_path=":memory:",
        model_context_limit=limit,
        input_cost_per_1m=1.0,
        output_cost_per_1m=2.0,
    )


def test_chat_loop_debug_and_stats(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)

    fake_console = FakeConsole(inputs=["/debug", "hello", "/stats", "/exit"])
    model = FakeModel(text="answer")
    settings = _settings()

    stats_calls: list[int] = []

    def _capture_stats(stats, _pricing) -> None:
        stats_calls.append(stats.message_count)

    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "_print_session_stats", _capture_stats)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(model=model, storage=storage, session_id=session_id, settings=settings)

    assert any("Token debug enabled." in line for line in fake_console.print_calls)
    assert any("tokens: request=" in line for line in fake_console.print_calls)
    assert stats_calls == [3]


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
