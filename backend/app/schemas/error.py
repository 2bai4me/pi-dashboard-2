"""Pydantic v2 Schema fuer einheitliche Error-Responses.

CLEANUP-AUDIT 23.06.2026: Stub (Original-Datei fehlt im Repository).
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Fehler-Typ (z.B. 'http_error', 'internal_error')")
    detail: str = Field(..., description="Menschen-lesbare Fehlermeldung")
    status_code: int = Field(..., description="HTTP-Statuscode")
    timestamp: Optional[str] = Field(None, description="ISO-Timestamp")

    @classmethod
    def from_exception(
        cls, error: str, detail: str, status_code: int, timestamp: Optional[str] = None,
    ) -> "ErrorResponse":
        return cls(
            error=error, detail=detail, status_code=status_code,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        )


__all__ = ["ErrorResponse"]
