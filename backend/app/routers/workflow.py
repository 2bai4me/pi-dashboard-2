"""Standard-Workflow Router -- CIO-Triage-Review -> Worker -> Tester-Loop -> CIO-Final-Review.

User-Direktive 15.06.2026:
  TRIAGE -> [CIO Review] -> GO -> [Worker assigned] -> IN_PROGRESS
        -> [Worker done] -> REVIEW -> [Tester Code-Review]
        -> if issues: -> IN_PROGRESS (Loop)
        -> if OK: -> BLOCK -> [Auto-Create Freigabe-Task fuer CIO] -> DONE

Implementiert:
  POST /api/workflow/tasks/{id}/triage-approve     TRIAGE -> GO  (CIO-Review OK)
  POST /api/workflow/tasks/{id}/triage-reject      TRIAGE -> ? (Feedback)
  POST /api/workflow/tasks/{id}/assign             GO -> GO   (CIO weist Worker zu)
  POST /api/workflow/tasks/{id}/start              GO -> IN_PROGRESS (Worker startet)
  POST /api/workflow/tasks/{id}/submit-review      IN_PROGRESS -> REVIEW (Worker done)
  POST /api/workflow/tasks/{id}/tester-reject      REVIEW -> IN_PROGRESS (Tester findet Bugs)
  POST /api/workflow/tasks/{id}/tester-approve     REVIEW -> BLOCK + AUTO-CREATE Freigabe-Task
  POST /api/workflow/tasks/{id}/cio-approve        BLOCK -> DONE (CIO final OK + Freigabe-Task done)
  POST /api/workflow/tasks/{id}/cio-reject         BLOCK -> IN_PROGRESS (CIO final NICHT OK)
"""
from __future__ import annotations

import json
import re
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, Field

from ..db.base import get_db
from ..auth import require_auth
from ..models.task import Task
from ..models.history import TaskHistory
from ..services.task_service import TaskService
from ..services.task_service import _gen_id

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# ------------------------------------------------------------ Helpers ------------------------------------------------------------

def _conflict_keyword_matches(kw: str, text: str) -> bool:
    """Prueft ob ein Konflikt-Keyword im Text vorkommt.

    Wort-Keywords (nur Wortzeichen) werden mit Wortgrenzen-Match geprueft
    (re.search mit \\b), um False-Positives zu vermeiden. Beispiel:
    'tba' matcht NICHT in 'sichtbar', weil 'tba' kein eigenstaendiges Wort ist.

    Symbol-Keywords (enthalten Sonderzeichen wie ':', '?', '[', ']') werden
    als Substring gematcht, weil \\b fuer Sonderzeichen nicht definiert ist.
    Beispiel: 'todo:' matcht ueberall wo 'todo:' vorkommt (auch in der Wortmitte).

    Args:
        kw: Das Konflikt-Keyword (z.B. 'tba', 'todo:', '???').
        text: Der zu pruefende Text (bereits lowercase).

    Returns:
        True wenn Keyword gefunden wurde, sonst False.
    """
    if re.match(r'^\w+$', kw):
        # Wort-Keyword: Wortgrenzen-Match (kein False-Positive bei 'sichtbar'->'tba')
        return bool(re.search(rf'\b{re.escape(kw)}\b', text))
    # Symbol-Keyword: Substring-Match
    return kw in text


def _get_task(db: Session, task_id: str) -> Task:
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, f"Task {task_id} not found")
    return t


def _add_history(db: Session, task: Task, event: str, agent: str, **details):
    """Add a history entry to a task."""
    details_json = details.pop("details", None) or details
    TaskService._add_history(db, task, event, agent=agent, details=details_json)


def _set_status(db: Session, task: Task, new_status: str, agent: str, reason: str, **extra):
    """Atomically: set status + add history + update timestamp (sync, mit 5s-Background-Delay).

    User-Direktive 16.06.2026: Bei JEDEM Status-Wechsel 5s warten.
    Fuehrt auch Auto-Claim aus, wenn new_status='todo' (analog TaskService.set_status).
    Fuer neue Endpoints mit 5s-Verzoegerung siehe `_set_status_with_delay` (async).
    """
    from ..services.task_service import TaskService
    from ..services.pricing_service import take_pricing_snapshot

    old_status = task.status
    if old_status == new_status:
        return
    task.status = new_status
    task.updated_at = datetime.utcnow()
    details = {"from": old_status, "to": new_status, "reason": reason, **extra}
    _add_history(db, task, "status_changed", agent=agent, details=details)
    # Transition-Record (sync, delay=0) -- User-sichtbar in der Performance-Tabelle
    from ..models.transition import TaskTransition
    transition_at = task.updated_at
    # Transition-Record mit 5s-Delay (User-Direktive 16.06.2026)
    # Statt direktem Status-Wechsel: 5s Background-Delay, dann Auto-Claim
    TaskService._do_set_status_sync_body(
        db, task, old_status, new_status, agent, reason, details, delay_s=5.0
    )


async def _set_status_with_delay(db: Session, task: Task, new_status: str,
                                  agent: str, reason: str,
                                  delay_s: float = 5.0, **extra) -> Task:
    """Async-Helper: set status + respektiert 5s-Delay + dokumentiert Transition.

    Reihenfolge:
    1) Status setzen
    2) Transition-Record anlegen (transition_at=jetzt, processing_at=jetzt+delay)
    3) History 'transition_started' anlegen
    4) DB-Commit
    5) asyncio.sleep(delay_s) -- sichtbarer Delay
    6) Transition-Record updaten (processing_at, completed_at)
    7) History 'status_changed' final
    8) DB-Commit
    """
    from datetime import timedelta
    from ..models.transition import TaskTransition

    old_status = task.status
    if old_status == new_status:
        return task
    transition_at = datetime.utcnow()
    delay_seconds = max(0.0, float(delay_s))
    expected_processing_at = transition_at + timedelta(seconds=delay_seconds) if delay_seconds > 0 else transition_at

    task.status = new_status
    task.updated_at = transition_at
    details = {"from": old_status, "to": new_status, "reason": reason, **extra}

    # Session-ID ermitteln (PFLICHT: Performance-Tabelle muss Session zuordnen koennen)
    from ..services.session_helper import get_session_id
    _transition_session_id = get_session_id()
    if not _transition_session_id:
        # Fallback + Log: sollte nie passieren, da session_helper auto-init
        import logging as _logging
        _logging.getLogger("pi-dashboard-2").warning(
            f"[session-id] TaskTransition ohne session_id fuer Task {task.id[:8]} "
            f"{old_status!r}->{new_status!r} reason={reason!r}. session_helper lieferte leer."
        )
        _transition_session_id = "session-unknown"

    # Transition-Record anlegen
    tr = TaskTransition(
        task_id=task.id, project_id=task.project_id,
        from_status=old_status or "", to_status=new_status,
        transition_at=transition_at,
        processing_at=expected_processing_at,
        completed_at=None,
        delay_s=delay_seconds,
        duration_ms=None,
        session_id=_transition_session_id,
        agent=agent, reason=reason, details=details,
    )
    db.add(tr)
    _add_history(db, task, "transition_started", agent=agent, details=details)
    db.commit()
    db.refresh(task)

    # Sichtbarer Delay
    import asyncio
    import logging
    logger = logging.getLogger("pi-dashboard-2")
    if delay_seconds > 0:
        logger.info(
            f"[transition-delay] Task {task.id[:8]} {old_status!r}->{new_status!r} "
            f"reason={reason!r}: waiting {delay_seconds}s"
        )
        await asyncio.sleep(delay_seconds)

    # Transition finalisieren
    processing_started_at = datetime.utcnow()
    completed_at = datetime.utcnow()
    duration_ms = int((completed_at - processing_started_at).total_seconds() * 1000)
    tr.processing_at = processing_started_at
    tr.completed_at = completed_at
    tr.duration_ms = duration_ms
    _add_history(db, task, "status_changed", agent=agent, details={
        **details,
        "transition_at": transition_at.isoformat(),
        "processing_at": processing_started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
    })
    db.commit()
    db.refresh(task)
    return task


# ------------------------------------------------------------ PHASE 1: TRIAGE -> GO (CIO Review) ------------------------------------------------------------

class TriageApproveBody(BaseModel):
    agent: str = Field("CIO", description="Wer hat approved (z.B. 'CIO', 'system')")
    note: Optional[str] = None

