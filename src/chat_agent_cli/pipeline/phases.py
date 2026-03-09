from __future__ import annotations

from ..storage import TaskStateRecord


def detect_interaction_phase(task_state: TaskStateRecord | None) -> str:
    if task_state is None:
        return "default"
    return task_state.stage
