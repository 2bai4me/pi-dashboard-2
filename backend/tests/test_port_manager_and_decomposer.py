"""Tests fuer Port-Manager und Task-Decomposer.

User-Direktive 23.06.2026 (Task 4bf7146b0780):
- Port-Management: reserve_block, release_block, find_free_block
- Task-Decomposition: should_decompose, detect_themes
"""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Temp-DB mit port_allocations-Tabelle."""
    db_path = tmp_path / "test_ports.db"
    monkeypatch.setenv("PI_DB_PATH", str(db_path))
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE app_port_allocations (
            id VARCHAR(32) PRIMARY KEY,
            app_name VARCHAR(64) NOT NULL,
            port_start INTEGER NOT NULL,
            port_end INTEGER NOT NULL,
            task_id VARCHAR(32),
            allocated_at DATETIME,
            released_at DATETIME,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()
    yield str(db_path)


# === Port-Manager Tests ===

class TestPortManager:
    def test_find_free_block_finds_10_consecutive(self, temp_db):
        """Sollte einen 10er-Block finden, der frei ist."""
        from app.services.port_manager import find_free_block
        block = find_free_block("test-app", count=10, start_search=8000)
        assert block is not None
        assert block[1] - block[0] == 9  # 10 Ports = 9 Differenz

    def test_find_free_block_avoids_reserved(self, temp_db):
        """Sollte reservierte Bereiche ueberspringen."""
        from app.services.port_manager import find_free_block, RESERVED_RANGES
        # Suche ab 1024, sollte 5555-5560 ueberspringen
        block = find_free_block("test-app", count=10, start_search=1024)
        assert block is not None
        # Block sollte nicht in RESERVED_RANGES fallen
        for reserved_start, reserved_end in RESERVED_RANGES:
            if reserved_start >= 1024:
                assert not (block[0] <= reserved_end and block[1] >= reserved_start), \
                    f"Block {block} kollidiert mit reserviertem {reserved_start}-{reserved_end}"

    def test_reserve_and_release(self, temp_db):
        """Reserviert und gibt einen Block frei."""
        from app.services.port_manager import reserve_block, release_block, list_allocations
        block = reserve_block("my-app", task_id="task-1", count=10)
        assert block.status == "active"
        assert block.port_end - block.port_start == 9

        allocs = list_allocations(app_name="my-app")
        assert len(allocs) == 1

        success = release_block(block.id)
        assert success is True

        allocs_after = list_allocations(app_name="my-app")
        assert allocs_after[0].status == "released"

    def test_multiple_blocks_per_app(self, temp_db):
        """Mehrere Bloecke pro App sind erlaubt."""
        from app.services.port_manager import reserve_block, list_allocations
        b1 = reserve_block("my-app", count=10)
        b2 = reserve_block("my-app", count=10)
        assert b1.id != b2.id
        assert b1.port_start != b2.port_start
        allocs = list_allocations(app_name="my-app")
        assert len(allocs) == 2

    def test_find_block_for_task(self, temp_db):
        """Sollte den Block fuer einen bestimmten Task finden."""
        from app.services.port_manager import reserve_block, find_block_for_task
        reserve_block("my-app", task_id="task-x", count=10)
        reserve_block("my-app", task_id="task-y", count=10)
        block_x = find_block_for_task("task-x")
        assert block_x is not None
        assert block_x.task_id == "task-x"


# === Decomposer Tests ===

class TestTaskDecomposer:
    def test_detect_themes_frontend_backend(self):
        """Erkennt Frontend + Backend Themen."""
        from app.services.task_decomposer import detect_themes
        text = "Bau eine neue Login-Page mit React-Frontend und FastAPI-Backend"
        themes = detect_themes(text)
        assert "frontend" in themes
        assert "backend" in themes

    def test_detect_themes_single(self):
        """Erkennt nur ein Thema."""
        from app.services.task_decomposer import detect_themes
        text = "Implementiere eine Login-Seite mit React"
        themes = detect_themes(text)
        assert "frontend" in themes
        assert len(themes) == 1

    def test_should_decompose_multiple_themes(self):
        """Sollte zerlegen bei mehreren Themen."""
        from app.services.task_decomposer import should_decompose
        title = "Login-System implementieren"
        description = (
            "Wir brauchen ein neues Login-System mit React-Frontend, "
            "FastAPI-Backend, PostgreSQL-Datenbank und JWT-Authentifizierung. "
            "Dazu gehoeren Tests, Deployment und Dokumentation."
        )
        result = should_decompose(title, description)
        assert result.should_split is True
        assert len(result.detected_themes) >= 2
        assert len(result.proposed_subtasks) >= 2

    def test_should_not_decompose_single_topic(self):
        """Sollte NICHT zerlegen bei nur einem Thema."""
        from app.services.task_decomposer import should_decompose
        title = "Login-Button rot einfärben"
        description = "Der Login-Button auf der Startseite soll rot statt blau sein."
        result = should_decompose(title, description)
        assert result.should_split is False

    def test_should_not_decompose_short_description(self):
        """Sollte NICHT zerlegen bei zu kurzer Description."""
        from app.services.task_decomposer import should_decompose
        result = should_decompose("Test", "Kurze Beschreibung")
        assert result.should_split is False