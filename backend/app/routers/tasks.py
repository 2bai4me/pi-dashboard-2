"""Tasks Router — komplett sauber (v2.0-rc)."""
from __future__ import annotations

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.base import get_db
from ..auth import require_auth
from ..schemas.task import (
    TaskRead, TaskCreate, TaskUpdate, TaskList, TaskStats,
    TaskStatusUpdate, TaskPriorityUpdate, TaskDispatchUpdate, TaskTokenReport,
    TaskHistoryEntry, TaskWithStats,
    SubTaskCreate, SubTaskCreateList,
)
from ..services.task_service import TaskService
from ..models.task import Task
from .. import events as _events

router = APIRouter(prefix="/api/kanban/tasks", tags=["tasks"])


@router.get("", response_model=TaskList)
async def list_tasks(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    tasks = TaskService.list_tasks(db, project_id=project_id, status=status)
    paginated = tasks[offset:offset + limit]
    return TaskList(
        items=[TaskRead.model_validate(t) for t in paginated],
        total=len(tasks),
        limit=limit,
        offset=offset,
    )


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
    await _events.publish_event(t.project_id or "", "task_created",
                                {"task_id": t.id, "title": t.title, "status": t.status})
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
    t = TaskService.set_status(db, task_id, req.status)
    if not t:
        raise HTTPException(404, "Task not found")
    await _events.publish_event(t.project_id or "", "task_status_changed",
                                {"task_id": t.id, "new_status": t.status, "priority": t.priority})
    return TaskRead.model_validate(t)


@router.put("/{task_id}/priority", response_model=TaskRead)
async def set_task_priority(
    task_id: str,
    req: TaskPriorityUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    t = TaskService.set_priority(db, task_id, req.priority)
    if not t:
        raise HTTPException(404, "Task not found")
    await _events.publish_event(t.project_id or "", "task_priority_changed",
                                {"task_id": t.id, "new_priority": t.priority, "emergency": t.emergency})
    return TaskRead.model_validate(t)


@router.patch("/{task_id}/dispatch", response_model=dict)
async def report_dispatch(
    task_id: str,
    req: TaskDispatchUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
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
    result = TaskService.report_usage(
        db, task_id, tokens_in=req.tokens_in, tokens_out=req.tokens_out,
        model=req.model, role=req.role, note=req.note,
    )
    if not result:
        raise HTTPException(404, "Task not found")
    if result.get("task_id"):
        t = TaskService.get_task(db, result["task_id"])
        if t:
            await _events.publish_event(t.project_id or "", "task_usage_reported",
                                        {"task_id": t.id, "cost_usd": result.get("cost_usd"),
                                         "tokens_in": result.get("tokens_in"),
                                         "tokens_out": result.get("tokens_out")})
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
    history = list(db.execute(
        select(TaskHistory).where(TaskHistory.task_id == task_id)
        .order_by(TaskHistory.ts.desc()).limit(limit)
    ).scalars())
    return {
        "task_id": task_id,
        "history": [TaskHistoryEntry.model_validate(h) for h in history],
        "stats": TaskService.task_stats(db, task_id),
    }


@router.post("/{task_id}/subtasks", response_model=List[TaskRead], status_code=201)
async def create_subtasks(
    task_id: str,
    req: SubTaskCreateList = Body(...),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Erstellt Sub-Tasks fuer eine Parent-Task."""
    parent = TaskService.get_task(db, task_id)
    if not parent:
        raise HTTPException(404, "Parent-Task nicht gefunden")
    created = []
    for st in req.subtasks:
        sub = TaskService.create_task(
            db, title=st.title, project_id=parent.project_id,
            description=st.description, priority=st.priority, category=st.category,
            parent_id=task_id, assigned_role=st.assigned_role,
        )
        created.append(sub)
    db.commit()
    return [TaskRead.model_validate(s) for s in created]


@router.post("/{task_id}/aggregate", response_model=TaskRead)
async def aggregate_subtasks(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aggregiert Sub-Task-Status zum Parent."""
    parent = TaskService.get_task(db, task_id)
    if not parent:
        raise HTTPException(404, "Parent-Task nicht gefunden")
    subs = list(db.execute(select(Task).where(Task.parent_id == task_id)).scalars())
    if not subs:
        raise HTTPException(400, "Task hat keine Sub-Tasks")
    statuses = [s.status for s in subs]
    if all(s == "done" for s in statuses):
        new_status = "done"
    elif any(s == "block" for s in statuses):
        new_status = "block"
    elif any(s == "in_progress" for s in statuses):
        new_status = "in_progress"
    elif all(s == "review" for s in statuses):
        new_status = "review"
    else:
        return TaskRead.model_validate(parent)
    parent.status = new_status
    parent.updated_at = datetime.utcnow()
    TaskService._add_history(db, parent, "subtasks_aggregated", agent="system",
                             details={"new_status": new_status, "sub_count": len(subs)})
    db.commit()
    db.refresh(parent)
    return TaskRead.model_validate(parent)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    ok = TaskService.delete_task(db, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
