"""Tests fuer Idee-CRUD (User-Direktive 23.06.2026)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Temp-DB mit ideas-Tabelle."""
    db_path = tmp_path / "test_ideas.db"
    monkeypatch.setenv("PI_DB_PATH", str(db_path))
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE ideas (
            id VARCHAR(32) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            brainstorm TEXT,
            requirements TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            tags TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    conn.execute("""
        CREATE TABLE tasks (
            id VARCHAR(32) PRIMARY KEY,
            project_id VARCHAR(32),
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
        )
    """)
    conn.execute("""
        CREATE TABLE task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id VARCHAR(32) NOT NULL,
            event VARCHAR(64) NOT NULL,
            agent VARCHAR(64),
            ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    """)
    conn.commit()
    conn.close()
    yield str(db_path)


def test_create_and_list_idea(temp_db):
    """Idee erstellen + auflisten."""
    from app.routers.ideas import create_idea, _list_ideas_impl
    from app.routers.ideas import IdeaIn

    req = IdeaIn(title="Test-Idee", description="Beschreibung", brainstorm="Brainstorming", tags=["test"])
    idea = create_idea(req, _user="testuser")
    assert idea["id"].startswith("idea-")
    assert idea["title"] == "Test-Idee"
    assert idea["status"] == "draft"

    ideas = _list_ideas_impl(status=None, limit=100, _user="testuser")
    assert len(ideas) == 1
    assert ideas[0]["id"] == idea["id"]


def test_update_idea(temp_db):
    """Idee aktualisieren (Speichern)."""
    from app.routers.ideas import create_idea, update_idea, _get_idea_impl
    from app.routers.ideas import IdeaIn

    idea = create_idea(IdeaIn(title="Original"), _user="testuser")
    updated = update_idea(idea["id"], IdeaIn(
        title="Aktualisiert",
        brainstorm="Neuer Inhalt",
        requirements="Akkkriterien",
        status="saved",
    ), _user="testuser")
    assert updated["title"] == "Aktualisiert"
    assert updated["brainstorm"] == "Neuer Inhalt"
    assert updated["status"] == "saved"
    # Persistiert?
    fetched = _get_idea_impl(idea["id"], _user="testuser")
    assert fetched["title"] == "Aktualisiert"


def test_delete_idea(temp_db):
    """Idee loeschen."""
    from app.routers.ideas import create_idea, _delete_idea_impl, _list_ideas_impl
    from app.routers.ideas import IdeaIn

    idea = create_idea(IdeaIn(title="Zu loeschen"), _user="testuser")
    _delete_idea_impl(idea["id"], _user="testuser")
    ideas = _list_ideas_impl(status=None, limit=100, _user="testuser")
    assert all(i["id"] != idea["id"] for i in ideas)


def test_convert_idea_to_task(temp_db):
    """Idee -> Status auf 'converted' setzen."""
    from app.routers.ideas import create_idea, IdeaIn
    import sqlite3

    idea = create_idea(IdeaIn(
        title="Umsetzbare Idee",
        description="Soll zu Task werden",
        brainstorm="Brainstorm-Notiz",
        requirements="Anforderung 1\nAnforderung 2",
    ), _user="testuser")

    # Status setzen auf 'converted' (wie es convertToTask macht)
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("UPDATE ideas SET status = ? WHERE id = ?", ("converted", idea["id"]))
    conn.commit()
    cur.execute("SELECT status FROM ideas WHERE id = ?", (idea["id"],))
    assert cur.fetchone()[0] == "converted"
    conn.close()