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
class ScenarioModel:
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

    def reply(self, messages):
        text = self._answer(messages)
        input_tokens = self.token_counter.count_messages(messages)
        output_tokens = self.token_counter.count_text(text)
        return ChatReply(
            text=text,
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
        prompt = last_user.lower()
        if "repeat goal" in prompt:
            return self._facts_summary(messages)
        if "what database" in prompt:
            database = self._extract_latest_value(messages, "database")
            return f"database={database or 'UNKNOWN'}"
        return "ack"

    def _facts_summary(self, messages: list[dict[str, str]]) -> str:
        fields = [
            "goal",
            "owner",
            "constraint",
            "preference",
            "decision",
            "deadline",
            "codeword",
        ]
        parts = []
        for field in fields:
            parts.append(f"{field}={self._extract_latest_value(messages, field) or 'UNKNOWN'}")
        return " | ".join(parts)

    @staticmethod
    def _extract_latest_value(messages: list[dict[str, str]], key: str) -> str | None:
        pattern = re.compile(rf"(?i)\b{re.escape(key)}\b\s*[:=]\s*([^|\n.;]+)")
        matches: list[str] = []
        for message in messages:
            matches.extend(match.group(1).strip() for match in pattern.finditer(message.get("content", "")))
        if not matches:
            return None
        return matches[-1]


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


def _run_dialog(
    monkeypatch,
    storage: ChatStorage,
    session_id: str,
    user_messages: list[str],
) -> FakeConsole:
    fake_console = FakeConsole(inputs=[*user_messages, "/exit"])
    model = ScenarioModel(token_counter=FakeTokenCounter("gpt-4.1-mini"))
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )
    return fake_console


def _base_scenario() -> list[str]:
    return [
        "goal=prepare technical spec; owner=Maria; codeword=ALPHA",
        "constraint=budget below 50k; preference=python cli without new dependencies",
        "We need 12-15 short discovery turns before writing the final draft.",
        "decision=store checkpoints in sqlite",
        "Discuss integrations with billing, audit logs, and release checklist.",
        "Review rollout risks, monitoring notes, and migration steps for operators.",
        "deadline=Friday noon",
        "Confirm support handoff, documentation outline, and change approval path.",
        "repeat goal, owner, constraint, preference, decision, deadline, codeword",
    ]


def test_facts_strategy_stores_key_value_memory(tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="facts",
        context_window_messages=4,
    )
    storage.append_message(session_id, "user", "goal=prepare spec; owner=Maria", token_count=4)
    storage.append_message(session_id, "assistant", "ack", token_count=1)
    storage.append_message(session_id, "user", "decision=store checkpoints in sqlite", token_count=6)

    manager = ContextManager(storage=storage, token_counter=FakeTokenCounter("gpt-4.1-mini"))
    built = manager.build_messages(session_id, storage.load_message_records(session_id))

    facts = storage.list_session_facts(session_id)
    assert [(item.key, item.value) for item in facts] == [
        ("goal", "prepare spec"),
        ("owner", "Maria"),
        ("decision", "store checkpoints in sqlite"),
    ]
    assert any("Stored facts:" in message["content"] for message in built.messages)


def test_context_strategies_compare_quality_and_tokens(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    user_messages = _base_scenario()
    expected_pairs = {
        "goal=prepare technical spec",
        "owner=Maria",
        "constraint=budget below 50k",
        "preference=python cli without new dependencies",
        "decision=store checkpoints in sqlite",
        "deadline=Friday noon",
        "codeword=ALPHA",
    }

    strategies = {
        "sliding": storage.create_session(
            "You are test assistant.",
            token_count=5,
            context_strategy="sliding",
            context_window_messages=4,
        ),
        "facts": storage.create_session(
            "You are test assistant.",
            token_count=5,
            context_strategy="facts",
            context_window_messages=4,
        ),
        "branching": storage.create_session(
            "You are test assistant.",
            token_count=5,
            context_strategy="branching",
            context_window_messages=4,
        ),
    }

    results: dict[str, tuple[str, int, int]] = {}
    for strategy, session_id in strategies.items():
        _run_dialog(monkeypatch, storage, session_id, user_messages)
        records = storage.load_message_records(session_id)
        last_answer = [row.content for row in records if row.role == "assistant"][-1]
        quality = sum(pair in last_answer for pair in expected_pairs)
        prompt_tokens = storage.session_token_stats(session_id).billed_input_tokens
        results[strategy] = (last_answer, quality, prompt_tokens)

    sliding_answer, sliding_quality, sliding_tokens = results["sliding"]
    facts_answer, facts_quality, facts_tokens = results["facts"]
    branching_answer, branching_quality, branching_tokens = results["branching"]

    assert sliding_quality < facts_quality
    assert facts_quality == len(expected_pairs)
    assert branching_quality == len(expected_pairs)

    assert "codeword=UNKNOWN" in sliding_answer
    assert "codeword=ALPHA" in facts_answer
    assert "codeword=ALPHA" in branching_answer

    assert sliding_tokens < facts_tokens < branching_tokens


def test_branching_strategy_switches_independent_branches(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="branching",
        context_window_messages=4,
    )

    _run_dialog(
        monkeypatch,
        storage,
        session_id,
        [
            "goal=compare solutions",
            "database=postgres",
            "/checkpoint base",
            "/branch base option-a",
            "/branch base option-b",
            "/switch option-a",
            "database=sqlite",
            "what database on this branch?",
            "/switch option-b",
            "database=mysql",
            "what database on this branch?",
            "/switch main",
            "what database on this branch?",
            "/branches",
        ],
    )

    storage.switch_branch(session_id, "option-a")
    option_a_answers = [row.content for row in storage.load_message_records(session_id) if row.role == "assistant"]
    storage.switch_branch(session_id, "option-b")
    option_b_answers = [row.content for row in storage.load_message_records(session_id) if row.role == "assistant"]
    storage.switch_branch(session_id, "main")
    main_answers = [row.content for row in storage.load_message_records(session_id) if row.role == "assistant"]

    assert "database=sqlite" in option_a_answers
    assert "database=mysql" in option_b_answers
    assert "database=postgres" in main_answers

    branches = storage.list_branches(session_id)
    assert [branch.name for branch in branches] == ["main", "option-a", "option-b"]
    assert storage.get_active_branch_name(session_id) == "main"
