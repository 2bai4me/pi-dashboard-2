"""Auth-Service — JWT-Authentifizierung und Autorisierung.

Verwendet:
  - python-jose fuer Token-Erstellung/Validierung
  - bcrypt fuer Passwort-Hashing

Architektur:
  POST /api/auth/login        → Username/Password → JWT-Token
  GET  /api/auth/verify       → Validiert Token → User-Info
  POST /api/auth/refresh      → Erneuert Token (bei gültigem Alt-Token)

Token-Format (JWT):
  {
    "sub": "admin",           # Username
    "role": "admin",          # Rolle
    "iat": 1712345678,        # Issued-At (UTC-Timestamp)
    "exp": 1712432078,        # Expiry (UTC-Timestamp, 24h nach iat)
    "jti": "uuid",            # JWT-ID (für Token-Revocation)
  }

Rollen:
  - "admin"    → Vollzugriff (Tasks, SOPs, Config, Backup/Restore)
  - "cio"      → Task-Review, Projekt-Verwaltung, KEINE Config
  - "ceo"      → Fragen beantworten, KEINE Tasks/SOPs verwalten
  - "viewer"   → Nur Lesen (Dashboard, Status)

Environment-Variablen:
  AUTH_ENABLED=true           # Pflicht für Production
  JWT_SECRET=<32-Byte-Base64> # Pflicht, sonst Start-Fehler
  JWT_TTL_HOURS=24            # Optional, Default 24
  ADMIN_USER=admin            # Optional, Default "admin"
  ADMIN_PASSWORD=<hash>       # Wird bei erstem Start gehasht

Wichtige Änderung (v2.0-rc):
  - AUTH_ENABLED ist jetzt default TRUE
  - Ohne JWT_SECRET startet die App nicht
  - Token-Validierung in require_auth() ist echt (kein Stub mehr)
  - Login-Endpoint mit bcrypt-Passwort-Prüfung
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from jose import jwt, JWTError, ExpiredSignatureError

from ...config import settings
from ...utils.exceptions import (
    InvalidTokenError, TokenExpiredError,
    InsufficientPermissionsError, AuthError,
)

logger = logging.getLogger("pi-dashboard-2.auth")

# Security-Schema für Swagger UI
_security = HTTPBearer(auto_error=False)


def _get_jwt_secret() -> str:
    """Lazy-Initialisierung des JWT-Secrets.

    Stellt sicher, dass JWT_SECRET gesetzt ist und ein gültiger Key vorliegt.
    """
    secret = os.getenv("JWT_SECRET") or settings.JWT_SECRET
    if not secret or secret in {
        "",
        "__CHANGE_ME__",
        "change-me-to-a-random-32-byte-base64-secret",
    }:
        raise RuntimeError(
            "JWT_SECRET nicht oder unsicher gesetzt! "
            "Setze JWT_SECRET auf einen zufälligen 32-Byte-String (base64-kodiert).\n"
            "Beispiel (PowerShell):\n"
            "  $bytes = [byte[]]::new(32); [Security.Cryptography.RandomNumberGenerator]::GetBytes($bytes)\n"
            "  $env:JWT_SECRET = [Convert]::ToBase64String($bytes)"
        )
    return secret


def create_token(
    username: str,
    role: str = "admin",
    ttl_hours: int = 24,
) -> str:
    """Erstellt einen JWT-Token für einen authentifizierten User.

    Args:
        username: Der Username (z.B. "admin")
        role: Die Rolle des Users (z.B. "admin", "cio", "ceo", "viewer")
        ttl_hours: Gültigkeitsdauer in Stunden

    Returns:
        JWT-Token als String

    Raises:
        RuntimeError: Wenn JWT_SECRET nicht gesetzt ist
    """
    secret = _get_jwt_secret()
    now = datetime.now(timezone.utc)

    claims = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
        "jti": str(uuid.uuid4()),
    }

    token = jwt.encode(claims, secret, algorithm=settings.JWT_ALGORITHM)
    logger.info(f"Token erstellt für user={username} role={role} exp={ttl_hours}h")
    return token


def verify_token(token: str) -> Dict[str, Any]:
    """Validiert einen JWT-Token und gibt die Claims zurück.

    Args:
        token: Der JWT-Token-String

    Returns:
        Dict mit den Token-Claims (sub, role, iat, exp, jti)

    Raises:
        InvalidTokenError: Wenn der Token ungültig oder abgelaufen ist
    """
    secret = _get_jwt_secret()
    try:
        claims = jwt.decode(
            token, secret, algorithms=[settings.JWT_ALGORITHM]
        )
        return {
            "sub": claims.get("sub", "unknown"),
            "role": claims.get("role", "viewer"),
            "iat": claims.get("iat"),
            "exp": claims.get("exp"),
            "jti": claims.get("jti"),
        }
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except JWTError as e:
        raise InvalidTokenError(f"Token validation failed: {e}")


# === Rollen-Hierarchie (für require_role) ===
_ROLE_HIERARCHY = {
    "admin": 100,
    "cio": 80,
    "ceo": 60,
    "developer": 40,
    "viewer": 10,
}


def _role_level(role: str) -> int:
    """Gibt die Berechtigungsstufe einer Rolle zurück."""
    return _ROLE_HIERARCHY.get(role, 0)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """FastAPI-Dependency: Validiert JWT und gibt Username zurück.

    Diese Dependency wird von allen geschützten Endpoints verwendet.

    Args:
        credentials: Der Authorization-Header (Bearer Token)

    Returns:
        Username (sub aus Token)

    Raises:
        401 Unauthorized: Wenn kein Token oder ungültiger Token
    """
    if not settings.AUTH_ENABLED:
        # Entwicklungsmodus: Jeder Request ist erlaubt
        return "dev-user"

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = verify_token(credentials.credentials)
        return claims.get("sub", "unknown")
    except (InvalidTokenError, TokenExpiredError) as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(min_role: str = "viewer"):
    """FastAPI-Dependency-Factory: Validiert Token + Rolle.

    Verwendung in Routern:
        @router.get("/api/admin-only")
        async def admin_endpoint(
            _user: str = Depends(require_role("admin")),
        ):
            ...

    Args:
        min_role: Die minimal benötigte Rolle

    Returns:
        Async Dependency, die den Username zurückgibt.

    Raises:
        401/403: Wenn nicht authentifiziert oder autorisiert
    """
    async def _require_role_dependency(
        credentials: HTTPAuthorizationCredentials = Depends(_security),
    ) -> str:
        if not settings.AUTH_ENABLED:
            return "dev-user"

        username = await require_auth(credentials)
        claims = verify_token(credentials.credentials)

        user_role = claims.get("role", "viewer")
        if _role_level(user_role) < _role_level(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {min_role}, got: {user_role}",
            )

        return username

    return _require_role_dependency


async def login(username: str, password: str) -> Dict[str, Any]:
    """Authentifiziert einen User und gibt einen JWT-Token zurück.

    Args:
        username: Der Username
        password: Das Passwort

    Returns:
        Dict mit token, username, role, expires_in

    Raises:
        AuthError: Bei falschen Anmeldedaten
    """
    import bcrypt

    # Admin-Credentials aus Settings
    admin_user = settings.ADMIN_USER
    admin_password = settings.ADMIN_PASSWORD

    if username != admin_user:
        raise AuthError("Invalid username or password")

    # Unterstuetze bcrypt-Hashes und Klartext-Passwoerter in der Uebergangsphase
    if admin_password.startswith(("$2a$", "$2b$", "$2y$")):
        if not bcrypt.checkpw(password.encode(), admin_password.encode()):
            raise AuthError("Invalid username or password")
    else:
        if password != admin_password:
            raise AuthError("Invalid username or password")

    ttl_hours = settings.JWT_TTL_HOURS or 24
    token = create_token(username, role="admin", ttl_hours=ttl_hours)

    return {
        "token": token,
        "username": username,
        "role": "admin",
        "expires_in": ttl_hours * 3600,
    }
