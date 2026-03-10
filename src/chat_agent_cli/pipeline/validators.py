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
from .types import (
    AgentTaskUpdate,
    InvariantCheckResult,
    ResponseContractViolation,
    ResponseParseResult,
    ResponseValidationContext,
)


def _with_updates(
    result: ResponseParseResult,
    *,
    assistant_text: str | None = None,
    task_update: AgentTaskUpdate | None = None,
    invariant_check: InvariantCheckResult | None = None,
) -> ResponseParseResult:
    return ResponseParseResult(
        raw_reply_text=result.raw_reply_text,
        assistant_text=result.assistant_text if assistant_text is None else assistant_text,
        task_update=result.task_update if task_update is None else task_update,
        invariant_check=result.invariant_check if invariant_check is None else invariant_check,
        contract_violations=result.contract_violations,
    )


def _extract_task_protocol_fields(normalized_reply: str) -> tuple[str, dict[str, str]]:
    match = task_protocol_pattern().search(normalized_reply)
    if match is None:
        return normalized_reply, {}

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
    return normalized_reply[: match.start()].strip(), fields


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
        visible_text, fields = _extract_task_protocol_fields(normalized_reply)
        if not fields:
            return ResponseParseResult(
                raw_reply_text=normalized_reply,
                assistant_text=visible_text,
                task_update=result.task_update,
                invariant_check=result.invariant_check,
                contract_violations=result.contract_violations,
            )

        stage = fields.get("stage")
        current_step = fields.get("current_step")
        expected_action = fields.get("expected_action")
        transition = fields.get("transition", "").lower()
        parsed_result = ResponseParseResult(
            raw_reply_text=normalized_reply,
            assistant_text=visible_text,
            task_update=result.task_update,
            invariant_check=result.invariant_check,
            contract_violations=result.contract_violations,
        )
        if stage is None or current_step is None or expected_action is None:
            return parsed_result
        if transition not in {"auto", "confirm"}:
            return parsed_result
        confirm_prompt = fields.get("confirm_prompt")
        if transition == "confirm" and not confirm_prompt:
            return parsed_result

        invariant_status = fields.get("invariants_status", "").lower()
        if invariant_status:
            violated_raw = fields.get("violated_invariants", "none")
            violated = tuple(
                item.strip()
                for item in violated_raw.split(",")
                if item.strip() and item.strip().lower() != "none"
            )
            refusal_reason = fields.get("refusal_reason")
            parsed_result.invariant_check = InvariantCheckResult(
                status=invariant_status,
                violated_invariants=violated,
                refusal_reason=refusal_reason,
            )

        parsed_result.task_update = AgentTaskUpdate(
            stage=stage,
            current_step=current_step,
            expected_action=expected_action,
            transition=transition,
            confirm_prompt=confirm_prompt,
        )
        return parsed_result


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
            return _with_updates(
                result,
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
            return _with_updates(
                result,
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
            return _with_updates(
                result,
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
            return _with_updates(
                result,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="planning",
                    current_step=task_state.current_step,
                    expected_action="Answer the open planning questions",
                    transition="auto",
                ),
            )

        return _with_updates(result, assistant_text=normalized)


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
            return _with_updates(
                result,
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
            return _with_updates(
                result,
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
            return _with_updates(
                result,
                assistant_text=normalized,
                task_update=AgentTaskUpdate(
                    stage="execution",
                    current_step=current_step,
                    expected_action=expected_action,
                    transition="auto",
                ),
            )

        return result


class InvariantConflictValidator:
    def supports_phase(self, phase: str) -> bool:
        return phase != "default"

    def validate(
        self,
        context: ResponseValidationContext,
        result: ResponseParseResult,
    ) -> ResponseParseResult:
        if not context.invariants:
            return result

        invariant_check = result.invariant_check
        if invariant_check is None:
            if result.task_update is None:
                return result
            task_state = context.task_state
            if task_state is None:
                return result
            assistant_text = normalize_text(result.assistant_text).strip()
            explanation = (
                "I can't continue because the response did not confirm compliance "
                "with the active invariants."
            )
            if explanation not in assistant_text:
                assistant_text = "\n".join(part for part in (assistant_text, explanation) if part)
            return _with_updates(
                result,
                assistant_text=assistant_text,
                task_update=AgentTaskUpdate(
                    stage=task_state.stage,
                    current_step=task_state.current_step,
                    expected_action="Revise the request so it satisfies the active invariants",
                    transition="auto",
                ),
            )

        if invariant_check.status == "satisfied":
            return result

        if invariant_check.status != "conflict":
            return result

        task_state = context.task_state
        refusal_reason = invariant_check.refusal_reason or "The request conflicts with the active invariants."
        violated_summary = ", ".join(invariant_check.violated_invariants)
        if violated_summary:
            explanation = f"{refusal_reason} Violated invariants: {violated_summary}."
        else:
            explanation = refusal_reason

        assistant_text = normalize_text(result.assistant_text).strip()
        if explanation not in assistant_text:
            assistant_text = "\n".join(part for part in (assistant_text, explanation) if part)

        if task_state is None:
            return _with_updates(
                result,
                assistant_text=assistant_text,
                task_update=None,
            )

        return _with_updates(
            result,
            assistant_text=assistant_text,
            task_update=AgentTaskUpdate(
                stage=task_state.stage,
                current_step=task_state.current_step,
                expected_action="Revise the request so it satisfies the active invariants",
                transition="auto",
            ),
        )


class ResponseContractValidator:
    _ALLOWED_STAGE_TRANSITIONS = {
        "planning": frozenset({"planning", "execution"}),
        "execution": frozenset({"execution", "validation"}),
        "validation": frozenset({"validation", "done"}),
        "done": frozenset({"done", "planning"}),
    }

    def supports_phase(self, phase: str) -> bool:
        return phase != "default"

    def validate(
        self,
        context: ResponseValidationContext,
        result: ResponseParseResult,
    ) -> ResponseParseResult:
        task_state = context.task_state
        if task_state is None:
            return result

        violations: list[ResponseContractViolation] = list(result.contract_violations)
        normalized_reply = normalize_text(result.raw_reply_text).strip()
        _visible_text, fields = _extract_task_protocol_fields(normalized_reply)
        if not fields:
            violations.append(
                ResponseContractViolation(
                    code="required_metadata",
                    message=(
                        "В ответе отсутствует обязательный metadata-блок <<TASK_STATE>> "
                        "с описанием состояния задачи."
                    ),
                )
            )
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=result.assistant_text,
                task_update=result.task_update,
                invariant_check=result.invariant_check,
                contract_violations=tuple(violations),
            )

        required_fields = ("stage", "current_step", "expected_action", "transition")
        missing_fields = [field for field in required_fields if not fields.get(field)]
        if missing_fields:
            violations.append(
                ResponseContractViolation(
                    code="required_metadata",
                    message=(
                        "В metadata-блоке отсутствуют обязательные поля: "
                        + ", ".join(missing_fields)
                        + "."
                    ),
                )
            )

        transition = fields.get("transition", "").lower()
        if transition == "confirm" and not fields.get("confirm_prompt"):
            violations.append(
                ResponseContractViolation(
                    code="required_metadata",
                    message=(
                        "В metadata-блоке для transition=confirm отсутствует поле confirm_prompt."
                    ),
                )
            )

        if missing_fields:
            return ResponseParseResult(
                raw_reply_text=result.raw_reply_text,
                assistant_text=result.assistant_text,
                task_update=result.task_update,
                invariant_check=result.invariant_check,
                contract_violations=tuple(violations),
            )

        next_stage = fields.get("stage", "").lower()
        allowed = self._ALLOWED_STAGE_TRANSITIONS.get(task_state.stage, frozenset())
        if next_stage not in allowed:
            violations.append(
                ResponseContractViolation(
                    code="valid_task_transition",
                    message=(
                        f"Переход состояния {task_state.stage} -> {next_stage or 'UNKNOWN'} "
                        "недопустим для текущей task state machine."
                    ),
                )
            )

        return ResponseParseResult(
            raw_reply_text=result.raw_reply_text,
            assistant_text=result.assistant_text,
            task_update=result.task_update,
            invariant_check=result.invariant_check,
            contract_violations=tuple(violations),
        )
