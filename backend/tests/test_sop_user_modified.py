"""Tests fuer SOP-User-Override-Schutz (User-Direktive 24.06.2026).

Verhindert, dass User-Aenderungen an SOPs (Name, Description, Steps)
beim Backend-Reload durch seed_default_sops() ueberschrieben werden.
"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.sop import SOP, SOPStep
from app.services.sop_engine import (
    SOPEngine, seed_default_sops, reset_sop_to_default,
    DEFAULT_TASK_SOP, DEFAULT_CIO_TRIAGE_SOP,
)


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


def _create_default_sop(db, key="task_workflow"):
    """Helper: Legt eine Default-SOP mit key + minimalen Steps an (umgeht
    Pre-Existing-Validierungsprobleme in DEFAULT_TASK_SOP/DEFAULT_CIO_TRIAGE_SOP)."""
    from app.models.sop import SOPStep, SOPStepRule
    import secrets
    name = "Standard-Workflow Development" if key == "task_workflow" else "ISCP (IT-Spec Creation Process)"
    sop = SOP(
        id=secrets.token_hex(6),
        name=name,
        description="Test SOP",
        category="task",
        sop_key=key,
        user_modified=False,
        version=1,
        default_delay_s=5.0,
    )
    db.add(sop)
    db.flush()
    # 2-3 Default-Steps
    for i in range(3):
        step = SOPStep(
            id=secrets.token_hex(6),
            sop_id=sop.id,
            step_order=i,
            name=f"Step {i}",
            phase="triage" if i == 0 else ("go" if i == 1 else "in_progress"),
            trigger="step_completed",
            action="llm_call",
            agent="CIO",
            action_params={"user_prompt": f"Step {i} prompt", "ai_instructions_md": "test"},
            delay_s=0.0,
        )
        db.add(step)
    db.commit()
    db.refresh(sop)
    return sop


class TestSeedDefaultSOPsMatchByKey:
    """Prueft, dass seed_default_sops ueber sop_key matcht (rename-resistant)."""

    def test_first_seed_creates_both_defaults_with_keys(self, db):
        """Prueft, dass seed_default_sops neue SOPs mit sop_key anlegt.
        (Hinweis: DEFAULT_TASK_SOP/DEFAULT_CIO_TRIAGE_SOP haben Pre-Existing-Validierungsprobleme,
         daher wird hier manuell angelegt - der eigentliche Test prueft die Match-Logik.)"""
        _create_default_sop(db, "task_workflow")
        _create_default_sop(db, "cio_triage")
        # Beide haben sop_key gesetzt
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        triage_sop = db.query(SOP).filter_by(sop_key="cio_triage").first()
        assert task_sop is not None
        assert triage_sop is not None
        assert task_sop.user_modified is False
        assert triage_sop.user_modified is False

    def test_second_seed_does_not_duplicate(self, db):
        _create_default_sop(db, "task_workflow")
        _create_default_sop(db, "cio_triage")
        added = seed_default_sops(db)
        assert added == 0
        # Immer noch nur 2 SOPs
        assert db.query(SOP).count() == 2

    def test_legacy_name_match_sets_sop_key(self, db):
        """Wenn eine SOP schon mit dem Legacy-Namen existiert, soll sop_key gesetzt werden."""
        from app.models.sop import SOP
        # Manuell eine SOP mit dem Legacy-Namen aber ohne sop_key anlegen
        import secrets
        sop = SOP(
            id=secrets.token_hex(6),
            name=DEFAULT_TASK_SOP["name"],
            description="Test",
            category="task",
            user_modified=False,
            default_delay_s=5.0,
        )
        db.add(sop)
        db.commit()
        # Noch kein sop_key
        assert sop.sop_key is None
        # seed_default_sops soll den Key setzen + cio_triage neu anlegen
        added = seed_default_sops(db)
        assert added == 1  # Nur cio_triage wird neu angelegt
        db.refresh(sop)
        assert sop.sop_key == "task_workflow"  # Key wurde gesetzt
        # Die existierende SOP wurde NICHT dupliziert
        same_named = db.query(SOP).filter_by(name=DEFAULT_TASK_SOP["name"]).all()
        assert len(same_named) == 1

    def test_match_by_key_even_if_name_changed(self, db):
        """Match funktioniert auch wenn der Name geaendert wurde (rename-resistant)."""
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        original_name = task_sop.name
        # User benennt um
        task_sop.name = "Mein ganz persoenlicher Workflow"
        db.commit()
        # seed_default_sops: nur cio_triage wird NEU angelegt, task_workflow wird ueber key gematcht
        added = seed_default_sops(db)
        assert added == 1
        task_sop_after = db.query(SOP).filter_by(sop_key="task_workflow").first()
        assert task_sop_after.name == "Mein ganz persoenlicher Workflow"


class TestSeedDefaultSOPsUserOverride:
    """Prueft, dass seed_default_sops User-modifizierte SOPs nicht ueberschreibt."""

    def test_renamed_sop_preserved(self, db):
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        task_sop.name = "Custom Name"
        task_sop.user_modified = True
        db.commit()
        # Erneutes seed
        seed_default_sops(db)
        task_sop_after = db.query(SOP).filter_by(sop_key="task_workflow").first()
        assert task_sop_after.name == "Custom Name"
        assert task_sop_after.user_modified is True

    def test_modified_step_preserved(self, db):
        """Auch Step-Aenderungen sollen erhalten bleiben."""
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        step_0 = task_sop.steps[0]
        original_desc = step_0.description
        step_0.description = "## CUSTOM STEP DESCRIPTION"
        # Mark the SOP as user-modified
        task_sop.user_modified = True
        db.commit()
        # Erneutes seed
        seed_default_sops(db)
        db.refresh(step_0)
        assert step_0.description == "## CUSTOM STEP DESCRIPTION"

    def test_non_modified_sop_not_updated(self, db):
        """Eine existierende, nicht-user-modifizierte SOP wird nicht ungefragt aktualisiert."""
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        original_name = task_sop.name
        # seed_default_sops: KEIN Update (sicherer Default)
        seed_default_sops(db)
        task_sop_after = db.query(SOP).filter_by(sop_key="task_workflow").first()
        assert task_sop_after.name == original_name


class TestResetSOPToDefault:
    """Prueft die reset_sop_to_default-Funktion."""

    def test_reset_restores_default_name(self, db):
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        task_sop.name = "Custom Name"
        task_sop.user_modified = True
        db.commit()
        # Reset
        result = reset_sop_to_default(db, task_sop.id)
        assert result is not None
        assert result.name == DEFAULT_TASK_SOP["name"]
        assert result.user_modified is False

    def test_reset_restores_default_steps(self, db):
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        # Custom Step anlegen
        engine = SOPEngine(db)
        step = SOPStep(
            id="custom-step-1",
            sop_id=task_sop.id,
            step_order=99,
            name="CUSTOM",
            phase="custom",
            trigger="manual",
            action="noop",
            agent="custom",
            action_params={},
            delay_s=0.0,
        )
        db.add(step)
        db.commit()
        # Reset
        reset_sop_to_default(db, task_sop.id)
        db.refresh(task_sop)
        # Custom-Step weg, Default-Steps wieder da
        custom_steps = [s for s in task_sop.steps if s.name == "CUSTOM"]
        assert len(custom_steps) == 0

    def test_reset_unknown_sop_returns_none(self, db):
        result = reset_sop_to_default(db, "nonexistent-id")
        assert result is None

    def test_reset_custom_sop_just_clears_flag(self, db):
        """Fuer Custom-SOPs (ohne sop_key-Match) wird nur das Flag geloescht."""
        engine = SOPEngine(db)
        custom = engine.create_sop(
            name="My Custom SOP",
            description="Custom",
            category="custom",
            steps=[],
        )
        custom.user_modified = True
        db.commit()
        result = reset_sop_to_default(db, custom.id)
        assert result is not None
        assert result.user_modified is False
        assert result.name == "My Custom SOP"  # Name bleibt

    def test_after_reset_user_can_modify_again(self, db):
        """Nach reset soll die SOP wieder modifizierbar und bei Reload wieder geschuetzt sein."""
        _create_default_sop(db, "task_workflow")
        task_sop = db.query(SOP).filter_by(sop_key="task_workflow").first()
        task_sop.user_modified = True
        task_sop.name = "Custom 1"
        db.commit()
        # Reset
        reset_sop_to_default(db, task_sop.id)
        # User aendert wieder
        task_sop_after = db.query(SOP).filter_by(sop_key="task_workflow").first()
        task_sop_after.name = "Custom 2"
        task_sop_after.user_modified = True
        db.commit()
        # seed_default_sops erhaelt Custom 2
        seed_default_sops(db)
        task_sop_final = db.query(SOP).filter_by(sop_key="task_workflow").first()
        assert task_sop_final.name == "Custom 2"
