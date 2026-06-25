"""Tests fuer _substitute_task_placeholders (User-Direktive 24.06.2026)."""
from __future__ import annotations

import os
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.task import Task
from app.models.project import Project
from app.models.sop import SOP, SOPStep, SOPInstance
from app.services.sop_engine import _substitute_task_placeholders, _get_status_display


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_task(db):
    proj = Project(
        id="proj-1", name="Test-Project", project_number="PROJ-2026-099",
        status="active", mode="execution",
    )
    task = Task(
        id="task-1",
        title="Test-Task: Login implementieren",
        description="Login mit OAuth2 und Google-Provider.",
        status="triage", priority=50,
        project_id="proj-1",
        assigned_role="pi-coder",
        success_criteria=["Login funktioniert", "OAuth2 genutzt"],
        tags=["auth", "login"],
        meta={"decomposition": {"themes": ["frontend", "backend"]}},
    )
    db.add_all([proj, task])
    db.commit()
    return task, proj


class TestSubstituteTaskPlaceholders:
    """Prueft Template-Substitution fuer alle unterstuetzten Platzhalter."""

    def test_task_id(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "ID={task_id}", task=task)
        assert out == "ID=task-1"

    def test_task_title(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "Title: {task_title}", task=task)
        assert out == "Title: Test-Task: Login implementieren"

    def test_task_description(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "{task_description}", task=task)
        assert "Login mit OAuth2" in out

    def test_task_status_and_display(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(
            db, "{task_status} / {task_status_display}", task=task
        )
        assert out == "triage / Triage"

    def test_task_priority(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "Prio: {task_priority}", task=task)
        assert out == "Prio: 50"

    def test_project_name_and_number(self, db, sample_task):
        task, proj = sample_task
        out = _substitute_task_placeholders(
            db, "{project_name} ({project_number})", task=task
        )
        assert out == "Test-Project (PROJ-2026-099)"

    def test_success_criteria(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "{success_criteria}", task=task)
        data = json.loads(out)
        assert "Login funktioniert" in data
        assert "OAuth2 genutzt" in data

    def test_task_meta(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "{task_meta}", task=task)
        assert "decomposition" in out
        assert "frontend" in out

    def test_assigned_role(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(db, "Role: {assigned_role}", task=task)
        assert out == "Role: pi-coder"

    def test_unbekannter_platzhalter_bleibt(self, db, sample_task):
        task, _ = sample_task
        out = _substitute_task_placeholders(
            db, "Unbekannt: {unknown_xyz} bleibt!", task=task
        )
        assert out == "Unbekannt: {unknown_xyz} bleibt!"

    def test_leeres_task(self, db):
        """Ohne task-Objekt bleiben Task-Platzhalter unveraendert (Re-Use in Step 0 nicht noetig)."""
        out = _substitute_task_placeholders(db, "Task={task_id}", task=None)
        # Platzhalter bleibt unveraendert (kein Task-Kontext verfuegbar)
        assert out == "Task={task_id}"

    def test_task_ohne_description(self, db):
        """Task mit leerer Description: Platzhalter wird durch '[n/a]' ersetzt."""
        task = Task(
            id="t1", title="X", description="", status="triage",
            priority=50, project_id=None,
        )
        db.add(task)
        db.commit()
        out = _substitute_task_placeholders(
            db, "Desc={task_description}", task=task,
        )
        # Leere description -> [n/a]
        assert out == "Desc=[n/a]"

    def test_step_placeholder(self, db):
        """Step-Platzhalter (step_id, step_name, step_order, step_agent)."""
        from app.models.sop import SOPStep
        step = SOPStep(
            id="step-1", sop_id="sop-1", step_order=2, name="Test-Step",
            phase="go", trigger="manual", action="llm_call", agent="pi-architect",
            action_params={}, delay_s=0.0,
        )
        out = _substitute_task_placeholders(
            db,
            "Step {step_name} #{step_order} (agent={step_agent})",
            task=None, step=step,
        )
        assert out == "Step Test-Step #2 (agent=pi-architect)"

    def test_sop_placeholder(self, db):
        """SOP-Platzhalter (sop_id, sop_name)."""
        sop = SOP(id="sop-x", name="My-SOP", description="", category="task")
        db.add(sop)
        db.commit()
        inst = SOPInstance(
            id="inst-1", sop_id="sop-x", task_id=None, status="running",
        )
        out = _substitute_task_placeholders(
            db, "{sop_id} / {sop_name}", task=None, instance=inst,
        )
        assert out == "sop-x / My-SOP"

    def test_combined_prompt(self, db, sample_task):
        """Realistischer Prompt mit vielen Platzhaltern (wie in der SOP)."""
        task, _ = sample_task
        prompt = (
            "TASK: {task_title}\n"
            "DESC: {task_description}\n"
            "STATUS: {task_status}\n"
            "PROJECT: {project_name} ({project_number})\n"
            "CRITERIA: {success_criteria}\n"
            "AGENT: {assigned_role}"
        )
        out = _substitute_task_placeholders(db, prompt, task=task)
        assert "Test-Task: Login implementieren" in out
        assert "Login mit OAuth2" in out
        assert "triage" in out
        assert "Test-Project" in out
        assert "PROJ-2026-099" in out
        assert "pi-coder" in out
        # Keine Platzhalter mehr im Output
        assert "{" not in out or "{unknown" in out


class TestGetStatusDisplay:
    def test_known_statuses(self):
        assert _get_status_display("triage") == "Triage"
        assert _get_status_display("todo") == "GO"
        assert _get_status_display("in_progress") == "In Progress"
        assert _get_status_display("done") == "Done"
        assert _get_status_display("rueckfrage") == "Rückfrage"
        assert _get_status_display("cancelled") == "Cancelled"

    def test_unknown_status(self):
        assert _get_status_display("xyz") == "xyz"
        assert _get_status_display("") == "[n/a]"
        assert _get_status_display(None) == "[n/a]"