@router.post("/tasks/{task_id}/triage-approve")
async def triage_approve(task_id: str, body: TriageApproveBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO approved: Triage -> GO (mit 5s-Verzoegerung)."""
    t = _get_task(db, task_id)
    if t.status != "triage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'triage'")
    await _set_status_with_delay(db, t, "todo", body.agent, "cio_triage_approved", delay_s=5.0, note=body.note)
    return {"ok": True, "task_id": task_id, "new_status": "todo", "agent": body.agent, "delay_s": 5.0}


class TriageRejectBody(BaseModel):
    agent: str = "CIO"
    reason: str = Field(..., min_length=1, description="Feedback fuer User")

@router.post("/tasks/{task_id}/triage-reject")
def triage_reject(task_id: str, body: TriageRejectBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO rejected: bleibt in Triage mit Feedback. (Status bleibt 'triage', History dokumentiert Reject.)"""
    t = _get_task(db, task_id)
    if t.status != "triage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'triage'")
    _add_history(db, t, "triage_rejected", agent=body.agent, details={"reason": body.reason})
    db.commit()
    db.refresh(t)
    return {"ok": True, "task_id": task_id, "status": "triage", "reason": body.reason, "agent": body.agent}


# ------------------------------------------------------------ AUTO-TRIAGE: CIO bewertet automatisch (Live-Modus) ------------------------------------------------------------

def _check_cio_heuristic(db: Session, t: Task) -> dict:
    """CIO-Heuristik: prueft ob Task OK fuer GO ist.

    User-Direktive 16.06.2026: 4 Kriterien werden geprueft:
      1. Title/Description vollstaendig (ausfuehrlich genug, Aufgabe + Ergebnis klar)
      2. Verschlechterung des Prozess-Ergebnisses? (Widerspruch zum Zweck)
      3. Architektur/OpenBrain-Konsistenz (Standardvorgaben)
      4. Interne Widersprueche in der Anforderung

    Returns: {
        "ok": bool,
        "issues": [...],
        "questions": [...]
    }

    RACI:
      R = CIO (fuer Pruefung verantwortlich)
      A = CIO (fuer Freigabe verantwortlich)
      C = themenabhaengig (z.B. PI_Security bei Security-Themen)
      I = CEOdigital (wird informiert)
    """
    issues = []
    questions = []

    # === 1. Title-Check ===
    if not t.title or len(t.title) < 10:
        issues.append({
            "title": "Titel zu kurz oder fehlt",
            "description": (
                "Der Titel des Tasks ist die wichtigste Information, um den Task spaeter "
                "wiederzufinden und zu verstehen. Ein guter Titel beschreibt die KERN-Aufgabe in 5-15 Worten "
                "und beantwortet die Frage 'Was soll konkret gemacht werden?'. "
                f"Aktuell hat der Titel nur {len(t.title or '')} Zeichen (Minimum: 10)."
            ),
            "suggestions": [
                "Formuliere den Titel als Aufgabe: 'Implementiere X' / 'Fixe Bug Y' / 'Refactor Z'",
                "Verwende konkrete Substantive statt generischer Woerter ('User-Authentifizierung' statt 'Auth')",
                "Inkludiere den scope: 'Backend', 'Frontend', 'API', 'DB' wenn relevant",
                "Beispiel: 'Implementiere OAuth2-Login mit Google Provider' (51 Zeichen) statt 'Auth machen' (11 Zeichen)",
            ],
            "recommendation": (
                "Schreibe den Titel als konkrete Aufgabe mit Scope-Indikator. "
                "Beispiel: 'Refactor User-Profile-API: Pagination + Filter implementieren'"
            ),
        })

    # === 2. Description-Check ===
    desc_len = len(t.description or "")
    if desc_len < 50:
        issues.append({
            "title": "Description fehlt oder zu kurz",
            "description": (
                "Die Description ist der Ort, wo Erwartungen, Akzeptanzkriterien, Edge-Cases und "
                "technische Constraints dokumentiert werden. Ohne ausreichende Description weiss der "
                "Worker nicht, WAS genau implementiert werden soll und der CIO/Tester kann nicht pruefen, "
                "OB die Implementation korrekt ist. Aktuell: " + str(desc_len) + " Zeichen (Minimum: 50, ideal: 200+)."
            ),
            "suggestions": [
                "Strukturierte Description: '**Ziel:** ... **Akzeptanz:** ... **Edge-Cases:** ...'",
                "Konkrete Beispiele: Input/Output, Vorher/Nachher, Test-Cases",
                "Verweise auf existierenden Code (Dateien, Funktionen) wenn relevant",
                "Liste der Constraints: muss mit X kompatibel sein, darf Y nicht brechen, etc.",
                "Beispiel: 'OAuth2-Login via Google. Redirect zu /dashboard nach Auth. CSRF-Token in Cookie. "
                "Test mit User aus staging-DB. Bestehender Code in auth/google.py erweitern.'",
            ],
            "recommendation": (
                "Schreibe die Description als 3-Absatz-Struktur: 1) Was soll erreicht werden, "
                "2) Wie soll es umgesetzt werden (technische Hinweise), 3) Wann ist es fertig (Akzeptanz). "
                "Mindestens 200 Zeichen."
            ),
        })

    # === 3. assigned_role Check ===
    # Fix (User-Direktive 18.06.2026): assigned_role wird NICHT mehr als Heuristik-Kriterium
    # abgefragt, weil die SOP-Engine es pro Step setzt (Step 0=CIO, Step 1=CIO, Step 2=pi-coder,
    # Step 3=pi-tester, Step 4=CIO). Waehrend Triage ist assigned_role absichtlich None.
    # Der Frage-Block ist obsolet und wurde entfernt.

    # === 4. success_criteria Check ===
    sc = t.success_criteria or []
    if isinstance(sc, str):
        try:
            sc = json.loads(sc)
        except Exception:
            sc = []
    if not sc or len(sc) < 1:
        questions.append({
            "title": "Welche konkreten Erfolgskriterien soll der Task erfuellen?",
            "description": (
                "Ohne Erfolgskriterien kann der Worker nicht wissen, wann der Task 'fertig' ist, und der "
                "Tester kann nicht objektiv pruefen, ob der Task korrekt umgesetzt wurde. Die Erfolgskriterien "
                "sind die 'Definition of Done' -- sie beantworten die Frage 'Wie wissen wir, dass es funktioniert?'. "
                "Mindestens 1 Kriterium noetig, ideal: 1-3 konkrete, pruefbare Items."
            ),
            "suggestions": [
                "Testbar formulieren: 'X funktioniert' statt 'X ist gut'",
                "Pro Kriterium eine Checkbox-Frage: 'Wurde X in Y integriert?' (ja/nein)",
                "Beispiel-Kriterien: 'Login funktioniert mit Google-OAuth', "
                "'Redirect nach /dashboard nach erfolgreichem Login', "
                "'CSRF-Token wird in Cookie gespeichert', "
                "'Bestehender Test in tests/test_auth.py laeuft gruen'",
                "Verwende GIVEN-WHEN-THEN Format: 'GIVEN X WHEN Y THEN Z'",
            ],
            "recommendation": (
                "Schreibe 1-3 testbare Kriterien als Bullet-Points. "
                "Beispiel: 'User kann sich mit Google einloggen', "
                "'Bestehende Unit-Tests laufen alle gruen', "
                "'Coverage fuer auth.py > 80%'. "
                "Diese Kriterien werden 1:1 als Checkliste im Detail-Panel angezeigt."
            ),
        })

    # === 5. Conflict-Keywords Check ===
    full_text = f"{t.title or ''} {t.description or ''}".lower()
    # ACHTUNG: 'todo' ist der interne DB-Status-Key (Phase GO) und kommt in
    # vielen User-Texten vor (z.B. 'no_todos', 'in_todo_phase'). NICHT als
    # Konflikt-Keyword pruefen! Stattdessen nur 'TODO:' (mit Doppelpunkt) als
    # Code-Marker pruefen. Fix (User-Direktive 18.06.2026).
    #
    # BUGFIX 22.06.2026: Wortgrenzen (re.search mit \b) verhindern False-Positives
    # wie 'sichtbar' -> 'tba' (User-Direktive Test mit Task 13b322a2b926).
    conflict_keywords = ["todo:", "tbd", "??", "fixme", "klären", "unbekannt", "???", "tba", "[todo]"]
    for kw in conflict_keywords:
        keyword_found = _conflict_keyword_matches(kw, full_text)
        if keyword_found:
            kw_label = {
                "todo:": "TODO (Code-Marker fuer 'noch zu tun')",
                "tbd": "TBD (To Be Determined)",
                "??": "Ungeloeste Fragezeichen",
                "fixme": "FIXME (bekannter Bug-Marker)",
                "klären": "Offene Klaerung",
                "unbekannt": "Unbekannt",
                "???": "Mehrere offene Fragen",
                "tba": "TBA (To Be Announced)",
                "[todo]": "TODO (Code-Marker fuer 'noch zu tun')",
            }.get(kw, kw)
            issues.append({
                "title": f"Konflikt-Keyword '{kw}' in Title/Description gefunden",
                "description": (
                    f"Das Keyword '{kw_label}' deutet darauf hin, dass der Task noch unvollstaendig "
                    f"definiert ist. Solche Marker fuehren zu Verwirrung beim Worker (was soll er tun, "
                    f"wenn er auf 'TODO' stoesst -- ueberspringen? raten? fragen?) und beim Tester "
                    f"(was soll er pruefen, wenn unklar ist, was implementiert werden soll?). "
                    f"Ausserdem verstoessen sie gegen unsere OpenBrain-Vorgabe 'Tasks muessen selbsterklaerend sein'."
                ),
                "suggestions": [
                    f"Ersetze '{kw}' durch die konkrete Information (z.B. statt 'TODO: was passieren soll' -> 'Was passieren soll: User wird auf /dashboard weitergeleitet')",
                    "Entferne FIXME-Marker -- entweder den Bug fixen oder eine separate Task dafuer anlegen",
                    "Loese offene Fragen SELBST: lies existierenden Code, frage im OpenBrain, oder recherchiere",
                    "Verwende statt 'tbd' den konkreten Default-Wert (z.B. 'timeout=30s (Standard-Default)')",
                ],
                "recommendation": (
                    f"Gehe durch den Task und ersetze JEDES '{kw}' durch die konkrete Information. "
                    f"Der Task sollte nach dem Cleanup selbsterklaerend sein -- ein Worker ohne Kontext "
                    f"sollte genau wissen, was zu tun ist. "
                    f"Beispiel: 'TODO: Auth-Provider waehlen' -> 'Auth-Provider: Google OAuth2 (laut Architektur-Entscheidung PI-DASHBOARD-12)'"
                ),
            })
            break

    # === 6. Priority-Check ===
    if t.priority is None or t.priority < 0 or t.priority > 100:
        issues.append({
            "title": "Priority nicht gesetzt oder ausserhalb 0-100",
            "description": (
                "Die Priority bestimmt die Reihenfolge der Bearbeitung. 0-24 = niedrig, 25-49 = normal, "
                "50-74 = hoch, 75-89 = sehr hoch, 90-100 = NOTFALL (mit Auto-Eskalation). "
                "Ohne korrekte Priority weiss der Operator nicht, ob dieser Task vor anderen kommt. "
                f"Aktueller Wert: {t.priority}"
            ),
            "suggestions": [
                "50 (Standard) fuer die meisten Implementations-Tasks",
                "75-89 fuer wichtige Features, die vor anderen fertig sein muessen",
                "90-100 (NOTFALL) nur fuer Produktions-Bugs / Blocker",
                "25-49 fuer nice-to-have, low-priority Refactorings",
                "10-24 fuer 'irgendwann mal' Aufgaben",
            ],
            "recommendation": (
                "Setze die Priority auf 50 (Standard) wenn du dir unsicher bist. "
                "Der User kann die Priority jederzeit im Detail-Panel ueber den Slider anpassen."
            ),
        })

    # === 7. Architektur-Konsistenz (OpenBrain-Standardvorgaben) ===
    # User-Direktive 16.06.2026: "Widerspricht die Umsetzung den Entwicklungs- und
    # Architekturvorgaben aus dem openbrain?"
    arch_issues = _check_architecture_alignment(db, t)
    issues.extend(arch_issues)

    # === 8. Anforderungs-Widersprueche (interne Konsistenz) ===
    # User-Direktive 16.06.2026: "Sind Widersprueche in der Anforderung zu finden?"
    consistency_issues = _check_requirement_consistency(t)
    issues.extend(consistency_issues)

    return {
        "ok": len(issues) == 0 and len(questions) == 0,
        "issues": issues,
        "questions": questions,
    }


