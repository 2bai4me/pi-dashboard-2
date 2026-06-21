"""Tests fuer JWT-Authentifizierung."""
from __future__ import annotations

import os

# Test-Env MUSS vor dem Import von app-Modulen gesetzt werden,
# da config.py settings beim Laden instanziiert.
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import create_access_token, require_auth
from app.config import settings
from app.routers import auth as auth_router


app = FastAPI()
app.include_router(auth_router.router)


@app.get("/protected")
def protected_endpoint(user: str = Depends(require_auth)):
    return {"user": user}


client = TestClient(app)


def test_login_success_returns_jwt():
    response = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USER, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Token muss den geschuetzten Endpunkt freigeben
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    protected = client.get("/protected", headers=headers)
    assert protected.status_code == 200
    assert protected.json()["user"] == settings.ADMIN_USER


def test_login_invalid_credentials_returns_401():
    response = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USER, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_protected_endpoint_without_token_returns_401():
    response = client.get("/protected")
    assert response.status_code == 401


def test_token_payload_contains_role():
    token = create_access_token(username="admin", role="admin")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/protected", headers=headers)
    assert response.status_code == 200
