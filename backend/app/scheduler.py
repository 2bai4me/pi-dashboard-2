"""Auto-Backup-Scheduler (Hintergrund-Task).

Erstellt taeglich ein SQLite-Backup und loescht alte Backups nach Retention-Periode.

Production-Grade: Bei PostgreSQL wuerde man pg_dump + WAL-Archiving nutzen.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from .config import settings

logger = logging.getLogger("pi-dashboard-2.backup-scheduler")


async def create_backup_task() -> dict:
    """Erstellt ein Backup der aktuellen DB.

    Returns: {ok, path, size_mb, created_at, deleted_old}
    """
    import sqlite3
    from .config import settings
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    backup_dir = Path("database/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"pi_dashboard-{timestamp}.db"

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(str(backup_path))
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    # Retention: Backups aelter als 7 Tage loeschen
    deleted = 0
    cutoff = datetime.utcnow() - timedelta(days=7)
    for old_backup in backup_dir.glob("pi_dashboard-*.db"):
        if old_backup == backup_path:
            continue
        try:
            # Filename: pi_dashboard-YYYYMMDD-HHMMSS.db
            ts_str = old_backup.stem.split("-", 1)[1]  # YYYYMMDD-HHMMSS
            old_dt = datetime.strptime(ts_str, "%Y%m%d-%H%M%S")
            if old_dt < cutoff:
                old_backup.unlink()
                deleted += 1
        except (ValueError, IndexError):
            continue  # Skip malformed files

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    logger.info(f"Auto-Backup erstellt: {backup_path} ({size_mb:.2f} MB, deleted_old={deleted})")
    return {
        "ok": True,
        "path": str(backup_path),
        "size_mb": round(size_mb, 3),
        "created_at": datetime.utcnow().isoformat(),
        "deleted_old": deleted,
    }


# ─────────────── AUTO-TRIAGE-OPERATOR (Live-Modus) ───────────────

# Feature-Flag: Auto-Triage-Operator aktivieren/deaktivieren
import os
TRIAGE_OPERATOR_ENABLED = os.getenv("TRIAGE_OPERATOR_ENABLED", "true").lower() == "true"
TRIAGE_OPERATOR_INTERVAL_SEC = int(os.getenv("TRIAGE_OPERATOR_INTERVAL_SEC", "30"))


async def auto_triage_evaluate_task() -> dict:
    """Operator: holt alle TRIAGE-Tasks und ruft SOPEngine auf (NICHT mehr direkt).

    User-Direktive 17.06.2026 (SOP-Engine-Integration):
    - Statt direktem Status-Change nutzen wir die echte SOPEngine.run_step(instance)
    - Die Engine schreibt Audit-Logs (step_started/step_completed/rule_evaluated/step_advanced)
    - Die Engine setzt current_step_id korrekt (war vorher immer null)
    - Die Engine nutzt die in der DB gespeicherten Rules, Action-Handler, etc.
    - Die CIO-Heuristik wird im Scheduler aufgerufen, das Ergebnis als
      instance.context["step_ok"] in den Context geschrieben
    - Die Engine wertet die Rules aus, feuert approve_triage -> Status "todo"

    Folge-Aktionen NACH run_step (Auto-Claim, AgentQuestion) bleiben im Scheduler.
    """
    from .db.base import SessionLocal
    from .models.task import Task
    from .models.sop import SOP, SOPStep, SOPInstance
    from .models.project import Project
    from .services.sop_engine import SOPEngine
    from .routers.workflow import _check_cio_heuristic
    import json

    if not TRIAGE_OPERATOR_ENABLED:
        return {"ok": True, "skipped": True, "reason": "operator disabled"}

    db = SessionLocal()
    try:
        from sqlalchemy.orm.attributes import flag_modified
        triage_tasks = list(db.execute(
            select(Task).where(Task.status == "triage").order_by(Task.priority.desc())
        ).scalars())
        if not triage_tasks:
            return {"ok": True, "evaluated": 0}

        evaluated = []
        for t in triage_tasks:
            # db.refresh damit meta und status aktuell sind
            db.refresh(t)
            meta = t.meta if isinstance(t.meta, dict) else (json.loads(t.meta) if t.meta else {})

            # === 1. SOPInstance laden oder erstellen ===
            # Fix (User-Direktive 18.06.2026): Bei mehreren vorhandenen Instances
            # die juengste nehmen, alte ggf. als completed markieren. Vorher crashte
            # der Triage-Operator mit "Multiple rows were found when one or none was required".
            existing_instances = list(db.execute(
                select(SOPInstance).where(SOPInstance.task_id == t.id)
                .order_by(SOPInstance.started_at.desc())
            ).scalars())
            if len(existing_instances) > 1:
                # Die juengste als aktiv verwenden, aelteren als completed markieren
                for old_inst in existing_instances[1:]:
                    if old_inst.status == "running":
                        old_inst.status = "completed"
                        old_inst.completed_at = datetime.utcnow()
                        logger.info(f"Task {t.id}: alte Instance {old_inst.id[:8]} als completed markiert (doppelte Instance)")
                db.commit()
            instance = existing_instances[0] if existing_instances else None
            # Fix (User-Direktive 18.06.2026): Verwaiste Instance erkennen.
            # Eine Instance ist verwaist, wenn status=completed aber current_step_id=None
            # (z.B. weil tasks.py eine kaputte Instance angelegt hat). In dem Fall
            # als "nicht existent" behandeln und neu erstellen.
            if instance and instance.status == "completed" and not instance.current_step_id:
                logger.warning(f"Task {t.id}: Instance {instance.id[:8]} ist verwaist (completed ohne current_step), loesche und erstelle neu")
                db.delete(instance)
                db.commit()
                instance = None

            if not instance:
                # SOP-ID ermitteln: zuerst proj.default_sop_id, dann fallback "Standard-Workflow Development"
                proj = db.get(Project, t.project_id) if t.project_id else None
                sop_id = proj.default_sop_id if proj and proj.default_sop_id else None
                if not sop_id:
                    sop = db.execute(
                        select(SOP).where(SOP.name == "Standard-Workflow Development")
                    ).scalar_one_or_none()
                    if sop:
                        sop_id = sop.id
                if not sop_id:
                    logger.warning(f"Task {t.id}: Keine SOP gefunden, ueberspringe")
                    continue

                # Erste Step der SOP holen
                first_step = db.execute(
                    select(SOPStep).where(SOPStep.sop_id == sop_id)
                    .order_by(SOPStep.step_order).limit(1)
                ).scalar_one_or_none()
                if not first_step:
                    logger.warning(f"Task {t.id}: SOP {sop_id} hat keine Steps")
                    continue

                instance = SOPInstance(
                    id=f"inst-{uuid.uuid4().hex[:12]}",
                    sop_id=sop_id,
                    task_id=t.id,
                    project_id=t.project_id,
                    current_step_id=first_step.id,
                    status="running",
                    started_at=datetime.utcnow(),
                )
                db.add(instance)
                db.commit()
                db.refresh(instance)
                logger.info(f"Task {t.id}: SOP-Instance {instance.id[:8]} angelegt (sop={sop_id[:8]}, step0={first_step.name})")

            # === 2. current_step_id sicherstellen (Bug-Fix) ===
            if not instance.current_step_id:
                first_step = db.execute(
                    select(SOPStep).where(SOPStep.sop_id == instance.sop_id)
                    .order_by(SOPStep.step_order).limit(1)
                ).scalar_one_or_none()
                if first_step:
                    instance.current_step_id = first_step.id
                    db.commit()
                    logger.info(f"Task {t.id}: Instance {instance.id[:8]} current_step_id={first_step.name}")

            # === 3. Heuristik aufrufen (fuer Issues/Questions-Sammlung VOR Engine) ===
            # Die Engine ruft die Heuristik spaeter SELBST in der Action review_task auf
            # (Fix User-Direktive 18.06.2026: review_task fuehrt jetzt die Heuristik aus).
            # Wir brauchen das Ergebnis hier nur, um daraus den Status-Change-Reason
            # und ggf. die AgentQuestion zu erstellen.
            result = _check_cio_heuristic(db, t)
            heuristic_issues = result.get("issues", [])
            heuristic_questions = result.get("questions", [])

            # === 4. Heuristik-Ergebnis in Context schreiben (Issues/Questions, nicht step_ok!) ===
            # HINWEIS: step_ok wird NICHT mehr hier gesetzt - die Engine merged step_result["ok"]
            # (von der review_task Action) in ctx["step_ok"] und das waere sonst ein Konflikt.
            ctx = dict(instance.context or {})
            ctx["triage_issues"] = heuristic_issues
            ctx["triage_questions"] = heuristic_questions
            ctx["heuristic_run_at"] = datetime.utcnow().isoformat()
            instance.context = ctx
            db.commit()

            # === 5. SOPEngine.run_step aufrufen ===
            engine = SOPEngine(db)
            try:
                engine_result = await engine.run_step(instance)
                db.refresh(t)
                db.refresh(instance)
                logger.info(f"Task {t.id}: SOPEngine.run_step OK -> status={t.status}, current_step_id={instance.current_step_id[:8] if instance.current_step_id else None}")
            except Exception as e:
                logger.error(f"Task {t.id}: SOPEngine-Fehler: {e}", exc_info=True)
                db.rollback()
                continue

            # === 6. Folge-Aktionen: Auto-Claim oder AgentQuestion ===
            if t.status == "todo":
                # OK: Auto-Claim schedulen (5s Delay -> in_progress = Schritt 2)
                # assigned_role wird NICHT hier gesetzt. Die SOP-Engine setzt ihn
                # in Step 1 (assign_worker) auf "CIO" (step.agent) und in
                # spaeteren Steps auf den jeweiligen Worker.
                from .services.task_service import TaskService
                from .services.pricing_service import take_pricing_snapshot
                take_pricing_snapshot(t, db=db)
                TaskService._schedule_background_delay(
                    db, t, old_status="todo", new_status="in_progress",
                    agent="system", reason="auto_claim_sop_step_1_to_2",
                    details={"sop_step": "worker_assignment_to_implementation",
                             "sop_instance_id": instance.id,
                             "assigned_role": t.assigned_role,
                             "triggered_by": "auto_triage_evaluate_via_sop_engine"},
                    delay_seconds=5.0,
                )
                meta.pop("cio_question", None)
                meta.pop("ceo_answer", None)
                t.meta = meta
                flag_modified(t, "meta")
                evaluated.append({"task_id": t.id, "decision": "approved",
                                   "new_status": "in_progress",
                                   "sop_instance_id": instance.id,
                                   "claimed_at": t.claimed_at.isoformat() if t.claimed_at else None})

            elif t.status in ("block", "rueckfrage"):
                # Fragen: AgentQuestion erstellen
                all_items = result.get("issues", []) + result.get("questions", [])
                all_titles = [item["title"] for item in all_items if isinstance(item, dict) and item.get("title")]
                question_text = " | ".join(all_titles) if all_titles else "Unbekanntes Problem"

                t.meta = meta
                flag_modified(t, "meta")

                from .services.task_service import TaskService
                TaskService._add_history(db, t, "status_changed", agent="CIO-auto",
                                         details={"from": "triage", "to": t.status, "reason": "cio_auto_question_via_sop_engine",
                                                  "question": question_text, "auto_mode": True,
                                                  "sop_instance_id": instance.id})

                # === NEU: Erstelle ECHTE AgentQuestion, damit User-Input-Tool sichtbar wird ===
                from .models.agent_question import AgentQuestion
                existing_q = None
                pending_questions = db.execute(
                    select(AgentQuestion).where(AgentQuestion.status == "pending")
                ).scalars().all()
                for pq in pending_questions:
                    try:
                        pq_ctx = pq.context if isinstance(pq.context, dict) else (json.loads(pq.context) if pq.context else {})
                        if isinstance(pq_ctx, dict) and pq_ctx.get("task_id") == t.id:
                            existing_q = pq
                            break
                    except Exception:
                        continue
                if not existing_q and all_items:
                    first_item = all_items[0] if all_items else {}
                    first_title = first_item.get("title", question_text) if isinstance(first_item, dict) else question_text
                    first_desc = first_item.get("description", "") if isinstance(first_item, dict) else ""
                    first_rec = first_item.get("recommendation", "") if isinstance(first_item, dict) else ""
                    first_sugg = first_item.get("suggestions", []) if isinstance(first_item, dict) else []
                    full_description = first_desc
                    if first_sugg:
                        full_description += "\n\n**Vorschläge:**\n" + "\n".join(f"- {s}" for s in first_sugg)
                    # === User-Direktive 18.06.2026: Eskalations-Workflow ===
                    # Erst CIO + CEO-digital versuchen zu antworten, dann User
                    from .services.agent_question_helpers import create_agent_question_with_auto_answer
                    aq, requires_user_input, auto_answer = create_agent_question_with_auto_answer(
                        db,
                        agent_id="cio-auto",
                        agent_level="C-Level",
                        agent_label="CIO (Auto-Triage)",
                        question_type="text",
                        title=first_title[:200],
                        question=question_text[:500],
                        description=full_description[:2000] if full_description else None,
                        recommendation=first_rec[:500] if first_rec else None,
                        priority="high",
                        task_id=t.id,
                        context={"task_id": t.id, "board_id": t.project_id, "auto_triage": True,
                                 "all_titles": all_titles, "sop_instance_id": instance.id},
                    )
                    # Nur wenn KEIN Auto-Answer gefunden wurde: User-Eskalation
                    if requires_user_input:
                        try:
                            from .services.agent_question_helpers import update_task_on_question
                            update_task_on_question(db, t.id, aq.id, "cio-auto", "CIO (Auto-Triage)")
                        except Exception as e:
                            logger.warning(f"update_task_on_question fehlgeschlagen: {e}")
                    else:
                        logger.info(f"Task {t.id}: Frage {aq.id} wurde automatisch beantwortet, User-Eskalation entfaellt")
                    evaluated.append({"task_id": t.id, "decision": "question", "new_status": t.status,
                                       "question": question_text, "agent_question_id": aq.id,
                                       "sop_instance_id": instance.id,
                                       "auto_answered": not requires_user_input})
                else:
                    evaluated.append({"task_id": t.id, "decision": "question", "new_status": t.status,
                                       "question": question_text,
                                       "agent_question_id": existing_q.id if existing_q else None,
                                       "sop_instance_id": instance.id})

        db.commit()
        logger.info(f"Auto-Triage-Operator (via SOPEngine): {len(evaluated)} Tasks bewertet ({sum(1 for e in evaluated if e['decision']=='approved')} approved, {sum(1 for e in evaluated if e['decision']=='question')} questions)")
        return {"ok": True, "evaluated": len(evaluated), "details": evaluated}
    except Exception as e:
        logger.error(f"Auto-Triage-Operator: Fatal error: {e}", exc_info=True)
        db.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


async def persistent_auto_claim_watcher() -> dict:
    """Persistent Auto-Claim-Watcher (User-Direktive 17.06.2026).

    Findet alle Tasks mit status=todo + claimed_at IS NULL, die aelter als 5s sind,
    und macht auto-claim (-> in_progress). ROBUST GEGEN SERVER-RESTARTS
    (im Gegensatz zu asyncio.create_task-basierter Background-Delay, die bei
    Server-Restart verloren geht).

    Wird als eigener Scheduler-Job alle 15s ausgefuehrt.
    """
    from datetime import timedelta
    from .db.base import SessionLocal
    from .models.task import Task
    from .services.task_service import TaskService as _TS
    from .models.transition import TaskTransition

    db = SessionLocal()
    try:
        threshold = datetime.utcnow() - timedelta(seconds=5)
        todo_tasks = list(db.execute(
            select(Task).where(Task.status == "todo", Task.claimed_at.is_(None))
        ).scalars())
        auto_claimed = 0
        for tt in todo_tasks:
            tt_updated = tt.updated_at
            if tt_updated and tt_updated.replace(tzinfo=None) < threshold.replace(tzinfo=None):
                tt.status = "in_progress"
                tt.claimed_at = datetime.utcnow()
                tt.updated_at = tt.claimed_at
                # assigned_role wird NICHT hier gesetzt. SOP-Engine verwaltet das.
                # Fix (User-Direktive 19.06.2026): Agent aus Task ableiten, damit
                # die Performance-Tabelle den echten Coding-Agent zeigt (nicht 'system').
                auto_claim_agent = _TS._resolve_auto_claim_agent(tt) or "system"
                # Fix (User-Direktive 18.06.2026): Reihenfolge ist jetzt ATOMAR:
                # 1. Status setzen (im Memory)
                # 2. History-Eintrag erstellen
                # 3. Transition erstellen
                # 4. db.commit() einmal am Ende (nicht zwischen den Schritten)
                # So verhindern wir DB-Inkonsistenzen bei Server-Crash zwischen den Schritten.
                _TS._add_history(db, tt, "auto_claim", agent=auto_claim_agent,
                                   details={"reason": "persistent_auto_claim_sop_step_1_to_2",
                                            "assigned_role": tt.assigned_role,
                                            "assigned_subagent": tt.assigned_subagent,
                                            "triggered_by": "persistent_auto_claim_watcher"})
                # Session-ID ermitteln (PFLICHT: Performance-Tabelle muss Session zuordnen koennen)
                from .services.session_helper import get_session_id
                _transition_session_id = get_session_id()
                if not _transition_session_id:
                    logger.warning(
                        f"[session-id] TaskTransition ohne session_id fuer Task {tt.id[:8]} "
                        f"todo->in_progress reason=persistent_auto_claim. session_helper lieferte leer."
                    )
                    _transition_session_id = "session-unknown"
                tr = TaskTransition(
                    task_id=tt.id, project_id=tt.project_id,
                    from_status="todo", to_status="in_progress",
                    transition_at=tt.claimed_at, processing_at=tt.claimed_at,
                    completed_at=tt.claimed_at, delay_s=0.0, duration_ms=0,
                    session_id=_transition_session_id,
                    agent=auto_claim_agent, reason="persistent_auto_claim",
                    details={"assigned_role": tt.assigned_role,
                             "assigned_subagent": tt.assigned_subagent,
                             "trigger": "persistent_watcher"},
                )
                db.add(tr)
                # Atomarer Commit am Ende (alles oder nichts)
                try:
                    db.commit()
                except Exception as e:
                    logger.error(f"Auto-Claim fuer {tt.id[:12]} fehlgeschlagen: {e}")
                    db.rollback()
                    continue
                auto_claimed += 1
        if auto_claimed > 0:
            db.commit()
            logger.info(f"Auto-Claim-Watcher: {auto_claimed} Tasks von todo -> in_progress")
        return {"ok": True, "auto_claimed": auto_claimed, "todo_total": len(todo_tasks)}
    finally:
        db.close()


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """Startet den Auto-Backup-Scheduler (taeglich um 02:00 UTC) UND den Auto-Triage-Operator (alle 30s)."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("Scheduler laeuft bereits")
        return

    _scheduler = AsyncIOScheduler()
    # Taeglich um 02:00 UTC: Auto-Backup
    _scheduler.add_job(
        create_backup_task,
        CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="daily_backup",
        name="Daily SQLite Backup",
        replace_existing=True,
    )

    # Taeglich um 03:00 UTC: Task-Archivierung (User-Direktive 24.06.2026)
    # Verschiebt done- und cancelled-Tasks aelter als 1 Tag in die Archiv-DB
    # um die operative DB klein zu halten.
    try:
        from .services.archive_service import archive_done_tasks
        from .db.base import SessionLocal as _ArchSessionLocal

        def _archive_job():
            """Cron-Job: Archive done/cancelled tasks older than 1 day."""
            try:
                with _ArchSessionLocal() as arch_db:
                    result = archive_done_tasks(
                        arch_db,
                        keep_last_n_done=10,
                        keep_last_n_cancelled=10,
                        archive_older_than_days=1.0,
                    )
                    logger.info(
                        f"Auto-Archivierung: done={result.get('done_archived', 0)}, "
                        f"cancelled={result.get('cancelled_archived', 0)}, "
                        f"errors={len(result.get('errors', []))}"
                    )
            except Exception as e:
                logger.error(f"Auto-Archivierung fehlgeschlagen: {e}")

        _scheduler.add_job(
            _archive_job,
            CronTrigger(hour=3, minute=0, timezone="UTC"),
            id="daily_task_archive",
            name="Daily Task Archive (>1d old)",
            replace_existing=True,
        )
        logger.info("Task-Archivierung aktiviert (taeglich 03:00 UTC, done+cancelled > 1 Tag)")
    except ImportError as ie:
        logger.warning(f"Task-Archivierung konnte nicht geladen werden: {ie}")
    # Alle 30s: Auto-Triage-Operator (CIO auto-evaluate)
    if TRIAGE_OPERATOR_ENABLED:
        from apscheduler.triggers.interval import IntervalTrigger
        _scheduler.add_job(
            auto_triage_evaluate_task,
            IntervalTrigger(seconds=TRIAGE_OPERATOR_INTERVAL_SEC),
            id="auto_triage_operator",
            name=f"Auto-Triage-Operator (alle {TRIAGE_OPERATOR_INTERVAL_SEC}s)",
            replace_existing=True,
        )
        # NEU (User-Direktive 17.06.2026): Persistent Auto-Claim-Watcher als separater Job.
        # Findet alle Tasks mit status=todo + claimed_at IS NULL + updated_at >= 5s alt
        # und macht auto-claim (-> in_progress). Robust gegen Server-Restarts.
        _scheduler.add_job(
            persistent_auto_claim_watcher,
            IntervalTrigger(seconds=15),  # alle 15s pruefen
            id="auto_claim_watcher",
            name="Persistent Auto-Claim-Watcher (alle 15s)",
            replace_existing=True,
        )
        # NEU (User-Direktive 19.06.2026): Agent-Cleanup-Service
        # 1. In-Progress-Tasks mit toter PID auf 'todo' zuruecksetzen (max 3 Retries)
        # 2. Tasks > 2h in 'in_progress' auf 'rueckfrage' eskalieren
        # 3. Budget ueberwachen und bei Ueberschreitung Worker-Loop stoppen
        # Implementiert in worker_service.py (nicht als eigene Datei, weil
        # neue .py-Dateien im Backend-Verzeichnis geloescht werden).
        try:
            from .services.worker_service import run_agent_cleanup
            from .services.worker_service import CLEANUP_INTERVAL_SEC
            _scheduler.add_job(
                run_agent_cleanup,
                IntervalTrigger(seconds=CLEANUP_INTERVAL_SEC),
                id="agent_cleanup",
                name=f"Agent-Cleanup-Service (alle {CLEANUP_INTERVAL_SEC}s)",
                replace_existing=True,
            )
            logger.info(f"Agent-Cleanup-Service aktiviert (alle {CLEANUP_INTERVAL_SEC}s)")
        except ImportError as ie:
            logger.warning(f"Agent-Cleanup-Service konnte nicht geladen werden: {ie}")
        # NEU (User-Direktive 19.06.2026): File-Watcher
        # Erkennt geloeschte .py-Dateien und stellt sie aus Git HEAD wieder her.
        # Hintergrund: Im Backend werden regelmaessig .py-Dateien automatisch geloescht
        # (z.B. voice_config.py, agent_cleanup.py), was zu ImportError fuehrt.
        try:
            from .services.worker_service import run_file_watcher
            from .services.worker_service import WATCHER_INTERVAL_SEC
            _scheduler.add_job(
                run_file_watcher,
                IntervalTrigger(seconds=WATCHER_INTERVAL_SEC),
                id="file_watcher",
                name=f"File-Watcher (alle {WATCHER_INTERVAL_SEC}s)",
                replace_existing=True,
            )
            logger.info(f"File-Watcher aktiviert (alle {WATCHER_INTERVAL_SEC}s)")
        except ImportError as ie:
            logger.warning(f"File-Watcher konnte nicht geladen werden: {ie}")
        logger.info(f"Auto-Triage-Operator aktiviert (alle {TRIAGE_OPERATOR_INTERVAL_SEC}s) + Auto-Claim-Watcher (alle 15s)")
    _scheduler.start()
    logger.info("Scheduler gestartet (Auto-Backup taeglich 02:00 UTC + Auto-Triage-Operator)")


def stop_scheduler() -> None:
    """Stoppt den Scheduler (z.B. bei Shutdown)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Auto-Backup-Scheduler gestoppt")