# === Kriterium 7: Architektur-Konsistenz (OpenBrain-Standardvorgaben) ===
# User-Direktive 16.06.2026: "Widerspricht die Umsetzung den Entwicklungs- und
# Architekturvorgaben aus dem openbrain?"
def _check_architecture_alignment(db: Session, t: Task) -> list:
    """Prueft die Task-Description gegen persistente Architecture-Rules.

    Strategie: Konflikt nur bei EXPLIZITER Negation der Standardvorgabe.
    Z.B. "kein Microservices" oder "nicht SOA" = Verstoss.
    Bloßes Erwähnen eines Architektur-Keywords (z.B. "Microservices verwenden")
    ist KEIN Konflikt, sondern Compliance.

    Returns: Liste von Issue-Dicts
    """
    from ..models.architecture_rule import ArchitectureRule
    issues = []
    if not t.description:
        return issues
    desc_lower = t.description.lower()
    try:
        rules = db.execute(_select(ArchitectureRule).where(ArchitectureRule.is_active == True)).scalars().all()
    except Exception:
        return issues
    for rule in rules:
        if not rule.description:
            continue
        rule_lower = rule.description.lower()
        # Extrahiere die wichtigsten 2-3 Schluesselwoerter der Rule (>= 5 Zeichen, keine Stoppwoerter)
        # Vermeide zu kurze/generische Woerter wie "jeder", "soll", etc.
        ARCH_STOPWORDS = _STOPWORDS | {"regel", "vorgabe", "standard", "beispiel", "eigen", "eigenstaendig", "eigenständig", "auch", "sowie", "kein", "keine", "keinen", "vermeiden", "sollte", "muss", "darf", "wird"}
        keywords = [w for w in re.findall(r"\b[a-z]{5,}\b", rule_lower) if w not in ARCH_STOPWORDS][:5]
        for kw in keywords:
            # Suche nach EXPLIZITER Negation des Keywords in der Description
            # Pattern: "kein <kw>", "keine <kw>", "keinen <kw>", "nicht <kw>", "<kw> vermeiden", "<kw> ablehnen", "ohne <kw>"
            negation_patterns = [
                f"kein {kw}", f"keine {kw}", f"keinen {kw}", f"keinem {kw}",
                f"nicht {kw}", f"nicht mit {kw}", f"nicht in {kw}",
                f"{kw} vermeiden", f"{kw} ablehnen", f"{kw} ignorieren",
                f"ohne {kw}", f"gegen {kw}", f"weg von {kw}",
                f"kein {kw} ", f"kein-{kw}",
            ]
            is_negated = any(neg in desc_lower for neg in negation_patterns)
            if is_negated:
                severity_note = "PFLICHT-VERLETZUNG" if rule.severity == "must" else "Empfehlung"
                issues.append({
                    "title": f"Architektur-Konflikt: {rule.name}",
                    "description": (
                        f"Deine Task-Description verneint explizit '{kw}', was im Konflikt mit unserer "
                        f"OpenBrain-Standardvorgabe steht. "
                        f"Regel: {rule.description} "
                        f"(Severity: {rule.severity}, {severity_note})"
                    ),
                    "suggestions": [
                        f"Pruefe, ob die Verneinung wirklich noetig ist oder ob du die Standardvorgabe doch nutzen kannst",
                        f"Falls die Regel nicht passt: dokumentiere im OpenBrain, warum du hier abweichen willst",
                        f"Frage ggf. den PI_Security Worker (Consulted) bei Security-Regeln oder den CIO bei Architektur-Fragen",
                    ],
                    "recommendation": (
                        f"Pruefe explizit, ob die Verneinung von '{kw}' wirklich noetig ist. "
                        f"Im Zweifel: halte dich an die Standardvorgabe '{rule.name}'."
                    ),
                    "openbrain_ref": rule.source_ref or rule.id,
                    "severity": rule.severity,
                })
                break  # Pro Rule nur 1 Issue melden
    return issues


