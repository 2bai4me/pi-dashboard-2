"""Tests fuer project_id-Handling (FIX 23.06.2026, Task 0973563537c4)."""
import pytest
from pydantic import ValidationError

from app.schemas.task import TaskUpdate


class TestProjectIdHandling:
    def test_task_update_allows_project_id(self):
        """TaskUpdate-Schema akzeptiert project_id (FIX: vorher wurde es ignoriert)."""
        u = TaskUpdate(project_id="abc123")
        assert u.project_id == "abc123"

    def test_task_update_project_id_optional(self):
        """project_id ist optional (default None)."""
        u = TaskUpdate(title="Test")
        assert u.project_id is None

    def test_task_update_project_id_explicit_none(self):
        """project_id=None ist erlaubt (Self-Tracking)."""
        u = TaskUpdate(project_id=None)
        assert u.project_id is None

    def test_task_update_project_id_set_in_dump(self):
        """project_id wird in model_dump(exclude_unset=True) aufgenommen wenn explizit gesetzt."""
        u = TaskUpdate(project_id="xyz", title="Test")
        dump = u.model_dump(exclude_unset=True)
        assert "project_id" in dump
        assert dump["project_id"] == "xyz"
        assert "title" in dump
        assert dump["title"] == "Test"

    def test_task_update_exclude_unset_omits_unset(self):
        """exclude_unset=True: nur explizit gesetzte Felder sind in dump."""
        u = TaskUpdate(project_id="abc")  # nur project_id explizit
        dump = u.model_dump(exclude_unset=True)
        assert "project_id" in dump
        assert "title" not in dump
        assert "status" not in dump
        assert "priority" not in dump


class TestProjectIdOrphanPolicy:
    """Dokumentation des project_id=None-Verhaltens (kein 400-Error)."""

    def test_orphan_task_is_legitimate_for_self_tracking(self):
        """project_id=None ist GUELTIG fuer:
        - Service-Self-Tracking (z.B. ME4-PI-Integration trackt sich selbst)
        - Globale/projektuebergreifende Tasks (z.B. 'Doku schreiben')
        """
        # TaskCreate-Schema erlaubt project_id=None
        from app.schemas.task import TaskCreate
        t = TaskCreate(title="Service Self-Tracking", project_id=None)
        assert t.project_id is None

    def test_orphan_task_not_rejected_by_default(self):
        """TaskCreate akzeptiert project_id=None ohne Validierungs-Error."""
        from app.schemas.task import TaskCreate
        # Kein ValidationError
        t = TaskCreate(title="Test")
        assert t.project_id is None
