"""Tests fuer User-Override-Schutz bei seed_defaults (User-Direktive 24.06.2026).

Verhindert, dass User-Aenderungen an Rollen beim Backend-Reload
durch seed_defaults() ueberschrieben werden.
"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.role import Role
from app.services.role_service import RoleService, DEFAULT_ROLES


@pytest.fixture
def db():
    """Frische In-Memory-SQLite-Session pro Test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_roles(db):
    """Seeded Default-Rollen in der DB (idempotent)."""
    RoleService.seed_defaults(db)
    return db


class TestSeedDefaultsUserModified:
    """Prueft, dass seed_defaults() User-Aenderungen nicht ueberschreibt."""

    def test_first_seed_creates_all_defaults(self, db):
        added = RoleService.seed_defaults(db)
        assert added == len(DEFAULT_ROLES)
        # Alle Default-Rollen vorhanden
        for rd in DEFAULT_ROLES:
            r = db.query(Role).filter_by(name=rd["name"]).first()
            assert r is not None
            assert r.user_modified is False

    def test_second_seed_does_not_modify_defaults(self, db):
        RoleService.seed_defaults(db)
        # Original-Prompts speichern
        originals = {r.name: r.system_prompt for r in db.query(Role).all()}
        # Erneut seeden
        added = RoleService.seed_defaults(db)
        assert added == 0
        # Prompts unveraendert
        for name, prompt in originals.items():
            r = db.query(Role).filter_by(name=name).first()
            assert r.system_prompt == prompt

    def test_user_modification_is_preserved(self, seed_roles):
        """Kern-Test: User-Aenderung bleibt nach Reload erhalten."""
        cio = seed_roles.query(Role).filter_by(name="CIO").first()
        original_prompt = cio.system_prompt

        # User aendert CIO
        cio.user_modified = True
        cio.system_prompt = "## USER-CUSTOMIZED\nMein custom CIO-Prompt."
        seed_roles.commit()

        # seed_defaults (wie beim Startup)
        RoleService.seed_defaults(seed_roles)

        # Pruefen: Aenderung erhalten
        cio_after = seed_roles.query(Role).filter_by(name="CIO").first()
        assert cio_after.user_modified is True
        assert "USER-CUSTOMIZED" in cio_after.system_prompt
        assert cio_after.system_prompt != original_prompt

    def test_provider_migration_works_for_non_modified_roles(self, db):
        """Provider-Migration (z.B. CIO: minimax -> ollama) muss fuer NICHT-user-modifizierte Rollen greifen."""
        RoleService.seed_defaults(db)
        cio = db.query(Role).filter_by(name="CIO").first()
        old_model = cio.model
        old_provider = cio.provider

        # Simuliere Migration: Aendere DEFAULT_ROLES
        # (in der Praxis: DEFAULT_ROLES wird im Code geaendert)
        # Wir simulieren, indem wir manuell setzen
        cio.user_modified = True
        cio.model = "user-chosen-model"
        db.commit()

        # Andere Rolle: nicht user-modifiziert
        coder = db.query(Role).filter_by(name="pi-coder").first()
        coder.user_modified = False
        coder.model = "old-model"
        db.commit()

        # Erneutes seed_defaults
        RoleService.seed_defaults(db)

        # CIO bleibt custom
        cio_after = db.query(Role).filter_by(name="CIO").first()
        assert cio_after.model == "user-chosen-model"
        assert cio_after.user_modified is True

        # pi-coder wurde aktualisiert (nicht user-modifiziert)
        coder_after = db.query(Role).filter_by(name="pi-coder").first()
        # Wird auf aktuellen Default-Wert gesetzt
        coder_default = next(rd for rd in DEFAULT_ROLES if rd["name"] == "pi-coder")
        assert coder_after.model == coder_default["model"]


class TestResetToDefault:
    """Prueft die reset_to_default-Methode."""

    def test_reset_clears_user_modified_flag(self, seed_roles):
        cio = seed_roles.query(Role).filter_by(name="CIO").first()
        cio.user_modified = True
        cio.system_prompt = "Custom"
        seed_roles.commit()

        # Reset
        result = RoleService.reset_to_default(seed_roles, cio.id)
        assert result is not None
        assert result.user_modified is False
        # Prompt ist wieder der Default
        cio_default = next(rd for rd in DEFAULT_ROLES if rd["name"] == "CIO")
        assert result.system_prompt == cio_default["system_prompt"]

    def test_after_reset_seed_defaults_updates_again(self, seed_roles):
        """Nach reset_to_default soll seed_defaults() wieder aktualisieren koennen."""
        cio = seed_roles.query(Role).filter_by(name="CIO").first()
        cio.user_modified = True
        cio.system_prompt = "Custom"
        seed_roles.commit()

        # Reset
        RoleService.reset_to_default(seed_roles, cio.id)

        # User macht Aenderung
        cio_after = seed_roles.query(Role).filter_by(name="CIO").first()
        cio_after.user_modified = True
        cio_after.system_prompt = "Custom again"
        seed_roles.commit()

        # Erneutes seed_defaults erhaelt Custom
        RoleService.seed_defaults(seed_roles)
        cio_final = seed_roles.query(Role).filter_by(name="CIO").first()
        assert "Custom again" in cio_final.system_prompt

    def test_reset_unknown_role_returns_none(self, db):
        result = RoleService.reset_to_default(db, "nonexistent-id")
        assert result is None


class TestUpdateRoleMarksUserModified:
    """Prueft, dass das update_role via API user_modified korrekt setzt."""

    def test_update_with_protected_field_marks_user_modified(self, seed_roles):
        """Bei Aenderung von system_prompt wird user_modified=True gesetzt."""
        cio = seed_roles.query(Role).filter_by(name="CIO").first()
        assert cio.user_modified is False

        # Simulation der API-Logik aus roles.py
        update_data = {"system_prompt": "New prompt"}
        protected_fields = {"system_prompt", "provider", "model", "tool_whitelist",
                            "timeout_sec", "fresh_context"}
        if any(k in update_data for k in protected_fields):
            update_data["user_modified"] = True

        result = RoleService.update_role(seed_roles, cio.id, **update_data)
        assert result is not None
        assert result.user_modified is True
        assert result.system_prompt == "New prompt"

    def test_update_without_protected_field_does_not_mark(self, seed_roles):
        """Bei Aenderung von description (nicht protected) bleibt user_modified=False."""
        cio = seed_roles.query(Role).filter_by(name="CIO").first()
        assert cio.user_modified is False

        update_data = {"description": "New desc"}
        protected_fields = {"system_prompt", "provider", "model", "tool_whitelist",
                            "timeout_sec", "fresh_context"}
        if any(k in update_data for k in protected_fields):
            update_data["user_modified"] = True

        result = RoleService.update_role(seed_roles, cio.id, **update_data)
        assert result is not None
        assert result.user_modified is False
        assert result.description == "New desc"
