"""AgentAnswerService — Eskalations-Workflow (User-Direktive 18.06.2026).

Wenn eine AgentQuestion erstellt wird (z.B. weil Heuristik Issues findet),
soll zunaechst versucht werden, die Frage durch KI-Agents zu beantworten:

  Stufe 1: CIO (interne Regeln, Architektur, Codebase)
  Stufe 2: CEO-digital (mehr Kontext, offene Fragen)
  Stufe 3: User (menschliche Entscheidung, NUR wenn beide Stufen scheitern)

Nur wenn weder CIO noch CEO-digital eine befriedigende Antwort liefern
koennen, wird der User ueber die UI benachrichtigt (Rueckfrage-Button).
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.agent_question import AgentQuestion
from ..models.task import Task
from .subagent_service import SubAgentService

logger = logging.getLogger("pi-dashboard-2.agent-answer")


# === Confidence-Threshold ===
# Wenn die KI eine Antwort mit Confidence >= diesem Wert liefert,
# wird die Antwort akzeptiert und der User wird NICHT gefragt.
MIN_CONFIDENCE = 0.7


def _extract_confidence(answer: str) -> Tuple[str, float]:
    """Extrahiert die Confidence aus der KI-Antwort.

    Erwartetes Format:
        <Antwort>
        CONFIDENCE: <0.0-1.0>

    Wenn keine Confidence angegeben ist, wird 0.5 angenommen.
    """
    if not answer:
        return "", 0.0
    match = re.search(r"CONFIDENCE[:\s]+([0-9]*\.?[0-9]+)", answer, re.IGNORECASE)
    if match:
        try:
            conf = float(match.group(1))
            # Entferne die CONFIDENCE-Zeile aus der Antwort
            answer_clean = re.sub(r"\n?CONFIDENCE[:\s]+[0-9]*\.?[0-9]+\s*$", "", answer, flags=re.IGNORECASE).strip()
            return answer_clean, max(0.0, min(1.0, conf))
        except ValueError:
            pass
    return answer.strip(), 0.5


def try_auto_answer(
    db: Session,
    question_id: str,
    role_name: str,
) -> Tuple[bool, str, float]:
    """Versucht, eine AgentQuestion durch einen KI-Agent zu beantworten.

    Args:
        db: SQLAlchemy Session
        question_id: AgentQuestion-ID
        role_name: Welcher Agent soll antworten ('CIO' oder 'CEO-digital')

    Returns:
        (answered, answer_text, confidence)
        - answered: True, wenn die Antwort akzeptabel ist (confidence >= MIN_CONFIDENCE)
        - answer_text: Die Antwort des Agents
        - confidence: Die Confidence der Antwort (0.0-1.0)
    """
    q = db.get(AgentQuestion, question_id)
    if not q:
        logger.warning(f"AgentQuestion {question_id} nicht gefunden")
        return False, "", 0.0

    task = db.get(Task, q.context.get("task_id") if isinstance(q.context, dict) else None)
    if not task:
        # Fallback: task_id aus context extrahieren
        if isinstance(q.context, dict):
            task_id = q.context.get("task_id")
            if task_id:
                task = db.get(Task, task_id)

    # Build prompt fuer den Agent
    prompt = _build_answer_prompt(q, task, role_name)

    try:
        agent = SubAgentService.build_agent(db, role_name, task=task)
        import asyncio
        try:
            # Falls wir schon in einem Event-Loop sind (FastAPI async)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In einem laufenden Loop koennen wir nicht asyncio.run() aufrufen
                # Wir nutzen den Thread-Pool als Workaround
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, agent.run(prompt))
                    response_text = future.result(timeout=60)
            else:
                response_text = asyncio.run(agent.run(prompt))
        except RuntimeError:
            # Fallback: versuche asyncio.run (kann fehlschlagen wenn Loop laeuft)
            response_text = asyncio.run(agent.run(prompt))
        answer_clean, confidence = _extract_confidence(response_text)
        logger.info(
            f"{role_name} antwortet auf Frage {question_id}: "
            f"confidence={confidence:.2f}, len={len(answer_clean)}"
        )
        answered = confidence >= MIN_CONFIDENCE
        return answered, answer_clean, confidence
    except Exception as e:
        logger.warning(f"{role_name} konnte Frage {question_id} nicht beantworten: {e}")
        return False, "", 0.0


def _build_answer_prompt(q: AgentQuestion, task: Optional[Task], role_name: str) -> str:
    """Baut den Prompt fuer den Agent zur Beantwortung der Frage."""
    context = q.context if isinstance(q.context, dict) else {}
    task_id = context.get("task_id", "unknown")
    task_title = task.title if task else "unknown"
    task_desc = (task.description or "")[:500] if task else ""

    if role_name == "CIO":
        role_intro = (
            "Du bist der CIO. Deine Aufgabe ist es, offene Fragen zu Tasks zu beantworten, "
            "wenn die Antwort aus Architektur-Regeln, Code-Konventionen oder bekannten "
            "Standards abgeleitet werden kann. Wenn du dir SICHER bist, antworte mit der Loesung. "
            "Wenn du NICHT sicher bist, schreibe explizit: 'KEINE_ANTWORT' und erklaere warum."
        )
    elif role_name == "CEO-digital":
        role_intro = (
            "Du bist CEO-digital. Deine Aufgabe ist es, offene strategische Fragen zu Tasks "
            "zu beantworten. Du hast Zugriff auf OpenBrain und kannst vage Anforderungen praezisieren. "
            "Wenn du eine sinnvolle Antwort geben kannst, tue es. "
            "Wenn nicht, schreibe 'KEINE_ANTWORT' und erklaere warum."
        )
    else:
        role_intro = f"Du bist {role_name}. Beantworte die Frage so gut du kannst."

    prompt = f"""{role_intro}

TASK: {task_title} (ID: {task_id})
BESCHREIBUNG: {task_desc[:300]}

FRAGE: {q.title}

DETAILS: {(q.description or "")[:500]}

EMPFEHLUNG: {(q.recommendation or "")[:300]}

Gib eine konkrete Antwort in 1-3 Saetzen. Wenn du unsicher bist, schreibe 'KEINE_ANTWORT' und erklaere warum.

Am Ende schreibe eine Zeile:
CONFIDENCE: <0.0-1.0>

Wobei:
- 0.0-0.3: Ich bin sehr unsicher, der User sollte antworten
- 0.4-0.6: Teilsicher, waere besser wenn der User bestaetigt
- 0.7-1.0: Ich bin sicher, der User muss nicht gefragt werden

Deine Antwort:
"""
    return prompt


def answer_question(
    db: Session,
    question_id: str,
) -> Tuple[bool, str, str]:
    """Versucht, eine AgentQuestion zu beantworten (CIO -> CEO-digital -> User).

    Returns:
        (resolved, answer_text, answered_by_role)
        - resolved: True, wenn eine befriedigende Antwort gefunden wurde
        - answer_text: Die finale Antwort
        - answered_by_role: Wer hat geantwortet ('CIO', 'CEO-digital', 'user', 'none')
    """
    q = db.get(AgentQuestion, question_id)
    if not q:
        return False, "", "none"

    # Stufe 1: CIO
    answered, answer, conf = try_auto_answer(db, question_id, "CIO")
    if answered:
        return True, answer, "CIO"

    # Stufe 2: CEO-digital
    answered, answer, conf = try_auto_answer(db, question_id, "CEO-digital")
    if answered:
        return True, answer, "CEO-digital"

    # Stufe 3: User (bleibt offen)
    return False, "", "none"