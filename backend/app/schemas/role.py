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
    emoji: Optional[str] = None
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
    emoji: Optional[str] = None
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
    """Liste von Rollen (alle Typen)."""
    items: List[RoleRead]
    total: int


class OrgRoleList(BaseModel):
    """Liste von Org-Rollen (CEO-digital, CIO, CMO, CFO)."""
    items: List[RoleRead]
    total: int


class SubAgentList(BaseModel):
    """Liste von Sub-Agents (pi-coder, pi-tester, pi-reviewer, pi-fixer)."""
    items: List[RoleRead]
    total: int
