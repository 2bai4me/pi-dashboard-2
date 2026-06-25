"""ProjectService — Business-Logic fuer Projects."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models.project import Project
from ..models.task import Task

logger = logging.getLogger("pi-dashboard-2")


def _gen_id() -> str:
    """12-Zeichen-Hex-ID."""
    return secrets.token_hex(6)


class ProjectService:
    """Service-Klasse fuer Project-Operationen."""

    @staticmethod
    def list_projects(db: Session) -> List[Project]:
        return list(db.execute(select(Project).order_by(Project.created_at.desc())).scalars())

    @staticmethod
    def get_project(db: Session, project_id: str) -> Optional[Project]:
        return db.get(Project, project_id)

    @staticmethod
    def create_project(db: Session, name: str, description: Optional[str] = None,
                       mode: str = "preparation", category: str = "new_request") -> Project:
        p = Project(
            id=_gen_id(),
            name=name,
            description=description,
            mode=mode,
            category=category,
            status="active",
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        logger.info(f"Project created: {p.id} '{p.name}' mode={p.mode}")
        return p

    @staticmethod
    def update_project(db: Session, project_id: str, **fields) -> Optional[Project]:
        # Felder, die explizit auf null gesetzt werden duerfen (z.B. SOP-Auswahl aufheben)
        # Standardmaessig werden None-Werte ignoriert, um versehentliche Loeschungen zu vermeiden.
        NULLABLE_FIELDS = {"default_sop_id"}
        p = db.get(Project, project_id)
        if not p:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(p, k):
                setattr(p, k, v)
            elif k in NULLABLE_FIELDS and v is None and hasattr(p, k):
                setattr(p, k, None)  # explizit null fuer nullable Felder
        p.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(p)
        return p

    @staticmethod
    def set_mode(db: Session, project_id: str, mode: str, note: Optional[str] = None) -> Optional[Project]:
        """Setzt Modus (preparation/execution/paused/completed) + erzeugt ggf. Abschlussbericht."""
        from .task_service import TaskService  # lazy import
        p = db.get(Project, project_id)
        if not p:
            return None
        old_mode = p.mode
        p.mode = mode
        p.updated_at = datetime.utcnow()
        if mode == "completed" and old_mode != "completed":
            # Abschlussbericht generieren
            report = TaskService.generate_completion_report(db, p)
            p.completion_report = report
            p.closed_at = datetime.utcnow()
            p.status = "archived"
            logger.info(f"Project {p.id} completed — report generated")
        db.commit()
        db.refresh(p)
        return p

    @staticmethod
    def delete_project(db: Session, project_id: str) -> bool:
        p = db.get(Project, project_id)
        if not p:
            return False
        db.delete(p)
        db.commit()
        return True

    @staticmethod
    def project_stats(db: Session, project: Project) -> Dict[str, int]:
        """Counts: tasks_done, tasks_in_progress, tasks_open, total_cost_usd, task_count.

        tasks_open = nicht (done | cancelled) = alle offenen Tasks.
        Basiert auf User-Direktive 23.06.2026 (Task dad90780eb76): Frontend-Kachel
        soll immer die Anzahl OFFENER Tasks anzeigen, nicht nur die Gesamtzahl.

        DEPRECATED: Benutze project_stats_bulk() fuer bessere Performance
        bei vielen Projekten (User-Direktive 24.06.2026, Performance-Audit).
        """
        return ProjectService.project_stats_bulk(db, [project.id]).get(project.id, {
            "task_count": 0, "tasks_done": 0, "tasks_cancelled": 0,
            "tasks_in_progress": 0, "tasks_open": 0, "total_cost_usd": 0.0,
        })

    @staticmethod
    def project_stats_bulk(db: Session, project_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """Berechnet Stats fuer MEHRERE Projekte in EINER Query (Performance-Fix).

        Vermeidet N+1: Statt N Queries (eine pro Projekt) wird EINE aggregierte
        Query ausgefuehrt, die alle Projekt-Stats zurueckgibt.

        Performance (User-Direktive 24.06.2026):
          - Vorher: 4 Projekte * 1.5s = 6s fuer /api/projects
          - Nachher: 1 Query mit GROUP BY = <50ms

        Returns:
            Dict project_id -> {task_count, tasks_done, ..., total_cost_usd}
        """
        if not project_ids:
            return {}
        from ..models.history import TaskHistory
        from sqlalchemy import func as sqlfunc

        OPEN_STATUSES = ("triage", "in_progress", "review", "block", "failed",
                         "rueckfrage", "todo", "go", "wait")

        # === EINE aggregierte Query statt N+1 ===
        # GROUP BY project_id, status -> wir wissen, wie viele Tasks pro Status pro Projekt
        rows = db.execute(
            select(
                Task.project_id,
                Task.status,
                sqlfunc.count(Task.id).label("count"),
            )
            .where(Task.project_id.in_(project_ids))
            .group_by(Task.project_id, Task.status)
        ).all()

        # Initialisiere leere Stats pro Projekt
        result: Dict[str, Dict[str, int]] = {}
        for pid in project_ids:
            result[pid] = {
                "task_count": 0,
                "tasks_done": 0,
                "tasks_cancelled": 0,
                "tasks_in_progress": 0,
                "tasks_open": 0,
                "total_cost_usd": 0.0,
            }

        # Aggregiere die Ergebnisse
        for project_id, status, count in rows:
            stats = result[project_id]
            stats["task_count"] += count
            if status == "done":
                stats["tasks_done"] += count
            elif status == "cancelled":
                stats["tasks_cancelled"] += count
            elif status == "in_progress":
                stats["tasks_in_progress"] += count
            if status in OPEN_STATUSES:
                stats["tasks_open"] += count

        # === Total cost: EINE aggregierte SUM-Query ===
        cost_rows = db.execute(
            select(
                Task.project_id,
                sqlfunc.coalesce(sqlfunc.sum(TaskHistory.cost_usd), 0).label("total_cost"),
            )
            .join(Task, Task.id == TaskHistory.task_id)
            .where(Task.project_id.in_(project_ids))
            .group_by(Task.project_id)
        ).all()
        for project_id, total_cost in cost_rows:
            result[project_id]["total_cost_usd"] = float(total_cost)

        return result
