from __future__ import annotations

from typing import Protocol

from .types import PromptBuildContext, ResponseParseResult, ResponseValidationContext


class SystemPromptBuilder(Protocol):
    def supports_phase(self, phase: str) -> bool: ...

    def build_messages(self, context: PromptBuildContext) -> list[dict[str, str]]: ...


class PromptBuilder(Protocol):
    def supports_phase(self, phase: str) -> bool: ...

    def build_messages(
        self,
        context: PromptBuildContext,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]: ...


class ResponseValidator(Protocol):
    def supports_phase(self, phase: str) -> bool: ...

    def validate(
        self,
        context: ResponseValidationContext,
        result: ResponseParseResult,
    ) -> ResponseParseResult: ...
