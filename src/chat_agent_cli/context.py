from __future__ import annotations

import re
from dataclasses import dataclass

from .storage import ChatStorage, MessageRecord, SessionContextConfig
from .tokens import TokenCounter


_FACT_LABELS = {
    "goal": "goal",
    "owner": "owner",
    "constraint": "constraint",
    "constraints": "constraint",
    "preference": "preference",
    "preferences": "preference",
    "decision": "decision",
    "agreement": "agreement",
    "deadline": "deadline",
    "budget": "budget",
    "codeword": "codeword",
    "stack": "stack",
    "storage": "storage",
    "branch": "branch",
    "database": "database",
    "цель": "goal",
    "владелец": "owner",
    "ограничение": "constraint",
    "ограничения": "constraint",
    "предпочтение": "preference",
    "предпочтения": "preference",
    "решение": "decision",
    "договоренность": "agreement",
    "договорённость": "agreement",
    "срок": "deadline",
    "бюджет": "budget",
    "кодовое_слово": "codeword",
    "кодовое слово": "codeword",
    "стек": "stack",
    "хранилище": "storage",
    "ветка": "branch",
    "база": "database",
}

_EXPLICIT_FACT_RE = re.compile(
    r"(?P<key>[A-Za-zА-Яа-я0-9_ -]{2,40})\s*[:=]\s*(?P<value>[^.;\n]+)"
)
_IS_FACT_RE = re.compile(
    r"(?i)\b(?P<key>goal|constraint|preference|decision|agreement|deadline|budget|owner|codeword|stack|storage|database)\b\s+is\s+(?P<value>[^.;\n]+)"
)
_WORKING_MEMORY_KEYS = {
    "goal",
    "task",
    "constraint",
    "agreement",
    "deadline",
    "budget",
    "codeword",
    "storage",
    "branch",
    "database",
    "deliverable",
    "status",
    "risk",
}
_LONG_TERM_MEMORY_KEYS = {
    "owner",
    "preference",
    "decision",
    "profile",
    "knowledge",
    "stack",
}
_EXPLICIT_MEMORY_LAYER_RE = re.compile(
    r"(?i)^(?P<layer>working|work|long|long_term|long-term|рабочая|долговременная)\s*:\s*(?P<body>.+)$"
)


@dataclass(slots=True)
class ContextBuildResult:
    messages: list[dict[str, str]]
    summarized_chunks: int


