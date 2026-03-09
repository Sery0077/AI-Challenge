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
    storage.set_task_state(
        session_id,
        "planning",
        "Collect \udcd6requirements",
        "Prepare \udcd1implementation plan",
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

    task_session_id = storage.create_session("System prompt", token_count=3)
    storage.set_task_state(
        task_session_id,
        "execution",
        "Implement \udcd2task state",
        "Run \udcd3targeted tests",
    )
    task_state = storage.get_task_state(task_session_id)
    assert task_state is not None
    _assert_no_surrogates(task_state.current_step)
    _assert_no_surrogates(task_state.expected_action)


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


def test_task_state_roundtrip_and_pause_flow(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)

    planning = storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Inspect relevant files",
    )
    assert planning.stage == "planning"
    assert planning.is_paused is False

    paused_planning = storage.pause_task(session_id, "Wait for resume")
    assert paused_planning.stage == "planning"
    assert paused_planning.is_paused is True

    resumed_planning = storage.resume_task(session_id, "Start implementation")
    assert resumed_planning.is_paused is False
    assert resumed_planning.expected_action == "Start implementation"

    execution = storage.advance_task_state(
        session_id,
        current_step="Implement storage for task state",
        expected_action="Wire task state into prompt context",
    )
    assert execution.stage == "execution"
    assert execution.is_paused is False

    paused_execution = storage.pause_task(session_id)
    assert paused_execution.stage == "execution"
    assert paused_execution.is_paused is True

    resumed_execution = storage.resume_task(session_id, "Validate pause and resume")
    assert resumed_execution.stage == "execution"
    assert resumed_execution.is_paused is False

    validation = storage.advance_task_state(
        session_id,
        current_step="Run targeted tests",
        expected_action="Confirm resume works without repeated context",
    )
    assert validation.stage == "validation"

    paused_validation = storage.pause_task(session_id)
    assert paused_validation.stage == "validation"
    assert paused_validation.is_paused is True

    done = storage.advance_task_state(
        session_id,
        current_step="Ship the change",
        expected_action="No further action",
    )
    assert done.stage == "done"
    assert done.is_paused is False

    stored = storage.get_task_state(session_id)
    assert stored is not None
    assert stored.stage == "done"
    assert stored.current_step == "Ship the change"
    assert stored.expected_action == "No further action"
    assert stored.awaiting_confirmation is False


def test_task_state_pending_transition_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Prepare the first execution step",
    )

    proposed = storage.propose_task_state_transition(
        session_id,
        stage="execution",
        current_step="Implement automatic task transitions",
        expected_action="Validate the resumed flow",
        confirmation_prompt="Move the task to execution?",
    )
    assert proposed.stage == "planning"
    assert proposed.is_paused is True
    assert proposed.awaiting_confirmation is True
    assert proposed.pending_stage == "execution"

    stored = storage.get_task_state(session_id)
    assert stored is not None
    assert stored.pending_current_step == "Implement automatic task transitions"
    assert stored.pending_expected_action == "Validate the resumed flow"
    assert stored.pending_confirmation_prompt == "Move the task to execution?"

    approved = storage.approve_pending_task_transition(session_id)
    assert approved.stage == "execution"
    assert approved.current_step == "Implement automatic task transitions"
    assert approved.expected_action == "Validate the resumed flow"
    assert approved.awaiting_confirmation is False

    storage.propose_task_state_transition(
        session_id,
        stage="validation",
        current_step="Run targeted tests",
        expected_action="Ship the change",
        confirmation_prompt="Move the task to validation?",
    )
    rejected = storage.reject_pending_task_transition(
        session_id,
        expected_action="Revise execution after rejection",
    )
    assert rejected.stage == "execution"
    assert rejected.expected_action == "Revise execution after rejection"
    assert rejected.awaiting_confirmation is False


def test_task_state_rejects_invalid_transition(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)
    storage.set_task_state(
        session_id,
        stage="planning",
        current_step="Clarify the task scope",
        expected_action="Inspect relevant files",
    )

    try:
        storage.set_task_state(
            session_id,
            stage="validation",
            current_step="Skip execution",
            expected_action="This should fail",
        )
    except ValueError as exc:
        assert "Invalid task stage transition" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected invalid task stage transition to fail")


def test_task_state_rejects_invalid_pending_transition(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)

    try:
        storage.set_task_state(
            session_id,
            stage="planning",
            current_step="Clarify the task scope",
            expected_action="Inspect relevant files",
            pending_stage="done",
            pending_current_step="Skip straight to the end",
            pending_expected_action="No further action",
            pending_confirmation_prompt="Finish immediately?",
        )
    except ValueError as exc:
        assert "Invalid task stage transition" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected invalid pending task transition to fail")


def test_replace_task_state_overwrites_active_task(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement old task",
        expected_action="Ship old task",
        is_paused=True,
        pending_stage="validation",
        pending_current_step="Run tests",
        pending_expected_action="Ship old task",
        pending_confirmation_prompt="Move to validation?",
    )

    replaced = storage.replace_task_state(
        session_id,
        stage="planning",
        current_step="Start replacement task",
        expected_action="Clarify requirements",
    )
    assert replaced.stage == "planning"
    assert replaced.current_step == "Start replacement task"
    assert replaced.expected_action == "Clarify requirements"
    assert replaced.is_paused is False
    assert replaced.awaiting_confirmation is False

    stored = storage.get_task_state(session_id)
    assert stored is not None
    assert stored.stage == "planning"
    assert stored.pending_stage is None


def test_complete_task_forces_done_from_active_stage(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    storage = ChatStorage(str(db_path))
    storage.init()

    session_id = storage.create_session("System prompt", token_count=3)
    storage.set_task_state(
        session_id,
        stage="execution",
        current_step="Implement feature",
        expected_action="Run tests",
    )

    completed = storage.complete_task(session_id)
    assert completed.stage == "done"
    assert completed.current_step == "Implement feature"
    assert completed.expected_action == "No further action"
    assert completed.awaiting_confirmation is False
