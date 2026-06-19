"""Worker-Loop — Background-Task der automatisch Tasks abarbeitet.

Startet beim App-Startup, laeuft alle 60 Sekunden.
Prueft auf `todo`-Tasks, claimed einen, laesst den LLM-Worker arbeiten.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger("pi-dashboard-2.worker-loop")

# Konfiguration via ENV
WORKER_LOOP_ENABLED = os.getenv("WORKER_LOOP_ENABLED", "true").lower() == "true"
WORKER_LOOP_INTERVAL_SEC = int(os.getenv("WORKER_LOOP_INTERVAL_SEC", "60"))
WORKER_MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT", "1"))

_worker_task = None
_worker_stop = False
# === Budget-Override (gesetzt vom Agent-Cleanup-Service, User-Direktive 19.06.2026) ===
# Wenn True: Worker-Loop ueberspringt ALLE Iterationen, bis das Flag zurueckgesetzt wird.
# Zweck: Schutz gegen unkontrollierte Kosten. Wird vom agent_cleanup.py alle 60s
# basierend auf TokenUsage-Aggregation gesetzt.
_budget_exceeded: bool = False


def is_budget_exceeded() -> bool:
    """Gibt zurueck, ob das Budget-Limit aktuell ueberschritten ist.

    Wird von worker_loop_iteration() geprueft, bevor ein Task geclaimt wird.
    """
    return _budget_exceeded


def set_budget_exceeded(value: bool) -> None:
    """Setzt das Budget-Override-Flag (vom Agent-Cleanup-Service aufgerufen).

    Bei True: Worker-Loop pausiert bis zum naechsten Cleanup-Run.
    Bei False: Worker-Loop laeuft normal weiter.
    """
    global _budget_exceeded
    if value and not _budget_exceeded:
        logger.warning(
            "BUDGET EXCEEDED: Worker-Loop pausiert. "
            "Wird durch Agent-Cleanup-Service zurueckgesetzt, "
            "sobald Budget wieder unter Critical-Threshold."
        )
    elif not value and _budget_exceeded:
        logger.info("Budget-Override aufgehoben: Worker-Loop laeuft wieder.")
    _budget_exceeded = value


async def worker_loop_iteration() -> dict:
    """Eine Loop-Iteration: 1 Task claimen + ausfuehren."""
    from .worker_service import WorkerService
    from .session_helper import init_session_id

    # Worker-Loop hat eine eigene Session-ID
    init_session_id(force_type="worker")

    # === Budget-Guard (User-Direktive 19.06.2026) ===
    # Wenn der Agent-Cleanup-Service das Flag gesetzt hat, KEINE neuen Tasks
    # claimen. Bestehende laufende Tasks laufen aus, neue werden uebersprungen.
    if is_budget_exceeded():
        logger.debug("Worker-Loop: Budget-Override aktiv, ueberspringe Iteration")
        return {"claimed": False, "skipped": True, "reason": "budget_exceeded"}

    # 1) Naechsten Task holen
    try:
        task = WorkerService.claim_next_task()
    except Exception as e:
        logger.error(f"claim_next_task fehlgeschlagen: {e}")
        return {"claimed": False, "error": str(e)}

    if not task:
        return {"claimed": False, "reason": "no_todo_tasks"}

    # 2) Task ausfuehren
    try:
        result = await WorkerService.execute_task(task)
        return {
            "claimed": True,
            "task_id": task.id,
            "ok": result.get("ok", False),
            "error": result.get("error"),
        }
    except Exception as e:
        logger.error(f"execute_task fehlgeschlagen fuer {task.id}: {e}")
        return {"claimed": True, "task_id": task.id, "ok": False, "error": str(e)}


async def _worker_loop_main() -> None:
    """Haupt-Loop: alle WORKER_LOOP_INTERVAL_SEC Sekunden eine Iteration."""
    logger.info(
        f"Worker-Loop gestartet (Intervall: {WORKER_LOOP_INTERVAL_SEC}s, max-concurrent: {WORKER_MAX_CONCURRENT})"
    )
    while not _worker_stop:
        try:
            result = await worker_loop_iteration()
            if result.get("claimed"):
                logger.info(
                    f"Worker-Loop: Task {result.get('task_id', '?')[:12]} -> ok={result.get('ok')}"
                )
            elif result.get("skipped") and result.get("reason") == "budget_exceeded":
                # Budget-Override aktiv — logge nur einmal pro 5 Minuten
                if not hasattr(_worker_loop_main, "_last_budget_log") or \
                   (time.time() - _worker_loop_main._last_budget_log) > 300:
                    logger.info(
                        "Worker-Loop pausiert (Budget-Override aktiv, "
                        "wird durch Agent-Cleanup-Service ueberwacht)"
                    )
                    _worker_loop_main._last_budget_log = time.time()
        except Exception as e:
            logger.error(f"Worker-Loop-Iteration fehlgeschlagen: {e}")
        # Naechste Iteration
        for _ in range(WORKER_LOOP_INTERVAL_SEC):
            if _worker_stop:
                break
            await asyncio.sleep(1)
    logger.info("Worker-Loop beendet")


async def start_worker_loop() -> None:
    """Startet den Worker-Loop als Background-Task."""
    global _worker_task, _worker_stop
    if not WORKER_LOOP_ENABLED:
        logger.info("Worker-Loop ist deaktiviert (WORKER_LOOP_ENABLED=false)")
        return
    if _worker_task and not _worker_task.done():
        logger.warning("Worker-Loop laeuft bereits")
        return
    _worker_stop = False
    _worker_task = asyncio.create_task(_worker_loop_main())
    logger.info("Worker-Loop-Task erstellt")


async def stop_worker_loop() -> None:
    """Stoppt den Worker-Loop (z.B. bei App-Shutdown)."""
    global _worker_task, _worker_stop
    _worker_stop = True
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info("Worker-Loop gestoppt")
