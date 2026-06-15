"""Role Schemas — Pydantic v2."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    role_type: str = "sub_agent"  # sub_agent | org
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    tool_whitelist: List[str] = Field(default_factory=list)
    timeout_sec: int = 300
    fresh_context: bool = True
    estimated_savings_usd: Decimal = Decimal("0")


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    description: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    tool_whitelist: Optional[List[str]] = None
    timeout_sec: Optional[int] = None
    fresh_context: Optional[bool] = None
    estimated_savings_usd: Optional[Decimal] = None


class RoleRead(RoleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleList(BaseModel):
    items: List[RoleRead]
    total: int
