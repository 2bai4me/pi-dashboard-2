"""Helper-Funktionen fuer AgentQuestion, damit Router und SOPEngine dieselbe
Logik fuer Task-Status-Updates nutzen.

NEU (User-Direktive 18.06.2026): Eskalations-Workflow
================================================================
Wenn eine AgentQuestion erstellt wird (z.B. weil Heuristik Issues findet
oder die SOP-Engine User-Input braucht), wird zunaechst automatisch
versucht, die Frage durch KI-Agents zu beantworten:

  Stufe 1: CIO (interne Regeln, Architektur, Codebase)
  Stufe 2: CEO-digital (mehr Kontext, offene Fragen)
  Stufe 3: User (menschliche Entscheidung, NUR wenn beide scheitern)

Nur wenn weder CIO noch CEO-digital eine befriedigende Antwort liefern
koennen, wird der User ueber die Rueckfrage benachrichtigt.

Dieser Workflow ist in der SOP verankert: Alle Stellen, die eine
AgentQuestion erstellen (SOPEngine._await_user_input, Auto-Triage-Operator,
Board-Operator), nutzen diese zentrale Helper-Funktion.
"""
from __future__ import annotations

import logging
import uuid
import json as _json
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from ..models.task import Task
from ..models.history import TaskHistory
from ..models.agent_question import AgentQuestion

logger = logging.getLogger("pi-dashboard-2.tools")


def create_agent_question_with_auto_answer(
    db: Session,
    agent_id: str,
    agent_level: str,
    agent_label: str,
    question_type: str,
    title: str,
    question: str,
    description: Optional[str] = None,
    recommendation: Optional[str] = None,
    options: Optional[list] = None,
    options_config: Optional[str] = None,
    priority: str = "medium",
    task_id: Optional[str] = None,
    context: Optional[dict] = None,
) -> Tuple[AgentQuestion, bool, Optional[str]]:
    """Erstellt eine AgentQuestion mit automatischer Eskalation.

    Reihenfolge:
      1. CIO versucht zu antworten (Confidence >= 0.7)
      2. CEO-digital versucht zu antworten (Confidence >= 0.7)
      3. Wenn beide scheitern: AgentQuestion bleibt offen fuer User

    Args:
        db: SQLAlchemy Session
        agent_id, agent_level, agent_label: Agent-Identifikation
        question_type: 'text', 'confirmation', 'choice', 'image', 'attachment'
        title, question, description, recommendation: Frage-Inhalt
        options: List von Optionen (fuer 'choice')
        options_config: JSON-String
        priority: 'high', 'medium', 'low'
        task_id: Optional Task-ID
        context: Optional Dict mit weiteren Kontext-Daten

    Returns:
        Tuple (agent_question, requires_user_input, auto_answer)
        - agent_question: Die erstellte AgentQuestion (status='answered' wenn auto, sonst 'pending')
        - requires_user_input: True wenn User antworten muss, False wenn KI geantwortet hat
        - auto_answer: Die automatische Antwort (None wenn keine)
    """
    # 1) AgentQuestion IMMER erstellen (fuer Audit-Trail)
    q = AgentQuestion(
        id=f"q-{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        agent_level=agent_level,
        agent_label=agent_label,
        question_type=question_type,
        title=title,
        question=question,
        description=description,
        recommendation=recommendation,
        options=_json.dumps(options) if options else None,
        options_config=options_config,
        context=context or {},
        priority=priority,
        status="pending",
    )
    db.add(q)
    db.flush()  # damit q.id verfuegbar ist

    # 2) Auto-Answer versuchen (CIO -> CEO-digital)
    # Import hier, um zirkulaere Imports zu vermeiden
    from .agent_answer_service import answer_question
    resolved, auto_answer, answered_by = answer_question(db, q.id)
    logger.info(
        f"AgentQuestion {q.id} ({task_id or 'no-task'}): "
        f"resolved={resolved}, answered_by={answered_by}"
    )

    if resolved:
        # KI hat geantwortet -> als 'answered' markieren
        q.status = "answered"
        q.answer_text = auto_answer
        q.answered_at = datetime.utcnow()
        q.answered_by = answered_by
        # audit: auto-answered
        try:
            th = TaskHistory(
                task_id=task_id,
                event="agent_question_auto_answered",
                agent=answered_by,
                details={
                    "question_id": q.id,
                    "answered_by": answered_by,
                    "confidence": ">=0.7",
                    "answer_preview": (auto_answer or "")[:200],
                },
            )
            db.add(th)
        except Exception as e:
            logger.warning(f"TaskHistory konnte nicht erstellt werden: {e}")
        db.commit()
        return q, False, auto_answer

    # 3) User muss antworten
    db.commit()
    return q, True, None


