from __future__ import annotations

from ..text import normalize_text
from .helpers import (
    extract_first_actionable_line,
    extract_readiness_value,
    extract_section_value,
    planning_approval_hints,
    planning_question_hints,
    task_protocol_pattern,
)
from .types import AgentTaskUpdate, ResponseParseResult, ResponseValidationContext


class MetadataTaskUpdateValidator:
    def supports_phase(self, phase: str) -> bool:
        return phase != "default"

    def validate(
        self,
        context: ResponseValidationContext,
        result: ResponseParseResult,
    ) -> ResponseParseResult:
        del context
        normalized_reply = normalize_text(result.raw_reply_text).strip()
        match = task_protocol_pattern().search(normalized_reply)
        if match is None:
            return ResponseParseResult(
                raw_reply_text=normalized_reply,
                assistant_text=normalized_reply,
                task_update=result.task_update,
            )

        fields: dict[str, str] = {}
        for raw_line in match.group("body").splitlines():
            line = normalize_text(raw_line).strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            normalized_key = normalize_text(key).strip().lower()
            normalized_value = normalize_text(value).strip()
            if normalized_value:
                fields[normalized_key] = normalized_value

        visible_text = normalized_reply[: match.start()].strip()
        stage = fields.get("stage")
        current_step = fields.get("current_step")
        expected_action = fields.get("expected_action")
        transition = fields.get("transition", "").lower()
        if stage is None or current_step is None or expected_action is None:
            return ResponseParseResult(
                raw_reply_text=normalized_reply,
                assistant_text=visible_text,
                task_update=result.task_update,
            )
        if transition not in {"auto", "confirm"}:
            return ResponseParseResult(
                raw_reply_text=normalized_reply,
                assistant_text=visible_text,
                task_update=result.task_update,
            )
        confirm_prompt = fields.get("confirm_prompt")
        if transition == "confirm" and not confirm_prompt:
            return ResponseParseResult(
                raw_reply_text=normalized_reply,
                assistant_text=visible_text,
                task_update=result.task_update,
            )
        return ResponseParseResult(
            raw_reply_text=normalized_reply,
            assistant_text=visible_text,
            task_update=AgentTaskUpdate(
                stage=stage,
                current_step=current_step,
                expected_action=expected_action,
                transition=transition,
                confirm_prompt=confirm_prompt,
            ),
        )


class PlanningPlainTextTaskUpdateValidator:
    def supports_phase(self, phase: str) -> bool:
        return phase == "planning"

    def validate(
        self,
        context: ResponseValidationContext,
        result: ResponseParseResult,
    ) -> ResponseParseResult:
        task_state = context.task_state
        if task_state is None or task_state.awaiting_confirmation:
            return result
        if result.task_update is not None:
            return result

        normalized = normalize_text(result.assistant_text).strip()
        if not normalized:
            return result
        lowered = normalized.lower()
        has_question = "?" in normalized
        readiness = extract_readiness_value(normalized, "READINESS")
        plan_section = extract_section_value(normalized, "PLAN")
        approval_requested = any(hint in lowered for hint in planning_approval_hints())
        asks_for_clarification = has_question and any(
            hint in lowered for hint in planning_question_hints()
        )

        if readiness == "READY_FOR_EXECUTION":
            current_step = extract_first_actionable_line(plan_section or normalized)
            if current_step is None:
                current_step = "Start implementing the approved plan"
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="execution",
                    current_step=current_step,
                    expected_action="Execute the approved plan and report progress",
                    transition="confirm",
                    confirm_prompt="Approve the proposed plan and move to execution?",
                ),
            )

        if readiness == "NEEDS_CLARIFICATION":
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="planning",
                    current_step=task_state.current_step,
                    expected_action="Answer the open planning questions",
                    transition="auto",
                ),
            )

        if approval_requested:
            current_step = extract_first_actionable_line(normalized)
            if current_step is None:
                current_step = "Start implementing the approved plan"
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="execution",
                    current_step=current_step,
                    expected_action="Execute the approved plan and report progress",
                    transition="confirm",
                    confirm_prompt="Approve the proposed plan and move to execution?",
                ),
            )

        if asks_for_clarification:
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="planning",
                    current_step=task_state.current_step,
                    expected_action="Answer the open planning questions",
                    transition="auto",
                ),
            )

        return ResponseParseResult(
            raw_reply_text=result.raw_reply_text,
            assistant_text=normalized,
            task_update=result.task_update,
        )


class ExecutionStructuredTaskUpdateValidator:
    def supports_phase(self, phase: str) -> bool:
        return phase == "execution"

    def validate(
        self,
        context: ResponseValidationContext,
        result: ResponseParseResult,
    ) -> ResponseParseResult:
        task_state = context.task_state
        if task_state is None or task_state.awaiting_confirmation:
            return result
        if result.task_update is not None:
            return result

        normalized = normalize_text(result.assistant_text).strip()
        if not normalized:
            return result
        readiness = extract_readiness_value(normalized, "VALIDATION_READINESS")
        next_section = extract_section_value(normalized, "NEXT")
        progress_section = extract_section_value(normalized, "PROGRESS")
        blockers_section = extract_section_value(normalized, "BLOCKERS")

        if readiness == "READY_FOR_VALIDATION":
            current_step = extract_first_actionable_line(progress_section or normalized)
            if current_step is None:
                current_step = task_state.current_step
            expected_action = extract_first_actionable_line(next_section or "")
            if expected_action is None:
                expected_action = "Validate the completed implementation"
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="validation",
                    current_step=current_step,
                    expected_action=expected_action,
                    transition="auto",
                ),
            )

        if readiness == "NEEDS_INPUT":
            expected_action = extract_first_actionable_line(blockers_section or next_section or "")
            if expected_action is None:
                expected_action = "Provide the missing input needed to continue execution"
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="execution",
                    current_step=task_state.current_step,
                    expected_action=expected_action,
                    transition="auto",
                ),
            )

        if readiness == "IN_PROGRESS":
            current_step = extract_first_actionable_line(progress_section or task_state.current_step)
            expected_action = extract_first_actionable_line(next_section or "")
            if current_step is None:
                current_step = task_state.current_step
            if expected_action is None:
                expected_action = task_state.expected_action
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="execution",
                    current_step=current_step,
                    expected_action=expected_action,
                    transition="auto",
                ),
            )

        return result
