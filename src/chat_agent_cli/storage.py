from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    title: str
    updated_at: str
    message_count: int


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
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            self._migrate_session_key(conn)
            conn.commit()

    def create_session(self, system_prompt: str) -> str:
        now = _now_iso()
        session_key = self._new_session_key()
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (session_key, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (session_key, now, now),
            )
            db_session_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (db_session_id, "system", system_prompt, now),
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
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT m.role, m.content
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE s.session_key = ?
                ORDER BY m.id ASC
                """,
                (session_id,),
            ).fetchall()
        return [{"role": str(row[0]), "content": str(row[1])} for row in rows]

    def append_message(self, session_id: str, role: str, content: str) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (db_session_id, role, content, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_key = ?",
                (now, session_id),
            )
            if role == "user":
                self._maybe_set_title(conn, session_id, content)
            conn.commit()

    def clear_session(self, session_id: str, system_prompt: str) -> None:
        now = _now_iso()
        with sqlite3.connect(self._path) as conn:
            db_session_id = self._get_db_session_id(conn, session_id)
            conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (db_session_id,),
            )
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (db_session_id, "system", system_prompt, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ?, title = ? WHERE session_key = ?",
                (now, "Untitled session", session_id),
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

    def _migrate_session_key(self, conn: sqlite3.Connection) -> None:
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
                (self._new_session_key(), int(row[0])),
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_session_key ON sessions(session_key)"
        )

    @staticmethod
    def _new_session_key() -> str:
        return token_hex(8)
