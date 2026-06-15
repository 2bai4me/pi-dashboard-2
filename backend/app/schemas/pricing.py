"""Pricing Schemas — Pydantic v2."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ModelPricingRead(BaseModel):
    id: int
    provider: str
    model_id: str
    input_per_1m: Decimal
    output_per_1m: Decimal
    currency: str = "USD"
    source: Optional[str] = None
    last_updated: datetime
    note: Optional[str] = None
    is_default: bool = False

    model_config = ConfigDict(from_attributes=True)


class PricingUpdateRequest(BaseModel):
    """POST /api/models/pricing/update — Manuelles Override."""
    provider: str
    model_id: Optional[str] = None
    input_per_1m: Decimal
    output_per_1m: Decimal
    note: Optional[str] = None


class PricingRefreshResult(BaseModel):
    """POST /api/models/pricing/refresh — Ergebnis."""
    ok: bool
    updated_count: int
    skipped_count: int
    updated: List[Dict[str, Any]]
    skipped: List[Dict[str, Any]]
    refreshed_at: datetime


class ModelInfo(BaseModel):
    """Provider/Model-Info (aus models.json)."""
    id: str
    provider: str
    full_id: str
    input_per_1m: Optional[Decimal] = None
    output_per_1m: Optional[Decimal] = None
    price_source: Optional[str] = None
    price_last_updated: Optional[datetime] = None
    context_window: Optional[int] = None
    reasoning: Optional[bool] = None
    enabled: bool = False
    is_default: bool = False


class ProviderInfo(BaseModel):
    name: str
    api: Optional[str] = None
    base_url: Optional[str] = None
    model_count: int = 0
    has_key: bool = False
    has_pricing: bool = False
