from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from chat_agent_cli import cli
from chat_agent_cli import pipeline
from chat_agent_cli.pipeline import registry as pipeline_registry
from chat_agent_cli.config import Settings
from chat_agent_cli.context import ContextManager
from chat_agent_cli.llm import ChatReply, ResponseUsage
from chat_agent_cli.storage import ChatStorage
from chat_agent_cli.user_profile import UserProfile


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


@dataclass
class TaskStateAwareModel:
    def reply_stream(self, messages, on_delta):
        answer = self._answer(messages)
        on_delta(answer)
        return ChatReply(text=answer, usage=None)

    def _answer(self, messages: list[dict[str, str]]) -> str:
        last_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        if "continue without repeating context" not in last_user.lower():
            return "ack"

        task_message = next(
            (
                message.get("content", "")
                for message in messages
                if message.get("role") == "system"
                and "Task state:" in message.get("content", "")
            ),
            "",
        )
        fields: dict[str, str] = {}
        for line in task_message.splitlines():
            match = re.match(r"^([a-z_]+):\s+(.+)$", line.strip())
            if match is None:
                continue
            fields[match.group(1)] = match.group(2)
        return (
            f"stage={fields.get('stage', 'UNKNOWN')} "
            f"status={fields.get('status', 'UNKNOWN')} "
            f"step={fields.get('current_step', 'UNKNOWN')} "
            f"next={fields.get('expected_action', 'UNKNOWN')}"
        )


@dataclass
class ConfirmingTaskStateModel:
    def reply_stream(self, messages, on_delta):
        last_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        if "approved task state" in last_user.lower():
            answer = (
                "Continuing from the approved state.\n"
                "<<TASK_STATE>>\n"
                "stage: execution\n"
                "current_step: Implement automatic task transitions\n"
                "expected_action: Validate resumed task flow\n"
                "transition: auto\n"
                "<<END_TASK_STATE>>"
            )
        else:
            answer = (
                "I have the plan and need approval before execution.\n"
                "<<TASK_STATE>>\n"
                "stage: execution\n"
                "current_step: Implement automatic task transitions\n"
                "expected_action: Validate resumed task flow\n"
                "transition: confirm\n"
                "confirm_prompt: Move the task to execution and continue?\n"
                "<<END_TASK_STATE>>"
            )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class StreamingTaskProtocolModel:
    def reply_stream(self, _messages, on_delta):
        chunks = [
            "Streaming ",
            "answer",
            " before ",
            "metadata.\n<<TASK_",
            "STATE>>\nstage: execution\n",
            "current_step: Stream the visible reply\n",
            "expected_action: Persist the task state\n",
            "transition: auto\n",
            "<<END_TASK_STATE>>",
        ]
        for chunk in chunks:
            on_delta(chunk)
        return ChatReply(text="".join(chunks), usage=None)


@dataclass
class SystemMessageInspectingModel:
    seen_messages: list[dict[str, str]] | None = None

    def reply_stream(self, messages, on_delta):
        self.seen_messages = [dict(message) for message in messages]
        on_delta("ack")
        return ChatReply(text="ack", usage=None)


