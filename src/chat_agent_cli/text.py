from __future__ import annotations


def normalize_text(value: str) -> str:
    return value.encode("utf-8", errors="replace").decode("utf-8")
