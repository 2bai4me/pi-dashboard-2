"""Swarm-API: Multi-Agent-Swarm steuern.

User-Direktive 22.06.2026: Frontend und externe Tools koennen Swarms
starten und deren Status abfragen.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db
from ..services.swarm_spawner import (
    SwarmConfig, WorkerConfig, SwarmType, MergeStrategy,
    SWARM_CONFIGS, create_swarm_run, execute_swarm, get_swarm_run,
)

logger = logging.getLogger("pi-dashboard-2.swarm_api")
router = APIRouter(prefix="/api/swarms", tags=["swarms"])


# === Pydantic-Schemas ===

class WorkerConfigIn(BaseModel):
    role: str
    variant: str = "default"
    weight: float = 1.0
    system_prompt: Optional[str] = None


class SpawnSwarmRequest(BaseModel):
    task_id: str
    sop_instance_id: Optional[str] = None
    step_id: Optional[str] = None
    swarm_type: str = "parallel"
    workers: List[WorkerConfigIn] = Field(..., min_length=1)
    merge_strategy: str = "reviewer_picks_best"
    consensus_threshold: float = 75.0
    auto_approve_threshold: float = 90.0
    max_cost_usd: float = 0.50
    timeout_sec: int = 600
    stage_key: Optional[str] = None


class WorkerOut(BaseModel):
    id: str
    subagent_role: str
    variant: Optional[str]
    weight: float
    status: str
    cost_usd: float
    score: Optional[float]
    started_at: Optional[str]
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class SwarmRunOut(BaseModel):
    id: str
    task_id: Optional[str]
    sop_instance_id: Optional[str]
    step_id: Optional[str]
    swarm_type: str
    status: str
    merge_strategy: Optional[str]
    consensus_threshold: float
    auto_approve_threshold: float
    total_cost_usd: float
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[dict]
    workers: List[WorkerOut]

    class Config:
        from_attributes = True


# === Endpoints ===

@router.post("", response_model=SwarmRunOut, status_code=201)
async def spawn_swarm(
    req: SpawnSwarmRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Startet einen neuen Swarm."""
    # Stage-Key hat Vorrang
    if req.stage_key and req.stage_key in SWARM_CONFIGS:
        config = SWARM_CONFIGS[req.stage_key]
    else:
        try:
            config = SwarmConfig(
                swarm_type=SwarmType(req.swarm_type),
                workers=[WorkerConfig(**w.dict(exclude_none=True)) for w in req.workers],
                merge_strategy=MergeStrategy(req.merge_strategy),
                consensus_threshold=req.consensus_threshold,
                auto_approve_threshold=req.auto_approve_threshold,
                max_cost_usd=req.max_cost_usd,
                timeout_sec=req.timeout_sec,
            )
        except (ValueError, KeyError) as e:
            raise HTTPException(400, f"Ungueltige Swarm-Konfiguration: {e}")

    swarm_id = create_swarm_run(
        task_id=req.task_id,
        sop_instance_id=req.sop_instance_id or "",
        step_id=req.step_id or "",
        config=config,
    )

    # Sofort ausfuehren (Background-Task koennte spaeter kommen)
    result = await execute_swarm(swarm_id, task_context={"task_id": req.task_id})
    return _run_out(swarm_id)


@router.get("/{swarm_id}", response_model=SwarmRunOut)
def get_swarm(swarm_id: str, _user: str = Depends(require_auth)):
    """Liefert Swarm-Status inkl. aller Worker."""
    run = get_swarm_run(swarm_id)
    if not run:
        raise HTTPException(404, f"Swarm {swarm_id} nicht gefunden")
    return _run_dict_to_out(run)


@router.get("", response_model=List[SwarmRunOut])
def list_swarms(
    task_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    _user: str = Depends(require_auth),
):
    """Listet Swarms, optional gefiltert nach task_id und status."""
    import sqlite3
    import json
    import os
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    where = []
    params = []
    if task_id:
        where.append("task_id = ?")
        params.append(task_id)
    if status:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM swarm_runs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    runs = [dict(zip(cols, r)) for r in cur.fetchall()]
    # Worker fuer jeden Run laden
    for run in runs:
        cur.execute("SELECT * FROM swarm_workers WHERE swarm_run_id = ?", (run["id"],))
        w_cols = [d[0] for d in cur.description]
        run["workers"] = [dict(zip(w_cols, w)) for w in cur.fetchall()]
        if isinstance(run.get("result"), str):
            try:
                run["result"] = json.loads(run["result"])
            except json.JSONDecodeError:
                pass
    conn.close()
    return [_run_dict_to_out(r) for r in runs]


def _run_out(swarm_id: str) -> SwarmRunOut:
    run = get_swarm_run(swarm_id)
    if not run:
        raise HTTPException(404, "Swarm nicht gefunden")
    return _run_dict_to_out(run)


def _run_dict_to_out(run: dict) -> SwarmRunOut:
    """Konvertiert DB-Dict zu Pydantic-Schema (parst JSON-Felder)."""
    import json
    if isinstance(run.get("workers_config"), str):
        try:
            run["workers_config"] = json.loads(run["workers_config"])
        except json.JSONDecodeError:
            pass
    if isinstance(run.get("result"), str):
        try:
            run["result"] = json.loads(run["result"])
        except json.JSONDecodeError:
            pass
    return SwarmRunOut(**run)