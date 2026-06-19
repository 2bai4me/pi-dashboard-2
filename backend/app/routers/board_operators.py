"""BoardOperator-Router: Steuerung der Live-Board Watchdog-Instanzen.

Endpoints:
  GET    /api/operators/                    — Liste aller Operatoren
  GET    /api/operators/active              — nur aktive Operatoren (fuer Sidebar-Badge)
  GET    /api/operators/{board_id}          — Status eines Board-Operators
  POST   /api/operators/{board_id}/start    — manuell starten
  POST   /api/operators/{board_id}/stop     — manuell stoppen
  POST   /api/operators/{board_id}/heartbeat — Heartbeat (vom Operator selbst)
  GET    /api/operators/{board_id}/stats    — Watchdog-Statistiken + letzte Findings

User-Direktive 17.06.2026.
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
