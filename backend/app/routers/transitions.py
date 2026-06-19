"""Performance-Router — Task-Transition-Endpoints (zentrale Performance-Tabelle).

User-Direktive 15.06.2026:
  - JEDER Status-Wechsel eines JEDEN Tasks wird in task_transitions
    dokumentiert (Projekt-ID, Timestamps, from/to, Delay).
  - 5-Sekunden-Verzoegerung zwischen Status-Wechsel und Weiterverarbeitung,
    damit der User visuell sieht, dass der Prozess eingehalten wird.

Endpoints:
  GET /api/performance/transitions                  — alle Transitions
  GET /api/performance/transitions/{task_id}        — Transitions eines Tasks
  GET /api/performance/projects/{project_id}/timeline — Timeline eines Projekts
  GET /api/performance/projects/{project_id}/stats — Performance-Stats
  GET /api/performance/stats                        — Globale Stats
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..auth import require_auth
from ..models.transition import TaskTransition
from ..models.task import Task
from ..models.project import Project
from ..schemas.transition import (
    TaskTransitionRead, TaskTransitionList, ProjectTransitionTimeline,
)

router = APIRouter(prefix="/api/performance", tags=["performance"])


def _to_read(t: TaskTransition) -> TaskTransitionRead:
    """Konvertiert ORM-Objekt in Pydantic-Schema."""
    # === Bugfix 19.06.2026 (Task 921bba39d13f) ===
    # Display-Namen ableiten (z.B. "todo" -> "GO"), damit die UI die
    # user-freundlichen Texte rendern kann.
    from ..utils.status_labels import display_status
    return TaskTransitionRead(
        id=t.id,
        task_id=t.task_id,
        project_id=t.project_id,
        from_status=t.from_status,
        to_status=t.to_status,
        from_status_display=display_status(t.from_status) if t.from_status else None,
        to_status_display=display_status(t.to_status) if t.to_status else None,
        transition_at=t.transition_at,
        processing_at=t.processing_at,
        completed_at=t.completed_at,
        delay_s=t.delay_s,
        duration_ms=t.duration_ms,
        agent=t.agent,
        reason=t.reason,
        details=t.details or {},
    )


@router.get("/transitions", response_model=TaskTransitionList)
async def list_transitions(
    project_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    from_status: Optional[str] = Query(None),
    to_status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle Task-Transitions (zentrale Performance-Tabelle)."""
    stmt = select(TaskTransition).order_by(TaskTransition.transition_at.desc())
    if project_id:
        stmt = stmt.where(TaskTransition.project_id == project_id)
    if task_id:
        # User-Direktive 18.06.2026: Fuzzy-Suche fuer teilweise IDs (Performance.tsx truncated auf 10 Zeichen)
        if len(task_id) < 12:
            stmt = stmt.where(TaskTransition.task_id.like(f"{task_id}%"))
        else:
            stmt = stmt.where(TaskTransition.task_id == task_id)
    if from_status:
        stmt = stmt.where(TaskTransition.from_status == from_status)
    if to_status:
        stmt = stmt.where(TaskTransition.to_status == to_status)
    total_stmt = select(sqlfunc.count()).select_from(stmt.subquery())
    total = db.execute(total_stmt).scalar() or 0
    rows = list(db.execute(stmt.offset(offset).limit(limit)).scalars())
    return TaskTransitionList(
        items=[_to_read(r) for r in rows],
        total=int(total),
        project_id=project_id,
    )


