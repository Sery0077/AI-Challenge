from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from openai import OpenAI


@dataclass(slots=True)
class ResponseUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(slots=True)
class ChatReply:
    text: str
    usage: ResponseUsage | None = None


class ChatModel:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def reply(self, messages: list[dict[str, str]]) -> ChatReply:
        response = self._client.responses.create(
            model=self._model,
            input=messages,
        )

        text = getattr(response, "output_text", None)
        usage = self._extract_usage(response)
        if text:
            return ChatReply(text=text.strip(), usage=usage)

        return ChatReply(text=self._fallback_text(response), usage=usage)

    def reply_stream(
        self,
        messages: list[dict[str, str]],
        on_delta: Callable[[str], None],
    ) -> ChatReply:
        chunks: list[str] = []
        with self._client.responses.stream(
            model=self._model,
            input=messages,
        ) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    delta = event.delta or ""
                    if delta:
                        chunks.append(delta)
                        on_delta(delta)

            final_response = stream.get_final_response()

        final_text = "".join(chunks).strip()
        usage = self._extract_usage(final_response)
        if final_text:
            return ChatReply(text=final_text, usage=usage)

        text = getattr(final_response, "output_text", None)
        if text:
            return ChatReply(text=text.strip(), usage=usage)
        return ChatReply(text=self._fallback_text(final_response), usage=usage)

    @staticmethod
    def _fallback_text(response: Any) -> str:
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    return getattr(content, "text", "").strip()
        return "(empty response)"

    @staticmethod
    def _extract_usage(response: Any) -> ResponseUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        if input_tokens == 0:
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        if output_tokens == 0:
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
            return None
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        return ResponseUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
