from __future__ import annotations

from dataclasses import dataclass

from ..storage import SessionInvariantRecord, TaskStateRecord


@dataclass(slots=True)
class ResponseContractViolation:
    code: str
    message: str


@dataclass(slots=True)
class AgentTaskUpdate:
    stage: str
    current_step: str
    expected_action: str
    transition: str
    confirm_prompt: str | None = None


@dataclass(slots=True)
class PromptBuildContext:
    phase: str
    task_state: TaskStateRecord | None
    invariants: list[SessionInvariantRecord]


@dataclass(slots=True)
class InvariantCheckResult:
    status: str
    violated_invariants: tuple[str, ...]
    refusal_reason: str | None = None


@dataclass(slots=True)
class ResponseParseResult:
    raw_reply_text: str
    assistant_text: str
    task_update: AgentTaskUpdate | None
    invariant_check: InvariantCheckResult | None
    contract_violations: tuple[ResponseContractViolation, ...] = ()


@dataclass(slots=True)
class ResponseValidationContext:
    phase: str
    task_state: TaskStateRecord | None
    invariants: list[SessionInvariantRecord]
