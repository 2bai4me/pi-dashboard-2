"""Auth (Stub fuer v2.0-beta)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import settings


_security = HTTPBearer(auto_error=False)


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """Stub-Auth: akzeptiert alles, gibt 'dev-user' zurueck (v2.0-beta)."""
    if not settings.AUTH_ENABLED:
        return "dev-user"
    # TODO: echte JWT-Validierung
    if not credentials or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    return credentials.credentials
