"""Tasks Router."""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..auth import require_auth
from ..schemas.task import (
    TaskRead, TaskCreate, TaskUpdate, TaskList, TaskStats,
    TaskStatusUpdate, TaskPriorityUpdate, TaskDispatchUpdate, TaskTokenReport,
    TaskHistoryEntry, TaskWithStats,
)
from ..services.task_service import TaskService

router = APIRouter(prefix="/api/kanban/tasks", tags=["tasks"])


@router.get("", response_model=TaskList)
async def list_tasks(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    tasks = TaskService.list_tasks(db, project_id=project_id, status=status)
    return TaskList(items=[TaskRead.model_validate(t) for t in tasks], total=len(tasks))


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    req: TaskCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.create_task(
        db, title=req.title, project_id=req.project_id, description=req.description,
        status=req.status, priority=req.priority, category=req.category,
        parent_id=req.parent_id, assigned_role=req.assigned_role,
    )
    return TaskRead.model_validate(t)


@router.get("/{task_id}", response_model=TaskWithStats)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.get_task(db, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    stats = TaskService.task_stats(db, task_id)
    return TaskWithStats(
        **TaskRead.model_validate(t).model_dump(),
        stats=TaskStats(**stats),
    )


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    req: TaskUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.update_task(db, task_id, **req.model_dump(exclude_unset=True))
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.put("/{task_id}/status", response_model=TaskRead)
async def set_task_status(
    task_id: str,
    req: TaskStatusUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt Status. Bei 'todo' wird auto_claim + Pricing-Snapshot ausgeloest."""
    t = TaskService.set_status(db, task_id, req.status)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.put("/{task_id}/priority", response_model=TaskRead)
async def set_task_priority(
    task_id: str,
    req: TaskPriorityUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt Prio (Notfall-Watchdog bei >=90)."""
    t = TaskService.set_priority(db, task_id, req.priority)
    if not t:
        raise HTTPException(404, "Task not found")
    return TaskRead.model_validate(t)


@router.patch("/{task_id}/dispatch", response_model=dict)
async def report_dispatch(
    task_id: str,
    req: TaskDispatchUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Sub-Agent meldet Dispatch-Status zurueck (vom swarm-spawner aufgerufen)."""
    result = TaskService.report_dispatch(
        db, task_id, role=req.role or "subagent", status=req.status or "dispatched",
        model=req.model or "minimax/minimax-m3",
        agent_pid=req.agent_pid, reason=req.reason,
        tokens_in=req.tokens_in, tokens_out=req.tokens_out,
    )
    if not result:
        raise HTTPException(404, "Task not found")
    return result


@router.post("/{task_id}/usage", response_model=dict)
async def report_usage(
    task_id: str,
    req: TaskTokenReport,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Sub-Agent meldet kumulierte Token-Counts (fuer Pricing-Snapshot-Berechnung)."""
    result = TaskService.report_usage(
        db, task_id, tokens_in=req.tokens_in, tokens_out=req.tokens_out,
        model=req.model, role=req.role, note=req.note,
    )
    if not result:
        raise HTTPException(404, "Task not found")
    return result


@router.get("/{task_id}/stats", response_model=TaskStats)
async def get_task_stats(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    stats = TaskService.task_stats(db, task_id)
    if not stats:
        raise HTTPException(404, "Task not found")
    return TaskStats(**stats)


@router.get("/{task_id}/history", response_model=dict)
async def get_task_history(
    task_id: str,
    limit: int = Query(100),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    from ..models.history import TaskHistory
    from sqlalchemy import select
    history = list(db.execute(
        select(TaskHistory).where(TaskHistory.task_id == task_id)
        .order_by(TaskHistory.ts.desc()).limit(limit)
    ).scalars())
    return {
        "task_id": task_id,
        "history": [TaskHistoryEntry.model_validate(h) for h in history],
        "stats": TaskService.task_stats(db, task_id),
    }


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    ok = TaskService.delete_task(db, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
