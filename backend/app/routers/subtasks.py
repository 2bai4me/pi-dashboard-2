"""Subtasks API: Sub-Tasks mit Parent-Beziehung, Planung, Session-ID.

User-Direktive 23.06.2026 (Task 61ab3dfe26d3):
- Jeder SubTask bekommt eigene Planung (Stufen + Inhalte)
- SubTask wird an eigenen Agenten abgegeben
- Session-ID wird dokumentiert
- Kosten + Token werden pro Subtask erfasst
- Performance-Tabelle: parent_task_id Beziehung
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db

logger = logging.getLogger("pi-dashboard-2.subtasks")
router = APIRouter(prefix="/api/subtasks", tags=["subtasks"])


# === Pydantic-Schemas ===

class PlanStep(BaseModel):
    step: str = Field(..., description="Stufen-Beschreibung, z.B. 'Datenmodell erstellen'")
    content: str = Field(..., description="Inhalt der Stufe")
    agent: Optional[str] = Field(None, description="Verantwortlicher Agent")


class PlanIn(BaseModel):
    steps: List[PlanStep] = Field(default_factory=list)


class SubTaskIn(BaseModel):
    parent_task_id: str
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    assigned_subagent: Optional[str] = None
    plan: Optional[PlanIn] = None
    priority: int = 50
    category: str = "new_request"
    session_id: Optional[str] = None


class SubTaskOut(BaseModel):
    id: str
    parent_task_id: str
    project_id: Optional[str]
    title: str
    description: Optional[str]
    status: str
    priority: int
    assigned_subagent: Optional[str]
    plan: Optional[PlanIn]
    session_id: Optional[str]
    result: Optional[dict]
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    created_at: Optional[str]
    updated_at: Optional[str]


# === Helper ===

def _row_to_subtask(row, plan: Optional[dict] = None, tokens_in: int = 0,
                     tokens_out: int = 0, cost_usd: float = 0.0) -> dict:
    import json
    from .subtasks import PlanIn
    plan_obj = plan
    if plan_obj is None:
        # Plan ist in task.meta (JSON) gespeichert, nicht als eigene Spalte
        meta_raw = row["meta"] if "meta" in row.keys() else None
        if meta_raw:
            try:
                meta_dict = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                plan_data = meta_dict.get("plan") if isinstance(meta_dict, dict) else None
                if isinstance(plan_data, dict):
                    plan_obj = PlanIn(**plan_data)
            except (json.JSONDecodeError, TypeError):
                plan_obj = None
    return {
        "id": row["id"],
        "parent_task_id": row["parent_id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "assigned_subagent": row["assigned_subagent"],
        "plan": plan_obj,
        "session_id": row["session_id"] if "session_id" in row.keys() else None,
        "result": None,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# === Endpoints ===

@router.get("", response_model=List[SubTaskOut])
def list_subtasks(
    parent_task_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    _user: str = Depends(require_auth),
):
    """Liste aller Sub-Tasks (gefiltert nach parent_task_id)."""
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where = ["parent_id IS NOT NULL"]
    params = []
    if parent_task_id:
        where.append("parent_id = ?")
        params.append(parent_task_id)
    if status:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM tasks WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    # Aggregate token-usage per task
    cur.execute("""SELECT task_id, SUM(tokens_in), SUM(tokens_out), SUM(cost_usd)
                   FROM token_usage WHERE task_id IN ({}) GROUP BY task_id""".format(
        ",".join("?" * len(rows))
    ), [r["id"] for r in rows])
    usage = {r[0]: {"tokens_in": r[1] or 0, "tokens_out": r[2] or 0, "cost_usd": float(r[3] or 0)}
             for r in cur.fetchall()}
    conn.close()
    return [
        _row_to_subtask(
            dict(r),
            tokens_in=usage.get(r["id"], {}).get("tokens_in", 0),
            tokens_out=usage.get(r["id"], {}).get("tokens_out", 0),
            cost_usd=usage.get(r["id"], {}).get("cost_usd", 0.0),
        )
        for r in rows
    ]


@router.post("", response_model=SubTaskOut, status_code=201)
def create_subtask(
    req: SubTaskIn,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Neuen Sub-Task mit Planung erstellen."""
    from ..models.task import Task
    from ..models.history import TaskHistory
    from ..models.token_usage import TokenUsage
    import os
    import sqlite3
    import json

    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper.
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Parent-Task lesen
    cur.execute("SELECT id, project_id FROM tasks WHERE id = ?", (req.parent_task_id,))
    parent = cur.fetchone()
    if not parent:
        conn.close()
        raise HTTPException(404, f"Parent-Task {req.parent_task_id} nicht gefunden")

    # Sub-Task anlegen (session_id wird in task_history gespeichert, nicht in tasks)
    subtask_id = secrets.token_hex(6)
    now = datetime.now(timezone.utc).isoformat()
    plan_json = json.dumps(req.plan.dict() if req.plan else {})
    cur.execute("""INSERT INTO tasks
                   (id, project_id, parent_id, title, description, status,
                    priority, category, assigned_subagent,
                    iteration_count, "order", emergency,
                    worker_understanding_confirmed, review_iteration_count,
                    bza_iteration_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (subtask_id, parent["project_id"], req.parent_task_id,
                 req.title, req.description or "", "todo",
                 req.priority, req.category, req.assigned_subagent,
                 0, 0, 0, 0, 0, 0))
    # Plan in meta speichern — direkt als Dict (SQLite macht JSON-Encoding automatisch)
    meta_with_plan = {"plan": req.plan.dict() if req.plan else {}}
    cur.execute("UPDATE tasks SET meta = ? WHERE id = ?", (json.dumps(meta_with_plan), subtask_id))
    conn.commit()

    # History mit Session-ID
    cur.execute("""INSERT INTO task_history
                   (task_id, event, agent, model, tokens_in, tokens_out, cost_usd, details, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (subtask_id, "subtask_created",
                 req.assigned_subagent or "user",
                 None, 0, 0, 0.0,
                 json.dumps({
                     "parent_task_id": req.parent_task_id,
                     "plan_steps_count": len(req.plan.steps) if req.plan else 0,
                 }),
                 req.session_id))

    # TokenUsage-Eintrag mit parent_task_id (Performance-Tabelle)
    cur.execute("""INSERT INTO token_usage
                   (task_id, parent_task_id, model, provider, role,
                    tokens_in, tokens_out, cost_usd, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (subtask_id, req.parent_task_id, "minimax-m3", "minimax-direct",
                 req.assigned_subagent or "user",
                 0, 0, 0.0, now))
    conn.commit()
    cur.execute("SELECT * FROM tasks WHERE id = ?", (subtask_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_subtask(dict(row))


@router.get("/{subtask_id}", response_model=SubTaskOut)
def get_subtask(subtask_id: str, _user: str = Depends(require_auth)):
    """Einen Sub-Task abrufen."""
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper.
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = ? AND parent_id IS NOT NULL", (subtask_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Sub-Task {subtask_id} nicht gefunden")
    cur.execute("""SELECT SUM(tokens_in), SUM(tokens_out), SUM(cost_usd)
                   FROM token_usage WHERE task_id = ?""", (subtask_id,))
    usage = cur.fetchone()
    conn.close()
    return _row_to_subtask(
        dict(row),
        tokens_in=usage[0] or 0,
        tokens_out=usage[1] or 0,
        cost_usd=float(usage[2] or 0),
    )


@router.put("/{subtask_id}/plan")
def update_subtask_plan(
    subtask_id: str,
    req: PlanIn,
    _user: str = Depends(require_auth),
):
    """Planung eines Sub-Tasks aktualisieren."""
    import os
    import sqlite3
    import json
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper.
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    plan_json = json.dumps(req.dict())
    cur.execute("""UPDATE tasks SET meta = json_set(COALESCE(meta, '{}'), '$.plan', ?),
                                 updated_at = ?
                   WHERE id = ? AND parent_id IS NOT NULL""",
                (plan_json, datetime.now(timezone.utc).isoformat(), subtask_id))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(404, f"Sub-Task {subtask_id} nicht gefunden")
    conn.close()
    return {"ok": True, "subtask_id": subtask_id, "steps_count": len(req.steps)}


@router.post("/{subtask_id}/result")
def submit_subtask_result(
    subtask_id: str,
    result: dict,
    _user: str = Depends(require_auth),
):
    """Sub-Task-Ergebnis zurueckgeben."""
    import os
    import sqlite3
    import json
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper.
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET meta = json_set(COALESCE(meta, '{}'), '$.result', ?), "
                "updated_at = ?, status = COALESCE(?, status) "
                "WHERE id = ? AND parent_id IS NOT NULL",
                (json.dumps(result), datetime.now(timezone.utc).isoformat(),
                 result.get("status", "review"), subtask_id))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(404, f"Sub-Task {subtask_id} nicht gefunden")
    # History mit Session-ID
    cur.execute("""INSERT INTO task_history
                   (task_id, event, agent, details, session_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (subtask_id, "subtask_result_submitted",
                 result.get("agent", "system"),
                 json.dumps({"result_keys": list(result.keys())}),
                 result.get("session_id")))
    conn.commit()
    conn.close()
    return {"ok": True, "subtask_id": subtask_id, "status": "review"}