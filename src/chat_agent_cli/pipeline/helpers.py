from __future__ import annotations

import re

from ..text import normalize_text

_TASK_PROTOCOL_RE = re.compile(
    r"<<TASK_STATE>>\s*(?P<body>.*?)\s*<<END_TASK_STATE>>\s*$",
    re.DOTALL,
)
_PLANNING_APPROVAL_HINTS = (
    "approve",
    "approval",
    "подтверд",
    "соглас",
    "хочешь",
    "могу сразу",
    "сразу сгенерировать",
    "перейти к реализации",
    "move to execution",
    "ready to implement",
)
_PLANNING_QUESTION_HINTS = (
    "уточ",
    "какой",
    "какая",
    "какие",
    "где",
    "нужно ли",
    "требуется ли",
    "подскаж",
    "which",
    "what",
    "where",
    "do you need",
)


def task_protocol_pattern() -> re.Pattern[str]:
    return _TASK_PROTOCOL_RE


def planning_approval_hints() -> tuple[str, ...]:
    return _PLANNING_APPROVAL_HINTS


def planning_question_hints() -> tuple[str, ...]:
    return _PLANNING_QUESTION_HINTS


def extract_first_actionable_line(text: str) -> str | None:
    for raw_line in normalize_text(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if not line:
            continue
        if len(line) > 120:
            line = line[:117].rstrip() + "..."
        return line
    return None


def extract_section_value(text: str, header: str) -> str | None:
    normalized = normalize_text(text)
    pattern = re.compile(
        rf"(?mi)^{re.escape(header)}:\s*\n(?P<body>.*?)(?=^\S[\S ]*:\s*$|\Z)",
        re.DOTALL,
    )
    match = pattern.search(normalized)
    if match is None:
        return None
    body = match.group("body").strip()
    if not body:
        return None
    return body


def extract_readiness_value(text: str, header: str) -> str | None:
    section = extract_section_value(text, header)
    if section is None:
        return None
    for raw_line in section.splitlines():
        line = normalize_text(raw_line).strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        if line:
            return line
    return None
