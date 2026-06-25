"""Tests fuer SOPEngine.run_single_step() (User-Direktive 24.06.2026).

Verifiziert, dass run_single_step:
- NUR den aktuellen Step ausfuehrt
- KEIN advance() zum naechsten Step macht
- Instance-Status auf 'paused' setzt
- step_result im Context speichert
- Audit-Log schreibt
"""
from __future__ import annotations

import os
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import asyncio
import json
from datetime import datetime
from unittest.mock import patch, AsyncMock
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.sop import SOP, SOPStep, SOPInstance, SOPExecution
from app.models.task import Task
from app.models.project import Project
from app.models.history import TaskHistory
from app.services.sop_engine import SOPEngine


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
def sop_with_steps(db):
    """SOP mit 3 Steps: CIO Triage (llm_call) -> Plan (llm_call) -> Test (noop)."""
    sop = SOP(
        id="sop-test",
        name="Test-SOP",
        description="Test",
        category="task",
        sop_key="test_sop",
        user_modified=False,
    )
    db.add(sop)
    db.flush()
    from app.models.sop import SOPStepRule
    steps = []
    for i, (action, agent, next_step) in enumerate([
        ("llm_call", "CIO", "step-1"),
        ("llm_call", "pi-architect", "step-2"),
        ("noop", "system", None),
    ]):
        step = SOPStep(
            id=f"step-{i}",
            sop_id=sop.id,
            step_order=i,
            name=f"Step {i}",
            phase="triage" if i == 0 else "go",
            trigger="step_completed",
            action=action,
            agent=agent,
            action_params={"user_prompt": f"Step {i} prompt", "ai_instructions_md": "x"},
            delay_s=0.0,
            next_step_id=next_step,
        )
        db.add(step)
        steps.append(step)
        # Rule: wenn step_ok == true, dann advance
        if next_step:
            rule = SOPStepRule(
                id=f"rule-{i}",
                step_id=step.id,
                rule_order=0,
                condition_field="step_ok",
                condition_operator="eq",
                condition_value=True,
                action_type="move_status",
                action_target=next_step,
            )
            db.add(rule)
    db.commit()
    return sop, steps


@pytest.fixture
def project_and_task(db, sop_with_steps):
    sop, _ = sop_with_steps
    proj = Project(
        id="proj-1", name="Test-Project",
        description="", status="active", mode="execution",
    )
    task = Task(
        id="task-1", title="Test-Task", description="Beschreibung",
        status="triage", project_id="proj-1", priority=50,
    )
    db.add_all([proj, task])
    db.commit()
    inst = SOPInstance(
        id="inst-1", sop_id=sop.id, task_id=task.id,
        current_step_id="step-0", status="running",
    )
    db.add(inst)
    db.commit()
    return proj, task, inst


