"""Auth Router: Login + JWT-Ausgabe."""
from __future__ import annotations

import bcrypt
from fastapi import APIRouter, HTTPException, status

from ..auth import create_access_token
from ..config import settings
from ..schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _verify_password(plain: str, hashed: str) -> bool:
    """Prueft ein Passwort gegen einen bcrypt-Hash.

    Unterstuetzt waehrend der Uebergangsphase auch Klartext-Passwoerter,
    solange ADMIN_PASSWORD noch nicht gehasht wurde (es wird dann eine
    Warnung in config.py geloggt).
    """
    if not hashed.startswith("$"):
        return plain == hashed
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Authentifiziert den Admin-User und liefert einen JWT."""
    if req.username != settings.ADMIN_USER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not _verify_password(req.password, settings.ADMIN_PASSWORD):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(
        username=settings.ADMIN_USER,
        role="admin",
    )
    return TokenResponse(access_token=token, token_type="bearer")