@dataclass
class RetryingMetadataModel:
    calls: int = 0
    seen_messages: list[dict[str, str]] | None = None

    def reply_stream(self, messages, on_delta):
        self.calls += 1
        self.seen_messages = [dict(message) for message in messages]
        if self.calls == 1:
            answer = "Показываю план без metadata-блока."
        else:
            answer = (
                "Исправил ответ и добавил metadata.\n"
                "<<TASK_STATE>>\n"
                "stage: execution\n"
                "current_step: Implement automatic task transitions\n"
                "expected_action: Validate resumed task flow\n"
                "transition: confirm\n"
                "confirm_prompt: Перейти к реализации?\n"
                "<<END_TASK_STATE>>"
            )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class RetryingInvalidTransitionModel:
    calls: int = 0
    seen_messages: list[dict[str, str]] | None = None

    def reply_stream(self, messages, on_delta):
        self.calls += 1
        self.seen_messages = [dict(message) for message in messages]
        if self.calls == 1:
            answer = (
                "Пропускаю промежуточные стадии.\n"
                "<<TASK_STATE>>\n"
                "stage: done\n"
                "current_step: Skip directly to done\n"
                "expected_action: No further action\n"
                "transition: auto\n"
                "<<END_TASK_STATE>>"
            )
        else:
            answer = (
                "Оставляю задачу на планировании и прошу подтверждение на следующий шаг.\n"
                "<<TASK_STATE>>\n"
                "stage: execution\n"
                "current_step: Implement the approved plan\n"
                "expected_action: Execute the approved plan and report progress\n"
                "transition: confirm\n"
                "confirm_prompt: Перейти к реализации по этому плану?\n"
                "<<END_TASK_STATE>>"
            )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class ConflictingInvariantModel:
    def reply_stream(self, _messages, on_delta):
        answer = (
            "Не могу предложить переход на Node.js, потому что это нарушает активные инварианты.\n"
            "<<TASK_STATE>>\n"
            "stage: validation\n"
            "current_step: Switch the implementation to Node.js\n"
            "expected_action: Replace the CLI stack with Next.js\n"
            "transition: auto\n"
            "invariants_status: conflict\n"
            "violated_invariants: stack, technical_decision\n"
            "refusal_reason: Active invariants require a Python CLI without new dependencies.\n"
            "<<END_TASK_STATE>>"
        )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class PlainTextPlanningModel:
    def reply_stream(self, messages, on_delta):
        last_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        lowered = last_user.lower()
        if "start working on the task from the current task state" in lowered:
            answer = (
                "Чтобы спланировать задачу, уточним пару моментов:\n"
                "1. Где будет работать агент?\n"
                "2. Нужно ли хранить состояние?\n"
            )
        elif "telegram" in lowered or "телеграм" in lowered:
            answer = (
                "Отлично, план для MVP готов:\n"
                "1. Создать Telegram-бота на Python.\n"
                "2. Обрабатывать все входящие сообщения.\n"
                "3. Всегда отвечать текстом Pong.\n"
                "Хочешь, я сразу перейду к реализации?"
            )
        elif "continue from the approved task state" in lowered:
            answer = "Начинаю реализацию Telegram-бота с ответом Pong."
        else:
            answer = "ack"
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class RevisingPlanModel:
    def reply_stream(self, messages, on_delta):
        last_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        lowered = last_user.lower()
        if "start working on the task from the current task state" in lowered:
            answer = "План готов: сделать Telegram-бота, который отвечает Pong. Хочешь, я сразу перейду к реализации?"
        elif "добавь" in lowered or "логирование" in lowered:
            answer = (
                "Обновил план:\n"
                "1. Добавить обработчик /start.\n"
                "2. Отвечать Pong на любые сообщения.\n"
                "3. Добавить простое логирование.\n"
                "Хочешь, я перейду к реализации по этому плану?"
            )
        elif "continue from the approved task state" in lowered:
            answer = "Начинаю реализацию по обновлённому плану."
        else:
            answer = "ack"
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class DoneTaskStateModel:
    current_step: str = "Implementation verified by the user"
    expected_action: str = "No further action"

    def reply_stream(self, _messages, on_delta):
        answer = (
            "Рад, что всё работает.\n"
            "<<TASK_STATE>>\n"
            "stage: done\n"
            f"current_step: {self.current_step}\n"
            f"expected_action: {self.expected_action}\n"
            "transition: auto\n"
            "<<END_TASK_STATE>>"
        )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class StructuredPlanningModel:
    def reply_stream(self, messages, on_delta):
        last_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        lowered = last_user.lower()
        if "start working on the task from the current task state" in lowered:
            answer = (
                "GOAL:\n"
                "Сделать простого чат-агента.\n\n"
                "UNDERSTANDING:\n"
                "- Нужно собрать минимальный план реализации.\n"
                "- Надо понять, хватает ли вводных.\n\n"
                "CONSTRAINTS:\n"
                "- none\n\n"
                "ASSUMPTIONS:\n"
                "- none\n\n"
                "QUESTIONS:\n"
                "- Какой интерфейс нужен агенту?\n\n"
                "PLAN:\n"
                "1. Уточнить интерфейс агента.\n"
                "   RESULT: Понятен целевой сценарий использования.\n\n"
                "DONE_CRITERIA:\n"
                "- Есть согласованный план.\n\n"
                "READINESS:\n"
                "- NEEDS_CLARIFICATION"
            )
        else:
            answer = (
                "GOAL:\n"
                "Сделать простого чат-агента для терминала.\n\n"
                "UNDERSTANDING:\n"
                "- Нужно сделать минимальную рабочую версию.\n"
                "- Требуется перейти к реализации после подтверждения.\n\n"
                "CONSTRAINTS:\n"
                "- Без лишних зависимостей.\n\n"
                "ASSUMPTIONS:\n"
                "- Python уже выбран.\n\n"
                "QUESTIONS:\n"
                "- none\n\n"
                "PLAN:\n"
                "1. Добавить цикл чтения пользовательского ввода.\n"
                "   RESULT: Агент принимает сообщения из терминала.\n"
                "2. Подключить генерацию ответа модели.\n"
                "   RESULT: Агент отвечает на каждое сообщение.\n"
                "3. Проверить базовый сценарий общения.\n"
                "   RESULT: Подтверждена работоспособность MVP.\n\n"
                "DONE_CRITERIA:\n"
                "- Агент отвечает в терминале.\n\n"
                "READINESS:\n"
                "- READY_FOR_EXECUTION\n\n"
                "Можно переходить к выполнению?"
            )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class StructuredExecutionModel:
    def reply_stream(self, messages, on_delta):
        answer = (
            "PROGRESS:\n"
            "- Реализация основных изменений завершена.\n\n"
            "CHANGES:\n"
            "- Обновлён task pipeline.\n\n"
            "BLOCKERS:\n"
            "- none\n\n"
            "NEXT:\n"
            "- Прогнать validation-сценарии.\n\n"
            "VALIDATION_READINESS:\n"
            "- READY_FOR_VALIDATION"
        )
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


