"""TaskDraft Router — Iterativer Task-Refinement-Workflow (User-Direktive 18.06.2026).

Endpoints:
  POST   /api/task-drafts                       — Neuen Entwurf erstellen (User-Beschreibung -> KI)
  GET    /api/task-drafts/{id}                  — Aktuellen Entwurf laden
  POST   /api/task-drafts/{id}/refine           — Verfeinern mit User-Feedback
  POST   /api/task-drafts/{id}/publish          — Entwurf als echten Task freigeben
  DELETE /api/task-drafts/{id}                  — Entwurf verwerfen
  GET    /api/task-drafts                        — Liste aller Entwuerfe (User-facing)
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.base import get_db
from ..auth import require_auth
from ..models.task_draft import TaskDraft
from ..services.task_draft_service import TaskDraftService
from ..services.task_service import TaskService

logger = logging.getLogger("pi-dashboard-2.task-draft-router")
router = APIRouter(prefix="/api/task-drafts", tags=["task-drafts"])


# === Pydantic-Schemas ===

class CreateDraftBody(BaseModel):
    user_input: str = Field(..., min_length=3, max_length=2000, description="Initiale User-Beschreibung")
    project_id: Optional[str] = None


class RefineDraftBody(BaseModel):
    user_feedback: str = Field(..., min_length=1, max_length=2000, description="User-Feedback zur Verfeinerung")


class UpdateDraftBody(BaseModel):
    """Direktes Update der current-Felder (ohne KI-Aufruf)."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    category: Optional[str] = None
    success_criteria: Optional[List[str]] = None
    assigned_role: Optional[str] = None
    project_id: Optional[str] = None
    tags: Optional[List[str]] = None


class DraftRead(BaseModel):
    id: str
    user_input: str
    current: dict
    iterations: list
    status: str
    final_task_id: Optional[str] = None
    iteration_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DraftListRead(BaseModel):
    items: List[DraftRead]
    total: int


class PublishResponse(BaseModel):
    ok: bool
    task_id: str
    draft_id: str


# === Endpoints ===

@router.post("", response_model=DraftRead, status_code=201)
async def create_draft(
    body: CreateDraftBody,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Erstellt einen neuen Task-Entwurf.

    User-Beschreibung wird an die KI gegeben, die einen vollstaendigen
    Task-Entwurf generiert (title, description, success_criteria, priority, ...).
    """
    draft = TaskDraftService.create_draft(db, body.user_input, body.project_id)
    return draft.to_dict()


@router.get("", response_model=DraftListRead)
async def list_drafts(
    status: Optional[str] = Query(None, description="Filter: draft, published, abandoned"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle Task-Entwuerfe."""
    stmt = select(TaskDraft).order_by(TaskDraft.updated_at.desc())
    if status:
        stmt = stmt.where(TaskDraft.status == status)
    drafts = list(db.execute(stmt.limit(limit)).scalars())
    return {
        "items": [d.to_dict() for d in drafts],
        "total": len(drafts),
    }


@router.get("/{draft_id}", response_model=DraftRead)
async def get_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Laedt einen einzelnen Entwurf."""
    draft = db.get(TaskDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Draft {draft_id} nicht gefunden")
    return draft.to_dict()


@router.patch("/{draft_id}", response_model=DraftRead)
async def update_draft(
    draft_id: str,
    body: UpdateDraftBody,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Direktes Update des Entwurfs (ohne KI-Aufruf).

    Fuer User-Edits: title, description, success_criteria, priority, etc.
    """
    draft = db.get(TaskDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Draft {draft_id} nicht gefunden")
    if draft.status != "draft":
        raise HTTPException(400, f"Draft ist bereits {draft.status}, kann nicht mehr editiert werden")
    from datetime import datetime, timezone
    new_current = dict(draft.current or {})
    # Nur Felder aktualisieren, die im Body gesetzt sind
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            new_current[key] = value
    draft.current = new_current
    draft.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(draft)
    return draft.to_dict()


@router.post("/{draft_id}/refine", response_model=DraftRead)
async def refine_draft(
    draft_id: str,
    body: RefineDraftBody,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Verfeinert den Entwurf basierend auf User-Feedback.

    Die KI analysiert den aktuellen Entwurf + User-Feedback und generiert
    eine verfeinerte Version. Kann mehrfach aufgerufen werden.
    """
    try:
        draft = TaskDraftService.refine_draft(db, draft_id, body.user_feedback)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return draft.to_dict()


@router.post("/{draft_id}/publish", response_model=PublishResponse)
async def publish_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Erstellt einen echten Task aus dem Entwurf (status=triage).

    Setzt draft.status = 'published' und final_task_id = task.id.
    """
    draft = db.get(TaskDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Draft {draft_id} nicht gefunden")
    if draft.status != "draft":
        raise HTTPException(400, f"Draft ist bereits {draft.status} (final_task_id={draft.final_task_id})")

    cur = draft.current or {}
    # Echte Task erstellen
    t = TaskService.create_task(
        db,
        title=cur.get("title", "Unbenannter Task"),
        project_id=cur.get("project_id"),
        description=cur.get("description", ""),
        status="triage",
        priority=cur.get("priority", 50),
        category=cur.get("category", "new_request"),
        assigned_role=cur.get("assigned_role"),
        success_criteria=cur.get("success_criteria", []),
    )
    # Tags setzen (separat, weil create_task keine tags hat)
    if cur.get("tags"):
        t.tags = cur["tags"]
        db.commit()
        db.refresh(t)

    # Pricing-Snapshot
    try:
        take_pricing_snapshot(t, db=db)
    except Exception:
        pass

    # Draft als published markieren
    draft.status = "published"
    draft.final_task_id = t.id
    from datetime import datetime, timezone
    draft.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"ok": True, "task_id": t.id, "draft_id": draft.id}


@router.delete("/{draft_id}", status_code=204)
async def abandon_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Verwirft einen Entwurf (status=abandoned)."""
    draft = db.get(TaskDraft, draft_id)
    if not draft:
        raise HTTPException(404, f"Draft {draft_id} nicht gefunden")
    if draft.status == "published":
        raise HTTPException(400, f"Published Drafts koennen nicht verworfen werden")
    from datetime import datetime, timezone
    draft.status = "abandoned"
    draft.updated_at = datetime.now(timezone.utc)
    db.commit()
    return None
