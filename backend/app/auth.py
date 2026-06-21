"""Auth (Wrapper) — Nutzt den neuen Auth-Service aus services/micro/.

Dieser Wrapper stellt die alte auth.py-Schnittstelle bereit, 
damit bestehende Router ohne Änderungen funktionieren.
Die eigentliche Logik liegt im Auth-Service.

Migration: Ersetze in Routern:
  from ..auth import require_auth
  → from ..services.micro.auth_service import require_auth
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials

from .services.micro.auth_service import (
    require_auth as _require_auth,
    require_role as _require_role,
    create_token,
    verify_token,
    login,
)
from .config import settings


_security = HTTPBearer(auto_error=False)


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """Wrapper für auth_service.require_auth().
    
    Diese Funktion wird von bestehenden Routern importiert.
    Die Implementierung liegt im Auth-Service.
    """
    return await _require_auth(credentials)


async def require_role(
    min_role: str = "viewer",
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Wrapper für auth_service.require_role()."""
    return await _require_role(min_role, credentials)
