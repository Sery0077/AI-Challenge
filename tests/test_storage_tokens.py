from __future__ import annotations

from chat_agent_cli.storage import ChatStorage


def _assert_no_surrogates(value: str) -> None:
    assert "\udcd1" not in value
    assert "\udcd2" not in value
    assert "\udcd3" not in value
    assert "\udcd4" not in value
    assert "\udcd5" not in value
    assert "\udcd6" not in value


def test_session_token_stats_and_fill_missing_tokens(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)
    storage.append_message(session_id, "user", "hello", token_count=2)
    storage.append_message(
        session_id,
        "assistant",
        "world",
        token_count=4,
        request_input_tokens=11,
        request_output_tokens=7,
    )
    storage.append_message(session_id, "user", "missing token")  # token_count=None

    updated = storage.fill_missing_token_counts(session_id, lambda text: len(text))
    assert updated == 1

    stats = storage.session_token_stats(session_id)
    assert stats.message_count == 4
    assert stats.system_messages == 1
    assert stats.user_messages == 2
    assert stats.assistant_messages == 1
    assert stats.content_tokens == 3 + 2 + 4 + len("missing token")
    assert stats.system_tokens == 3
    assert stats.user_tokens == 2 + len("missing token")
    assert stats.assistant_tokens == 4
    assert stats.billed_input_tokens == 11
    assert stats.billed_output_tokens == 7
    assert stats.billed_total_tokens == 18


def test_session_model_alias_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session(
        "System prompt",
        token_count=3,
        model_alias="local",
    )

    assert storage.get_session_model_alias(session_id) == "local"

    storage.set_session_model_alias(session_id, "remote")

    assert storage.get_session_model_alias(session_id) == "remote"
    assert storage.list_sessions(limit=1)[0].model_alias == "remote"


def test_storage_sanitizes_surrogates_before_sqlite_write(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session(
        "System \udcd1prompt",
        token_count=3,
        model_alias="lo\udcd2cal",
    )
    storage.append_message(session_id, "user", "Числа \udcd3поездки 10.09-15.09", token_count=5)
    records = storage.load_message_records(session_id)
    user_message_id = records[-1].id
    assert user_message_id is not None

    storage.append_session_summary(
        session_id,
        start_message_id=user_message_id,
        end_message_id=user_message_id,
        summary_text="sum\udcd4mary",
        token_count=4,
    )
    storage.replace_session_facts(
        session_id,
        [("own\udcd5er", "Mar\udcd6ia")],
    )
    storage.replace_working_memory(
        session_id,
        [("task\udcd1", "Book \udcd2flights")],
    )
    storage.replace_long_term_memory(
        session_id,
        [("pref\udcd3erence", "Wind\udcd4ow seat")],
    )
    storage.clear_session(
        session_id,
        "Reset \udcd5prompt",
        token_count=2,
    )

    messages = storage.load_message_records(session_id)
    assert len(messages) == 1
    _assert_no_surrogates(messages[0].content)
    assert "Reset" in messages[0].content

    session = storage.list_sessions(limit=1)[0]
    _assert_no_surrogates(session.title)
    _assert_no_surrogates(session.model_alias or "")

    summary_session_id = storage.create_session("System prompt", token_count=3)
    storage.append_message(summary_session_id, "user", "hello", token_count=2)
    summary_records = storage.load_message_records(summary_session_id)
    summary_message_id = summary_records[-1].id
    assert summary_message_id is not None
    storage.append_session_summary(
        summary_session_id,
        start_message_id=summary_message_id,
        end_message_id=summary_message_id,
        summary_text="sum\udcd1mary",
        token_count=4,
    )
    summary = storage.list_session_summaries(summary_session_id)[0]
    _assert_no_surrogates(summary.content)

    fact_session_id = storage.create_session("System prompt", token_count=3)
    storage.replace_session_facts(
        fact_session_id,
        [("own\udcd2er", "Mar\udcd3ia")],
    )
    fact = storage.list_session_facts(fact_session_id)[0]
    _assert_no_surrogates(fact.key)
    _assert_no_surrogates(fact.value)

    memory_session_id = storage.create_session("System prompt", token_count=3)
    storage.replace_working_memory(
        memory_session_id,
        [("task\udcd4", "Book \udcd5flights")],
    )
    storage.replace_long_term_memory(
        memory_session_id,
        [("pref\udcd6erence", "Wind\udcd1ow seat")],
    )
    working = storage.list_working_memory(memory_session_id)[0]
    long_term = storage.list_long_term_memory(memory_session_id)[0]
    _assert_no_surrogates(working.key)
    _assert_no_surrogates(working.value)
    _assert_no_surrogates(long_term.key)
    _assert_no_surrogates(long_term.value)


def test_storage_sanitizes_branching_write_paths(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session(
        "System prompt",
        token_count=3,
        context_strategy="branching",
    )
    storage.append_message(session_id, "user", "hello", token_count=2)

    checkpoint = storage.create_checkpoint(session_id, "trip\udcd1-plan")
    branch = storage.create_branch(session_id, "trip\udcd1-plan", "opt\udcd2ion-a")
    switched = storage.switch_branch(session_id, "opt\udcd2ion-a")

    _assert_no_surrogates(checkpoint.name)
    _assert_no_surrogates(branch.name)
    _assert_no_surrogates(switched.name)
    _assert_no_surrogates(storage.get_active_branch_name(session_id) or "")

    saved_checkpoint = storage.list_checkpoints(session_id)[0]
    saved_branches = storage.list_branches(session_id)
    assert any(saved.name == "opt?ion-a" for saved in saved_branches)
    _assert_no_surrogates(saved_checkpoint.name)
