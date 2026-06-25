"""Tests fuer SOP-Action-Whitelist und action_params-Validierung."""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from unittest.mock import patch

# Env-Defaults MUSSEN vor dem Import von app-Modulen gesetzt werden,
# da config.py settings beim Laden instanziiert.
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.sop import SOPStep
from app.models.token_usage import TokenUsage
from app.services.sop_engine import SOPEngine, ALLOWED_SOP_ACTIONS
from app.schemas.sop_action import ALLOWED_ACTIONS


@pytest.fixture
def db():
    """Bereitstellt eine frische In-Memory-SQLite-Session pro Test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


class TestSOPActionWhitelist:
    """Whitelist- und Validierungstests fuer SOP-Actions."""

    def test_disallowed_action_in_create_sop_raises(self, db):
        """create_sop muss unbekannte Actions mit ValueError ablehnen."""
        engine = SOPEngine(db)

        with pytest.raises(ValueError, match="Disallowed SOP action"):
            engine.create_sop(
                name="Bad SOP",
                description="SOP with a disallowed action",
                steps=[
                    {
                        "name": "Bad Step",
                        "action": "evil_action",
                        "agent": "system",
                        "delay_s": 0.0,
                    }
                ],
            )

    def test_create_sop_accepts_allowed_action_with_valid_params(self, db):
        """create_sop muss gueltige Actions mit validen action_params akzeptieren."""
        engine = SOPEngine(db)

        sop = engine.create_sop(
            name="Good SOP",
            description="SOP with allowed action",
            steps=[
                {
                    "name": "Spawn Sub-SOP",
                    "action": "spawn_sop",
                    "agent": "system",
                    "delay_s": 0.0,
                    "action_params": {
                        "sop_id": "abc123",
                        "context": {"foo": "bar"},
                    },
                }
            ],
        )

        assert sop is not None
        assert len(sop.steps) == 1
        step = sop.steps[0]
        assert step.action == "spawn_sop"
        assert step.action_params == {
            "sop_id": "abc123",
            "context": {"foo": "bar"},
        }

    def test_create_sop_rejects_invalid_action_params(self, db):
        """create_sop muss ungueltige action_params gegen das Schema ablehnen."""
        engine = SOPEngine(db)

        with pytest.raises(ValueError):
            engine.create_sop(
                name="Bad Params SOP",
                description="SOP with invalid params",
                steps=[
                    {
                        "name": "Spawn without sop_id",
                        "action": "spawn_sop",
                        "agent": "system",
                        "delay_s": 0.0,
                        "action_params": {"context": {"foo": "bar"}},
                    }
                ],
            )

    def test_run_step_rejects_unknown_action(self, db):
        """run_step muss bei nicht erlaubter Actions ein ok=False zurueckgeben."""
        engine = SOPEngine(db)

        sop = engine.create_sop(
            name="Run SOP",
            description="SOP for run_step whitelist test",
            steps=[
                {
                    "name": "Initial Noop",
                    "action": "noop",
                    "agent": "system",
                    "delay_s": 0.0,
                }
            ],
        )
        instance = engine.create_instance(sop.id)
        assert instance is not None

        # Manipuliere die Action auf einen nicht erlaubten Wert
        step = db.get(SOPStep, instance.current_step_id)
        step.action = "not_allowed_action"
        db.commit()

        result = asyncio.run(engine.run_step(instance))

        assert result["ok"] is False
        assert "Unknown or disallowed SOP action" in result["error"]

    def test_allowed_action_runs(self, db):
        """Eine erlaubte noop-Action laeuft in run_step erfolgreich durch."""
        engine = SOPEngine(db)

        sop = engine.create_sop(
            name="Noop SOP",
            description="SOP with allowed noop action",
            steps=[
                {
                    "name": "Noop Step",
                    "action": "noop",
                    "agent": "system",
                    "delay_s": 0.0,
                }
            ],
        )
        instance = engine.create_instance(sop.id)
        assert instance is not None

        result = asyncio.run(engine.run_step(instance))

        assert result["ok"] is True
        # Wenn kein next_step definiert ist, markiert run_step die Instance als
        # completed und gibt action="completed" zurueck.
        assert result["action"] in ("noop", "completed")

    def test_whitelist_contains_expected_actions(self):
        """Die Engine-Whitelist enthaelt alle implementierten Actions."""
        expected = {
            "noop",
            "llm_call",
            "spawn_sop",
            "review_task",
            "assign_worker",
            "cio_final_review",
            "tester_code_review",
            "move_status",
            "approve_triage",
            "start_work",
            "submit_review",
            "tester_approve",
            "tester_reject",
            "cio_final_approve",
            "cio_final_reject",
            "check_title",
            "check_description",
            "check_success_criteria",
            "check_architecture",
            "check_consistency",
            "decide_triage",
        }
        assert expected.issubset(ALLOWED_SOP_ACTIONS)

    def test_whitelist_matches_schema(self):
        """Engine-Whitelist und Schema-Whitelist sind synchron."""
        assert ALLOWED_SOP_ACTIONS == ALLOWED_ACTIONS


class TestSOPExecutionGuards:
    """Tests fuer Timeout-, Budget- und Iterations-Guards in der SOP-Engine."""

    def test_step_execution_timeout(self, db):
        """Ein Step, der das Timeout ueberschreitet, wird abgebrochen."""
        engine = SOPEngine(db)

        sop = engine.create_sop(
            name="Timeout SOP",
            description="SOP with slow llm_call",
            steps=[
                {
                    "name": "Slow Step",
                    "action": "llm_call",
                    "agent": "system",
                    "delay_s": 0.0,
                    "action_params": {
                        "user_prompt": "test",
                        "timeout_sec": 0.05,
                    },
                }
            ],
        )
        instance = engine.create_instance(sop.id, task_id="task-123")

        async def slow_chat_completion(*args, **kwargs):
            await asyncio.sleep(0.2)
            return "never"

        with patch("app.services.sop_engine.chat_completion", side_effect=slow_chat_completion):
            result = asyncio.run(engine.run_step(instance))

        assert result["ok"] is False or result.get("action") == "failed"
        assert instance.status == "failed"

    def test_budget_guard_blocks_expensive_instance(self, db):
        """Wenn das Task-Budget ueberschritten ist, darf kein LLM-Call laufen."""
        engine = SOPEngine(db)

        sop = engine.create_sop(
            name="Budget SOP",
            description="SOP with tight budget",
            steps=[
                {
                    "name": "LLM Step",
                    "action": "llm_call",
                    "agent": "system",
                    "delay_s": 0.0,
                    "action_params": {
                        "user_prompt": "test",
                        "max_cost_usd": 1.0,
                    },
                }
            ],
        )
        instance = engine.create_instance(sop.id, task_id="task-budget")

        # Budget bereits ueberschritten
        db.add(TokenUsage(
            task_id="task-budget",
            model="test",
            provider="test",
            tokens_in=100,
            tokens_out=100,
            cost_usd=Decimal("5.00"),
        ))
        db.commit()

        with patch("app.services.sop_engine.chat_completion") as mock_llm:
            result = asyncio.run(engine.run_step(instance))

        mock_llm.assert_not_called()
        assert result["ok"] is False or result.get("action") == "failed"
        assert "budget" in result.get("reason", "").lower() or "budget" in str(result).lower()

    def test_iteration_guard_triggers_after_limit(self, db):
        """Ein Step darf nicht beliebig oft ausgefuehrt werden."""
        engine = SOPEngine(db)

        sop = engine.create_sop(
            name="Loop SOP",
            description="SOP with low iteration limit",
            steps=[
                {
                    "name": "Noop Step",
                    "action": "noop",
                    "agent": "system",
                    "delay_s": 0.0,
                    "action_params": {"max_step_iterations": 3},
                    "next_step": 0,  # auf sich selbst zeigen
                }
            ],
        )
        instance = engine.create_instance(sop.id)
        # SOPStep.next_step_id ist eine Beziehung; setze explizit auf eigenes id
        step = db.get(SOPStep, instance.current_step_id)
        step.next_step_id = step.id
        db.commit()

        for _ in range(3):
            asyncio.run(engine.run_step(instance))
            instance.status = "running"
            instance.current_step_id = step.id
            db.commit()

        # 4. Lauf muss vom Guard blockiert werden
        result = asyncio.run(engine.run_step(instance))

        assert result["ok"] is False or result.get("action") == "failed"
        assert "iteration" in str(result).lower()
