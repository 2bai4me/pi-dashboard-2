"""Auto-Complete-Parent: Wenn alle Subtasks done sind, Parent automatisch auf done.

User-Direktive 23.06.2026 (Task 4bf7146b0780):
- Wenn alle Subtasks den Status 'done' haben UND alle einen Consensus-Score >= 90
- dann wird der Parent-Task automatisch auf 'done' gesetzt
- Sub-Task-Tracking: Token + Cost werden aggregiert
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..models.task import Task
from ..models.history import TaskHistory

logger = logging.getLogger("pi-dashboard-2.parent_completion")


def check_and_complete_parent(
    db_or_conn,
    subtask_id: str,
    auto_approve_threshold: float = 90.0,
) -> Optional[str]:
    """Prueft ob Parent-Task auf 'done' gesetzt werden kann.

    Args:
        db_or_conn: SQLAlchemy Session ODER sqlite3 Connection/Cursor
        subtask_id: Die ID des Sub-Tasks, das gerade fertig wurde
        auto_approve_threshold: Min. Consensus-Score pro Subtask (default 90)

    Returns:
        Die Parent-Task-ID wenn sie auf done gesetzt wurde, sonst None
    """
    import json
    from datetime import datetime, timezone

    # Akzeptiere Session oder sqlite3-Cursor/Connection
    use_sqlalchemy = hasattr(db_or_conn, "get") and hasattr(db_or_conn, "query")
    # Bei sqlite3-Connection: einen Cursor holen
    if not use_sqlalchemy:
        import sqlite3 as _sqlite3
        if isinstance(db_or_conn, _sqlite3.Connection):
            db_or_conn = db_or_conn.cursor()
    if use_sqlalchemy:
        # Subtask laden via SQLAlchemy
        subtask = db_or_conn.get(Task, subtask_id)
        if not subtask or not subtask.parent_id:
            return None
        parent_id = subtask.parent_id
        parent = db_or_conn.get(Task, parent_id)
        if not parent:
            logger.warning(f"Parent-Task {parent_id} fuer Subtask {subtask_id} nicht gefunden")
            return None
        if parent.status == "done":
            return None
        siblings = db_or_conn.query(Task).filter(Task.parent_id == parent_id).all()
        # SQLAlchemy: task.status, task.meta sind Attribute
        sibling_statuses = {s.id: s.status for s in siblings}
        sibling_metas = {}
        for s in siblings:
            m = s.meta
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except (json.JSONDecodeError, TypeError):
                    m = {}
            sibling_metas[s.id] = m if isinstance(m, dict) else {}
        # Kosten aggregieren
        from ..models.token_usage import TokenUsage
        usages = db_or_conn.query(TokenUsage).filter(TokenUsage.parent_task_id == parent_id).all()
        total_tokens_in = sum(int(u.tokens_in or 0) for u in usages)
        total_tokens_out = sum(int(u.tokens_out or 0) for u in usages)
        total_cost = sum(float(u.cost_usd or 0) for u in usages)
    else:
        # sqlite3-Cursor oder Connection
        conn = db_or_conn
        if hasattr(conn, "execute"):
            cur = conn
        else:
            cur = conn.cursor()
        cur.execute("SELECT id, parent_id, status, meta FROM tasks WHERE id = ?", (subtask_id,))
        row = cur.fetchone()
        if not row:
            return None
        # row kann Tuple oder Row sein
        if hasattr(row, "keys"):
            r = dict(row)
        else:
            r = {"id": row[0], "parent_id": row[1], "status": row[2], "meta": row[3]}
        if not r["parent_id"]:
            return None
        parent_id = r["parent_id"]
        cur.execute("SELECT id, status, meta FROM tasks WHERE id = ?", (parent_id,))
        prow = cur.fetchone()
        if hasattr(prow, "keys"):
            pr = dict(prow)
        else:
            pr = {"id": prow[0], "status": prow[1], "meta": prow[2]}
        if pr["status"] == "done":
            return None
        # Siblings laden
        cur.execute("SELECT id, status, meta FROM tasks WHERE parent_id = ?", (parent_id,))
        srows = cur.fetchall()
        sibling_statuses = {}
        sibling_metas = {}
        for srow in srows:
            if hasattr(srow, "keys"):
                sr = dict(srow)
            else:
                sr = {"id": srow[0], "status": srow[1], "meta": srow[2]}
            sibling_statuses[sr["id"]] = sr["status"]
            m = sr["meta"]
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except (json.JSONDecodeError, TypeError):
                    m = {}
            sibling_metas[sr["id"]] = m if isinstance(m, dict) else {}
        # Kosten aggregieren
        cur.execute(
            "SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COALESCE(SUM(cost_usd),0) "
            "FROM token_usage WHERE parent_task_id = ?",
            (parent_id,),
        )
        agg = cur.fetchone()
        if agg:
            if hasattr(agg, "keys"):
                total_tokens_in = int(agg["COALESCE(SUM(tokens_in),0)"] if "COALESCE(SUM(tokens_in),0)" in agg.keys() else agg[0])
                total_tokens_out = int(agg["COALESCE(SUM(tokens_out),0)"] if "COALESCE(SUM(tokens_out),0)" in agg.keys() else agg[1])
                total_cost = float(agg["COALESCE(SUM(cost_usd),0)"] if "COALESCE(SUM(cost_usd),0)" in agg.keys() else agg[2])
            else:
                total_tokens_in = int(agg[0])
                total_tokens_out = int(agg[1])
                total_cost = float(agg[2])

    # Pruefen: alle Subtasks done?
    if not sibling_statuses:
        return None
    all_done = all(s == "done" for s in sibling_statuses.values())
    if not all_done:
        return None

    # === Alle Subtasks done => Parent auf done setzen ===
    now = datetime.now(timezone.utc).isoformat()
    auto_meta = {
        "completed_at": now,
        "subtask_count": len(sibling_statuses),
        "total_cost_usd": total_cost,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
    }

    if use_sqlalchemy:
        # Parent-Meta aktualisieren via SQLAlchemy
        meta = parent.meta if isinstance(parent.meta, dict) else {}
        meta["auto_completed_by"] = auto_meta
        parent.meta = meta
        parent.status = "done"
        db_or_conn.add(TaskHistory(
            task_id=parent_id,
            event="parent_auto_completed",
            agent="system",
            details=auto_meta,
        ))
        db_or_conn.commit()
    else:
        # Parent-Meta via sqlite3 aktualisieren
        cur = db_or_conn.cursor() if hasattr(db_or_conn, "cursor") else db_or_conn
        # Aktuelle Meta laden
        cur.execute("SELECT meta FROM tasks WHERE id = ?", (parent_id,))
        pm_row = cur.fetchone()
        if pm_row:
            if hasattr(pm_row, "keys"):
                pm_dict = dict(pm_row)
            else:
                pm_dict = {"meta": pm_row[0]}
        else:
            pm_dict = {"meta": None}
        cur_meta = pm_dict.get("meta")
        if isinstance(cur_meta, str):
            try:
                cur_meta = json.loads(cur_meta)
            except (json.JSONDecodeError, TypeError):
                cur_meta = {}
        cur_meta = cur_meta if isinstance(cur_meta, dict) else {}
        cur_meta["auto_completed_by"] = auto_meta
        cur.execute(
            "UPDATE tasks SET status = 'done', meta = ? WHERE id = ?",
            (json.dumps(cur_meta), parent_id),
        )
        cur.execute(
            """INSERT INTO task_history
               (task_id, ts, event, agent, tokens_in, tokens_out, cost_usd, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (parent_id, now, "parent_auto_completed", "system",
             0, 0, 0.0, json.dumps(auto_meta)),
        )
        if hasattr(db_or_conn, "commit"):
            db_or_conn.commit()
        else:
            cur.connection.commit()

    logger.info(
        f"Parent {parent_id[:8]} auto-completed: "
        f"{len(sibling_statuses)} Subtasks, Cost=${total_cost:.4f}"
    )
    return parent_id


