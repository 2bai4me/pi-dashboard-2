"""Ideas API: CRUD fuer die Idee-Page.

User-Direktive 23.06.2026: Idee-Page braucht Neu/Speichern/Loeschen/Umsetzen.
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

logger = logging.getLogger("pi-dashboard-2.ideas")
router = APIRouter(prefix="/api/ideas", tags=["ideas"])


# === Pydantic-Schemas ===

class IdeaIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    brainstorm: Optional[str] = None
    requirements: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = "draft"


class IdeaOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    brainstorm: Optional[str]
    requirements: Optional[str]
    status: str
    tags: Optional[List[str]]
    created_at: Optional[str]
    updated_at: Optional[str]


# === Helper ===

def _row_to_dict(row) -> dict:
    import json
    tags = row["tags"]
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = []
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "brainstorm": row["brainstorm"],
        "requirements": row["requirements"],
        "status": row["status"],
        "tags": tags,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _list_ideas_impl(status=None, limit=100, _user="testuser"):
    """Implementierung der Idee-Liste (testbar ohne FastAPI)."""
    import sqlite3
    import os
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where = []
    params = []
    if status:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM ideas"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(dict(r)) for r in rows]


def _get_idea_impl(idea_id, _user="testuser"):
    """Implementierung get_idea (testbar)."""
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, f"Idee {idea_id} nicht gefunden")
    return _row_to_dict(dict(row))


def _delete_idea_impl(idea_id, _user="testuser"):
    """Implementierung delete_idea (testbar)."""
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(404, f"Idee {idea_id} nicht gefunden")
    return None


# === Endpoints ===

@router.get("", response_model=List[IdeaOut])
def list_ideas(
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    _user: str = Depends(require_auth),
):
    """Liste aller Ideen."""
    import sqlite3
    import os
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where = []
    params = []
    if status:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM ideas"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(dict(r)) for r in rows]


@router.post("", response_model=IdeaOut, status_code=201)
def create_idea(
    req: IdeaIn,
    _user: str = Depends(require_auth),
):
    """Neue Idee erstellen."""
    import json
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    idea_id = f"idea-{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("""
        INSERT INTO ideas (id, title, description, brainstorm, requirements, status, tags, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (idea_id, req.title, req.description or "", req.brainstorm or "",
          req.requirements or "", req.status or "draft",
          json.dumps(req.tags or []), now, now))
    conn.commit()
    cur.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(dict(row))


@router.get("/{idea_id}", response_model=IdeaOut)
def get_idea(idea_id: str, _user: str = Depends(require_auth)):
    """Eine Idee abrufen."""
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Idee {idea_id} nicht gefunden")
    return _row_to_dict(dict(row))


@router.put("/{idea_id}", response_model=IdeaOut)
def update_idea(
    idea_id: str,
    req: IdeaIn,
    _user: str = Depends(require_auth),
):
    """Idee aktualisieren (Speichern)."""
    import json
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id FROM ideas WHERE id = ?", (idea_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(404, f"Idee {idea_id} nicht gefunden")
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("""
        UPDATE ideas
        SET title = ?, description = ?, brainstorm = ?, requirements = ?,
            status = ?, tags = ?, updated_at = ?
        WHERE id = ?
    """, (req.title, req.description or "", req.brainstorm or "",
          req.requirements or "", req.status or "draft",
          json.dumps(req.tags or []), now, idea_id))
    conn.commit()
    cur.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(dict(row))


@router.delete("/{idea_id}", status_code=204)
def delete_idea(idea_id: str, _user: str = Depends(require_auth)):
    """Idee loeschen."""
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(404, f"Idee {idea_id} nicht gefunden")
    conn.close()
    return None


@router.post("/{idea_id}/umsetzen", response_model=dict)
def convert_idea_to_task(
    idea_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Konvertiert Idee zu Task im aktuellen Projekt.

    Erstellt einen neuen Task mit Title + Description aus der Idee.
    Setzt Ideen-Status auf 'converted'.
    """
    from ..models.task import Task
    from ..models.history import TaskHistory
    import os
    import sqlite3
    # CLEANUP-AUDIT 23.06.2026: Zentraler Helper (relativer Pfad brach bei wechselndem CWD).
    from ..utils.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Idee {idea_id} nicht gefunden")
    idea = dict(row)
    conn.close()

    # Task erstellen
    task_id = secrets.token_hex(6)
    task = Task(
        id=task_id,
        title=idea["title"],
        description=(idea.get("description") or "") + "\n\n--- Brainstorm ---\n" + (idea.get("brainstorm") or "") +
                  "\n\n--- Requirements ---\n" + (idea.get("requirements") or ""),
        status="triage",
        priority=50,
        category="new_request",
        iteration_count=0,
        order=0,
        emergency=False,
        worker_understanding_confirmed=False,
        review_iteration_count=0,
        bza_iteration_count=0,
        assigned_role="CIO",
    )
    db.add(task)
    db.flush()
    db.add(TaskHistory(
        task_id=task_id,
        event="task_created_from_idea",
        agent="user",
        details={"idea_id": idea_id, "source": "idee_page"},
    ))
    db.commit()
    db.refresh(task)

    # Ideen-Status auf 'converted' setzen
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE ideas SET status = ?, updated_at = ? WHERE id = ?",
                ("converted", datetime.now(timezone.utc).isoformat(), idea_id))
    conn.commit()
    conn.close()

    return {"ok": True, "task_id": task_id, "idea_id": idea_id, "status": "converted"}