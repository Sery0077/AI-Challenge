from __future__ import annotations

from ..storage import SessionInvariantRecord, TaskStateRecord
from ..text import normalize_text
from .interfaces import PromptBuilder, ResponseValidator, SystemPromptBuilder
from .phases import detect_interaction_phase
from .registry import (
    get_prompt_builders,
    get_response_validators,
    get_system_prompt_builders,
)
from .types import PromptBuildContext, ResponseParseResult, ResponseValidationContext


def build_turn_messages(
    messages: list[dict[str, str]],
    task_state: TaskStateRecord | None,
    invariants: list[SessionInvariantRecord] | None = None,
    system_prompt_builders: list[SystemPromptBuilder] | None = None,
    prompt_builders: list[PromptBuilder] | None = None,
) -> list[dict[str, str]]:
    phase = detect_interaction_phase(task_state)
    context = PromptBuildContext(
        phase=phase,
        task_state=task_state,
        invariants=list(invariants or []),
    )
    built_messages = list(messages)
    extra_system_messages: list[dict[str, str]] = []

    for builder in system_prompt_builders or get_system_prompt_builders():
        if builder.supports_phase(phase):
            extra_system_messages.extend(builder.build_messages(context))

    if extra_system_messages:
        insert_at = 1 if built_messages and built_messages[0]["role"] == "system" else 0
        built_messages = [
            *built_messages[:insert_at],
            *extra_system_messages,
            *built_messages[insert_at:],
        ]

    for builder in prompt_builders or get_prompt_builders():
        if builder.supports_phase(phase):
            built_messages = builder.build_messages(context, built_messages)

    return built_messages


def parse_model_response(
    reply_text: str,
    task_state: TaskStateRecord | None,
    invariants: list[SessionInvariantRecord] | None = None,
    validators: list[ResponseValidator] | None = None,
) -> ResponseParseResult:
    phase = detect_interaction_phase(task_state)
    context = ResponseValidationContext(
        phase=phase,
        task_state=task_state,
        invariants=list(invariants or []),
    )
    result = ResponseParseResult(
        raw_reply_text=normalize_text(reply_text),
        assistant_text=normalize_text(reply_text).strip(),
        task_update=None,
        invariant_check=None,
        contract_violations=(),
    )
    for validator in validators or get_response_validators():
        if validator.supports_phase(phase):
            result = validator.validate(context, result)
    if task_state is None:
        result.task_update = None
    return result