@router.get("/transitions/{task_id}", response_model=TaskTransitionList)
async def list_task_transitions(
    task_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Listet alle Transitions eines bestimmten Tasks (Audit-Trail)."""
    # Pruefe ob Task existiert
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    rows = list(db.execute(
        select(TaskTransition)
        .where(TaskTransition.task_id == task_id)
        .order_by(TaskTransition.transition_at.desc())
        .limit(limit)
    ).scalars())
    return TaskTransitionList(
        items=[_to_read(r) for r in rows],
        total=len(rows),
        project_id=task.project_id,
    )


@router.get("/projects/{project_id}/timeline", response_model=ProjectTransitionTimeline)
async def project_timeline(
    project_id: str,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Timeline aller Transitions fuer ein Projekt (Performance-Dashboard)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = list(db.execute(
        select(TaskTransition)
        .where(TaskTransition.project_id == project_id,
               TaskTransition.transition_at >= cutoff)
        .order_by(TaskTransition.transition_at.desc())
        .limit(limit)
    ).scalars())

    # Summary
    by_from_to: dict = {}
    for r in rows:
        key = f"{r.from_status}->{r.to_status}"
        by_from_to[key] = by_from_to.get(key, 0) + 1
    by_agent: dict = {}
    for r in rows:
        ag = r.agent or "unknown"
        by_agent[ag] = by_agent.get(ag, 0) + 1
    avg_delay = sum(r.delay_s for r in rows) / len(rows) if rows else 0.0
    avg_duration_ms = (
        sum((r.duration_ms or 0) for r in rows) / len(rows) if rows else 0.0
    )
    summary = {
        "total_transitions": len(rows),
        "by_transition": by_from_to,
        "by_agent": by_agent,
        "avg_delay_s": round(avg_delay, 3),
        "avg_duration_ms": round(avg_duration_ms, 2),
        "days_window": days,
        "first_transition": rows[-1].transition_at.isoformat() if rows else None,
        "last_transition": rows[0].transition_at.isoformat() if rows else None,
    }
    return ProjectTransitionTimeline(
        project_id=project_id,
        items=[_to_read(r) for r in rows],
        total=len(rows),
        summary=summary,
    )


@router.get("/projects/{project_id}/stats")
async def project_stats(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Performance-Stats eines Projekts: durchschnittliche Verweildauer pro Status."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    # Verweildauer pro Status: Differenz zwischen aufeinanderfolgenden Transitions
    rows = list(db.execute(
        select(TaskTransition)
        .where(TaskTransition.project_id == project_id)
        .order_by(TaskTransition.task_id, TaskTransition.transition_at.asc())
    ).scalars())
    # Gruppieren nach task_id
    by_task: dict = {}
    for r in rows:
        by_task.setdefault(r.task_id, []).append(r)
    # Berechne Dauer in to_status (von transition_at bis processing_at)
    durations_by_status: dict = {}
    counts_by_status: dict = {}
    for tid, transitions in by_task.items():
        for tr in transitions:
            if tr.processing_at and tr.transition_at:
                dur_s = (tr.processing_at - tr.transition_at).total_seconds()
            else:
                dur_s = 0.0
            durations_by_status[tr.to_status] = durations_by_status.get(tr.to_status, 0.0) + dur_s
            counts_by_status[tr.to_status] = counts_by_status.get(tr.to_status, 0) + 1
    avg_durations = {
        s: round(durations_by_status[s] / counts_by_status[s], 3) if counts_by_status.get(s, 0) > 0 else 0.0
        for s in counts_by_status
    }
    # Anzahl Tasks
    task_count = db.execute(
        select(sqlfunc.count(Task.id)).where(Task.project_id == project_id)
    ).scalar() or 0
    return {
        "project_id": project_id,
        "task_count": int(task_count),
        "transition_count": len(rows),
        "avg_durations_s_per_status": avg_durations,
        "transitions_per_status": counts_by_status,
        "expected_delay_s": 5.0,
        "note": "avg_durations_s_per_status = durchschnittliche Verweildauer im Status (in Sekunden, inkl. 5s-Default-Delay).",
    }


@router.get("/stats")
async def global_stats(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Globale Performance-Stats ueber alle Projekte."""
    total = db.execute(select(sqlfunc.count(TaskTransition.id))).scalar() or 0
    by_from_to = dict(db.execute(
        select(
            sqlfunc.concat(TaskTransition.from_status, "->", TaskTransition.to_status).label("k"),
            sqlfunc.count(TaskTransition.id).label("c"),
        ).group_by("k")
    ).all())
    by_agent = dict(db.execute(
        select(TaskTransition.agent, sqlfunc.count(TaskTransition.id))
        .group_by(TaskTransition.agent)
    ).all())
    avg_delay_row = db.execute(
        select(sqlfunc.avg(TaskTransition.delay_s))
    ).first()
    avg_delay = float(avg_delay_row[0]) if avg_delay_row and avg_delay_row[0] is not None else 0.0
    avg_dur_row = db.execute(
        select(sqlfunc.avg(TaskTransition.duration_ms))
    ).first()
    avg_duration = float(avg_dur_row[0]) if avg_dur_row and avg_dur_row[0] is not None else 0.0
    return {
        "total_transitions": int(total),
        "by_transition": {k: int(v) for k, v in by_from_to.items() if k},
        "by_agent": {(k or "unknown"): int(v) for k, v in by_agent.items()},
        "avg_delay_s": round(avg_delay, 3),
        "avg_duration_ms": round(avg_duration, 2),
        "expected_delay_s": 5.0,
    }
