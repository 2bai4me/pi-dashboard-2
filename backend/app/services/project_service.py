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
        p = db.get(Project, project_id)
        if not p:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(p, k):
                setattr(p, k, v)
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
        """Counts: tasks_done, tasks_in_progress, total_cost_usd, task_count."""
        from ..models.history import TaskHistory
        from ..services.pricing_service import calc_cost_from_snapshot

        tasks = list(db.execute(
            select(Task).where(Task.project_id == project.id)
        ).scalars())
        done = sum(1 for t in tasks if t.status == "done")
        in_prog = sum(1 for t in tasks if t.status == "in_progress")

        # Total cost: SUM aus TokenUsage (per-task aggregiert)
        # Schnellweg: SUM cost_usd aus task_history
        from sqlalchemy import func as sqlfunc
        total_cost = db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(TaskHistory.cost_usd), 0))
            .join(Task, Task.id == TaskHistory.task_id)
            .where(Task.project_id == project.id)
        ).scalar() or 0
        return {
            "task_count":    len(tasks),
            "tasks_done":    done,
            "tasks_in_progress": in_prog,
            "total_cost_usd": float(total_cost),
        }