# === Kriterium 8: Anforderungs-Widersprueche (interne Konsistenz) ===
# User-Direktive 16.06.2026: "Sind Widersprueche in der Anforderung zu finden?"
def _check_requirement_consistency(t: Task) -> list:
    """Prueft die Task-Description auf interne logische Widersprueche.

    Returns: Liste von Issue-Dicts
    """
    issues = []
    if not t.description:
        return issues
    desc = t.description.lower()
    title = (t.title or "").lower()

    # Liste von bekannten Widerspruchs-Paaren
    contradiction_pairs = [
        (["oauth", "openid"], ["lokal", "passwort"], "Auth-Konflikt: OAuth/OpenID widerspricht lokaler Passwort-Auth"),
        (["sql", "postgres"], ["nosql", "mongodb", "redis"], "DB-Konflikt: SQL widerspricht NoSQL"),
        (["synchron", "sync"], ["async", "asynchron"], "Concurrency-Konflikt: synchron vs. asynchron"),
        (["monolith"], ["microservice"], "Architektur-Konflikt: Monolith vs. Microservices"),
        (["client-side", "clientseitig"], ["server-side", "serverseitig"], "Wo soll die Logik laufen?"),
        (["push"], ["pull"], "Push vs. Pull Pattern"),
        (["websocket"], ["polling"], "Realtime-Pattern: WebSocket vs. Polling"),
        (["relational"], ["document"], "DB-Typ: Relational vs. Document-Store"),
        (["serverless"], ["langer prozess", "long-running"], "Serverless nicht fuer long-running"),
        (["eigenstaendig", "eigenständig"], ["shared", "geteilt"], "Architektur-Konflikt: eigenstaendig vs. shared"),
    ]
    found_contradictions = []
    for group_a, group_b, desc_text in contradiction_pairs:
        has_a = any(kw in desc or kw in title for kw in group_a)
        has_b = any(kw in desc or kw in title for kw in group_b)
        if has_a and has_b:
            found_contradictions.append(desc_text)
    if found_contradictions:
        for c in found_contradictions:
            issues.append({
                "title": f"Anforderungs-Widerspruch: {c}",
                "description": (
                    f"Deine Task-Description enthaelt Widersprueche. "
                    f"Konkrete Konflikte: {c}. "
                    f"Ein Worker, der diese Aufgabe unklar erhaelt, wird entweder falsch implementieren "
                    f"oder Endlosschleifen mit Rueckfragen erzeugen."
                ),
                "suggestions": [
                    "Loese den Widerspruch, indem du eine der beiden Optionen explizit ausschliesst",
                    "Beispiel: 'NICHT lokal, sondern OAuth2' oder 'NICHT Polling, sondern WebSocket'",
                    "Frag den User (im Kommentar), welche der Optionen gilt",
                ],
                "recommendation": (
                    "Pruefe, welche der beiden Optionen tatsaechlich gilt, und dokumentiere das explizit. "
                    "Ein klarer Task hat keine 'entweder/oder'-Formulierungen."
                ),
            })
    # Pruefe auf ECHTE Widersprueche: "nicht X, aber X" / "nicht X, aber Y wo X..." im SELBEN Satz
    # Vorher: feuerte bei JEDEM "nicht" + "aber" irgendwo in der Description.
    # Jetzt: nur wenn die Negation und das "aber" nahe beieinander stehen UND das
    # negierte Substantiv nach dem "aber" wirklich als POSITIV vorkommt (nicht in
    # einer "wird nicht X" Konstruktion).
    import re
    if desc:
        # Suche Saetze mit "nicht" UND "aber"
        sentences = re.split(r'(?<=[.!?])\s+|\n+', desc)
        for sentence in sentences:
            sent_lower = sentence.lower()
            if "nicht " in sent_lower and " aber " in sent_lower:
                # Extrahiere das negierte Substantiv nach "nicht" (z.B. "nicht X" -> "X")
                m = re.search(r"nicht\s+([a-zäöüß\-]+)", sent_lower)
                if m:
                    negated = m.group(1)
                    after_aber = sent_lower.split(" aber ", 1)[-1]
                    # Nur kurze Negationen (echte Widersprueche), nicht "nicht nur" etc.
                    if len(negated) <= 3:
                        continue
                    # Pruefe, ob das negierte Wort nach "aber" wirklich POSITIV vorkommt
                    # (= ohne "nicht" / "kein" davor). Wenn "nicht X" auch nach "aber" steht,
                    # ist es kein Widerspruch, sondern eine konsistente Negation.
                    # Beispiel: "User waehlt X aus, aber Y wird nicht Z" -> nach "aber" steht "nicht Z"
                    # -> das ist KEIN Widerspruch, sondern eine berechtigte Aussage.
                    if f"nicht {negated}" in after_aber or f"kein {negated}" in after_aber or f"keine {negated}" in after_aber:
                        # Konsistente Negation, kein Widerspruch
                        continue
                    # Negation muss als positive Behauptung im "nach 'aber'" Teil stehen
                    if negated in after_aber:
                        issues.append({
                            "title": "Komplexe Negation in der Description",
                            "description": (
                                f"Im Satz: \"{sentence.strip()}\" wird etwas negiert "
                                f"('{negated}') und nach 'aber' wird es wieder positiv erwaehnt. "
                                "Das ist ein echter Widerspruch, der vom Worker nicht aufgeloest "
                                "werden kann, ohne den Task zuerst zu klaeren."
                            ),
                            "suggestions": [
                                "Formuliere die Anforderung klar: 'X ist immer A' oder 'X ist nie A'",
                                "Wenn es eine Ausnahme gibt: 'X ist A, ausser wenn Bedingung B erfuellt'",
                            ],
                            "recommendation": (
                                "Vereinfache die Anforderung in eine klare, nicht-widersprüchliche Form."
                            ),
                        })
                        # Nur ein Issue pro Description, nicht mehrere
                        break
    return issues


# === RACI-Helper fuer Triage-Phase ===
# User-Direktive 16.06.2026:
#   R = CIO  (fuehrt die Pruefung durch)
#   A = CIO  (gibt die Freigabe)
#   C = themenabhaengig (z.B. pi-security bei Security, pi-coder bei Architektur, etc.)
#   I = CEOdigital (wird ueber das Ergebnis informiert)
def _build_raci_for_task(t: Task, heuristic_result: dict) -> dict:
    """Baut die RACI-Matrix fuer einen Task basierend auf seinem Inhalt.

    Themen-Detection:
      - Security/Auth/Password/Verschluesselung -> C = pi_security
      - Architecture/Microservices/SOA -> C = pi_coder (bzw. CIO selbst)
      - Testing/Test/Coverage -> C = pi_tester
      - Code-Review/Refactor -> C = pi_reviewer
      - Bug/Fix/Defect -> C = pi_fixer
      - Default -> C = (keiner)
    """
    desc = (t.description or "").lower()
    title = (t.title or "").lower()
    text = f"{title} {desc}"

    # Security-Themen
    if any(kw in text for kw in ["security", "auth", "password", "verschlüsselung", "encryption", "oauth", "jwt", "token", "xss", "csrf", "sql-injection", "berechtigung"]):
        c = "pi_security"
    # Architecture-Themen
    elif any(kw in text for kw in ["architektur", "architecture", "microservice", "soa", "design", "konzept"]):
        c = "pi_coder"
    # Testing-Themen
    elif any(kw in text for kw in ["test", "coverage", "pytest", "jest", "unit-test", "e2e"]):
        c = "pi_tester"
    # Review-Themen
    elif any(kw in text for kw in ["review", "refactor", "code-quality", "clean-code"]):
        c = "pi_reviewer"
    # Bug-Fix-Themen
    elif any(kw in text for kw in ["bug", "fix", "defect", "fehler", "regression"]):
        c = "pi_fixer"
    else:
        c = None

    return {
        "R": "CIO",          # Responsible: prueft
        "A": "CIO",          # Accountable: gibt Freigabe
        "C": c or "(keiner)", # Consulted: themenabhaengig
        "I": "CEOdigital",   # Informed: wird ueber Ergebnis benachrichtigt
        "criteria_checked": [
            "1. Description ausfuehrlich genug (Aufgabe + Ergebnis klar)",
            "2. Keine Verschlechterung des Prozess-Ergebnisses",
            "3. Konsistent mit OpenBrain-Architekturvorgaben",
            "4. Keine Widersprueche in der Anforderung",
        ],
        "auto_approved": len(heuristic_result.get("issues", [])) == 0 and len(heuristic_result.get("questions", [])) == 0,
    }


# === Similarity-Check: verhindert Doppel-Start thematisch identischer Tasks ===
# User-Direktive 16.06.2026: "der CIO hätte nicht zwei mal das gleiche nicht starten dürfen"
#
# Vor jedem Auto-Approve pruefen wir, ob es im gleichen Projekt einen OFFENEN Task
# (Status != done) gibt, der eine hohe Titel-/Beschreibungsaehnlichkeit hat.
# Wenn ja, wird der aktuelle Task auf 'block' gesetzt mit der Frage:
# "Es gibt bereits einen aehnlichen offenen Task {id} -- soll dieser als Sub-Task
# angelegt oder der bestehende erweitert werden?"

import re
from difflib import SequenceMatcher
from sqlalchemy import select as _select
from ..models.task import Task as _Task


