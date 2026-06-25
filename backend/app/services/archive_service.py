"""Archivierungs-Service (User-Direktive 24.06.2026).

Verschiebt abgeschlossene Tasks (done) und stornierte Tasks (cancelled)
aus der operativen Datenbank in eine separate Archiv-DB.
"""
from __future__ import annotations

import json as _json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from ..config import settings

logger = logging.getLogger("pi-dashboard-2.archive")


def get_archive_db_path() -> Path:
    """Pfad zur Archiv-DB."""
    main_path = Path(settings.DATABASE_URL.replace("sqlite:///", ""))
    return main_path.parent / "pi_dashboard_archive.db"


def init_archive_db(archive_path: Optional[Path] = None) -> None:
    """Erstellt die Archiv-DB mit dem noetigen Schema.

    User-Direktive 24.06.2026: Schema folgt dem operativen Task-Model.
    Falls die Archiv-DB bereits mit einem alten Schema existiert, wird sie
    automatisch um fehlende Spalten erweitert.
    """
    archive_path = archive_path or get_archive_db_path()
    conn = sqlite3.connect(str(archive_path), timeout=30)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
        id VARCHAR(32) PRIMARY KEY,
        title VARCHAR(500),
        description TEXT,
        status VARCHAR(32),
        priority INTEGER,
        category VARCHAR(32),
        assigned_role VARCHAR(64),
        assigned_subagent VARCHAR(64),
        iteration_count INTEGER DEFAULT 0,
        "order" INTEGER DEFAULT 0,
        emergency BOOLEAN DEFAULT 0,
        pricing_snapshot TEXT,
        tags TEXT,
        success_criteria TEXT,
        meta TEXT,
        task_type VARCHAR(32),
        implementation_plan TEXT,
        standards_check TEXT,
        subagent_readiness TEXT,
        project_id VARCHAR(32),
        parent_id VARCHAR(32),
        created_at DATETIME,
        updated_at DATETIME,
        claimed_at DATETIME,
        archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_archive_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_archive_tasks_project ON tasks(project_id);
    CREATE INDEX IF NOT EXISTS idx_archive_tasks_updated ON tasks(updated_at);

    CREATE TABLE IF NOT EXISTS task_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id VARCHAR(32),
        ts DATETIME,
        event VARCHAR(64),
        session_id VARCHAR(64),
        agent VARCHAR(64),
        model VARCHAR(128),
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        cost_usd NUMERIC(12, 6) DEFAULT 0,
        details TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_archive_history_task ON task_history(task_id);
    """)
    conn.commit()

    # === Schema-Migration: fehlende Spalten hinzufuegen ===
    cur = conn.cursor()
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(tasks)").fetchall()}
    required_cols = {
        "task_type": "VARCHAR(32)",
        "standards_check": "TEXT",
        "subagent_readiness": "TEXT",
    }
    for col_name, col_def in required_cols.items():
        if col_name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}")
                logger.info(f"Archiv-DB-Schema: Spalte '{col_name}' hinzugefuegt")
            except Exception as e:
                logger.warning(f"ALTER TABLE tasks ADD COLUMN {col_name} fehlgeschlagen: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Archiv-DB initialisiert: {archive_path}")


def json_dumps(obj):
    """Sichere JSON-Serialisierung."""
    if obj is None:
        return None
    try:
        return _json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return None


def archive_done_tasks(
    db: Session,
    keep_last_n_done: int = 10,
    keep_last_n_cancelled: int = 10,
    archive_older_than_days: float = 1.0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Verschiebt fertige Tasks in die Archiv-DB (User-Direktive 24.06.2026).

    Standard-Verhalten (Cron-Job):
      - done-Tasks UND cancelled-Tasks aelter als archive_older_than_days
      - Behalte die letzten keep_last_n_done/cancelled in der operativen DB
      - So werden alte Tasks automatisch aufgeraeumt, ohne dass die
        UI-Anzeige der letzten Done-Tasks verloren geht.

    Args:
        keep_last_n_done: Die letzten N done-Tasks in der operativen DB behalten
        keep_last_n_cancelled: Die letzten N cancelled-Tasks in der operativen DB behalten
        archive_older_than_days: Nur Tasks aelter als X Tage archivieren
                                    (Schutz vor Archivierung gerade abgeschlossener Tasks)
        dry_run: Nur zaehlen, nicht tatsaechlich archivieren
    """
    archive_path = get_archive_db_path()
    init_archive_db(archive_path)

    from ..models.task import Task
    from ..models.history import TaskHistory
    from datetime import timedelta

    # Altersgrenze
    cutoff = datetime.utcnow() - timedelta(days=archive_older_than_days)

    # Zaehlen Total
    done_count_total = db.execute(
        select(func.count(Task.id)).where(Task.status == "done")
    ).scalar() or 0
    cancelled_count_total = db.execute(
        select(func.count(Task.id)).where(Task.status == "cancelled")
    ).scalar() or 0

    # Zu archivierende done-Tasks:
    # 1. status = done
    # 2. updated_at < cutoff (aelter als 1 Tag)
    # 3. Sortiert nach updated_at DESC, ueberspringe die letzten keep_last_n_done
    #    (die juengsten bleiben, auch wenn sie aelter als 1 Tag sind)
    done_to_archive = db.execute(
        select(Task)
        .where(
            (Task.status == "done")
            & (Task.updated_at < cutoff)
        )
        .order_by(Task.updated_at.desc())
        .offset(keep_last_n_done)
    ).scalars().all()
    done_count = len(done_to_archive)

    # Zu archivierende cancelled-Tasks (analog)
    cancelled_to_archive = db.execute(
        select(Task)
        .where(
            (Task.status == "cancelled")
            & (Task.updated_at < cutoff)
        )
        .order_by(Task.updated_at.desc())
        .offset(keep_last_n_cancelled)
    ).scalars().all()
    cancelled_count = len(cancelled_to_archive)

    total_to_archive = done_count + cancelled_count

    if dry_run:
        return {
            "dry_run": True,
            "done_total": done_count_total,
            "cancelled_total": cancelled_count_total,
            "keep_last_n_done": keep_last_n_done,
            "keep_last_n_cancelled": keep_last_n_cancelled,
            "archive_older_than_days": archive_older_than_days,
            "would_archive_done": done_count,
            "would_archive_cancelled": cancelled_count,
            "archive_path": str(archive_path),
        }

    if total_to_archive == 0:
        return {
            "done_total": done_count_total,
            "cancelled_total": cancelled_count_total,
            "keep_last_n_done": keep_last_n_done,
            "keep_last_n_cancelled": keep_last_n_cancelled,
            "archive_older_than_days": archive_older_than_days,
            "done_archived": 0,
            "cancelled_archived": 0,
            "history_moved": 0,
            "archive_path": str(archive_path),
            "message": "Nichts zu archivieren (alles innerhalb der Altersgrenze oder zu wenige)",
        }

    # Archiv-DB verbinden und Tasks + History kopieren
    archive_conn = sqlite3.connect(str(archive_path), timeout=60)
    archive_cur = archive_conn.cursor()
    archive_conn.execute("BEGIN IMMEDIATE")

    history_moved = 0
    done_archived = 0
    cancelled_archived = 0
    errors = []

    def _archive_task(task_obj):
        nonlocal history_moved
        try:
            # 1. Task in Archiv-DB kopieren (nur existierende Attribute)
            archive_cur.execute("""
                INSERT OR REPLACE INTO tasks
                (id, title, description, status, priority, category,
                 assigned_role, assigned_subagent, success_criteria, tags,
                 project_id, parent_id, iteration_count, "order", emergency,
                 pricing_snapshot, implementation_plan, meta,
                 task_type, standards_check, subagent_readiness,
                 created_at, updated_at, claimed_at,
                 archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_obj.id, task_obj.title, task_obj.description, task_obj.status,
                task_obj.priority, task_obj.category, task_obj.assigned_role,
                task_obj.assigned_subagent,
                json_dumps(task_obj.success_criteria),
                json_dumps(task_obj.tags),
                task_obj.project_id, task_obj.parent_id,
                task_obj.iteration_count, task_obj.order,
                task_obj.emergency,
                json_dumps(task_obj.pricing_snapshot),
                json_dumps(task_obj.implementation_plan),
                json_dumps(task_obj.meta),
                getattr(task_obj, "task_type", None),
                json_dumps(getattr(task_obj, "standards_check", None)),
                json_dumps(getattr(task_obj, "subagent_readiness", None)),
                task_obj.created_at, task_obj.updated_at, task_obj.claimed_at,
                datetime.utcnow()
            ))

            # 2. History-Eintraege kopieren
            history_rows = db.execute(
                select(TaskHistory).where(TaskHistory.task_id == task_obj.id)
            ).scalars().all()
            for h in history_rows:
                archive_cur.execute("""
                    INSERT INTO task_history
                    (task_id, ts, event, session_id, agent, model,
                     tokens_in, tokens_out, cost_usd, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    h.task_id, h.ts, h.event, h.session_id, h.agent, h.model,
                    h.tokens_in, h.tokens_out, float(h.cost_usd or 0),
                    json_dumps(h.details)
                ))
                history_moved += 1

            # 3. History aus operativer DB loeschen
            db.execute(
                TaskHistory.__table__.delete().where(TaskHistory.task_id == task_obj.id)
            )

            # 4. Task aus operativer DB loeschen
            db.delete(task_obj)
            return True, None
        except Exception as e:
            return False, str(e)

    for task_obj in done_to_archive:
        ok, err = _archive_task(task_obj)
        if ok:
            done_archived += 1
        else:
            errors.append(f"done {task_obj.id}: {err}")

    for task_obj in cancelled_to_archive:
        ok, err = _archive_task(task_obj)
        if ok:
            cancelled_archived += 1
        else:
            errors.append(f"cancelled {task_obj.id}: {err}")

    archive_conn.commit()
    archive_conn.close()
    db.commit()

    # Cache invalidieren
    try:
        from ..cache import invalidate_cache
        invalidate_cache()
    except Exception:
        pass

    # WAL-Checkpoint
    try:
        db.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        db.commit()
    except Exception as e:
        logger.warning(f"WAL-Checkpoint fehlgeschlagen: {e}")

    logger.info(
        f"Archivierung: done={done_archived} (aelter als {archive_older_than_days}d), "
        f"cancelled={cancelled_archived}, history_moved={history_moved}, errors={len(errors)}"
    )

    return {
        "done_total": done_count_total,
        "cancelled_total": cancelled_count_total,
        "keep_last_n_done": keep_last_n_done,
        "keep_last_n_cancelled": keep_last_n_cancelled,
        "archive_older_than_days": archive_older_than_days,
        "done_archived": done_archived,
        "cancelled_archived": cancelled_archived,
        "history_moved": history_moved,
        "archive_path": str(archive_path),
        "errors": errors,
    }


def get_archive_stats() -> Dict[str, Any]:
    """Gibt Statistiken ueber die Archiv-DB zurueck."""
    archive_path = get_archive_db_path()
    if not archive_path.exists():
        return {"exists": False, "path": str(archive_path)}

    conn = sqlite3.connect(str(archive_path), timeout=10)
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    by_status = dict(cur.execute(
        "SELECT status, COUNT(*) FROM tasks GROUP BY status"
    ).fetchall())
    total_history = cur.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
    oldest = cur.execute("SELECT MIN(archived_at) FROM tasks").fetchone()[0]
    newest = cur.execute("SELECT MAX(archived_at) FROM tasks").fetchone()[0]
    conn.close()
    return {
        "exists": True,
        "path": str(archive_path),
        "size_mb": round(archive_path.stat().st_size / 1024 / 1024, 2),
        "total_tasks": total,
        "by_status": by_status,
        "total_history": total_history,
        "oldest_archived": oldest,
        "newest_archived": newest,
    }
