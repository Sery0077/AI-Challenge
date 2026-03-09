from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(slots=True)
class AppSettings:
    system_prompt: str
    storage_path: str
    user_profile_path: str


@dataclass(slots=True)
class ModelProfile:
    alias: str
    api_key: str
    base_url: str | None
    model: str
    model_context_limit: int
    input_cost_per_1m: float
    output_cost_per_1m: float


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
    model_alias: str | None = None
    available_model_aliases: tuple[str, ...] = ()


def _default_agent_dir() -> Path:
    return Path.home() / ".chat-agent"


def load_app_settings() -> AppSettings:
    load_dotenv()

    system_prompt = os.getenv(
        "SYSTEM_PROMPT",
        (
            "Ты практичный ассистент для работы в терминальном чат-агенте.\n"
            "Отвечай по существу, не пересказывай лишнее и не выдумывай сделанную работу.\n"
            "Если активной задачи нет, помогай как обычный ассистент и отвечай на текущий запрос пользователя.\n"
            "Если в контексте есть активная задача, следуй текущей стадии задачи, состоянию задачи и последним пользовательским инструкциям.\n"
            "Task flow:\n"
            "- На стадии planning сначала собери недостающие вводные, затем предложи короткий практичный план.\n"
            "- На стадии planning не начинай реализацию, пока план не согласован, если задача не совсем тривиальна и полностью определена.\n"
            "- Когда план готов, явно попроси подтверждение перед переходом к выполнению.\n"
            "- На стадии execution выполняй уже согласованный план, двигай задачу вперёд и не возвращайся к широкому планированию без причины.\n"
            "- Если пользователь меняет требования, адаптируй дальнейшие действия под новые вводные.\n"
            "- Если данных недостаточно, сначала задай точные уточняющие вопросы.\n"
            "- Если задача фактически завершена, явно скажи, что сделано и что осталось проверить или подтвердить."
        ),
    ).strip()
    storage_path = os.getenv(
        "CHAT_STORAGE_PATH",
        str(_default_agent_dir() / "history.db"),
    ).strip()
    user_profile_path = os.getenv(
        "CHAT_USER_PROFILE_PATH",
        str(_default_agent_dir() / "user_profile.json"),
    ).strip()
    return AppSettings(
        system_prompt=system_prompt,
        storage_path=storage_path,
        user_profile_path=user_profile_path,
    )


def load_settings(selected_model: str | None = None) -> Settings:
    app_settings = load_app_settings()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    env_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    model_context_limit = int(os.getenv("MODEL_CONTEXT_LIMIT", "128000").strip())
    input_cost_per_1m = float(os.getenv("INPUT_COST_PER_1M", "0").strip())
    output_cost_per_1m = float(os.getenv("OUTPUT_COST_PER_1M", "0").strip())
    models_path = os.getenv(
        "CHAT_MODELS_PATH",
        str(_default_agent_dir() / "models.toml"),
    ).strip()

    profiles, configured_default = _load_model_profiles(
        path=Path(models_path),
        default_context_limit=model_context_limit,
        default_input_cost=input_cost_per_1m,
        default_output_cost=output_cost_per_1m,
    )
    available_aliases = tuple(profiles.keys())

    if profiles:
        target_alias = selected_model or os.getenv("CHAT_DEFAULT_MODEL", "").strip() or configured_default
        if not target_alias:
            target_alias = available_aliases[0]
        profile = profiles.get(target_alias)
        if profile is None:
            raise ValueError(
                f"Model profile '{target_alias}' not found. Available profiles: "
                + ", ".join(available_aliases)
            )
        return Settings(
            api_key=profile.api_key,
            base_url=profile.base_url,
            model=profile.model,
            system_prompt=app_settings.system_prompt,
            storage_path=app_settings.storage_path,
            model_context_limit=profile.model_context_limit,
            input_cost_per_1m=profile.input_cost_per_1m,
            output_cost_per_1m=profile.output_cost_per_1m,
            model_alias=profile.alias,
            available_model_aliases=available_aliases,
        )

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to environment or .env file."
        )

    model = selected_model or env_model
    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=app_settings.system_prompt,
        storage_path=app_settings.storage_path,
        model_context_limit=model_context_limit,
        input_cost_per_1m=input_cost_per_1m,
        output_cost_per_1m=output_cost_per_1m,
        model_alias=selected_model,
        available_model_aliases=available_aliases,
    )


def _load_model_profiles(
    path: Path,
    default_context_limit: int,
    default_input_cost: float,
    default_output_cost: float,
) -> tuple[dict[str, ModelProfile], str | None]:
    if not path.exists():
        return {}, None

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    models_section = raw.get("models", {})
    if not isinstance(models_section, dict):
        raise ValueError(f"{path} must contain a [models] table")

    profiles: dict[str, ModelProfile] = {}
    for alias, raw_profile in models_section.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(f"Profile '{alias}' in {path} must be a table")
        profiles[str(alias)] = _parse_model_profile(
            alias=str(alias),
            raw_profile=raw_profile,
            default_context_limit=default_context_limit,
            default_input_cost=default_input_cost,
            default_output_cost=default_output_cost,
        )

    default_model = raw.get("default")
    if default_model is None:
        default_model = raw.get("default_model")
    normalized_default = str(default_model).strip() if default_model is not None else None
    if normalized_default == "":
        normalized_default = None
    return profiles, normalized_default


def _parse_model_profile(
    alias: str,
    raw_profile: dict[str, Any],
    default_context_limit: int,
    default_input_cost: float,
    default_output_cost: float,
) -> ModelProfile:
    model_name = str(raw_profile.get("model", "")).strip()
    if not model_name:
        raise ValueError(f"Model profile '{alias}' must define 'model'")

    return ModelProfile(
        alias=alias,
        api_key=_resolve_api_key(alias, raw_profile),
        base_url=_normalize_optional_text(raw_profile.get("base_url")),
        model=model_name,
        model_context_limit=int(raw_profile.get("context_limit", default_context_limit)),
        input_cost_per_1m=float(raw_profile.get("input_cost_per_1m", default_input_cost)),
        output_cost_per_1m=float(raw_profile.get("output_cost_per_1m", default_output_cost)),
    )


def _resolve_api_key(alias: str, raw_profile: dict[str, Any]) -> str:
    inline_api_key = _normalize_optional_text(raw_profile.get("api_key"))
    if inline_api_key:
        return inline_api_key

    api_key_env = _normalize_optional_text(raw_profile.get("api_key_env"))
    if api_key_env:
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            raise ValueError(
                f"Environment variable '{api_key_env}' for model profile '{alias}' is not set"
            )
        return api_key

    fallback_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if fallback_api_key:
        return fallback_api_key

    raise ValueError(
        f"Model profile '{alias}' is missing api_key/api_key_env and OPENAI_API_KEY is not set"
    )


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
