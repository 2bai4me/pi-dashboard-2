"""TaskService — Business-Logic fuer Tasks + Pricing-Snapshot-Mechanik."""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models.project import Project
from ..models.task import Task
from ..models.history import TaskHistory
from ..models.transition import TaskTransition
from ..models.token_usage import TokenUsage
from .pricing_service import (
    take_pricing_snapshot, calc_cost_from_snapshot, get_current_pricing,
)

logger = logging.getLogger("pi-dashboard-2")


def _gen_id() -> str:
    return secrets.token_hex(6)


# === Status-Wechsel Delay (User-Direktive 15.06.2026) ===
# Damit der User visuell sehen kann, dass der Prozess eingehalten wird,
# bleibt der Task 5 Sekunden im neuen Status, bevor die Weiterverarbeitung
# (Auto-Claim, Watchdog, History-Eintrag) startet.
DEFAULT_TRANSITION_DELAY_S: float = 5.0


class TaskService:
    """Service-Klasse fuer Task-Operationen."""

    @staticmethod
    def list_tasks(db: Session, project_id: Optional[str] = None,
                   status: Optional[str] = None,
                   with_history: bool = False,
                   with_tokens: bool = False) -> List[Task]:
        """Listet Tasks OHNE history/token_usages (default, schnell).

        Fuer History oder Token-Usage: with_history=True / with_tokens=True
        (nutzt joinedload + selectinload fuer N+1-Vermeidung).
        """
        from sqlalchemy.orm import selectinload
        stmt = select(Task).order_by(Task.priority.desc(), Task.created_at.asc())
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if status:
            stmt = stmt.where(Task.status == status)
        if with_history:
            stmt = stmt.options(selectinload(Task.history_entries))
        if with_tokens:
            stmt = stmt.options(selectinload(Task.token_usages))
        return list(db.execute(stmt).scalars())

    @staticmethod
    def get_task(db: Session, task_id: str) -> Optional[Task]:
        return db.get(Task, task_id)

    @staticmethod
    def create_task(db: Session, title: str, project_id: Optional[str] = None,
                   description: Optional[str] = None, status: str = "triage",
                   priority: int = 1, category: str = "new_request",
                   parent_id: Optional[str] = None,
                   assigned_role: Optional[str] = None,
                   success_criteria: Optional[List[str]] = None) -> Task:
        """Erstellt einen neuen Task.

        Standard-Defaults (User-Direktive 15.06.2026, Skill kanban-operator):
          - status   = "triage"  (neue Tasks starten IMMER in Triage)
          - priority = 1         (CIO bewertet im Triage-Prozess, hebt Prio an)
          - category = "new_request"
          - assigned_role = None  (BLEIBT LEER! Die SOP-Engine setzt ihn pro Step,
                                   z.B. Step 0 = CIO, Step 2 = pi-coder, Step 3 = pi-tester)

        Standard-Success-Criteria (User-Direktive 18.06.2026):
          Jeder Task bekommt IMMER mindestens 2 Standard-Kriterien:
            1. "Die in der Description dokumentierte Aenderung wurde umgesetzt und ist funktional"
            2. "Tester hat den Code als gut und fehlerfrei eingestuft (Code-Review bestanden)"

          Wenn der User eigene Kriterien mitgibt, werden diese ZUSÄTZLICH zu den
          Standard-Kriterien gespeichert. Duplikate werden vermieden.

        Diese Defaults sind Teil der SOP "task-creation-default" und duerfen
        nur durch explizite Argumente ueberschrieben werden.

        Fix (User-Direktive 18.06.2026): Vorher war Default "pi-coder", was
        waehrend der Triage-Phase falsch war (CIO bewertet, nicht pi-coder).
        Jetzt: Default LEER, Engine fuellt pro Step.
        """
        # Standard-Success-Criteria (User-Direktive 18.06.2026)
        STANDARD_CRITERIA = [
            "Die in der Description dokumentierte Aenderung wurde umgesetzt und ist funktional",
            "Tester hat den Code als gut und fehlerfrei eingestuft (Code-Review bestanden)",
        ]
        # User-Kriterien + Standard-Kriterien kombinieren (keine Duplikate)
        user_criteria = success_criteria or []
        combined_criteria = list(user_criteria)
        for sc in STANDARD_CRITERIA:
            if sc not in combined_criteria:
                combined_criteria.append(sc)

        t = Task(
            id=_gen_id(),
            project_id=project_id,
            parent_id=parent_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            category=category,
            assigned_role=assigned_role,  # None oder expliziter Wert, KEIN "pi-coder"-Default
            tags=[],
            success_criteria=combined_criteria,
            meta={},
        )
        db.add(t)
        db.flush()
        # History: task_created (mit SOP-Referenz)
        TaskService._add_history(db, t, "task_created", agent="system",
                                 details={
                                     "reason": "manual creation",
                                     "sop": "task-creation-default",
                                     "default_status": "triage",
                                     "default_priority": 1,
                                 })
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def update_task(db: Session, task_id: str, **fields) -> Optional[Task]:
        t = db.get(Task, task_id)
        if not t:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def set_status(db: Session, task_id: str, new_status: str) -> Optional[Task]:
        """Setzt Status + auto_claim bei todo + emergency_watchdog bei Prio>=90.

        Hinweis: Diese synchrone Variante wird aus Legacy-Gruenden beibehalten,
        nutzt aber die zentrale Transition-Logik nicht. Fuer neuen Code
        sollte `change_status_with_delay` (async) verwendet werden.
        """
        return TaskService.set_status_sync(db, task_id, new_status, delay_s=0.0)

    @staticmethod
    def set_status_sync(
        db: Session, task_id: str, new_status: str,
        agent: str = "system", reason: Optional[str] = None,
        delay_s: float = 0.0,
    ) -> Optional[Task]:
        """Synchrone Status-Aenderung (ohne asyncio.sleep) — fuer Tests / Legacy.

        Dokumentiert trotzdem den Status-Wechsel in der Transition-Tabelle
        (delay_s=0.0 wenn sofort).
        """
        t = db.get(Task, task_id)
        if not t:
            return None
        old_status = t.status
        if old_status == new_status:
            return t

        transition_at = datetime.utcnow()
        t.status = new_status
        t.updated_at = transition_at
        # HINWEIS: eigentliche Logik in der Legacy-Version unten; ueberladen mit _do_set_status_sync_body
        return TaskService._do_set_status_sync_body(
            db, t, old_status, new_status, agent, reason or "set_status_sync", {}, delay_s
        )

    @staticmethod
    def _do_set_status_sync_body(
        db: Session, t: Task, old_status: str, new_status: str,
        agent: str, reason: str, details: Dict[str, Any], delay_s: float,
    ) -> Task:
        """Gemeinsamer Body fuer set_status_sync: dokumentiert die Transition.

        Wenn delay_s > 0, wird der Task im aktuellen Status sichtbar
        (transition_started) und der Background-Delay laeuft asynchron,
        waehrend die HTTP-Response sofort zurueckkommt.
        """
        from datetime import timedelta
        from ..models.transition import TaskTransition
        from ..services.pricing_service import take_pricing_snapshot

        transition_at = datetime.utcnow()
        delay_seconds = max(0.0, float(delay_s))
        expected_processing_at = transition_at + timedelta(seconds=delay_seconds) if delay_seconds > 0 else transition_at

        # Status bereits gesetzt vom Caller (Legacy-Kompat)
        # Falls nicht: setzen
        if t.status != new_status:
            t.status = new_status
        t.updated_at = transition_at

        # Transition-Record IMMER anlegen
        TaskService._log_transition(
            db, t,
            from_status=old_status,
            to_status=new_status,
            agent=agent,
            reason=reason,
            details={**details, "sync": True, "delay_s": delay_seconds},
            delay_s=delay_seconds,
            transition_at=transition_at,
            processing_at=expected_processing_at,
            completed_at=expected_processing_at if delay_seconds == 0 else None,
        )
        # History
        TaskService._add_history(
            db, t, "transition_started", agent=agent,
            details={
                "from": old_status, "to": new_status, "reason": reason,
                "delay_s": delay_seconds,
                "transition_at": transition_at.isoformat(),
                "processing_at": expected_processing_at.isoformat(),
            },
        )
        # Status 'transitioned' (an den Ziel-Status) wird sofort festgeschrieben
        TaskService._add_history(
            db, t, "status_changed", agent=agent,
            details={"from": old_status, "to": new_status, "reason": reason},
        )
        db.commit()
        db.refresh(t)

        # === Background-Delay: 5s warten + Auto-Claim + Watchdog ===
        if delay_seconds > 0:
            TaskService._schedule_background_delay(
                db, t, old_status, new_status, agent, reason, details, delay_seconds
            )

        return t

    @staticmethod
    def _schedule_background_delay(
        db: Session, t: Task, old_status: str, new_status: str,
        agent: str, reason: str, details: Dict[str, Any], delay_seconds: float,
    ) -> None:
        """Startet einen Background-Task, der nach delay_seconds:
        1. Die Transition-Record abschliesst (completed_at)
        2. Auto-Claim-Logik ausfuehrt (bei new_status=='todo' oder in_progress)
        3. Watchdog-Logik (Notfall)
        """
        import asyncio
        from datetime import timedelta
        from ..models.transition import TaskTransition
        from ..services.pricing_service import take_pricing_snapshot

        async def _delay_and_finalize():
            try:
                await asyncio.sleep(delay_seconds)
                # Eigene DB-Session (Original kann mittlerweile geschlossen sein)
                from ..db.base import SessionLocal
                bg_db = SessionLocal()
                try:
                    bg_t = bg_db.get(Task, t.id)
                    if not bg_t:
                        return
                    processing_started_at = datetime.utcnow()
                    completed_at = datetime.utcnow()
                    duration_ms = int((completed_at - processing_started_at).total_seconds() * 1000)

                    # Auto-Claim (analog change_status_with_delay)
                    auto_claim_triggered = False
                    if new_status == "todo" and bg_t.status == "todo":
                        bg_t.status = "in_progress"
                        bg_t.claimed_at = processing_started_at
                        auto_claim_triggered = True
                    elif new_status == "in_progress" and bg_t.claimed_at is None:
                        bg_t.claimed_at = processing_started_at
                        auto_claim_triggered = True
                    if auto_claim_triggered:
                        # assigned_role wird NICHT hier gesetzt. SOP-Engine verwaltet das.
                        take_pricing_snapshot(bg_t, db=bg_db)
                        TaskService._add_history(
                            bg_db, bg_t, "auto_claim", agent="system",
                            details={"reason": "post_sync_transition_auto_claim",
                                     "assigned_role": bg_t.assigned_role,
                                     "delay_respected_s": delay_seconds,
                                     "triggered_via": new_status}
                        )
                        # Auto-Claim-Transition-Record
                        TaskService._log_transition(
                            bg_db, bg_t,
                            from_status="todo", to_status="in_progress",
                            agent="system", reason="auto_claim",
                            details={"assigned_role": bg_t.assigned_role,
                                     "trigger": "post_sync_transition_auto_claim"},
                            delay_s=0.0,
                            transition_at=processing_started_at,
                            processing_at=processing_started_at,
                            completed_at=completed_at,
                        )

                    # Watchdog-Logik (Prio>=90)
                    if bg_t.priority >= 90 and bg_t.status != "done" and not bg_t.emergency:
                        bg_t.emergency = True
                        bg_t.emergency_at = processing_started_at
                        take_pricing_snapshot(bg_t, db=bg_db)
                        TaskService._add_history(
                            bg_db, bg_t, "watchdog_triggered", agent="system",
                            details={"reason": "post_sync_priority>=90", "priority": bg_t.priority}
                        )

                    # Transition-Record finalisieren
                    from sqlalchemy import select as _sel
                    tr = bg_db.execute(
                        _sel(TaskTransition)
                        .where(TaskTransition.task_id == bg_t.id,
                               TaskTransition.from_status == old_status,
                               TaskTransition.to_status == new_status)
                        .order_by(TaskTransition.transition_at.desc())
                        .limit(1)
                    ).scalar_one_or_none()
                    if tr:
                        tr.processing_at = processing_started_at
                        tr.completed_at = completed_at
                        tr.duration_ms = duration_ms

                    bg_db.commit()
                    logger.info(
                        f"[bg-delay] Task {bg_t.id[:8]} {old_status!r}->{new_status!r}: "
                        f"finalized after {delay_seconds}s (auto_claim={auto_claim_triggered}, "
                        f"status={bg_t.status}, claimed_at={bg_t.claimed_at})"
                    )
                finally:
                    bg_db.close()
            except Exception as e:
                logger.error(f"[bg-delay] Failed for task {t.id[:8]}: {e}")

        # Background-Task starten — 3 Faelle:
        # (a) Async-Endpoint mit laufendem Loop: asyncio.create_task
        # (b) Sync-Endpoint (ThreadPool): eigenen Thread starten, der asyncio.run() aufruft
        # (c) Kein Event-Loop: synchron warten (Notfall)
        try:
            try:
                loop = asyncio.get_running_loop()
                # (a) Async-Kontext: Task einreihen
                loop.create_task(_delay_and_finalize())
            except RuntimeError:
                # Kein laufender Event-Loop (z.B. def-Endpoint in ThreadPool)
                # (b) Eigenen Thread starten, der einen neuen Loop erstellt
                import threading
                t_bg = threading.Thread(
                    target=lambda: asyncio.run(_delay_and_finalize()),
                    daemon=True,
                    name=f"bg-delay-{t.id[:8]}-{new_status}"
                )
                t_bg.start()
        except Exception as e:
            # (c) Notfall: synchron warten
            logger.warning(f"[bg-delay] Fallback synchron fuer Task {t.id[:8]}: {e}")
            try:
                asyncio.run(_delay_and_finalize())
            except Exception:
                pass

        return t


    @staticmethod
    def set_priority(db: Session, task_id: str, priority: int) -> Optional[Task]:
        """Setzt Prio (Notfall-Watchdog bei >= 90)."""
        t = db.get(Task, task_id)
        if not t:
            return None
        old = t.priority
        t.priority = priority
        t.updated_at = datetime.utcnow()
        if priority >= 90 and t.status != "done":
            t.emergency = True
            t.emergency_at = datetime.utcnow()
            take_pricing_snapshot(t, db=db)
            TaskService._add_history(db, t, "emergency_watchdog", agent="system",
                                     details={"old_prio": old, "new_prio": priority})
        elif priority < 90 and t.emergency:
            t.emergency = False
            t.emergency_cleared_at = datetime.utcnow()
        TaskService._add_history(db, t, "priority_changed", agent="system",
                                 details={"from": old, "to": priority})
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def report_dispatch(db: Session, task_id: str, role: str, status: str,
                        model: str, agent_pid: Optional[int] = None,
                        reason: Optional[str] = None,
                        tokens_in: int = 0, tokens_out: int = 0) -> Optional[Dict[str, Any]]:
        """Sub-Agent meldet Dispatch-Status zurueck."""
        t = db.get(Task, task_id)
        if not t:
            return None
        t.assigned_subagent = role
        t.updated_at = datetime.utcnow()
        if not t.pricing_snapshot or t.pricing_snapshot.get("model") != model:
            take_pricing_snapshot(t, model_id=model, db=db)
        snap = t.pricing_snapshot
        cost = calc_cost_from_snapshot(tokens_in, tokens_out, snap)
        TaskService._add_history(db, t, "subagent_dispatched", agent=role,
                                 model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                                 cost_usd=cost,
                                 details={"status": status, "agent_pid": agent_pid,
                                          "reason": reason, "pricing_snapshot_used": snap})
        db.commit()
        db.refresh(t)
        return {"ok": True, "task_id": task_id, "model": model, "cost_usd": float(cost),
                "pricing_snapshot": snap}

    @staticmethod
    def report_usage(db: Session, task_id: str, tokens_in: int, tokens_out: int,
                     model: Optional[str] = None, role: Optional[str] = None,
                     note: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Sub-Agent meldet kumulierte Token-Counts."""
        t = db.get(Task, task_id)
        if not t:
            return None
        model = model or t.assigned_subagent_model or "minimax/minimax-m3"
        if not t.pricing_snapshot or t.pricing_snapshot.get("model") != model:
            take_pricing_snapshot(t, model_id=model, db=db)
        snap = t.pricing_snapshot
        cost = calc_cost_from_snapshot(tokens_in, tokens_out, snap)
        # History
        h = TaskService._add_history(db, t, "token_usage_report", agent=role or t.assigned_subagent or "subagent",
                                     model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                                     cost_usd=cost,
                                     details={"note": note or "", "pricing_snapshot_used": snap},
                                     return_entry=True)
        # TokenUsage-Record (fuer Analytics)
        in_per_m  = Decimal(str(snap.get("input_per_1m", "0")))
        out_per_m = Decimal(str(snap.get("output_per_1m", "0")))
        tu = TokenUsage(
            task_id=t.id,
            history_id=h.id,
            model=model,
            provider=snap.get("provider", "unknown"),
            role=role,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            input_per_1m=in_per_m,
            output_per_1m=out_per_m,
            pricing_source=snap.get("source"),
            snapshot_at=datetime.fromisoformat(snap["snapshot_at"]) if snap.get("snapshot_at") else None,
        )
        db.add(tu)
        db.commit()
        db.refresh(t)
        return {"ok": True, "task_id": task_id, "tokens_in": tokens_in, "tokens_out": tokens_out,
                "cost_usd": float(cost), "pricing_snapshot": snap}

    @staticmethod
    def delete_task(db: Session, task_id: str) -> bool:
        t = db.get(Task, task_id)
        if not t:
            return False
        db.delete(t)
        db.commit()
        return True

    @staticmethod
    def _add_history(db: Session, t: Task, event: str, agent: str = "system",
                     model: Optional[str] = None,
                     tokens_in: int = 0, tokens_out: int = 0,
                     cost_usd: Optional[Decimal] = None,
                     details: Optional[Dict[str, Any]] = None,
                     return_entry: bool = False,
                     session_id: Optional[str] = None):
        # Auto-Generate Session-ID wenn nicht explizit angegeben
        if session_id is None:
            from .session_helper import get_or_create_session_id
            session_id = get_or_create_session_id()
        h = TaskHistory(
            task_id=t.id, event=event, agent=agent, model=model,
            session_id=session_id,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost_usd or Decimal("0"),
            details=details or {},
        )
        db.add(h)
        db.flush()
        return h if return_entry else None

    # === Transition-Logging (User-Direktive 15.06.2026) ===
    @staticmethod
    def _log_transition(
        db: Session, t: Task, from_status: str, to_status: str,
        agent: str = "system", reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        delay_s: float = DEFAULT_TRANSITION_DELAY_S,
        transition_at: Optional[datetime] = None,
        processing_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> TaskTransition:
        """Legt einen Eintrag in der zentralen Performance-Tabelle an.

        Wird beim JEDEN Status-Wechsel aufgerufen. Erfasst:
        - from/to-Status
        - transition_at (Request-Zeitpunkt)
        - processing_at (Beginn der Weiterverarbeitung nach Delay)
        - completed_at (Ende der Verarbeitung)
        - delay_s (konfigurierter Delay)
        - duration_ms (Verarbeitungsdauer)
        """
        from .session_helper import get_session_id
        tr = TaskTransition(
            task_id=t.id,
            project_id=t.project_id,
            from_status=from_status or "",
            to_status=to_status,
            transition_at=transition_at or datetime.utcnow(),
            processing_at=processing_at,
            completed_at=completed_at,
            delay_s=delay_s,
            duration_ms=None,
            session_id=get_session_id(),
            agent=agent,
            reason=reason,
            details=details or {},
        )
        db.add(tr)
        db.flush()
        return tr

    @staticmethod
    async def change_status_with_delay(
        db: Session, t: Task, new_status: str,
        agent: str = "system", reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        delay_s: float = DEFAULT_TRANSITION_DELAY_S,
    ) -> Task:
        """Setzt den Task-Status neu und respektiert die 5s-Verzoegerung.

        Reihenfolge:
        1) Task-Status auf neuen Wert setzen
        2) History-Eintrag 'status_changed_pending' anlegen
        3) Transition-Eintrag anlegen (transition_at=jetzt, processing_at=jetzt+delay)
        4) DB-Commit (Status ist sichtbar, andere koennen reagieren)
        5) asyncio.sleep(delay_s) — sichtbarer Delay
        6) Transition-Eintrag updaten (processing_at, completed_at)
        7) Auto-Claim / Watchdog-Logik (falls new_status=='todo' oder Prio>=90)
        8) History 'status_changed' final anlegen + Commit

        Vorteil: User sieht den Status visuell, 'Weiterverarbeitung' startet erst
        nach Delay. Andere Requests, die den Task lesen, sehen den neuen Status
        sofort.
        """
        old_status = t.status
        if old_status == new_status:
            logger.debug(f"Task {t.id[:8]} already in status {new_status}, skipping transition")
            return t

        transition_requested_at = datetime.utcnow()

        # 1) Task-Status sofort setzen
        t.status = new_status
        t.updated_at = transition_requested_at

        # 2) Transition-Eintrag anlegen (zentrale Performance-Tabelle)
        delay_seconds = max(0.0, float(delay_s))
        expected_processing_at = None
        if delay_seconds > 0:
            from datetime import timedelta
            expected_processing_at = transition_requested_at + timedelta(seconds=delay_seconds)

        TaskService._log_transition(
            db, t,
            from_status=old_status,
            to_status=new_status,
            agent=agent,
            reason=reason or "status_change",
            details=details or {},
            delay_s=delay_seconds,
            transition_at=transition_requested_at,
            processing_at=expected_processing_at,
            completed_at=None,
        )

        # 3) History-Eintrag 'transition_started' (sichtbar fuer Audit)
        TaskService._add_history(
            db, t, "transition_started", agent=agent,
            details={
                "from": old_status, "to": new_status,
                "reason": reason, "delay_s": delay_seconds,
                "transition_at": transition_requested_at.isoformat(),
                "processing_at": expected_processing_at.isoformat() if expected_processing_at else None,
            },
        )

        db.commit()
        db.refresh(t)

        # 4) Sleep: sichtbarer Delay fuer User (BESTAETIGT, dass Status-Wechsel passiert ist)
        if delay_seconds > 0:
            logger.info(
                f"Task {t.id[:8]} status {old_status!r}->{new_status!r}: "
                f"delay {delay_seconds}s (transition_at={transition_requested_at.isoformat()})"
            )
            await asyncio.sleep(delay_seconds)

        processing_started_at = datetime.utcnow()

        # 5) Auto-Claim-Logik (analog set_status_sync + _set_status)
        # Triggert wenn:
        #  a) new_status == "todo" und Task noch in "todo" (von triage kommend)
        #  b) new_status == "in_progress" und claimed_at noch null (manuelles start)
        auto_claim_triggered = False
        if new_status == "todo" and t.status == "todo":
            # Fall a: triage → todo → auto-claim → in_progress
            t.status = "in_progress"
            t.claimed_at = processing_started_at
            auto_claim_triggered = True
        elif new_status == "in_progress" and t.claimed_at is None:
            # Fall b: direkter Start-Befehl ohne vorherigen todo-Status
            t.claimed_at = processing_started_at
            auto_claim_triggered = True
        if auto_claim_triggered:
            # assigned_role wird NICHT hier gesetzt. SOP-Engine verwaltet das.
            take_pricing_snapshot(t, db=db)
            TaskService._add_history(db, t, "auto_claim", agent="system",
                                     details={"reason": "post_transition_auto_claim",
                                              "assigned_role": t.assigned_role,
                                              "delay_respected_s": delay_seconds,
                                              "triggered_via": new_status})

        # === NEU: Sub-Agent-Spawning-Hook (User-Direktive 19.06.2026) ===
        # Wird bei JEDEM Status-Wechsel auf in_progress (oder nach Auto-Claim) ausgeloest,
        # wenn ein assigned_subagent gesetzt ist. Schliesst die architektonische Luecke
        # zwischen Auto-Claim und tatsaechlicher Worker-Ausfuehrung.
        if new_status == "in_progress" and (t.assigned_subagent or t.assigned_role):
            try:
                from .sub_agent import _spawn_sub_agent
                spawn_result = await _spawn_sub_agent(t, db)
                if spawn_result:
                    logger.info(
                        f"Sub-Agent fuer Task {t.id[:8]} gestartet: "
                        f"PID {spawn_result.get('pid')}, Rolle {spawn_result.get('role')}"
                    )
            except Exception as spawn_err:
                logger.error(
                    f"Sub-Agent-Spawn fehlgeschlagen fuer Task {t.id[:8]}: {spawn_err}. "
                    f"Task bleibt in in_progress, Worker uebernimmt manuell."
                )

        # 6) Watchdog-Logik
        if t.priority >= 90 and t.status != "done" and not t.emergency:
            t.emergency = True
            t.emergency_at = processing_started_at
            take_pricing_snapshot(t, db=db)
            TaskService._add_history(db, t, "watchdog_triggered", agent="system",
                                     details={"reason": "post_transition_priority>=90"})
        elif t.priority < 90 and t.emergency:
            t.emergency = False

        # 7) Finaler History-Eintrag + Transition-Update
        TaskService._add_history(db, t, "status_changed", agent=agent,
                                 details={"from": old_status, "to": new_status,
                                          "reason": reason,
                                          "transition_at": transition_requested_at.isoformat(),
                                          "processing_at": processing_started_at.isoformat()})

        # 8) Transition-Eintrag final aktualisieren
        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - processing_started_at).total_seconds() * 1000)
        # Letzten TaskTransition-Record fuer diesen Wechsel holen und updaten
        from sqlalchemy import select as _select
        tr = db.execute(
            _select(TaskTransition)
            .where(TaskTransition.task_id == t.id,
                   TaskTransition.from_status == old_status,
                   TaskTransition.to_status == new_status)
            .order_by(TaskTransition.transition_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if tr:
            tr.processing_at = processing_started_at
            tr.completed_at = completed_at
            tr.duration_ms = duration_ms
            # Falls der Status durch Auto-Claim doch geaendert wurde: zusaetzlicher Eintrag
            if t.status != new_status:
                TaskService._log_transition(
                    db, t, from_status=new_status, to_status=t.status,
                    agent="system", reason="auto_claim_after_delay",
                    details={"parent_transition_id": tr.id},
                    delay_s=0.0,
                    transition_at=processing_started_at,
                    processing_at=processing_started_at,
                    completed_at=completed_at,
                )

        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def task_stats(db: Session, task_id: str) -> Dict[str, Any]:
        """Aggregierte Stats: tokens, cost, model, duration, history_count, snapshot."""
        t = db.get(Task, task_id)
        if not t:
            return {}
        history = list(db.execute(
            select(TaskHistory).where(TaskHistory.task_id == task_id).order_by(TaskHistory.ts)
        ).scalars())
        tokens_in  = sum(h.tokens_in for h in history)
        tokens_out = sum(h.tokens_out for h in history)
        snap = t.pricing_snapshot
        if snap:
            cost = float(calc_cost_from_snapshot(tokens_in, tokens_out, snap))
        else:
            cost = float(sum(h.cost_usd for h in history))
        model_usage: Dict[str, int] = {}
        for h in history:
            m = h.model or "unknown"
            model_usage[m] = model_usage.get(m, 0) + 1
        main_model = max(model_usage, key=model_usage.get) if model_usage else "unknown"
        # Duration
        duration_s = 0
        if len(history) >= 1:
            try:
                duration_s = int((history[-1].ts - history[0].ts).total_seconds())
            except (AttributeError, TypeError):
                pass
        return {
            "task_id":          task_id,
            "model":            main_model,
            "model_usage":      model_usage,
            "tokens":           {"in": tokens_in, "out": tokens_out, "total": tokens_in + tokens_out},
            "cost_usd":         cost,
            "duration_s":       duration_s,
            "history_count":    len(history),
            "pricing_snapshot": snap,
        }

    @staticmethod
    def generate_completion_report(db: Session, project: Project) -> str:
        """Generiert ausfuehrlichen Abschlussbericht im Markdown-Format."""
        from ..models.history import TaskHistory
        from ..models.token_usage import TokenUsage
        from sqlalchemy import func as sqlfunc

        tasks = list(db.execute(select(Task).where(Task.project_id == project.id)).scalars())
        # Status-Distribution
        status_dist: Dict[str, int] = {}
        for t in tasks:
            status_dist[t.status] = status_dist.get(t.status, 0) + 1
        # Token-Aggregation
        tokens = db.execute(
            select(
                sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_in), 0),
                sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_out), 0),
                sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0),
            )
            .join(Task, Task.id == TokenUsage.task_id)
            .where(Task.project_id == project.id)
        ).one()
        total_in, total_out, total_cost = tokens
        # Cost by Provider
        cost_by_prov: Dict[str, float] = {}
        cost_by_role: Dict[str, float] = {}
        cost_by_model: Dict[str, float] = {}
        rows = db.execute(
            select(TokenUsage.provider, TokenUsage.role, TokenUsage.model, TokenUsage.cost_usd)
            .join(Task, Task.id == TokenUsage.task_id)
            .where(Task.project_id == project.id)
        ).all()
        for prov, role, model, cost in rows:
            if prov:
                cost_by_prov[prov] = cost_by_prov.get(prov, 0) + float(cost)
            if role:
                cost_by_role[role] = cost_by_role.get(role, 0) + float(cost)
            if model:
                cost_by_model[model] = cost_by_model.get(model, 0) + float(cost)
        # Top 5 teuerste Tasks (sortiert nach Summe-Cost DESC)
        cost_col = sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0).label("c")
        top5 = db.execute(
            select(Task.id, Task.title, cost_col)
            .join(TokenUsage, TokenUsage.task_id == Task.id, isouter=True)
            .where(Task.project_id == project.id)
            .group_by(Task.id, Task.title)
            .order_by(cost_col.desc())
            .limit(5)
        ).all()
        top5_list = [{"id": t[0], "title": t[1], "cost_usd": float(t[2])} for t in top5]
        # Duration
        dur_days = 0
        if project.created_at:
            dur = datetime.utcnow() - project.created_at
            dur_days = dur.days

        # Markdown-Report
        lines = [
            f"# Abschlussbericht: {project.name}",
            "",
            f"**Projekt-ID:** {project.id}",
            f"**Abgeschlossen am:** {datetime.utcnow().isoformat()}",
            f"**Dauer:** {dur_days} Tage",
            f"**Modus:** {project.mode}",
            f"**Kategorie (ITIL):** {project.category}",
            "",
            "## Kennzahlen-Uebersicht",
            "",
            f"- **Tasks gesamt:** {len(tasks)}",
        ]
        for status, cnt in sorted(status_dist.items(), key=lambda x: -x[1]):
            lines.append(f"  - {status}: {cnt}")
        lines += [
            f"- **Tokens (Input):** {total_in:,}".replace(",", "."),
            f"- **Tokens (Output):** {total_out:,}".replace(",", "."),
            f"- **Gesamtkosten:** ${float(total_cost):.4f}",
            "",
            "## Kosten pro Provider",
            "",
        ]
        for prov, c in sorted(cost_by_prov.items(), key=lambda x: -x[1]):
            lines.append(f"- **{prov}:** ${c:.4f}")
        if not cost_by_prov:
            lines.append("- (keine Provider-Kosten erfasst)")
        lines += ["", "## Kosten pro Rolle", ""]
        for role, c in sorted(cost_by_role.items(), key=lambda x: -x[1]):
            lines.append(f"- **{role}:** ${c:.4f}")
        if not cost_by_role:
            lines.append("- (keine Rollen-Kosten erfasst)")
        lines += ["", "## Kosten pro Modell", ""]
        for m, c in sorted(cost_by_model.items(), key=lambda x: -x[1]):
            lines.append(f"- **{m}:** ${c:.4f}")
        if not cost_by_model:
            lines.append("- (keine Modell-Kosten erfasst)")
        lines += [
            "",
            "## Top 5 teuerste Tasks",
            "",
        ]
        for i, t in enumerate(top5_list, 1):
            lines.append(f"{i}. **{t['title'][:60]}** — ${t['cost_usd']:.4f} (`{t['id'][:12]}`)")
        if not top5_list:
            lines.append("- (keine Tasks mit Kosten erfasst)")

        return "\n".join(lines)