def _normalize_text(s: str) -> str:
    """Normalisiert Text fuer Similarity-Vergleich: lowercase, nur Wörter, keine Stoppwörter."""
    if not s:
        return ""
    s = s.lower()
    # Nur alphanumerische Zeichen
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # Doppelte Whitespaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Deutsche + englische Stoppwörter, die bei der Similarity-Berechnung rausgefiltert werden
_STOPWORDS = {
    # Deutsch
    "der", "die", "das", "ein", "eine", "und", "oder", "aber", "mit", "von", "aus", "auf",
    "fuer", "f\u00fcr", "fuer", "ueber", "\u00fcber", "ueber", "ueber", "ueber", "ueber",
    "soll", "sollte", "sollen", "werden", "wird", "wurde", "worden", "kann", "kannst",
    "bei", "nach", "vor", "seit", "trotz", "w\u00e4hrend", "waehrend",
    "ist", "sind", "war", "hat", "haben", "hatte", "muss", "muessen",
    "alle", "jeder", "jede", "jedes", "diese", "dieser", "diesem", "dieses",
    "auch", "noch", "schon", "mehr", "wenn", "dann", "weil", "denn", "weil",
    "wie", "was", "wer", "wem", "wen", "wann", "wo", "womit", "wodurch",
    # Englisch
    "the", "a", "an", "and", "or", "but", "for", "from", "to", "in", "on", "at", "by",
    "with", "without", "should", "must", "will", "would", "can", "could", "may", "might",
    "is", "are", "was", "were", "has", "have", "had", "do", "does", "did",
    "all", "any", "some", "this", "that", "these", "those", "their", "its",
    "be", "been", "being", "which", "what", "who", "whom", "where", "when", "how",
    "of", "as", "into", "out", "up", "down", "then", "than",
}


def _significant_words(s: str) -> set:
    """Extrahiert signifikante Woerter: >= 4 Zeichen, keine Stoppwoerter, normalisiert."""
    norm = _normalize_text(s)
    return {
        w for w in norm.split()
        if len(w) >= 4 and w not in _STOPWORDS
    }


def _word_overlap_ratio(text1: str, text2: str) -> float:
    """Berechnet Jaccard-Score auf signifikanten Woertern (>= 4 Zeichen, ohne Stoppwoerter)."""
    words1 = _significant_words(text1)
    words2 = _significant_words(text2)
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


def _similarity_score(t1: str, t2: str) -> float:
    """Kombinierter Score: 50% Word-Overlap (signifikante Woerter) + 50% SequenceMatcher.

    Threshold-Tuning:
    - Selektieren-Button vs Selektieren-Button: ~50-60% (sollte erkannt werden)
    - PostgreSQL vs Login-Button: ~10-15% (sollte NICHT erkannt werden)
    - Threshold 0.30 trifft die richtige Balance.
    """
    norm1 = _normalize_text(t1)
    norm2 = _normalize_text(t2)
    if not norm1 or not norm2:
        return 0.0
    seq_score = SequenceMatcher(None, norm1, norm2).ratio()
    overlap = _word_overlap_ratio(norm1, norm2)
    # Gewichtung: 50% Word-Overlap (signifikante Wörter), 50% Sequence
    return 0.5 * seq_score + 0.5 * overlap


# Sehr generische Wörter, die KEINEN thematischen Match ausmachen
# (z.B. "Backend implementieren" matched praktisch jeden Task)
_GENERIC_WORDS = {
    "backend", "frontend", "system", "modul", "komponente", "komponenten",
    "implementieren", "umsetzen", "realisieren", "machen", "tun", "erstellen",
    "task", "tasks", "aufgabe", "aufgaben", "funktion", "funktionen",
    "feature", "features", "code", "logik", "test", "tests",
    "arbeit", "arbeiten", "schritt", "schritte", "schritten", "phase", "phasen",
    "allgemein", "generell", "speziell", "konkret", "all",
    "user", "users", "kunde", "kunden", "system",
    "app", "application", "anwendung", "web", "plattform",
    "code", "script", "file", "files", "datei", "dateien",
    "verwenden", "nutzen", "erweitern", "ergaenzen", "anpassen", "aendern",
    "erstellen", "bauen", "machen",
}


def _has_substantive_match(text1: str, text2: str, min_substantive: int = 2) -> bool:
    """Prueft, ob mindestens N substantielle (nicht-generische) Wörter matchen.

    Verhindert False-Positives bei Tasks, die nur generische Wörter
    gemeinsam haben (z.B. "Backend implementieren").
    """
    sig1 = {w for w in _significant_words(text1)} - _GENERIC_WORDS
    sig2 = {w for w in _significant_words(text2)} - _GENERIC_WORDS
    intersection = sig1 & sig2
    return len(intersection) >= min_substantive


