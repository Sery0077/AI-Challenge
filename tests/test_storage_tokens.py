from __future__ import annotations

from chat_agent_cli.storage import ChatStorage


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
