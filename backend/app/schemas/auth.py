"""Auth Schemas (Login + Token)."""
from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Login-Payload fuer /api/auth/login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT-Login-Response."""

    access_token: str
    token_type: str