class ContextManager:
    def __init__(self, storage: ChatStorage, token_counter: TokenCounter) -> None:
        self._storage = storage
        self._token_counter = token_counter

    def build_messages(
        self,
        session_id: str,
        message_records: list[MessageRecord],
    ) -> ContextBuildResult:
        config = self._storage.get_session_context_config(session_id)

        if config.strategy == "sum":
            summarized_chunks = self._materialize_summaries(
                session_id=session_id,
                message_records=message_records,
                config=config,
            )
            messages = self._build_compacted_messages(
                session_id=session_id,
                message_records=message_records,
            )
            return ContextBuildResult(messages=messages, summarized_chunks=summarized_chunks)

        if config.strategy == "sliding":
            return ContextBuildResult(
                messages=self._build_sliding_messages(message_records, config.window_messages),
                summarized_chunks=0,
            )

        if config.strategy == "facts":
            self._refresh_facts(session_id=session_id, message_records=message_records)
            return ContextBuildResult(
                messages=self._build_fact_messages(session_id, message_records, config.window_messages),
                summarized_chunks=0,
            )

        if config.strategy == "memory":
            self._refresh_memory_layers(session_id=session_id, message_records=message_records)
            return ContextBuildResult(
                messages=self._build_memory_messages(
                    session_id=session_id,
                    message_records=message_records,
                    window_messages=config.window_messages,
                ),
                summarized_chunks=0,
            )

        if config.strategy == "branching":
            return ContextBuildResult(
                messages=self._build_branch_messages(session_id, message_records),
                summarized_chunks=0,
            )

        return ContextBuildResult(
            messages=[{"role": row.role, "content": row.content} for row in message_records],
            summarized_chunks=0,
        )

    def _build_sliding_messages(
        self,
        message_records: list[MessageRecord],
        window_messages: int,
    ) -> list[dict[str, str]]:
        system_messages = [
            {"role": row.role, "content": row.content}
            for row in message_records
            if row.role == "system"
        ]
        recent_messages = [
            {"role": row.role, "content": row.content}
            for row in message_records
            if row.role != "system"
        ][-max(1, window_messages):]
        return [*system_messages, *recent_messages]

    def _build_fact_messages(
        self,
        session_id: str,
        message_records: list[MessageRecord],
        window_messages: int,
    ) -> list[dict[str, str]]:
        messages = self._build_sliding_messages(message_records, window_messages)
        facts = self._storage.list_session_facts(session_id)
        if not facts:
            return messages

        fact_lines = "\n".join(f"{item.key}: {item.value}" for item in facts)
        fact_message = {
            "role": "system",
            "content": "Stored facts:\n" + fact_lines,
        }
        insert_at = 1 if messages and messages[0]["role"] == "system" else 0
        messages.insert(insert_at, fact_message)
        return messages

    def _build_memory_messages(
        self,
        session_id: str,
        message_records: list[MessageRecord],
        window_messages: int,
    ) -> list[dict[str, str]]:
        messages = self._build_sliding_messages(message_records, window_messages)
        inserts: list[dict[str, str]] = []

        working_memory = self._storage.list_working_memory(session_id)
        if working_memory:
            working_lines = "\n".join(
                f"{item.key}: {item.value}" for item in working_memory
            )
            inserts.append(
                {
                    "role": "system",
                    "content": "Working memory (current task):\n" + working_lines,
                }
            )

        long_term_memory = self._storage.list_long_term_memory(session_id)
        if long_term_memory:
            long_term_lines = "\n".join(
                f"{item.key}: {item.value}" for item in long_term_memory
            )
            inserts.append(
                {
                    "role": "system",
                    "content": (
                        "Long-term memory (profile, preferences, stable decisions, knowledge):\n"
                        + long_term_lines
                    ),
                }
            )

        if not inserts:
            return messages

        insert_at = 1 if messages and messages[0]["role"] == "system" else 0
        for offset, item in enumerate(inserts):
            messages.insert(insert_at + offset, item)
        return messages

    def _build_branch_messages(
        self,
        session_id: str,
        message_records: list[MessageRecord],
    ) -> list[dict[str, str]]:
        messages = [{"role": row.role, "content": row.content} for row in message_records]
        active_branch = self._storage.get_active_branch_name(session_id)
        if active_branch is None:
            return messages
        branch_notice = {
            "role": "system",
            "content": f"Active branch: {active_branch}",
        }
        insert_at = 1 if messages and messages[0]["role"] == "system" else 0
        messages.insert(insert_at, branch_notice)
        return messages

    def _refresh_facts(
        self,
        session_id: str,
        message_records: list[MessageRecord],
    ) -> None:
        ordered_keys: list[str] = []
        facts_by_key: dict[str, str] = {}

        for row in message_records:
            if row.role != "user":
                continue
            for key, value in self._extract_facts(row.content):
                if key in facts_by_key:
                    ordered_keys.remove(key)
                facts_by_key[key] = value
                ordered_keys.append(key)

        facts = [(key, facts_by_key[key]) for key in ordered_keys]
        self._storage.replace_session_facts(session_id, facts)

    def _refresh_memory_layers(
        self,
        session_id: str,
        message_records: list[MessageRecord],
    ) -> None:
        working_order: list[str] = []
        working_values: dict[str, str] = {}
        long_term_order: list[str] = []
        long_term_values: dict[str, str] = {}

        for row in message_records:
            if row.role != "user":
                continue
            for layer, key, value in self._extract_memory_items(row.content):
                if layer == "long_term":
                    if key in long_term_values:
                        long_term_order.remove(key)
                    long_term_values[key] = value
                    long_term_order.append(key)
                    continue
                if key in working_values:
                    working_order.remove(key)
                working_values[key] = value
                working_order.append(key)

        self._storage.replace_working_memory(
            session_id,
            [(key, working_values[key]) for key in working_order],
        )
        self._storage.replace_long_term_memory(
            session_id,
            [(key, long_term_values[key]) for key in long_term_order],
        )

    def _extract_facts(self, text: str) -> list[tuple[str, str]]:
        facts: list[tuple[str, str]] = []

        for match in _EXPLICIT_FACT_RE.finditer(text):
            key = self._normalize_fact_key(match.group("key"))
            value = self._normalize_fact_value(match.group("value"))
            if key is not None and value:
                facts.append((key, value))

        for match in _IS_FACT_RE.finditer(text):
            key = self._normalize_fact_key(match.group("key"))
            value = self._normalize_fact_value(match.group("value"))
            if key is not None and value:
                facts.append((key, value))

        return facts

    def _extract_memory_items(self, text: str) -> list[tuple[str, str, str]]:
        items: list[tuple[str, str, str]] = []
        for segment in self._split_segments(text):
            items.extend(self._extract_memory_segment(segment))
        return items

    def _extract_memory_segment(self, segment: str) -> list[tuple[str, str, str]]:
        forced_layer: str | None = None
        body = segment
        explicit = _EXPLICIT_MEMORY_LAYER_RE.match(segment)
        if explicit is not None:
            forced_layer = self._normalize_memory_layer(explicit.group("layer"))
            body = explicit.group("body").strip()

        items: list[tuple[str, str, str]] = []
        for key, value in self._extract_facts(body):
            layer = forced_layer or self._route_memory_layer(key)
            items.append((layer, key, value))
        return items

    @staticmethod
    def _split_segments(text: str) -> list[str]:
        return [segment.strip() for segment in re.split(r"[;\n]+", text) if segment.strip()]

    @staticmethod
    def _normalize_memory_layer(raw_layer: str) -> str:
        layer = raw_layer.strip().lower().replace("-", "_").replace(" ", "_")
        if layer in {"long", "long_term", "долговременная"}:
            return "long_term"
        return "working"

    @staticmethod
    def _route_memory_layer(key: str) -> str:
        if key in _LONG_TERM_MEMORY_KEYS:
            return "long_term"
        if key in _WORKING_MEMORY_KEYS:
            return "working"
        return "working"

    @staticmethod
    def _normalize_fact_key(raw_key: str) -> str | None:
        key = " ".join(raw_key.strip().lower().split())
        key = key.replace("-", "_")
        if key in _FACT_LABELS:
            return _FACT_LABELS[key]
        key = key.replace(" ", "_")
        if key in _FACT_LABELS:
            return _FACT_LABELS[key]
        if re.fullmatch(r"[a-zа-я0-9_]{2,40}", key):
            return key
        return None

    @staticmethod
    def _normalize_fact_value(raw_value: str) -> str:
        return " ".join(raw_value.strip().split())

    def _materialize_summaries(
        self,
        session_id: str,
        message_records: list[MessageRecord],
        config: SessionContextConfig,
    ) -> int:
        non_system = [m for m in message_records if m.role != "system" and m.id is not None]
        if not non_system:
            return 0

        summaries = self._storage.list_session_summaries(session_id)
        last_summary_end_id = summaries[-1].end_message_id if summaries else 0
        pending = [m for m in non_system if m.id is not None and m.id > last_summary_end_id]
        if not pending:
            return 0

        threshold = max(1, config.summary_trigger_user_messages)
        chunk: list[MessageRecord] = []
        chunk_user_messages = 0
        chunk_start_id: int | None = None
        created = 0

        for record in pending:
            if chunk_start_id is None:
                chunk_start_id = int(record.id)
            chunk.append(record)
            if record.role == "user":
                chunk_user_messages += 1
            if chunk_user_messages < threshold:
                continue

            chunk_end_id = int(record.id)
            summary_text = self._summarize_chunk(chunk)
            self._storage.append_session_summary(
                session_id=session_id,
                start_message_id=chunk_start_id,
                end_message_id=chunk_end_id,
                summary_text=summary_text,
                token_count=self._token_counter.count_text(summary_text),
            )
            chunk = []
            chunk_user_messages = 0
            chunk_start_id = None
            created += 1
        return created

    def _build_compacted_messages(
        self,
        session_id: str,
        message_records: list[MessageRecord],
    ) -> list[dict[str, str]]:
        summaries = self._storage.list_session_summaries(session_id)
        summary_end_id = summaries[-1].end_message_id if summaries else 0

        compacted: list[dict[str, str]] = []
        for record in message_records:
            if record.role == "system":
                compacted.append({"role": record.role, "content": record.content})
                continue
            if record.id is not None and record.id <= summary_end_id:
                continue
            compacted.append({"role": record.role, "content": record.content})

        if not summaries:
            return compacted

        summary_body = "\n".join(
            f"{index + 1}. {item.content}"
            for index, item in enumerate(summaries)
        )
        summary_message = {
            "role": "system",
            "content": "Summary of earlier conversation:\n" + summary_body,
        }

        insertion_index = 1 if compacted and compacted[0]["role"] == "system" else 0
        compacted.insert(insertion_index, summary_message)
        return compacted

    @staticmethod
    def _summarize_chunk(chunk: list[MessageRecord]) -> str:
        lines: list[str] = []
        for item in chunk:
            role = "user" if item.role == "user" else "assistant"
            normalized = " ".join(item.content.strip().split())
            if len(normalized) > 160:
                normalized = normalized[:157] + "..."
            lines.append(f"{role}: {normalized}")
        return " | ".join(lines)
