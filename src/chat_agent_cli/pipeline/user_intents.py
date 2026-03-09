from __future__ import annotations

from dataclasses import dataclass

from ..storage import TaskStateRecord
from ..text import normalize_text
from .phases import detect_interaction_phase

_TASK_COMPLETION_HINTS = (
    "всё работает",
    "все работает",
    "всё ок",
    "все ок",
    "готово",
    "сработало",
    "работает",
    "thanks, it works",
    "it works",
    "works now",
)
_TASK_COMPLETION_CLOSERS = (
    "спасибо",
    "thanks",
    "thank you",
)


@dataclass(slots=True)
class UserIntentContext:
    phase: str
    task_state: TaskStateRecord | None


@dataclass(slots=True)
class UserIntentResult:
    action: str
    reason: str | None = None


class UserIntentParser:
    def supports_phase(self, phase: str) -> bool:
        return True

    def parse(
        self,
        context: UserIntentContext,
        user_text: str,
    ) -> UserIntentResult | None:
        raise NotImplementedError


class ExecutionCompletionIntentParser(UserIntentParser):
    def supports_phase(self, phase: str) -> bool:
        return phase == "execution"

    def parse(
        self,
        context: UserIntentContext,
        user_text: str,
    ) -> UserIntentResult | None:
        task_state = context.task_state
        if task_state is None or task_state.awaiting_confirmation or task_state.is_paused:
            return None

        normalized = normalize_text(user_text).strip().lower()
        if not normalized:
            return None
        if normalized in {"done", "completed"}:
            return UserIntentResult(
                action="complete_task",
                reason="User confirmed that the execution result is complete.",
            )
        if any(hint in normalized for hint in _TASK_COMPLETION_HINTS):
            return UserIntentResult(
                action="complete_task",
                reason="User confirmed that the execution result works.",
            )
        if any(closer in normalized for closer in _TASK_COMPLETION_CLOSERS) and any(
            word in normalized for word in ("работ", "work", "done", "готов")
        ):
            return UserIntentResult(
                action="complete_task",
                reason="User confirmed completion together with a closing acknowledgement.",
            )
        return None


USER_INTENT_PARSERS: list[UserIntentParser] = [
    ExecutionCompletionIntentParser(),
]


def get_user_intent_parsers() -> list[UserIntentParser]:
    return list(USER_INTENT_PARSERS)


def parse_user_intent(
    task_state: TaskStateRecord | None,
    user_text: str,
    parsers: list[UserIntentParser] | None = None,
) -> UserIntentResult | None:
    phase = detect_interaction_phase(task_state)
    context = UserIntentContext(phase=phase, task_state=task_state)
    for parser in parsers or get_user_intent_parsers():
        if parser.supports_phase(phase):
            result = parser.parse(context, user_text)
            if result is not None:
                return result
    return None
