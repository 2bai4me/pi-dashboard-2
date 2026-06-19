"""ArchitectureRules Router — Standardvorgaben-Verwaltung (Schritt 0)."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.base import get_db
from ..auth import require_auth
from ..models.architecture_rule import ArchitectureRule

router = APIRouter(prefix="/api/architecture-rules", tags=["architecture-rules"])


@router.get("")
async def list_rules(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle Standardvorgaben (filterbar nach category + severity)."""
    q = select(ArchitectureRule)
    if active_only:
        q = q.where(ArchitectureRule.is_active == True)  # noqa: E712
    if category:
        q = q.where(ArchitectureRule.category == category)
    if severity:
        q = q.where(ArchitectureRule.severity == severity)
    q = q.order_by(ArchitectureRule.category, ArchitectureRule.severity, ArchitectureRule.name)
    rules = list(db.execute(q).scalars())
    return {
        "items": [r.to_dict() for r in rules],
        "total": len(rules),
    }


@router.get("/{rule_id}")
async def get_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert eine einzelne Standardvorgabe."""
    r = db.get(ArchitectureRule, rule_id)
    if not r:
        raise HTTPException(404, "Architecture rule not found")
    return r.to_dict()


@router.get("/by-source/{source_ref}")
async def get_rules_by_source(
    source_ref: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert alle Regeln, die zu einer Quelle (z.B. OpenBrain-Tag) gehoeren."""
    q = select(ArchitectureRule).where(ArchitectureRule.source_ref == source_ref)
    rules = list(db.execute(q).scalars())
    return {"items": [r.to_dict() for r in rules], "total": len(rules)}
