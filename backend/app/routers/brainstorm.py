"""Brainstorming + Requirements + Review-Pipeline + Implementation-Plan Router."""
from __future__ import annotations

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..db.base import get_db
from ..auth import require_auth
from ..models import BrainstormEntry, RequirementDoc, ReviewPipeline, ImplementationStep
from ..models.task import Task

router = APIRouter(prefix="/api", tags=["brainstorm"])


# === Brainstorming ===
class BrainstormCreate(BaseModel):
    role: str = Field("user", pattern="^(user|assistant)$")
    text: str = Field(..., min_length=1)
    phase: str = "input"


@router.get("/kanban/projects/{project_id}/brainstorm", response_model=List[dict])
async def list_brainstorm(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle Brainstorming-Eintraege eines Projekts."""
    rows = db.execute(
        select(BrainstormEntry).where(BrainstormEntry.project_id == project_id)
        .order_by(BrainstormEntry.ts)
    ).scalars()
    return [{"id": r.id, "role": r.role, "text": r.text, "phase": r.phase, "ts": r.ts.isoformat()} for r in rows]


@router.post("/kanban/projects/{project_id}/brainstorm", response_model=dict, status_code=201)
async def add_brainstorm(
    project_id: str,
    req: BrainstormCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    entry = BrainstormEntry(project_id=project_id, role=req.role, text=req.text, phase=req.phase)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "role": entry.role, "text": entry.text, "phase": entry.phase, "ts": entry.ts.isoformat()}


# === Requirements ===
class RequirementDocCreate(BaseModel):
    markdown: str = Field(..., min_length=10)
    version: int = 1


@router.get("/kanban/projects/{project_id}/requirements", response_model=List[dict])
async def list_requirements(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    rows = db.execute(
        select(RequirementDoc).where(RequirementDoc.project_id == project_id)
        .order_by(RequirementDoc.version.desc())
    ).scalars()
    return [
        {
            "id": r.id, "version": r.version, "status": r.status, "markdown": r.markdown,
            "review_score": r.review_score, "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        } for r in rows
    ]


@router.post("/kanban/projects/{project_id}/requirements", response_model=dict, status_code=201)
async def create_requirement(
    project_id: str,
    req: RequirementDocCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    doc = RequirementDoc(
        project_id=project_id, version=req.version, status="draft", markdown=req.markdown,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {
        "id": doc.id, "version": doc.version, "status": doc.status, "markdown": doc.markdown,
        "review_score": doc.review_score, "created_at": doc.created_at.isoformat(),
    }


@router.put("/kanban/requirements/{doc_id}", response_model=dict)
async def update_requirement(
    doc_id: int,
    req: RequirementDocCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    doc = db.get(RequirementDoc, doc_id)
    if not doc:
        raise HTTPException(404, "Doc not found")
    doc.markdown = req.markdown
    doc.version = req.version
    doc.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "version": doc.version, "status": doc.status, "markdown": doc.markdown}


# === Review-Pipeline ===
class ReviewStepCreate(BaseModel):
    step_name: str = Field(..., min_length=1)
    step_index: int = Field(..., ge=0, le=8)
    result: Optional[str] = None
    status: str = "pending"


@router.get("/kanban/projects/{project_id}/review-pipeline", response_model=List[dict])
async def list_review_pipeline(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    rows = db.execute(
        select(ReviewPipeline).where(ReviewPipeline.project_id == project_id)
        .order_by(ReviewPipeline.step_index)
    ).scalars()
    return [
        {
            "id": r.id, "step_name": r.step_name, "step_index": r.step_index,
            "status": r.status, "result": r.result, "started_at": r.started_at,
            "completed_at": r.completed_at,
        } for r in rows
    ]


@router.post("/kanban/projects/{project_id}/review-pipeline", response_model=dict, status_code=201)
async def add_review_step(
    project_id: str,
    req: ReviewStepCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    step = ReviewPipeline(
        project_id=project_id, step_name=req.step_name, step_index=req.step_index,
        status=req.status, result=req.result,
        started_at=datetime.utcnow() if req.status == "running" else None,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return {"id": step.id, "step_name": step.step_name, "step_index": step.step_index, "status": step.status}


# === Implementation-Steps ===
class ImplStepCreate(BaseModel):
    phase: int = Field(..., ge=1, le=3)
    step_index: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    description: Optional[str] = None


@router.get("/kanban/projects/{project_id}/implementation", response_model=List[dict])
async def list_impl_steps(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    rows = db.execute(
        select(ImplementationStep).where(ImplementationStep.project_id == project_id)
        .order_by(ImplementationStep.phase, ImplementationStep.step_index)
    ).scalars()
    return [
        {
            "id": r.id, "phase": r.phase, "step_index": r.step_index, "title": r.title,
            "description": r.description, "status": r.status, "cio_approved": r.cio_approved,
            "completed_at": r.completed_at,
        } for r in rows
    ]


@router.post("/kanban/projects/{project_id}/implementation", response_model=dict, status_code=201)
async def add_impl_step(
    project_id: str,
    req: ImplStepCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    step = ImplementationStep(
        project_id=project_id, phase=req.phase, step_index=req.step_index,
        title=req.title, description=req.description, status="pending",
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return {"id": step.id, "phase": step.phase, "step_index": step.step_index, "title": step.title, "status": step.status}


@router.put("/kanban/implementation/{step_id}/complete", response_model=dict)
async def complete_impl_step(
    step_id: int,
    cio_approved: bool = False,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    step = db.get(ImplementationStep, step_id)
    if not step:
        raise HTTPException(404, "Step not found")
    step.status = "done"
    step.cio_approved = cio_approved
    step.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(step)
    return {"id": step.id, "status": step.status, "cio_approved": step.cio_approved}