class TestRunSingleStep:
    """Prueft die zentrale Funktion."""

    @pytest.mark.asyncio
    async def test_step_executed_no_advance(self, db, project_and_task):
        """Step wird ausgefuehrt, aber KEIN advance zum naechsten Step."""
        _, _, instance = project_and_task
        engine = SOPEngine(db)

        mock_resp = {
            "content": '{"ok": true, "issues": []}',
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 10, "tokens_out": 5},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await engine.run_single_step(instance)

        assert result["ok"] is True
        assert result["mode"] == "single_step"
        assert result["step_id"] == "step-0"
        assert result["step_name"] == "Step 0"
        # Instance bleibt auf Step 0 (KEIN advance)
        db.refresh(instance)
        assert instance.current_step_id == "step-0"
        # Status ist 'paused'
        assert instance.status == "paused"
        # Naechster Step wird nur VORGESCHLAGEN
        assert result["next_step_id"] == "step-1"
        assert result["next_step_name"] == "Step 1"
        # step_result ist im Context
        ctx = instance.context or {}
        assert "step_0_result" in ctx
        assert ctx["step_0_result"]["ok"] is True

    @pytest.mark.asyncio
    async def test_audit_log_single_step(self, db, project_and_task):
        """Audit-Eintraege step_started + step_completed mit mode='single_step'."""
        _, _, instance = project_and_task
        engine = SOPEngine(db)

        mock_resp = {
            "content": "OK", "model": "m", "provider": "p",
            "usage": {"tokens_in": 1, "tokens_out": 1},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            await engine.run_single_step(instance)

        # Audit-Eintraege pruefen
        executions = db.query(SOPExecution).filter_by(instance_id=instance.id).all()
        events = [e.event for e in executions]
        assert "step_started" in events
        assert "step_completed" in events
        # Beide haben mode='single_step' in details
        for e in executions:
            if e.event in ("step_started", "step_completed"):
                assert e.details.get("mode") == "single_step"

    @pytest.mark.asyncio
    async def test_instance_status_paused_not_completed(self, db, project_and_task):
        """Instance-Status ist 'paused', NICHT 'completed' (anders als run_step)."""
        _, _, instance = project_and_task
        engine = SOPEngine(db)

        mock_resp = {
            "content": "OK", "model": "m", "provider": "p",
            "usage": {"tokens_in": 1, "tokens_out": 1},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await engine.run_single_step(instance)

        db.refresh(instance)
        # Status 'paused', NICHT 'completed'
        assert instance.status == "paused"
        assert result["instance_status"] == "paused"

    @pytest.mark.asyncio
    async def test_task_status_unchanged(self, db, project_and_task):
        """Task-Status bleibt NICHT auf 'done' (wie es run_step am Ende macht).
        Waehrend des LLM-Calls darf auf 'in_progress' gesetzt werden (Agent arbeitet)."""
        _, task, instance = project_and_task
        engine = SOPEngine(db)

        mock_resp = {
            "content": "OK", "model": "m", "provider": "p",
            "usage": {"tokens_in": 1, "tokens_out": 1},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            await engine.run_single_step(instance)

        db.refresh(task)
        # Task-Status ist NICHT 'done' (das ist der Hauptunterschied zu run_step)
        assert task.status != "done", (
            f"run_single_step darf Task NICHT auf 'done' setzen, "
            f"aktueller Status: {task.status}"
        )
        # Assigned-Role wird auf step.agent gesetzt
        assert task.assigned_role == "CIO"

    @pytest.mark.asyncio
    async def test_subsequent_call_advances_via_run_step(self, db, project_and_task):
        """Nach run_single_step kann run_step() zum naechsten Step advance."""
        _, _, instance = project_and_task
        engine = SOPEngine(db)

        mock_resp = {
            "content": '{"ok": true, "issues": []}',
            "model": "m", "provider": "p",
            "usage": {"tokens_in": 1, "tokens_out": 1},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            # Erst single step
            r1 = await engine.run_single_step(instance)
            assert r1["ok"] is True
            assert instance.status == "paused"
            assert instance.current_step_id == "step-0"

            # Dann run_step -> advance zu step-1
            # Status auf 'running' setzen, sonst fail
            instance.status = "running"
            db.commit()
            r2 = await engine.run_step(instance)
            db.refresh(instance)
            assert instance.current_step_id == "step-1"

    @pytest.mark.asyncio
    async def test_noop_step_works(self, db, project_and_task):
        """noop-Step funktioniert auch (kein LLM-Call noetig)."""
        _, _, instance = project_and_task
        # Setze current_step_id auf noop-step
        instance.current_step_id = "step-2"
        db.commit()
        engine = SOPEngine(db)

        result = await engine.run_single_step(instance)
        assert result["ok"] is True
        assert result["step_id"] == "step-2"
        # noop macht nichts, aber Status auf paused
        db.refresh(instance)
        assert instance.status == "paused"

    @pytest.mark.asyncio
    async def test_fails_if_instance_not_running(self, db, project_and_task):
        """Wenn Instance nicht running/paused ist, wird abgebrochen."""
        _, _, instance = project_and_task
        instance.status = "completed"
        db.commit()
        engine = SOPEngine(db)

        result = await engine.run_single_step(instance)
        assert result["ok"] is False
        assert "not running/paused" in result["error"]
