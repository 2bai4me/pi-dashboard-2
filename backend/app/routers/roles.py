"""Roles Router (Sub-Agents + Org-Rollen)."""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..auth import require_auth
from ..schemas.role import (
    RoleRead, RoleCreate, RoleUpdate, RoleList, OrgRoleList, SubAgentList,
)
from ..services.role_service import RoleService

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("", response_model=RoleList)
async def list_roles(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Alle Rollen (Sub-Agents + Org-Rollen, sortiert nach role_type, name)."""
    # Ensure defaults are seeded
    RoleService.seed_defaults(db)
    roles = RoleService.list_roles(db)
    return RoleList(items=[RoleRead.model_validate(r) for r in roles], total=len(roles))


@router.get("/sub-agents", response_model=SubAgentList)
async def list_sub_agents(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Nur Sub-Agents (pi-coder, pi-tester, pi-reviewer, pi-fixer).

    Werden als swarm-spawner-Subprozesse gestartet.
    """
    RoleService.seed_defaults(db)
    roles = RoleService.list_sub_agents(db)
    return SubAgentList(items=[RoleRead.model_validate(r) for r in roles], total=len(roles))


@router.get("/org", response_model=OrgRoleList)
async def list_org_roles(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Organisationale Rollen (CEO-digital, CIO, CMO, CFO).

    Strategische Perspektiven, laufen typisch mit ollama/gemma4:12b (lokal + kostenfrei).
    """
    RoleService.seed_defaults(db)
    roles = RoleService.list_org_roles(db)
    return OrgRoleList(items=[RoleRead.model_validate(r) for r in roles], total=len(roles))


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    r = RoleService.get_role(db, role_id)
    if not r:
        raise HTTPException(404, "Role not found")
    return RoleRead.model_validate(r)


@router.post("", response_model=RoleRead, status_code=201)
async def create_role(
    req: RoleCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    r = RoleService.create_role(db, name=req.name, **req.model_dump(exclude={"name"}))
    return RoleRead.model_validate(r)


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: str,
    req: RoleUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    r = RoleService.update_role(db, role_id, **req.model_dump(exclude_unset=True))
    if not r:
        raise HTTPException(404, "Role not found")
    return RoleRead.model_validate(r)
