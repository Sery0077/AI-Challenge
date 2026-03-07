from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .text import normalize_text


@dataclass(slots=True)
class UserProfile:
    user_id: str = "default"
    name: str = ""
    preferences: dict[str, dict[str, Any]] | None = None

    def normalized_preferences(self) -> dict[str, dict[str, Any]]:
        raw_preferences = self.preferences or {}
        normalized: dict[str, dict[str, Any]] = {}
        for section, values in raw_preferences.items():
            if not isinstance(values, dict):
                continue
            safe_section = normalize_text(str(section)).strip()
            if not safe_section:
                continue
            items: dict[str, Any] = {}
            for key, value in values.items():
                safe_key = normalize_text(str(key)).strip()
                if not safe_key:
                    continue
                items[safe_key] = _normalize_profile_value(value)
            if items:
                normalized[safe_section] = items
        return normalized

    def is_empty(self) -> bool:
        return not self.name.strip() and not self.normalized_preferences()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"user_id": self.user_id}
        if self.name.strip():
            data["name"] = self.name.strip()
        data["preferences"] = self.normalized_preferences()
        return data

    def to_prompt_message(self) -> dict[str, str] | None:
        if self.is_empty():
            return None

        lines = [
            "User profile:",
            f"user_id: {self.user_id}",
        ]
        if self.name.strip():
            lines.append(f"name: {self.name.strip()}")
        for section, values in self.normalized_preferences().items():
            lines.append(f"{section}:")
            lines.extend(f"- {key}: {normalize_text(str(value)).strip()}" for key, value in values.items())
        lines.append(
            "Apply this profile automatically unless the user explicitly overrides it in the current request."
        )
        return {"role": "system", "content": "\n".join(lines)}


def load_user_profile(path: str) -> UserProfile:
    profile_path = Path(path)
    if not profile_path.exists():
        return UserProfile()

    with profile_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return _parse_user_profile(raw)


def save_user_profile(path: str, profile: UserProfile) -> None:
    profile_path = Path(path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    with profile_path.open("w", encoding="utf-8") as handle:
        json.dump(profile.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def set_user_profile_value(path: str, dotted_key: str, value: str) -> UserProfile:
    profile = load_user_profile(path)
    parts = [normalize_text(part).strip() for part in dotted_key.split(".")]
    if any(not part for part in parts):
        raise ValueError("Profile key must look like section.field or name")

    if parts[0] == "name":
        if len(parts) != 1:
            raise ValueError("The 'name' field must be updated as 'name'")
        profile.name = normalize_text(value).strip()
        save_user_profile(path, profile)
        return profile

    if len(parts) != 2:
        raise ValueError("Profile key must look like section.field")

    preferences = profile.preferences or {}
    section = preferences.setdefault(parts[0], {})
    section[parts[1]] = _coerce_value(value)
    profile.preferences = preferences
    save_user_profile(path, profile)
    return profile


def _parse_user_profile(raw: Any) -> UserProfile:
    if not isinstance(raw, dict):
        raise ValueError("User profile must be a JSON object")
    user_id = normalize_text(str(raw.get("user_id", "default"))).strip() or "default"
    name = normalize_text(str(raw.get("name", ""))).strip()
    preferences = raw.get("preferences")
    if preferences is not None and not isinstance(preferences, dict):
        raise ValueError("User profile 'preferences' must be an object")
    return UserProfile(
        user_id=user_id,
        name=name,
        preferences=preferences,
    )


def _coerce_value(value: str) -> Any:
    text = normalize_text(value).strip()
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered.isdigit():
        return int(lowered)
    return text


def _normalize_profile_value(value: Any) -> Any:
    if isinstance(value, bool | int):
        return value
    return normalize_text(str(value)).strip()
