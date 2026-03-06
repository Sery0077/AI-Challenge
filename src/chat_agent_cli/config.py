from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    api_key: str
    base_url: str | None
    model: str
    system_prompt: str
    storage_path: str
    model_context_limit: int
    input_cost_per_1m: float
    output_cost_per_1m: float


def load_settings() -> Settings:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    system_prompt = os.getenv(
        "SYSTEM_PROMPT",
        "You are a practical assistant in a terminal chat.",
    ).strip()
    storage_path = os.getenv("CHAT_STORAGE_PATH", ".chat/history.db").strip()
    model_context_limit = int(os.getenv("MODEL_CONTEXT_LIMIT", "128000").strip())
    input_cost_per_1m = float(os.getenv("INPUT_COST_PER_1M", "0").strip())
    output_cost_per_1m = float(os.getenv("OUTPUT_COST_PER_1M", "0").strip())

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to environment or .env file."
        )

    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        storage_path=storage_path,
        model_context_limit=model_context_limit,
        input_cost_per_1m=input_cost_per_1m,
        output_cost_per_1m=output_cost_per_1m,
    )