def find_related_open_tasks(
    db: Session, current_task: _Task,
    similarity_threshold: float = 0.25,
    limit: int = 3,
) -> list[dict]:
    """Findet thematisch verwandte OFFENE Tasks im gleichen Projekt.

    Strategie: Title-Only-Vergleich (Titel enthaelt die wichtigsten Keywords).
    Description ist oft zu lang und verwaessert den Score.

    Returns: Liste von {task, score, reason}-Dicts, sortiert nach Score DESC.
    OFFEN = Status nicht 'done' (also in Bearbeitung, wartend, blockiert, etc.)
    Ausgeschlossen: aktueller Task selbst und Sub-Tasks.
    """
    if not current_task.project_id:
        return []

    open_statuses = ["triage", "todo", "in_progress", "review", "block", "waiting", "rueckfrage", "warten"]
    candidates = list(db.execute(
        _select(_Task).where(
            _Task.project_id == current_task.project_id,
            _Task.id != current_task.id,
            _Task.parent_id.is_(None),  # nur Top-Level-Tasks
            _Task.status.in_(open_statuses),
        ).limit(50)
    ).scalars())

    matches = []
    # Title-Only-Vergleich (Titel ist konzentriert, Description oft zu lang)
    title1 = current_task.title or ""
    for cand in candidates:
        title2 = cand.title or ""
        score = _similarity_score(title1, title2)
        # Zusatz-Bedingung: mindestens 2 substantielle Wörter müssen matchen
        # (verhindert False-Positives bei nur-generischen Wort-Matches)
        if score >= similarity_threshold and _has_substantive_match(title1, title2, min_substantive=2):
            # Reason: erklaerende Hinweise
            reason_parts = [f"Title-Score {score:.0%}"]
            if cand.priority and cand.priority >= 90:
                reason_parts.append(f"NOTFALL-Prio {cand.priority}")
            if cand.assigned_role:
                reason_parts.append(f"Worker: {cand.assigned_role}")
            matches.append({
                "task": cand,
                "score": round(score, 3),
                "reason": " * ".join(reason_parts),
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:limit]


class TriageEvaluateBody(BaseModel):
    agent: str = "CIO"
    auto_mode: bool = True

@router.post("/tasks/{task_id}/triage-evaluate")
def triage_evaluate(task_id: str, body: TriageEvaluateBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO Triage Review: nutzt die 'cio-triage-review' SOP aus der DB.

    User-Direktive 16.06.2026: Die Triage-Logik wird deklarativ in der SOP definiert.
    Die App nutzt die SOP, um klare Anweisungen auszuführen.
    Aktuell wird die 'CIO Triage Review (4 Kriterien)' SOP verwendet, die folgende
    Schritte ausführt: Title-Check, Description-Check, Success-Criteria-Check,
    Architektur-Alignment, Requirement-Consistency, Entscheidung.

    - OK  -> TRIAGE -> GO (auto-approve)
    - ISSUES -> TRIAGE -> RUECKFRAGE mit Details
    """
    import json as _json
    from ..models.task import Task as _TaskModel
    from ..models.sop import SOP, SOPInstance
    from ..services.sop_engine import SOPEngine

    t = _get_task(db, task_id)
    if t.status != "triage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'triage'")

    # 1) SOP "CIO Triage Review" aus der DB laden
    sop = db.execute(_select(SOP).where(SOP.name == "CIO Triage Review (4 Kriterien)")).scalar_one_or_none()
    if not sop:
        raise HTTPException(500, "SOP 'CIO Triage Review (4 Kriterien)' nicht gefunden. Bitte seed-defaults ausführen.")

    # 2) SOP-Instance anlegen
    instance = SOPInstance(
        sop_id=sop.id,
        task_id=task_id,
        project_id=t.project_id,
        current_step_id=sop.steps[0].id if sop.steps else None,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # 3) Steps ausführen (sync, nicht async -- wir sind im Sync-Endpoint)
    engine = SOPEngine(db)
    step_results = []
    all_issues = []
    while instance.status == "running" and instance.current_step_id:
        step = db.get(SOPStep, instance.current_step_id)
        if not step:
            instance.status = "failed"
            instance.error = "Step not found"
            break
        # Step ausführen (synchron, da wir im sync-Endpoint)
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                # Falls bereits ein Loop laeuft, fuehre synchron aus
                result = engine._execute_action(instance, step)
            else:
                result = loop.run_until_complete(engine._execute_action(instance, step))
        except RuntimeError:
            result = _asyncio.run(engine._execute_action(instance, step))
        # Issue-Tracking: alle Issues sammeln
        if isinstance(result, dict) and result.get("issues_count") is not None:
            # Meta der Instance nach _execute_action erneut lesen
            db.refresh(instance)
            try:
                meta = _json.loads(instance.meta) if instance.meta and isinstance(instance.meta, str) else (instance.meta or {})
            except Exception:
                meta = {}
            for issue in meta.get("triage_issues", []):
                if issue not in all_issues:
                    all_issues.append(issue)
        step_results.append({"step": step.name, "ok": result.get("ok", True), "result": result})
        # Rules evaluieren
        from ..services.sop_engine import SOPEngine as _SE
        next_step_id, _action = _SE.evaluate_rules(engine, instance, step, result)
        if next_step_id is None:
            instance = engine._complete_instance(instance, step, result)
            break
        engine.advance(instance, next_step_id, result)
        db.refresh(instance)

    # 4) Resultat extrahieren
    db.refresh(instance)
    db.refresh(t)
    final_status = t.status
    decision = "approved" if final_status == "todo" else "question"
    meta = t.meta if isinstance(t.meta, dict) else (_json.loads(t.meta) if t.meta else {})

    return {
        "ok": True,
        "task_id": task_id,
        "decision": decision,
        "new_status": final_status,
        "issues": all_issues,
        "questions": [],
        "sop_used": sop.name,
        "sop_instance_id": instance.id,
        "step_results": [{"step": r["step"], "ok": r["ok"]} for r in step_results],
        "raci": meta.get("triage_raci", {}),
    }


# ------------------------------------------------------------ TRIAGE-APPROVE ------------------------------------------------------------

@router.post("/tasks/{task_id}/triage-approve")
def triage_approve(task_id: str, body: TriageEvaluateBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO Triage Review: prueft 4 Kriterien und schiebt Task nach GO oder RUECKFRAGE.

    User-Direktive 16.06.2026: Die Triage-Logik wird deklarativ in der SOP definiert.
    Evaluiert: CIO-Heuristik, Architektur-Alignment, Requirement-Consistency, Entscheidung.

    - OK  -> TRIAGE -> GO (auto-approve)
    - ISSUES -> TRIAGE -> RUECKFRAGE mit Details

    Falls ein **aktives Process-Template** fuer das Projekt existiert, wird der
    erste Edge (von 'start' zum naechsten Knoten) als Transition-Map genutzt.
    D.h. der Template-Designer kann z.B. festlegen, dass der erste Schritt nach
    'block' (Rueckfragen) statt 'todo' fuehrt.

    Speichert CIO-Frage(n) in task.meta["cio_question"].
    """
    t = _get_task(db, task_id)
    if t.status != "triage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'triage'")

    result = _check_cio_heuristic(db, t)
    meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})

    # === Process-Template pruefen: Wenn ein aktives Template existiert, wird der
    # erste Edge (von 'start' zum naechsten Knoten) als Transition-Override genutzt.
    # Designer koennen so z.B. festlegen: Triage -> nach 'block' (Rueckfragen) statt 'todo'.
    from ..models.process_template import ProcessTemplate
    from sqlalchemy import select
    active_template = db.execute(
        select(ProcessTemplate)
        .where(ProcessTemplate.activated_for_project_id == t.project_id)
        .where(ProcessTemplate.is_active == True)
    ).scalar_one_or_none()

    template_target_status = None
    template_used_name = None
    if active_template:
        template_used_name = active_template.name
        start_edge = active_template.get_start_edge()
        if start_edge:
            template_target_status = start_edge.get("target_status")
            # Erlaubte Status-Werte filtern
            valid_statuses = ("triage", "todo", "in_progress", "review", "block", "done", "rueckfrage")
            if template_target_status not in valid_statuses:
                template_target_status = None

    # === Similarity-Check (User-Direktive 16.06.2026) ===
    # Verhindert, dass thematisch identische Tasks beide approved werden.
    # Vor jedem approved-Pfad pruefen, ob ein OFFENER Task mit aehnlichem
    # Titel/Description existiert. Falls ja: Rueckfrage mit "Sub-Task / Erweitern / Separate".
    related_tasks = find_related_open_tasks(db, t, similarity_threshold=0.15)
    if related_tasks:
        top_match = related_tasks[0]
        related_titles = [
            f"{m['task'].id[:8]} (Score {m['score']:.0%}): {m['task'].title[:60]}"
            for m in related_tasks
        ]
        question_text = (
            f"Ähnlicher offener Task existiert bereits: "
            f"{top_match['task'].id} (Score {top_match['score']:.0%}) -- "
            f"'{top_match['task'].title[:80]}'. "
            f"Soll dieser Task (1) als Sub-Task angelegt, "
            f"(2) der bestehende erweitert, oder (3) separat fortgefahren werden?"
        )
        meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})
        meta["cio_question"] = question_text
        meta["cio_question_at"] = datetime.utcnow().isoformat()
        meta["cio_question_related_tasks"] = [
            {"id": m["task"].id, "title": m["task"].title, "score": m["score"], "status": m["task"].status}
            for m in related_tasks
        ]
        meta["cio_question_issues"] = []
        meta["cio_question_questions"] = [{
            "title": "Thematisch verwandter Task existiert bereits",
            "description": question_text,
            "suggestions": [
                f"Sub-Task anlegen: parent_id={related_tasks[0]['task'].id} setzen",
                f"Bestehenden erweitern: '{related_tasks[0]['task'].title}' editieren",
                "Separat fortfahren: explizit bestaetigen, dass es ein anderer Anwendungsfall ist",
            ],
            "recommendation": (
                f"Oeffne Task {related_tasks[0]['task'].id} im Detail-Panel und entscheide: "
                f"Sub-Task / Erweitern / Separate. Verwandte Tasks: " + " | ".join(related_titles)
            ),
        }]
        t.meta = meta
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(t, "meta")
        _set_status(db, t, "rueckfrage", body.agent, "cio_duplicate_detected",
                    question=question_text,
                    related_task_ids=[m["task"].id for m in related_tasks],
                    top_similarity=related_tasks[0]["score"])
        db.commit()
        db.refresh(t)
        return {
            "ok": True,
            "task_id": task_id,
            "decision": "duplicate_detected",
            "new_status": "rueckfrage",
            "question": question_text,
            "related_tasks": [
                {"id": m["task"].id, "title": m["task"].title, "score": m["score"], "status": m["task"].status}
                for m in related_tasks
            ],
        }

    if result["ok"]:
        # Alles OK -> Ziel-Status (Template-Override oder Default 'todo')
        target_status = template_target_status or "todo"
        _set_status(db, t, target_status, body.agent, "cio_auto_approved",
                    issues=result["issues"], questions=result["questions"],
                    auto_mode=body.auto_mode,
                    template_id=active_template.id if active_template else None,
                    template_target_status=template_target_status)
        # RACI bei Triage-Freigabe dokumentieren
        raci = _build_raci_for_task(t, result)
        meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})
        meta.pop("cio_question", None)
        meta.pop("ceo_answer", None)
        meta["triage_raci"] = raci
        t.meta = meta
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(t, "meta")
        db.commit()
        db.refresh(t)
        return {
            "ok": True,
            "task_id": task_id,
            "decision": "approved",
            "new_status": target_status,
            "issues": result["issues"],
            "questions": result["questions"],
            "template_used": template_used_name,
            "raci": raci,
        }
    else:
        # Probleme -> Ziel-Status (Template-Override oder Default 'rueckfrage')
        target_status = template_target_status or "rueckfrage"
        all_items = result["issues"] + result["questions"]
        all_titles = [item["title"] for item in all_items if isinstance(item, dict) and item.get("title")]
        question_text = " | ".join(all_titles) if all_titles else "Unbekanntes Problem"
        meta["cio_question"] = question_text
        meta["cio_question_at"] = datetime.utcnow().isoformat()
        meta["cio_question_issues"] = result["issues"]
        meta["cio_question_questions"] = result["questions"]
        t.meta = meta
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(t, "meta")
        _set_status(db, t, target_status, body.agent, "cio_auto_question",
                    question=question_text, issues=result["issues"], questions=result["questions"],
                    template_id=active_template.id if active_template else None,
                    template_target_status=template_target_status)
        db.commit()
        db.refresh(t)
        return {
            "ok": True,
            "task_id": task_id,
            "decision": "question",
            "new_status": target_status,
            "question": question_text,
            "issues": result["issues"],
            "questions": result["questions"],
            "template_used": template_used_name,
        }


# ------------------------------------------------------------ CEO-ANTWORT ------------------------------------------------------------

class CEOAnswerBody(BaseModel):
    agent: str = "CEO-digital"  # oder 'CEO' (User)
    answer: str = Field(..., min_length=1, description="Antwort des CEO")
    target_status: str = Field("todo", description="Status nach Antwort: 'todo' (re-Triage) oder 'triage' (re-Triage with fix)")

