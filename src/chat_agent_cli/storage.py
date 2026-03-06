from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex
from typing import Callable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    title: str
    updated_at: str
    message_count: int


@dataclass(slots=True)
class MessageRecord:
    role: str
    content: str
    token_count: int | None
    id: int | None = None


@dataclass(slots=True)
class SessionContextConfig:
    strategy: str
    summary_trigger_user_messages: int
    window_messages: int


@dataclass(slots=True)
class SessionSummaryRecord:
    start_message_id: int
    end_message_id: int
    content: str
    token_count: int | None


@dataclass(slots=True)
class SessionTokenStats:
    message_count: int
    user_messages: int
    assistant_messages: int
    system_messages: int
    content_tokens: int
    user_tokens: int
    assistant_tokens: int
    system_tokens: int
    billed_input_tokens: int
    billed_output_tokens: int
    billed_total_tokens: int


@dataclass(slots=True)
class SessionFactRecord:
    key: str
    value: str


@dataclass(slots=True)
class BranchRecord:
    name: str
    parent_name: str | None
    fork_message_id: int | None
    is_active: bool


@dataclass(slots=True)
class CheckpointRecord:
    name: str
    branch_name: str
    message_id: int


class ChatStorage:
    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)
        if self._path.parent != Path():
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def init(self) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT UNIQUE,
                    title TEXT NOT NULL DEFAULT 'Untitled session',
                    context_strategy TEXT NOT NULL DEFAULT 'full',
                    summary_trigger_user_messages INTEGER NOT NULL DEFAULT 10,
                    context_window_messages INTEGER NOT NULL DEFAULT 6,
                    active_branch_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    branch_id INTEGER,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER,
                    request_input_tokens INTEGER,
                    request_output_tokens INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    start_message_id INTEGER NOT NULL,
                    end_message_id INTEGER NOT NULL,
                    summary_text TEXT NOT NULL,
                    token_count INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    fact_key TEXT NOT NULL,
                    fact_value TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_branches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    parent_branch_id INTEGER,
                    fork_message_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS branch_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    branch_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            self._migrate_session_key(conn)
            self._migrate_sessions_context(conn)
            self._migrate_messages_tokens(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_summaries_session_id
                ON session_summaries(session_id, end_message_id)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_session_facts_key
                ON session_facts(session_id, fact_key)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_session_branches_name
                ON session_branches(session_id, name)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_branch_checkpoints_name
                ON branch_checkpoints(session_id, name)
                """
            )
            conn.commit()

    def create_session(
        self,
        system_prompt: str,
        token_count: int | None = None,
        context_strategy: str = "full",
        summary_trigger_user_messages: int = 10,
        context_window_messages: int = 6,
    ) -> str:
        now = _now_iso()
        session_key = self._new_session_key()
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (
                    session_key,
                    context_strategy,
                    summary_trigger_user_messages,
                    context_window_messages,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_key,
                    context_strategy,
                    summary_trigger_user_messages,
                    context_window_messages,
                    now,
                    now,
                ),
            )
            db_session_id = int(cursor.lastrowid)
            if context_strategy == "branching":
                branch_id = self._insert_branch(
                    conn,
                    db_session_id=db_session_id,
                    name="main",
                    parent_branch_id=None,
                    fork_message_id=None,
                    created_at=now,
                )
                conn.execute(
                    "UPDATE sessions SET active_branch_id = ? WHERE id = ?",
                    (branch_id, db_session_id),
                )
            conn.execute(
                """
                INSERT INTO messages (session_id, branch_id, role, content, token_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (db_session_id, None, "system", system_prompt, token_count, now),
            )
            conn.commit()
            return session_key

    def session_exists(self, session_id: str) -> bool:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE session_key = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT
                    s.session_key,
                    s.title,
                    s.updated_at,
                    COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            SessionSummary(
                session_id=str(row[0]),
                title=str(row[1]),
                updated_at=str(row[2]),
                message_count=int(row[3]),
            )
            for row in rows
        ]

    def load_messages(self, session_id: str) -> list[dict[str, str]]:
        rows = self.load_message_records(session_id)
        return [{"role": row.role, "content": row.content} for row in rows]

    def load_message_records(self, session_id: str) -> list[MessageRecord]:
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            strategy = self._get_context_strategy(conn, session_id)
            if strategy == "branching":
                return self._load_branching_message_records(conn, db_session_id)
            rows = conn.execute(
                """
                SELECT m.id, m.role, m.content, m.token_count
                FROM messages m
                WHERE m.session_id = ?
                ORDER BY m.id ASC
                """,
                (db_session_id,),
            ).fetchall()
        return self._map_message_rows(rows)

    def get_session_context_config(self, session_id: str) -> SessionContextConfig:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT
                    context_strategy,
                    summary_trigger_user_messages,
                    context_window_messages
                FROM sessions
                WHERE session_key = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Session '{session_id}' not found")
        return SessionContextConfig(
            strategy=str(row[0] or "full"),
            summary_trigger_user_messages=int(row[1] or 10),
            window_messages=int(row[2] or 6),
        )

    def list_session_summaries(self, session_id: str) -> list[SessionSummaryRecord]:
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT ss.start_message_id, ss.end_message_id, ss.summary_text, ss.token_count
                FROM session_summaries ss
                JOIN sessions s ON s.id = ss.session_id
                WHERE s.session_key = ?
                ORDER BY ss.end_message_id ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            SessionSummaryRecord(
                start_message_id=int(row[0]),
                end_message_id=int(row[1]),
                content=str(row[2]),
                token_count=int(row[3]) if row[3] is not None else None,
            )
            for row in rows
        ]

    def append_session_summary(
        self,
        session_id: str,
        start_message_id: int,
        end_message_id: int,
        summary_text: str,
        token_count: int | None = None,
    ) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            conn.execute(
                """
                INSERT INTO session_summaries (
                    session_id,
                    start_message_id,
                    end_message_id,
                    summary_text,
                    token_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    db_session_id,
                    start_message_id,
                    end_message_id,
                    summary_text,
                    token_count,
                    now,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            conn.commit()

    def clear_session_summaries(self, session_id: str) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            conn.execute(
                "DELETE FROM session_summaries WHERE session_id = ?",
                (db_session_id,),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            conn.commit()

    def replace_session_facts(self, session_id: str, facts: list[tuple[str, str]]) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            conn.execute(
                "DELETE FROM session_facts WHERE session_id = ?",
                (db_session_id,),
            )
            for position, (key, value) in enumerate(facts, start=1):
                conn.execute(
                    """
                    INSERT INTO session_facts (
                        session_id,
                        fact_key,
                        fact_value,
                        position,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (db_session_id, key, value, position, now),
                )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            conn.commit()

    def list_session_facts(self, session_id: str) -> list[SessionFactRecord]:
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT sf.fact_key, sf.fact_value
                FROM session_facts sf
                JOIN sessions s ON s.id = sf.session_id
                WHERE s.session_key = ?
                ORDER BY sf.position ASC, sf.id ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            SessionFactRecord(key=str(row[0]), value=str(row[1]))
            for row in rows
        ]

    def create_checkpoint(self, session_id: str, name: str) -> CheckpointRecord:
        checkpoint_name = name.strip()
        if not checkpoint_name:
            raise ValueError("Checkpoint name cannot be empty")

        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            self._require_branching_strategy(conn, session_id)
            active_branch_id = self._get_active_branch_id(conn, session_id)
            visible_messages = self._load_branching_message_records(conn, db_session_id)
            visible_non_system = [row for row in visible_messages if row.role != "system" and row.id is not None]
            if not visible_non_system:
                raise ValueError("Checkpoint requires at least one non-system message")
            message_id = int(visible_non_system[-1].id)
            conn.execute(
                "DELETE FROM branch_checkpoints WHERE session_id = ? AND name = ?",
                (db_session_id, checkpoint_name),
            )
            conn.execute(
                """
                INSERT INTO branch_checkpoints (
                    session_id,
                    branch_id,
                    name,
                    message_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (db_session_id, active_branch_id, checkpoint_name, message_id, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            conn.commit()

        return CheckpointRecord(
            name=checkpoint_name,
            branch_name=self.get_active_branch_name(session_id) or "main",
            message_id=message_id,
        )

    def list_checkpoints(self, session_id: str) -> list[CheckpointRecord]:
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT bc.name, sb.name, bc.message_id
                FROM branch_checkpoints bc
                JOIN sessions s ON s.id = bc.session_id
                JOIN session_branches sb ON sb.id = bc.branch_id
                WHERE s.session_key = ?
                ORDER BY bc.id ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            CheckpointRecord(
                name=str(row[0]),
                branch_name=str(row[1]),
                message_id=int(row[2]),
            )
            for row in rows
        ]

    def create_branch(self, session_id: str, checkpoint_name: str, branch_name: str) -> BranchRecord:
        normalized_name = branch_name.strip()
        if not normalized_name:
            raise ValueError("Branch name cannot be empty")

        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            self._require_branching_strategy(conn, session_id)
            checkpoint = conn.execute(
                """
                SELECT bc.branch_id, bc.message_id, parent.name
                FROM branch_checkpoints bc
                JOIN session_branches parent ON parent.id = bc.branch_id
                WHERE bc.session_id = ? AND bc.name = ?
                """,
                (db_session_id, checkpoint_name),
            ).fetchone()
            if checkpoint is None:
                raise ValueError(f"Checkpoint '{checkpoint_name}' not found")
            parent_branch_id = int(checkpoint[0])
            fork_message_id = int(checkpoint[1])
            parent_name = str(checkpoint[2])
            self._insert_branch(
                conn,
                db_session_id=db_session_id,
                name=normalized_name,
                parent_branch_id=parent_branch_id,
                fork_message_id=fork_message_id,
                created_at=now,
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            conn.commit()
        return BranchRecord(
            name=normalized_name,
            parent_name=parent_name,
            fork_message_id=fork_message_id,
            is_active=False,
        )

    def list_branches(self, session_id: str) -> list[BranchRecord]:
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            active_branch_id = self._get_active_branch_id(conn, session_id, allow_missing=True)
            rows = conn.execute(
                """
                SELECT child.name, parent.name, child.fork_message_id, child.id
                FROM session_branches child
                LEFT JOIN session_branches parent ON parent.id = child.parent_branch_id
                WHERE child.session_id = ?
                ORDER BY child.id ASC
                """,
                (db_session_id,),
            ).fetchall()
        return [
            BranchRecord(
                name=str(row[0]),
                parent_name=str(row[1]) if row[1] is not None else None,
                fork_message_id=int(row[2]) if row[2] is not None else None,
                is_active=active_branch_id is not None and int(row[3]) == active_branch_id,
            )
            for row in rows
        ]

    def switch_branch(self, session_id: str, branch_name: str) -> BranchRecord:
        normalized_name = branch_name.strip()
        if not normalized_name:
            raise ValueError("Branch name cannot be empty")

        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            self._require_branching_strategy(conn, session_id)
            row = conn.execute(
                """
                SELECT child.id, parent.name, child.fork_message_id
                FROM session_branches child
                LEFT JOIN session_branches parent ON parent.id = child.parent_branch_id
                WHERE child.session_id = ? AND child.name = ?
                """,
                (db_session_id, normalized_name),
            ).fetchone()
            if row is None:
                raise ValueError(f"Branch '{normalized_name}' not found")
            branch_id = int(row[0])
            parent_name = str(row[1]) if row[1] is not None else None
            fork_message_id = int(row[2]) if row[2] is not None else None
            conn.execute(
                "UPDATE sessions SET active_branch_id = ?, updated_at = ? WHERE id = ?",
                (branch_id, now, db_session_id),
            )
            conn.commit()
        return BranchRecord(
            name=normalized_name,
            parent_name=parent_name,
            fork_message_id=fork_message_id,
            is_active=True,
        )

    def get_active_branch_name(self, session_id: str) -> str | None:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT sb.name
                FROM sessions s
                LEFT JOIN session_branches sb ON sb.id = s.active_branch_id
                WHERE s.session_key = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_count: int | None = None,
        request_input_tokens: int | None = None,
        request_output_tokens: int | None = None,
    ) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            branch_id = None
            if role != "system" and self._get_context_strategy(conn, session_id) == "branching":
                branch_id = self._get_active_branch_id(conn, session_id)
            conn.execute(
                """
                INSERT INTO messages (
                    session_id,
                    branch_id,
                    role,
                    content,
                    token_count,
                    request_input_tokens,
                    request_output_tokens,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    db_session_id,
                    branch_id,
                    role,
                    content,
                    token_count,
                    request_input_tokens,
                    request_output_tokens,
                    now,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            if role == "user":
                self._maybe_set_title(conn, session_id, content)
            conn.commit()

    def fill_missing_token_counts(
        self,
        session_id: str,
        counter: Callable[[str], int],
    ) -> int:
        updated = 0
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            rows = conn.execute(
                """
                SELECT id, content
                FROM messages
                WHERE session_id = ? AND token_count IS NULL
                ORDER BY id ASC
                """,
                (db_session_id,),
            ).fetchall()
            for row in rows:
                message_id = int(row[0])
                content = str(row[1])
                conn.execute(
                    "UPDATE messages SET token_count = ? WHERE id = ?",
                    (counter(content), message_id),
                )
                updated += 1
            conn.commit()
        return updated

    def session_token_stats(self, session_id: str) -> SessionTokenStats:
        with sqlite3.connect(self._path) as conn:
            if self._get_context_strategy(conn, session_id) == "branching":
                db_session_id = self._get_db_session_id(conn, session_id)
                rows = self._load_branching_message_rows(conn, db_session_id)
                return self._build_token_stats_from_rows(rows)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS message_count,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS user_messages,
                    SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) AS assistant_messages,
                    SUM(CASE WHEN role = 'system' THEN 1 ELSE 0 END) AS system_messages,
                    COALESCE(SUM(token_count), 0) AS content_tokens,
                    COALESCE(SUM(CASE WHEN role = 'user' THEN token_count ELSE 0 END), 0) AS user_tokens,
                    COALESCE(SUM(CASE WHEN role = 'assistant' THEN token_count ELSE 0 END), 0) AS assistant_tokens,
                    COALESCE(SUM(CASE WHEN role = 'system' THEN token_count ELSE 0 END), 0) AS system_tokens,
                    COALESCE(SUM(request_input_tokens), 0) AS billed_input_tokens,
                    COALESCE(SUM(request_output_tokens), 0) AS billed_output_tokens
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE s.session_key = ?
                """,
                (session_id,),
            ).fetchone()

        message_count = int(row[0]) if row is not None else 0
        user_messages = int(row[1]) if row is not None else 0
        assistant_messages = int(row[2]) if row is not None else 0
        system_messages = int(row[3]) if row is not None else 0
        content_tokens = int(row[4]) if row is not None else 0
        user_tokens = int(row[5]) if row is not None else 0
        assistant_tokens = int(row[6]) if row is not None else 0
        system_tokens = int(row[7]) if row is not None else 0
        billed_input_tokens = int(row[8]) if row is not None else 0
        billed_output_tokens = int(row[9]) if row is not None else 0

        return SessionTokenStats(
            message_count=message_count,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            system_messages=system_messages,
            content_tokens=content_tokens,
            user_tokens=user_tokens,
            assistant_tokens=assistant_tokens,
            system_tokens=system_tokens,
            billed_input_tokens=billed_input_tokens,
            billed_output_tokens=billed_output_tokens,
            billed_total_tokens=billed_input_tokens + billed_output_tokens,
        )

    def clear_session(
        self,
        session_id: str,
        system_prompt: str,
        token_count: int | None = None,
    ) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            strategy = self._get_context_strategy(conn, session_id)
            conn.execute("DELETE FROM messages WHERE session_id = ?", (db_session_id,))
            conn.execute("DELETE FROM session_summaries WHERE session_id = ?", (db_session_id,))
            conn.execute("DELETE FROM session_facts WHERE session_id = ?", (db_session_id,))
            conn.execute("DELETE FROM branch_checkpoints WHERE session_id = ?", (db_session_id,))
            conn.execute("DELETE FROM session_branches WHERE session_id = ?", (db_session_id,))

            active_branch_id = None
            if strategy == "branching":
                active_branch_id = self._insert_branch(
                    conn,
                    db_session_id=db_session_id,
                    name="main",
                    parent_branch_id=None,
                    fork_message_id=None,
                    created_at=now,
                )
            conn.execute(
                """
                INSERT INTO messages (session_id, branch_id, role, content, token_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (db_session_id, None, "system", system_prompt, token_count, now),
            )
            conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?, title = ?, active_branch_id = ?
                WHERE session_key = ?
                """,
                (now, "Untitled session", active_branch_id, session_id),
            )
            conn.commit()

    @staticmethod
    def _maybe_set_title(conn: sqlite3.Connection, session_id: str, content: str) -> None:
        row = conn.execute(
            "SELECT title FROM sessions WHERE session_key = ?",
            (session_id,),
        ).fetchone()
        if row is None or row[0] != "Untitled session":
            return

        title = " ".join(content.strip().split())
        if not title:
            return
        if len(title) > 70:
            title = f"{title[:67]}..."
        conn.execute(
            "UPDATE sessions SET title = ? WHERE session_key = ?",
            (title, session_id),
        )

    @staticmethod
    def _get_db_session_id(conn: sqlite3.Connection, session_key: str) -> int:
        row = conn.execute(
            "SELECT id FROM sessions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session '{session_key}' not found")
        return int(row[0])

    @staticmethod
    def _get_context_strategy(conn: sqlite3.Connection, session_id: str) -> str:
        row = conn.execute(
            "SELECT context_strategy FROM sessions WHERE session_key = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session '{session_id}' not found")
        return str(row[0] or "full")

    @staticmethod
    def _migrate_session_key(conn: sqlite3.Connection) -> None:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "session_key" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN session_key TEXT")

        rows = conn.execute(
            "SELECT id FROM sessions WHERE session_key IS NULL OR session_key = ''"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE sessions SET session_key = ? WHERE id = ?",
                (ChatStorage._new_session_key(), int(row[0])),
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_session_key ON sessions(session_key)"
        )

    @staticmethod
    def _migrate_sessions_context(conn: sqlite3.Connection) -> None:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "context_strategy" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN context_strategy TEXT NOT NULL DEFAULT 'full'"
            )
        if "summary_trigger_user_messages" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN summary_trigger_user_messages INTEGER NOT NULL DEFAULT 10"
            )
        if "context_window_messages" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN context_window_messages INTEGER NOT NULL DEFAULT 6"
            )
        if "active_branch_id" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN active_branch_id INTEGER")

    @staticmethod
    def _migrate_messages_tokens(conn: sqlite3.Connection) -> None:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "branch_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN branch_id INTEGER")
        if "token_count" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN token_count INTEGER")
        if "request_input_tokens" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN request_input_tokens INTEGER")
        if "request_output_tokens" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN request_output_tokens INTEGER")

    @staticmethod
    def _map_message_rows(rows: list[tuple[object, ...]]) -> list[MessageRecord]:
        return [
            MessageRecord(
                role=str(row[1]),
                content=str(row[2]),
                token_count=int(row[3]) if row[3] is not None else None,
                id=int(row[0]),
            )
            for row in rows
        ]

    def _load_branching_message_records(
        self,
        conn: sqlite3.Connection,
        db_session_id: int,
    ) -> list[MessageRecord]:
        return self._map_message_rows(self._load_branching_message_rows(conn, db_session_id))

    def _load_branching_message_rows(
        self,
        conn: sqlite3.Connection,
        db_session_id: int,
    ) -> list[tuple[object, ...]]:
        branch_rows = conn.execute(
            """
            SELECT id, name, parent_branch_id, fork_message_id
            FROM session_branches
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (db_session_id,),
        ).fetchall()
        if not branch_rows:
            rows = conn.execute(
                """
                SELECT id, role, content, token_count, request_input_tokens, request_output_tokens
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (db_session_id,),
            ).fetchall()
            return [tuple(row) for row in rows]

        branch_map = {
            int(row[0]): {
                "parent": int(row[2]) if row[2] is not None else None,
                "fork_message_id": int(row[3]) if row[3] is not None else None,
            }
            for row in branch_rows
        }
        active_branch_id = self._get_active_branch_id_by_db_session_id(conn, db_session_id)
        if active_branch_id is None:
            rows = conn.execute(
                """
                SELECT id, role, content, token_count, request_input_tokens, request_output_tokens
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (db_session_id,),
            ).fetchall()
            return [tuple(row) for row in rows]

        path: list[int] = []
        cursor = active_branch_id
        while cursor is not None:
            path.append(cursor)
            cursor = branch_map.get(cursor, {}).get("parent")
        path.reverse()

        upper_bounds: dict[int, int | None] = {}
        for index, branch_id in enumerate(path):
            if index + 1 >= len(path):
                upper_bounds[branch_id] = None
                continue
            child_branch_id = path[index + 1]
            upper_bounds[branch_id] = branch_map[child_branch_id]["fork_message_id"]

        path_set = set(path)
        rows = conn.execute(
            """
            SELECT id, role, content, token_count, request_input_tokens, request_output_tokens, branch_id
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (db_session_id,),
        ).fetchall()

        visible: list[tuple[object, ...]] = []
        for row in rows:
            message_id = int(row[0])
            role = str(row[1])
            branch_id = int(row[6]) if row[6] is not None else None
            if role == "system":
                visible.append((row[0], row[1], row[2], row[3], row[4], row[5]))
                continue
            if branch_id not in path_set:
                continue
            upper_bound = upper_bounds.get(branch_id)
            if upper_bound is not None and message_id > upper_bound:
                continue
            visible.append((row[0], row[1], row[2], row[3], row[4], row[5]))
        return visible

    @staticmethod
    def _build_token_stats_from_rows(rows: list[tuple[object, ...]]) -> SessionTokenStats:
        message_count = 0
        user_messages = 0
        assistant_messages = 0
        system_messages = 0
        content_tokens = 0
        user_tokens = 0
        assistant_tokens = 0
        system_tokens = 0
        billed_input_tokens = 0
        billed_output_tokens = 0

        for row in rows:
            message_count += 1
            role = str(row[1])
            token_count = int(row[3]) if row[3] is not None else 0
            content_tokens += token_count
            billed_input_tokens += int(row[4]) if len(row) > 4 and row[4] is not None else 0
            billed_output_tokens += int(row[5]) if len(row) > 5 and row[5] is not None else 0
            if role == "user":
                user_messages += 1
                user_tokens += token_count
            elif role == "assistant":
                assistant_messages += 1
                assistant_tokens += token_count
            else:
                system_messages += 1
                system_tokens += token_count

        return SessionTokenStats(
            message_count=message_count,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            system_messages=system_messages,
            content_tokens=content_tokens,
            user_tokens=user_tokens,
            assistant_tokens=assistant_tokens,
            system_tokens=system_tokens,
            billed_input_tokens=billed_input_tokens,
            billed_output_tokens=billed_output_tokens,
            billed_total_tokens=billed_input_tokens + billed_output_tokens,
        )

    def _insert_branch(
        self,
        conn: sqlite3.Connection,
        db_session_id: int,
        name: str,
        parent_branch_id: int | None,
        fork_message_id: int | None,
        created_at: str,
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO session_branches (
                session_id,
                name,
                parent_branch_id,
                fork_message_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (db_session_id, name, parent_branch_id, fork_message_id, created_at),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _require_branching_strategy(conn: sqlite3.Connection, session_id: str) -> None:
        row = conn.execute(
            "SELECT context_strategy FROM sessions WHERE session_key = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session '{session_id}' not found")
        if str(row[0]) != "branching":
            raise ValueError("Branch commands are available only for context=branching sessions")

    @staticmethod
    def _get_active_branch_id(
        conn: sqlite3.Connection,
        session_id: str,
        allow_missing: bool = False,
    ) -> int | None:
        row = conn.execute(
            "SELECT active_branch_id FROM sessions WHERE session_key = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session '{session_id}' not found")
        if row[0] is None and allow_missing:
            return None
        if row[0] is None:
            raise ValueError(f"Session '{session_id}' has no active branch")
        return int(row[0])

    @staticmethod
    def _get_active_branch_id_by_db_session_id(
        conn: sqlite3.Connection,
        db_session_id: int,
    ) -> int | None:
        row = conn.execute(
            "SELECT active_branch_id FROM sessions WHERE id = ?",
            (db_session_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    @staticmethod
    def _new_session_key() -> str:
        return token_hex(8)
