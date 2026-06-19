"""Worker-Loop — Background-Task der automatisch Tasks abarbeitet.

Startet beim App-Startup, laeuft alle 60 Sekunden.
Prueft auf `todo`-Tasks, claimed einen, laesst den LLM-Worker arbeiten.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("pi-dashboard-2.worker-loop")

# Konfiguration via ENV
WORKER_LOOP_ENABLED = os.getenv("WORKER_LOOP_ENABLED", "true").lower() == "true"
WORKER_LOOP_INTERVAL_SEC = int(os.getenv("WORKER_LOOP_INTERVAL_SEC", "60"))
WORKER_MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT", "1"))

_worker_task = None
_worker_stop = False


async def worker_loop_iteration() -> dict:
    """Eine Loop-Iteration: 1 Task claimen + ausfuehren."""
    from .worker_service import WorkerService
    from .session_helper import init_session_id

    # Worker-Loop hat eine eigene Session-ID
    init_session_id(force_type="worker")

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
