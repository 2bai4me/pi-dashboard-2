"""Tests für Provider Credentials (zentrale API-Key-Verwaltung)."""
from __future__ import annotations

import os

# Test-Env MUSS vor dem Import von app-Modulen gesetzt werden,
# da config.py settings beim Laden instanziiert.
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base, get_db
from app.routers import provider_credentials


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


@pytest.fixture(autouse=True)
def disable_auth(monkeypatch):
    """Auth für Router-Tests deaktivieren."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)


@pytest.fixture
def client(db_session):
    """TestClient mit überschriebener DB-Dependency."""
    app = FastAPI()
    app.include_router(provider_credentials.router)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    del app.dependency_overrides[get_db]


class TestProviderCredentials:
    """Backend-Tests für Provider-Credential CRUD."""

    def test_create_credential(self, client):
        """Credential erstellen."""
        response = client.post(
            "/api/provider-credentials",
            json={
                "provider": "deepseek",
                "model": "deepseek-4-pro",
                "label": "DeepSeek 4 Pro",
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com/v1",
                "is_active": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek-4-pro"
        assert data["label"] == "DeepSeek 4 Pro"
        assert data["api_key"] == "sk-test"
        assert data["base_url"] == "https://api.deepseek.com/v1"
        assert data["is_active"] is True
        assert "id" in data

    def test_list_credentials(self, client):
        """Liste aller Credentials."""
        client.post(
            "/api/provider-credentials",
            json={
                "provider": "kimi",
                "model": "kimi-k2.7-code",
                "label": "Kimi K2.7",
                "api_key": "sk-kimi-test",
            },
        )
        response = client.get("/api/provider-credentials")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(item["provider"] == "kimi" for item in data["items"])

    def test_update_credential(self, client):
        """Credential aktualisieren."""
        response = client.post(
            "/api/provider-credentials",
            json={
                "provider": "openai",
                "model": "gpt-4",
                "label": "OpenAI GPT-4",
            },
        )
        credential_id = response.json()["id"]

        response = client.put(
            f"/api/provider-credentials/{credential_id}",
            json={"model": "gpt-4o", "label": "OpenAI GPT-4o"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "gpt-4o"
        assert data["label"] == "OpenAI GPT-4o"

    def test_delete_credential(self, client):
        """Credential löschen."""
        response = client.post(
            "/api/provider-credentials",
            json={
                "provider": "ollama",
                "model": "gemma4:12b",
                "label": "Ollama Gemma",
            },
        )
        credential_id = response.json()["id"]

        response = client.delete(f"/api/provider-credentials/{credential_id}")
        assert response.status_code == 204

        response = client.get(f"/api/provider-credentials/{credential_id}")
        assert response.status_code == 404
