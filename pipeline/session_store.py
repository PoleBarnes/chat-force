"""Thin SQLite persistence layer for session metadata."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    run_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    container_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    closed_at TEXT,
    message_count INTEGER DEFAULT 0,
    sandbox_version TEXT DEFAULT '',
    first_message TEXT DEFAULT '',
    verdict_json TEXT,
    pr_url TEXT,
    error TEXT
)
"""


class SessionStore:
    """Thread-safe SQLite wrapper for session metadata."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def create_session(
        self,
        run_id: str,
        user_id: str,
        channel_id: str,
        first_message: str,
        created_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (
                    run_id,
                    user_id,
                    channel_id,
                    first_message,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, user_id, channel_id, first_message, created_at),
            )
            self._conn.commit()

    def update_container(
        self,
        run_id: str,
        container_id: str,
        sandbox_version: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET container_id = ?, sandbox_version = ?
                WHERE run_id = ?
                """,
                (container_id, sandbox_version, run_id),
            )
            self._conn.commit()

    def update_message_count(self, run_id: str, count: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET message_count = ? WHERE run_id = ?",
                (count, run_id),
            )
            self._conn.commit()

    def close_session(
        self,
        run_id: str,
        status: str,
        closed_at: str,
        verdict_json: dict[str, Any] | str | None = None,
        pr_url: str | None = None,
        error: str | None = None,
    ) -> None:
        if verdict_json is not None and not isinstance(verdict_json, str):
            verdict_json = json.dumps(verdict_json)

        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET status = ?,
                    closed_at = ?,
                    verdict_json = ?,
                    pr_url = ?,
                    error = ?
                WHERE run_id = ?
                """,
                (status, closed_at, verdict_json, pr_url, error, run_id),
            )
            self._conn.commit()

    def get_active_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE status = 'active' ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None
