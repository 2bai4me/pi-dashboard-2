"""BoardOperator-Router: Steuerung der Live-Board Watchdog-Instanzen.

Endpoints:
  GET    /api/operators/                    — Liste aller Operatoren
  GET    /api/operators/active              — nur aktive Operatoren (fuer Sidebar-Badge)
  GET    /api/agents/active                 — ALLE aktiven Agenten/Sub-Agenten (Task 44c7229af57e)
  GET    /api/operators/{board_id}          — Status eines Board-Operators
  POST   /api/operators/{board_id}/start    — manuell starten
  POST   /api/operators/{board_id}/stop     — manuell stoppen
  POST   /api/operators/{board_id}/heartbeat — Heartbeat (vom Operator selbst)
  GET    /api/operators/{board_id}/stats    — Watchdog-Statistiken + letzte Findings

User-Direktive 17.06.2026 / 19.06.2026.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db
from ..models.board_operator import BoardOperator
from ..models.project import Project
from ..services import board_operator_service as svc

logger = logging.getLogger("pi-dashboard-2.operators")
router = APIRouter(prefix="/api/operators", tags=["operators"])


@router.get("/")
async def list_operators(
    status: Optional[str] = Query(None, description="Filter: active|stale|stopped|error|..."),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Liste aller Board-Operatoren."""
    stmt = select(BoardOperator).order_by(BoardOperator.updated_at.desc())
    if status:
        stmt = stmt.where(BoardOperator.agent_status == status)
    items = list(db.execute(stmt).scalars())
    return {
        "items": [o.to_dict() for o in items],
        "total": len(items),
    }


