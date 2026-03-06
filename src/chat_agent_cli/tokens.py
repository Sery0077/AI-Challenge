from __future__ import annotations

from dataclasses import dataclass

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None


@dataclass(slots=True)
class ModelPricing:
    input_per_1m: float
    output_per_1m: float

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_1m + output_tokens * self.output_per_1m) / 1_000_000


class TokenCounter:
    def __init__(self, model: str) -> None:
        self._fallback = tiktoken is None
        self._encoder = None
        if tiktoken is None:
            return
        try:
            self._encoder = tiktoken.encoding_for_model(model)
        except KeyError:
            self._encoder = tiktoken.get_encoding("cl100k_base")

    @property
    def fallback(self) -> bool:
        return self._fallback

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        if self._encoder is None:
            # Simple estimate used only when tiktoken is not installed.
            return max(1, len(text) // 4)
        return len(self._encoder.encode(text))

    def count_messages(self, messages: list[dict[str, str]]) -> int:
        # Approximation for Responses API payload (content + small per-message overhead).
        total = 0
        for message in messages:
            total += self.count_text(message.get("content", ""))
            total += 4
        total += 2
        return total
