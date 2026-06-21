"""ProviderCredential Schemas — Pydantic v2."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProviderCredentialCreate(BaseModel):
    """POST /api/provider-credentials — Neue Credential anlegen."""

    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=255)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: bool = True
    input_cost_per_1m: Optional[Decimal] = None
    output_cost_per_1m: Optional[Decimal] = None


class ProviderCredentialUpdate(BaseModel):
    """PUT /api/provider-credentials/{id} — Credential aktualisieren."""

    provider: Optional[str] = Field(None, min_length=1, max_length=64)
    model: Optional[str] = Field(None, min_length=1, max_length=128)
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    input_cost_per_1m: Optional[Decimal] = None
    output_cost_per_1m: Optional[Decimal] = None


class ProviderCredentialRead(BaseModel):
    """Response: Eine Credential."""

    id: str
    provider: str
    model: str
    label: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: bool
    input_cost_per_1m: Optional[Decimal] = None
    output_cost_per_1m: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderCredentialListResponse(BaseModel):
    """Liste von Provider-Credentials."""

    items: list[ProviderCredentialRead]
    total: int
