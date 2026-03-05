from __future__ import annotations

from typing import Any

from openai import OpenAI


class ChatModel:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def reply(self, messages: list[dict[str, str]]) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=messages,
        )

        text = getattr(response, "output_text", None)
        if text:
            return text.strip()

        return self._fallback_text(response)

    @staticmethod
    def _fallback_text(response: Any) -> str:
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    return getattr(content, "text", "").strip()
        return "(empty response)"
