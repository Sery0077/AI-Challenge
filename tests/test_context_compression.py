from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from chat_agent_cli import cli
from chat_agent_cli.config import Settings
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
class MemoryAwareFakeModel:
    token_counter: FakeTokenCounter

    def reply_stream(self, messages, on_delta):
        marker = self._extract_marker(messages)
        answer = f"memory_marker={marker}"
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
    def _extract_marker(messages: list[dict[str, str]]) -> str:
        joined = " ".join(message.get("content", "") for message in messages)
        match = re.search(r"codeword=([A-Z0-9_-]+)", joined)
        if match is None:
            return "UNKNOWN"
        return match.group(1)


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
    model = MemoryAwareFakeModel(token_counter=FakeTokenCounter("gpt-4.1-mini"))
    monkeypatch.setattr(cli, "console", fake_console)
    monkeypatch.setattr(cli, "TokenCounter", FakeTokenCounter)
    cli._chat_loop(
        model=model,
        storage=storage,
        session_id=session_id,
        settings=_settings(),
    )


def test_context_compression_quality_and_tokens(monkeypatch, tmp_path) -> None:
    storage = ChatStorage(str(tmp_path / "history.db"))
    storage.init()
    user_messages = [
        "turn01 Context for sprint: project=RIVERBANK, team lead=Maria, and release codeword=ALPHA.",
        "turn02 We process payment webhooks from Stripe and Adyen. Priority is idempotency and retry safety. "
        + ("Validation includes signature checks, stale event filtering, and deterministic retries. " * 4),
        "turn03 Current bug: duplicate invoice gets created when provider retries within 3 seconds. "
        + ("This appears during timeout storms, worker restarts, and delayed queue acknowledgements. " * 4),
        "turn04 Decision: enforce unique key by provider_event_id and store raw payload for audit. "
        + ("Also persist normalized status transitions to simplify reconciliation and postmortems. " * 4),
        "turn05 Non-functional target: P95 webhook processing under 250ms during normal traffic. "
        + ("Load profile assumes burst traffic on campaign days and slower downstream tax service calls. " * 4),
        "turn06 Security note: redact PAN-like sequences from logs and mask customer email usernames. "
        + ("Access to raw payloads is limited to incident responders with explicit audit trail entries. " * 4),
        "turn07 API contract change: field customer_region is required for EU merchants starting next release. "
        + ("Backward compatibility window is two weeks with warnings before strict validation mode. " * 4),
        "turn08 Rollout plan: canary 10%, then 50%, then 100% if error rate stays below 0.3%. "
        + ("Rollback condition includes elevated timeout rate, duplicate events, or queue lag spikes. " * 4),
        "turn09 Observability: add dashboard for duplicate-prevention hits and dead-letter queue size. "
        + ("Alerting should cover error budget burn, saturation, and missing provider callback traffic. " * 4),
        "turn10 Communication: publish migration guide and notify support one week before release. "
        + ("Support runbook needs customer-facing templates and escalation matrix for on-call engineers. " * 4),
        "turn11 final check: what is my release codeword from the beginning?",
    ]

    full_session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="full",
    )
    sum_session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sum",
        summary_trigger_user_messages=5,
    )

    _run_dialog(monkeypatch, storage, full_session_id, user_messages)
    _run_dialog(monkeypatch, storage, sum_session_id, user_messages)

    full_records = storage.load_message_records(full_session_id)
    sum_records = storage.load_message_records(sum_session_id)
    full_last_answer = [r.content for r in full_records if r.role == "assistant"][-1]
    sum_last_answer = [r.content for r in sum_records if r.role == "assistant"][-1]
    assert "memory_marker=ALPHA" in full_last_answer
    assert "memory_marker=ALPHA" in sum_last_answer
    assert sum_last_answer == full_last_answer

    full_stats = storage.session_token_stats(full_session_id)
    sum_stats = storage.session_token_stats(sum_session_id)
    assert sum_stats.billed_input_tokens < full_stats.billed_input_tokens
    assert len(storage.list_session_summaries(sum_session_id)) >= 1


def test_context_compression_two_sessions_keeps_history_for_manual_inspection(monkeypatch) -> None:
    db_path = Path(".chat") / "context_compare_history.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    storage = ChatStorage(str(db_path))
    storage.init()
    user_messages = [
        "msg01 Project brief: RIVERBANK checkout revamp, owner is Maria, release codeword=ALPHA.",
        "msg02 Scope: unify webhook handlers for Stripe and Adyen and reduce duplicate invoice creation. "
        + ("Coverage includes signature validation, replay defense, and deterministic error classification. " * 4),
        "msg03 Incident detail: duplicates happen when retries arrive quickly after timeout on provider side. "
        + ("Symptoms include invoice spikes, delayed acknowledgements, and inconsistent reconciliation totals. " * 4),
        "msg04 Data decision: persist provider_event_id and reject replays with deterministic response. "
        + ("Store both raw and normalized payload snapshots to support audits and incident forensics. " * 4),
        "msg05 Reliability SLO: keep failed webhook ratio below 0.5% and P95 latency below 250ms. "
        + ("Peak traffic assumptions include promotions, batch settlements, and delayed callback bursts. " * 4),
        "msg06 Compliance: mask emails in logs and remove any card-like number patterns before storage. "
        + ("Restrict payload visibility to approved responders and record every privileged access event. " * 4),
        "msg07 API update: make customer_region mandatory for EU merchants in v2 endpoint. "
        + ("Deprecation notice should be visible in docs, changelog, and partner communication emails. " * 4),
        "msg08 Rollout: 10% canary, 50% partial, 100% full rollout if alert thresholds remain green. "
        + ("Stop rollout when timeout, duplicate rejection anomalies, or queue lag exceeds threshold. " * 4),
        "msg09 Monitoring: track replay rejections, queue lag, and handler timeout distribution. "
        + ("Dashboards should include burn rate, saturation, dependency error spikes, and callback gaps. " * 4),
        "msg10 Release ops: send migration guide, changelog, and support script before deployment day. "
        + ("Prepare incident templates, customer FAQ, and on-call escalation map for launch week. " * 4),
        "msg11 check memory: repeat my codeword from msg01",
    ]

    full_session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="full",
    )
    sum_session_id = storage.create_session(
        "You are test assistant.",
        token_count=5,
        context_strategy="sum",
        summary_trigger_user_messages=5,
    )

    _run_dialog(monkeypatch, storage, full_session_id, user_messages)
    _run_dialog(monkeypatch, storage, sum_session_id, user_messages)

    full_records = storage.load_message_records(full_session_id)
    sum_records = storage.load_message_records(sum_session_id)
    full_last_answer = [r.content for r in full_records if r.role == "assistant"][-1]
    sum_last_answer = [r.content for r in sum_records if r.role == "assistant"][-1]

    assert "memory_marker=ALPHA" in full_last_answer
    assert "memory_marker=ALPHA" in sum_last_answer

    full_stats = storage.session_token_stats(full_session_id)
    sum_stats = storage.session_token_stats(sum_session_id)
    assert sum_stats.billed_input_tokens < full_stats.billed_input_tokens
    assert len(storage.list_session_summaries(sum_session_id)) >= 2

    sessions_path = Path(".chat") / "context_compare_sessions.txt"
    sessions_path.write_text(
        "\n".join(
            [
                f"db_path={db_path}",
                f"full_session_id={full_session_id}",
                f"sum_session_id={sum_session_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
