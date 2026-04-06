"""Unit tests for SQLite-backed session persistence."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from pipeline.session_store import SessionStore


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_create_and_get_session(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.db"))

    store.create_session("run-1", "U1", "C1", "Build it", _ts())

    row = store.get_session("run-1")
    assert row is not None
    assert row["run_id"] == "run-1"
    assert row["user_id"] == "U1"
    assert row["channel_id"] == "C1"
    assert row["status"] == "active"
    assert row["first_message"] == "Build it"
    assert row["message_count"] == 0


def test_update_container(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.db"))
    store.create_session("run-2", "U2", "C2", "Hello", _ts())

    store.update_container("run-2", "container-123", "abc1234")

    row = store.get_session("run-2")
    assert row is not None
    assert row["container_id"] == "container-123"
    assert row["sandbox_version"] == "abc1234"


def test_close_session(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.db"))
    store.create_session("run-3", "U3", "C3", "Hello", _ts())

    verdict = {"approved": True, "reason": "Looks good"}
    store.close_session(
        "run-3",
        status="approved",
        closed_at=_ts(),
        verdict_json=verdict,
        pr_url="https://github.com/example/repo/pull/123",
    )

    row = store.get_session("run-3")
    assert row is not None
    assert row["status"] == "approved"
    assert row["closed_at"] is not None
    assert json.loads(row["verdict_json"]) == verdict
    assert row["pr_url"] == "https://github.com/example/repo/pull/123"


def test_get_active_sessions(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.db"))
    store.create_session("run-active", "U1", "C1", "Active", _ts())
    store.create_session("run-closed", "U2", "C2", "Closed", _ts())
    store.close_session("run-closed", status="rejected", closed_at=_ts(), error="nope")

    rows = store.get_active_sessions()

    assert [row["run_id"] for row in rows] == ["run-active"]


def test_thread_safety(tmp_path):
    db_path = tmp_path / "sessions.db"
    store = SessionStore(str(db_path))
    errors: list[BaseException] = []

    def writer(prefix: str) -> None:
        try:
            for i in range(25):
                run_id = f"{prefix}-{i}"
                store.create_session(run_id, prefix, "C1", f"message {i}", _ts())
                store.update_container(run_id, f"container-{i}", f"sha-{i}")
                store.update_message_count(run_id, i + 1)
                if i % 2 == 0:
                    store.close_session(run_id, "closed", _ts())
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=("U1",)),
        threading.Thread(target=writer, args=("U2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 50

    sample = store.get_session("U1-24")
    assert sample is not None
    assert sample["message_count"] == 25
