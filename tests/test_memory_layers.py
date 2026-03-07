from __future__ import annotations

import re
from dataclasses import dataclass

from chat_agent_cli import cli
from chat_agent_cli.config import Settings
from chat_agent_cli.context import ContextManager
from chat_agent_cli.llm import ChatReply, ResponseUsage
from chat_agent_cli.storage import ChatStorage


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
class MemoryScenarioModel:
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

    def _answer(self, messages: list[dict[str, str]]) -> str:
        last_user = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        if "repeat memory layers" not in last_user.lower():
            return "ack"

        fields = [
            "owner",
            "preference",
            "goal",
            "constraint",
            "database",
            "decision",
        ]
        return " | ".join(
            f"{field}={self._extract_latest_value(messages, field) or 'UNKNOWN'}"
            for field in fields
        )

    @staticmethod
    def _extract_latest_value(messages: list[dict[str, str]], key: str) -> str | None:
        pattern = re.compile(rf"(?i)\b{re.escape(key)}\b\s*[:=]\s*([^|\n.;]+)")
        values: list[str] = []
        for message in messages:
            values.extend(match.group(1).strip() for match in pattern.finditer(message.get("content", "")))
        if not values:
            return None
        return values[-1]


def _settings() -> Settings:
    return Settings(
        api_key="test",
        base_url=None,
        model="gpt-4.1-mini",
        system_prompt="You are test assistant.",
        storage_path=":memory:",
        model_context_limit=128000,
        input_cost_per_1m=1.0,
        output_cost_per_1m=2.0,
    )


def _run_dialog(
    monkeypatch,
    storage: ChatStorage,
    session_id: str,
    user_messages: list[str],
) -> None:
    fake_console = FakeConsole(inputs=[*user_messages, "/exit"])
    model = MemoryScenarioModel(token_counter=FakeTokenCounter("gpt-4.1-mini"))
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )


def test_memory_strategy_routes_items_to_layers(tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="memory",
        context_window_messages=4,
    )
    storage.append_message(session_id, "user", "owner=Maria; preference=reply in Russian", token_count=8)
    storage.append_message(session_id, "assistant", "ack", token_count=1)
    storage.append_message(
        session_id,
        "user",
        "goal=prepare release plan; constraint=without new dependencies",
        token_count=10,
    )
    storage.append_message(session_id, "assistant", "ack", token_count=1)
    storage.append_message(
        session_id,
        "user",
        "working: owner=task captain Olga; long: constraint=always keep audit trail",
        token_count=12,
    )
    storage.append_message(session_id, "assistant", "ack", token_count=1)
    storage.append_message(
        session_id,
        "user",
        "decision=keep sqlite checkpoints; status=collect rollout constraints",
        token_count=11,
    )

    manager = ContextManager(storage=storage, token_counter=FakeTokenCounter("gpt-4.1-mini"))
    built = manager.build_messages(session_id, storage.load_message_records(session_id))

    working = storage.list_working_memory(session_id)
    long_term = storage.list_long_term_memory(session_id)

    assert [(item.key, item.value) for item in working] == [
        ("goal", "prepare release plan"),
        ("constraint", "without new dependencies"),
        ("owner", "task captain Olga"),
        ("status", "collect rollout constraints"),
    ]
    assert [(item.key, item.value) for item in long_term] == [
        ("owner", "Maria"),
        ("preference", "reply in Russian"),
        ("constraint", "always keep audit trail"),
        ("decision", "keep sqlite checkpoints"),
    ]

    system_contents = [message["content"] for message in built.messages if message["role"] == "system"]
    assert any("Working memory (current task):" in content for content in system_contents)
    assert any("Long-term memory" in content for content in system_contents)

    non_system_contents = [message["content"] for message in built.messages if message["role"] != "system"]
    assert "owner=Maria; preference=reply in Russian" not in non_system_contents
    assert "decision=keep sqlite checkpoints; status=collect rollout constraints" in non_system_contents


def test_memory_strategy_improves_answers_vs_sliding(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    scenario = [
        "owner=Maria; preference=reply in Russian",
        "goal=assemble payment webhook spec",
        "constraint=without new dependencies",
        "decision=store local checkpoints in sqlite",
        "Discuss rollout phases and rollback conditions for operations.",
        "Review migration risks, observability, and support handoff details.",
        "database=postgres",
        "Capture runbook examples and release notes for support.",
        "List open questions for alerting, dashboards, and audit logs.",
        "repeat memory layers: owner, preference, goal, constraint, database, decision",
    ]
    expected_pairs = {
        "owner=Maria",
        "preference=reply in Russian",
        "goal=assemble payment webhook spec",
        "constraint=without new dependencies",
        "database=postgres",
        "decision=store local checkpoints in sqlite",
    }

    sliding_session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sliding",
        context_window_messages=4,
    )
    memory_session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="memory",
        context_window_messages=4,
    )

    _run_dialog(monkeypatch, storage, sliding_session_id, scenario)
    _run_dialog(monkeypatch, storage, memory_session_id, scenario)

    sliding_records = storage.load_message_records(sliding_session_id)
    memory_records = storage.load_message_records(memory_session_id)
    sliding_answer = [row.content for row in sliding_records if row.role == "assistant"][-1]
    memory_answer = [row.content for row in memory_records if row.role == "assistant"][-1]

    sliding_quality = sum(pair in sliding_answer for pair in expected_pairs)
    memory_quality = sum(pair in memory_answer for pair in expected_pairs)

    assert sliding_quality < memory_quality
    assert memory_quality == len(expected_pairs)
    assert "owner=UNKNOWN" in sliding_answer
    assert "owner=Maria" in memory_answer
    assert "decision=store local checkpoints in sqlite" in memory_answer

    sliding_stats = storage.session_token_stats(sliding_session_id)
    memory_stats = storage.session_token_stats(memory_session_id)
    assert memory_stats.billed_input_tokens > sliding_stats.billed_input_tokens