@router.post("/tasks/{task_id}/ceo-answer")
def ceo_answer(task_id: str, body: CEOAnswerBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CEO beantwortet die CIO-Frage. Task wird zurueck in GO (oder Triage) geschoben."""
    t = _get_task(db, task_id)
    if t.status != "rueckfrage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'block'")
    if body.target_status not in ("todo", "triage", "in_progress"):
        raise HTTPException(400, "target_status muss 'todo', 'triage' oder 'in_progress' sein")

    meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})
    meta["ceo_answer"] = body.answer
    meta["ceo_answer_at"] = datetime.utcnow().isoformat()
    meta["ceo_answer_by"] = body.agent
    t.meta = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(t, "meta")

    # Wenn die Description fehlt, mit der Antwort befuellen
    if not t.description or len(t.description) < 50:
        t.description = (t.description or "") + f"\n\n[CEO-Antwort]: {body.answer}"

    _set_status(db, t, body.target_status, body.agent, "ceo_answered_cio_question",
                answer=body.answer, target_status=body.target_status)
    db.commit()
    db.refresh(t)
    return {
        "ok": True,
        "task_id": task_id,
        "new_status": body.target_status,
        "answer": body.answer,
    }


# ------------------------------------------------------------ RECOMMENDATION UMSETZEN ------------------------------------------------------------

class ApplyRecommendationBody(BaseModel):
    agent: str = "CEO"
    recommendation: str = Field(..., min_length=1, description="Die (ggf. editierte) Empfehlung")
    kind: str = Field("description", description="Wo anwenden: 'title' | 'description' | 'general'")
    target_field: Optional[str] = Field(None, description="Optionales spezifisches Feld (z.B. 'title', 'description', 'assigned_role')")
    issue_index: Optional[int] = Field(None, description="Welches Issue/Question (0-basiert)")

@router.post("/tasks/{task_id}/apply-recommendation")
def apply_recommendation(task_id: str, body: ApplyRecommendationBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CEO wendet die (editierte) Empfehlung an.

    Setzt den entsprechenden Task-Inhalt und schiebt den Task zurueck in Triage
    fuer eine Re-Evaluation durch den Auto-Operator.

    Modes:
    - kind='title': Setzt task.title = recommendation (mit Pruefung: min 10 Zeichen)
    - kind='description': Ersetzt oder ergaenzt task.description mit recommendation
    - kind='general': Default: ergaenzt description + setzt status='triage'
    """
    t = _get_task(db, task_id)
    if t.status != "rueckfrage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'block' (um Empfehlung umzusetzen)")

    rec = body.recommendation.strip()
    if not rec:
        raise HTTPException(400, "Empfehlung darf nicht leer sein")

    kind = body.kind
    field = body.target_field or kind

    meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})

    applied = {}

    if field == "title" or kind == "title":
        # Titel ersetzen
        if len(rec) < 10:
            raise HTTPException(400, f"Titel zu kurz ({len(rec)} Zeichen, min 10)")
        old_title = t.title
        t.title = rec
        applied["title"] = {"old": old_title, "new": rec}

    elif field in ("description", "success_criteria", "general") or kind in ("description", "general"):
        # Description: ergaenzen (append) oder ersetzen
        if field == "success_criteria" or (body.target_field == "success_criteria"):
            # Setze success_criteria als JSON-Array
            try:
                sc_items = json.loads(rec)
                if not isinstance(sc_items, list):
                    sc_items = [s.strip() for s in rec.split("\n") if s.strip()]
            except Exception:
                sc_items = [s.strip() for s in rec.split("\n") if s.strip()]
            t.success_criteria = sc_items
            applied["success_criteria"] = sc_items
        else:
            # Description ergaenzen
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            new_block = f"\n\n--- Ergänzt von {body.agent} am {ts} ---\n{rec}"
            t.description = (t.description or "") + new_block
            applied["description_append"] = rec

    elif field == "assigned_role" or body.target_field == "assigned_role":
        # Worker-Rolle setzen
        old_role = t.assigned_role
        t.assigned_role = rec
        applied["assigned_role"] = {"old": old_role, "new": rec}

    else:
        # Default: description append
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        t.description = (t.description or "") + f"\n\n--- {body.agent} am {ts} ---\n{rec}"
        applied["description_append"] = rec

    # Meta-Update: Empfehlung als angewendet markieren
    applied_recommendations = meta.get("applied_recommendations", [])
    applied_recommendations.append({
        "kind": field,
        "recommendation": rec,
        "applied_at": datetime.utcnow().isoformat(),
        "applied_by": body.agent,
        "issue_index": body.issue_index,
    })
    meta["applied_recommendations"] = applied_recommendations

    # Alte cio_question aus Meta entfernen (ist geloest)
    if "cio_question" in meta:
        meta.pop("cio_question", None)
    if "ceo_answer" in meta:
        meta.pop("ceo_answer", None)
    if "cio_question_at" in meta:
        meta.pop("cio_question_at", None)
    if "cio_question_issues" in meta:
        meta.pop("cio_question_issues", None)
    if "cio_question_questions" in meta:
        meta.pop("cio_question_questions", None)
    t.meta = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(t, "meta")

    # Task zurueck in Triage (Auto-Operator bewertet erneut)
    t.updated_at = datetime.utcnow()
    _set_status(db, t, "triage", body.agent, "recommendation_applied",
                applied=applied, kind=field)
    db.commit()
    db.refresh(t)

    return {
        "ok": True,
        "task_id": task_id,
        "new_status": "triage",
        "applied": applied,
        "message": f"Empfehlung angewendet. Task zurück in Triage für Re-Evaluation durch Auto-Operator.",
    }


# ------------------------------------------------------------ PHASE 2: GO (Worker Assignment) ------------------------------------------------------------

class AssignBody(BaseModel):
    agent: str = "CIO"
    worker: str = Field(..., min_length=1, description="Worker-Rolle: pi-coder, pi-tester, pi-reviewer, pi-fixer")
    note: Optional[str] = None

