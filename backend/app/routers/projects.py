"""Projects Router."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..auth import require_auth
from ..schemas.project import (
    ProjectRead, ProjectCreate, ProjectUpdate, ProjectList,
    ProjectModeUpdate, ProjectCategoryUpdate, CompletionReport,
)
from ..services.project_service import ProjectService
from ..services.role_service import RoleService
from .. import events as _events

router = APIRouter(prefix="/api/kanban/projects", tags=["projects"])


@router.get("", response_model=ProjectList)
async def list_projects(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    projects = ProjectService.list_projects(db)
    items = []
    for p in projects:
        stats = ProjectService.project_stats(db, p)
        items.append(ProjectRead(
            id=p.id, name=p.name, description=p.description,
            status=p.status, mode=p.mode, category=p.category,
            created_at=p.created_at, updated_at=p.updated_at,
            closed_at=p.closed_at, completion_report=p.completion_report,
            **stats,
        ))
    return ProjectList(items=items, total=len(items))


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    p = ProjectService.create_project(db, name=req.name, description=req.description,
                                       mode=req.mode, category=req.category)
    stats = ProjectService.project_stats(db, p)
    return ProjectRead(**{**{k: getattr(p, k) for k in
                              ["id", "name", "description", "status", "mode", "category",
                               "created_at", "updated_at", "closed_at", "completion_report"]},
                          **stats})


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    p = ProjectService.get_project(db, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    stats = ProjectService.project_stats(db, p)
    return ProjectRead(**{**{k: getattr(p, k) for k in
                              ["id", "name", "description", "status", "mode", "category",
                               "created_at", "updated_at", "closed_at", "completion_report"]},
                          **stats})


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    req: ProjectUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    p = ProjectService.update_project(db, project_id, **req.model_dump(exclude_unset=True))
    if not p:
        raise HTTPException(404, "Project not found")
    stats = ProjectService.project_stats(db, p)
    return ProjectRead(**{**{k: getattr(p, k) for k in
                              ["id", "name", "description", "status", "mode", "category",
                               "created_at", "updated_at", "closed_at", "completion_report"]},
                          **stats})


@router.put("/{project_id}/mode", response_model=ProjectRead)
async def set_project_mode(
    project_id: str,
    req: ProjectModeUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt Modus (preparation/execution/paused/completed).

    Bei mode=completed wird automatisch ein Abschlussbericht generiert.
    """
    p = ProjectService.set_mode(db, project_id, req.mode, note=req.note)
    if not p:
        raise HTTPException(404, "Project not found")
    await _events.publish_event(project_id, "project_mode_changed",
                                {"project_id": project_id, "new_mode": p.mode,
                                 "completion_report_generated": p.mode == "completed"})
    stats = ProjectService.project_stats(db, p)
    return ProjectRead(**{**{k: getattr(p, k) for k in
                              ["id", "name", "description", "status", "mode", "category",
                               "created_at", "updated_at", "closed_at", "completion_report"]},
                          **stats})


@router.put("/{project_id}/category", response_model=ProjectRead)
async def set_project_category(
    project_id: str,
    req: ProjectCategoryUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt ITIL-Klassifizierung (new_request/ticket/change)."""
    p = ProjectService.update_project(db, project_id, category=req.category)
    if not p:
        raise HTTPException(404, "Project not found")
    stats = ProjectService.project_stats(db, p)
    return ProjectRead(**{**{k: getattr(p, k) for k in
                              ["id", "name", "description", "status", "mode", "category",
                               "created_at", "updated_at", "closed_at", "completion_report"]},
                          **stats})


@router.get("/{project_id}/completion-report", response_model=dict)
async def get_completion_report(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert den gespeicherten Abschlussbericht."""
    p = ProjectService.get_project(db, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    if not p.completion_report:
        raise HTTPException(404, "Project has no completion report (still running?)")
    return {"project_id": p.id, "report": p.completion_report, "completed_at": p.closed_at}


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    ok = ProjectService.delete_project(db, project_id)
    if not ok:
        raise HTTPException(404, "Project not found")
