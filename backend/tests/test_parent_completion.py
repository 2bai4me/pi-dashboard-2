"""Tests fuer Auto-Complete-Parent (User-Direktive 23.06.2026).

Wenn alle Subtasks 'done' sind, wird der Parent-Task automatisch auf
'done' gesetzt.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Temp-DB mit tasks + token_usage Tabellen."""
    db_path = tmp_path / "test_parent.db"
    monkeypatch.setenv("PI_DB_PATH", str(db_path))
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE tasks (
            id VARCHAR(32) PRIMARY KEY,
            project_id VARCHAR(32),
            parent_id VARCHAR(32),
            title VARCHAR(500),
            description TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'triage',
            priority INTEGER NOT NULL DEFAULT 1,
            category VARCHAR(32) NOT NULL DEFAULT 'new_request',
            assigned_role VARCHAR(64),
            iteration_count INTEGER NOT NULL DEFAULT 0,
            "order" INTEGER NOT NULL DEFAULT 0,
            emergency BOOLEAN NOT NULL DEFAULT 0,
            worker_understanding_confirmed BOOLEAN NOT NULL DEFAULT 0,
            review_iteration_count INTEGER NOT NULL DEFAULT 0,
            bza_iteration_count INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME,
            meta TEXT
        );
        CREATE TABLE task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id VARCHAR(32) NOT NULL,
            ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            event VARCHAR(64) NOT NULL,
            agent VARCHAR(64),
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
            details TEXT
        );
        CREATE TABLE token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id VARCHAR(32),
            parent_task_id VARCHAR(32),
            model VARCHAR(128) NOT NULL DEFAULT 'm',
            provider VARCHAR(64) NOT NULL DEFAULT 'p',
            role VARCHAR(64),
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
            input_per_1m NUMERIC(10,4),
            output_per_1m NUMERIC(10,4),
            pricing_source VARCHAR(255),
            snapshot_at DATETIME,
            recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    yield str(db_path)


def _insert_task(db, id, parent_id=None, status="triage", meta=None):
    import sqlite3, json
    from datetime import datetime, timezone
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("""INSERT INTO tasks
                   (id, project_id, parent_id, title, description, status,
                    priority, category, iteration_count, "order", emergency,
                    worker_understanding_confirmed, review_iteration_count,
                    bza_iteration_count, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, "proj-1", parent_id, f"Task {id}", "Test",
                 status, 50, "new_request",
                 0, 0, 0, 0, 0, 0,
                 json.dumps(meta or {})))
    conn.commit()
    conn.close()


class TestParentCompletion:
    def test_no_parent_no_action(self, temp_db):
        """Task ohne parent_id: nichts tun."""
        import sqlite3
        from app.services.parent_completion import check_and_complete_parent

        _insert_task(temp_db, "task-1", parent_id=None, status="done")
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        result = check_and_complete_parent(cur, "task-1")
        assert result is None
        conn.close()

    def test_all_subtasks_done_completes_parent(self, temp_db):
        """Alle Subtasks done: Parent sollte auf done gesetzt werden."""
        import sqlite3
        from app.services.parent_completion import check_and_complete_parent

        _insert_task(temp_db, "parent-1", parent_id=None, status="go")
        _insert_task(temp_db, "sub-1", parent_id="parent-1", status="done")
        _insert_task(temp_db, "sub-2", parent_id="parent-1", status="done")
        _insert_task(temp_db, "sub-3", parent_id="parent-1", status="done")

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        result = check_and_complete_parent(cur, "sub-1")
        assert result == "parent-1"
        # Parent-Status pruefen
        cur.execute("SELECT status FROM tasks WHERE id = ?", ("parent-1",))
        assert cur.fetchone()["status"] == "done"
        conn.close()

    def test_one_subtask_pending_no_complete(self, temp_db):
        """Ein Subtask noch nicht done: Parent bleibt."""
        import sqlite3
        from app.services.parent_completion import check_and_complete_parent

        _insert_task(temp_db, "parent-1", parent_id=None, status="go")
        _insert_task(temp_db, "sub-1", parent_id="parent-1", status="done")
        _insert_task(temp_db, "sub-2", parent_id="parent-1", status="in_progress")
        _insert_task(temp_db, "sub-3", parent_id="parent-1", status="done")

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        result = check_and_complete_parent(cur, "sub-1")
        assert result is None
        cur.execute("SELECT status FROM tasks WHERE id = ?", ("parent-1",))
        assert cur.fetchone()["status"] == "go"
        conn.close()

    def test_parent_already_done_no_action(self, temp_db):
        """Parent bereits done: nichts tun."""
        import sqlite3
        from app.services.parent_completion import check_and_complete_parent

        _insert_task(temp_db, "parent-1", parent_id=None, status="done")
        _insert_task(temp_db, "sub-1", parent_id="parent-1", status="done")

        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        result = check_and_complete_parent(cur, "sub-1")
        assert result is None
        conn.close()

    def test_parent_meta_has_aggregated_costs(self, temp_db):
        """Parent-Meta hat aggregierte Cost + Tokens."""
        import sqlite3
        from app.services.parent_completion import check_and_complete_parent

        _insert_task(temp_db, "parent-1", parent_id=None, status="go")
        _insert_task(temp_db, "sub-1", parent_id="parent-1", status="done")
        _insert_task(temp_db, "sub-2", parent_id="parent-1", status="done")

        # TokenUsage-Eintraege
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        for sub_id, ti, to, cost in [("sub-1", 100, 50, 0.005),
                                     ("sub-2", 200, 100, 0.01)]:
            cur.execute("""INSERT INTO token_usage
                           (task_id, parent_task_id, model, provider,
                            tokens_in, tokens_out, cost_usd, recorded_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (sub_id, "parent-1", "m", "p",
                         ti, to, cost, "2026-06-23"))
        conn.commit()
        conn.close()

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        check_and_complete_parent(cur, "sub-1")
        cur.execute("SELECT meta FROM tasks WHERE id = ?", ("parent-1",))
        meta = json.loads(cur.fetchone()["meta"])
        agg = meta["auto_completed_by"]
        assert agg["subtask_count"] == 2
        assert agg["total_tokens_in"] == 300
        assert agg["total_tokens_out"] == 150
        assert abs(agg["total_cost_usd"] - 0.015) < 0.001
        conn.close()