@router.post("/tasks/{task_id}/assign")
def assign_worker(task_id: str, body: AssignBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO weist Task einem Worker zu (GO bleibt in GO, aber assigned_role wird gesetzt)."""
    t = _get_task(db, task_id)
    if t.status != "todo":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'todo'")
    old_role = t.assigned_role
    t.assigned_role = body.worker
    t.updated_at = datetime.utcnow()
    _add_history(db, t, "worker_assigned", agent=body.agent, details={"from": old_role, "to": body.worker, "note": body.note})
    db.commit()
    db.refresh(t)
    return {"ok": True, "task_id": task_id, "worker": body.worker, "previous_worker": old_role}


# ------------------------------------------------------------ PHASE 3: GO -> IN_PROGRESS (Worker starts) ------------------------------------------------------------

class StartBody(BaseModel):
    # === Bugfix 19.06.2026 (Task 921bba39d13f) ===
    # Default-Agent: statt "system" verwenden wir den tatsaechlichen
    # Worker-Agent des Tasks. Das stellt sicher, dass die Performance-Tabelle
    # den Coding-Agent (z.B. "pi-coder") anzeigt und nicht "system".
    # Fallback auf "system" nur, wenn der Task keinen assigned_agent hat.
    agent: Optional[str] = None

@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str, body: StartBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Worker startet Task: GO -> IN_PROGRESS (mit 5 Sekunden Verzoegerung)."""
    t = _get_task(db, task_id)
    if t.status != "todo":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'todo'")
    t.claimed_at = datetime.utcnow()
    # === Bugfix 19.06.2026 (Task 921bba39d13f) ===
    # Agent-Aufloesung: Reihenfolge
    #   1) body.agent (explizit vom Caller)
    #   2) t.assigned_subagent (z.B. "pi-coder", von SOP-Engine gesetzt)
    #   3) t.assigned_role (Worker-Rolle aus SOP)
    #   4) Fallback: "system"
    agent = (
        body.agent
        or t.assigned_subagent
        or t.assigned_role
        or "system"
    )
    await _set_status_with_delay(db, t, "in_progress", agent, "worker_started", delay_s=5.0)
    return {"ok": True, "task_id": task_id, "new_status": "in_progress", "worker": t.assigned_role, "agent": agent, "delay_s": 5.0}


# ------------------------------------------------------------ PHASE 4: IN_PROGRESS -> REVIEW (Worker done) ------------------------------------------------------------

class SubmitReviewBody(BaseModel):
    agent: str = "system"
    note: Optional[str] = None

@router.post("/tasks/{task_id}/submit-review")
async def submit_for_review(task_id: str, body: SubmitReviewBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Worker ist fertig: IN_PROGRESS -> REVIEW (mit 5 Sekunden Verzoegerung)."""
    t = _get_task(db, task_id)
    if t.status != "in_progress":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'in_progress'")
    await _set_status_with_delay(db, t, "review", body.agent, "worker_submitted_for_review", delay_s=5.0, note=body.note)
    return {"ok": True, "task_id": task_id, "new_status": "review", "delay_s": 5.0}


# ------------------------------------------------------------ PHASE 5: REVIEW -> IN_PROGRESS (Tester-Loop) oder -> BLOCK (Tester OK) ------------------------------------------------------------

class TesterRejectBody(BaseModel):
    agent: str = Field("pi-tester", description="Wer hat getestet")
    issues: str = Field(..., min_length=1, description="Beschreibung der gefundenen Probleme")
    note: Optional[str] = None

@router.post("/tasks/{task_id}/tester-reject")
async def tester_reject(task_id: str, body: TesterRejectBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Tester findet Probleme: REVIEW -> IN_PROGRESS (Worker muss fixen, mit 5 Sekunden Verzoegerung)."""
    t = _get_task(db, task_id)
    if t.status != "review":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'review'")
    t.iteration_count = (t.iteration_count or 0) + 1
    await _set_status_with_delay(db, t, "in_progress", body.agent, "tester_rejected", delay_s=5.0, issues=body.issues, note=body.note)
    return {"ok": True, "task_id": task_id, "new_status": "in_progress", "issues": body.issues, "iteration": t.iteration_count, "delay_s": 5.0}


class TesterApproveBody(BaseModel):
    agent: str = "pi-tester"
    note: Optional[str] = None

@router.post("/tasks/{task_id}/tester-approve")
async def tester_approve(task_id: str, body: TesterApproveBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Tester OK: REVIEW -> BLOCK + AUTO-CREATE Freigabe-Task fuer CIO in GO (5 Sekunden Delay)."""
    t = _get_task(db, task_id)
    if t.status != "review":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'review'")
    await _set_status_with_delay(db, t, "rueckfrage", body.agent, "tester_approved", delay_s=5.0, note=body.note)

    # AUTO-CREATE Freigabe-Task fuer CIO
    release_task = Task(
        id=_gen_id(),
        project_id=t.project_id,
        parent_id=t.id,
        title=f"[FREIGABE] {t.title}",
        description=f"CIO Final-Review fuer Task '{t.title}' (ID: {t.id}).\n\n"
                    f"Pruefe ob:\n"
                    f"- Aufgabe tatsaechlich erledigt\n"
                    f"- Ziele erreicht\n"
                    f"- Code-Qualitaet stimmt\n\n"
                    f"Bei OK: setze Original-Task in 'done' UND schliesse diesen Freigabe-Task ebenfalls.\n"
                    f"Bei NICHT OK: setze Original-Task zurueck in 'in_progress' und dokumentiere.",
        priority=t.priority,
        status="todo",
        category="review",
        assigned_role="CIO",
        order=0,
    )
    db.add(release_task)
    db.commit()
    db.refresh(release_task)
    _add_history(db, t, "release_task_created", agent="system",
                 details={"release_task_id": release_task.id, "title": release_task.title})
    db.commit()
    return {
        "ok": True,
        "task_id": task_id,
        "new_status": "rueckfrage",
        "release_task_id": release_task.id,
        "release_task_title": release_task.title,
        "delay_s": 5.0,
    }


# ------------------------------------------------------------ PHASE 6: BLOCK -> DONE (CIO Final Approval) ------------------------------------------------------------

class CIOApproveBody(BaseModel):
    agent: str = "CIO"
    note: Optional[str] = None

@router.post("/tasks/{task_id}/cio-approve")
async def cio_approve(task_id: str, body: CIOApproveBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO approved Final: BLOCK -> DONE (5 Sekunden Delay). Schliesst auch den Freigabe-Task (falls vorhanden)."""
    t = _get_task(db, task_id)
    if t.status != "rueckfrage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'block'")
    await _set_status_with_delay(db, t, "done", body.agent, "cio_final_approved", delay_s=5.0, note=body.note)

    # Finde + schliesse Freigabe-Task
    release_task = db.execute(
        select(Task).where(Task.parent_id == task_id, Task.status == "todo", Task.title.like("[FREIGABE]%"))
    ).scalar_one_or_none()
    release_task_id = None
    if release_task:
        _set_status(db, release_task, "done", "system", "release_task_completed_via_parent_done",
                    parent_task_id=task_id, parent_status="done")
        db.commit()
        db.refresh(release_task)
        release_task_id = release_task.id

    return {
        "ok": True,
        "task_id": task_id,
        "new_status": "done",
        "release_task_id": release_task_id,
        "delay_s": 5.0,
    }


class CIORejectBody(BaseModel):
    agent: str = "CIO"
    reason: str = Field(..., min_length=1, description="Grund fuer Reject")
    target_status: str = Field("in_progress", description="Status nach Reject: 'in_progress' oder 'todo'")

@router.post("/tasks/{task_id}/cio-reject")
async def cio_reject(task_id: str, body: CIORejectBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """CIO rejects Final: BLOCK -> in_progress (oder todo) mit 5 Sekunden Delay. Schliesst Freigabe-Task als done."""
    t = _get_task(db, task_id)
    if t.status != "rueckfrage":
        raise HTTPException(400, f"Task is in status '{t.status}', expected 'block'")
    if body.target_status not in ("in_progress", "todo"):
        raise HTTPException(400, "target_status muss 'in_progress' oder 'todo' sein")

    await _set_status_with_delay(db, t, body.target_status, body.agent, "cio_final_rejected", delay_s=5.0, reason=body.reason)

    # Schliesse Freigabe-Task
    release_task = db.execute(
        select(Task).where(Task.parent_id == task_id, Task.status == "todo", Task.title.like("[FREIGABE]%"))
    ).scalar_one_or_none()
    release_task_id = None
    if release_task:
        _set_status(db, release_task, "done", "system", "release_task_completed_via_reject",
                    parent_task_id=task_id, parent_status=body.target_status, reason=body.reason)
        db.commit()
        db.refresh(release_task)
        release_task_id = release_task.id

    return {
        "ok": True,
        "task_id": task_id,
        "new_status": body.target_status,
        "reason": body.reason,
        "release_task_id": release_task_id,
        "delay_s": 5.0,
    }


# ------------------------------------------------------------ REOPEN: Task zurueck in Triage (Soft-Reset) ------------------------------------------------------------

class ReopenBody(BaseModel):
    agent: str = "CEO"
    reason: str = Field("Wieder in Triage", min_length=1, description="Warum wird der Task zurueck in Triage gestellt?")
    reset_iteration: Optional[bool] = Field(True, description="Iteration-Counter zuruecksetzen (Standard-Workflow von vorne)")

@router.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: str, body: ReopenBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Task zurueck in Triage stellen (Soft-Reset, loescht NICHT).

    User-Direktive 15.06.2026: Statt Tasks hart zu loeschen, sollen sie ueber
    die Re-Triage den Standard-Workflow erneut durchlaufen. So bleibt die
    History erhalten und der Task kann mit neuen Erkenntnissen aufgegriffen werden.

    Was passiert:
    - status = 'triage' (Operator bewertet erneut)
    - assigned_role bleibt erhalten (z.B. 'pi-coder')
    - iteration_count wird auf 0 zurueckgesetzt (optional)
    - claimed_at wird auf NULL gesetzt
    - meta: reopen-Info wird gespeichert, alte CIO-Question/CEO-Answer/Recommendations geloescht
    - History: 'task_reopened' Eintrag mit Agent, Reason, vorheriger Status
    """
    t = _get_task(db, task_id)
    if t.status == "triage":
        raise HTTPException(400, f"Task ist bereits in Triage")
    if t.status == "done":
        raise HTTPException(400, f"Task ist bereits abgeschlossen (done). Re-Triage nicht mehr sinnvoll.")

    old_status = t.status
    if body.reset_iteration:
        t.iteration_count = 0
    t.claimed_at = None
    t.emergency = False  # Reset Emergency-Flag

    # Meta: Reopen-Info speichern
    meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})
    reopens = meta.get("reopens", [])
    reopens.append({
        "from_status": old_status,
        "by": body.agent,
        "reason": body.reason,
        "reopened_at": datetime.utcnow().isoformat(),
    })
    meta["reopens"] = reopens
    # Alte CIO-Question/Answer/Recommendations entfernen, damit Operator frisch bewertet
    for key in ("cio_question", "cio_question_at", "cio_question_issues", "cio_question_questions",
                "ceo_answer", "ceo_answer_at", "ceo_answer_by",
                "applied_recommendations"):
        meta.pop(key, None)
    t.meta = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(t, "meta")

    # Status auf Triage setzen mit History
    _set_status(db, t, "triage", body.agent, "task_reopened",
                from_status=old_status, reset_iteration=body.reset_iteration)
    db.commit()
    db.refresh(t)

    # Reason separat in History loggen
    _add_history(db, t, "reopen_reason", body.agent, details={"reason": body.reason})

    return {
        "ok": True,
        "task_id": task_id,
        "old_status": old_status,
        "new_status": "triage",
        "reopens_count": len(reopens),
        "message": f"Task wurde von '{old_status}' zurueck in Triage gestellt. Auto-Operator bewertet erneut.",
    }
