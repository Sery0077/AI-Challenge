from __future__ import annotations

from .builders import (
    ExecutionStageSystemPromptBuilder,
    MergeSystemMessagesBuilder,
    PlanningStageSystemPromptBuilder,
    TaskProtocolSystemPromptBuilder,
)
from .interfaces import PromptBuilder, ResponseValidator, SystemPromptBuilder
from .validators import (
    ExecutionStructuredTaskUpdateValidator,
    MetadataTaskUpdateValidator,
    PlanningPlainTextTaskUpdateValidator,
)

SYSTEM_PROMPT_BUILDERS: list[SystemPromptBuilder] = [
    PlanningStageSystemPromptBuilder(),
    ExecutionStageSystemPromptBuilder(),
    TaskProtocolSystemPromptBuilder(),
]
PROMPT_BUILDERS: list[PromptBuilder] = [MergeSystemMessagesBuilder()]
RESPONSE_VALIDATORS: list[ResponseValidator] = [
    MetadataTaskUpdateValidator(),
    PlanningPlainTextTaskUpdateValidator(),
    ExecutionStructuredTaskUpdateValidator(),
]


def get_system_prompt_builders() -> list[SystemPromptBuilder]:
    return list(SYSTEM_PROMPT_BUILDERS)


def get_prompt_builders() -> list[PromptBuilder]:
    return list(PROMPT_BUILDERS)


def get_response_validators() -> list[ResponseValidator]:
    return list(RESPONSE_VALIDATORS)
