"""SSE-Events fuer Swarm-Live-Updates (Phase 14).

User-Direktive 22.06.2026: Frontend soll Swarm-Fortschritt in Echtzeit sehen.
Server-Sent Events (SSE) statt Polling, damit das Frontend nicht staendig
das Backend abfragen muss.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from typing import AsyncGenerator

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("pi-dashboard-2.swarm_sse")
router = APIRouter(prefix="/api/swarms", tags=["swarms-sse"])


def _get_swarm_status(swarm_id: str) -> dict:
    """Laedt aktuellen Swarm-Status aus der DB."""
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM swarm_runs WHERE id = ?", (swarm_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {}
    cols = [d[0] for d in cur.description]
    run = dict(zip(cols, row))
    cur.execute("SELECT * FROM swarm_workers WHERE swarm_run_id = ?", (swarm_id,))
    w_cols = [d[0] for d in cur.description]
    run["workers"] = [dict(zip(w_cols, w)) for w in cur.fetchall()]
    if isinstance(run.get("result"), str):
        try:
            run["result"] = json.loads(run["result"])
        except json.JSONDecodeError:
            pass
    conn.close()
    return run


@router.get("/{swarm_id}/events")
async def swarm_events(swarm_id: str, interval: float = Query(2.0, ge=0.5, le=10.0)):
    """SSE-Stream fuer Swarm-Live-Updates.

    Sendet regelmaessig (alle `interval` Sekunden) den aktuellen Status.
    Stoppt automatisch, wenn der Swarm completed/failed ist.
    """
    async def event_generator() -> AsyncGenerator[dict, None]:
        last_status = None
        last_worker_statuses = {}
        max_iterations = 600  # Max 20 Minuten (600 * 2s)
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            try:
                run = await asyncio.to_thread(_get_swarm_status, swarm_id)
                if not run:
                    yield {"event": "error", "data": json.dumps({"error": f"Swarm {swarm_id} nicht gefunden"})}
                    break

                current_status = run.get("status")
                current_worker_statuses = {w["id"]: w["status"] for w in run.get("workers", [])}

                # Sende Update nur bei Aenderung
                if (current_status != last_status
                    or current_worker_statuses != last_worker_statuses):
                    payload = {
                        "swarm_id": swarm_id,
                        "status": current_status,
                        "swarm_type": run.get("swarm_type"),
                        "total_cost_usd": run.get("total_cost_usd", 0.0),
                        "workers": [
                            {
                                "id": w["id"],
                                "role": w.get("subagent_role"),
                                "variant": w.get("variant"),
                                "status": w.get("status"),
                                "cost_usd": w.get("cost_usd", 0.0),
                            }
                            for w in run.get("workers", [])
                        ],
                    }
                    if run.get("result") and isinstance(run["result"], dict):
                        merged = run["result"].get("merged_output", {})
                        if isinstance(merged, dict):
                            payload["consensus_score"] = merged.get("avg_score")
                            payload["auto_approved"] = merged.get("auto_approve")
                    yield {"event": "swarm_update", "data": json.dumps(payload, default=str)}
                    last_status = current_status
                    last_worker_statuses = current_worker_statuses

                # Heartbeat (jede 5. Iteration)
                if iteration % 5 == 0:
                    yield {"event": "heartbeat", "data": json.dumps({"iteration": iteration})}

                # Stop bei completed/failed
                if current_status in ("completed", "failed"):
                    yield {"event": "swarm_done", "data": json.dumps({"final_status": current_status})}
                    break

                await asyncio.sleep(interval)
            except Exception as e:
                logger.exception(f"SSE-Generator-Fehler: {e}")
                yield {"event": "error", "data": json.dumps({"error": str(e)})}
                break

    return EventSourceResponse(event_generator())