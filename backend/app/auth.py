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
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .services.micro.auth_service import (
    require_auth as _require_auth,
    require_role as _require_role_factory,
    create_token,
    verify_token,
    login,
)
from .config import settings


# Alias fuer Abwaertskompatibilitaet (Router + Tests verwenden create_access_token)
create_access_token = create_token


_security = HTTPBearer(auto_error=False)


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """Wrapper für auth_service.require_auth().
    
    Diese Funktion wird von bestehenden Routern importiert.
    Die Implementierung liegt im Auth-Service.
    """
    return await _require_auth(credentials)


def require_role(min_role: str = "viewer"):
    """Wrapper-Factory für auth_service.require_role()."""
    return _require_role_factory(min_role)


# Convenience-Dependencies für haefige Rollen
async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Shortcut für require_role('admin')."""
    return await _require_role_factory("admin")(credentials)


async def require_cio(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Shortcut für require_role('cio')."""
    return await _require_role_factory("cio")(credentials)


async def require_ceo(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Shortcut für require_role('ceo')."""
    return await _require_role_factory("ceo")(credentials)