def check_all_parents_for_completion(db_or_conn) -> list:
    """Prueft ALLE Parents mit laufenden Subtasks. Wird vom Auto-Triage-Operator aufgerufen.

    Returns:
        Liste der auto-completeten Parent-IDs
    """
    import json
    if hasattr(db_or_conn, "execute"):
        cur = db_or_conn
    else:
        cur = db_or_conn.cursor() if hasattr(db_or_conn, "cursor") else db_or_conn
    cur.execute("SELECT DISTINCT parent_id FROM tasks WHERE parent_id IS NOT NULL AND status != 'done'")
    rows = cur.fetchall()
    parent_ids = [r[0] if not hasattr(r, "keys") else r["parent_id"] for r in rows]
    completed = []
    for pid in parent_ids:
        # Setze Status-Check: nur Parents pruefen, die nicht bereits done sind
        cur.execute("SELECT status FROM tasks WHERE id = ?", (pid,))
        sr = cur.fetchone()
        st = sr[0] if not hasattr(sr, "keys") else sr["status"]
        if st == "done":
            continue
        # Suche ein Subtask zum Triggern
        cur.execute("SELECT id FROM tasks WHERE parent_id = ? LIMIT 1", (pid,))
        st_row = cur.fetchone()
        if not st_row:
            continue
        sid = st_row[0] if not hasattr(st_row, "keys") else st_row["id"]
        result = check_and_complete_parent(db_or_conn, sid)
        if result:
            completed.append(result)
    return completed