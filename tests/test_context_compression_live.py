from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from chat_agent_cli import cli
from chat_agent_cli.config import Settings
from chat_agent_cli.context import ContextManager
from chat_agent_cli.llm import ChatModel
from chat_agent_cli.storage import ChatStorage
from chat_agent_cli.tokens import TokenCounter


@dataclass(slots=True)
class SessionRunResult:
    db_path: str
    session_id: str
    last_answer: str
    billed_input_tokens: int
    billed_output_tokens: int
    summary_count: int


def _build_live_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live test")
    return Settings(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "").strip() or None,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        system_prompt="You are a concise assistant. Keep exact factual memory across turns.",
        storage_path=":memory:",
        model_context_limit=int(os.getenv("MODEL_CONTEXT_LIMIT", "128000")),
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
    )


def _base_messages() -> list[str]:
    return [
        "Контекст проекта: маркетплейс RIVERBANK, релиз в апреле, кодовое слово OAK-741. Запомни это.",
        "Интеграции: Stripe и Adyen. Главный риск: дубли вебхуков и повторное создание инвойса.",
        "Решение: сохраняем provider_event_id, request_id и checksum payload для дедупликации.",
        "Требования: P95 <= 250ms и доля ошибок <= 0.5% на 15-минутном окне.",
        "Безопасность: маскируем email и удаляем PAN-подобные строки из логов.",
        "API change: customer_region обязателен для EU-мерчантов.",
        "Rollout: 10% -> 50% -> 100% при error_rate < 0.3% и стабильном queue lag.",
    ]


def _memory_check_message() -> str:
    return "Контроль памяти: какое кодовое слово было в первом сообщении? Ответь только кодовым словом."


def _run_session(
    *,
    settings: Settings,
    db_path: str,
    context_strategy: str,
    summary_after_user_messages: int,
    with_compact: bool,
) -> SessionRunResult:
    storage = ChatStorage(db_path)
    storage.init()
    token_counter = TokenCounter(settings.model)
    context_manager = ContextManager(storage=storage, token_counter=token_counter)
    model = ChatModel(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
    )
    session_id = storage.create_session(
        settings.system_prompt,
        token_count=token_counter.count_text(settings.system_prompt),
        context_strategy=context_strategy,
        summary_trigger_user_messages=summary_after_user_messages,
    )

    for user_text in _base_messages():
        storage.append_message(
            session_id,
            "user",
            user_text,
            token_count=token_counter.count_text(user_text),
        )
        message_records = storage.load_message_records(session_id)
        built = context_manager.build_messages(
            session_id=session_id,
            message_records=message_records,
        )
        reply = model.reply(built.messages)
        storage.append_message(
            session_id,
            "assistant",
            reply.text,
            token_count=token_counter.count_text(reply.text),
            request_input_tokens=reply.usage.input_tokens if reply.usage else None,
            request_output_tokens=reply.usage.output_tokens if reply.usage else None,
        )

    if with_compact:
        compacted = cli._compact_history_with_llm(
            model=model,
            storage=storage,
            session_id=session_id,
            token_counter=token_counter,
        )
        assert compacted is True

    check_text = _memory_check_message()
    storage.append_message(
        session_id,
        "user",
        check_text,
        token_count=token_counter.count_text(check_text),
    )
    message_records = storage.load_message_records(session_id)
    built = context_manager.build_messages(
        session_id=session_id,
        message_records=message_records,
    )
    reply = model.reply(built.messages)
    storage.append_message(
        session_id,
        "assistant",
        reply.text,
        token_count=token_counter.count_text(reply.text),
        request_input_tokens=reply.usage.input_tokens if reply.usage else None,
        request_output_tokens=reply.usage.output_tokens if reply.usage else None,
    )

    stats = storage.session_token_stats(session_id)
    summaries = storage.list_session_summaries(session_id)
    return SessionRunResult(
        db_path=db_path,
        session_id=session_id,
        last_answer=reply.text,
        billed_input_tokens=stats.billed_input_tokens,
        billed_output_tokens=stats.billed_output_tokens,
        summary_count=len(summaries),
    )


def test_live_context_compact_parallel_real_model(require_live_model_tests) -> None:
    _ = require_live_model_tests
    settings = _build_live_settings()
    db_dir = Path(".chat")
    db_dir.mkdir(parents=True, exist_ok=True)
    full_db = db_dir / "live_context_full.db"
    sum_db = db_dir / "live_context_sum.db"
    if full_db.exists():
        full_db.unlink()
    if sum_db.exists():
        sum_db.unlink()

    with ThreadPoolExecutor(max_workers=2) as executor:
        full_future = executor.submit(
            _run_session,
            settings=settings,
            db_path=str(full_db),
            context_strategy="full",
            summary_after_user_messages=3,
            with_compact=False,
        )
        sum_future = executor.submit(
            _run_session,
            settings=settings,
            db_path=str(sum_db),
            context_strategy="sum",
            summary_after_user_messages=3,
            with_compact=True,
        )
        full_result = full_future.result()
        sum_result = sum_future.result()

    assert "OAK-741" in full_result.last_answer.upper()
    assert "OAK-741" in sum_result.last_answer.upper()
    assert full_result.billed_input_tokens > 0
    assert sum_result.billed_input_tokens > 0
    assert sum_result.billed_input_tokens < full_result.billed_input_tokens
    assert sum_result.summary_count == 1

    report_path = Path(".chat") / "live_context_compare_sessions.txt"
    report_path.write_text(
        "\n".join(
            [
                f"model={settings.model}",
                f"full_db_path={full_result.db_path}",
                f"sum_db_path={sum_result.db_path}",
                f"full_session_id={full_result.session_id}",
                f"sum_session_id={sum_result.session_id}",
                f"full_billed_input_tokens={full_result.billed_input_tokens}",
                f"sum_billed_input_tokens={sum_result.billed_input_tokens}",
                f"full_memory_answer={full_result.last_answer}",
                f"sum_memory_answer={sum_result.last_answer}",
                "summary_trigger_user_messages=3",
                "messages_before_compact=7",
                "compact_used=true",
                "run_mode=parallel_threads",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