@router.get("/active")
async def list_active_operators(
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Nur Operatoren mit Status active/starting (fuer globale Badge-Logik)."""
    items = list(db.execute(
        select(BoardOperator).where(
            BoardOperator.agent_status.in_(["active", "starting", "stale"])
        )
    ).scalars())
    return {
        "items": [o.to_dict() for o in items],
        "total": len(items),
    }


@router.get("/agents/active")
async def list_active_agents(
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Uebersicht ALLER aktiven Agenten/Sub-Agenten (Task 44c7229af57e).

    Liefert:
      - board_operators (Live-Operatoren)
      - sub_agents (via swarm-spawner gestartete Prozesse)
      - worker_loop (automatischer Worker)
      - in_progress_tasks (Tasks, die gerade aktiv bearbeitet werden)
      - scheduler_jobs (APScheduler-Jobs)
    """
    from ..services.sub_agent import list_active_agents as list_active_sub_agents
    from ..services.worker_loop import _worker_task, _worker_stop
    from ..services.session_helper import get_session_id
    from ..models.task import Task
    from ..models.transition import TaskTransition
    from sqlalchemy import func as sqlfunc

    now = datetime.utcnow()

    # 1) Board-Operatoren (live)
    operators = list(db.execute(
        select(BoardOperator).where(
            BoardOperator.agent_status.in_(["active", "starting", "stale"])
        )
    ).scalars())
    operator_items = []
    for op in operators:
        age_s = None
        if op.last_heartbeat:
            age_s = int((now - op.last_heartbeat.replace(tzinfo=None)).total_seconds())
        operator_items.append({
            "type": "board_operator",
            "agent": f"kanban-operator-{op.id[:8]}",
            "role": "kanban-operator",
            "session_id": f"session-operator-{op.id[:8]}",
            "task_id": None,
            "board_id": op.board_id,
            "status": op.agent_status,
            "last_heartbeat_age_s": age_s,
            "checks_total": op.checks_total,
            "stale_tasks_found": op.stale_tasks_found,
            "alerts_sent": op.alerts_sent,
            "details": {"id": op.id, "started_at": op.started_at.isoformat() if op.started_at else None},
        })

    # 2) Sub-Agenten (swarm-spawner)
    sub_agents = list_active_sub_agents()
    sub_agent_items = []
    for sa in sub_agents:
        # Session-ID aus letzter Transition fuer diesen Task
        session_id = None
        if sa.get("task_id"):
            tr = db.execute(
                select(TaskTransition)
                .where(TaskTransition.task_id == sa["task_id"])
                .order_by(TaskTransition.transition_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if tr:
                session_id = tr.session_id
        sub_agent_items.append({
            "type": "sub_agent",
            "agent": sa["role"],
            "role": sa["role"],
            "session_id": session_id or "session-unknown",
            "task_id": sa.get("task_id"),
            "pid": sa.get("pid"),
            "status": "running",
            "uptime_s": int(sa.get("uptime_s", 0)),
            "log_path": sa.get("log_path"),
            "details": {"spawned_at": datetime.fromtimestamp(sa.get("spawned_at", 0)).isoformat() if sa.get("spawned_at") else None},
        })

    # 3) Worker-Loop
    worker_active = bool(_worker_task and not _worker_task.done() and not _worker_stop)
    worker_item = None
    if worker_active:
        # Aktuell bearbeiteter Task (letzte in_progress Transition)
        current_task_id = None
        current_session_id = None
        latest = db.execute(
            select(TaskTransition)
            .where(TaskTransition.to_status == "in_progress")
            .order_by(TaskTransition.transition_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest:
            current_task_id = latest.task_id
            current_session_id = latest.session_id
        worker_item = {
            "type": "worker_loop",
            "agent": "worker-auto",
            "role": "worker-loop",
            "session_id": current_session_id or get_session_id() or "session-worker",
            "task_id": current_task_id,
            "status": "running",
            "details": {"budget_exceeded": False},  # wird unten ggf. korrigiert
        }

    # 4) In-Progress-Tasks (ohne laufenden Sub-Agenten)
    in_progress_tasks = list(db.execute(
        select(Task).where(Task.status == "in_progress")
    ).scalars())
    in_progress_items = []
    for t in in_progress_tasks:
        # Session-ID aus letzter Transition
        session_id = None
        tr = db.execute(
            select(TaskTransition)
            .where(TaskTransition.task_id == t.id)
            .order_by(TaskTransition.transition_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if tr:
            session_id = tr.session_id
        in_progress_items.append({
            "type": "in_progress_task",
            "agent": t.assigned_subagent or t.assigned_role or "unassigned",
            "role": t.assigned_role,
            "session_id": session_id or "session-unknown",
            "task_id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "details": {"assigned_subagent": t.assigned_subagent},
        })

    # 5) Scheduler-Jobs (Hintergrund-Jobs)
    try:
        from ..scheduler import _scheduler
        scheduler_items = []
        if _scheduler and _scheduler.running:
            for job in _scheduler.get_jobs():
                scheduler_items.append({
                    "type": "scheduler_job",
                    "agent": job.id,
                    "role": "scheduler",
                    "session_id": get_session_id() or "session-server",
                    "task_id": None,
                    "status": "running",
                    "details": {"name": job.name, "trigger": str(job.trigger), "next_run": job.next_run_time.isoformat() if job.next_run_time else None},
                })
    except Exception:
        scheduler_items = []

    all_items = operator_items + sub_agent_items + ([worker_item] if worker_item else []) + in_progress_items + scheduler_items

    return {
        "total": len(all_items),
        "by_type": {
            "board_operators": len(operator_items),
            "sub_agents": len(sub_agent_items),
            "worker_loop": 1 if worker_item else 0,
            "in_progress_tasks": len(in_progress_items),
            "scheduler_jobs": len(scheduler_items),
        },
        "items": all_items,
        "checked_at": now.isoformat(),
    }


@router.get("/{board_id}")
async def get_operator(
    board_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Status des Operators fuer ein Board."""
    op = db.execute(
        select(BoardOperator).where(BoardOperator.board_id == board_id)
    ).scalar_one_or_none()
    if not op:
        # 200 mit Default-Werten (no_operator), damit Frontend nicht 404 braucht
        return {
            "id": None,
            "board_id": board_id,
            "agent_status": "not_started",
            "live_color": "gray",
            "live_label": "inactive",
            "last_heartbeat": None,
            "last_heartbeat_age_s": None,
            "checks_total": 0,
            "stale_tasks_found": 0,
            "alerts_sent": 0,
            "questions_asked": 0,
        }
    return op.to_dict()


@router.post("/{board_id}/start")
async def start_operator(
    board_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Startet den Operator fuer ein Board manuell.

    Normalerweise nicht noetig — der globale Watchdog startet Operatoren
    automatisch, sobald ein Board auf mode=live gesetzt wird. Dieser
    Endpoint ist fuer explizites Triggern (z.B. nach manuellem Fix).
    """
    board = db.get(Project, board_id)
    if not board:
        raise HTTPException(404, f"Board {board_id} nicht gefunden")

    op = await svc.start_operator(board_id)
    # Sicherstellen dass Modus = live
    if board.mode != "live":
        board.mode = "live"
        db.commit()
    return op.to_dict()


@router.post("/{board_id}/stop")
async def stop_operator(
    board_id: str,
    reason: str = Query("user_request", min_length=1),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Stoppt den Operator fuer ein Board."""
    op = await svc.stop_operator(board_id, reason)
    if not op:
        return {
            "id": None,
            "board_id": board_id,
            "agent_status": "stopped",
            "live_color": "gray",
            "live_label": "inactive",
        }
    return op.to_dict()


@router.post("/{board_id}/heartbeat")
async def heartbeat(
    board_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Heartbeat-Endpoint (wird vom Operator alle 5s aufgerufen)."""
    ok = await svc.record_heartbeat(board_id)
    if not ok:
        # Kein Operator-Record -> automatisch anlegen (graceful)
        await svc.start_operator(board_id)
        await svc.record_heartbeat(board_id)
    op = db.execute(
        select(BoardOperator).where(BoardOperator.board_id == board_id)
    ).scalar_one_or_none()
    return op.to_dict() if op else {"ok": False}


@router.get("/{board_id}/stats")
async def get_stats(
    board_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Statistiken + letzte Findings des Operators."""
    op = db.execute(
        select(BoardOperator).where(BoardOperator.board_id == board_id)
    ).scalar_one_or_none()
    if not op:
        raise HTTPException(404, f"Kein Operator fuer Board {board_id}")

    # Letzte AgentQuestions, die der Operator erstellt hat
    from ..models.agent_question import AgentQuestion
    questions = list(db.execute(
        select(AgentQuestion).where(
            AgentQuestion.agent_id.like(f"kanban-operator-{op.id[:8]}%")
        ).order_by(AgentQuestion.created_at.desc()).limit(10)
    ).scalars())

    return {
        **op.to_dict(),
        "recent_questions": [q.to_dict() for q in questions],
    }
