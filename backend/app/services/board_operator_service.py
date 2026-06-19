"""BoardOperator-Service: Watchdog-Instanzen fuer Live-Boards.

Architektur (User-Direktive 17.06.2026):
  - Beim Backend-Startup wird ein globaler Watchdog gestartet.
  - Der Watchdog prueft alle 10s alle Boards:
    * Board mit mode=live UND kein aktiver Operator  -> Operator starten
    * Board mit mode=live UND Operator stale (>30s)  -> Operator neu starten
    * Board mit mode != live UND Operator laeuft    -> Operator stoppen
  - Jeder Operator laeuft als eigenstaendige asyncio-Task (coroutine).
  - Operator sendet alle 5s Heartbeat ans Backend.
  - Operator prueft alle 30s die Tasks des Boards:
    * in_progress ohne Update > 30 min  -> "stale" (alert)
    * triage seit > 60 min              -> "needs_attention"
    * rueckfrage seit > 30 min           -> "needs_user" (AgentQuestion)
    * warten seit > 60 min               -> "needs_review"
  - Frontend zeigt Live-Icon gruen, wenn Heartbeat < 15s alt.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.base import SessionLocal
from ..models.board_operator import BoardOperator
from ..models.project import Project
from ..models.task import Task

logger = logging.getLogger("pi-dashboard-2.operator")


# === Operator-Tasks Registry (pro Prozess) ===
# Key = board_id, Value = asyncio.Task
_operator_tasks: Dict[str, asyncio.Task] = {}
# Lock fuer sicheres Start/Stop
_lock = asyncio.Lock()

# Watchdog-Loop-Task
_watchdog_task: Optional[asyncio.Task] = None

# Konfiguration
HEARTBEAT_INTERVAL_S = 5.0
WATCHDOG_INTERVAL_S = 10.0
OPERATOR_CHECK_INTERVAL_S = 30.0
STALE_HEARTBEAT_S = 15.0  # Frontend zeigt gelb ab diesem Alter
DEAD_HEARTBEAT_S = 60.0   # Watchdog startet neu ab diesem Alter


# ===========================================
#  Operator-Lifecycle
# ===========================================

async def start_operator(board_id: str) -> BoardOperator:
    """Startet eine Operator-Task fuer ein Board (idempotent)."""
    async with _lock:
        # 1) DB-Record anlegen/holen
        with SessionLocal() as db:
            op = db.execute(
                select(BoardOperator).where(BoardOperator.board_id == board_id)
            ).scalar_one_or_none()
            if not op:
                op = BoardOperator(board_id=board_id, agent_status="starting")
                db.add(op)
                db.commit()
                db.refresh(op)
            else:
                op.agent_status = "starting"
                op.error_message = None
                op.started_at = datetime.utcnow()
                op.stopped_at = None
                db.commit()
                db.refresh(op)

        # 2) Task schon laufend? Nichts tun
        existing = _operator_tasks.get(board_id)
        if existing and not existing.done():
            logger.info(f"Operator fuer Board {board_id[:8]} laeuft bereits")
            return op

        # 3) Neue Task starten
        task = asyncio.create_task(_operator_loop(board_id, op.id))
        _operator_tasks[board_id] = task
        logger.info(f"Operator-Task fuer Board {board_id[:8]} gestartet")
        return op


async def stop_operator(board_id: str, reason: str = "user_request") -> Optional[BoardOperator]:
    """Stoppt die Operator-Task fuer ein Board."""
    async with _lock:
        task = _operator_tasks.pop(board_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Operator-Task-Cancel-Fehler: {e}")

        with SessionLocal() as db:
            op = db.execute(
                select(BoardOperator).where(BoardOperator.board_id == board_id)
            ).scalar_one_or_none()
            if op:
                op.agent_status = "stopped"
                op.stopped_at = datetime.utcnow()
                op.error_message = reason if reason != "user_request" else None
                db.commit()
                db.refresh(op)
        logger.info(f"Operator fuer Board {board_id[:8]} gestoppt ({reason})")
        return op


async def record_heartbeat(board_id: str) -> bool:
    """Schreibt last_heartbeat = now() (vom Operator selbst aufgerufen)."""
    with SessionLocal() as db:
        op = db.execute(
            select(BoardOperator).where(BoardOperator.board_id == board_id)
        ).scalar_one_or_none()
        if not op:
            return False
        op.last_heartbeat = datetime.utcnow()
        if op.agent_status == "starting":
            op.agent_status = "active"
        db.commit()
        return True


# ===========================================
#  Watchdog (global, prueft alle 10s)
# ===========================================

async def start_watchdog() -> None:
    """Startet den globalen Watchdog (einmal pro Prozess)."""
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        return
    _watchdog_task = asyncio.create_task(_watchdog_loop())
    logger.info("Board-Operator-Watchdog gestartet")


async def stop_watchdog() -> None:
    """Stoppt den globalen Watchdog und alle Operatoren."""
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass
    # Alle Operator-Tasks stoppen
    for board_id in list(_operator_tasks.keys()):
        await stop_operator(board_id, "shutdown")


async def _watchdog_loop() -> None:
    """Hauptloop des Watchdogs: prueft alle 10s, ob Operatoren korrekt laufen."""
    while True:
        try:
            await _watchdog_iteration()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Watchdog-Iteration-Fehler: {e}", exc_info=True)
        await asyncio.sleep(WATCHDOG_INTERVAL_S)


async def _watchdog_iteration() -> None:
    """Eine Watchdog-Iteration: startet/stoppt Operatoren basierend auf mode."""
    with SessionLocal() as db:
        # 1) Hole alle Live-Boards
        live_boards = list(db.execute(
            select(Project).where(Project.mode == "live")
        ).scalars())
        live_ids = {b.id for b in live_boards}

        # 2) Hole alle Operatoren
        all_operators = list(db.execute(select(BoardOperator)).scalars())
        op_by_board = {o.board_id: o for o in all_operators}

    # 3) Start Operatoren fuer Live-Boards, die keinen haben
    for board_id in live_ids:
        op = op_by_board.get(board_id)
        if not op:
            # Gar kein Operator -> starten
            await start_operator(board_id)
        elif op.agent_status in ("stopped", "error"):
            # Operator gestoppt, aber Board ist live -> neu starten
            await start_operator(board_id)
        elif op.agent_status in ("active", "starting"):
            # Pruefe Heartbeat
            if op.last_heartbeat:
                age = (datetime.utcnow() - op.last_heartbeat.replace(tzinfo=None)).total_seconds()
                if age > DEAD_HEARTBEAT_S:
                    logger.warning(
                        f"Operator {op.id[:8]} fuer Board {board_id[:8]} stale "
                        f"({int(age)}s) -> Neustart"
                    )
                    op.agent_status = "stale"
                    with SessionLocal() as db:
                        db.merge(op)
                        db.commit()
                    await start_operator(board_id)

    # 4) Stoppe Operatoren fuer Boards, die NICHT mehr live sind
    for board_id, op in op_by_board.items():
        if board_id not in live_ids and op.agent_status not in ("stopped", "not_started"):
            await stop_operator(board_id, "board_no_longer_live")


# ===========================================
#  Operator-Loop (eigenstaendige Coroutine pro Board)
# ===========================================

async def _operator_loop(board_id: str, operator_id: str) -> None:
    """Operator-Hauptloop: Heartbeat + Task-Checks.

    Wird beim Board-Start als asyncio-Task gestartet, laeuft bis zum Stop.
    """
    logger.info(f"Operator-Loop gestartet: board={board_id[:8]} op={operator_id[:8]}")
    try:
        # Erster Heartbeat sofort
        await record_heartbeat(board_id)
        last_check = 0.0
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            # Heartbeat
            await record_heartbeat(board_id)
            # Periodischer Task-Check
            now = asyncio.get_event_loop().time()
            if now - last_check >= OPERATOR_CHECK_INTERVAL_S:
                last_check = now
                try:
                    await _check_board_tasks(board_id, operator_id)
                except Exception as e:
                    logger.error(f"Task-Check-Fehler: {e}", exc_info=True)
    except asyncio.CancelledError:
        logger.info(f"Operator-Loop fuer Board {board_id[:8]} abgebrochen")
        raise
    except Exception as e:
        logger.error(f"Operator-Loop-Crash: {e}", exc_info=True)
        with SessionLocal() as db:
            op = db.get(BoardOperator, operator_id)
            if op:
                op.agent_status = "error"
                op.error_message = str(e)[:500]
                op.stopped_at = datetime.utcnow()
                db.commit()


async def _check_board_tasks(board_id: str, operator_id: str) -> None:
    """Prueft alle Tasks des Boards auf haengende / wartende States."""
    with SessionLocal() as db:
        op = db.get(BoardOperator, operator_id)
        if not op:
            return
        op.checks_total += 1
        db.commit()

        tasks = list(db.execute(
            select(Task).where(Task.project_id == board_id)
        ).scalars())

        stale = []
        needs_user = []
        needs_attention = []
        needs_review = []

        now_naive = datetime.utcnow().replace(tzinfo=None)

        for t in tasks:
            # updated_at als Bezugspunkt
            updated = (t.updated_at or t.created_at)
            if updated and updated.tzinfo:
                updated = updated.replace(tzinfo=None)
            if not updated:
                continue
            age_min = (now_naive - updated).total_seconds() / 60.0

            if t.status == "in_progress" and age_min > 30:
                stale.append((t, age_min))
            elif t.status == "triage" and age_min > 60:
                needs_attention.append((t, age_min))
            elif t.status == "rueckfrage" and age_min > 30:
                needs_user.append((t, age_min))
            elif t.status == "warten" and age_min > 60:
                needs_review.append((t, age_min))

        # Statistiken aktualisieren
        op.stale_tasks_found = len(stale) + len(needs_user) + len(needs_attention) + len(needs_review)
        if needs_user or stale:
            # Nur EINMAL pro Check zaehlen (ein Alert pro Run)
            op.alerts_sent += 1
        db.commit()

        # Findings loggen
        if stale or needs_user or needs_attention or needs_review:
            logger.info(
                f"Operator board={board_id[:8]}: "
                f"stale={len(stale)} needs_user={len(needs_user)} "
                f"needs_attention={len(needs_attention)} needs_review={len(needs_review)}"
            )

        # Bei Bedarf AgentQuestion erstellen (User fragen, wenn was haengt)
        if needs_user and op.questions_asked < 5:  # Max 5 Fragen pro Operator-Lifetime
            await _maybe_ask_user(db, op, board_id, needs_user)


async def _maybe_ask_user(db: Session, op: BoardOperator, board_id: str,
                          needs_user_list: list) -> None:
    """Erstellt eine AgentQuestion, wenn Tasks im rueckfrage-Status haengen.

    Maximal eine Frage pro Check, um User nicht zu spammen.
    """
    from ..models.agent_question import AgentQuestion
    t, age_min = needs_user_list[0]
    # Pruefen, ob es schon eine offene Frage fuer diesen Task gibt
    existing = db.execute(
        select(AgentQuestion).where(
            AgentQuestion.context["task_id"].astext == t.id,
            AgentQuestion.status == "pending",
        )
    ).scalar_one_or_none()
    if existing:
        return
    q = AgentQuestion(
        agent_id=f"kanban-operator-{op.id[:8]}",
        agent_level="Worker",
        agent_label=f"Kanban-Operator (Board {board_id[:8]})",
        question_type="text",
        title=f"Task haengt seit {int(age_min)} min: {t.title[:80]}",
        question=(
            f"Der Task '{t.title}' ist seit {int(age_min)} Minuten im Status "
            f"'{t.status}', ohne dass sich etwas getan hat. "
            f"Brauchst du Input von mir (User), oder kann der Subagent weitermachen?"
        ),
        context={"task_id": t.id, "board_id": board_id, "age_min": int(age_min)},
        priority="medium" if age_min < 60 else "high",
        status="pending",
    )
    db.add(q)
    op.questions_asked += 1
    db.commit()
    logger.info(f"Operator hat User-Frage erstellt: {q.id} (task={t.id})")
