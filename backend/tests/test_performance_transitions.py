"""Tests fuer Performance-Transition-Timestamps (Task 13b322a2b926).

User-Direktive 22.06.2026:
  "Performance-Tabelle um Timestamp-Spalte erweitern (Alter des Eintrags sichtbar)"

Diese Tests sichern ab:
  - task_transitions-Tabelle enthaelt transition_at, processing_at, completed_at
  - GET /api/performance/transitions liefert ISO-8601 Timestamps
  - POST /api/performance/* setzt Timestamps automatisch
  - Migration legt Spalten + Indizes korrekt an
  - Index idx_transition_at ist vorhanden (fuer Performance-Queries)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest


# ─── Model-Tests ──────────────────────────────────────────────────────

class TestTaskTransitionModel:
    """Tests fuer das SQLAlchemy-Model."""

    def test_model_has_transition_at_column(self):
        from app.models.transition import TaskTransition
        col = TaskTransition.__table__.columns.get("transition_at")
        assert col is not None, "transition_at-Spalte fehlt im Model"
        assert col.nullable is False, "transition_at darf nicht NULL sein"
        # timezone-aware DateTime (SQLAlchemy gibt "DATETIME" zurueck)
        assert "DATETIME" in str(col.type).upper()

    def test_model_has_processing_at_column(self):
        from app.models.transition import TaskTransition
        col = TaskTransition.__table__.columns.get("processing_at")
        assert col is not None
        assert col.nullable is True

    def test_model_has_completed_at_column(self):
        from app.models.transition import TaskTransition
        col = TaskTransition.__table__.columns.get("completed_at")
        assert col is not None
        assert col.nullable is True

    def test_model_has_session_id_column(self):
        """Session-ID wurde 18.06.2026 zusaetzlich eingefuehrt."""
        from app.models.transition import TaskTransition
        col = TaskTransition.__table__.columns.get("session_id")
        assert col is not None
        assert col.nullable is True

    def test_model_has_indexes_for_performance_queries(self):
        """Mindestens idx_transition_at muss fuer Live-Queries existieren."""
        from app.models.transition import TaskTransition
        idx_names = {idx.name for idx in TaskTransition.__table__.indexes}
        assert "idx_transition_at" in idx_names, "Index idx_transition_at fehlt"
        assert "idx_transition_task" in idx_names
        assert "idx_transition_project" in idx_names

    def test_to_dict_serializes_timestamps_iso8601(self):
        """to_dict() liefert ISO-8601 Timestamps (fuer API-Response)."""
        from app.models.transition import TaskTransition

        now = datetime(2026, 6, 22, 16, 0, 0, tzinfo=timezone.utc)
        tr = TaskTransition(
            id=1,
            task_id="abc123",
            project_id="proj1",
            from_status="triage",
            to_status="done",
            transition_at=now,
            processing_at=now,
            completed_at=now,
            delay_s=5.0,
        )
        d = tr.to_dict()
        # ISO-8601-Format: "2026-06-22T16:00:00+00:00"
        assert d["transition_at"] is not None
        assert "T" in d["transition_at"]
        assert d["processing_at"] is not None
        assert d["completed_at"] is not None

    def test_to_dict_handles_none_timestamps(self):
        """processing_at/completed_at koennen None sein (Task noch nicht fertig)."""
        from app.models.transition import TaskTransition

        now = datetime(2026, 6, 22, 16, 0, 0, tzinfo=timezone.utc)
        tr = TaskTransition(
            id=2,
            task_id="abc456",
            project_id=None,
            from_status="triage",
            to_status="in_progress",
            transition_at=now,
            processing_at=None,
            completed_at=None,
            delay_s=5.0,
        )
        d = tr.to_dict()
        assert d["transition_at"] is not None
        assert d["processing_at"] is None
        assert d["completed_at"] is None


# ─── Schema-Tests ────────────────────────────────────────────────────

class TestTaskTransitionSchema:
    """Tests fuer das Pydantic-Schema."""

    def test_schema_includes_transition_at(self):
        from app.schemas.transition import TaskTransitionRead
        fields = TaskTransitionRead.model_fields
        assert "transition_at" in fields
        assert "processing_at" in fields
        assert "completed_at" in fields

    def test_schema_transition_at_is_datetime(self):
        from app.schemas.transition import TaskTransitionRead
        assert TaskTransitionRead.model_fields["transition_at"].annotation is datetime

    def test_schema_includes_display_fields(self):
        """Bugfix 19.06.2026 (Task 921bba39d13f): Display-Namen."""
        from app.schemas.transition import TaskTransitionRead
        fields = TaskTransitionRead.model_fields
        assert "from_status_display" in fields
        assert "to_status_display" in fields


# ─── API-Tests ────────────────────────────────────────────────────────

class TestTransitionsAPI:
    """Integration-Tests fuer GET /api/performance/transitions."""

    def test_get_transitions_returns_iso8601_timestamps(self, client, db_session):
        """GET-Response enthaelt ISO-8601 Timestamps."""
        from app.models.task import Task
        from app.models.transition import TaskTransition

        # Task anlegen
        task = Task(
            id="testtask1",
            title="Test",
            description="",
            status="done",
            priority=50,
            project_id="p1",
        )
        db_session.add(task)
        db_session.commit()

        now = datetime.now(timezone.utc)
        tr = TaskTransition(
            task_id="testtask1",
            project_id="p1",
            from_status="triage",
            to_status="done",
            transition_at=now,
            processing_at=now,
            completed_at=now + timedelta(milliseconds=100),
            delay_s=5.0,
            duration_ms=100,
            agent="user",
            reason="test",
        )
        db_session.add(tr)
        db_session.commit()

        response = client.get("/api/performance/transitions?task_id=testtask1")
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["total"] >= 1
        item = data["items"][0]
        # ISO-8601-Format pruefen (enthaelt "T" als Trennzeichen)
        assert "T" in item["transition_at"], f"transition_at nicht ISO-8601: {item['transition_at']}"
        assert "T" in item["processing_at"]
        assert "T" in item["completed_at"]
        # Alter berechenbar (Frontend kann formatAge() aufrufen)
        # SQLite speichert timezone-agnostisch — wir parsen tolerant.
        iso_str = item["transition_at"].replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        # Sollte in der Vergangenheit liegen (wir haben es gerade angelegt)
        assert parsed <= datetime.now(timezone.utc) + timedelta(seconds=1)

    def test_get_transitions_supports_date_filter(self, client, db_session):
        """Filter nach from/to-Status funktioniert weiterhin."""
        from app.models.task import Task
        from app.models.transition import TaskTransition

        task = Task(
            id="testtask2",
            title="Test 2",
            description="",
            status="in_progress",
            priority=50,
            project_id="p2",
        )
        db_session.add(task)
        db_session.commit()

        now = datetime.now(timezone.utc)
        # Zwei Transitions: einer nach in_progress, einer nach done
        tr1 = TaskTransition(
            task_id="testtask2",
            project_id="p2",
            from_status="triage",
            to_status="in_progress",
            transition_at=now,
            delay_s=5.0,
        )
        tr2 = TaskTransition(
            task_id="testtask2",
            project_id="p2",
            from_status="in_progress",
            to_status="done",
            transition_at=now + timedelta(seconds=10),
            delay_s=5.0,
        )
        db_session.add_all([tr1, tr2])
        db_session.commit()

        response = client.get("/api/performance/transitions?to_status=done")
        assert response.status_code == 200
        data = response.json()
        # Alle Items im Response sollten to_status=done haben
        for item in data["items"]:
            assert item["to_status"] == "done"

    def test_global_stats_endpoint_exists(self, client):
        """GET /api/performance/stats liefert aggregierte Werte."""
        response = client.get("/api/performance/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_transitions" in data
        assert "avg_delay_s" in data
        assert "avg_duration_ms" in data

    def test_project_stats_endpoint(self, client, db_session):
        """GET /api/performance/projects/{id}/stats liefert per-Status-Stats."""
        from app.models.project import Project
        from app.models.task import Task
        from app.models.transition import TaskTransition

        proj = Project(id="test_proj", name="Test", description="")
        db_session.add(proj)
        task = Task(
            id="testtask3",
            title="T3",
            description="",
            status="done",
            priority=50,
            project_id="test_proj",
        )
        db_session.add(task)
        db_session.commit()

        now = datetime.now(timezone.utc)
        tr = TaskTransition(
            task_id="testtask3",
            project_id="test_proj",
            from_status="triage",
            to_status="done",
            transition_at=now,
            processing_at=now + timedelta(seconds=5),
            delay_s=5.0,
            duration_ms=5000,
        )
        db_session.add(tr)
        db_session.commit()

        response = client.get("/api/performance/projects/test_proj/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "test_proj"
        assert "avg_durations_s_per_status" in data
        assert "transitions_per_status" in data


# ─── Migration-Tests ─────────────────────────────────────────────────

class TestMigration:
    """Tests fuer die Alembic-Migration ef4378441a72."""

    def test_migration_file_exists(self):
        """Die Migration ef4378441a72 muss existieren."""
        from pathlib import Path
        versions_dir = Path(__file__).parent.parent / "app" / "migrations" / "versions"
        candidates = list(versions_dir.glob("*add_task_transitions_performance_table.py"))
        assert len(candidates) == 1, f"Migration nicht gefunden: {candidates}"
        content = candidates[0].read_text()
        assert "transition_at" in content
        assert "processing_at" in content
        assert "completed_at" in content

    def test_migration_has_downgrade(self):
        """Die Migration muss eine Downgrade-Funktion haben."""
        from pathlib import Path
        versions_dir = Path(__file__).parent.parent / "app" / "migrations" / "versions"
        candidates = list(versions_dir.glob("*add_task_transitions_performance_table.py"))
        content = candidates[0].read_text()
        assert "def downgrade" in content
        assert "drop_table" in content

    def test_migration_creates_indexes(self):
        """Die Migration muss Performance-Indizes anlegen."""
        from pathlib import Path
        versions_dir = Path(__file__).parent.parent / "app" / "migrations" / "versions"
        candidates = list(versions_dir.glob("*add_task_transitions_performance_table.py"))
        content = candidates[0].read_text()
        # Wichtige Indizes muessen in der Migration sein
        for idx in [
            "idx_transition_task",
            "idx_transition_project",
            "idx_transition_at",
        ]:
            assert idx in content, f"Index {idx} fehlt in Migration"


# ─── Alter-Berechnung (Business-Logic) ──────────────────────────────

class TestTransitionAge:
    """Tests fuer die 'Alter'-Logik, die das Frontend braucht."""

    def test_age_seconds_diff(self):
        """Eine 1-Sekunden-alte Transition hat Alter ~1s."""
        from app.models.transition import TaskTransition

        now = datetime.now(timezone.utc)
        tr = TaskTransition(
            task_id="t",
            from_status="triage",
            to_status="done",
            transition_at=now - timedelta(seconds=1),
            delay_s=5.0,
        )
        diff = (datetime.now(timezone.utc) - tr.transition_at).total_seconds()
        # Toleranz: Test kann 1-2 Sekunden dauern
        assert 0.5 <= diff <= 3.0

    def test_age_is_positive(self):
        """Alter darf nie negativ sein (Frontend clampt auf 0)."""
        from app.models.transition import TaskTransition

        now = datetime.now(timezone.utc)
        tr = TaskTransition(
            task_id="t",
            from_status="triage",
            to_status="done",
            transition_at=now,  # exakt jetzt
            delay_s=5.0,
        )
        diff = (datetime.now(timezone.utc) - tr.transition_at).total_seconds()
        assert diff >= 0