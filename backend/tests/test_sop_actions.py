"""Tests fuer SOP-Action-Whitelist und action_params-Validierung."""
from __future__ import annotations

import asyncio
import os

# Env-Defaults MUSSEN vor dem Import von app-Modulen gesetzt werden,
# da config.py settings beim Laden instanziiert.
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.sop import SOPStep
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
        """Die Engine-Whitelist enthaelt die geforderten Actions."""
        expected = {
            "noop",
            "set_status",
            "ask_user",
            "llm_call",
            "spawn_sop",
            "review_task",
            "assign_worker",
            "implement",
            "test",
            "cio_final_review",
            "tester_code_review",
        }
        assert expected.issubset(ALLOWED_SOP_ACTIONS)