@dataclass
class PipelineInspectingModel:
    seen_messages: list[dict[str, str]] | None = None

    def reply_stream(self, messages, on_delta):
        self.seen_messages = [dict(message) for message in messages]
        answer = "SPECIAL_PLAN_TOKEN"
        on_delta(answer)
        return ChatReply(text=answer, usage=None)


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


def test_main_defaults_to_chat_command(monkeypatch) -> None:
    captured_argv: list[list[str]] = []

    def _fake_app() -> None:
        captured_argv.append(list(cli.sys.argv))

    monkeypatch.setattr(cli, "app", _fake_app)
    monkeypatch.setattr(cli.sys, "argv", ["chat-agent"])

    cli.main()

    assert captured_argv == [["chat-agent", "chat"]]


def test_packaged_chat_agent_entrypoint_uses_main() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert config["project"]["scripts"]["chat-agent"] == "chat_agent_cli.cli:main"


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


def test_chat_loop_merges_system_messages_before_model_request(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    model = SystemMessageInspectingModel()

    fake_console = FakeConsole(inputs=["hello", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(
        cli,
        "load_user_profile",
        lambda _path: UserProfile(
            user_id="default",
            name="Sergey",
            preferences={"style": {"verbosity": "short"}},
        ),
    )

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert model.seen_messages is not None
    system_messages = [message for message in model.seen_messages if message["role"] == "system"]
    assert len(system_messages) == 1
    assert "You are test assistant." in system_messages[0]["content"]
    assert "User profile:" in system_messages[0]["content"]


def test_chat_loop_injects_planning_stage_prompt(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify scope",
        expected_action="Prepare a short plan",
    )
    model = SystemMessageInspectingModel()

    fake_console = FakeConsole(inputs=["hello", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert model.seen_messages is not None
    system_messages = [message for message in model.seen_messages if message["role"] == "system"]
    assert len(system_messages) == 1
    assert "Ты находишься на стадии PLAN в агенте со стейт-машиной:" in system_messages[0]["content"]
    assert "Не используй жёсткий шаблон с заголовками вроде GOAL" in system_messages[0]["content"]
    assert "Протокол переходов задачи:" in system_messages[0]["content"]


def test_chat_loop_injects_execution_stage_prompt(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement feature",
        expected_action="Report progress",
    )
    model = SystemMessageInspectingModel()

    fake_console = FakeConsole(inputs=["hello", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert model.seen_messages is not None
    system_messages = [message for message in model.seen_messages if message["role"] == "system"]
    assert len(system_messages) == 1
    assert "Ты находишься на стадии EXECUTION в агенте со стейт-машиной:" in system_messages[0]["content"]
    assert "Не используй жёсткий шаблон с заголовками вроде PROGRESS" in system_messages[0]["content"]
    assert "Протокол переходов задачи:" in system_messages[0]["content"]


def test_chat_loop_injects_active_invariants_into_system_prompt(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify scope",
        expected_action="Prepare a short plan",
    )
    storage.add_session_invariant(
        session_id,
        category="architecture",
        text="Keep the assistant as a terminal-first CLI.",
    )
    storage.add_session_invariant(
        session_id,
        category="business_rule",
        text="Every assistant reply must include required task metadata.",
    )
    model = SystemMessageInspectingModel()

    fake_console = FakeConsole(inputs=["hello", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert model.seen_messages is not None
    system_messages = [message for message in model.seen_messages if message["role"] == "system"]
    assert len(system_messages) == 1
    assert "Активные инварианты задачи:" in system_messages[0]["content"]
    assert "- architecture: Keep the assistant as a terminal-first CLI." in system_messages[0]["content"]
    assert "invariants_status: satisfied|conflict" in system_messages[0]["content"]


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


def test_invariant_command_manages_separate_invariant_storage(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)

    fake_console = FakeConsole(
        inputs=[
            "/invariant add architecture | Keep the assistant in the existing Python CLI architecture",
            "/invariant",
            "/invariant clear",
            "/invariant",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=FakeModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    printed_output = "\n".join(fake_console.print_calls)
    assert "Invariant added." in printed_output
    assert "[architecture] Keep the assistant in the existing Python CLI architecture" in printed_output
    assert "Invariants:" in printed_output
    assert "No active invariants." in printed_output
    assert storage.list_session_invariants(session_id) == []


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


def test_chat_loop_task_state_survives_pause_and_restart(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )

    first_console = FakeConsole(
        inputs=[
            "/task set planning Clarify requirements | Inspect the repository",
            "We need a formal task state with planning, execution, validation, and done.",
            "Capture another implementation detail.",
            "One more note that should push old context out of the sliding window.",
            "/task set execution Implement task state storage | Inject task state into prompt context",
            "/pause Wait for resume",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", first_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=TaskStateAwareModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    paused_state = storage.get_task_state(session_id)
    assert paused_state is not None
    assert paused_state.stage == "execution"
    assert paused_state.is_paused is True
    assert any("Task state updated." in line for line in first_console.print_calls)
    assert any("Task paused." in line for line in first_console.print_calls)

    manager = ContextManager(storage=storage, token_counter=FakeTokenCounter("gpt-4.1-mini"))
    built = manager.build_messages(session_id, storage.load_message_records(session_id))
    system_contents = [message["content"] for message in built.messages if message["role"] == "system"]
    non_system_contents = [message["content"] for message in built.messages if message["role"] != "system"]

    assert any(content.startswith("Task state:") for content in system_contents)
    assert (
        "We need a formal task state with planning, execution, validation, and done."
        not in non_system_contents
    )

    second_console = FakeConsole(
        inputs=[
            "/continue Validate resumed task flow",
            "continue without repeating context",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", second_console)

    cli._chat_loop(
        model=TaskStateAwareModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    resumed_state = storage.get_task_state(session_id)
    assert resumed_state is not None
    assert resumed_state.stage == "execution"
    assert resumed_state.is_paused is False
    assert resumed_state.expected_action == "Validate resumed task flow"
    resumed_output = "".join(second_console.print_calls)
    assert any("Task resumed." in line for line in second_console.print_calls)
    assert "Stage: execution" in resumed_output
    assert "Status: active" in resumed_output
    assert "Current: Implement task state storage" in resumed_output
    assert "next=Validate resumed task flow" in resumed_output


def test_task_command_initializes_planning_state_from_goal_and_bootstraps_model(
    monkeypatch, tmp_path
) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )

    fake_console = FakeConsole(inputs=["/task Fix LM Studio compatibility", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=ConfirmingTaskStateModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "planning"
    assert task_state.is_paused is True
    assert task_state.awaiting_confirmation is True
    assert task_state.current_step == "Fix LM Studio compatibility"
    assert task_state.expected_action == "Clarify requirements and define the next concrete step"
    assert any("Task started." in line for line in fake_console.print_calls)
    assert any("I have the plan and need approval before execution." in line for line in fake_console.print_calls)
    assert any("Awaiting confirmation:" in line for line in fake_console.print_calls)


def test_task_command_transitions_from_planning_to_execution_with_plain_text_flow(
    monkeypatch, tmp_path
) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )

    fake_console = FakeConsole(
        inputs=[
            "/task сделай простого чат-агента",
            "хочу телеграм бота, который всегда отвечает pong",
            "yes",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=PlainTextPlanningModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "execution"
    assert task_state.is_paused is False
    assert task_state.awaiting_confirmation is False
    printed_output = "".join(fake_console.print_calls)
    assert "Answer the open planning questions" in printed_output
    assert "Awaiting confirmation:" in printed_output
    assert "Task transition confirmed." in printed_output
    assert "Stage: execution" in printed_output


def test_task_confirmation_accepts_human_friendly_approval_phrase(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )

    fake_console = FakeConsole(
        inputs=[
            "/task сделай простого чат-агента",
            "хочу телеграм бота, который всегда отвечает pong",
            "да, давай приступай",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=PlainTextPlanningModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "execution"
    assert task_state.awaiting_confirmation is False
    printed_output = "".join(fake_console.print_calls)
    assert "Task transition confirmed." in printed_output
    assert "Начинаю реализацию Telegram-бота с ответом Pong." in printed_output


def test_task_planning_structured_readiness_drives_transition(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )

    fake_console = FakeConsole(
        inputs=[
            "/task сделай простого чат-агента",
            "нужен терминальный интерфейс",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=StructuredPlanningModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "planning"
    assert task_state.awaiting_confirmation is True
    assert task_state.pending_stage == "execution"
    printed_output = "".join(fake_console.print_calls)
    assert "READINESS:" in printed_output
    assert "Awaiting confirmation:" in printed_output


def test_task_pipeline_supports_phase_specific_builders_and_validators(
    monkeypatch, tmp_path
) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    model = PipelineInspectingModel()

    class PlanningOnlySystemBuilder:
        def supports_phase(self, phase: str) -> bool:
            return phase == "planning"

        def build_messages(self, context) -> list[dict[str, str]]:
            assert context.phase == "planning"
            return [{"role": "system", "content": "Planning invariant: keep the plan minimal."}]

    class PlanningOnlyValidator:
        def supports_phase(self, phase: str) -> bool:
            return phase == "planning"

        def validate(self, context, result):
            assert context.phase == "planning"
            if result.assistant_text != "SPECIAL_PLAN_TOKEN":
                return result
            return pipeline.ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text="План готов. Нужен апрув перед началом реализации.",
                task_update=pipeline.AgentTaskUpdate(
                    stage="execution",
                    current_step="Implement the approved plan",
                    expected_action="Execute the approved plan and report progress",
                    transition="confirm",
                    confirm_prompt="Перейти к реализации по этому плану?",
                ),
                invariant_check=None,
            )

    monkeypatch.setattr(cli, "console", FakeConsole(inputs=["/task Собери pipeline", "/exit"]))
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    monkeypatch.setattr(
        pipeline,
        "SYSTEM_PROMPT_BUILDERS",
        [PlanningOnlySystemBuilder()],
    )
    monkeypatch.setattr(
        pipeline_registry,
        "SYSTEM_PROMPT_BUILDERS",
        [PlanningOnlySystemBuilder()],
    )
    monkeypatch.setattr(
        pipeline,
        "PROMPT_BUILDERS",
        [pipeline.MergeSystemMessagesBuilder()],
    )
    monkeypatch.setattr(
        pipeline_registry,
        "PROMPT_BUILDERS",
        [pipeline.MergeSystemMessagesBuilder()],
    )
    monkeypatch.setattr(
        pipeline,
        "RESPONSE_VALIDATORS",
        [PlanningOnlyValidator()],
    )
    monkeypatch.setattr(
        pipeline_registry,
        "RESPONSE_VALIDATORS",
        [PlanningOnlyValidator()],
    )

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "planning"
    assert task_state.awaiting_confirmation is True
    assert task_state.pending_stage == "execution"
    assert model.seen_messages is not None
    system_messages = [message for message in model.seen_messages if message["role"] == "system"]
    assert len(system_messages) == 1
    assert "Planning invariant: keep the plan minimal." in system_messages[0]["content"]
    assert "Task transition protocol:" not in system_messages[0]["content"]


def test_task_execution_structured_readiness_moves_to_validation(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement the task pipeline",
        expected_action="Finish the current implementation step",
    )

    fake_console = FakeConsole(inputs=["продолжай", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=StructuredExecutionModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "validation"
    assert task_state.current_step == "Реализация основных изменений завершена."
    assert task_state.expected_action == "Прогнать validation-сценарии."
    printed_output = "".join(fake_console.print_calls)
    assert "VALIDATION_READINESS:" in printed_output
    assert "Stage: validation" in printed_output


def test_task_confirmation_accepts_freeform_plan_changes(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )

    fake_console = FakeConsole(
        inputs=[
            "/task сделай простого чат-агента",
            "да, но добавь /start и логирование",
            "ок, давай",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=RevisingPlanModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "execution"
    assert task_state.awaiting_confirmation is False
    printed_output = "".join(fake_console.print_calls)
    assert "Task transition confirmed." in printed_output
    assert "Обновил план:" in printed_output
    assert "Task transition canceled." not in printed_output
    assert "Начинаю реализацию по обновлённому плану." in printed_output


def test_task_command_replaces_active_task_with_new_goal(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement the old task",
        expected_action="Ship the old task",
    )

    fake_console = FakeConsole(inputs=["/task Start the replacement task", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=ConfirmingTaskStateModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "planning"
    assert task_state.current_step == "Start the replacement task"
    assert task_state.awaiting_confirmation is True
    assert any("Task started." in line for line in fake_console.print_calls)


def test_task_done_completes_active_task(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement task state storage",
        expected_action="Run targeted tests",
    )

    fake_console = FakeConsole(inputs=["/task done", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=FakeModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "done"
    assert task_state.current_step == "Implement task state storage"
    assert task_state.expected_action == "No further action"
    assert any("Task completed." in line for line in fake_console.print_calls)


def test_user_completion_reply_finishes_execution_task_via_model_done_transition(
    monkeypatch, tmp_path
) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement Telegram bot",
        expected_action="Wait for user confirmation after manual check",
    )

    fake_console = FakeConsole(inputs=["всё работает, спасибо", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=DoneTaskStateModel(
            current_step="Implement Telegram bot",
            expected_action="No further action",
        ),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "done"
    assert task_state.current_step == "Implement Telegram bot"
    assert task_state.expected_action == "No further action"
    assert any("Рад, что всё работает." in line for line in fake_console.print_calls)
    assert any("Task state synced." in line for line in fake_console.print_calls)


def test_invariant_conflict_blocks_invalid_state_transition(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement invariant-aware pipeline",
        expected_action="Keep the implementation in Python CLI",
    )
    storage.add_session_invariant(
        session_id,
        category="stack",
        text="Use Python CLI only and do not add new dependencies.",
    )
    storage.add_session_invariant(
        session_id,
        category="technical_decision",
        text="Do not switch the task implementation to Node.js.",
    )

    fake_console = FakeConsole(inputs=["Переделай это на Node.js и Next.js", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=ConflictingInvariantModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "execution"
    assert task_state.current_step == "Implement invariant-aware pipeline"
    assert task_state.expected_action == "Revise the request so it satisfies the active invariants"

    printed_output = "\n".join(fake_console.print_calls)
    assert "нарушает активные инварианты" in printed_output
    assert "Active invariants require a Python CLI without new dependencies." in printed_output
    assert "Stage: validation" not in printed_output


def test_model_can_complete_task_from_pending_execution_confirmation(
    monkeypatch, tmp_path
) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="напиши просто эхо бота для телеграм на питоне",
        expected_action="Process the user's updated guidance",
        is_paused=True,
        pending_stage="execution",
        pending_current_step="Написан код эхо-бота на Python с использованием python-telegram-bot.",
        pending_expected_action="Confirm the bot works as expected or assist with setup.",
        pending_confirmation_prompt="Код готов. Ты хочешь, чтобы я помог с запуском?",
    )

    fake_console = FakeConsole(inputs=["всё работает, спасибо", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=DoneTaskStateModel(
            current_step="Написан и проверен рабочий эхо-бот для Telegram",
            expected_action="No further action",
        ),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "done"
    assert task_state.current_step == "Написан и проверен рабочий эхо-бот для Telegram"
    assert task_state.expected_action == "No further action"
    assert task_state.is_paused is False
    assert task_state.awaiting_confirmation is False
    assert any("Рад, что всё работает." in line for line in fake_console.print_calls)
    assert any("Stage: done" in line for line in fake_console.print_calls)


def test_chat_loop_paused_task_requires_continue(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=2,
    )
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement task state storage",
        expected_action="Wait for resume",
        is_paused=True,
    )

    fake_console = FakeConsole(inputs=["continue without repeating context", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=TaskStateAwareModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    paused_state = storage.get_task_state(session_id)
    assert paused_state is not None
    assert paused_state.is_paused is True
    assert any("Task is paused. Use /continue to resume it" in line for line in fake_console.print_calls)
    assert not any("Stage: execution\nStatus: active" in line for line in fake_console.print_calls)


def test_task_command_without_state_shows_goal_hint(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)

    fake_console = FakeConsole(inputs=["/task", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=FakeModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert any("Use /task <goal> to initialize it." in line for line in fake_console.print_calls)


def test_chat_loop_does_not_create_task_state_from_regular_messages(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=1,
    )

    first_console = FakeConsole(
        inputs=[
            "Build a persisted FSM for task state and continue automatically.",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", first_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=ConfirmingTaskStateModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    assert storage.get_task_state(session_id) is None
    printed_output = "".join(first_console.print_calls)
    assert "Awaiting confirmation:" not in printed_output
    assert "Task state synced." not in printed_output
    assert "I have the plan and need approval before execution." in printed_output


def test_chat_loop_task_confirmation_requires_explicit_task_mode(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=1,
    )

    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Prepare the first execution step",
    )

    first_console = FakeConsole(
        inputs=[
            "Build a persisted FSM for task state and continue automatically.",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "console", first_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=ConfirmingTaskStateModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    paused_state = storage.get_task_state(session_id)
    assert paused_state is not None
    assert paused_state.stage == "planning"


def test_chat_loop_retries_when_required_task_metadata_is_missing(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Prepare the first execution step",
    )
    model = RetryingMetadataModel()

    fake_console = FakeConsole(inputs=["Собери план", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "planning"
    assert task_state.awaiting_confirmation is True
    assert model.calls == 2
    assert model.seen_messages is not None
    assert any(
        "required_metadata" in message["content"]
        for message in model.seen_messages
        if message["role"] == "system"
    )
    printed_output = "\n".join(fake_console.print_calls)
    assert "violated task response invariants" in printed_output
    assert "Исправил ответ и добавил metadata." in printed_output


def test_chat_loop_retries_when_task_transition_is_invalid(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session("You are test assistant.", token_count=5)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Prepare the first execution step",
    )
    model = RetryingInvalidTransitionModel()

    fake_console = FakeConsole(inputs=["Сделай план", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "planning"
    assert task_state.awaiting_confirmation is True
    assert model.calls == 2
    assert model.seen_messages is not None
    assert any(
        "valid_task_transition" in message["content"]
        for message in model.seen_messages
        if message["role"] == "system"
    )
    printed_output = "\n".join(fake_console.print_calls)
    assert "violated task response invariants" in printed_output
    assert "Оставляю задачу на планировании" in printed_output
    assert paused_state.is_paused is True
    assert paused_state.awaiting_confirmation is True
    assert paused_state.pending_stage == "execution"
    assert any("Awaiting confirmation:" in line for line in first_console.print_calls)

    manager = ContextManager(storage=storage, token_counter=FakeTokenCounter("gpt-4.1-mini"))
    built = manager.build_messages(session_id, storage.load_message_records(session_id))
    system_contents = [message["content"] for message in built.messages if message["role"] == "system"]
    non_system_contents = [message["content"] for message in built.messages if message["role"] != "system"]

    assert any("awaiting_confirmation: yes" in content for content in system_contents)
    assert any("pending_stage: execution" in content for content in system_contents)
    assert (
        "Build a persisted FSM for task state and continue automatically."
        not in non_system_contents
    )

    second_console = FakeConsole(inputs=["yes", "/exit"])
    monkeypatch.setattr(cli, "console", second_console)

    cli._chat_loop(
        model=ConfirmingTaskStateModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    resumed_state = storage.get_task_state(session_id)
    assert resumed_state is not None
    assert resumed_state.stage == "execution"
    assert resumed_state.is_paused is False
    assert resumed_state.awaiting_confirmation is False
    assert resumed_state.current_step == "Implement automatic task transitions"
    assert resumed_state.expected_action == "Validate resumed task flow"
    assert any("Task transition confirmed." in line for line in second_console.print_calls)
    assert any("Continuing from the approved state." in line for line in second_console.print_calls)
    assert any("Stage: execution" in line for line in second_console.print_calls)


def test_chat_loop_streams_visible_reply_without_task_metadata(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=1,
    )

    fake_console = FakeConsole(inputs=["Start task streaming", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=StreamingTaskProtocolModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    printed_output = "".join(fake_console.print_calls)
    assert "Streaming answer before metadata." in printed_output
    assert "<<TASK_STATE>>" not in printed_output
    assert "current_step: Stream the visible reply" not in printed_output

    task_state = storage.get_task_state(session_id)
    assert task_state is None


def test_chat_loop_streams_visible_reply_and_applies_metadata_in_task_mode(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=1,
    )
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Prepare the first execution step",
    )

    fake_console = FakeConsole(inputs=["Start task streaming", "/exit"])
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)

    cli._chat_loop(
        model=StreamingTaskProtocolModel(),
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )

    printed_output = "".join(fake_console.print_calls)
    assert "Streaming answer before metadata." in printed_output
    assert "<<TASK_STATE>>" not in printed_output
    assert "current_step: Stream the visible reply" not in printed_output

    task_state = storage.get_task_state(session_id)
    assert task_state is not None
    assert task_state.stage == "execution"
    assert task_state.current_step == "Stream the visible reply"
    assert task_state.expected_action == "Persist the task state"


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