def update_task_on_question(
    db: Session,
    task_id: str,
    question_id: str,
    agent_id: str,
    agent_label: Optional[str] = None,
) -> None:
    """Setzt den Task-Status auf 'rueckfrage' und setzt Meta-Felder,
    sobald eine AgentQuestion fuer diesen Task erstellt wurde.

    Wird sowohl vom Router (routers/agent_questions.py) als auch von der
    SOPEngine (services/sop_engine.py) aufgerufen, damit beide Pfade
    konsistent sind.
    """
    try:
        t = db.get(Task, task_id)
        if not t:
            return
        if t.status in ("done", "cancelled"):
            return
        old_status = t.status
        if t.status != "rueckfrage":
            t.status = "rueckfrage"
        try:
            meta = dict(t.meta or {})
        except Exception:
            meta = {}
        meta = dict(meta or {})
        meta["input_required"] = True
        meta["input_question_id"] = question_id
        meta["input_from_agent"] = agent_id
        meta["input_from_label"] = agent_label or agent_id
        meta["input_created_at"] = datetime.utcnow().isoformat()
        t.meta = meta
        # Audit
        try:
            th = TaskHistory(
                task_id=t.id,
                event="input_required",
                agent=agent_id,
                details={
                    "question_id": question_id,
                    "old_status": old_status,
                    "new_status": "rueckfrage",
                },
            )
            db.add(th)
        except Exception as e:
            logger.warning(f"TaskHistory konnte nicht erstellt werden: {e}")
        db.commit()
    except Exception as e:
        logger.warning(f"update_task_on_question fehlgeschlagen fuer task {task_id}: {e}")


def update_task_on_answer(
    db: Session,
    task_id: str,
    question_id: str,
    agent_id: str,
    auto_workflow: bool = True,
    agent_level: Optional[str] = None,
) -> dict:
    """Wenn User eine Frage beantwortet: setzt Task-Status zurueck
    und (bei C-Level-Fragen) auto-approve zu 'todo'.

    Returns: dict mit auto_workflow_result.
    """
    result = {"auto_approved": False, "old_status": None, "new_status": None}
    try:
        t = db.get(Task, task_id)
        if not t:
            return result
        if t.status == "rueckfrage":
            result["old_status"] = t.status
            # Meta bereinigen
            try:
                meta = dict(t.meta or {})
            except Exception:
                meta = {}
            meta = dict(meta or {})
            meta["input_required"] = False
            meta["input_answered_at"] = datetime.utcnow().isoformat()
            t.meta = meta
            # Audit: input_answered
            try:
                th = TaskHistory(
                    task_id=t.id,
                    event="input_answered",
                    agent=agent_id,
                    details={"question_id": question_id, "old_status": "rueckfrage", "new_status": "triage"},
                )
                db.add(th)
            except Exception as e:
                logger.warning(f"TaskHistory input_answered: {e}")
            # Auf triage zurueck
            t.status = "triage"
            result["new_status"] = "triage"
            # Auto-Approve nur bei C-Level
            if auto_workflow and agent_level == "C-Level":
                try:
                    th2 = TaskHistory(
                        task_id=t.id,
                        event="triage_approved_auto",
                        agent=agent_id,
                        details={"reason": "user_answered_cio_question", "question_id": question_id, "from": "auto_workflow"},
                    )
                    db.add(th2)
                except Exception as e:
                    logger.warning(f"TaskHistory triage_approved_auto: {e}")
                t.status = "todo"
                result["new_status"] = "todo"
                result["auto_approved"] = True
                try:
                    meta = dict(t.meta or {})
                except Exception:
                    meta = {}
                meta = dict(meta or {})
                meta["auto_workflow"] = "user_input_answered"
                t.meta = meta
            db.commit()
    except Exception as e:
        logger.warning(f"update_task_on_answer fehlgeschlagen: {e}")
    return result
