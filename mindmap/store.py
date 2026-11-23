"""SQLite persistence for sessions (map nodes) and their messages."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    brief       TEXT,
    x           REAL NOT NULL DEFAULT 0,
    y           REAL NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_id);
"""


@dataclass(frozen=True)
class Session:
    id: int
    parent_id: int | None
    title: str
    brief: str | None
    x: float
    y: float


@dataclass(frozen=True)
class Message:
    id: int
    session_id: int
    role: str
    content: str


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # --- sessions -----------------------------------------------------
    def create_session(
        self,
        title: str,
        parent_id: int | None = None,
        brief: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
    ) -> Session:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO sessions (parent_id, title, brief, x, y, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (parent_id, title, brief, x, y, time.time()),
            )
        return self.get_session(cur.lastrowid)

    def get_session(self, session_id: int) -> Session:
        row = self.db.execute(
            "SELECT id, parent_id, title, brief, x, y FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return Session(*row)

    def sessions(self) -> list[Session]:
        rows = self.db.execute(
            "SELECT id, parent_id, title, brief, x, y FROM sessions ORDER BY id"
        ).fetchall()
        return [Session(*r) for r in rows]

    def children(self, session_id: int) -> list[Session]:
        rows = self.db.execute(
            "SELECT id, parent_id, title, brief, x, y FROM sessions"
            " WHERE parent_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [Session(*r) for r in rows]

    def subtree_ids(self, session_id: int) -> list[int]:
        rows = self.db.execute(
            """
            WITH RECURSIVE sub(id) AS (
                SELECT ?
                UNION ALL
                SELECT s.id FROM sessions s JOIN sub ON s.parent_id = sub.id
            )
            SELECT id FROM sub
            """,
            (session_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def ancestry(self, session_id: int) -> list[Session]:
        """Path from the root down to (and including) this session."""
        path: list[Session] = []
        current: int | None = session_id
        while current is not None:
            s = self.get_session(current)
            path.append(s)
            current = s.parent_id
        return list(reversed(path))

    def rename(self, session_id: int, title: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE sessions SET title = ? WHERE id = ?", (title, session_id)
            )

    def set_position(self, session_id: int, x: float, y: float) -> None:
        with self.db:
            self.db.execute(
                "UPDATE sessions SET x = ?, y = ? WHERE id = ?", (x, y, session_id)
            )

    def move_subtree(self, session_id: int, dx: float, dy: float) -> list[int]:
        ids = self.subtree_ids(session_id)
        with self.db:
            self.db.executemany(
                "UPDATE sessions SET x = x + ?, y = y + ? WHERE id = ?",
                [(dx, dy, i) for i in ids],
            )
        return ids

    def delete_session(self, session_id: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # --- messages -----------------------------------------------------
    def add_message(self, session_id: int, role: str, content: str) -> Message:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO messages (session_id, role, content, created_at)"
                " VALUES (?, ?, ?, ?)",
                (session_id, role, content, time.time()),
            )
        return Message(cur.lastrowid, session_id, role, content)

    def messages(self, session_id: int) -> list[Message]:
        rows = self.db.execute(
            "SELECT id, session_id, role, content FROM messages"
            " WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [Message(*r) for r in rows]
