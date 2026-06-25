"""Tests für Provider-Resolver (Multi-Provider-Fähigkeit über Role → Credential)."""
from __future__ import annotations

import os

# Test-Env MUSS vor dem Import von app-Modulen gesetzt werden,
# da config.py settings beim Laden instanziiert.
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.role import Role
from app.models.provider_credential import ProviderCredential


@pytest.fixture(scope="session")
def engine():
    """Shared In-Memory-Engine für die Test-Session."""
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )


@pytest.fixture(scope="session")
def tables(engine):
    """Erstellt alle Tabellen einmal pro Session."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(engine, tables):
    """Frische DB-Session pro Test mit Rollback."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def resolver_session(engine, monkeypatch):
    """Lässt den Provider-Resolver die Test-DB verwenden."""
    from app.services import provider_resolver as pr

    TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(pr, "SessionLocal", TestSessionLocal)
    yield


class TestProviderResolver:
    """Unit-Tests für Provider-Resolver."""

    def test_resolver_uses_role_credential(
        self, db_session, resolver_session
    ):
        """Resolver bevorzugt Werte aus der referenzierten Credential einer Rolle."""
        from app.services.provider_resolver import resolve_model_config

        credential = ProviderCredential(
            provider="deepseek",
            model="deepseek-4-pro",
            label="DeepSeek Pro",
            api_key="sk-from-credential",
            base_url="https://api.deepseek.com/v1",
        )
        db_session.add(credential)
        db_session.flush()

        role = Role(
            id="role-pi-coder",
            name="pi-coder",
            role_type="sub_agent",
            provider="openrouter",
            model="openrouter/auto",
            api_key_id=credential.id,
        )
        db_session.add(role)
        db_session.commit()

        config = resolve_model_config("pi-coder")
        assert config["provider"] == "deepseek"
        assert config["model"] == "deepseek-4-pro"
        assert config["api_key"] == "sk-from-credential"
        assert config["base_url"] == "https://api.deepseek.com/v1"

    def test_resolver_uses_role_provider_model(
        self, db_session, resolver_session
    ):
        """Resolver verwendet lokale provider/model-Werte der Rolle."""
        from app.services.provider_resolver import resolve_model_config

        role = Role(
            id="role-pi-tester",
            name="pi-tester",
            role_type="sub_agent",
            provider="kimi",
            model="kimi-k2.7-code",
        )
        db_session.add(role)
        db_session.commit()

        config = resolve_model_config("pi-tester")
        assert config["provider"] == "kimi"
        assert config["model"] == "kimi-k2.7-code"

    def test_fallback_to_env(self, db_session, resolver_session, monkeypatch):
        """Fallback auf ENV funktioniert, wenn keine Rolle konfiguriert ist."""
        from app.config import settings
        from app.services.provider_resolver import resolve_model_config

        # Settings hat Vorrang vor os.environ; daher direkt patchen.
        monkeypatch.setattr(settings, "MINIMAX_API_KEY", "sk-minimax-test")
        monkeypatch.setattr(settings, "KIMI_API_KEY", "")

        config = resolve_model_config("unknown-role")
        assert config["provider"] == "minimax-direct"
        assert config["model"] == "minimax-m3"
        assert config["api_key"] == "sk-minimax-test"
        assert config["base_url"] == "https://api.minimax.io/v1"

    def test_error_when_nothing_configured(
        self, db_session, resolver_session, monkeypatch
    ):
        """Fehler, wenn weder Role noch ENV noch auth.json konfiguriert ist."""
        from app.config import settings
        from app.services import provider_resolver as pr
        from app.services.provider_resolver import resolve_model_config

        # Alle bekannten API-Keys in Settings und ENV leeren.
        for key in ("MINIMAX_API_KEY", "KIMI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
            if hasattr(settings, key):
                monkeypatch.setattr(settings, key, "")
            monkeypatch.delenv(key, raising=False)

        # Auch auth.json leeren, damit der Test isoliert bleibt.
        monkeypatch.setattr(pr, "_read_auth_json", lambda: {})

        with pytest.raises(RuntimeError, match="Keine Provider-Konfiguration"):
            resolve_model_config("unknown-role")
